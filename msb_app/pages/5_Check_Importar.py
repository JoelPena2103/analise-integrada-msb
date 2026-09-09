import io

import pandas as pd
import streamlit as st

from utils.io_utils import save_uploaded_file, load_csv, file_exists, save_csv, READ_CONFIG
from utils.branding import set_logo
from utils.check_logic import build_check_analise

st.set_page_config(page_title="Importar & Gerar Check — MSB", page_icon="🧩", layout="wide")
set_logo()
st.title("🧩 Fase 2 — Importar & Gerar Check")
st.caption(
    "Importa part_description.csv, service_parts.csv e task_parts.csv, e gera o "
    "check_analise.csv (merge por msbId + partId, filtrado a country == 'PO')."
)


def import_block(key: str, titulo: str, descricao: str, exemplo_cols: list[str] | None = None):
    st.markdown(f"### {titulo}")
    st.caption(descricao)
    cfg = READ_CONFIG[key]
    st.caption(f"Delimitador: `{cfg.get('sep') or 'auto-detetado'}` · Encoding: `{cfg.get('encoding', 'utf-8')}`")

    uploaded = st.file_uploader(
        f"Carregar {titulo}", type=["csv"], key=f"uploader_{key}", label_visibility="collapsed"
    )
    if uploaded is not None:
        save_uploaded_file(uploaded, key)
        st.success(f"'{uploaded.name}' guardado com sucesso.")

    if file_exists(key):
        try:
            df = load_csv(key)
            st.write(f"✅ Ficheiro atual: **{len(df):,} linhas**, **{len(df.columns)} colunas**".replace(",", " "))
            with st.expander("Pré-visualizar dados"):
                st.dataframe(df.head(50), width='stretch')
            if exemplo_cols:
                faltam = [c for c in exemplo_cols if c not in df.columns]
                if faltam:
                    st.warning(f"Colunas esperadas em falta: {faltam}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Erro ao ler o ficheiro guardado: {e}")
    else:
        st.info("Ainda sem ficheiro importado.")
    st.markdown("---")


import_block(
    "part_description",
    "part_description.csv",
    "Catálogo de peças possíveis para recolha (uma peça = uma linha, identificada por 'id'). "
    "A coluna 'description' é a descrição oficial de cada peça, usada para comparar com o "
    "que foi registado em task_parts.csv (coluna 'partDescription').",
    exemplo_cols=["id", "description"],
)

import_block(
    "service_parts",
    "service_parts.csv",
    "Peças associadas a serviços. Liga-se por msbId + partId. Só conta country == 'PO'.",
    exemplo_cols=["msbId", "partId", "partNumber", "price", "quantity", "country"],
)

import_block(
    "task_parts",
    "task_parts.csv",
    "Peças associadas a tarefas (o que foi realmente feito/recolhido). Liga-se por "
    "msbId + partId. Só conta country == 'PO'.",
    exemplo_cols=["msbId", "partId", "partNumber", "price", "quantity", "country"],
)

st.markdown("#### Gerar ficheiro (merge)")
faltam = [k for k in ("part_description", "service_parts", "task_parts") if not file_exists(k)]
if faltam:
    st.warning(f"Ainda faltam importar: {', '.join(faltam)}")
else:
    if st.button("▶️ Gerar ficheiro (merge)", type="primary"):
        with st.spinner("A fazer o merge..."):
            try:
                part_description = load_csv("part_description")
                service_parts = load_csv("service_parts")
                task_parts = load_csv("task_parts")
                check, meta = build_check_analise(part_description, service_parts, task_parts)
            except Exception as e:  # noqa: BLE001
                st.error(f"Erro ao gerar o ficheiro: {e}")
                st.stop()

        st.session_state["check_df"] = check
        st.session_state["check_meta"] = meta
        st.success(f"Ficheiro gerado com {len(check):,} linhas.".replace(",", " "))

if "check_df" in st.session_state:
    check = st.session_state["check_df"]

    st.markdown("#### Pré-visualização")
    st.dataframe(check.head(100), width='stretch')

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 Guardar check_analise.csv", type="primary"):
            save_csv(check, "check_analise")
            st.success("check_analise.csv guardado com sucesso.")
    with c2:
        st.download_button(
            "⬇️ Descarregar CSV",
            data=check.to_csv(index=False).encode("utf-8"),
            file_name="check_analise.csv",
            mime="text/csv",
        )
    with c3:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            check.to_excel(writer, index=False, sheet_name="analise")
        st.download_button(
            "⬇️ Descarregar analise.xlsx",
            data=buffer.getvalue(),
            file_name="analise.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.markdown("---")
st.write("Próximo passo: página **📋 Check Dashboard** para ver as diferenças e exportar.")
