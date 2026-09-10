import io

import pandas as pd
import streamlit as st

from utils.io_utils import list_analises, load_analise, list_functions_com_parametros, call_function
from utils.branding import set_logo

st.set_page_config(page_title="Análises SQL — MSB", page_icon="🧮", layout="wide")
set_logo()
st.title("🧮 Análises SQL")
st.caption(
    "Consulta views e funções criadas diretamente no Postgres (ex.: no SQL Editor do "
    "Supabase). Crie lá, e aparece automaticamente aqui na lista."
)

analises_simples = list_analises()  # views + funções sem argumentos
funcoes_parametrizadas = list_functions_com_parametros()  # {nome: [(param, tipo), ...]}

SUFIXO_PARAM = " (parâmetros)"
opcoes = analises_simples + [f"{nome}{SUFIXO_PARAM}" for nome in funcoes_parametrizadas]

if not opcoes:
    st.info(
        "Ainda não há nenhuma view ou função criada (com o prefixo 'msb_') na base de "
        "dados. Crie uma no SQL Editor do Supabase — aparece aqui automaticamente."
    )
    st.stop()

escolha = st.selectbox("Escolha uma análise", opcoes)

df = None
nome_exportacao = escolha

if escolha.endswith(SUFIXO_PARAM):
    nome_funcao = escolha.removesuffix(SUFIXO_PARAM)
    nome_exportacao = nome_funcao
    parametros = funcoes_parametrizadas[nome_funcao]

    st.markdown(f"##### Parâmetros de `{nome_funcao}`")
    valores = {}
    with st.form(f"form_{nome_funcao}"):
        for nome_param, tipo in parametros:
            tipo_lower = tipo.lower()
            if "date" in tipo_lower or "timestamp" in tipo_lower:
                valores[nome_param] = st.date_input(nome_param)
            elif any(t in tipo_lower for t in ("int", "numeric", "real", "double", "float")):
                valores[nome_param] = st.number_input(nome_param, step=1.0)
            elif "bool" in tipo_lower:
                valores[nome_param] = st.checkbox(nome_param)
            else:
                valores[nome_param] = st.text_input(nome_param)
        executar = st.form_submit_button("▶️ Executar", type="primary")

    if executar:
        with st.spinner("A correr..."):
            df = call_function(nome_funcao, valores)
else:
    df = load_analise(escolha)

if df is not None:
    st.markdown(f"##### Resultado — `{escolha}`")
    st.write(f"{len(df):,} linhas, {len(df.columns)} colunas".replace(",", " "))
    st.dataframe(df, width='stretch', height=450)

    st.markdown("---")
    st.markdown("#### Exportar")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Exportar CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"{nome_exportacao}.csv",
            mime="text/csv",
        )
    with c2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=nome_exportacao[:31])
        st.download_button(
            "⬇️ Exportar Excel",
            data=buffer.getvalue(),
            file_name=f"{nome_exportacao}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
