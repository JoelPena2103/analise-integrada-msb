"""
Fase 3 — Kinto Analisis.

Ficheiros mensais como 'kinto_Maintenance_Profile_2026_02_13.csv' e
'kinto_Vehicle_All_2026_06_15.csv' têm sempre a mesma estrutura; o que
muda é o número de linhas e a data no nome. Este módulo trata de:

1. Extrair (ano, mês) do nome do ficheiro por regex.
2. Acrescentar cada mês importado a uma tabela histórica persistida,
   substituindo (upsert) o mês caso já tenha sido importado antes.
3. Ligar essa tabela histórica às bases já existentes da Fase 1
   (maintenance.csv e cars.csv), para trazer informação adicional
   (make, msbQuality, status, etc.) sem ter de reimportar nada.
4. Calcular a diferença mês-a-mês (o que realmente mudou desde o mês
   anterior), como alternativa à vista acumulada.
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


def merge_kinto_maintenance(historico: pd.DataFrame, maintenance_base: pd.DataFrame) -> pd.DataFrame:
    """
    Liga o histórico mensal kinto_Maintenance_Profile ao maintenance.csv
    da Fase 1 — chave: 'MsbKeyID' no ficheiro kinto, 'id' no maintenance.csv.
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

    merged = hist.merge(base, how="left", on="_join_key", suffixes=("", "_base"))
    return merged.rename(columns={"_join_key": col_hist_key})


def merge_kinto_vehicle(historico: pd.DataFrame, cars_base: pd.DataFrame) -> pd.DataFrame:
    """
    Liga o histórico mensal kinto_Vehicle_All ao cars.csv da Fase 1 —
    chave: 'CarID'/'CARID' no ficheiro kinto, 'carId' no cars.csv.
    """
    hist = historico.copy()
    base = cars_base.copy()

    col_hist_key = find_col(hist, ["CarID", "CARID", "carId"])
    col_base_key = find_col(base, ["carId", "CarID", "CARID"])

    if col_hist_key is None or col_base_key is None:
        return hist

    base = base.rename(columns={col_base_key: "_join_key"})
    hist = hist.rename(columns={col_hist_key: "_join_key"})
    hist["_join_key"] = hist["_join_key"].astype(str).str.strip()
    base["_join_key"] = base["_join_key"].astype(str).str.strip()

    merged = hist.merge(base, how="left", on="_join_key", suffixes=("", "_base"))
    return merged.rename(columns={"_join_key": col_hist_key})


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
