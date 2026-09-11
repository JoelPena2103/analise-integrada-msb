import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.io_utils import file_exists, load_csv
from utils.branding import set_logo
from utils.merge_logic import quality_ratio_by_make, compute_anos_diferenca

st.set_page_config(page_title="Dashboard — MSB", page_icon="📊", layout="wide")
set_logo()
st.title("📊 Dashboard & Análises")
st.caption("Filtre a base `maintenance.csv` e explore a informação com gráficos e tabela.")

if not file_exists("maintenance"):
    st.warning(
        "Ainda não existe `maintenance.csv`. Construa-o na página "
        "**🗄️ Construir Maintenance** primeiro."
    )
    st.stop()

df = load_csv("maintenance")

# --- normalizar tipos numéricos que vieram como str (dtype=str na leitura) ---
for col in ["contagem_carids", "leasys_matriculas", "kinto_prioridade", "markYear",
            "msbQuality", "predictedQuality"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Se o maintenance.csv foi gerado antes desta coluna existir, calcula-se aqui
# na hora (com a data de hoje como referência) para não obrigar a reconstruir.
if "anos_diferenca" in df.columns:
    df["anos_diferenca"] = pd.to_numeric(df["anos_diferenca"], errors="coerce").fillna(0).astype(int)
else:
    df["anos_diferenca"] = compute_anos_diferenca(df)

st.sidebar.header("Filtros")


def multiselect_filter(df_in: pd.DataFrame, col: str, label: str) -> pd.DataFrame:
    if col not in df_in.columns:
        return df_in
    opcoes = sorted([o for o in df_in[col].dropna().unique().tolist()])
    escolha = st.sidebar.multiselect(label, opcoes)
    if escolha:
        return df_in[df_in[col].isin(escolha)]
    return df_in


df_filtrado = df.copy()
df_filtrado = multiselect_filter(df_filtrado, "make", "Marca (make)")
df_filtrado = multiselect_filter(df_filtrado, "status", "Status")
df_filtrado = multiselect_filter(df_filtrado, "kinto", "Kinto")
df_filtrado = multiselect_filter(df_filtrado, "fuelType", "Combustível")
df_filtrado = multiselect_filter(df_filtrado, "msbQuality", "Qualidade")

busca_id = st.sidebar.text_input("Pesquisar por id / msbKey")
if busca_id:
    cols_busca = [c for c in ["id", "msbKey"] if c in df_filtrado.columns]
    mask = False
    for c in cols_busca:
        mask = mask | df_filtrado[c].astype(str).str.contains(busca_id, case=False, na=False)
    df_filtrado = df_filtrado[mask]

# --- Filtro (último): diferença de anos face ao maxEndDate ----------------
# Slider por opções (não numérico) para conseguir mostrar o maior valor à
# esquerda e o menor (0 = mais recente / sem data) à direita.
opcoes_anos = sorted(df_filtrado["anos_diferenca"].dropna().unique().tolist(), reverse=True)
if len(opcoes_anos) >= 2:
    sel_max, sel_min = st.sidebar.select_slider(
        "Diferença de anos (maxEndDate)",
        options=opcoes_anos,
        value=(opcoes_anos[0], opcoes_anos[-1]),
    )
    df_filtrado = df_filtrado[df_filtrado["anos_diferenca"].between(sel_min, sel_max)]
elif len(opcoes_anos) == 1:
    st.sidebar.caption(f"Diferença de anos (maxEndDate): {opcoes_anos[0]} (valor único)")

st.sidebar.markdown("---")
st.sidebar.write(f"**{len(df_filtrado):,} / {len(df):,} linhas**".replace(",", " "))

# --- KPIs -----------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ids filtrados", f"{len(df_filtrado):,}".replace(",", " "))
if "contagem_carids" in df_filtrado.columns:
    k2.metric("Total carid's", f"{int(df_filtrado['contagem_carids'].sum()):,}".replace(",", " "))
if "leasys_matriculas" in df_filtrado.columns:
    k3.metric("Total matrículas (leasys)", f"{int(df_filtrado['leasys_matriculas'].sum()):,}".replace(",", " "))
if "kinto" in df_filtrado.columns:
    k4.metric("Ids marcados 'kinto'", int((df_filtrado["kinto"] == "kinto").sum()))

st.markdown("---")

# ---------------------------------------------------------------------------
# Dados agregados (calculados uma vez, reutilizados na visualização e na
# exportação — assim a exportação reflete exatamente o que está no ecrã).
# ---------------------------------------------------------------------------
contagem_make = pd.DataFrame(columns=["make", "quantidade"])
if "make" in df_filtrado.columns:
    contagem_make = df_filtrado["make"].value_counts().reset_index()
    contagem_make.columns = ["make", "quantidade"]

status_df = pd.DataFrame(columns=["status", "quantidade"])
if "status" in df_filtrado.columns:
    status_df = df_filtrado["status"].value_counts().reset_index()
    status_df.columns = ["status", "quantidade"]

qual_df = pd.DataFrame(columns=["msbQuality", "quantidade"])
if "msbQuality" in df_filtrado.columns:
    qual_df = df_filtrado["msbQuality"].value_counts().sort_index().reset_index()
    qual_df.columns = ["msbQuality", "quantidade"]
    qual_df["msbQuality"] = qual_df["msbQuality"].astype("Int64").astype(str)

ratio_carids = quality_ratio_by_make(
    df_filtrado, quality_col="msbQuality", weight_col="contagem_carids"
)
ratio_msbs = quality_ratio_by_make(
    df_filtrado, quality_col="msbQuality", weight_col=None
)


def _tabela_percent(df_in: pd.DataFrame) -> pd.DataFrame:
    """Converte pct_alta/pct_baixa de fração (0-1) para percentagem (0-100)."""
    if df_in.empty:
        return df_in
    out = df_in.copy()
    for c in ("pct_alta", "pct_baixa"):
        if c in out.columns:
            out[c] = out[c] * 100
    return out


# ---------------------------------------------------------------------------
# Navegação por "separadores" — usamos st.radio (em vez de st.tabs) porque
# o Streamlit não expõe ao Python qual st.tabs está aberto no ecrã; com o
# radio conseguimos saber sempre o separador ativo, o que é necessário para
# a exportação Excel "do separador atual".
# ---------------------------------------------------------------------------
OPCOES_SEPARADOR = ["📈 Gráficos", "🏷️ Qualidade por Marca", "📋 Tabela"]

st.markdown(
    """
<style>
div[data-testid="stRadio"] > div {flex-direction: row; gap: 0.5rem;}
div[data-testid="stRadio"] label {
    border: 1px solid #363b47; border-radius: 8px 8px 0 0;
    padding: 0.4rem 1rem; margin-bottom: -1px;
}
</style>
""",
    unsafe_allow_html=True,
)
separador_ativo = st.radio(
    "Separador", OPCOES_SEPARADOR, horizontal=True, label_visibility="collapsed", key="separador_ativo"
)
st.markdown("---")

if separador_ativo == "📈 Gráficos":
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("##### Contagem de ids por marca")
        if not contagem_make.empty:
            fig = px.bar(contagem_make.head(20), x="make", y="quantidade")
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')

    with g2:
        st.markdown("##### Distribuição por status")
        if not status_df.empty:
            fig = px.pie(status_df, names="status", values="quantidade", hole=0.45)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')

    st.markdown("##### Qualidade (msbQuality)")
    if not qual_df.empty:
        fig = px.bar(qual_df, x="msbQuality", y="quantidade")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width='stretch')

