import io

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.io_utils import file_exists, load_csv
from utils.branding import set_logo
from utils.kinto_logic import (
    MESES_PT, find_col, merge_kinto_maintenance, merge_kinto_vehicle, monthly_diff_summary,
)

st.set_page_config(page_title="Kinto Dashboard — MSB", page_icon="📅", layout="wide")
set_logo()
st.title("📅 Kinto Dashboard")
st.caption(
    "Evolução mensal do kinto_Maintenance_Profile e do kinto_Vehicle_All, ligados às "
    "bases da Fase 1."
)


def multiselect_filter(df_in: pd.DataFrame, col: str | None, label: str) -> pd.DataFrame:
    if not col or col not in df_in.columns:
        return df_in
    opcoes = sorted([o for o in df_in[col].dropna().unique().tolist()], key=str)
    escolha = st.sidebar.multiselect(label, opcoes, key=f"kinto_filtro_{label}")
    if escolha:
        return df_in[df_in[col].isin(escolha)]
    return df_in


def excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for nome_folha, dados in sheets.items():
            if dados is None or dados.empty:
                continue
            dados.to_excel(writer, index=False, sheet_name=nome_folha[:31])
    return buffer.getvalue()


def prepare_merged(historico_key: str, base_key: str, merge_fn) -> pd.DataFrame:
    """Liga o histórico à base da Fase 1, sem aplicar filtros (usado como
    fallback para a exportação de um separador ainda não visitado)."""
    if not file_exists(historico_key):
        return pd.DataFrame()
    historico = load_csv(historico_key)
    historico["ano"] = pd.to_numeric(historico["ano"], errors="coerce")
    historico["mes"] = pd.to_numeric(historico["mes"], errors="coerce")
    if file_exists(base_key):
        return merge_fn(historico, load_csv(base_key))
    return historico


def render_tab(
    label: str,
    df: pd.DataFrame,
    id_col_candidates: list[str],
    make_col_candidates: list[str],
    value_col_candidates: list[str],
    value_col_label: str,
) -> pd.DataFrame:
    """Renderiza um separador completo (filtros + KPIs + gráficos) a partir
    de um dataframe já ligado à base da Fase 1, e devolve a tabela filtrada,
    para ser usada depois na exportação Excel."""
    if df.empty:
        st.warning("Ainda não há histórico importado. Vá à página **🗓️ Importar Ficheiros** (Fase 3).")
        return df

    id_col = find_col(df, id_col_candidates)
    make_col = find_col(df, make_col_candidates)
    value_col = find_col(df, value_col_candidates)

    st.sidebar.markdown(f"**Filtros — {label}**")
    df_filtrado = df.copy()
    df_filtrado = multiselect_filter(df_filtrado, make_col, "Marca")
    df_filtrado = multiselect_filter(df_filtrado, value_col, value_col_label)
    df_filtrado = multiselect_filter(df_filtrado, "ano", "Ano")

    if "mes" in df_filtrado.columns:
        meses_existentes = sorted(df_filtrado["mes"].dropna().unique().tolist())
        opcoes_mes_label = [MESES_PT.get(int(m), str(m)) for m in meses_existentes]
        escolha_mes = st.sidebar.multiselect("Mês", opcoes_mes_label, key=f"kinto_filtro_mes_{label}")
        if escolha_mes:
            mes_nums = [m for m in meses_existentes if MESES_PT.get(int(m)) in escolha_mes]
            df_filtrado = df_filtrado[df_filtrado["mes"].isin(mes_nums)]

    st.sidebar.markdown("---")

    # --- KPIs -----------------------------------------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("Linhas (id x mês)", f"{len(df_filtrado):,}".replace(",", " "))
    if id_col:
        k2.metric(f"{id_col} únicos", f"{df_filtrado[id_col].nunique():,}".replace(",", " "))
    if make_col:
        k3.metric("Marcas distintas", df_filtrado[make_col].nunique())

    st.markdown("---")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Quantidade por marca")
        if make_col:
            contagem_make = df_filtrado[make_col].value_counts().reset_index()
            contagem_make.columns = ["marca", "quantidade"]
            fig = px.bar(contagem_make.head(20), x="marca", y="quantidade")
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Coluna de marca não encontrada.")

    with g2:
        st.markdown(f"##### Quantidade por {value_col_label.lower()}")
        if value_col:
            contagem_valor = df_filtrado[value_col].value_counts().reset_index()
            contagem_valor.columns = [value_col_label, "quantidade"]
            fig = px.bar(contagem_valor, x=value_col_label, y="quantidade")
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info(f"Coluna de {value_col_label.lower()} não encontrada.")

    st.markdown("---")
    st.markdown("##### Evolução por mês")
    visualizacao = st.radio(
        "Visualização", ["Acumulado", "Diferença vs. mês anterior"],
        horizontal=True, key=f"kinto_viz_{label}",
    )

    if "ano" in df_filtrado.columns and "mes" in df_filtrado.columns:
        df_filtrado["periodo"] = (
            df_filtrado["ano"].astype("Int64").astype(str) + "-"
            + df_filtrado["mes"].astype("Int64").map(MESES_PT)
        )
        ordem_periodos = (
            df_filtrado[["ano", "mes", "periodo"]]
            .dropna()
            .drop_duplicates()
            .sort_values(["ano", "mes"])["periodo"]
            .tolist()
        )

        if visualizacao == "Acumulado" and value_col:
            evolucao = (
                df_filtrado.groupby(["periodo", value_col]).size().reset_index(name="quantidade")
            )
            fig = px.bar(
                evolucao, x="periodo", y="quantidade", color=value_col,
                category_orders={"periodo": ordem_periodos}, barmode="stack",
            )
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text=value_col_label)
            st.plotly_chart(fig, width='stretch')
        elif visualizacao == "Diferença vs. mês anterior" and id_col and value_col:
            diff = monthly_diff_summary(df_filtrado, id_col=id_col, value_col=value_col)
            if diff.empty:
                st.info("É preciso pelo menos 2 meses (com dados) para calcular diferenças.")
            else:
                diff["periodo"] = diff["ano"].astype(int).astype(str) + "-" + diff["mes"].astype(int).map(MESES_PT)
                plot_df = diff.melt(
                    id_vars="periodo", value_vars=["novos", "alterados", "sem_alteracao"],
                    var_name="tipo", value_name="quantidade",
                )
                fig = px.bar(plot_df, x="periodo", y="quantidade", color="tipo", barmode="group")
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
                st.plotly_chart(fig, width='stretch')
                with st.expander("Ver tabela de diferenças"):
                    st.dataframe(diff, width='stretch', hide_index=True)
        else:
            st.info("Não há colunas suficientes para esta visualização.")
    else:
        st.info("Sem colunas 'ano'/'mes' no histórico.")

    st.markdown("---")
    st.markdown("##### Tabela")
    st.dataframe(df_filtrado, width='stretch', height=420)

    return df_filtrado


