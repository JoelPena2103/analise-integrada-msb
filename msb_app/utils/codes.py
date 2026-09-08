"""
Registo de códigos de acesso partilhados.

Regras (conforme pedido):

- Cada código é gerado aleatoriamente e é único.
- Nunca é gravado — vive apenas na memória do processo do servidor
  (o dicionário `_CODES` abaixo). Se o servidor reiniciar, todos os
  códigos por usar / em uso deixam de existir.
- Tem um limite de utilização de 4 horas, mas o relógio só arranca no
  momento em que o código é usado pela primeira vez. Enquanto não for
  usado, fica válido indefinidamente (até o servidor reiniciar).

É intencional que este estado seja partilhado por todas as sessões do
servidor (ao contrário de `st.session_state`, que é por sessão/separador):
quem gera o código, na página "Acessos", está numa sessão diferente de
quem o vai introduzir no ecrã de login. O modelo assume um único processo
de servidor — que é como a aplicação é lançada (`streamlit run app.py`).
"""
from __future__ import annotations

import secrets
import string
import threading
import time

# 4 horas, em segundos. O relógio só começa a contar no 1.º uso.
DURACAO_SEGUNDOS = 4 * 60 * 60

_COMPRIMENTO = 8
# Alfabeto sem caracteres ambíguos (sem O/0, I/1) para ser fácil de ditar.
_ALFABETO = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "O0I1")

# code -> {"gerado_em": float, "usado_em": float | None}
_CODES: dict[str, dict] = {}
_LOCK = threading.Lock()


def _normalizar(code: str) -> str:
    return "".join((code or "").split()).replace("-", "").upper()


def gerar_codigo() -> str:
    """Gera um código aleatório único e regista-o como 'por usar'."""
    with _LOCK:
        while True:
            code = "".join(secrets.choice(_ALFABETO) for _ in range(_COMPRIMENTO))
            if code not in _CODES:
                break
        _CODES[code] = {"gerado_em": time.time(), "usado_em": None}
        return code


def validar_codigo(code: str) -> bool:
    """
    Valida um código no login.

    - Código inexistente  -> False.
    - Primeira utilização -> arranca o relógio das 4h e devolve True.
    - Utilização seguinte, ainda dentro das 4h -> True.
    - Depois das 4h -> remove o código e devolve False.
    """
    code = _normalizar(code)
    if not code:
        return False
    with _LOCK:
        info = _CODES.get(code)
        if info is None:
            return False
        agora = time.time()
        if info["usado_em"] is None:
            info["usado_em"] = agora
            return True
        if agora - info["usado_em"] < DURACAO_SEGUNDOS:
            return True
        _CODES.pop(code, None)
        return False


def expira_em(code: str) -> float | None:
    """
    Timestamp epoch em que o código expira, ou None se ainda não foi
    usado (relógio parado) ou não existe.
    """
    info = _CODES.get(_normalizar(code))
    if not info or info["usado_em"] is None:
        return None
    return info["usado_em"] + DURACAO_SEGUNDOS


def codigos_ativos() -> list[dict]:
    """
    Fotografia dos códigos válidos, para a página de administração.
    Aproveita para limpar os que já expiraram.
    """
    agora = time.time()
    out: list[dict] = []
    with _LOCK:
        for code, info in list(_CODES.items()):
            usado_em = info["usado_em"]
            if usado_em is not None and agora - usado_em >= DURACAO_SEGUNDOS:
                _CODES.pop(code, None)
                continue
            out.append(
                {
                    "code": code,
                    "estado": "por usar" if usado_em is None else "em uso",
                    "expira_em": None if usado_em is None else usado_em + DURACAO_SEGUNDOS,
                }
            )
    return out
