"""
Utilitários de leitura/escrita e persistência de ficheiros.

Todos os ficheiros importados pelo utilizador são guardados na pasta
`data/` (a "pasta origem para base de dados" referida no projeto), para
que o pipeline possa ser reexecutado sem ter de reimportar tudo sempre
que a aplicação é reaberta.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Caminhos "canónicos" de cada ficheiro do pipeline
FILES = {
    "maintenance_profiles": DATA_DIR / "maintenance_profiles.csv",
    "maintenance_profiles_final": DATA_DIR / "maintenance_profiles_FINAL.csv",
    "cars": DATA_DIR / "cars.csv",
    "matriculas": DATA_DIR / "Matriculas.csv",
    "kinto_prioridade": DATA_DIR / "kinto_prioridade.csv",
    "maintenance": DATA_DIR / "maintenance.csv",
    # Fase 2 — Check Service
    "part_description": DATA_DIR / "part_description.csv",
    "service_parts": DATA_DIR / "service_parts.csv",
    "task_parts": DATA_DIR / "task_parts.csv",
    "check_analise": DATA_DIR / "check_analise.csv",
    # Fase 3 — Kinto Analisis (históricos mensais, persistidos e atualizados por upsert)
    "kinto_maintenance_historico": DATA_DIR / "kinto_maintenance_historico.csv",
    "kinto_vehicle_historico": DATA_DIR / "kinto_vehicle_historico.csv",
}

# Configuração de leitura de cada ficheiro (delimitador / encoding),
# conforme especificado no documento do projeto.
READ_CONFIG = {
    "maintenance_profiles": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "maintenance_profiles_final": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "cars": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "matriculas": {"sep": None, "encoding": "latin-1", "dtype": str, "engine": "python"},
    "kinto_prioridade": {"sep": ";", "encoding": "utf-8", "dtype": str},
    "maintenance": {"sep": ",", "encoding": "utf-8", "dtype": str},
    # Fase 2 — Check Service (tal como usado no CHECK.py original)
    "part_description": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "service_parts": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "task_parts": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "check_analise": {"sep": ",", "encoding": "utf-8", "dtype": str},
    # Fase 3 — Kinto Analisis (persistidos sempre por nós próprios em CSV normal)
    "kinto_maintenance_historico": {"sep": ",", "encoding": "utf-8", "dtype": str},
    "kinto_vehicle_historico": {"sep": ",", "encoding": "utf-8", "dtype": str},
}

# Encodings a tentar, por ordem, se o encoding configurado falhar a
# descodificar o ficheiro (comum em CSVs exportados do Excel em PT).
FALLBACK_ENCODINGS = ["utf-8", "latin-1", "cp1252"]


def file_exists(key: str) -> bool:
    return FILES[key].exists()


def save_uploaded_file(uploaded_file, key: str) -> Path:
    """Grava um ficheiro submetido via st.file_uploader na pasta data/."""
    path = FILES[key]
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def load_csv(key: str) -> pd.DataFrame:
    """
    Lê um dos ficheiros do pipeline com a configuração correta. Se o
    encoding configurado falhar a descodificar o ficheiro, tenta os
    FALLBACK_ENCODINGS por ordem (comum em CSVs exportados do Excel em PT).
    """
    cfg = dict(READ_CONFIG[key])
    encoding_configurado = cfg.pop("encoding", "utf-8")

    encodings_a_tentar = [encoding_configurado] + [
        e for e in FALLBACK_ENCODINGS if e != encoding_configurado
    ]

    ultimo_erro = None
    for encoding in encodings_a_tentar:
        try:
            return pd.read_csv(FILES[key], encoding=encoding, **cfg)
        except UnicodeDecodeError as e:
            ultimo_erro = e
            continue
    raise ultimo_erro


def save_csv(df: pd.DataFrame, key: str) -> Path:
    path = FILES[key]
    df.to_csv(path, index=False, encoding="utf-8")
    return path


def last_modified(key: str):
    if file_exists(key):
        import datetime
        ts = FILES[key].stat().st_mtime
        return datetime.datetime.fromtimestamp(ts)
    return None


def pipeline_status() -> dict:
    """Devolve o estado (presente/ausente + nº de linhas) de cada ficheiro."""
    status = {}
    for key in FILES:
        if file_exists(key):
            try:
                df = load_csv(key)
                status[key] = {"existe": True, "linhas": len(df), "colunas": len(df.columns)}
            except Exception as e:  # noqa: BLE001
                status[key] = {"existe": True, "erro": str(e)}
        else:
            status[key] = {"existe": False}
    return status
