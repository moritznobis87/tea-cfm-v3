"""
Visuelles Fundament der App: Design-Tokens, CSS und ein zentrales
Plotly-Template.

Designsprache "Sonnenband": Trianel-Rot (Interaktion/Auswahl), Solar-
Bernstein (Erzeugung/Erloese) und Tannengruen-Ink (Finanzen/Struktur)
bilden eine feste Dreiklang-Palette; das schmale Verlaufband unter der
Kopfzeile und an den KPI-Kacheln ist das wiedererkennbare Signaturelement.
Display-Schrift: Space Grotesk (Ueberschriften, KPI-Werte, tabellarische
Ziffern), Flusstext: Inter.

Prinzip: Jede Farbe, jeder Abstand und jedes Diagramm bezieht seine
Gestaltung aus DIESEM Modul. Views und Komponenten enthalten keine
Hex-Codes.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------------------
# Design-Tokens
# ---------------------------------------------------------------------------


class Colors:
    """Sonnenband-Palette: Rot = Interaktion, Bernstein = Erzeugung/Erloes,
    Tannengruen = Finanzen/Struktur."""

    BRAND = "#BE172B"          # Trianel-Rot - Akzent, Auswahl, Primary-Buttons
    SOLAR = "#E8A23C"          # Solar-Bernstein - Erzeugung, Markterloese
    SOLAR_DEEP = "#C77F1A"     # dunklere Bernstein-Stufe (Linien, Text auf hell)
    INK = "#143530"            # Tiefes Tannengruen - Ueberschriften, Linien
    INK_SOFT = "#2E5A52"       # hellere Ink-Stufe (Sekundaerserien)
    MUTED = "#5B6B66"          # Sekundaertext
    LINE = "#E1E8E5"           # Rahmen, Trennlinien
    WASH = "#F6F9F8"           # Kartenhintergrund
    PAPER = "#FFFFFF"

    POSITIVE = "#2E7D32"       # Zufluesse, "im gruenen Bereich"
    NEGATIVE = "#C0392B"       # Abfluesse, Unterdeckung
    NEUTRAL = "#8AA6A0"        # Sekundaere Serien (z.B. Tilgung, Varianten)

    #: Signatur-Verlauf (Kopfzeile, KPI-Kacheln): Rot -> Bernstein -> Gruen.
    SONNENBAND = f"linear-gradient(90deg, {BRAND} 0%, #E8A23C 45%, #2E7D32 100%)"

    #: Gestufte Warmtoene fuer gestapelte Kostenpositionen.
    OPEX_SCALE = [
        "#C0392B", "#E67E22", "#D68910", "#B9770E", "#A04000",
        "#873600", "#6E2C00", "#943126",
    ]

    #: Serienfarben fuer Szenario-/Mehrlinienvergleiche.
    SERIES = ["#143530", "#BE172B", "#E8A23C", "#2E7D32", "#8AA6A0", "#6C3483"]

    #: Divergierende Skala fuer die IRR-Heatmap (rot -> sand -> gruen).
    HEAT_SCALE = [
        [0.0, "#C0392B"], [0.35, "#E8A23C"], [0.55, "#F4E7C6"],
        [0.75, "#8FBF9F"], [1.0, "#2E7D32"],
    ]


# ---------------------------------------------------------------------------
# Plotly-Template (einmal registrieren, ueberall nutzen)
# ---------------------------------------------------------------------------

_TEMPLATE_NAME = "tea"


def _register_plotly_template() -> None:
    if _TEMPLATE_NAME in pio.templates:
        return
    pio.templates[_TEMPLATE_NAME] = go.layout.Template(
        layout=go.Layout(
            font=dict(family="Inter, sans-serif", color=Colors.INK, size=13),
            title_font=dict(family="Space Grotesk, Inter, sans-serif", size=15),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            # Deutsche Zahlendarstellung in Achsen und Hovern:
            # 1. Zeichen = Dezimaltrenner, 2. Zeichen = Tausendertrenner.
            separators=",.",
            colorway=Colors.SERIES,
            margin=dict(t=28, b=28, l=8, r=8),
            bargap=0.25,
            hoverlabel=dict(
                bgcolor=Colors.PAPER,
                bordercolor=Colors.LINE,
                font=dict(family="Inter, sans-serif", color=Colors.INK, size=13),
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(
                gridcolor=Colors.LINE, zerolinecolor=Colors.LINE,
                linecolor=Colors.LINE, ticks="outside", tickcolor=Colors.LINE,
            ),
            yaxis=dict(
                gridcolor=Colors.LINE, zerolinecolor=Colors.LINE,
                linecolor=Colors.LINE,
            ),
        )
    )
    pio.templates.default = f"plotly_white+{_TEMPLATE_NAME}"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap');

    .block-container {{ padding-top: 1.4rem; max-width: 1280px; }}

    /* --- Typografie ------------------------------------------------------ */
    h1, h2, h3 {{
        font-family: "Space Grotesk", "Inter", sans-serif !important;
        color: {Colors.INK};
        letter-spacing: -0.015em;
    }}

    /* --- Kopfzeile / Hero ------------------------------------------------ */
    .app-hero-title {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-size: 2.05rem;
        font-weight: 700;
        color: {Colors.INK};
        letter-spacing: -0.02em;
        line-height: 1.1;
        margin: 0;
    }}
    .app-hero-sub {{
        color: {Colors.MUTED};
        font-size: 0.95rem;
        margin-top: 2px;
    }}
    .app-hero-sub b {{ color: {Colors.SOLAR_DEEP}; font-weight: 600; }}
    .app-header-rule {{
        height: 4px;
        background: {Colors.SONNENBAND};
        border: none; border-radius: 2px;
        margin: 0.5rem 0 1.2rem 0;
    }}

    /* --- KPI-Kacheln ------------------------------------------------------ */
    div[data-testid="stMetric"] {{
        background: {Colors.WASH};
        border: 1px solid {Colors.LINE};
        border-radius: 12px;
        padding: 14px 18px 10px 18px;
    }}
    div[data-testid="stMetric"] label {{ color: {Colors.MUTED}; }}

    .kpi-row {{
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: 1fr;
        gap: 12px;
        margin: 0.35rem 0 0.9rem 0;
    }}
    .kpi-card {{
        position: relative;
        background: linear-gradient(180deg, {Colors.PAPER} 0%, {Colors.WASH} 100%);
        border: 1px solid {Colors.LINE};
        border-radius: 12px;
        padding: 14px 16px 12px 16px;
        min-width: 0;               /* erlaubt Schrumpfen in der Grid-Zelle */
        overflow: hidden;
        transition: transform 140ms ease, box-shadow 140ms ease;
    }}
    .kpi-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: {Colors.SONNENBAND};
        opacity: 0.9;
    }}
    .kpi-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(20, 53, 48, 0.10);
    }}
    .kpi-card .kpi-label {{
        color: {Colors.MUTED};
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .kpi-card .kpi-value {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-variant-numeric: tabular-nums;
        color: {Colors.INK};
        font-weight: 700;
        font-size: 2rem;            /* Maximum; JS passt gruppenweise an */
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
    }}
    /* 1px-iframes (Schriftgroessen-Skript, siehe app/components/kpi.py)
       samt Container aus dem Layoutfluss nehmen, damit kein Leerraum
       entsteht. Skripte in display:none-iframes laufen weiterhin. */
    div[data-testid="stElementContainer"]:has(iframe[height="0"]),
    div[data-testid="stElementContainer"]:has(iframe[height="1"]) {{
        display: none;
    }}

    /* --- Projektkarten ---------------------------------------------------- */
    .project-card {{
        position: relative;
        border: 1px solid {Colors.LINE};
        border-radius: 12px;
        padding: 14px 16px 10px 16px;
        margin-bottom: 8px;
        background: {Colors.PAPER};
        overflow: hidden;
        transition: transform 140ms ease, box-shadow 140ms ease,
                    border-color 140ms ease;
    }}
    .project-card:hover {{
        transform: translateY(-2px);
        border-color: {Colors.NEUTRAL};
        box-shadow: 0 6px 18px rgba(20, 53, 48, 0.10);
    }}
    .project-card.selected {{
        border-color: {Colors.BRAND};
        box-shadow: 0 0 0 1px {Colors.BRAND};
    }}
    .project-card .card-title {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-weight: 600; color: {Colors.INK}; font-size: 1.02rem;
    }}
    .project-card .card-sub {{ color: {Colors.MUTED}; font-size: 0.84em; }}
    .project-card .card-kpi {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-variant-numeric: tabular-nums;
        font-size: 1.55em; font-weight: 700; color: {Colors.INK};
    }}
    .project-card .card-kpi-label {{ color: {Colors.MUTED}; font-size: 0.84em; }}
    .project-card .card-spark {{ margin-top: 4px; }}

    /* --- Badges ------------------------------------------------------------ */
    .badge {{
        display: inline-block;
        padding: 1px 9px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        vertical-align: middle;
    }}
    .badge-agri {{ background: #E7F2EA; color: {Colors.POSITIVE}; }}
    .badge-konv {{ background: #EEF1F0; color: {Colors.MUTED}; }}
    .badge-warn {{ background: #FBEEE6; color: {Colors.SOLAR_DEEP}; }}

    /* --- Tabs (Pill-Stil) --------------------------------------------------- */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 6px;
        border-bottom: none;
        flex-wrap: wrap;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-weight: 500;
        background: {Colors.WASH};
        border: 1px solid {Colors.LINE};
        border-radius: 999px;
        padding: 4px 16px;
        color: {Colors.MUTED};
    }}
    .stTabs [aria-selected="true"] {{
        background: {Colors.INK};
        border-color: {Colors.INK};
        color: #FFFFFF !important;
    }}
    .stTabs [aria-selected="true"] p {{ color: #FFFFFF !important; }}
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {{ display: none; }}

    /* --- Sidebar ------------------------------------------------------------ */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {Colors.WASH} 0%, {Colors.PAPER} 60%);
        border-right: 1px solid {Colors.LINE};
    }}
    section[data-testid="stSidebar"] .stRadio label {{ font-weight: 500; }}

    /* --- Buttons -------------------------------------------------------------- */
    .stButton > button, .stDownloadButton > button {{
        border-radius: 10px;
    }}

    /* --- Abschnittstitel mit Bernstein-Marker ---------------------------------- */
    .section-title {{
        font-family: "Space Grotesk", "Inter", sans-serif;
        font-weight: 600;
        color: {Colors.INK};
        font-size: 1.05rem;
        margin: 0.4rem 0 0.2rem 0;
    }}
    .section-title::before {{
        content: "";
        display: inline-block;
        width: 8px; height: 8px;
        border-radius: 2px;
        background: {Colors.SOLAR};
        margin-right: 8px;
        transform: rotate(45deg) translateY(-1px);
    }}

    @media (prefers-reduced-motion: reduce) {{
        .kpi-card, .project-card {{ transition: none; }}
        .kpi-card:hover, .project-card:hover {{ transform: none; }}
    }}
</style>
"""


def apply_theme() -> None:
    """Registriert das Plotly-Template und injiziert das App-CSS.

    Muss einmal pro Rerun frueh aufgerufen werden (macht der Entry-Point).
    """
    _register_plotly_template()
    st.markdown(_CSS, unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Abschnittsueberschrift mit Bernstein-Marker (Signaturelement)."""
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "konv") -> str:
    """HTML-Schnipsel fuer ein Badge ('agri', 'konv' oder 'warn')."""
    return f'<span class="badge badge-{kind}">{text}</span>'
