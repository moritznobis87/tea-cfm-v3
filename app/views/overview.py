"""
Portfolioseite: aggregierte Kennzahlen, Portfolio-Analytik
(Rendite-Risiko-Landkarte, Ranking, Vergleichstabelle), Projektkarten mit
Cashflow-Sparkline und darunter das Dashboard des ausgewaehlten Projekts.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.config import STATE_SELECTED_PROJECT
from app.formatting import fmt_eur, fmt_kwp, fmt_number, fmt_pct
from app.theme import Colors, badge
from app.views.project_detail import render_project_dashboard
from engine import AnlagenTyp
from engine.io_yaml import load_project_yaml


def _sparkline_svg(werte: list[float], breite: int = 220, hoehe: int = 40) -> str:
    """Inline-SVG-Sparkline des kumulierten Equity-Cashflows: Linie in Ink,
    Nulllinie gepunktet, Flaeche ueber null dezent bernstein gefuellt."""
    if len(werte) < 2:
        return ""
    minimum, maximum = min(werte), max(werte)
    spannweite = (maximum - minimum) or 1.0

    def punkt(i: int, v: float) -> tuple[float, float]:
        x = i / (len(werte) - 1) * (breite - 4) + 2
        y = hoehe - 3 - (v - minimum) / spannweite * (hoehe - 6)
        return x, y

    punkte = [punkt(i, v) for i, v in enumerate(werte)]
    pfad = " ".join(f"{x:.1f},{y:.1f}" for x, y in punkte)
    y_null = hoehe - 3 - (0 - minimum) / spannweite * (hoehe - 6)
    y_null = max(3.0, min(hoehe - 3.0, y_null))
    flaeche = (
        f"M {punkte[0][0]:.1f},{y_null:.1f} L {pfad.replace(' ', ' L ')} "
        f"L {punkte[-1][0]:.1f},{y_null:.1f} Z"
    )
    return (
        f'<svg class="card-spark" width="100%" height="{hoehe}" '
        f'viewBox="0 0 {breite} {hoehe}" preserveAspectRatio="none" '
        f'role="img" aria-label="Kumulierter Cashflow">'
        f'<path d="{flaeche}" fill="rgba(232,162,60,0.22)" stroke="none"/>'
        f'<line x1="2" y1="{y_null:.1f}" x2="{breite - 2}" y2="{y_null:.1f}" '
        f'stroke="{Colors.LINE}" stroke-dasharray="3,3" stroke-width="1"/>'
        f'<polyline points="{pfad}" fill="none" stroke="{Colors.INK}" '
        f'stroke-width="1.8" vector-effect="non-scaling-stroke"/>'
        f"</svg>"
    )


def render_overview() -> None:
    projects = services.list_project_files()
    if not projects:
        st.info("Noch keine Projekte angelegt. Starten Sie mit „Neues Projekt“.")
        return

    global_assumptions = services.get_global_assumptions()

    # Alle Projekte einmal bewerten (gecacht auf Datei-mtimes, siehe
    # services) - Grundlage fuer Portfolio-KPIs, Analytik und Karten.
    zeilen = []
    for pid, path in projects.items():
        project = load_project_yaml(path)
        result = services.get_valuation(pid)
        zeilen.append(
            {
                "id": pid,
                "projekt": project,
                "kpis": result.kpis,
                "kum_cf": result.cashflow.data["cf_kumuliert_eur"].tolist(),
            }
        )

    # --- Portfolio-KPIs ------------------------------------------------------
    gesamt_kwp = sum(z["projekt"].nennleistung_kwp for z in zeilen)
    gesamt_capex = sum(z["kpis"].capex_total_eur for z in zeilen)
    gesamt_ek = sum(z["kpis"].eigenkapital_eur for z in zeilen)
    irr_werte = [z["kpis"].equity_irr for z in zeilen if z["kpis"].equity_irr is not None]
    mittlere_irr = sum(irr_werte) / len(irr_werte) if irr_werte else None

    render_kpi_row(
        [
            ("Projekte", f"{len(zeilen)}"),
            ("Portfolio-Leistung", f"{fmt_number(gesamt_kwp / 1000, 1)} MWp"),
            ("Investitionsvolumen gesamt", fmt_eur(gesamt_capex)),
            ("Eigenkapital gesamt", fmt_eur(gesamt_ek)),
            ("Ø EK-Rendite", fmt_pct(mittlere_irr)),
        ],
        group="portfolio",
    )

    # --- Portfolio-Analytik ---------------------------------------------------
    selected = st.session_state.get(STATE_SELECTED_PROJECT)
    analytik = pd.DataFrame(
        [
            {
                "id": z["id"],
                "name": z["projekt"].name,
                "typ": "Agri-PV"
                if z["projekt"].anlagentyp == AnlagenTyp.AGRI_PV
                else "Konventionell",
                "kwp": z["projekt"].nennleistung_kwp,
                "irr_pct": (z["kpis"].equity_irr or 0) * 100,
                "invest_eur_kwp": (
                    z["kpis"].capex_total_eur / z["projekt"].nennleistung_kwp
                    if z["projekt"].nennleistung_kwp
                    else 0
                ),
            }
            for z in zeilen
        ]
    )

    tab_karte, tab_ranking, tab_tabelle = st.tabs(
        ["🗺️ Rendite-Risiko-Landkarte", "🏆 Ranking", "📋 Vergleichstabelle"]
    )
    with tab_karte:
        st.caption(
            "Spezifisches Invest gegen EK-Rendite; Blasengröße = "
            "Anlagenleistung. Oben links steht das effiziente Portfolio: "
            "hohe Rendite bei niedrigem spezifischem Invest."
        )
        st.plotly_chart(
            charts.portfolio_bubble_chart(analytik, selected), width="stretch"
        )
    with tab_ranking:
        st.plotly_chart(
            charts.portfolio_ranking_chart(analytik, selected), width="stretch"
        )
    with tab_tabelle:
        vergleich = pd.DataFrame(
            [
                {
                    "Projekt": z["projekt"].name,
                    "Typ": "Agri-PV"
                    if z["projekt"].anlagentyp == AnlagenTyp.AGRI_PV
                    else "Konventionell",
                    "Leistung (kWp)": round(z["projekt"].nennleistung_kwp),
                    "EK-Rendite (%)": round(z["kpis"].equity_irr * 100, 2)
                    if z["kpis"].equity_irr is not None
                    else None,
                    "NPV bei 8 % (€)": round(z["kpis"].npv_eur),
                    "Invest (€)": round(z["kpis"].capex_total_eur),
                    "Invest (€/kWp)": round(
                        z["kpis"].capex_total_eur / z["projekt"].nennleistung_kwp
                    )
                    if z["projekt"].nennleistung_kwp
                    else None,
                    "Min. DSCR (x)": round(z["kpis"].dscr_min, 2)
                    if z["kpis"].dscr_min is not None
                    else None,
                    "Payback (Jahr)": z["kpis"].payback_jahre,
                }
                for z in zeilen
            ]
        )
        st.dataframe(
            vergleich.sort_values("EK-Rendite (%)", ascending=False),
            width="stretch",
            hide_index=True,
        )

    # --- Projektkarten ------------------------------------------------------
    st.subheader("Projekte")
    cols = st.columns(min(len(zeilen), 4))
    for i, z in enumerate(zeilen):
        project = z["projekt"]
        kpis = z["kpis"]
        ist_agri = project.anlagentyp == AnlagenTyp.AGRI_PV
        typ_badge = badge("Agri-PV", "agri") if ist_agri else badge("Konventionell", "konv")
        selected_cls = " selected" if z["id"] == selected else ""
        with cols[i % len(cols)]:
            st.markdown(
                f"""<div class="project-card{selected_cls}">
                <span class="card-title">{html.escape(project.name)}</span> {typ_badge}<br/>
                <span class="card-sub">{fmt_kwp(project.nennleistung_kwp)} · IBN {project.inbetriebnahme_jahr}</span><br/>
                <span class="card-kpi">{fmt_pct(kpis.equity_irr)}</span>
                <span class="card-kpi-label"> EK-Rendite</span><br/>
                <span class="card-sub">EK {fmt_eur(kpis.eigenkapital_eur)} · Payback {"Jahr " + fmt_number(kpis.payback_jahre) if kpis.payback_jahre is not None else "n/a"}</span>
                {_sparkline_svg(z["kum_cf"])}
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Öffnen", key=f"open_{z['id']}", width="stretch"):
                st.session_state[STATE_SELECTED_PROJECT] = z["id"]
                st.rerun()

    if not selected or selected not in projects:
        return

    st.divider()
    project = load_project_yaml(projects[selected])
    render_project_dashboard(project, global_assumptions, projects[selected])
