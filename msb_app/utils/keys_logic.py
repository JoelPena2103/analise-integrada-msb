"""
Lógica do "Gerador de Keys" — portada do script standalone (Tkinter) descrito
no projeto original, mas sem dependências de UI (tkinter), para poder ser
usada dentro do Streamlit.

Regras (conforme documento):
    quality1_key = make_engineSize_fuelType
    quality2_key = make_model_engineSize_fuelType
    quality3_key = make_model_engineSize_fuelType_powerHp
    quality4_key = make_model_engineSize_fuelType_powerHp_mark
    qualidade 0  = veículo sem dados (nenhuma key aplicável)

A previsão de qualidade ("predictedQuality") copia informação de veículos
com msbQuality == 4 para veículos "irmãos" (mesma key) com qualidade menor,
do nível mais forte (4) para o mais fraco (1).
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLS = ["make", "model", "mark", "engineSize", "fuelType", "powerHp"]

QUALITY_KEY_COLS = ["quality4_key", "quality3_key", "quality2_key", "quality1_key"]

NIVEIS = [
    ("quality4_key", 4),
    ("quality3_key", 3),
    ("quality2_key", 2),
    ("quality1_key", 1),
]

COLUNAS_SCRIPT = [
    "quality4_key", "quality3_key", "quality2_key", "quality1_key",
    "predictedQuality", "id_copia", "descricao_copia", "msbQuality",
]


def norm(val) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if not s:
        return ""
    return " ".join(s.split()).upper()


def key_join(parts: list[str]) -> str:
    return "_".join([p for p in parts if p != ""])


def normalize_engine(v):
    try:
        val = float(str(v).replace(",", "."))
        return f"{val / 1000:g}"
    except (ValueError, TypeError):
        return v


def normalize_hp(v):
    if pd.isna(v):
        return ""
    s = str(v).upper()
    for tok in ("CV", "HP"):
        s = s.replace(tok, "")
    s = s.strip()
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return ""


def gerar_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Cria/recria as colunas quality4_key..quality1_key."""
    df = df.copy()

    # Apagar keys antigas para evitar duplicação
    for col in QUALITY_KEY_COLS:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # Garantir colunas obrigatórias
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""

    # Normalizar
    for col in REQUIRED_COLS:
        df[col] = df[col].map(norm)

    df["engineSize"] = df["engineSize"].apply(normalize_engine)
    df["powerHp"] = df["powerHp"].apply(normalize_hp)

    df["quality4_key"] = [
        key_join([m, mo, es, ft, hp, mk])
        for m, mo, es, ft, hp, mk in zip(
            df["make"], df["model"], df["engineSize"], df["fuelType"], df["powerHp"], df["mark"]
        )
    ]
    df["quality3_key"] = [
        key_join([m, mo, es, ft, mk])
        for m, mo, es, ft, mk in zip(
            df["make"], df["model"], df["engineSize"], df["fuelType"], df["mark"]
        )
    ]
    df["quality2_key"] = [
        key_join([m, mo, es, ft])
        for m, mo, es, ft in zip(df["make"], df["model"], df["engineSize"], df["fuelType"])
    ]
    df["quality1_key"] = [
        key_join([m, es, ft]) for m, es, ft in zip(df["make"], df["engineSize"], df["fuelType"])
    ]
    return df


def atribuir_qualidade(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, int]]:
    """Propaga a qualidade 4 pelos veículos "irmãos" com qualidade menor."""
    df = df.copy()
    df["msbQuality"] = pd.to_numeric(df["msbQuality"], errors="coerce").fillna(0).astype(int)
    df["predictedQuality"] = df["msbQuality"]
    df["id_copia"] = ""
    df["descricao_copia"] = ""

    # Apenas veículos com qualidade 4 são fontes de cópia
    fontes = df[df["msbQuality"] == 4].copy()

    contagens = {4: 0, 3: 0, 2: 0, 1: 0}

    for _, fonte in fontes.iterrows():
        id_fonte = fonte["id"]
        for key_col, nivel in NIVEIS:
            key_fonte = fonte[key_col]
            if key_fonte == "":
                # Key vazia (sem dados suficientes) não deve gerar cópias falsas
                continue
            mask = (df[key_col] == key_fonte) & (df["predictedQuality"] < nivel)
            df.loc[mask, "predictedQuality"] = nivel
            df.loc[mask, "id_copia"] = str(id_fonte)
            df.loc[mask, "descricao_copia"] = str(key_fonte)
            contagens[nivel] += int(mask.sum())

    return df, contagens


def build_maintenance_profiles_final(
    df_new: pd.DataFrame, df_existing: pd.DataFrame | None
) -> pd.DataFrame:
    """
    Atualiza (ou cria) o maintenance_profiles_FINAL:
    - se já existir um FINAL, atualiza as colunas geradas para os ids já
      existentes e acrescenta as linhas novas;
    - caso contrário, cria-o de raiz.
    Equivalente à lógica do script original (openpyxl -> aqui em CSV).
    """
    if "id" not in df_new.columns:
        raise ValueError("A coluna 'id' é obrigatória no ficheiro maintenance_profiles.")

    # O `id` é único por perfil: ids repetidos (ex.: gravações duplicadas)
    # são reduzidos a uma só linha, para não inflacionar as contagens.
    df_new = df_new.drop_duplicates(subset="id", keep="last")

    if df_existing is not None and not df_existing.empty:
        if "id" in df_existing.columns:
            df_existing = df_existing.drop_duplicates(subset="id", keep="last")
        df_final = df_existing.copy()
        if "id" not in df_final.columns:
            df_final["id"] = ""

        df_final = df_final.set_index("id")
        df_new_idx = df_new.set_index("id")

        # 1) Atualizar linhas existentes (apenas as colunas geradas pelo script)
        cols_disponiveis = [c for c in COLUNAS_SCRIPT if c in df_new_idx.columns]
        for col in cols_disponiveis:
            df_final[col] = df_new_idx[col]

        # 1b) Atualizar também os dados do perfil (status, maxEndDate, make,
        #     etc.) dos ids que existem nos dois lados: o export novo manda.
        #     Sem isto, um perfil que mudou de estado ou de data de fim na
        #     origem ficava com os valores antigos no FINAL para sempre.
        #     As colunas que só existem no FINAL ficam como estão.
        outras = [
            c for c in df_new_idx.columns
            if c not in COLUNAS_SCRIPT and c in df_final.columns
        ]
        comuns = df_final.index.intersection(df_new_idx.index)
        if outras and len(comuns):
            df_final.loc[comuns, outras] = df_new_idx.loc[comuns, outras]

        # 2) Adicionar linhas novas
        novas_linhas = df_new_idx[~df_new_idx.index.isin(df_final.index)]
        if not novas_linhas.empty:
            df_final = pd.concat([df_final, novas_linhas], axis=0)

        df_final = df_final.reset_index()
    else:
        df_final = df_new.copy()

    return df_final
