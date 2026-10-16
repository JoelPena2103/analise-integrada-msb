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
import time

import pandas as pd
import streamlit as st
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

TABLE_PREFIX = "msb_"
META_TABLE = f"{TABLE_PREFIX}_meta"

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

CACHE_TTL_SEGUNDOS = 300  # 5 minutos


def _get_connection():
    return st.connection("postgresql", type="sql")


def _query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """
    Executa uma consulta de leitura e devolve um DataFrame, FECHANDO a ligação.

    Substitui o `conn.query()` do Streamlit, que deixa a ligação aberta em
    "idle in transaction". Essas ligações seguram bloqueios de leitura nas
    tabelas e impedem que um TRUNCATE/ALTER TABLE (a gravação de um ficheiro)
    termine: a app ficava presa à espera de si própria.
    """
    conn = _get_connection()
    with conn.engine.connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def _table_name(key: str) -> str:
    return f"{TABLE_PREFIX}{TABLES[key]}"


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def _file_exists_cached(key: str) -> bool:
    conn = _get_connection()
    return inspect(conn.engine).has_table(_table_name(key))


def file_exists(key: str) -> bool:
    return _file_exists_cached(key)


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


def _limpar_cache() -> None:
    """Invalida toda a cache — chamado depois de qualquer escrita."""
    _file_exists_cached.clear()
    _load_csv_cached.clear()
    _last_modified_cached.clear()
    list_views.clear()
    list_functions.clear()
    list_functions_com_parametros.clear()
    load_analise.clear()


def _pg_type_for_dtype(dtype) -> str:
    """Mapeia um dtype do pandas para um tipo razoável do Postgres, usado
    em ALTER TABLE ADD COLUMN para colunas novas que ainda não existam."""
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    return "TEXT"


