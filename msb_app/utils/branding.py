"""Branding — mostra o logo FleetData no canto superior esquerdo da app."""
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def set_logo() -> None:
    """Coloca o logo no topo da barra lateral (canto superior esquerdo)."""
    if LOGO_PATH.exists():
        st.logo(str(LOGO_PATH), size="large")
