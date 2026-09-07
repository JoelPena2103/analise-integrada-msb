import streamlit as st
import pandas as pd

from utils.io_utils import file_exists, load_csv, save_csv
from utils.keys_logic import gerar_keys, atribuir_qualidade, build_maintenance_profiles_final
from utils.branding import set_logo

st.set_page_config(page_title="Gerador Keys — MSB", page_icon="🔑", layout="wide")
set_logo()
st.title("🔑 Gerador de Keys + Previsão de Qualidade")
st.caption(
    "Gera as colunas quality1_key…quality4_key e propaga a qualidade dos veículos "
    "com msbQuality = 4 para os veículos 'irmãos' com qualidade menor."
)

if not file_exists("maintenance_profiles"):
    st.warning(
        "Ainda não importou o maintenance_profiles.csv. Vá à página "
        "**📥 Importar Ficheiros** primeiro."
    )
    st.stop()

df_raw = load_csv("maintenance_profiles")

st.markdown("#### Ficheiro de origem: `maintenance_profiles.csv`")
st.write(f"{len(df_raw):,} linhas, {len(df_raw.columns)} colunas".replace(",", " "))

with st.expander("Pré-visualizar dados de origem"):
    st.dataframe(df_raw.head(50), width='stretch')

colunas_obrigatorias = ["id", "make", "model", "mark", "engineSize", "fuelType", "powerHp", "msbQuality"]
faltam = [c for c in colunas_obrigatorias if c not in df_raw.columns]
if faltam:
    st.error(f"Faltam colunas obrigatórias no ficheiro: {faltam}")
    st.stop()

st.markdown("---")

if st.button("▶️ Gerar keys e prever qualidade", type="primary"):
    with st.spinner("A calcular quality keys..."):
        df_keys = gerar_keys(df_raw)
        df_result, contagens = atribuir_qualidade(df_keys)

    st.session_state["maintenance_profiles_result"] = df_result
    st.session_state["maintenance_profiles_contagens"] = contagens
    st.success("Cálculo concluído.")

if "maintenance_profiles_result" in st.session_state:
    df_result = st.session_state["maintenance_profiles_result"]
    contagens = st.session_state["maintenance_profiles_contagens"]

    st.markdown("#### Resumo das cópias de qualidade")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Copiados nível 4", contagens.get(4, 0))
    c2.metric("Copiados nível 3", contagens.get(3, 0))
    c3.metric("Copiados nível 2", contagens.get(2, 0))
    c4.metric("Copiados nível 1", contagens.get(1, 0))

    st.markdown("#### Distribuição de qualidade (antes vs. depois)")
    dist_antes = df_result["msbQuality"].value_counts().sort_index()
    dist_depois = df_result["predictedQuality"].value_counts().sort_index()
    dist_df = pd.DataFrame(
        {"msbQuality (original)": dist_antes, "predictedQuality (prevista)": dist_depois}
    ).fillna(0).astype(int)
    st.bar_chart(dist_df)

    with st.expander("Pré-visualizar resultado"):
        st.dataframe(df_result.head(100), width='stretch')

    st.markdown("---")
    st.markdown("#### Guardar como `maintenance_profiles_FINAL`")
    st.caption(
        "Se já existir um FINAL, as linhas existentes são atualizadas (apenas as colunas "
        "geradas) e as linhas novas são acrescentadas — tal como no script original."
    )

    if st.button("💾 Atualizar / criar maintenance_profiles_FINAL", type="primary"):
        df_existing = load_csv("maintenance_profiles_final") if file_exists("maintenance_profiles_final") else None
        df_final = build_maintenance_profiles_final(df_result, df_existing)
        save_csv(df_final, "maintenance_profiles_final")
        st.success(f"maintenance_profiles_FINAL guardado com {len(df_final):,} linhas.".replace(",", " "))

    st.download_button(
        "⬇️ Descarregar resultado (CSV)",
        data=df_result.to_csv(index=False).encode("utf-8"),
        file_name="maintenance_profiles_FINAL.csv",
        mime="text/csv",
    )

st.markdown("---")
st.write(
    "Próximo passo: página **🗄️ Construir Maintenance** para ligar este ficheiro ao "
    "cars.csv, matrículas e kinto prioridade."
)
