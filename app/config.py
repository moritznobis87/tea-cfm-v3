"""
Zentrale Konfiguration der Anwendung: Pfade und app-weite Konstanten.

Alle anderen App-Module beziehen Pfade ausschliesslich von hier - dadurch
gibt es genau eine Stelle, an der z.B. ein Wechsel des Datenverzeichnisses
(etwa fuer Tests oder ein Deployment mit persistentem Volume) erfolgt.
"""

from __future__ import annotations

from pathlib import Path

#: Wurzelverzeichnis des Repositories (Ordner, der streamlit_app.py enthaelt).
ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
GLOBAL_ASSUMPTIONS_PATH = DATA_DIR / "global_assumptions.yaml"

ASSETS_DIR = ROOT_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "TRI_Logo_Pure_RGB_Red.png"
#: Beschnittene, quadratische Logovariante fuer den Browser-Tab.
FAVICON_PATH = ASSETS_DIR / "favicon.png"

APP_TITLE = "TEA PV-Projektbewertung"

#: Deutschsprachige Monatsnamen (Index 0 = Januar).
MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
MONATE_KURZ = [
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
]

#: Session-State-Schluessel (zentral, um Tippfehler-Bugs auszuschliessen).
STATE_SELECTED_PROJECT = "selected_project"
STATE_DELETE_CANDIDATE = "delete_candidate"
