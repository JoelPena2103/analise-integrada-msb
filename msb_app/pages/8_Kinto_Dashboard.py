import io

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.io_utils import file_exists, load_csv
from utils.branding import set_logo
from utils.kinto_logic import (
    MESES_PT, find_col, filter_kinto, merge_kinto_maintenance,
    monthly_diff_summary, kinto_relation_by_make, quality_breakdown_by_make,
)

st.set_page_config(page_title="Kinto Dashboard — MSB", page_icon="📅", layout="wide")
set_logo()
st.title("📅 Kinto Dashboard")
st.caption(
    "Comparação entre os ficheiros mensais da Kinto e as linhas 'kinto' do "
    "maintenance.csv da Fase 1 — só faz sentido comparar o que já sabemos ser kinto."
)


def multiselect_filter(df_in: pd.DataFrame, col: str | None, label: str, key: str) -> pd.DataFrame:
    if not col or col not in df_in.columns:
        return df_in
    opcoes = sorted([o for o in df_in[col].dropna().unique().tolist()], key=str)
    escolha = st.sidebar.multiselect(label, opcoes, key=key)
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


# ---------------------------------------------------------------------------
# Base comum às duas análises: maintenance.csv, só linhas kinto == "kinto"
# ---------------------------------------------------------------------------
if not file_exists("maintenance"):
    st.warning("Ainda não existe `maintenance.csv` (Fase 1). Construa-o primeiro.")
    st.stop()

maintenance_kinto = filter_kinto(load_csv("maintenance"))
if maintenance_kinto.empty:
    st.warning("Não há nenhuma linha com kinto == 'kinto' em maintenance.csv.")
    st.stop()


def build_maintenance_merged() -> pd.DataFrame:
    """Histórico kinto_Maintenance_Profile ligado (inner) às linhas kinto do
    maintenance.csv — sem filtros nem UI (usado também como fallback de export)."""
    if not file_exists("kinto_maintenance_historico"):
        return pd.DataFrame()
    historico = load_csv("kinto_maintenance_historico")
    historico["ano"] = pd.to_numeric(historico["ano"], errors="coerce")
    historico["mes"] = pd.to_numeric(historico["mes"], errors="coerce")
    return merge_kinto_maintenance(historico, maintenance_kinto, how="inner")


def build_vehicle_sheets() -> dict[str, pd.DataFrame]:
    """Relação de carid's por marca + qualidades — sem filtros nem UI (usado
    também como fallback de export)."""
    if not file_exists("kinto_vehicle_historico"):
        return {}
    vehicle_snapshot = load_csv("kinto_vehicle_historico")
    relacao = kinto_relation_by_make(maintenance_kinto, vehicle_snapshot)
    qualidade = quality_breakdown_by_make(maintenance_kinto)
    return {"Relacao_CarIDs_Marca": relacao, "Qualidade_Kinto_Marca": qualidade}


