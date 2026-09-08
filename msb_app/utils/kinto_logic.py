"""
Fase 3 — Kinto Analisis.

Ficheiros mensais como 'kinto_Maintenance_Profile_2026_02_13.csv' e
'kinto_Vehicle_All_2026_06_15.csv' têm sempre a mesma estrutura; o que
muda é o número de linhas e a data no nome. Este módulo trata de:

1. Extrair (ano, mês) do nome do ficheiro por regex.
2. Acrescentar cada mês importado a uma tabela histórica persistida
   (kinto_Maintenance_Profile), substituindo (upsert) o mês caso já
   tenha sido importado antes. O kinto_Vehicle_All NÃO é histórico —
   cada novo ficheiro substitui inteiramente o anterior (só interessa o
   mês mais recente).
3. Ligar o histórico kinto_Maintenance_Profile ao maintenance.csv da
   Fase 1, restringido às linhas com kinto == "kinto" (só faz sentido
   comparar o que já sabemos ser kinto no nosso sistema).
4. Calcular a diferença mês-a-mês (o que realmente mudou desde o mês
   anterior), como alternativa à vista acumulada.
5. Para o kinto_Vehicle_All (último ficheiro), calcular a relação entre
   o total de carid's desse export e o total de carid's do
   maintenance.csv (linhas kinto), por marca — e a distribuição de
   qualidade dessas mesmas linhas.
"""
from __future__ import annotations

import re

import pandas as pd

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

FILENAME_DATE_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})")


def extract_ano_mes(filename: str) -> tuple[int | None, int | None]:
    """Extrai (ano, mês) do nome do ficheiro, ex.: '..._2026_02_13.csv' -> (2026, 2)."""
    m = FILENAME_DATE_RE.search(filename)
    if not m:
        return None, None
    ano_str, mes_str, _dia = m.groups()
    try:
        ano, mes = int(ano_str), int(mes_str)
    except ValueError:
        return None, None
    if not (1 <= mes <= 12):
        return ano, None
    return ano, mes


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Devolve o nome real da 1ª coluna de `df` que bata (sem distinguir
    maiúsculas/minúsculas) com algum dos nomes candidatos."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def upsert_monthly(
    df_existing: pd.DataFrame | None,
    df_new: pd.DataFrame,
    ano: int,
    mes: int,
) -> pd.DataFrame:
    """
    Acrescenta `df_new` (com as colunas 'ano'/'mes' preenchidas) ao
    histórico existente, substituindo linhas já existentes para o mesmo
    (ano, mes) — permite reimportar/corrigir um mês sem duplicar dados.
    """
    df_new = df_new.copy()
    df_new["ano"] = ano
    df_new["mes"] = mes

    if df_existing is None or df_existing.empty:
        return df_new

    df_existing = df_existing.copy()
    df_existing["ano"] = pd.to_numeric(df_existing["ano"], errors="coerce")
    df_existing["mes"] = pd.to_numeric(df_existing["mes"], errors="coerce")

    mask_manter = ~((df_existing["ano"] == ano) & (df_existing["mes"] == mes))
    return pd.concat([df_existing[mask_manter], df_new], ignore_index=True)


def filter_kinto(df: pd.DataFrame, kinto_col: str = "kinto") -> pd.DataFrame:
    """Filtra o maintenance.csv às linhas com kinto == 'kinto' — só estas
    fazem sentido comparar com os ficheiros mensais da Kinto."""
    col = find_col(df, [kinto_col])
    if col is None:
        return df.iloc[0:0]
    return df[df[col].astype(str).str.strip().str.lower() == "kinto"]


def merge_kinto_maintenance(
    historico: pd.DataFrame,
    maintenance_base: pd.DataFrame,
    how: str = "left",
) -> pd.DataFrame:
    """
    Liga o histórico mensal kinto_Maintenance_Profile ao maintenance.csv
    da Fase 1 — chave: 'MsbKeyID' no ficheiro kinto, 'id' no maintenance.csv.
    Usar how="inner" com `maintenance_base` já filtrado a kinto == "kinto"
    restringe a análise apenas às linhas que são kinto.
    """
    hist = historico.copy()
    base = maintenance_base.copy()

    col_hist_key = find_col(hist, ["MsbKeyID", "msbKeyId", "id"])
    col_base_key = find_col(base, ["id", "MsbKeyID"])

    if col_hist_key is None or col_base_key is None:
        return hist

    base = base.rename(columns={col_base_key: "_join_key"})
    hist = hist.rename(columns={col_hist_key: "_join_key"})
    hist["_join_key"] = hist["_join_key"].astype(str).str.strip()
    base["_join_key"] = base["_join_key"].astype(str).str.strip()

    merged = hist.merge(base, how=how, on="_join_key", suffixes=("", "_base"))
    return merged.rename(columns={"_join_key": col_hist_key})


