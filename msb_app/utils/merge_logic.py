"""
Lógica de ligação entre os vários ficheiros para construir o `maintenance.csv`
final, conforme descrito no documento do projeto:

1. maintenance_profiles_FINAL <-> cars.csv, via msbKey (ambos em minúsculas)
   -> contagem de carId's por id/msbkey.
2. Ligação a Matriculas.csv, via CARID (que vem do cars.csv, coluna carId)
   -> preenche colunas [matricula] e [VIN] e conta "leasys matriculas" por id.
3. Ligação a kinto_prioridade.csv, pelo nome da marca (make)
   -> preenche a coluna [kinto prioridade].
4. Coluna [kinto]: ids com status "Ativo" e contagem_carids > 0 são
   kinto (contagem_carids == 0 significa que só existem carId's de outro
   país, ex.: "SQ", e por isso não contam). Ids com status
   "Descontinuado" também precisam de contagem_carids > 0, e além disso
   só são kinto se o maxEndDate estiver a, no máximo, "1 ano" de
   distância da data de referência (por omissão, hoje) — em qualquer
   sentido (passado ou futuro).

Nota sobre suposições assumidas (a rever/ajustar conforme o negócio real):
- "contagem de carid's por id" = nº de carId distintos em cars.csv para
  aquele msbKey (apenas os que tiverem country == "PO").
- "leasys matriculas" = nº de matrículas encontradas (via CARID) para os
  veículos daquele msbkey.
- As colunas [matricula] e [VIN] mostram, para cada id, a lista de
  matrículas/VINs encontrados (separados por ", "), já que um id pode ter
  vários carId's e portanto várias matrículas.
- [checkdate] e [observações] ficam vazias — são campos de preenchimento
  manual (editáveis no Dashboard).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _norm_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def _norm_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def merge_maintenance_cars(
    maintenance_profiles_final: pd.DataFrame,
    cars: pd.DataFrame,
    msbkey_col_profiles: str = "msbKey",
    msbkey_col_cars: str = "msbKey",
    carid_col: str = "carId",
    country_col: str = "country",
    country_filter: str | None = "PO",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Liga maintenance_profiles_FINAL a cars.csv pelo msbKey (em minúsculas).
    Devolve (maintenance_base, cars_filtrado) — o segundo é reutilizado
    depois para a ligação às matrículas.

    Se `country_filter` for indicado (por omissão "PO"), só são contados os
    carId cujo `country` seja igual a esse valor — carId's de outros países
    (ex.: "SQ") são ignorados, resultando em contagem 0 quando não existir
    nenhum carId "PO" para aquele msbKey.
    """
    mp = maintenance_profiles_final.copy()
    cars = cars.copy()

    if msbkey_col_profiles not in mp.columns:
        raise ValueError(f"Coluna '{msbkey_col_profiles}' não encontrada em maintenance_profiles_FINAL.")
    if msbkey_col_cars not in cars.columns:
        raise ValueError(f"Coluna '{msbkey_col_cars}' não encontrada em cars.csv.")

    mp["_msbkey_norm"] = _norm_key(mp[msbkey_col_profiles])
    cars["_msbkey_norm"] = _norm_key(cars[msbkey_col_cars])

    # Filtrar apenas os carId's do país pretendido (ex.: "PO").
    if country_filter and country_col in cars.columns:
        cars = cars[_norm_text(cars[country_col]) == country_filter.strip().upper()]

    # Contagem de carId's (distintos) por msbKey
    carid_counts = (
        cars.groupby("_msbkey_norm")[carid_col]
        .nunique()
        .rename("contagem_carids")
        .reset_index()
    )

    base = mp.merge(carid_counts, on="_msbkey_norm", how="left")
    base["contagem_carids"] = base["contagem_carids"].fillna(0).astype(int)

    return base, cars


