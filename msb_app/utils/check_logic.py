"""
Lógica da Fase 2 — "Check Service": ligação entre part_description.csv,
service_parts.csv e task_parts.csv, replicando o script CHECK.py fornecido.

Passos (tal como no script original):
1. Remover colunas administrativas de service_parts e task_parts, e
   filtrar ambos a `country == "PO"`.
2. Merge task + service, por ["msbId", "partId"], how="left" — mantém
   todas as linhas de task_parts, associando a informação de service_parts
   quando exista correspondência. Colunas repetidas ficam com sufixo
   "_task" / "_service".
3. Preparar part_description (renomear "id" -> "partId", remover colunas
   booleanas administrativas).
4. Merge do resultado com part_description, por "partId", how="outer".
5. Calcular as colunas de verificação:
   - check_collected  = partDescription == description_collected
                        (comparação com texto normalizado: ver _norm_txt)
   - check_price      = price_task == price_service
   - check_partnumber = partNumber_task == partNumber_service
   - check_qtd        = quantity_task == quantity_service

Nota: os `drop(columns=...)` usam `errors="ignore"`, para o pipeline não
rebentar se algum dos ficheiros reais tiver um conjunto de colunas
ligeiramente diferente do script original.

Alterações face à versão anterior:
- check_collected passa a comparar texto normalizado (espaços não
  separáveis, caracteres invisíveis, espaços repetidos/nas pontas e
  maiúsculas/minúsculas deixam de dar falsos "Falso").
- Se faltar a coluna da descrição registada ou a do catálogo, a função
  levanta um erro claro em vez de pôr tudo a False em silêncio.
"""
from __future__ import annotations

import pandas as pd

DROP_SERVICE = ["id", "msbKey", "serviceId", "serviceName", "serviceType"]
DROP_TASK = ["id", "msbKey", "taskId", "taskDescription", "componentCode", "workCode"]
DROP_PARTS = ["isFluid", "isService", "isCollected", "isMsb"]

MERGE_KEYS = ["msbId", "partId"]


def _norm_txt(s: pd.Series) -> pd.Series:
    """Normaliza texto para comparar: Unicode NFKC (inclui espaços não
    separáveis), remove caracteres invisíveis (largura zero, BOM, hífen
    suave), colapsa espaços, tira espaços das pontas, ignora maiúsculas."""
    return (
        s.astype("string")
        .str.normalize("NFKC")
        .str.replace("[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.casefold()
    )


def _to_str_key(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Garante que as colunas de ligação são strings, para evitar merges
    silenciosamente vazios por incompatibilidade de tipo (ex.: int vs str)."""
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def build_check_analise(
    part_description: pd.DataFrame,
    service_parts: pd.DataFrame,
    task_parts: pd.DataFrame,
    country_filter: str | None = "PO",
) -> tuple[pd.DataFrame, dict]:
    """
    Replica o merge do CHECK.py. Devolve (check, meta), onde `meta` inclui
    `total_recolhido` (nº de linhas de task_parts já filtradas por país —
    "peças exclusivas do task_parts").
    """
    parts = part_description.copy()
    service = service_parts.copy()
    task = task_parts.copy()

    service = service.drop(columns=[c for c in DROP_SERVICE if c in service.columns])
    task = task.drop(columns=[c for c in DROP_TASK if c in task.columns])

    if country_filter:
        if "country" in service.columns:
            service = service[
                service["country"].astype(str).str.strip().str.upper() == country_filter.upper()
            ]
        if "country" in task.columns:
            task = task[
                task["country"].astype(str).str.strip().str.upper() == country_filter.upper()
            ]

    total_recolhido = len(task)

    # Garantir tipos consistentes nas chaves de ligação (evita merges vazios)
    for col in MERGE_KEYS:
        service = _to_str_key(service, col)
        task = _to_str_key(task, col)
    parts = _to_str_key(parts, "id")

    # Merge task + service
    check = task.merge(service, on=MERGE_KEYS, how="left", suffixes=("_x", "_y"))
    check.columns = (
        check.columns
        .str.replace(r"_x$", "_task", regex=True)
        .str.replace(r"_y$", "_service", regex=True)
    )

    # Preparar parts
    parts = parts.rename(columns={"id": "partId"})
    parts = parts.drop(columns=[c for c in DROP_PARTS if c in parts.columns])

    # Merge final com parts
    check = check.merge(parts, on="partId", how="outer", suffixes=("_x", "_y"))
    if "description_y" in check.columns:
        check = check.rename(columns={"description_y": "description_collected"})

    # Coerção numérica para as colunas comparadas (evitar "1" != 1.0 por engano)
    for col in ("price_task", "price_service", "quantity_task", "quantity_service"):
        if col in check.columns:
            check[col] = pd.to_numeric(check[col], errors="coerce")

    # check_collected: descrição registada em task_parts vs descrição do catálogo
    desc_recolhida = next(
        (c for c in ("partDescription", "partDescription_task") if c in check.columns),
        None,
    )
    if desc_recolhida is None or "description_collected" not in check.columns:
        disponiveis = [c for c in check.columns if "descr" in c.lower()]
        raise ValueError(
            "Não consigo calcular check_collected: falta a coluna da descrição "
            "registada em task_parts ou a do catálogo. "
            f"Colunas de descrição disponíveis: {disponiveis}"
        )
    check["check_collected"] = (
        _norm_txt(check[desc_recolhida]) == _norm_txt(check["description_collected"])
    ).fillna(False).astype(bool)

    def _safe_eq(col_a: str, col_b: str) -> pd.Series:
        if col_a in check.columns and col_b in check.columns:
            return check[col_a] == check[col_b]
        return pd.Series(False, index=check.index)

    check["check_price"] = _safe_eq("price_task", "price_service")
    check["check_partnumber"] = _safe_eq("partNumber_task", "partNumber_service")
    check["check_qtd"] = _safe_eq("quantity_task", "quantity_service")

    meta = {"total_recolhido": total_recolhido}
    return check, meta


def tabela_diferencas(check: pd.DataFrame) -> pd.DataFrame:
    """
    Separador 1: remove linhas incompletas (sem dados de comparação em
    ambos os lados) e mantém apenas as que têm ALGUMA diferença entre
    service_parts e task_parts (check_price, check_partnumber ou
    check_qtd a False).
    """
    cols_comparacao = [
        "price_task", "price_service",
        "partNumber_task", "partNumber_service",
        "quantity_task", "quantity_service",
    ]
    cols_existentes = [c for c in cols_comparacao if c in check.columns]

    d = check.dropna(subset=cols_existentes, how="any") if cols_existentes else check.copy()

    mask = pd.Series(False, index=d.index)
    for col in ("check_price", "check_partnumber", "check_qtd"):
        if col in d.columns:
            mask = mask | (d[col] == False)  # noqa: E712

    return d[mask]


def tabela_recolhidas_false(check: pd.DataFrame) -> pd.DataFrame:
    """
    Separador 2: peças com check_collected == False, mantendo as linhas
    vazias/incompletas (sem dropna).
    """
    if "check_collected" not in check.columns:
        return check.iloc[0:0]
    return check[check["check_collected"] == False]  # noqa: E712
