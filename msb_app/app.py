"""
Ponto de entrada da aplicação.

Antes de qualquer coisa, exige login (ver `_ecra_login`): enquanto a
sessão não estiver autenticada, só aparece o ecrã de login — sem barra
lateral, sem páginas, sem nada da app. Depois do login, corre a app
normal, agrupada por fase com `st.navigation`.

Dois métodos de login:

- Password fixa (`utils/auth.py`).
- Código de acesso partilhado (`utils/codes.py`): aleatório, único, não
  guardado, válido 4 horas a contar da 1.ª utilização. As sessões abertas
  com código são terminadas assim que passam as 4 horas.

Quem entra com a password vê ainda a página "Acessos" (grupo
"Administração"), para gerar códigos.
"""
import time
from pathlib import Path

import streamlit as st

from utils.auth import validar_password
from utils.codes import expira_em, validar_codigo

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

ss = st.session_state
ss.setdefault("auth_ok", False)
ss.setdefault("auth_method", None)      # "password" | "codigo"
ss.setdefault("auth_expira_em", None)   # epoch (só para "codigo")
ss.setdefault("auth_code", None)
ss.setdefault("auth_msg", None)


def _limpar_sessao() -> None:
    for chave in ("auth_ok", "auth_method", "auth_expira_em", "auth_code"):
        ss[chave] = False if chave == "auth_ok" else None


def _conceder(metodo: str, code: str | None = None) -> None:
    ss.auth_ok = True
    ss.auth_method = metodo
    ss.auth_code = code
    ss.auth_expira_em = expira_em(code) if metodo == "codigo" else None
    ss.auth_msg = None
    st.rerun()


def _ecra_login() -> None:
    st.set_page_config(
        page_title="Acesso — Análise Integrada MSB",
        page_icon="🔒",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    # Ecrã de login "limpo": esconder barra lateral e cabeçalho da app.
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display: none;}
            [data-testid="stHeader"] {background: transparent;}
            [data-testid="stMainMenu"] {visibility: hidden;}
            .block-container {max-width: 30rem; padding-top: 4rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    logo = ASSETS_DIR / "logo.png"
    if logo.exists():
        col = st.columns([1, 2, 1])[1]
        col.image(str(logo), width="stretch")

    st.title("Iniciar sessão")
    st.caption("Acesso restrito. Introduza a password ou um código de acesso.")

    if ss.auth_msg:
        st.warning(ss.auth_msg)
        ss.auth_msg = None

    with st.form("login", border=True):
        metodo = st.segmented_control(
            "Método de acesso",
            options=["Password", "Código de acesso"],
            default="Password",
            label_visibility="collapsed",
            width="stretch",
        )
        valor = st.text_input(
            "Password ou código",
            type="password",
            label_visibility="collapsed",
            placeholder="Password ou código de acesso",
        )
        entrar = st.form_submit_button("Entrar", type="primary", width="stretch")

    if entrar:
        if (metodo or "Password") == "Password":
            if validar_password(valor):
                _conceder("password")
            else:
                st.error("Password incorreta.")
        else:
            if validar_codigo(valor):
                _conceder("codigo", code=valor)
            else:
                st.error("Código de acesso inválido ou expirado.")


# --- Porta de entrada -------------------------------------------------------

# Sessão por código que já passou das 4 horas: termina já, volta ao login.
if (
    ss.auth_ok
    and ss.auth_method == "codigo"
    and ss.auth_expira_em is not None
    and time.time() >= ss.auth_expira_em
):
    _limpar_sessao()
    ss.auth_msg = "A sessão do código de acesso expirou (4 horas). Inicie sessão novamente."

if not ss.auth_ok:
    _ecra_login()
    st.stop()

# --- App autenticada ------------------------------------------------------

pagina_home = st.Page("pages/0_Home.py", title="Home", icon="🏠", default=True)
pagina_importar = st.Page("pages/1_Importar_Ficheiros.py", title="Importar Ficheiros", icon="📥")
pagina_keys = st.Page("pages/2_Gerador_Keys.py", title="Gerador Keys", icon="🔑")
pagina_construir = st.Page("pages/3_Construir_Maintenance.py", title="Construir Maintenance", icon="🗄️")
pagina_dashboard = st.Page("pages/4_Dashboard_Analises.py", title="Dashboard Análises", icon="📊")

pagina_check_importar = st.Page("pages/5_Check_Importar.py", title="Importar & Gerar Check", icon="🧩")
pagina_check_dashboard = st.Page("pages/6_Check_Dashboard.py", title="Check Dashboard", icon="📋")

pagina_kinto_importar = st.Page("pages/7_Kinto_Importar.py", title="Kinto Importar", icon="🗓️")
pagina_kinto_dashboard = st.Page("pages/8_Kinto_Dashboard.py", title="Kinto Dashboard", icon="📅")

grupos = {
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

# A página de geração de códigos só existe para quem entrou com a password.
if ss.auth_method == "password":
    grupos["Administração"] = [
        st.Page("pages/9_Acessos.py", title="Acessos", icon="🔑"),
    ]

pg = st.navigation(grupos)

with st.sidebar:
    st.divider()
    if ss.auth_method == "codigo" and ss.auth_expira_em is not None:
        restante = max(0, int(ss.auth_expira_em - time.time()))
        st.caption(f"Acesso por código · termina em {restante // 3600}h{(restante % 3600) // 60:02d}m")
    else:
        st.caption("Sessão iniciada com password")
    if st.button("Terminar sessão", width="stretch"):
        _limpar_sessao()
        st.rerun()

pg.run()