def merge_matriculas(
    base: pd.DataFrame,
    cars_norm: pd.DataFrame,
    matriculas: pd.DataFrame,
    carid_col_cars: str = "carId",
    carid_col_matriculas: str = "CARID",
    matricula_col: str = "Matricula",
    vin_col: str = "VIN",
) -> pd.DataFrame:
    """
    Liga cars.csv (que tem carId + msbKey) às matrículas (que têm CARID),
    agrega ao nível do msbkey/id e junta ao `base`.
    """
    cars = cars_norm.copy()
    mt = matriculas.copy()

    if carid_col_cars not in cars.columns:
        raise ValueError(f"Coluna '{carid_col_cars}' não encontrada em cars.csv.")
    if carid_col_matriculas not in mt.columns:
        raise ValueError(f"Coluna '{carid_col_matriculas}' não encontrada em Matriculas.csv.")

    cars["_carid_norm"] = cars[carid_col_cars].astype(str).str.strip()
    mt["_carid_norm"] = mt[carid_col_matriculas].astype(str).str.strip()

    ligado = cars[["_msbkey_norm", "_carid_norm"]].drop_duplicates().merge(
        mt, on="_carid_norm", how="inner"
    )

    if matricula_col in ligado.columns:
        matriculas_por_id = (
            ligado.groupby("_msbkey_norm")[matricula_col]
            .apply(lambda s: ", ".join(sorted(set(s.dropna().astype(str)))))
            .rename("matricula")
        )
        leasys_por_id = (
            ligado.groupby("_msbkey_norm")[matricula_col]
            .nunique()
            .rename("leasys_matriculas")
        )
    else:
        matriculas_por_id = pd.Series(dtype=str, name="matricula")
        leasys_por_id = pd.Series(dtype=int, name="leasys_matriculas")

    if vin_col in ligado.columns:
        vin_por_id = (
            ligado.groupby("_msbkey_norm")[vin_col]
            .apply(lambda s: ", ".join(sorted(set(s.dropna().astype(str)))))
            .rename("VIN")
        )
    else:
        vin_por_id = pd.Series(dtype=str, name="VIN")

    result = base.merge(matriculas_por_id, on="_msbkey_norm", how="left")
    result = result.merge(vin_por_id, on="_msbkey_norm", how="left")
    result = result.merge(leasys_por_id, on="_msbkey_norm", how="left")

    result["matricula"] = result["matricula"].fillna("")
    result["VIN"] = result["VIN"].fillna("")
    result["leasys_matriculas"] = result["leasys_matriculas"].fillna(0).astype(int)

    return result


def merge_kinto_prioridade(
    df: pd.DataFrame,
    kinto_prioridade: pd.DataFrame,
    make_col: str = "make",
) -> pd.DataFrame:
    """
    Preenche a coluna [kinto prioridade], fazendo lookup pelo nome da marca
    no ficheiro kinto_prioridade.csv (colunas: nº prioridade ; make).
    """
    df = df.copy()
    kp = kinto_prioridade.copy()

    # O ficheiro tem 2 colunas: a 1ª é o número de prioridade, a 2ª a marca.
    # Usamos posição em vez do nome exato do cabeçalho, para maior robustez.
    col_prioridade, col_make = kp.columns[0], kp.columns[1]

    kp["_make_norm"] = _norm_text(kp[col_make])
    lookup = dict(zip(kp["_make_norm"], kp[col_prioridade]))

    if make_col not in df.columns:
        raise ValueError(f"Coluna '{make_col}' não encontrada para o lookup de kinto prioridade.")

    df["kinto_prioridade"] = _norm_text(df[make_col]).map(lookup)
    return df


def compute_kinto(
    df: pd.DataFrame,
    date_col: str = "maxEndDate",
    status_col: str = "status",
    carid_count_col: str = "contagem_carids",
    ref_date: pd.Timestamp | None = None,
    dias_limite: int = 365,
) -> pd.Series:
    """
    Regra do "kinto":
    - status "Ativo"          -> é kinto, desde que tenha pelo menos 1
      carid contado (contagem_carids > 0). Um id com contagem_carids == 0
      só tem carid's de outro país (ex.: "SQ"), por isso não conta.
    - status "Descontinuado"  -> só é kinto se tiver contagem_carids > 0 E
      o maxEndDate estiver a, no máximo, `dias_limite` dias (por omissão,
      1 ano) de distância da data de referência (por omissão, hoje) — em
      qualquer sentido, passado ou futuro.
    - qualquer outro status   -> nunca é kinto.
    """
    if ref_date is None:
        ref_date = pd.Timestamp.today().normalize()

    if status_col not in df.columns:
        return pd.Series([""] * len(df), index=df.index)

    status_norm = df[status_col].astype(str).str.strip().str.lower()
    is_ativo = status_norm == "ativo"
    is_descontinuado = status_norm == "descontinuado"

    if carid_count_col in df.columns:
        tem_carids = pd.to_numeric(df[carid_count_col], errors="coerce").fillna(0) > 0
    else:
        # Sem a coluna de contagem, não filtramos por carid's (mantém o comportamento antigo)
        tem_carids = pd.Series(True, index=df.index)

    if date_col in df.columns:
        dates = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        diff_days = (dates - ref_date).dt.days.abs()
        descontinuado_dentro_prazo = is_descontinuado & dates.notna() & (diff_days <= dias_limite)
    else:
        descontinuado_dentro_prazo = pd.Series(False, index=df.index)

    kinto = np.where(tem_carids & (is_ativo | descontinuado_dentro_prazo), "kinto", "")
    return pd.Series(kinto, index=df.index)


