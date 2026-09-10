"""
Análise Integrada de MSB — página "Home".

Mostra o estado do pipeline de dados (quais ficheiros já foram importados,
quantas linhas têm) e explica os passos seguintes, tanto da Fase 1
(manutenção/frota) como da Fase 2 (Check Service).
"""
import streamlit as st

from utils.io_utils import pipeline_status, last_modified
from utils.branding import set_logo

st.set_page_config(
    page_title="Análise Integrada MSB - TESTE ",
    page_icon="🚗",
    layout="wide",
)
set_logo()

CUSTOM_CSS = """
<style>
    .block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
    .msb-step {
        border: 1px solid #2b2f38;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.00));
    }
    .msb-step h4 {margin: 0 0 0.25rem 0;}
    .msb-ok {color: #3fb950; font-weight: 600;}
    .msb-pending {color: #d29922; font-weight: 600;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.title("🚗 Análise Integrada de MSB - TESTE ")
st.caption(
    "Importar, tratar, ligar e analisar os ficheiros de perfis de manutenção, frota "
    "e check service, num só lugar."
)

st.markdown("---")

status = pipeline_status()

FILE_LABELS_FASE1 = {
    "maintenance_profiles": "maintenance_profiles.csv (importado)",
    "maintenance_profiles_final": "maintenance_profiles_FINAL.csv (keys + qualidade)",
    "cars": "cars.csv (frota / carid's)",
    "matriculas": "Matriculas.csv (matrículas + VIN)",
    "kinto_prioridade": "kinto_prioridade.csv (prioridade por marca)",
    "maintenance": "maintenance.csv (base final para análise)",
}

FILE_LABELS_FASE2 = {
    "part_description": "part_description.csv (peças possíveis)",
    "service_parts": "service_parts.csv (peças no serviço)",
    "task_parts": "task_parts.csv (peças na tarefa)",
    "check_analise": "check_analise.csv (merge final)",
}

FILE_LABELS_FASE3 = {
    "kinto_maintenance_historico": "kinto_maintenance_historico.csv (todos os meses)",
    "kinto_vehicle_historico": "kinto_vehicle_historico.csv (todos os meses)",
}


def _render_status(labels: dict[str, str]):
    for key, label in labels.items():
        info = status[key]
        ts = last_modified(key)
        ts_txt = f" · atualizado em {ts:%d/%m/%Y %H:%M}" if ts else ""
        if info.get("existe"):
            if "erro" in info:
                st.markdown(f"⚠️ **{label}** — erro ao ler: `{info['erro']}`")
            else:
                st.markdown(
                    f"<span class='msb-ok'>●</span> **{label}** — "
                    f"{info['linhas']:,} linhas, {info['colunas']} colunas{ts_txt}".replace(",", " "),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"<span class='msb-pending'>○</span> **{label}** — ainda não importado",
                unsafe_allow_html=True,
            )


col1, col2 = st.columns([1.1, 1])

with col1:
    st.subheader("Estado da base de dados — Fase 1")
    _render_status(FILE_LABELS_FASE1)
    st.markdown("")
    st.subheader("Estado da base de dados — Fase 2 (Check Service)")
    _render_status(FILE_LABELS_FASE2)
    st.markdown("")
    st.subheader("Estado da base de dados — Fase 3 (Kinto Analisis)")
    _render_status(FILE_LABELS_FASE3)

with col2:
    st.subheader("Fluxo de trabalho — Fase 1")
    st.markdown(
        """
<div class="msb-step">
<h4>1. Importar Ficheiros</h4>
Carregar <code>maintenance_profiles.csv</code>, <code>cars.csv</code>,
<code>Matriculas.csv</code> e <code>kinto_prioridade.csv</code>. Ficam
guardados na pasta de dados da aplicação.
</div>
<div class="msb-step">
<h4>2. Gerador de Keys</h4>
Gera as <code>quality1_key</code>…<code>quality4_key</code> e a previsão de
qualidade (<code>predictedQuality</code>), atualizando o
<code>maintenance_profiles_FINAL</code>.
</div>
<div class="msb-step">
<h4>3. Construir Maintenance.csv</h4>
Liga o FINAL ao <code>cars.csv</code>, às matrículas e à prioridade
kinto, calculando contagens de carid's, matrículas, e a coluna
<code>kinto</code>.
</div>
<div class="msb-step">
<h4>4. Dashboard &amp; Análises</h4>
Filtros, gráficos (barras, linhas, circular), tabela e exportação da
análise.
</div>
""",
        unsafe_allow_html=True,
    )

    st.subheader("Fluxo de trabalho — Fase 2 (Check Service)")
    st.markdown(
        """
<div class="msb-step">
<h4>1. Importar &amp; Gerar Check</h4>
Carregar <code>part_description.csv</code>, <code>service_parts.csv</code> e
<code>task_parts.csv</code>, e gerar o <code>check_analise.csv</code> (merge
por msbId + partId, filtrado a country == "PO").
</div>
<div class="msb-step">
<h4>2. Check Dashboard</h4>
Separador de diferenças (check_price / check_partnumber / check_qtd) e
separador de peças recolhidas (check_collected), com exportação Excel.
</div>
""",
        unsafe_allow_html=True,
    )

    st.subheader("Fluxo de trabalho — Fase 3 (Kinto Analisis)")
    st.markdown(
        """
<div class="msb-step">
<h4>1. Importar Ficheiros</h4>
Carregar os ficheiros mensais <code>kinto_Maintenance_Profile</code> e
<code>kinto_Vehicle_All</code> — mês/ano detetados automaticamente pelo
nome do ficheiro (corrigíveis antes de confirmar). Cada mês fica guardado
num histórico; reimportar um mês substitui-o, sem duplicar.
</div>
<div class="msb-step">
<h4>2. Kinto Dashboard</h4>
Liga o histórico às bases da Fase 1 (<code>maintenance.csv</code> e
<code>cars.csv</code>). Filtros por marca/qualidade/ano/mês, evolução
mensal em modo Acumulado ou Diferença face ao mês anterior, e exportação
Excel.
</div>
""",
        unsafe_allow_html=True,
    )

st.markdown("---")
st.info(
    "Use o menu à esquerda (barra lateral) para navegar entre as páginas do pipeline.",
    icon="👈",
)
