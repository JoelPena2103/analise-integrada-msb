"""
Administração — geração de códigos de acesso partilhados.

Esta página só é adicionada à navegação para quem inicia sessão com a
password fixa (ver `app.py`). A verificação abaixo é uma segunda linha de
defesa, caso se navegue diretamente para o URL da página.

Cada código é aleatório, único, válido 4 horas a contar da 1.ª
utilização, e existe apenas na memória do servidor — nunca é gravado.
"""
import time

import streamlit as st

from utils.branding import set_logo
from utils.codes import DURACAO_SEGUNDOS, codigos_ativos, gerar_codigo

st.set_page_config(page_title="Acessos — MSB", page_icon="🔑", layout="wide")
set_logo()

if st.session_state.get("auth_method") != "password":
    st.error("Esta página só está disponível para quem inicia sessão com a password.")
    st.stop()

st.title("🔑 Códigos de acesso")
st.caption(
    f"Gere um código para dar a quem precisa de entrar sem a password. Cada "
    f"código é único, dura {DURACAO_SEGUNDOS // 3600} horas a partir da primeira "
    "utilização e não fica guardado em lado nenhum — se o servidor reiniciar, "
    "deixa de ser válido."
)

if st.button("Gerar novo código", type="primary", icon=":material/vpn_key:"):
    st.session_state.ultimo_codigo = gerar_codigo()

if st.session_state.get("ultimo_codigo"):
    st.success("Código gerado. Copie agora e partilhe — não volta a aparecer em destaque.")
    st.code(st.session_state.ultimo_codigo, language=None)

st.divider()
st.subheader("Códigos ativos")

ativos = codigos_ativos()
if not ativos:
    st.info("Nenhum código ativo neste momento.")
else:
    agora = time.time()
    linhas = []
    for a in ativos:
        if a["expira_em"] is None:
            termina = "— (ainda não usado)"
        else:
            restante = max(0, int(a["expira_em"] - agora))
            termina = f"{restante // 3600}h{(restante % 3600) // 60:02d}m"
        linhas.append({"Código": a["code"], "Estado": a["estado"], "Termina em": termina})
    st.dataframe(linhas, width="stretch", hide_index=True)
    st.caption("Lista mantida apenas em memória. Atualize a página para ver o tempo restante.")
