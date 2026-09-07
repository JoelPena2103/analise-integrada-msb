import datetime
import io

import pandas as pd
import streamlit as st

from utils.io_utils import file_exists, load_csv, save_csv
from utils.merge_logic import build_maintenance
from utils.branding import set_logo

st.set_page_config(page_title="Construir Maintenance — MSB", page_icon="🗄️", layout="wide")
set_logo()
st.title("🗄️ Construir `maintenance.csv`")
st.caption(
    "Liga o maintenance_profiles_FINAL ao cars.csv (contagem de carid's), às "
    "matrículas (matricula, VIN, leasys matriculas) e à prioridade Kinto."
)

faltam_ficheiros = []
if not file_exists("maintenance_profiles_final"):
    faltam_ficheiros.append("maintenance_profiles_FINAL (gere-o na página 🔑 Gerador Keys)")
if not file_exists("cars"):
    faltam_ficheiros.append("cars.csv")

if faltam_ficheiros:
    st.warning("Faltam ficheiros obrigatórios:\n\n- " + "\n- ".join(faltam_ficheiros))
    st.stop()

mp_final = load_csv("maintenance_profiles_final")
cars = load_csv("cars")
matriculas = load_csv("matriculas") if file_exists("matriculas") else None
kinto_prioridade = load_csv("kinto_prioridade") if file_exists("kinto_prioridade") else None

col1, col2, col3 = st.columns(3)
col1.metric("maintenance_profiles_FINAL", f"{len(mp_final):,}".replace(",", " ") + " linhas")
col2.metric("cars.csv", f"{len(cars):,}".replace(",", " ") + " linhas")
col3.metric(
    "Matriculas.csv",
    (f"{len(matriculas):,}".replace(",", " ") + " linhas") if matriculas is not None else "não importado",
)

if matriculas is None:
    st.info("Matriculas.csv não foi importado — as colunas 'matricula', 'VIN' e "
             "'leasys_matriculas' ficarão vazias/zero.")
if kinto_prioridade is None:
    st.info("kinto_prioridade.csv não foi importado — a coluna 'kinto_prioridade' ficará vazia.")

st.markdown("---")
st.markdown("#### Filtro de país para contagem de carid's")
st.caption(
    "Só são contados (e usados para matrículas/VIN) os carId cujo country seja igual "
    "ao valor indicado. carId's de outros países (ex.: 'SQ') contam como 0."
)
country_filter = st.text_input("Country a considerar", value="PO").strip() or None

st.markdown("---")
st.markdown("#### Regra da coluna `kinto`")
st.caption(
    "Ids com status 'Ativo' e contagem_carids > 0 são marcados como 'kinto' (um id com "
    "0 carid's só tem veículos de outro país e não conta). Ids com status "
    "'Descontinuado' também precisam de contagem_carids > 0, e além disso só são 'kinto' "
    "se o maxEndDate estiver a menos de (ou igual a) X dias de distância da data de "
    "referência — em qualquer sentido, passado ou futuro."
)
c1, c2 = st.columns(2)
ref_date = c1.date_input("Data de referência", value=datetime.date.today())
dias_limite = c2.number_input("Limite em dias (1 ano = 365)", min_value=1, value=365, step=1)

st.markdown("---")

if st.button("▶️ Construir maintenance.csv", type="primary"):
    with st.spinner("A ligar ficheiros..."):
        try:
            df_maintenance = build_maintenance(
                mp_final,
                cars,
                matriculas,
                kinto_prioridade,
                ref_date=pd.Timestamp(ref_date),
                country_filter=country_filter,
            )
            # aplicar dias_limite custom, se diferente de 365
            if dias_limite != 365:
                from utils.merge_logic import compute_kinto
                df_maintenance["kinto"] = compute_kinto(
                    df_maintenance, ref_date=pd.Timestamp(ref_date), dias_limite=dias_limite
                )
        except Exception as e:  # noqa: BLE001
            st.error(f"Erro ao construir maintenance.csv: {e}")
            st.stop()

    st.session_state["maintenance_df"] = df_maintenance
    st.success(f"maintenance.csv construído com {len(df_maintenance):,} linhas.".replace(",", " "))

if "maintenance_df" in st.session_state:
    df_maintenance = st.session_state["maintenance_df"]

    st.markdown("#### Pré-visualização")
    st.dataframe(df_maintenance.head(100), width='stretch')

    st.markdown("#### Edição manual — `checkdate` e `observacoes`")
    st.caption(
        "Pode editar diretamente estas duas colunas (por exemplo, para registar quando "
        "verificou um id, ou notas). As restantes colunas não são editáveis aqui."
    )
    cols_editaveis = ["id", "msbKey", "make", "status", "checkdate", "observacoes"]
    cols_editaveis = [c for c in cols_editaveis if c in df_maintenance.columns]
    edit_df = st.data_editor(
        df_maintenance[cols_editaveis],
        width='stretch',
        num_rows="fixed",
        disabled=[c for c in cols_editaveis if c not in ("checkdate", "observacoes")],
        key="editor_maintenance",
    )
    if st.button("Aplicar edições de checkdate / observações"):
        df_maintenance.loc[edit_df.index, "checkdate"] = edit_df["checkdate"]
        df_maintenance.loc[edit_df.index, "observacoes"] = edit_df["observacoes"]
        st.session_state["maintenance_df"] = df_maintenance
        st.success("Edições aplicadas (ainda não guardadas em disco).")

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 Guardar maintenance.csv", type="primary"):
            save_csv(df_maintenance, "maintenance")
            st.success("maintenance.csv guardado com sucesso.")
    with c2:
        st.download_button(
            "⬇️ Descarregar CSV",
            data=df_maintenance.to_csv(index=False).encode("utf-8"),
            file_name="maintenance.csv",
            mime="text/csv",
        )
    with c3:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_maintenance.to_excel(writer, index=False, sheet_name="maintenance")
        st.download_button(
            "⬇️ Descarregar Excel",
            data=buffer.getvalue(),
            file_name="maintenance.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.markdown("---")
st.write("Próximo passo: página **📊 Dashboard & Análises** para filtrar, visualizar e exportar.")
