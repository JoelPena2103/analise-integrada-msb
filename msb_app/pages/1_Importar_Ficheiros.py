import streamlit as st
import pandas as pd

from utils.io_utils import save_uploaded_file, load_csv, file_exists, READ_CONFIG
from utils.branding import set_logo




st.set_page_config(page_title="Importar Ficheiros — MSB", page_icon="📥", layout="wide")
set_logo()
st.title("📥 Importar Ficheiros")
st.caption(
    "Os ficheiros importados ficam guardados na pasta de dados da aplicação, "
    "servindo de base de dados para os passos seguintes do pipeline."
)


def import_block(key: str, titulo: str, descricao: str, exemplo_cols: list[str] | None = None):
    st.markdown(f"### {titulo}")
    st.caption(descricao)
    cfg = READ_CONFIG[key]
    delim = "auto-detetado" if cfg.get("sep") is None else f"`{cfg['sep']}`"
    st.caption(f"Delimitador: {delim} · Encoding: `{cfg.get('encoding', 'utf-8')}`")

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
    "maintenance_profiles",
    "maintenance_profiles.csv",
    "Perfis de veículos (um perfil = um grupo de carid's), identificados por msbKey. "
    "Delimitador ',' .",
    exemplo_cols=["id", "msbKey", "make", "model", "mark", "engineSize", "fuelType",
                  "powerHp", "msbQuality", "status", "maxEndDate"],
)

import_block(
    "cars",
    "cars.csv",
    "Informação de carId's (um carId = um veículo concreto). Delimitador ',' . "
    "Liga-se ao maintenance_profiles através do msbKey (ambos em minúsculas). "
    "Só contam os carId's com country == 'PO' (configurável na página Construir Maintenance).",
    exemplo_cols=["msbKey", "carId", "make", "model", "status", "country"],
)

import_block(
    "matriculas",
    "Matriculas.csv",
    "Matrículas e VIN de alguns veículos, ligados por CARID.",
    exemplo_cols=["CARID", "Matricula", "VIN"],
)

import_block(
    "kinto_prioridade",
    "kinto_prioridade.csv",
    "Número de prioridade Kinto por marca. Delimitador ';' .",
)

st.markdown("### Próximo passo")
st.write(
    "Depois de importar o **maintenance_profiles.csv**, siga para a página "
    "**🔑 Gerador Keys** para calcular as quality keys e a previsão de qualidade."
)


 