def _libertar_leituras_penduradas(c) -> None:
    """Termina leituras antigas desta base de dados que ficaram 'idle in
    transaction' e que bloqueariam um ALTER TABLE (rede de segurança: com o
    _query() acima já não deviam existir)."""
    c.execute(text("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND usename = current_user
          AND pid <> pg_backend_pid()
          AND state = 'idle in transaction'
          AND state_change < now() - interval '2 seconds'
    """))


def _replace_table_contents(df: pd.DataFrame, table: str, conn) -> None:
    """
    Substitui o CONTEÚDO de uma tabela já existente, SEM a apagar, numa só
    transação: acrescenta as colunas novas que faltem (ALTER TABLE ADD
    COLUMN), apaga as linhas antigas (DELETE) e insere as novas. Se algo
    falhar a meio, nada muda. Como a tabela nunca é apagada, quaisquer
    views/funções que dependam dela continuam a funcionar.

    Não usa TRUNCATE porque este espera por qualquer leitura aberta na
    tabela e pode ficar bloqueado; o DELETE convive com elas.
    """
    colunas_existentes = {c["name"] for c in inspect(conn.engine).get_columns(table)}
    colunas_novas = [c for c in df.columns if c not in colunas_existentes]

    with conn.engine.begin() as c:
        c.execute(text("SET LOCAL lock_timeout = '30s'"))
        if colunas_novas:
            _libertar_leituras_penduradas(c)
            for col in colunas_novas:
                tipo_pg = _pg_type_for_dtype(df[col].dtype)
                c.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {tipo_pg}'))
        c.execute(text(f'DELETE FROM "{table}"'))
        df.to_sql(table, c, if_exists="append", index=False, method="multi", chunksize=5000)


def _table_exists_live(table: str, conn=None) -> bool:
    """
    Pergunta diretamente à base de dados (sem passar pelo Inspector do
    SQLAlchemy, que pode dar respostas desatualizadas nalguns cenários)
    se a tabela existe mesmo, agora. Usado dentro de save_csv, onde é
    crítico não errar esta resposta — errar para "não existe" faria o
    código cair no caminho antigo (DROP TABLE), que falha se houver
    views/funções dependentes.
    """
    resultado = _query(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables "
        "  WHERE table_schema = 'public' AND table_name = :t"
        ") AS existe",
        params={"t": table},
    )
    return bool(resultado.iloc[0]["existe"])


def save_csv(df: pd.DataFrame, key: str, tentativas: int = 3) -> None:
    """
    Grava os dados na tabela correspondente a `key`.

    Se a tabela ainda não existir, cria-a de raiz. Se já existir, NUNCA a
    apaga — só acrescenta colunas novas que faltem e substitui o
    conteúdo (DELETE + INSERT, numa só transação). Importante porque, se
    alguma view/função
    criada no Supabase depender desta tabela, apagá-la e recriá-la
    (`DROP TABLE`, o que "if_exists=replace" faz por trás) falharia com
    um erro de dependências.
    """
    conn = _get_connection()
    table = _table_name(key)
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            if _table_exists_live(table, conn):
                _replace_table_contents(df, table, conn)
            else:
                df.to_sql(
                    table, conn.engine, if_exists="replace", index=False,
                    method="multi", chunksize=5000,
                )
            _touch_meta(key)
            _limpar_cache()
            return
        except (IntegrityError, OperationalError) as e:
            ultimo_erro = e
            time.sleep(0.5 * tentativa)
            continue
    raise ultimo_erro


def save_uploaded_file(uploaded_file, key: str) -> None:
    """Lê o CSV enviado pelo utilizador e grava-o já como tabela na base de dados."""
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


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner="A carregar dados...")
def _load_csv_cached(key: str) -> pd.DataFrame:
    return _query(f"SELECT * FROM {_table_name(key)}")


def load_csv(key: str) -> pd.DataFrame:
    return _load_csv_cached(key)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def _last_modified_cached(key: str):
    if not _file_exists_cached(key):
        return None
    _ensure_meta_table()
    try:
        resultado = _query(
            f"SELECT updated_at FROM {META_TABLE} WHERE table_name = :t",
            params={"t": _table_name(key)},
        )
        if not resultado.empty:
            return resultado.iloc[0]["updated_at"]
    except Exception:  # noqa: BLE001
        pass
    return None


def last_modified(key: str):
    return _last_modified_cached(key)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_views(prefix: str = "msb_") -> list[str]:
    df = _query(
        "SELECT table_name FROM information_schema.views "
        "WHERE table_schema = 'public' AND table_name LIKE :prefix "
        "ORDER BY table_name",
        params={"prefix": f"{prefix}%"},
    )
    return df["table_name"].tolist()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_functions(prefix: str = "msb_") -> list[str]:
    df = _query(
        "SELECT p.proname AS nome "
        "FROM pg_proc p "
        "JOIN pg_namespace n ON p.pronamespace = n.oid "
        "WHERE n.nspname = 'public' AND p.proname LIKE :prefix "
        "AND p.pronargs = 0 AND p.prokind = 'f' "
        "ORDER BY p.proname",
        params={"prefix": f"{prefix}%"},
    )
    return df["nome"].tolist()


def list_analises(prefix: str = "msb_") -> list[str]:
    return sorted(set(list_views(prefix)) | set(list_functions(prefix)))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner="A carregar dados...")
def load_analise(nome: str) -> pd.DataFrame:
    if nome in list_views(""):
        sql = f"SELECT * FROM {nome}"
    elif nome in list_functions(""):
        sql = f"SELECT * FROM {nome}()"
    else:
        raise ValueError(f"'{nome}' não é uma view nem uma função conhecida da base de dados.")
    return _query(sql)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_functions_com_parametros(prefix: str = "msb_") -> dict[str, list[tuple[str, str]]]:
    df = _query(
        "SELECT p.proname AS nome, "
        "pg_get_function_identity_arguments(p.oid) AS args "
        "FROM pg_proc p "
        "JOIN pg_namespace n ON p.pronamespace = n.oid "
        "WHERE n.nspname = 'public' AND p.proname LIKE :prefix "
        "AND p.pronargs > 0 AND p.prokind = 'f' "
        "ORDER BY p.proname",
        params={"prefix": f"{prefix}%"},
    )
    resultado: dict[str, list[tuple[str, str]]] = {}
    for _, linha in df.iterrows():
        parametros = []
        for pedaco in linha["args"].split(","):
            pedaco = pedaco.strip()
            if not pedaco:
                continue
            partes = pedaco.split(" ", 1)
            if len(partes) == 2:
                parametros.append((partes[0], partes[1]))
            else:
                parametros.append((pedaco, "text"))
        resultado[linha["nome"]] = parametros
    return resultado


def call_function(nome: str, valores: dict) -> pd.DataFrame:
    funcoes = list_functions_com_parametros("")
    if nome not in funcoes:
        raise ValueError(f"'{nome}' não é uma função conhecida da base de dados.")

    parametros_esperados = funcoes[nome]
    placeholders = ", ".join(f":p{i}" for i in range(len(parametros_esperados)))
    query_params = {
        f"p{i}": valores[nome_param] for i, (nome_param, _tipo) in enumerate(parametros_esperados)
    }

    sql = f"SELECT * FROM {nome}({placeholders})"
    return _query(sql, params=query_params)


def pipeline_status() -> dict:
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