OPCOES_SEPARADOR = ["🔧 Maintenance", "🚗 Vehicle All"]
st.markdown(
    """
<style>
div[data-testid="stRadio"] > div {flex-direction: row; gap: 0.5rem;}
</style>
""",
    unsafe_allow_html=True,
)
separador_ativo = st.radio(
    "Separador", OPCOES_SEPARADOR, horizontal=True, label_visibility="collapsed", key="kinto_separador_ativo"
)
st.markdown("---")

merged_maintenance = prepare_merged("kinto_maintenance_historico", "maintenance", merge_kinto_maintenance)
merged_vehicle = prepare_merged("kinto_vehicle_historico", "cars", merge_kinto_vehicle)

if separador_ativo == "🔧 Maintenance":
    tabela_maintenance = render_tab(
        label="Maintenance",
        df=merged_maintenance,
        id_col_candidates=["MsbKeyID", "id"],
        make_col_candidates=["Make", "make"],
        value_col_candidates=["msbQuality"],
        value_col_label="Qualidade",
    )
    tabela_vehicle = merged_vehicle
else:
    tabela_vehicle = render_tab(
        label="Vehicle All",
        df=merged_vehicle,
        id_col_candidates=["CarID", "CARID", "carId"],
        make_col_candidates=["Make", "make"],
        value_col_candidates=["Status", "status"],
        value_col_label="Status",
    )
    tabela_maintenance = merged_maintenance

st.markdown("---")
st.markdown("#### Exportar análise")

c1, c2 = st.columns(2)
with c1:
    sheet_atual = {
        "🔧 Maintenance": "Kinto_Maintenance",
        "🚗 Vehicle All": "Kinto_Vehicle_All",
    }[separador_ativo]
    tabela_atual = tabela_maintenance if separador_ativo == "🔧 Maintenance" else tabela_vehicle
    st.download_button(
        f"⬇️ Exportar Excel — separador atual ({separador_ativo})",
        data=excel_bytes({sheet_atual: tabela_atual}),
        file_name="kinto_analise_separador.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with c2:
    st.download_button(
        "⬇️ Exportar Excel — todos os separadores",
        data=excel_bytes({
            "Kinto_Maintenance": tabela_maintenance,
            "Kinto_Vehicle_All": tabela_vehicle,
        }),
        file_name="kinto_analise_completa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
