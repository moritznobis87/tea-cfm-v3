"""
Seite "Ausschreibung": Analyse der historischen EAG-Marktpraemien-
ausschreibungen (PV, Oesterreich), Prognose der Gebotsverteilung der
naechsten Runde (Price-Taker-Modell, engine/auktion.py) und Ableitung
eines empfohlenen Gebotswerts fuer eine gewuenschte Zuschlags-
wahrscheinlichkeit - mit Uebergabe an das Cashflow-Modell.
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.config import STATE_SELECTED_PROJECT
from app.formatting import fmt_ct_kwh, fmt_number, fmt_pct
from app.theme import section_title

#: Session-Schluessel, ueber den das Projektformular den empfohlenen
#: Gebotswert als Vorbelegung uebernimmt (manuell ueberschreibbar).
STATE_EMPFOHLENES_GEBOT = "empfohlenes_gebot_ct"


def render_auktion() -> None:
    runden, df = services.get_ausschreibungen()
    modell = services.get_auktions_modell()
    letzte = modell.letzte_runde

    st.markdown("### EAG-Ausschreibungssimulation (Photovoltaik)")
    st.caption(
        "Price-Taker-Modell: Geschätzt wird die Gebotsverteilung der "
        "übrigen Marktteilnehmer der nächsten Marktprämienausschreibung; "
        "das eigene Gebot beeinflusst den Grenzzuschlag nicht und wird "
        "anhand der Verteilung gewählt. Mechanismus: Pay-as-Bid mit "
        "Gebotspreisreihung (EAG §§ 18 ff., OeMAG)."
    )

    # --- Historie ------------------------------------------------------------
    section_title("Historische Ausschreibungen (2022–2026)")
    st.plotly_chart(charts.auktion_historie_chart(df), width="stretch")
    st.caption(
        "Runden bis 04/2025 waren unterzeichnet (Höchstzuschlag = "
        "Preisobergrenze, Restmengen blieben unbezuschlagt); seit 07/2025 "
        "herrscht Wettbewerb: Der Höchstzuschlag löst sich von der "
        "Obergrenze, die Zuschlagswerte sinken und verdichten sich – exakt "
        "das in der Auktionsliteratur beschriebene Pay-as-Bid-Muster."
    )
    with st.expander("Datentabelle und Modellkalibrierung"):
        anzeige = df.copy()
        anzeige["bezuschlagt_pct"] = (
            anzeige["bezuschlagt_mw"] / anzeige["ausgeschrieben_mw"] * 100
        ).round(0)
        st.dataframe(anzeige, width="stretch", hide_index=True)
        st.markdown(
            "**Kalibrierung je Runde** (Beta auf [0, Obergrenze]; Bedingungen: "
            "mengengewichteter Ø-Zuschlag und Minimum als 2 %-Quantil; bei "
            "überzeichneten Runden ist die Wettbewerbsquote r = Gebotsmenge / "
            "ausgeschriebene Menge **latent** und wird aus dem Abstand "
            "Grenzzuschlag ↔ Obergrenze rückgeschätzt, da die OeMAG das "
            "Gebotsvolumen nicht veröffentlicht):"
        )
        import pandas as pd

        st.dataframe(pd.DataFrame([
            {
                "Runde": f.ausschreibung.datum,
                "r (Gebote/Ausschr.)": round(f.wettbewerbsquote, 2),
                "r latent": "ja" if f.wettbewerbsquote_latent else "nein",
                "Lage µ/Obergrenze": round(f.mu_rel, 3),
                "Konzentration κ": round(f.kappa, 1),
            }
            for f in sorted(modell.fits, key=lambda f: f.ausschreibung.datum)
        ]), width="stretch", hide_index=True)

    with st.expander("Modellwahl und Validierung (Leave-one-out)"):
        vergleich, loo = services.get_auktions_validierung()
        st.markdown(
            "**Familienvergleich** – da nur Aggregate (Min/Ø/Max) je Runde "
            "veröffentlicht werden, scheiden KDE/GMM auf Einzelgeboten aus; "
            "verglichen werden beschränkte parametrische Familien. Die "
            "**Beta-Verteilung** reproduziert Ø und Minimum gemeinsam rund "
            "viermal genauer als die trunkierte Normalverteilung "
            "(fit_rmse) und bildet als einzige beide Regime automatisch ab: "
            "β < 1 (Masse an der Obergrenze) in unterzeichneten, β > 1 "
            "(Dichte ≈ 0 an der Obergrenze) in überzeichneten Runden."
        )
        st.dataframe(vergleich, width="stretch", hide_index=True)
        st.markdown(
            "**Leave-one-out über die Wettbewerbsrunden** – Prognose aus den "
            "jeweils übrigen Runden bei gegebener Wettbewerbsquote, "
            "verglichen mit dem bisherigen Ansatz (Fortschreibung des "
            "letzten Höchstzuschlags als fester Wert):"
        )
        st.dataframe(loo, width="stretch", hide_index=True)
        st.caption(
            "Der bisherige Ansatz liefert nur einen Punktwert ohne "
            "Verteilung – eine Zuschlagswahrscheinlichkeit ist damit "
            "prinzipiell nicht ableitbar. Das Modell liefert zusätzlich "
            "Minimum und Mittelwert sowie die volle prädiktive Verteilung "
            "des Grenzzuschlags inklusive Unsicherheit (Bootstrap der "
            "Regressionsresiduen, Lognormal-Unsicherheit der "
            "Wettbewerbsquote)."
        )

    st.divider()

    # --- Prognose naechste Runde ---------------------------------------------
    section_title("Prognose der nächsten Ausschreibung")
    col1, col2, col3 = st.columns(3)
    cap = col1.number_input(
        "Preisobergrenze (ct/kWh)", 1.0, 15.0,
        float(letzte.ausschreibung.preisobergrenze_ct), 0.01,
        help="Per Verordnung fixiert; 2026/2027: 7,77 ct/kWh.",
    )
    r_erwartet = col2.number_input(
        "Erwartete Wettbewerbsquote r (Gebote / ausgeschriebene Menge)",
        0.2, 5.0, float(round(letzte.wettbewerbsquote, 2)), 0.05,
        help="r > 1 = überzeichnet. Vorbelegung: latent geschätzte Quote "
             "der letzten Runde. Die EAG-Abwicklungsstelle meldet "
             "weiterhin 'enormes Interesse' (07/2026).",
    )
    sigma_r = col3.slider(
        "Unsicherheit der Wettbewerbsquote (σ von ln r)", 0.05, 0.6, 0.25, 0.05,
        help="Streuung der Lognormal-Ziehung von r über die "
             "Prognosewelten – historisch schwankt r deutlich zwischen "
             "den Runden.",
    )
    prognose = services.get_gebots_prognose(cap, r_erwartet, sigma_r)

    ziel_prob = st.select_slider(
        "Gewünschte Zuschlagswahrscheinlichkeit",
        options=[0.50, 0.60, 0.70, 0.80, 0.90, 0.95], value=0.80,
        format_func=lambda v: f"{v * 100:.0f} %",
    )
    empfohlen = prognose.empfohlenes_gebot(ziel_prob)

    render_kpi_row(
        [
            ("Empfohlenes Gebot", fmt_ct_kwh(empfohlen)),
            ("Zuschlagswahrscheinlichkeit", fmt_pct(ziel_prob, 0)),
            ("Erwarteter Grenzzuschlag (Median)",
             fmt_ct_kwh(float(np.median(prognose.pm_sample)))),
            ("Ø Gebot (Prognose)", fmt_ct_kwh(prognose.gebot_mittel_ct)),
            ("P(unterzeichnet)",
             fmt_pct(float(np.mean(prognose.pm_sample >= cap - 1e-9)), 0)),
        ],
        group="auktion",
    )

    col_links, col_rechts = st.columns(2)
    with col_links:
        section_title("Geschätzte Gebotsverteilung")
        st.plotly_chart(
            charts.gebotsdichte_chart(prognose, empfohlen), width="stretch"
        )
        st.caption(
            "Dichte gemittelt über die Prognosewelten; Markierungen: "
            "Preisobergrenze, Erwartungswert, Median, 5 %/95 %-Quantile "
            "und das empfohlene Gebot."
        )
    with col_rechts:
        section_title("Gebot ↔ Zuschlagswahrscheinlichkeit")
        st.plotly_chart(
            charts.zuschlagskurve_chart(prognose, ziel_prob, empfohlen),
            width="stretch",
        )
        st.caption(
            "P(Zuschlag | Gebot) = P(Grenzzuschlag > Gebot) über alle "
            "Prognosewelten. Je höher die gewünschte Sicherheit, desto "
            "niedriger das Gebot."
        )

    uebersicht = " · ".join(
        f"{int(z * 100)} % → {fmt_ct_kwh(prognose.empfohlenes_gebot(z))}"
        for z in (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
    )
    st.info(f"Empfohlene Gebote nach Zielwahrscheinlichkeit: {uebersicht}")

    st.divider()

    # --- Uebergabe an das Cashflow-Modell -------------------------------------
    section_title("Übergabe an das Cashflow-Modell")
    st.session_state[STATE_EMPFOHLENES_GEBOT] = float(round(empfohlen, 2))
    st.caption(
        "Der empfohlene Wert wird neuen Projekten automatisch als "
        "EAG-Zuschlagswert vorbelegt (im Formular jederzeit manuell "
        "überschreibbar) und kann hier direkt in ein bestehendes Projekt "
        "übernommen werden. Im Monte-Carlo-Tab des Projekts lässt sich "
        "zusätzlich die volle Gebotsverteilung als Zufallsquelle "
        "aktivieren."
    )
    projekte = services.list_project_files()
    if projekte:
        namen = {pid: services.get_project(pid).name for pid in projekte}
        col_a, col_b = st.columns([2, 1])
        ziel_projekt = col_a.selectbox(
            "Projekt", list(projekte), format_func=namen.get,
            key="auktion_ziel_projekt",
        )
        if col_b.button(
            f"Gebot {fmt_number(empfohlen, 2)} ct übernehmen",
            width="stretch", type="primary",
        ):
            projekt = services.get_project(ziel_projekt)
            projekt.eag_zuschlagswert_ct_kwh = float(round(empfohlen, 2))
            services.save_project(projekt, projekte[ziel_projekt])
            st.session_state[STATE_SELECTED_PROJECT] = ziel_projekt
            st.success(
                f"EAG-Zuschlagswert von „{projekt.name}“ auf "
                f"{fmt_ct_kwh(empfohlen)} gesetzt – Neuberechnung erfolgt "
                f"automatisch (Portfolio-Seite)."
            )
