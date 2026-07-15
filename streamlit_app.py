"""
TEA PV-Projektbewertung - Einstiegspunkt.

Bewusst duenn gehalten: Seitenkonfiguration, Theme, Kopfzeile und
Navigation. Die eigentlichen Seiten leben in app/views/, wieder-
verwendbare Bausteine in app/components/, Datenzugriff und Caching in
app/services.py, die Fachlogik in engine/.
"""

from __future__ import annotations

import streamlit as st

# Markenfarbe und Schrift zur Laufzeit fixieren: .streamlit/config.toml
# greift nur, wenn die App aus dem Projektordner gestartet wird. Damit das
# Trianel-Rot unabhaengig vom Startverzeichnis gilt, werden die Theme-
# Optionen hier zusaetzlich gesetzt (vor set_page_config, damit sie in der
# ersten an den Browser gesendeten Session ankommen).
from streamlit import config as _st_config  # noqa: E402

from app.config import APP_TITLE, FAVICON_PATH, LOGO_PATH
from app.theme import Colors, apply_theme

_INTER = (
    "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&display=swap, sans-serif"
)
for _option, _wert in [
    ("theme.primaryColor", Colors.BRAND),
    ("theme.font", _INTER),
    ("theme.headingFont", _INTER),
]:
    if _st_config.get_option(_option) != _wert:
        _st_config.set_option(_option, _wert)

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else "☀️",
)
apply_theme()

# Imports der Views erst NACH set_page_config - Streamlit verlangt, dass
# set_page_config der allererste Streamlit-Befehl des Skripts ist, und die
# Views fuehren beim Import bereits Streamlit-Code aus (Caching-Dekoratoren).
from app.components.sidebar import render_import_export  # noqa: E402
from app.views.assumptions import render_assumptions  # noqa: E402
from app.views.new_project import render_new_project  # noqa: E402
from app.views.overview import render_overview  # noqa: E402

# --- Kopfzeile (Hero) --------------------------------------------------------
col_logo, col_title = st.columns([1, 9], vertical_alignment="center")
if LOGO_PATH.exists():
    col_logo.image(str(LOGO_PATH), width=84)
col_title.markdown(
    f"""<div>
    <p class="app-hero-title">{APP_TITLE}</p>
    <p class="app-hero-sub">Wirtschaftlichkeit · Sensitivität · Risiko —
    EAG-Marktprämienmodell, Österreich</p>
    </div>""",
    unsafe_allow_html=True,
)
st.markdown('<div class="app-header-rule"></div>', unsafe_allow_html=True)

# --- Navigation ----------------------------------------------------------------
_NAV_PORTFOLIO = "Portfolio"
_NAV_NEU = "Neues Projekt"
_NAV_ANNAHMEN = "Globale Annahmen"
nav = st.sidebar.radio(
    "Navigation",
    [_NAV_PORTFOLIO, _NAV_NEU, _NAV_ANNAHMEN],
    key="nav",
)
render_import_export()

if nav == _NAV_PORTFOLIO:
    render_overview()
elif nav == _NAV_NEU:
    render_new_project()
else:
    render_assumptions()
