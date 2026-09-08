import pandas as pd
import streamlit as st

from utils.io_utils import file_exists, load_csv, save_csv
from utils.branding import set_logo
from utils.kinto_logic import extract_ano_mes, upsert_monthly, MESES_PT

st.set_page_config(page_title="Kinto Analisis — Importar", page_icon="🗓️", layout="wide")
set_logo()
st.title("🗓️ Fase 3 — Kinto Analisis — Importar Ficheiros")
st.caption(
    "Importe os ficheiros mensais kinto_Maintenance_Profile e kinto_Vehicle_All. "
    "O mês e o ano são detetados automaticamente pelo nome do ficheiro (pode corrigir "
    "antes de confirmar). O kinto_Maintenance_Profile acumula num histórico mensal "
    "(reimportar um mês substitui-o, sem duplicar); o kinto_Vehicle_All mantém sempre "
    "só o ficheiro mais recente."
)

ANOS_DISPONIVEIS = list(range(2026, 2047))
OPCOES_MES = [MESES_PT[m] for m in range(1, 13)]
MES_NOME_PARA_NUM = {v: k for k, v in MESES_PT.items()}


def render_import_block(
    titulo: str,
    descricao: str,
    historico_key: str,
    uploader_key: str,
    modo: str = "historico",
):
    st.markdown(f"### {titulo}")
    st.caption(descricao)
    st.caption("Delimitador: `;` (tal como exportado) · Encoding: `utf-8`")
    if modo == "ultimo_ficheiro":
        st.caption(
            "⚠️ Esta tabela **não** acumula meses — mantém sempre apenas o último "
            "ficheiro importado (com as colunas 'ano'/'mes' desse mês). Importar um "
            "novo ficheiro substitui por completo o anterior."
        )

    uploaded_files = st.file_uploader(
        f"Carregar ficheiros mensais — {titulo}",
        type=["csv"],
        accept_multiple_files=True,
        key=uploader_key,
        label_visibility="collapsed",
    )

    if uploaded_files:
        linhas = []
        for f in uploaded_files:
            ano_detetado, mes_detetado = extract_ano_mes(f.name)
            linhas.append({
                "ficheiro": f.name,
                "ano": ano_detetado if ano_detetado else ANOS_DISPONIVEIS[0],
                "mes": MESES_PT.get(mes_detetado, OPCOES_MES[0]),
            })
        tabela_confirmacao = pd.DataFrame(linhas)

        st.write("Confirme (ou corrija) o mês/ano de cada ficheiro antes de importar:")
        tabela_editada = st.data_editor(
            tabela_confirmacao,
            width='stretch',
            hide_index=True,
            disabled=["ficheiro"],
            column_config={
                "ficheiro": st.column_config.TextColumn("Ficheiro"),
                "ano": st.column_config.SelectboxColumn("Ano", options=ANOS_DISPONIVEIS, required=True),
                "mes": st.column_config.SelectboxColumn("Mês", options=OPCOES_MES, required=True),
            },
            key=f"editor_{uploader_key}",
        )

        rotulo_botao = "▶️ Substituir pelo mais recente" if modo == "ultimo_ficheiro" else "▶️ Adicionar ao histórico"
        if st.button(f"{rotulo_botao} — {titulo}", type="primary", key=f"btn_{uploader_key}"):
            with st.spinner("A processar ficheiros..."):
                ficheiros_lidos = []
                for f, (_, linha) in zip(uploaded_files, tabela_editada.iterrows()):
                    try:
                        df_mes = pd.read_csv(f, sep=";", dtype=str, encoding="utf-8")
                    except UnicodeDecodeError:
                        f.seek(0)
                        df_mes = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1")

                    ano = int(linha["ano"])
                    mes = MES_NOME_PARA_NUM[linha["mes"]]
                    ficheiros_lidos.append((ano, mes, df_mes))

                if modo == "ultimo_ficheiro":
                    # Mantém só o ficheiro mais recente (maior ano, depois maior mês)
                    ano, mes, historico = max(ficheiros_lidos, key=lambda t: (t[0], t[1]))
                    historico = historico.copy()
                    historico["ano"] = ano
                    historico["mes"] = mes
                    total_linhas_antes = len(load_csv(historico_key)) if file_exists(historico_key) else 0
                else:
                    historico = load_csv(historico_key) if file_exists(historico_key) else None
                    total_linhas_antes = len(historico) if historico is not None else 0
                    for ano, mes, df_mes in ficheiros_lidos:
                        historico = upsert_monthly(historico, df_mes, ano, mes)

            save_csv(historico, historico_key)
            st.success(
                f"Ficheiro atualizado: {total_linhas_antes:,} → {len(historico):,} linhas."
                .replace(",", " ")
            )
            st.rerun()

    st.markdown("---")
    st.markdown("#### Ficheiro atual" if modo == "ultimo_ficheiro" else "#### Histórico atual")
    if file_exists(historico_key):
        historico_atual = load_csv(historico_key)
        historico_atual["ano"] = pd.to_numeric(historico_atual["ano"], errors="coerce")
        historico_atual["mes"] = pd.to_numeric(historico_atual["mes"], errors="coerce")

        resumo = (
            historico_atual.groupby(["ano", "mes"])
            .size()
            .reset_index(name="linhas")
            .sort_values(["ano", "mes"])
        )
        resumo["mês"] = resumo["mes"].map(MESES_PT)
        st.dataframe(
            resumo[["ano", "mês", "linhas"]],
            width='stretch',
            hide_index=True,
        )
        st.caption(f"Total: {len(historico_atual):,} linhas.".replace(",", " "))
    else:
        st.info("Ainda sem ficheiro importado.")

    st.markdown("---")


render_import_block(
    titulo="kinto_Maintenance_Profile",
    descricao=(
        "Perfis de manutenção mensais exportados pela Kinto. Serão ligados às linhas "
        "'kinto' do maintenance.csv da Fase 1 (chave: MsbKeyID ↔ id) no Dashboard."
    ),
    historico_key="kinto_maintenance_historico",
    uploader_key="uploader_kinto_maintenance",
    modo="historico",
)

render_import_block(
    titulo="kinto_Vehicle_All",
    descricao=(
        "Veículos/carid's do mês mais recente exportados pela Kinto. Serão comparados "
        "com o total de carid's do maintenance.csv (linhas 'kinto') da Fase 1, por marca."
    ),
    historico_key="kinto_vehicle_historico",
    uploader_key="uploader_kinto_vehicle",
    modo="ultimo_ficheiro",
)

st.write("Próximo passo: página **📅 Kinto Dashboard** para analisar e exportar.")
