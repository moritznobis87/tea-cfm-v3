"""
Seite "Ausschreibung": Analyse der historischen EAG-Marktpraemien-
ausschreibungen (PV, Oesterreich), Prognose der Gebotsverteilung der
naechsten Runde (Price-Taker-Modell, engine/auktion.py) und Ableitung
eines empfohlenen Gebotswerts fuer eine gewuenschte Zuschlags-
wahrscheinlichkeit - mit Uebergabe an das Cashflow-Modell.
"""

from __future__ import annotations

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
    section_title("Geschätzte Gebotsverteilungen der historischen Runden")
    st.caption(
        "Da die OeMAG weder Einzelgebote noch Gebotsvolumina "
        "veröffentlicht, werden die Verteilungsparameter je Runde aus den "
        "Aggregaten (Ø, Minimum) geschätzt. Deutlich sichtbar: In den "
        "unterzeichneten Runden (gestrichelt) klebt die Masse an der "
        "Preisobergrenze; mit dem Wettbewerb ab 07/2025 wandern die "
        "Verteilungen nach links und verdichten sich."
    )
    tab_dichte, tab_cdf = st.tabs(["Dichte", "Verteilungsfunktion"])
    with tab_dichte:
        st.plotly_chart(
            charts.auktion_historische_verteilungen_chart(modell, "dichte"),
            width="stretch",
        )
    with tab_cdf:
        st.plotly_chart(
            charts.auktion_historische_verteilungen_chart(
                modell, "verteilungsfunktion"
            ),
            width="stretch",
        )

    with st.expander("Datentabelle und Modellkalibrierung"):
        anzeige = df.copy()
        anzeige["bezuschlagt_pct"] = (
            anzeige["bezuschlagt_mw"] / anzeige["ausgeschrieben_mw"] * 100
        ).round(0)
        st.dataframe(anzeige, width="stretch", hide_index=True)
        st.markdown(
            "**Kalibrierung je Runde** (gespiegelte Inverse Gamma auf "
            "[0, Obergrenze]; Bedingungen: "
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

    with st.expander("Modellwahl und Validierung (Backtest)"):
        vergleich, backtest = services.get_auktions_validierung()
        st.markdown(
            "**Familienvergleich** – da nur Aggregate (Min/Ø/Max) je Runde "
            "veröffentlicht werden, scheiden KDE/GMM auf Einzelgeboten aus; "
            "verglichen werden auf [0, Obergrenze] beschränkte "
            "parametrische Familien. Gewählt ist die **an der Y-Achse "
            "gespiegelte, an die Obergrenze verschobene Inverse-Gamma-"
            "Verteilung**: Sie passt auf die (prognoserelevanten) "
            "Wettbewerbsrunden am besten (Fit-RMSE 0,15 vs. 0,21 der "
            "Beta) und hat strukturell exakt die erwartete Form – Dichte "
            "an der Obergrenze null, steiler rechter Abfall, langsam "
            "auslaufender linker Rand. Die Beta bleibt als Referenz: Sie "
            "beschreibt die alten, unterzeichneten Runden mit Masse an "
            "der Obergrenze besser (β < 1), die die Inverse Gamma "
            "prinzipbedingt nicht abbilden kann; die trunkierte "
            "Normalverteilung scheitert als symmetrische Basis an "
            "linkem Ausläufer plus Konzentration (Fit-RMSE ~4× höher)."
        )
        st.dataframe(vergleich, width="stretch", hide_index=True)
        st.markdown(
            "**Rollierender Ein-Schritt-Backtest** – für jede "
            "Wettbewerbsrunde wurde das Modell nur auf den davor "
            "liegenden Runden kalibriert (Verankerung an der jeweils "
            "letzten Runde, Random Walk) und der Grenzzuschlag "
            "prognostiziert; Vergleich mit der naiven Fortschreibung "
            "des letzten Höchstzuschlags (bisheriger Ansatz):"
        )
        st.dataframe(backtest, width="stretch", hide_index=True)
        st.caption(
            "RMSE Grenzzuschlag über alle vier Wettbewerbsrunden: Modell "
            "0,60 vs. naiv 0,69 ct/kWh; im stabilen Regime ab 2026: 0,23 "
            "vs. 0,36 ct/kWh. Darüber hinaus liefert nur das Modell die "
            "volle prädiktive Verteilung des Grenzzuschlags – und damit "
            "die Zuschlagswahrscheinlichkeit je Gebot, die ein fester "
            "Punktwert prinzipiell nicht hergibt. Die schwächeren Zeilen "
            "2025 markieren den Regimewechsel (Eintritt des Wettbewerbs), "
            "den kein rein historisch kalibriertes Verfahren antizipieren "
            "konnte."
        )

    st.divider()

    # --- Prognose naechste Runde ---------------------------------------------
    section_title("Zuschlagswert bestimmen")
    modus_label = st.radio(
        "Grundlage des Zuschlagswerts",
        ["Letzte Ausschreibung (gesetzt)", "Prognosemodell (nächste Ausschreibung)"],
        horizontal=True,
        help="Letzte Ausschreibung: Die Verteilung der letzten Runde gilt "
             "unverändert; die Risikoneigung wählt das Quantil der "
             "Zuschlagswerte. Prognosemodell: Momentum-Prognose der "
             "nächsten Runde – Grenzzuschlag und Ø-Zuschlag werden aus "
             "letzter Änderung und Beschleunigung fortgeschrieben, daraus "
             "wird die neue Verteilung gebaut.",
    )
    modus = "letzte" if modus_label.startswith("Letzte") else "prognose"

    if modus == "prognose":
        col1, col3 = st.columns(2)
        cap = col1.number_input(
            "Preisobergrenze (ct/kWh)", 1.0, 15.0,
            float(letzte.ausschreibung.preisobergrenze_ct), 0.01,
            help="Per Verordnung fixiert; 2026/2027: 7,77 ct/kWh.",
        )
        sigma_pm = col3.slider(
            "Unsicherheit des Grenzzuschlags (± ct/kWh)", 0.15, 0.8, 0.55, 0.05,
            help="Streuung um die Punktprognose; Vorbelegung entspricht "
                 "der Streuung der historischen Rundenänderungen. An der "
                 "Preisobergrenze trunkiert.",
        )
        prognose = services.get_gebots_prognose("prognose", cap, sigma_pm)
        st.caption(
            f"Implizierte Wettbewerbsquote der gebauten Verteilung: "
            f"r = {prognose.wettbewerbsquote:,.2f}".replace(".", ",")
            + " (Anteil bezuschlagter Gebote = 1/r; ergibt sich aus "
            "Prognose-Grenzzuschlag, Ø-Prognose und Minimum-Anker)."
        )
        with st.expander("Prognosemethodik (Momentum-Formel)"):
            wett = sorted(
                (f.ausschreibung for f in modell.fits
                 if not f.ausschreibung.unterzeichnet),
                key=lambda a: a.datum,
            )
            maxes = [a.zuschlag_max_ct for a in wett]
            mittels = [a.zuschlag_mittel_ct for a in wett]
            st.markdown(
                "Fortschreibung je Stützstelle (Grenzzuschlag und "
                "Ø-Zuschlag) aus letzter Änderung und Beschleunigung – "
                "AR-artig:\n\n"
                "$x_{t+1} = x_t + \\Delta_t \\cdot (\\Delta_t - "
                "\\Delta_{t-1})$ mit $\\Delta_t = x_t - x_{t-1}$\n\n"
                f"Grenzzuschlag: {' → '.join(f'{v:,.2f}'.replace('.', ',') for v in maxes)} "
                f"⇒ **{fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct)}** · "
                f"Ø-Zuschlag: {' → '.join(f'{v:,.2f}'.replace('.', ',') for v in mittels)} "
                f"⇒ **{fmt_ct_kwh(prognose.mittel_prognose_ct)}**\n\n"
                "Aus beiden Punktprognosen wird die neue Verteilung "
                "gebaut (E[b | b ≤ max] = Ø und F(max) = 1/r); die "
                "Unsicherheit des Grenzzuschlags folgt der Streuung der "
                "historischen Rundenänderungen."
            )
    else:
        prognose = services.get_gebots_prognose("letzte")
        st.caption(
            f"Die letzte Ausschreibung ({letzte.ausschreibung.datum.strftime('%d.%m.%Y')}) "
            f"gilt als gesetzt: Grenzzuschlag {fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct)}, "
            f"Ø {fmt_ct_kwh(letzte.ausschreibung.zuschlag_mittel_ct)}, "
            f"Minimum {fmt_ct_kwh(letzte.ausschreibung.zuschlag_min_ct)}. Die "
            f"Risikoneigung wählt das Quantil der Zuschlagswert-Verteilung "
            f"dieser Runde."
        )

    ziel_prob = st.select_slider(
        "Risikoneigung: gewünschte Wahrscheinlichkeit",
        options=[0.50, 0.60, 0.70, 0.80, 0.90, 0.95], value=0.80,
        format_func=lambda v: f"{v * 100:.0f} %",
        help="Prognosemodell: Zuschlagswahrscheinlichkeit P(Grenzzuschlag "
             "> Gebot). Letzte Ausschreibung: Anteil der Zuschlagswerte "
             "der letzten Runde oberhalb des gewählten Werts – hohe "
             "Wahrscheinlichkeit = konservativ niedriger Wert.",
    )
    empfohlen = prognose.empfohlenes_gebot(ziel_prob)

    # Harte Ueberschreibung: der manuell gesetzte Wert gewinnt immer.
    col_o1, col_o2 = st.columns([1, 2])
    ueberschreiben = col_o1.toggle("Zuschlagswert manuell überschreiben",
                                   value=False, key="auktion_override")
    if ueberschreiben:
        effektiver_wert = col_o2.number_input(
            "Zuschlagswert (ct/kWh)", 0.1, 15.0, float(round(empfohlen, 2)),
            0.01, key="auktion_override_wert",
        )
    else:
        effektiver_wert = float(round(empfohlen, 2))

    render_kpi_row(
        [
            ("Zuschlagswert" + (" (manuell)" if ueberschreiben else " (empfohlen)"),
             fmt_ct_kwh(effektiver_wert)),
            ("Wahrscheinlichkeit",
             fmt_pct(prognose.zuschlagswahrscheinlichkeit(effektiver_wert), 0)),
            ("Grenzzuschlag " + ("(Prognose)" if modus == "prognose" else "(Ist, letzte Runde)"),
             fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct)),
            ("Ø Zuschlagswert " + ("(Prognose)" if modus == "prognose" else "(Ist)"),
             fmt_ct_kwh(prognose.gebot_mittel_ct if modus == "prognose"
                        else letzte.ausschreibung.zuschlag_mittel_ct)),
            ("Letzter Grenzzuschlag (Ist)",
             fmt_ct_kwh(letzte.ausschreibung.zuschlag_max_ct)),
        ],
        group="auktion",
    )

    col_links, col_rechts = st.columns(2)
    with col_links:
        section_title("Verteilung der Zuschlagswerte")
        st.plotly_chart(
            charts.gebotsdichte_chart(prognose, effektiver_wert), width="stretch"
        )
        st.caption(
            "Gefüllt: Dichte der Zuschlagswerte (am Grenzzuschlag "
            "abgeschnitten) – Peak knapp unter dem Grenzzuschlag, steiler "
            "Abfall nach rechts, langsamer linker Auslauf. Gestrichelt: "
            "alle Gebote inkl. nicht bezuschlagter."
            + (" Band: P10–P90 des prognostizierten Grenzzuschlags."
               if modus == "prognose" else "")
        )
    with col_rechts:
        section_title("Wert ↔ Wahrscheinlichkeit")
        st.plotly_chart(
            charts.zuschlagskurve_chart(prognose,
                prognose.zuschlagswahrscheinlichkeit(effektiver_wert),
                effektiver_wert),
            width="stretch",
        )
        st.caption(
            "Prognosemodell: P(Zuschlag | Gebot) = P(Grenzzuschlag > "
            "Gebot) über die Prognoseunsicherheit."
            if modus == "prognose" else
            "Quantilslage in der gesetzten letzten Runde: Anteil der "
            "Zuschlagswerte oberhalb des gewählten Werts."
        )

    uebersicht = " · ".join(
        f"{int(z * 100)} % → {fmt_ct_kwh(prognose.empfohlenes_gebot(z))}"
        for z in (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
    )
    st.info(f"Werte nach Risikoneigung: {uebersicht}")

    st.divider()

    # --- Uebergabe an das Cashflow-Modell -------------------------------------
    section_title("Übergabe an das Cashflow-Modell")
    st.session_state[STATE_EMPFOHLENES_GEBOT] = float(round(effektiver_wert, 2))
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
            f"Zuschlagswert {fmt_number(effektiver_wert, 2)} ct übernehmen",
            width="stretch", type="primary",
        ):
            projekt = services.get_project(ziel_projekt)
            projekt.eag_zuschlagswert_ct_kwh = float(round(effektiver_wert, 2))
            services.save_project(projekt, projekte[ziel_projekt])
            st.session_state[STATE_SELECTED_PROJECT] = ziel_projekt
            st.success(
                f"EAG-Zuschlagswert von „{projekt.name}“ auf "
                f"{fmt_ct_kwh(effektiver_wert)} gesetzt – Neuberechnung "
                f"erfolgt automatisch (Portfolio-Seite)."
            )
