"""
Autenticação por password fixa.

A password correta é lida de `.streamlit/secrets.toml` (secção [auth],
chave `password`). Se o ficheiro de secrets não existir ou não tiver a
chave, é usada a password por omissão abaixo — pensada para
desenvolvimento local. Em produção, defina sempre a password nos secrets.
"""
from __future__ import annotations

import hmac

import streamlit as st

# Usada apenas se não houver `[auth] password` em .streamlit/secrets.toml.
_PASSWORD_POR_OMISSAO = "fleetdata2026"


def _password_correta() -> str:
    try:
        return str(st.secrets["auth"]["password"])
    except Exception:
        return _PASSWORD_POR_OMISSAO


def validar_password(pwd: str) -> bool:
    """Compara `pwd` com a password fixa (comparação em tempo constante)."""
    return hmac.compare_digest(str(pwd or ""), _password_correta())
