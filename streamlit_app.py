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
from app.views.auktion import render_auktion  # noqa: E402
from app.views.new_project import render_new_project  # noqa: E402
from app.views.overview import render_overview  # noqa: E402
from texte import SESSION_KEY, SPRACHEN, sprachauswahl_label, txt  # noqa: E402

# --- Kopfzeile (Hero) --------------------------------------------------------
col_logo, col_title, col_sprache = st.columns(
    [1, 8, 1.4], vertical_alignment="center"
)
if LOGO_PATH.exists():
    col_logo.image(str(LOGO_PATH), width=84)
col_title.markdown(
    f"""<div>
    <p class="app-hero-title">{txt("oberflaeche.app_titel")}</p>
    <p class="app-hero-sub">{txt("oberflaeche.app_untertitel")}</p>
    </div>""",
    unsafe_allow_html=True,
)

# Sprachauswahl (Flagge + Name); die Auswahl greift ueber
# texte.aktive_sprache() ab dem naechsten Rerun ueberall in der App -
# eigener Widget-Key, damit kein Konflikt mit dem Speicher-Schluessel
# (SESSION_KEY) entsteht, den wir hier bewusst selbst befuellen.
_sprachcodes = list(SPRACHEN)
_aktuell = st.session_state.get(SESSION_KEY, _sprachcodes[0])
_gewaehlt = col_sprache.selectbox(
    "Sprache / Language",
    _sprachcodes,
    index=_sprachcodes.index(_aktuell) if _aktuell in _sprachcodes else 0,
    format_func=sprachauswahl_label,
    key="sprachauswahl_dropdown",
    label_visibility="collapsed",
)
if _gewaehlt != _aktuell:
    st.session_state[SESSION_KEY] = _gewaehlt
    st.rerun()

st.markdown('<div class="app-header-rule"></div>', unsafe_allow_html=True)

# --- Navigation ----------------------------------------------------------------
# Stabile interne Codes als Radio-Werte (nicht die uebersetzten Labels):
# so bleibt die Auswahl beim Sprachwechsel gueltig und Streamlit muss den
# gespeicherten Widget-Zustand nicht verwerfen. Explizite Zuordnung zu den
# Sprachdatei-Schluesseln (keine Namenskonvention noetig/riskant).
_NAV_SCHLUESSEL = {
    "portfolio": "oberflaeche.nav_portfolio",
    "neu": "oberflaeche.nav_neues_projekt",
    "auktion": "oberflaeche.nav_ausschreibung",
    "annahmen": "oberflaeche.nav_globale_annahmen",
}
nav = st.sidebar.radio(
    txt("oberflaeche.nav_titel"),
    list(_NAV_SCHLUESSEL),
    format_func=lambda code: txt(_NAV_SCHLUESSEL[code]),
    key="nav",
)
render_import_export()

if nav == "portfolio":
    render_overview()
elif nav == "neu":
    render_new_project()
elif nav == "auktion":
    render_auktion()
else:
    render_assumptions()
