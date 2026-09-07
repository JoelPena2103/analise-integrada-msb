"""
Ponto de entrada da aplicação.

Usa st.navigation para agrupar as páginas por fase — isto dá um separador
visual nativo do Streamlit entre a Fase 1 (Análise Integrada MSB) e a
Fase 2 (Check Service), e torna trivial acrescentar mais fases no futuro
(basta acrescentar mais um grupo ao dicionário abaixo).
"""
import streamlit as st

pagina_home = st.Page("pages/0_Home.py", title="Home", icon="🏠", default=True)
pagina_importar = st.Page("pages/1_Importar_Ficheiros.py", title="Importar Ficheiros", icon="📥")
pagina_keys = st.Page("pages/2_Gerador_Keys.py", title="Gerador Keys", icon="🔑")
pagina_construir = st.Page("pages/3_Construir_Maintenance.py", title="Construir Maintenance", icon="🗄️")
pagina_dashboard = st.Page("pages/4_Dashboard_Analises.py", title="Dashboard Análises", icon="📊")

pagina_check_importar = st.Page("pages/5_Check_Importar.py", title="Importar & Gerar Check", icon="🧩")
pagina_check_dashboard = st.Page("pages/6_Check_Dashboard.py", title="Check Dashboard", icon="📋")

pagina_kinto_importar = st.Page("pages/7_Kinto_Importar.py", title="Kinto Importar", icon="🗓️")
pagina_kinto_dashboard = st.Page("pages/8_Kinto_Dashboard.py", title="Kinto Dashboard", icon="📅")

pg = st.navigation(
    {
        "Fase 1 — Manutenção": [
            pagina_home,
            pagina_importar,
            pagina_keys,
            pagina_construir,
            pagina_dashboard,
        ],
        "Fase 2 — Check Service": [
            pagina_check_importar,
            pagina_check_dashboard,
        ],
        "Fase 3 — Kinto Analisis": [
            pagina_kinto_importar,
            pagina_kinto_dashboard,
        ],
    }
)
pg.run()