elif separador_ativo == "🏷️ Qualidade por Marca":
    st.caption(
        "Relação, por marca, entre veículos com qualidade alta (msbQuality 2, 3 ou 4) "
        "e qualidade baixa (msbQuality 0 ou 1), face ao total."
    )

    st.markdown("##### Por nº de carid's")
    if not ratio_carids.empty:
        top_n = ratio_carids.head(20).copy()
        plot_df = top_n.melt(
            id_vars="make",
            value_vars=["pct_alta", "pct_baixa"],
            var_name="grupo",
            value_name="percentagem",
        )
        plot_df["grupo"] = plot_df["grupo"].map(
            {"pct_alta": "Qualidade 2/3/4", "pct_baixa": "Qualidade 0/1"}
        )
        fig = px.bar(plot_df, x="make", y="percentagem", color="grupo", barmode="group")
        fig.update_layout(
            yaxis_tickformat=".0%", margin=dict(l=10, r=10, t=10, b=10), legend_title_text=""
        )
        st.plotly_chart(fig, width='stretch')

        with st.expander("Ver dados desta relação (por carid's)"):
            st.dataframe(
                _tabela_percent(ratio_carids),
                width='stretch',
                column_config={
                    "pct_alta": st.column_config.NumberColumn("% qualidade 2/3/4", format="%.1f%%"),
                    "pct_baixa": st.column_config.NumberColumn("% qualidade 0/1", format="%.1f%%"),
                },
            )
    else:
        st.info("Sem dados suficientes (colunas 'make', 'msbQuality' ou 'contagem_carids' em falta).")

    st.markdown("---")
    st.markdown("##### Por nº de msbs (ids)")
    st.caption("Mesma relação, mas contando o nº de ids/msbs em vez da soma de carid's.")
    if not ratio_msbs.empty:
        st.dataframe(
            _tabela_percent(ratio_msbs),
            width='stretch',
            column_config={
                "total": st.column_config.NumberColumn("total de msbs"),
                "qtd_qualidade_234": st.column_config.NumberColumn("msbs qualidade 2/3/4"),
                "pct_alta": st.column_config.NumberColumn("% qualidade 2/3/4", format="%.1f%%"),
                "qtd_qualidade_01": st.column_config.NumberColumn("msbs qualidade 0/1"),
                "pct_baixa": st.column_config.NumberColumn("% qualidade 0/1", format="%.1f%%"),
            },
        )
    else:
        st.info("Sem dados suficientes (colunas 'make' ou 'msbQuality' em falta).")

