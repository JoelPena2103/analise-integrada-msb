import io

import pandas as pd
import streamlit as st

from utils.io_utils import file_exists, load_csv
from utils.branding import set_logo
from utils.check_logic import tabela_diferencas, tabela_recolhidas_false

st.set_page_config(page_title="Check Dashboard — MSB", page_icon="📋", layout="wide")
set_logo()
st.title("📋 Check Dashboard")
st.caption("Diferenças entre service_parts e task_parts, e peças recolhidas vs. possíveis.")

if not file_exists("check_analise"):
    st.warning(
        "Ainda não existe `check_analise.csv`. Gere-o na página "
        "**🧩 Importar & Gerar Check** primeiro."
    )
    st.stop()

check = load_csv("check_analise")

# --- normalizar tipos numéricos que vieram como str (dtype=str na leitura) ---
for col in ("price_task", "price_service", "quantity_task", "quantity_service"):
    if col in check.columns:
        check[col] = pd.to_numeric(check[col], errors="coerce")

for col in ("check_price", "check_partnumber", "check_qtd", "check_collected"):
    if col in check.columns:
        check[col] = check[col].astype(str).str.strip().str.lower().map(
            {"true": True, "false": False}
        )

diferencas = tabela_diferencas(check)
recolhidas_false = tabela_recolhidas_false(check)

total_recolhido = None
if file_exists("task_parts"):
    try:
        task_parts_raw = load_csv("task_parts")
        if "country" in task_parts_raw.columns:
            total_recolhido = int(
                (task_parts_raw["country"].astype(str).str.strip().str.upper() == "PO").sum()
            )
        else:
            total_recolhido = len(task_parts_raw)
    except Exception:  # noqa: BLE001
        total_recolhido = None

# ---------------------------------------------------------------------------
# Navegação por separadores rastreável (para a exportação "separador atual")
# ---------------------------------------------------------------------------
OPCOES_SEPARADOR = ["🔍 Diferenças Service vs Task", "📦 Peças Recolhidas"]

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
    "Separador", OPCOES_SEPARADOR, horizontal=True, label_visibility="collapsed", key="check_separador_ativo"
)
st.markdown("---")

if separador_ativo == "🔍 Diferenças Service vs Task":
    st.caption(
        "Linhas incompletas (sem dados para comparar) foram eliminadas. Mostra apenas "
        "peças com alguma diferença entre service_parts e task_parts."
    )
    k1, k2, k3 = st.columns(3)
    k1.metric(
        "check_price = Falso",
        int((diferencas["check_price"] == False).sum()) if "check_price" in diferencas.columns else 0,  # noqa: E712
    )
    k2.metric(
        "check_partnumber = Falso",
        int((diferencas["check_partnumber"] == False).sum()) if "check_partnumber" in diferencas.columns else 0,  # noqa: E712
    )
    k3.metric(
        "check_qtd = Falso",
        int((diferencas["check_qtd"] == False).sum()) if "check_qtd" in diferencas.columns else 0,  # noqa: E712
    )

    st.markdown(f"##### Tabela de diferenças ({len(diferencas):,} linhas)".replace(",", " "))
    st.dataframe(diferencas, width='stretch', height=520)

else:
    st.caption(
        "Comparação entre as peças possíveis para recolha (part_description.csv) e as "
        "que foram realmente recolhidas (task_parts.csv)."
    )
    k1, k2 = st.columns(2)
    k1.metric("Total Recolhido (task_parts, país PO)", total_recolhido if total_recolhido is not None else "—")
    k2.metric(
        "check_collected = Falso",
        int((check["check_collected"] == False).sum()) if "check_collected" in check.columns else 0,  # noqa: E712
    )

    st.markdown(f"##### Peças com check_collected = Falso ({len(recolhidas_false):,} linhas)".replace(",", " "))
    st.caption("As linhas vazias/incompletas são mantidas aqui propositadamente.")
    st.dataframe(recolhidas_false, width='stretch', height=520)


def _sheets_do_separador(nome: str) -> dict[str, pd.DataFrame]:
    if nome == "🔍 Diferenças Service vs Task":
        return {"Diferencas_Service_Task": diferencas}
    return {"Pecas_Recolhidas_Falso": recolhidas_false}


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
        file_name="check_analise_separador.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with c2:
    todas_as_folhas = {}
    for nome in OPCOES_SEPARADOR:
        todas_as_folhas.update(_sheets_do_separador(nome))
    st.download_button(
        "⬇️ Exportar Excel — todos os separadores",
        data=_excel_bytes(todas_as_folhas),
        file_name="check_analise_completa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
