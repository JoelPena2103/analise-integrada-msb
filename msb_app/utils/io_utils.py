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

# Quanto tempo (em segundos) os dados ficam em cache antes de se voltar a
# perguntar à base de dados — mesmo sem nenhuma escrita pelo meio. Serve de
# rede de segurança para o caso de haver alterações feitas por fora da app
# (ex.: editadas diretamente no Supabase). Sempre que a app grava algo,
# a cache é limpa de imediato, sem esperar por este tempo.
CACHE_TTL_SEGUNDOS = 300  # 5 minutos


def _get_connection():
    """st.connection já faz cache/pooling internamente — não é preciso
    voltar a envolver isto em @st.cache_resource."""
    return st.connection("postgresql", type="sql")


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
    """Invalida toda a cache — chamado depois de qualquer escrita, para que
    a próxima leitura (de qualquer sessão/utilizador) veja logo os dados
    atualizados, sem esperar pelo CACHE_TTL_SEGUNDOS."""
    _file_exists_cached.clear()
    _load_csv_cached.clear()
    _last_modified_cached.clear()


def save_csv(df: pd.DataFrame, key: str, tentativas: int = 3) -> None:
    """
    Grava (substitui por completo) a tabela correspondente a `key`.

    Em apps partilhadas, duas escritas quase simultâneas à mesma tabela
    podem colidir a apagar/recriar o tipo interno do Postgres associado à
    tabela (erro "duplicate key value ... pg_type_typname_nsp_index").
    Isto é raro e transitório — por isso tenta-se automaticamente de novo
    algumas vezes antes de desistir.
    """
    conn = _get_connection()
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            df.to_sql(
                _table_name(key), conn.engine, if_exists="replace", index=False,
                method="multi", chunksize=5000,
            )
            _touch_meta(key)
            _limpar_cache()
            return
        except (IntegrityError, OperationalError) as e:
            ultimo_erro = e
            time.sleep(0.5 * tentativa)  # pequena espera crescente antes de repetir
            continue
    raise ultimo_erro


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


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner="A carregar dados...")
def _load_csv_cached(key: str) -> pd.DataFrame:
    conn = _get_connection()
    return conn.query(f"SELECT * FROM {_table_name(key)}", ttl=0)


def load_csv(key: str) -> pd.DataFrame:
    return _load_csv_cached(key)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def _last_modified_cached(key: str):
    if not _file_exists_cached(key):
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


def last_modified(key: str):
    return _last_modified_cached(key)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_views(prefix: str = "msb_") -> list[str]:
    """Lista as views existentes na base de dados (ex.: criadas à mão no
    SQL Editor do Supabase), para popular um selectbox na app."""
    conn = _get_connection()
    df = conn.query(
        "SELECT table_name FROM information_schema.views "
        "WHERE table_schema = 'public' AND table_name LIKE :prefix "
        "ORDER BY table_name",
        params={"prefix": f"{prefix}%"},
        ttl=0,
    )
    return df["table_name"].tolist()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner="A carregar view...")
def load_view(view_name: str) -> pd.DataFrame:
    """
    Lê uma view do Postgres (ex.: msb_kinto_quality) como DataFrame.
    `view_name` deve vir sempre de list_views() ou de uma lista fixa
    conhecida — nunca de texto livre do utilizador, para não abrir uma
    porta a SQL arbitrário.
    """
    if view_name not in list_views(""):
        raise ValueError(f"'{view_name}' não é uma view conhecida da base de dados.")
    conn = _get_connection()
    return conn.query(f"SELECT * FROM {view_name}", ttl=0)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_functions(prefix: str = "msb_") -> list[str]:
    """
    Lista funções SQL sem argumentos (ex.: criadas no SQL Editor do
    Supabase) que devolvam uma tabela/conjunto de linhas — para poderem
    ser tratadas como "análises" disponíveis, tal como as views.
    Funções COM argumentos não entram aqui de propósito: chamá-las exigiria
    pedir esses valores ao utilizador, o que ainda não está implementado.
    """
    conn = _get_connection()
    df = conn.query(
        "SELECT p.proname AS nome "
        "FROM pg_proc p "
        "JOIN pg_namespace n ON p.pronamespace = n.oid "
        "WHERE n.nspname = 'public' AND p.proname LIKE :prefix "
        "AND p.pronargs = 0 AND p.prokind = 'f' "
        "ORDER BY p.proname",
        params={"prefix": f"{prefix}%"},
        ttl=0,
    )
    return df["nome"].tolist()


