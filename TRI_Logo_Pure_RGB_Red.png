"""
Projekt-Dashboard: KPI-Leisten, sieben Analyse-Tabs (Cashflow, Erlöse,
Finanzierung, Sensitivität inkl. Tornado/Heatmap/Gebotsassistent,
Monte Carlo, Szenarien, Annahmen) sowie Bearbeiten, Duplizieren, Löschen
und Excel-Export eines Einzelprojekts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.components.project_form import render_project_form
from app.config import MONATE_KURZ, STATE_DELETE_CANDIDATE, STATE_SELECTED_PROJECT
from app.formatting import fmt_ct_kwh, fmt_dscr, fmt_eur, fmt_kwp, fmt_number, fmt_pct
from app.theme import section_title
from engine import (
    AnlagenTyp,
    GlobalAssumptions,
    NegativeStundenModus,
    NegativeStundenRegel,
    PVProject,
)
from engine.analytics import HEATMAP_ACHSEN, calculate_lcoe
from engine.kpis import npv_at

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _typ_label(project: PVProject) -> str:
    return "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"


def render_project_dashboard(
    project: PVProject, global_assumptions: GlobalAssumptions, file_path: Path
) -> None:
    result = services.get_valuation(file_path.stem)
    if result is None:
        st.error("Projekt konnte nicht geladen werden.")
        return
    df = result.cashflow.data
    kpis = result.kpis

    # --- Kopfzeile ---------------------------------------------------------
    st.markdown(f"### {project.name}")
    st.caption(
        f"{_typ_label(project)} · {fmt_kwp(project.nennleistung_kwp)} · "
        f"Inbetriebnahme {MONATE_KURZ[project.inbetriebnahme_monat - 1]} "
        f"{project.inbetriebnahme_jahr} · effektiver EAG-Zuschlag "
        f"{fmt_ct_kwh(project.eag_zuschlagswert_effektiv_ct_kwh)} · "
        f"Szenario {result.effective_assumptions.marktpreisszenario_name}"
    )

    # --- Aktionen ----------------------------------------------------------
    with st.expander("Projekt bearbeiten"):
        updated = render_project_form(existing=project, form_key=f"edit_{project.id}")
        if updated is not None:
            # Bewusst file_path statt project.id verwenden: id und Dateiname
            # koennen (z.B. durch manuelle YAML-Bearbeitung) auseinander-
            # laufen - wir wollen immer die tatsaechlich geoeffnete Datei
            # ueberschreiben, nicht versehentlich eine zweite erzeugen.
            services.save_project(updated, file_path)
            st.session_state.pop(f"pdf_bericht_{file_path.stem}", None)
            st.success("Projekt aktualisiert.")
            st.rerun()

    _, col_dup, col_del, col_export, col_pdf = st.columns([1.6, 1, 1, 1.8, 1.8])
    with col_dup:
        if st.button("Duplizieren", key=f"dup_{project.id}", width="stretch"):
            kopie = services.duplicate_project(file_path.stem)
            if kopie is not None:
                st.session_state[STATE_SELECTED_PROJECT] = kopie.id
                st.rerun()
    with col_del:
        if st.button("Löschen", key=f"del_{project.id}", width="stretch"):
            st.session_state[STATE_DELETE_CANDIDATE] = file_path.stem
    with col_export:
        st.download_button(
            "Cashflow als Excel",
            data=services.cashflow_to_excel(result),
            file_name=f"{services.slugify(project.name)}_cashflow.xlsx",
            mime=_XLSX_MIME,
            width="stretch",
        )
    with col_pdf:
        pdf_key = f"pdf_bericht_{file_path.stem}"
        if pdf_key not in st.session_state:
            if st.button("PDF-Bericht erstellen", key=f"pdf_btn_{project.id}",
                         width="stretch"):
                with st.spinner(
                    "Erstelle PDF-Bericht (inkl. Sensitivität und "
                    "Monte-Carlo-Simulation) …"
                ):
                    st.session_state[pdf_key] = services.build_project_report(
                        file_path.stem,
                        st.session_state.get("npv_diskontsatz_pct", 8.0) / 100,
                    )
                st.rerun()
        else:
            st.download_button(
                "PDF-Bericht herunterladen",
                data=st.session_state[pdf_key],
                file_name=f"{services.slugify(project.name)}_bericht.pdf",
                mime="application/pdf",
                width="stretch",
                key=f"pdf_dl_{project.id}",
            )

    # Loeschen nur nach expliziter Bestaetigung - das ist nicht rueckholbar.
    if st.session_state.get(STATE_DELETE_CANDIDATE) == file_path.stem:
        st.warning(f"Projekt „{project.name}“ endgültig löschen?")
        col_ja, col_nein, _ = st.columns([1, 1, 4])
        if col_ja.button("Ja, löschen", type="primary", key=f"del_ok_{project.id}"):
            services.delete_project(file_path.stem)
            st.session_state.pop(STATE_DELETE_CANDIDATE, None)
            st.session_state.pop(STATE_SELECTED_PROJECT, None)
            st.rerun()
        if col_nein.button("Abbrechen", key=f"del_no_{project.id}"):
            st.session_state.pop(STATE_DELETE_CANDIDATE, None)
            st.rerun()

    # --- KPI-Leisten ---------------------------------------------------------
    # NPV-Diskontsatz frei waehlbar (gilt fuer NPV-Kachel und LCOE). Der Wert
    # wird exakt per XNPV berechnet. Die Einstellung gilt app-weit
    # (Session-State), damit Projekte zum selben Satz verglichen werden.
    st.session_state.setdefault("npv_diskontsatz_pct", 8.0)
    col_rate, _ = st.columns([1.3, 5])
    npv_satz_pct = col_rate.number_input(
        "NPV-Diskontsatz (%)",
        min_value=0.0,
        max_value=10.0,
        step=0.25,
        key="npv_diskontsatz_pct",
        help="Diskontsatz für NPV-Kachel und LCOE (0–10 %). Der Wert wird "
             "exakt aus der Cashflow-Zeitreihe berechnet (XNPV), auch "
             "zwischen den Stützstellen der NPV-Kurve.",
    )
    npv_wert = npv_at(result.cashflow, npv_satz_pct / 100)

    lcoe = calculate_lcoe(df, npv_satz_pct / 100)
    render_kpi_row(
        [
            ("EK-Rendite (IRR)", fmt_pct(kpis.equity_irr)),
            (f"NPV bei {fmt_number(npv_satz_pct, 2)} %", fmt_eur(npv_wert)),
            ("Min. DSCR (Kreditlaufzeit)", fmt_dscr(kpis.dscr_min)),
            ("CAPEX", fmt_eur(kpis.capex_total_eur)),
            ("LCOE", fmt_ct_kwh(lcoe) if lcoe is not None else "n/a"),
        ],
        group="projekt",
    )

    if kpis.dscr_min is not None and kpis.dscr_min < 1.0:
        st.warning(
            f"Der minimale DSCR liegt bei {fmt_dscr(kpis.dscr_min)} und damit "
            f"unter 1,0x: Der operative Cashflow deckt den Schuldendienst in "
            f"mindestens einem Jahr der Kreditlaufzeit nicht vollständig. Mit den "
            f"aktuellen Annahmen müsste während der Fremdfinanzierungsphase "
            f"zusätzliches Eigenkapital nachgeschossen werden. Details siehe Tab "
            f"Finanzierung – meist hilft eine niedrigere Fremdkapitalquote oder "
            f"eine längere Kreditlaufzeit."
        )

    tab_cf, tab_erloese, tab_fin, tab_sens, tab_mc, tab_szen, tab_annahmen = st.tabs(
        [
            "Cashflow", "Erlöse", "Finanzierung", "Sensitivität",
            "Monte Carlo", "Szenarien", "Annahmen",
        ]
    )

    with tab_cf:
        _render_cashflow_tab(result, df)
    with tab_erloese:
        _render_revenue_tab(result, df)
    with tab_fin:
        _render_financing_tab(result, df, project)
    with tab_sens:
        _render_sensitivity_tab(result, project, file_path.stem)
    with tab_mc:
        _render_monte_carlo_tab(file_path.stem, npv_satz_pct / 100)
    with tab_szen:
        _render_scenario_tab(result, file_path.stem, npv_satz_pct / 100)
    with tab_annahmen:
        _render_assumptions_tab(result)


# ---------------------------------------------------------------------------
# Tab: Cashflow
# ---------------------------------------------------------------------------


def _render_cashflow_tab(result, df) -> None:
    section_title("Wertbrücke über die Gesamtlaufzeit")
    st.caption(
        "Von den Umsatzerlösen der gesamten Betriebsdauer über Kosten, "
        "Zinsen, Steuern und Finanzierung zum kumulierten Equity-Cashflow."
    )
    st.plotly_chart(charts.equity_waterfall_chart(df), width="stretch")

    section_title("Gesamt-Cashflow")
    st.caption(
        "Summe aus operativem, Investitions- und Finanzierungs-Cashflow je "
        "Jahr (Balken) sowie kumuliert über die Zeit (Linie, rechte Achse)."
    )
    st.plotly_chart(charts.total_cashflow_chart(df), width="stretch")

    section_title("Betriebskosten (nach Position)")
    st.caption(
        "Klicken Sie auf einzelne Positionen in der Legende, um sie "
        "ein-/auszublenden."
    )
    st.plotly_chart(
        charts.opex_stacked_chart(df, result.cashflow.opex_posten), width="stretch"
    )

    section_title("Operativer Cashflow (Umsatzerlöse − Betriebskosten)")
    st.caption(
        "Vereinfachte Betrachtung vor Zinsen und Steuer. Die für "
        "EK-Rendite/NPV massgebliche Cashflow-Definition (inkl. Zinsen und "
        "Steuer) finden Sie in der Tabelle unten."
    )
    st.plotly_chart(charts.operating_cashflow_chart(df), width="stretch")

    with st.expander("Detailtabelle (Erlöse, Betriebskosten, Zinsen, Steuer)"):
        detail_df = df[
            [
                "jahr", "marktwert_real_ct_kwh", "marktwert_nominal_ct_kwh",
                "verguetungssatz_ct_kwh", "erloes_eur", "opex_gesamt_eur",
                "gemeindeabgabe_eur", "direktvermarktungskosten_eur",
                "zinsen_eur", "tilgung_eur", "afa_eur",
                "steuerliches_ergebnis_vor_verlustvortrag_eur",
                "verlustvortrag_genutzt_eur", "verlustvortrag_bestand_eur",
                "steuerliches_ergebnis_eur", "steuer_eur",
            ]
        ].copy()
        for col in detail_df.columns:
            if col == "jahr":
                continue
            nachkommastellen = 3 if "ct_kwh" in col else 0
            detail_df[col] = detail_df[col].round(nachkommastellen)
        detail_df.columns = [
            "Jahr", "Marktwert real (ct/kWh)", "Marktwert nominal (ct/kWh)",
            "Vergütungssatz (ct/kWh)", "Erlöse (€)", "Betriebskosten gesamt (€)",
            "davon Gemeindeabgabe (€)", "davon Direktvermarktungskosten (€)",
            "Zinsen (€)", "Tilgung (€)", "AfA (€)",
            "Steuerl. Ergebnis vor Verlustvortrag (€)",
            "Verlustvortrag genutzt (€)", "Verlustvortrag-Bestand Ende Jahr (€)",
            "Steuerpflichtiges Ergebnis (€)", "Steuer (€)",
        ]
        st.dataframe(detail_df, width="stretch", hide_index=True)

    cf_spalten = [
        "cf_operativ_eur", "cf_invest_eur", "cf_finanzierung_eur",
        "cf_gesamt_eur", "cf_kumuliert_eur",
    ]
    display_df = df[["jahr", *cf_spalten]].copy()
    for col in cf_spalten:
        display_df[col] = display_df[col].round(0)
    display_df.columns = [
        "Jahr", "Operativ (€)", "Investition (€)", "Finanzierung (€)",
        "Gesamt (€)", "Kumuliert (€)",
    ]
    st.dataframe(display_df, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Erlöse
# ---------------------------------------------------------------------------


def _render_revenue_tab(result, df) -> None:
    ea = result.effective_assumptions

    section_title("Vergütungssatz und Marktwert im Zeitverlauf")
    st.caption(
        "Die bernsteinfarbene Fläche zwischen Vergütungssatz und Marktwert "
        "ist die Marktprämie (MAX-Mechanismus des EAG). Nach dem Förderende "
        "trägt der Markt allein."
    )
    st.plotly_chart(
        charts.verguetung_chart(
            df, ea.eag_zuschlagswert_effektiv_ct_kwh, ea.eag_foerderdauer_jahre
        ),
        width="stretch",
    )

    section_title("Markterlös vs. Marktprämie")
    st.caption(
        "Wie viel des Erlöses kommt aus dem Stromverkauf, wie viel aus dem "
        "EAG-Zuschuss? Der Prämienanteil zeigt die Förderabhängigkeit des "
        "Projekts."
    )
    st.plotly_chart(charts.revenue_split_chart(df), width="stretch")

    betrieb = df[df["jahr"] >= 1]
    erloes_gesamt = float(betrieb["erloes_eur"].sum())
    praemie_gesamt = float(betrieb["erloes_praemie_eur"].sum())
    anteil = praemie_gesamt / erloes_gesamt if erloes_gesamt else 0.0
    st.info(
        f"Über die Gesamtlaufzeit stammen {fmt_pct(anteil, 1)} der Erlöse "
        f"({fmt_eur(praemie_gesamt)}) aus der Marktprämie, der Rest aus dem "
        f"Marktverkauf."
    )

    section_title("Umsatzerlöse je Betriebsjahr")
    st.plotly_chart(charts.revenue_chart(df), width="stretch")


# ---------------------------------------------------------------------------
# Tab: Finanzierung
# ---------------------------------------------------------------------------


def _render_financing_tab(result, df, project) -> None:
    ea = result.effective_assumptions
    fremdkapital = ea.capex_total_eur * (1 - ea.eigenkapitalquote_pct)

    dscr_df = df.dropna(subset=["dscr"]).copy()
    if dscr_df.empty:
        st.info("Kein DSCR verfügbar (keine Fremdfinanzierung in diesem Projekt).")
    else:
        section_title("Schuldendienstdeckung (DSCR)")
        st.plotly_chart(charts.dscr_chart(dscr_df), width="stretch")

        section_title("Schuldenprofil")
        st.caption(
            "Restschuld (Fläche) sowie Zinsen und Tilgung (gestapelte Balken "
            "= Schuldendienst) über die Kreditlaufzeit."
        )
        st.plotly_chart(charts.debt_profile_chart(df, fremdkapital), width="stretch")

    col_kap, col_capex = st.columns(2)
    with col_kap:
        section_title("Kapitalstruktur")
        st.plotly_chart(
            charts.kapitalstruktur_donut_chart(
                ea.capex_total_eur * ea.eigenkapitalquote_pct, fremdkapital
            ),
            width="stretch",
        )
    with col_capex:
        section_title("Investitionsstruktur")
        capex = project.capex
        posten = {
            "EPC": capex.epc_eur,
            "Netzanschluss": capex.netzanschluss_eur,
            "Trasse": capex.trasse_eur,
            "Widmung": capex.widmung_eur,
            "Genehmigung": capex.genehmigung_eur,
            "Sonstige extern": capex.sonstige_extern_eur,
            "AGM": capex.agm_eur,
            "M&A": capex.m_and_a_eur,
            "Pönale-Puffer": capex.poenale_puffer_eur,
        }
        if any(v > 0 for v in posten.values()):
            st.plotly_chart(charts.capex_donut_chart(posten), width="stretch")
        else:
            st.info("Keine Investitionspositionen erfasst.")

    section_title("NPV-Sensitivität über den Diskontsatz")
    st.caption(
        "Die Nullstelle der Kurve ist per Definition die EK-Rendite (IRR)."
    )
    st.plotly_chart(
        charts.npv_curve_chart(result.npv_curve.copy(), result.kpis.equity_irr),
        width="stretch",
    )

    if not dscr_df.empty:
        dscr_display = dscr_df[["jahr", "dscr"]].copy()
        dscr_display["dscr"] = dscr_display["dscr"].round(2)
        dscr_display.columns = ["Jahr", "DSCR (x)"]
        with st.expander("DSCR-Tabelle"):
            st.dataframe(dscr_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Sensitivität (Tornado, Heatmap, EAG-Varianten, Gebotsassistent)
# ---------------------------------------------------------------------------

_ACHSEN_NAMEN = {k: name for k, (name, _) in HEATMAP_ACHSEN.items()}


def _render_sensitivity_tab(result, project, project_id: str) -> None:
    section_title("Tornado: Was bewegt die Rendite wirklich?")
    st.caption(
        "Jeder Werttreiber wird einzeln um ±10 % variiert (alle übrigen "
        "Annahmen konstant). Grün = Verbesserung, Rot = Verschlechterung "
        "der EK-Rendite gegenüber der Basis."
    )
    tornado_df = services.get_tornado(project_id)
    if tornado_df is not None and not tornado_df.empty:
        st.plotly_chart(charts.tornado_chart(tornado_df), width="stretch")

    st.divider()
    section_title("IRR-Landkarte: zwei Treiber gleichzeitig")
    st.caption(
        "EK-Rendite über ein Raster zweier frei wählbarer Treiber. Der "
        "Farbumschlag markiert die Grenze zur Ziel-Rendite."
    )
    col_x, col_y, col_ziel = st.columns([1.4, 1.4, 1])
    achse_x = col_x.selectbox(
        "Treiber X", list(_ACHSEN_NAMEN), format_func=_ACHSEN_NAMEN.get,
        index=0, key=f"hm_x_{project_id}",
    )
    optionen_y = [k for k in _ACHSEN_NAMEN if k != achse_x]
    achse_y = col_y.selectbox(
        "Treiber Y", optionen_y, format_func=_ACHSEN_NAMEN.get,
        index=0, key=f"hm_y_{project_id}",
    )
    ziel_irr_pct = col_ziel.number_input(
        "Ziel-IRR (%)", 0.0, 20.0, 8.0, 0.25, key=f"hm_ziel_{project_id}",
    )
    with st.spinner("Berechne IRR-Raster (49 Bewertungsläufe) …"):
        grid = services.get_irr_heatmap(project_id, achse_x, achse_y)
    if grid is not None:
        st.plotly_chart(
            charts.irr_heatmap_chart(
                grid, _ACHSEN_NAMEN[achse_x], _ACHSEN_NAMEN[achse_y],
                ziel_irr_pct / 100,
            ),
            width="stretch",
        )

    st.divider()
    section_title("Gebotsassistent: Break-even-EAG-Zuschlag")
    st.caption(
        "Der minimale anzulegende Wert (ct/kWh), bei dem das Projekt die "
        "Ziel-EK-Rendite gerade noch erreicht - die wirtschaftliche "
        "Untergrenze für ein Gebot in der EAG-Auktion."
    )
    col_be, col_res = st.columns([1, 2])
    ziel_gebot_pct = col_be.number_input(
        "Ziel-EK-Rendite (%)", 0.0, 20.0, 8.0, 0.25, key=f"be_ziel_{project_id}",
    )
    break_even = services.get_break_even_zuschlag(project_id, ziel_gebot_pct / 100)
    with col_res:
        if break_even is None:
            st.error(
                "Die Ziel-Rendite ist im Suchbereich (bis 15 ct/kWh) nicht "
                "erreichbar - Kostenseite oder Ertrag prüfen."
            )
        elif break_even <= 0.5:
            st.success(
                "Die Ziel-Rendite wird bereits ohne nennenswerte Prämie "
                "erreicht - der Marktwert trägt das Projekt allein. Jedes "
                "Gebot ab 0,5 ct/kWh genügt."
            )
        else:
            delta = project.eag_zuschlagswert_ct_kwh - break_even
            st.success(
                f"**Break-even: {fmt_ct_kwh(break_even)}** · aktuell angesetzt: "
                f"{fmt_ct_kwh(project.eag_zuschlagswert_ct_kwh)} "
                f"({'Puffer' if delta >= 0 else 'Fehlbetrag'}: "
                f"{fmt_ct_kwh(abs(delta))})"
            )

    st.divider()
    section_title("EAG-Zuschlag-Varianten (±5 % / ±10 %)")
    sens_df = services.get_eag_sensitivity(project_id)
    if sens_df is None or sens_df.empty:
        st.info("Keine Sensitivitätsdaten verfügbar.")
        return
    st.plotly_chart(charts.eag_sensitivity_chart(sens_df), width="stretch")

    sens_display = sens_df.copy()
    sens_display["eag_zuschlagswert_ct_kwh"] = sens_display[
        "eag_zuschlagswert_ct_kwh"
    ].round(3)
    sens_display["equity_irr"] = sens_display["equity_irr"].apply(fmt_pct)
    sens_display["npv_eur"] = sens_display["npv_eur"].round(0)
    sens_display = sens_display[
        ["variante", "eag_zuschlagswert_ct_kwh", "equity_irr", "npv_eur"]
    ]
    sens_display.columns = [
        "Variante", "EAG-Zuschlag (ct/kWh)", "EK-Rendite", "NPV (€)",
    ]
    with st.expander("Variantentabelle"):
        st.dataframe(sens_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Monte Carlo
# ---------------------------------------------------------------------------


def _render_monte_carlo_tab(project_id: str, diskontsatz: float) -> None:
    section_title("Monte-Carlo-Simulation")
    st.caption(
        "Alle Unsicherheiten gleichzeitig: Je Lauf werden Ertrag, "
        "Marktwert-Niveau, Investitions- und Betriebskosten zufällig um "
        "ihre Basis variiert (Normalverteilung, fester Seed → "
        "reproduzierbar) und die volle Bewertung gerechnet."
    )

    with st.expander("Unsicherheiten anpassen (Standardabweichung in %)"):
        col1, col2, col3, col4 = st.columns(4)
        s_prod = col1.slider("Spez. Ertrag", 0.0, 15.0, 5.0, 0.5,
                             key=f"mc_prod_{project_id}")
        s_markt = col2.slider("Marktwert-Niveau", 0.0, 30.0, 10.0, 0.5,
                              key=f"mc_markt_{project_id}")
        s_capex = col3.slider("Investitionskosten", 0.0, 15.0, 5.0, 0.5,
                              key=f"mc_capex_{project_id}")
        s_opex = col4.slider("Betriebskosten", 0.0, 15.0, 5.0, 0.5,
                             key=f"mc_opex_{project_id}")
        n_laeufe = st.select_slider(
            "Anzahl Läufe", options=[200, 400, 600, 1000], value=400,
            key=f"mc_n_{project_id}",
            help="Mehr Läufe = glattere Verteilung, längere Rechenzeit.",
        )

    sigmas = {
        "produktion": s_prod / 100, "marktwert": s_markt / 100,
        "capex": s_capex / 100, "opex": s_opex / 100,
    }

    gebots_key = None
    gebot_aktiv = st.toggle(
        "EAG-Zuschlagswert aus dem Ausschreibungsmodell ziehen",
        value=False, key=f"mc_gebot_{project_id}",
        help="Je Lauf wird der anzulegende Wert als zufälliges "
             "erfolgreiches Gebot der prognostizierten nächsten "
             "EAG-Ausschreibung gezogen (Seite 'Ausschreibung'), statt den "
             "fixen Projektwert zu verwenden. Der Konventionell-Abschlag "
             "bleibt erhalten; die Auktionsunsicherheit fließt so in die "
             "IRR-Verteilung ein.",
    )
    if gebot_aktiv:
        modell = services.get_auktions_modell()
        letzte = modell.letzte_runde
        cap = float(letzte.ausschreibung.preisobergrenze_ct)
        r_std = float(round(letzte.wettbewerbsquote, 2))
        col_g1, col_g2 = st.columns(2)
        r_mc = col_g1.number_input(
            "Erwartete Wettbewerbsquote r", 0.2, 5.0, r_std, 0.05,
            key=f"mc_gebot_r_{project_id}",
        )
        sigma_r_mc = col_g2.slider(
            "Unsicherheit σ(ln r)", 0.05, 0.6, 0.25, 0.05,
            key=f"mc_gebot_sigma_{project_id}",
        )
        gebots_key = (cap, r_mc, sigma_r_mc)

    # st.tabs rendert alle Tabs bei jedem Rerun - die Simulation laeuft
    # deshalb erst nach explizitem Start (danach haelt der Cache die
    # Ergebnisse, solange sich Projekt/Annahmen/Parameter nicht aendern).
    start_key = f"mc_gestartet_{project_id}"
    if not st.session_state.get(start_key):
        if st.button("Simulation starten", type="primary", key=f"mc_start_{project_id}"):
            st.session_state[start_key] = True
            st.rerun()
        return

    with st.spinner(f"Simuliere {n_laeufe} Bewertungsläufe …"):
        mc = services.get_monte_carlo(
            project_id, n_laeufe, sigmas, diskontsatz, gebots_key
        )
    if mc is None:
        st.error("Simulation konnte nicht ausgeführt werden.")
        return

    irr = mc.irr_gueltig
    if len(irr) == 0:
        st.error("Keine berechenbare IRR in den Simulationsläufen.")
        return
    p10, p50, p90 = (float(np.percentile(irr, q)) for q in (10, 50, 90))

    ziel_pct = st.slider(
        "Ziel-EK-Rendite für die Erfolgswahrscheinlichkeit (%)",
        0.0, 15.0, 8.0, 0.25, key=f"mc_ziel_{project_id}",
    )
    prob = mc.wahrscheinlichkeit_irr_ueber(ziel_pct / 100)

    render_kpi_row(
        [
            ("P10 (konservativ)", fmt_pct(p10)),
            ("P50 (Median)", fmt_pct(p50)),
            ("P90 (optimistisch)", fmt_pct(p90)),
            (f"P(IRR ≥ {fmt_number(ziel_pct, 2)} %)", fmt_pct(prob, 0)),
            (f"NPV-Median ({fmt_number(diskontsatz * 100, 2)} %)",
             fmt_eur(float(np.median(mc.npv)))),
        ],
        group="mc",
    )

    nicht_berechenbar = len(mc.irr) - len(irr)
    if nicht_berechenbar:
        st.caption(
            f"{nicht_berechenbar} von {len(mc.irr)} Läufen ohne berechenbare "
            f"IRR (durchgehend negativer Cashflow) - sie zählen in der "
            f"Erfolgswahrscheinlichkeit konservativ als 'unter Ziel'."
        )

    section_title("Verteilung der EK-Rendite")
    st.plotly_chart(charts.mc_irr_histogram(irr, p10, p50, p90), width="stretch")

    section_title("Bandbreite des kumulierten Equity-Cashflows")
    st.caption(
        "Fächer aus allen Läufen: inneres Band P25–P75, äußeres Band "
        "P10–P90, Linie = Median. Wo das äußere Band die Nulllinie "
        "schneidet, liegt die Payback-Bandbreite."
    )
    st.plotly_chart(charts.mc_fan_chart(mc), width="stretch")


# ---------------------------------------------------------------------------
# Tab: Szenarien
# ---------------------------------------------------------------------------


def _render_scenario_tab(result, project_id: str, diskontsatz: float) -> None:
    section_title("Marktpreisszenarien im Vergleich")
    st.caption(
        "Identisches Projekt, gerechnet über alle in den Globalen Annahmen "
        "hinterlegten Marktpreisszenarien. Das im Projekt gewählte Szenario: "
        f"**{result.effective_assumptions.marktpreisszenario_name}**."
    )
    vergleich = services.get_scenario_comparison(project_id, diskontsatz)
    if vergleich is None or vergleich.kennzahlen.empty:
        st.info("Keine Marktpreisszenarien hinterlegt.")
        return

    st.plotly_chart(charts.scenario_bar_chart(vergleich.kennzahlen), width="stretch")

    section_title("Kumulierter Equity-Cashflow je Szenario")
    st.plotly_chart(charts.scenario_cum_chart(vergleich.kum_cashflows), width="stretch")

    tabelle = vergleich.kennzahlen.copy()
    tabelle["equity_irr"] = tabelle["equity_irr"].apply(fmt_pct)
    tabelle["npv_eur"] = tabelle["npv_eur"].round(0)
    tabelle["erloes_gesamt_eur"] = tabelle["erloes_gesamt_eur"].round(0)
    tabelle.columns = [
        "Szenario", "EK-Rendite",
        f"NPV bei {fmt_number(diskontsatz * 100, 2)} % (€)",
        "Erlöse gesamt (€)",
    ]
    st.dataframe(tabelle, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Annahmen
# ---------------------------------------------------------------------------


def _render_assumptions_tab(result) -> None:
    """Transparenz-Tab: der vollstaendig aufgeloeste Parametersatz, mit dem
    dieses Projekt tatsaechlich gerechnet wurde (Projektmaske + Globale
    Annahmen nach dem Merge)."""
    ea = result.effective_assumptions
    st.caption(
        "Vollständig aufgelöster Parametersatz dieser Berechnung "
        "(Projektmaske zusammengeführt mit den Globalen Annahmen). "
        f"Marktpreisszenario: **{ea.marktpreisszenario_name}**."
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Anlage & Produktion**")
        st.markdown(
            f"- Leistung: {fmt_kwp(ea.nennleistung_kwp)}\n"
            f"- Vollbenutzungsstunden: {ea.vollbenutzungsstunden_kwh_kwp:.0f} kWh/kWp\n"
            f"- Degradation: {fmt_pct(ea.degradation_pct_pa)} p.a.\n"
            f"- Sicherheitsabschlag: {fmt_pct(ea.sicherheitsabschlag_pct)}\n"
            f"- Betrachtungsdauer: {ea.betriebsdauer_jahre} Jahre"
        )
    with col_b:
        st.markdown("**Erlöse & Förderung**")
        st.markdown(
            f"- EAG-Zuschlag (effektiv): {fmt_ct_kwh(ea.eag_zuschlagswert_effektiv_ct_kwh)}\n"
            f"- Förderdauer: {ea.eag_foerderdauer_jahre} Jahre\n"
            f"- Inflation Marktwerte: {fmt_pct(ea.marktpreis_inflation_pct_pa)} p.a. "
            f"ab {ea.marktpreis_inflation_basisjahr}\n"
            f"- Regel neg. Preise: "
            + (
                "6-Stunden (Österreich)"
                if ea.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN
                else "1-Stunde (Deutschland)"
            )
            + "\n"
            f"- Gewichtung neg. Stunden: {fmt_pct(ea.negative_stunden_gewichtung_pct, 0)}\n"
            f"- Negativstunden-Modus: "
            + (
                "Abregelung (Erlöse entfallen)"
                if ea.negative_stunden_modus == NegativeStundenModus.ABREGELUNG
                else "Rückfall auf Jahresmarktwert"
            )
        )
    with col_c:
        st.markdown("**Finanzierung & Steuer**")
        st.markdown(
            f"- Eigenkapitalquote: {fmt_pct(ea.eigenkapitalquote_pct, 0)}\n"
            f"- FK-Zins: {fmt_pct(ea.fremdkapitalzins_pct)}\n"
            f"- Kreditlaufzeit: {ea.kreditlaufzeit_jahre} Jahre "
            f"({ea.tilgungsart.value})\n"
            f"- Tilgungsfreies Anlaufjahr: "
            f"{'Ja' if ea.tilgungsfreies_anlaufjahr else 'Nein'}\n"
            f"- Steuermodus: {ea.tax_modus.value}\n"
            f"- Steuersatz: {fmt_pct(ea.steuersatz_pct, 0)}"
        )