def compute_anos_diferenca(
    df: pd.DataFrame,
    date_col: str = "maxEndDate",
    ref_date: pd.Timestamp | None = None,
) -> pd.Series:
    """
    Diferença, em anos completos, entre `maxEndDate` e a data de referência
    (por omissão, hoje) — em valor absoluto (não interessa se é passado ou
    futuro, só "há quantos anos de distância"). Linhas sem `maxEndDate`
    (vazias) ficam a 0 anos, ou seja, tratadas como as mais recentes.
    """
    if ref_date is None:
        ref_date = pd.Timestamp.today().normalize()

    if date_col not in df.columns:
        return pd.Series(0, index=df.index, dtype=int)

    dates = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    dif_dias = (dates - ref_date).abs().dt.days
    dif_dias = dif_dias.fillna(0)
    anos = (dif_dias // 365).astype(int)
    return anos


def build_maintenance(
    maintenance_profiles_final: pd.DataFrame,
    cars: pd.DataFrame,
    matriculas: pd.DataFrame | None,
    kinto_prioridade: pd.DataFrame | None,
    ref_date: pd.Timestamp | None = None,
    country_filter: str | None = "PO",
) -> pd.DataFrame:
    """Pipeline completo de construção do maintenance.csv."""
    base, cars_norm = merge_maintenance_cars(
        maintenance_profiles_final, cars, country_filter=country_filter
    )

    if matriculas is not None and not matriculas.empty:
        base = merge_matriculas(base, cars_norm, matriculas)
    else:
        base["matricula"] = ""
        base["VIN"] = ""
        base["leasys_matriculas"] = 0

    if kinto_prioridade is not None and not kinto_prioridade.empty:
        base = merge_kinto_prioridade(base, kinto_prioridade)
    else:
        base["kinto_prioridade"] = np.nan

    base["kinto"] = compute_kinto(base, ref_date=ref_date)
    base["anos_diferenca"] = compute_anos_diferenca(base, ref_date=ref_date)

    # Colunas de preenchimento manual
    if "checkdate" not in base.columns:
        base["checkdate"] = ""
    if "observacoes" not in base.columns:
        base["observacoes"] = ""

    base = base.drop(columns=["_msbkey_norm"], errors="ignore")
    base = add_copy_key_counts(base)
    return base


def add_copy_key_counts(
    df: pd.DataFrame,
    source_cols: tuple[tuple[str, str], ...] = (
        ("quality3_key", "copy_q3"),
        ("quality2_key", "copy_q2"),
    ),
    anchor_col: str = "contagem_carids",
) -> pd.DataFrame:
    """
    Para cada linha, conta quantas linhas do ficheiro têm exactamente o
    mesmo valor de `quality3_key` (-> copy_q3) e de `quality2_key`
    (-> copy_q2). Linhas com a chave vazia são contadas todas juntas.

    As colunas resultantes ficam imediatamente a seguir a `contagem_carids`.
    """
    df = df.copy()
    novas: list[str] = []
    for src, dest in source_cols:
        if src not in df.columns:
            continue
        chave = df[src].fillna("").astype(str)
        df[dest] = chave.groupby(chave).transform("size").astype(int)
        novas.append(dest)

    if novas and anchor_col in df.columns:
        cols = [c for c in df.columns if c not in novas]
        pos = cols.index(anchor_col) + 1
        cols[pos:pos] = novas
        df = df[cols]
    return df


def quality_ratio_by_make(
    df: pd.DataFrame,
    quality_col: str = "msbQuality",
    make_col: str = "make",
    weight_col: str | None = "contagem_carids",
    grupo_alto: tuple[int, ...] = (2, 3, 4),
    grupo_baixo: tuple[int, ...] = (0, 1),
) -> pd.DataFrame:
    """
    Calcula, por marca, a relação entre:
    - soma (ou contagem, se weight_col=None) de qualidade em `grupo_alto`
      (por omissão, 2/3/4) vs. o total;
    - soma/contagem de qualidade em `grupo_baixo` (por omissão, 0/1) vs. o
      total.

    Se `weight_col` for indicado, soma essa coluna (ex.: contagem_carids
    -> relação por nº de carid's). Se `weight_col` for None, conta o nº
    de linhas (ex.: relação por nº de msbs/ids).
    """
    d = df.copy()
    if make_col not in d.columns or quality_col not in d.columns:
        return pd.DataFrame()

    d[quality_col] = pd.to_numeric(d[quality_col], errors="coerce")

    if weight_col and weight_col in d.columns:
        peso = pd.to_numeric(d[weight_col], errors="coerce").fillna(0)
    else:
        peso = pd.Series(1, index=d.index)

    d["_grupo"] = np.select(
        [d[quality_col].isin(grupo_alto), d[quality_col].isin(grupo_baixo)],
        ["alta", "baixa"],
        default="outra",
    )
    d["_peso"] = peso

    pivot = d.groupby([make_col, "_grupo"])["_peso"].sum().unstack(fill_value=0)
    for col in ("alta", "baixa", "outra"):
        if col not in pivot.columns:
            pivot[col] = 0

    pivot["total"] = pivot[["alta", "baixa", "outra"]].sum(axis=1)
    pivot = pivot[pivot["total"] > 0]
    pivot["pct_alta"] = pivot["alta"] / pivot["total"]
    pivot["pct_baixa"] = pivot["baixa"] / pivot["total"]

    resultado = pivot.reset_index().sort_values("total", ascending=False)
    resultado = resultado.rename(columns={
        make_col: "make",
        "alta": "qtd_qualidade_234",
        "baixa": "qtd_qualidade_01",
    })
    return resultado[[
        "make", "total", "qtd_qualidade_234", "pct_alta",
        "qtd_qualidade_01", "pct_baixa",
    ]]