def list_analises(prefix: str = "msb_") -> list[str]:
    """Views + funções sem argumentos, juntas numa só lista (para o
    selectbox da página de Análises SQL)."""
    return sorted(set(list_views(prefix)) | set(list_functions(prefix)))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner="A carregar dados...")
def load_analise(nome: str) -> pd.DataFrame:
    """
    Lê uma view OU uma função sem argumentos como DataFrame — detecta
    automaticamente qual dos dois tipos `nome` é. `nome` deve vir sempre
    de list_analises() ou de uma lista fixa conhecida — nunca de texto
    livre do utilizador, para não abrir uma porta a SQL arbitrário.
    """
    if nome in list_views(""):
        sql = f"SELECT * FROM {nome}"
    elif nome in list_functions(""):
        sql = f"SELECT * FROM {nome}()"
    else:
        raise ValueError(f"'{nome}' não é uma view nem uma função conhecida da base de dados.")
    conn = _get_connection()
    return conn.query(sql, ttl=0)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def list_functions_com_parametros(prefix: str = "msb_") -> dict[str, list[tuple[str, str]]]:
    """
    Lista funções SQL COM argumentos (ex.: criadas no SQL Editor do
    Supabase). Devolve {nome_funcao: [(nome_parametro, tipo_sql), ...]},
    para a app conseguir gerar automaticamente um campo de input adequado
    a cada parâmetro (data, número, texto, ...).
    """
    conn = _get_connection()
    df = conn.query(
        "SELECT p.proname AS nome, "
        "pg_get_function_identity_arguments(p.oid) AS args "
        "FROM pg_proc p "
        "JOIN pg_namespace n ON p.pronamespace = n.oid "
        "WHERE n.nspname = 'public' AND p.proname LIKE :prefix "
        "AND p.pronargs > 0 AND p.prokind = 'f' "
        "ORDER BY p.proname",
        params={"prefix": f"{prefix}%"},
        ttl=0,
    )
    resultado: dict[str, list[tuple[str, str]]] = {}
    for _, linha in df.iterrows():
        parametros = []
        for pedaco in linha["args"].split(","):
            pedaco = pedaco.strip()
            if not pedaco:
                continue
            partes = pedaco.split(" ", 1)  # "nome tipo" -> só a 1ª espaço separa
            if len(partes) == 2:
                parametros.append((partes[0], partes[1]))
            else:
                parametros.append((pedaco, "text"))
        resultado[linha["nome"]] = parametros
    return resultado


def call_function(nome: str, valores: dict) -> pd.DataFrame:
    """
    Chama uma função COM argumentos (de list_functions_com_parametros),
    com os valores escolhidos pelo utilizador. `nome` deve vir sempre de
    list_functions_com_parametros() — nunca de texto livre, para não abrir
    uma porta a SQL arbitrário. Os VALORES dos parâmetros são sempre
    passados como parâmetros de query (nunca colados na string SQL).
    """
    funcoes = list_functions_com_parametros("")
    if nome not in funcoes:
        raise ValueError(f"'{nome}' não é uma função conhecida da base de dados.")

    parametros_esperados = funcoes[nome]
    placeholders = ", ".join(f":p{i}" for i in range(len(parametros_esperados)))
    query_params = {
        f"p{i}": valores[nome_param] for i, (nome_param, _tipo) in enumerate(parametros_esperados)
    }

    sql = f"SELECT * FROM {nome}({placeholders})"
    conn = _get_connection()
    return conn.query(sql, params=query_params, ttl=0)


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