def kinto_relation_by_make(
    maintenance_kinto: pd.DataFrame,
    vehicle_snapshot: pd.DataFrame,
    make_col_candidates: list[str] | None = None,
    carids_col_candidates: list[str] | None = None,
    vehicle_make_col_candidates: list[str] | None = None,
    prioridade_col_candidates: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compara, por marca, o total de carid's do sistema (maintenance.csv,
    apenas linhas kinto) com o total de carid's no último export
    kinto_Vehicle_All (1 linha = 1 carid), devolvendo a % de cobertura.
    A 1ª coluna do resultado é a kinto_prioridade (do maintenance.csv).
    """
    make_col_candidates = make_col_candidates or ["make", "Make"]
    carids_col_candidates = carids_col_candidates or ["contagem_carids"]
    vehicle_make_col_candidates = vehicle_make_col_candidates or ["Make", "make"]
    prioridade_col_candidates = prioridade_col_candidates or ["kinto_prioridade", "kinto prioridade"]

    make_col = find_col(maintenance_kinto, make_col_candidates)
    carids_col = find_col(maintenance_kinto, carids_col_candidates)
    prioridade_col = find_col(maintenance_kinto, prioridade_col_candidates)
    vehicle_make_col = find_col(vehicle_snapshot, vehicle_make_col_candidates)

    if make_col is None or carids_col is None:
        return pd.DataFrame()

    maintenance_kinto = maintenance_kinto.copy()
    maintenance_kinto[carids_col] = pd.to_numeric(maintenance_kinto[carids_col], errors="coerce").fillna(0)

    sistema = (
        maintenance_kinto.groupby(make_col)[carids_col]
        .sum()
        .rename("carids_sistema")
    )

    if prioridade_col is not None:
        prioridade_por_make = (
            maintenance_kinto.groupby(make_col)[prioridade_col].first().rename("kinto_prioridade")
        )
    else:
        prioridade_por_make = pd.Series(dtype=object, name="kinto_prioridade")

    if vehicle_make_col is not None and vehicle_make_col in vehicle_snapshot.columns:
        export = vehicle_snapshot.groupby(vehicle_make_col).size().rename("carids_export")
    else:
        export = pd.Series(dtype=int, name="carids_export")

    relacao = pd.concat([prioridade_por_make, sistema, export], axis=1)
    relacao["carids_sistema"] = relacao["carids_sistema"].fillna(0).astype(int)
    relacao["carids_export"] = relacao["carids_export"].fillna(0).astype(int)
    relacao["percentagem"] = relacao.apply(
        lambda r: round(r["carids_export"] / r["carids_sistema"] * 100, 2) if r["carids_sistema"] > 0 else 0.0,
        axis=1,
    )

    relacao = relacao.reset_index().rename(columns={"index": "make"})
    colunas_finais = ["kinto_prioridade", "make", "carids_sistema", "carids_export", "percentagem"]
    relacao = relacao[[c for c in colunas_finais if c in relacao.columns]]
    return relacao.sort_values("percentagem", ascending=True).reset_index(drop=True)


def quality_breakdown_by_make(
    df: pd.DataFrame,
    make_col_candidates: list[str] | None = None,
    quality_col_candidates: list[str] | None = None,
) -> pd.DataFrame:
    """Tabela make x qualidade (contagens), com coluna Total, ordenada por
    Total decrescente — para "ver as qualidades" das linhas kinto."""
    make_col_candidates = make_col_candidates or ["make", "Make"]
    quality_col_candidates = quality_col_candidates or ["msbQuality"]

    make_col = find_col(df, make_col_candidates)
    quality_col = find_col(df, quality_col_candidates)
    if make_col is None or quality_col is None:
        return pd.DataFrame()

    tabela = df.groupby(make_col)[quality_col].value_counts().unstack(fill_value=0)
    tabela["Total"] = tabela.sum(axis=1)
    tabela = tabela.sort_values("Total", ascending=False)
    return tabela.reset_index().rename(columns={make_col: "make"})


def monthly_diff_summary(
    df: pd.DataFrame,
    id_col: str,
    value_col: str,
    ano_col: str = "ano",
    mes_col: str = "mes",
) -> pd.DataFrame:
    """
    Para cada par de meses consecutivos (ordenados por ano+mês) presentes
    em `df`, calcula quantos `id_col` são novos, quantos mudaram de
    `value_col` e quantos ficaram iguais, face ao mês anterior — ou seja,
    o que foi efetivamente atualizado no sistema, e não apenas repetido.
    """
    colunas_saida = ["ano", "mes", "novos", "alterados", "sem_alteracao"]
    if id_col not in df.columns or value_col not in df.columns:
        return pd.DataFrame(columns=colunas_saida)

    periodos = sorted(
        df[[ano_col, mes_col]].dropna().drop_duplicates().itertuples(index=False, name=None)
    )

    linhas = []
    anterior: dict | None = None
    for ano, mes in periodos:
        atual_df = (
            df[(df[ano_col] == ano) & (df[mes_col] == mes)]
            [[id_col, value_col]]
            .drop_duplicates(subset=[id_col])
        )
        atual = dict(zip(atual_df[id_col], atual_df[value_col]))

        if anterior is not None:
            ids_atual = set(atual.keys())
            ids_anterior = set(anterior.keys())

            novos = ids_atual - ids_anterior
            comuns = ids_atual & ids_anterior
            alterados = {i for i in comuns if atual[i] != anterior[i]}
            sem_alteracao = comuns - alterados

            linhas.append({
                "ano": ano,
                "mes": mes,
                "novos": len(novos),
                "alterados": len(alterados),
                "sem_alteracao": len(sem_alteracao),
            })

        anterior = atual

    return pd.DataFrame(linhas, columns=colunas_saida)