def render_maintenance_tab(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if df.empty:
        st.warning("Ainda não há histórico kinto_Maintenance_Profile. Vá à página **🗓️ Kinto Importar**.")
        return {}

    id_col = find_col(df, ["MsbKeyID", "id"])
    make_col = find_col(df, ["Make", "make"])
    quality_col = find_col(df, ["msbQuality"])

    st.sidebar.markdown("**Filtros — Maintenance**")
    df_filtrado = df.copy()
    df_filtrado = multiselect_filter(df_filtrado, make_col, "Marca", "kinto_mnt_marca")
    df_filtrado = multiselect_filter(df_filtrado, quality_col, "Qualidade", "kinto_mnt_qualidade")
    df_filtrado = multiselect_filter(df_filtrado, "ano", "Ano", "kinto_mnt_ano")

    if "mes" in df_filtrado.columns:
        meses_existentes = sorted(df_filtrado["mes"].dropna().unique().tolist())
        opcoes_mes_label = [MESES_PT.get(int(m), str(m)) for m in meses_existentes]
        escolha_mes = st.sidebar.multiselect("Mês", opcoes_mes_label, key="kinto_mnt_mes")
        if escolha_mes:
            mes_nums = [m for m in meses_existentes if MESES_PT.get(int(m)) in escolha_mes]
            df_filtrado = df_filtrado[df_filtrado["mes"].isin(mes_nums)]

    st.sidebar.markdown("---")

    k1, k2, k3 = st.columns(3)
    k1.metric("Linhas (id x mês)", f"{len(df_filtrado):,}".replace(",", " "))
    if id_col:
        k2.metric("MsbKeyID únicos", f"{df_filtrado[id_col].nunique():,}".replace(",", " "))
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
        st.markdown("##### Quantidade por qualidade")
        if quality_col:
            contagem_valor = df_filtrado[quality_col].value_counts().reset_index()
            contagem_valor.columns = ["Qualidade", "quantidade"]
            fig = px.bar(contagem_valor, x="Qualidade", y="quantidade")
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Coluna de qualidade não encontrada.")

    st.markdown("---")
    st.markdown("##### Evolução por mês")
    visualizacao = st.radio(
        "Visualização", ["Acumulado", "Diferença vs. mês anterior"],
        horizontal=True, key="kinto_mnt_viz",
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

        if visualizacao == "Acumulado" and quality_col:
            evolucao = df_filtrado.groupby(["periodo", quality_col]).size().reset_index(name="quantidade")
            fig = px.bar(
                evolucao, x="periodo", y="quantidade", color=quality_col,
                category_orders={"periodo": ordem_periodos}, barmode="stack",
            )
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="Qualidade")
            st.plotly_chart(fig, width='stretch')
        elif visualizacao == "Diferença vs. mês anterior" and id_col and quality_col:
            diff = monthly_diff_summary(df_filtrado, id_col=id_col, value_col=quality_col)
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
        st.info("Sem colunas 'ano'/'mes' no histórico.")

    st.markdown("---")
    st.markdown("##### Tabela")
    st.dataframe(df_filtrado, width='stretch', height=420)

    return {"Kinto_Maintenance": df_filtrado}


def render_vehicle_tab(relacao: pd.DataFrame, qualidade: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not file_exists("kinto_vehicle_historico"):
        st.warning("Ainda não há ficheiro kinto_Vehicle_All importado. Vá à página **🗓️ Kinto Importar**.")
        return {}

    vehicle_snapshot = load_csv("kinto_vehicle_historico")
    ano_snap = pd.to_numeric(vehicle_snapshot["ano"], errors="coerce").iloc[0] if "ano" in vehicle_snapshot.columns else None
    mes_snap = pd.to_numeric(vehicle_snapshot["mes"], errors="coerce").iloc[0] if "mes" in vehicle_snapshot.columns else None
    if ano_snap and mes_snap:
        st.caption(f"Ficheiro atual: **{MESES_PT.get(int(mes_snap), mes_snap)}/{int(ano_snap)}**")

    st.sidebar.markdown("**Filtros — Vehicle All**")
    relacao_filtrada = multiselect_filter(relacao, "make", "Marca", "kinto_veh_marca")
    if "make" in qualidade.columns and "make" in relacao_filtrada.columns:
        marcas_selecionadas = relacao_filtrada["make"].unique().tolist()
        if len(marcas_selecionadas) < len(relacao["make"].unique()):
            qualidade = qualidade[qualidade["make"].isin(marcas_selecionadas)]
    st.sidebar.markdown("---")

    total_sistema = int(relacao_filtrada["carids_sistema"].sum()) if "carids_sistema" in relacao_filtrada.columns else 0
    total_export = int(relacao_filtrada["carids_export"].sum()) if "carids_export" in relacao_filtrada.columns else 0
    pct_global = round(total_export / total_sistema * 100, 2) if total_sistema > 0 else 0.0

    k1, k2, k3 = st.columns(3)
    k1.metric("Total carid's — sistema (kinto)", f"{total_sistema:,}".replace(",", " "))
    k2.metric("Total carid's — último export", f"{total_export:,}".replace(",", " "))
    k3.metric("% cobertura", f"{pct_global}%")

    st.markdown("---")
    st.markdown("##### Relação de carid's por marca (export vs. sistema)")
    if not relacao_filtrada.empty:
        def _cor(pct):
            if pct > 80:
                return "≥ 80%"
            elif pct >= 70:
                return "70–80%"
            return "< 70%"

        plot_df = relacao_filtrada.copy()
        plot_df["faixa"] = plot_df["percentagem"].apply(_cor)
        fig = px.bar(
            plot_df, x="percentagem", y="make", orientation="h", color="faixa",
            color_discrete_map={"≥ 80%": "#55A868", "70–80%": "#F0C808", "< 70%": "#DD8452"},
            text="percentagem",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="% cobertura", yaxis_title="")
        st.plotly_chart(fig, width='stretch')

        with st.expander("Ver tabela de relação"):
            st.dataframe(relacao_filtrada, width='stretch', hide_index=True)
    else:
        st.info("Sem dados suficientes para calcular a relação por marca.")

    st.markdown("---")
    st.markdown("##### Qualidades (linhas kinto do maintenance.csv)")
    if not qualidade.empty:
        st.dataframe(qualidade, width='stretch', hide_index=True)
    else:
        st.info("Coluna de qualidade não encontrada em maintenance.csv.")

    return {"Relacao_CarIDs_Marca": relacao_filtrada, "Qualidade_Kinto_Marca": qualidade}


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

if separador_ativo == "🔧 Maintenance":
    sheets_maintenance = render_maintenance_tab(build_maintenance_merged())
    sheets_vehicle = build_vehicle_sheets()
else:
    veh_sheets_base = build_vehicle_sheets()
    sheets_vehicle = render_vehicle_tab(
        veh_sheets_base.get("Relacao_CarIDs_Marca", pd.DataFrame()),
        veh_sheets_base.get("Qualidade_Kinto_Marca", pd.DataFrame()),
    )
    sheets_maintenance = {"Kinto_Maintenance": build_maintenance_merged()}

st.markdown("---")
st.markdown("#### Exportar análise")

c1, c2 = st.columns(2)
with c1:
    sheets_atuais = sheets_maintenance if separador_ativo == "🔧 Maintenance" else sheets_vehicle
    st.download_button(
        f"⬇️ Exportar Excel — separador atual ({separador_ativo})",
        data=excel_bytes(sheets_atuais),
        file_name="kinto_analise_separador.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with c2:
    todas_as_folhas = {**sheets_maintenance, **sheets_vehicle}
    st.download_button(
        "⬇️ Exportar Excel — todos os separadores",
        data=excel_bytes(todas_as_folhas),
        file_name="kinto_analise_completa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