else:  # "📋 Tabela"
    st.dataframe(df_filtrado, width='stretch', height=520)


def _sheets_do_separador(nome: str) -> dict[str, pd.DataFrame]:
    if nome == "📈 Gráficos":
        return {
            "Contagem_por_Marca": contagem_make,
            "Distribuicao_Status": status_df,
            "Qualidade_msbQuality": qual_df,
        }
    if nome == "🏷️ Qualidade por Marca":
        return {
            "Qualidade_por_Marca_CARIDS": _tabela_percent(ratio_carids),
            "Qualidade_por_Marca_MSBS": _tabela_percent(ratio_msbs),
        }
    return {"Dados_Filtrados": df_filtrado}


def _excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for nome_folha, dados in sheets.items():
            if dados is None:
                continue
            dados.to_excel(writer, index=False, sheet_name=nome_folha[:31])
    return buffer.getvalue()


st.markdown("---")
st.markdown("#### Exportar análise")

c1, c2 = st.columns(2)
with c1:
    st.download_button(
        f"⬇️ Exportar Excel — separador atual ({separador_ativo})",
        data=_excel_bytes(_sheets_do_separador(separador_ativo)),
        file_name="analise_msb.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with c2:
    todas_as_folhas = {}
    for nome in OPCOES_SEPARADOR:
        todas_as_folhas.update(_sheets_do_separador(nome))
    st.download_button(
        "⬇️ Exportar Excel — todos os separadores",
        data=_excel_bytes(todas_as_folhas),
        file_name="analise_msb_completa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
