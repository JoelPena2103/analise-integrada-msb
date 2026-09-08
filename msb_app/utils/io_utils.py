"""
Persistência em Postgres — substitui os CSVs locais em `data/`.

Porquê: no Streamlit Community Cloud, o sistema de ficheiros não é
sincronizado com o GitHub nem é persistente (um redeploy, um `git push`,
ou a app "adormecer" por inatividade apaga tudo o que tenha sido escrito
localmente). Guardar os dados numa base de dados externa resolve isto.

Configuração necessária (NUNCA commitar isto no GitHub):

  Localmente, em `.streamlit/secrets.toml`:

      [connections.postgresql]
      url = "postgresql://utilizador:password@host:5432/nome_da_bd"

  No Streamlit Cloud: Settings do app -> "Secrets" -> colar o mesmo TOML.

Dependências extra a acrescentar ao requirements.txt:
    sqlalchemy
    psycopg2-binary

Nada mais no projeto precisa de mudar — todas as páginas continuam a
chamar file_exists(), load_csv(), save_csv(), save_uploaded_file(),
last_modified() e pipeline_status() exatamente como antes.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st
from sqlalchemy import inspect, text

# Prefixo das tabelas, para não colidir com outras tabelas que já existam
# na mesma base de dados (ex.: tabelas de login / códigos temporários).
TABLE_PREFIX = "msb_"
META_TABLE = f"{TABLE_PREFIX}_meta"

# Nome "canónico" de cada tabela do pipeline (equivalente aos antigos
# caminhos de ficheiro em FILES).
TABLES = {
    "maintenance_profiles": "maintenance_profiles",
    "maintenance_profiles_final": "maintenance_profiles_final",
    "cars": "cars",
    "matriculas": "matriculas",
    "kinto_prioridade": "kinto_prioridade",
    "maintenance": "maintenance",
    "part_description": "part_description",
    "service_parts": "service_parts",
    "task_parts": "task_parts",
    "check_analise": "check_analise",
    "kinto_maintenance_historico": "kinto_maintenance_historico",
    "kinto_vehicle_historico": "kinto_vehicle_historico",
}

# Configuração de leitura dos CSVs BRUTOS enviados pelo utilizador
# (delimitador / encoding) — usada só no momento do upload, para os
# converter em DataFrame antes de gravar na base de dados.
READ_CONFIG = {
    "maintenance_profiles": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "maintenance_profiles_final": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "cars": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "matriculas": {"sep": None, "encoding": "latin-1", "dtype": str, "engine": "python"},
    "kinto_prioridade": {"sep": ";", "encoding": "utf-8", "dtype": str},
    "maintenance": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "part_description": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "service_parts": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "task_parts": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "check_analise": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "kinto_maintenance_historico": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "kinto_vehicle_historico": {"sep": ",", "encoding": "utf-8", "dtype": str},
}

FALLBACK_ENCODINGS = ["utf-8", "latin-1", "cp1252"]


def _get_connection():
    """st.connection já faz cache/pooling internamente — não é preciso
    voltar a envolver isto em @st.cache_resource."""
    return st.connection("postgresql", type="sql")


def _table_name(key: str) -> str:
    return f"{TABLE_PREFIX}{TABLES[key]}"


def file_exists(key: str) -> bool:
    conn = _get_connection()
    return inspect(conn.engine).has_table(_table_name(key))


def _ensure_meta_table():
    conn = _get_connection()
    with conn.session as s:
        s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {META_TABLE} "
            f"(table_name TEXT PRIMARY KEY, updated_at TIMESTAMP)"
        ))
        s.commit()


def _touch_meta(key: str):
    _ensure_meta_table()
    conn = _get_connection()
    with conn.session as s:
        s.execute(
            text(
                f"INSERT INTO {META_TABLE} (table_name, updated_at) VALUES (:t, :ts) "
                f"ON CONFLICT (table_name) DO UPDATE SET updated_at = :ts"
            ),
            {"t": _table_name(key), "ts": dt.datetime.now()},
        )
        s.commit()


def save_csv(df: pd.DataFrame, key: str) -> None:
    """Grava (substitui por completo) a tabela correspondente a `key`."""
    conn = _get_connection()
    df.to_sql(
        _table_name(key), conn.engine, if_exists="replace", index=False,
        method="multi", chunksize=5000,
    )
    _touch_meta(key)


def save_uploaded_file(uploaded_file, key: str) -> None:
    """
    Lê o CSV enviado pelo utilizador (com o delimitador/encoding certos)
    e grava-o já como tabela na base de dados.
    """
    cfg = dict(READ_CONFIG[key])
    encoding_configurado = cfg.pop("encoding", "utf-8")
    encodings_a_tentar = [encoding_configurado] + [
        e for e in FALLBACK_ENCODINGS if e != encoding_configurado
    ]

    ultimo_erro = None
    df = None
    for encoding in encodings_a_tentar:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, encoding=encoding, **cfg)
            break
        except UnicodeDecodeError as e:
            ultimo_erro = e
            continue
    if df is None:
        raise ultimo_erro

    save_csv(df, key)


def load_csv(key: str) -> pd.DataFrame:
    conn = _get_connection()
    return conn.query(f"SELECT * FROM {_table_name(key)}", ttl=0)


def last_modified(key: str):
    if not file_exists(key):
        return None
    _ensure_meta_table()
    conn = _get_connection()
    try:
        resultado = conn.query(
            f"SELECT updated_at FROM {META_TABLE} WHERE table_name = :t",
            params={"t": _table_name(key)},
            ttl=0,
        )
        if not resultado.empty:
            return resultado.iloc[0]["updated_at"]
    except Exception:  # noqa: BLE001
        pass
    return None


def pipeline_status() -> dict:
    """Devolve o estado (presente/ausente + nº de linhas) de cada tabela."""
    status = {}
    for key in TABLES:
        if file_exists(key):
            try:
                df = load_csv(key)
                status[key] = {"existe": True, "linhas": len(df), "colunas": len(df.columns)}
            except Exception as e:  # noqa: BLE001
                status[key] = {"existe": True, "erro": str(e)}
        else:
            status[key] = {"existe": False}
    return status
