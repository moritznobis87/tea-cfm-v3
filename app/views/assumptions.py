"""
Seite "Globale Annahmen": zentrale Verwaltung von Marktpreisszenarien,
Standardbetriebskosten, technischen Annahmen, Finanzierung und Steuern.

Aenderungen wirken erst nach explizitem "Speichern" - und dann automatisch
auf ALLE Projekte (die Bewertungs-Caches werden dabei invalidiert, siehe
services.save_global_assumptions).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import services
from engine import (
    DirektvermarktungsModus,
    MarktpreisSzenario,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    TaxModus,
    TilgungsArt,
)


def render_assumptions() -> None:
    st.subheader("Globale Annahmen")
    st.caption(
        "Gelten für alle Projekte, sofern nicht projektspezifisch überschrieben. "
        "Änderungen wirken sich erst nach „Speichern“ auf alle Projekte aus."
    )

    ga = services.get_global_assumptions()

    # --- Marktpreisszenarien -------------------------------------------------
    with st.expander("Marktpreisszenarien", expanded=True):
        st.caption(
            "Kurven sind nach echtem Kalenderjahr indiziert. Je Projekt wird "
            "eines dieser Szenarien ausgewählt; das Kalenderjahr, ab dem die "
            "Kurve verwendet wird, ergibt sich aus dem Inbetriebnahmejahr des "
            "jeweiligen Projekts."
        )

        st.markdown("**Inflationierung der Marktwerte**")
        st.caption(
            "Marktpreisstudien (Aurora/Enervis) liefern typischerweise reale "
            "Werte auf Preisbasis des Erscheinungsjahres, keine bereits "
            "inflationierten Nominalwerte. Für die Cashflow-Rechnung wird "
            "deshalb ein Inflationsaufschlag ab dem Basisjahr angewendet. Der "
            "EAG-Zuschlagswert ist davon nicht betroffen (bleibt gesetzlich "
            "nominal fix während der Förderdauer)."
        )
        col_infl1, col_infl2, col_infl3 = st.columns(3)
        marktpreis_inflation = col_infl1.number_input(
            "Inflation Marktwerte (%/Jahr)", min_value=0.0,
            value=ga.marktpreis_inflation_pct_pa * 100, step=0.1,
        )
        marktpreis_basisjahr = col_infl2.number_input(
            "Basisjahr der Kurven", min_value=2000, max_value=2100,
            value=ga.marktpreis_inflation_basisjahr, step=1,
            help="Preisbasis-Jahr der Marktpreisstudie - ab diesem Jahr wird "
                 "die Inflation aufgeschlagen.",
        )
        kosten_inflation = col_infl3.number_input(
            "Kosteninflation (%/Jahr)", min_value=0.0,
            value=ga.kosten_inflation_pct_pa * 100, step=0.1,
            help="Wirkt auf ALLE Kostenpositionen ohne eigene Preislogik: "
                 "Pacht, Gemeindeabgabe und Direktvermarktungskosten "
                 "(absoluter Modus) eskalieren damit ab dem 2. "
                 "Betriebsjahr (Eingaben = Preisstand bei Inbetriebnahme). "
                 "Die Standard-OPEX-Positionen tragen ihre eigene, unten "
                 "einstellbare Indexierung (Vorbelegung ebenfalls 2 %/Jahr "
                 "ab Jahr 1); Direktvermarktung im Relativ-Modus folgt "
                 "bereits dem nominalen Marktwert.",
        )

        st.markdown("**Gewichtung negativer Stunden**")
        st.caption(
            "In Stunden negativer Strompreise entfällt gesetzlich die "
            "Marktprämie. 100 % = volle Wirkung wie in den Preiskurven "
            "hinterlegt. Niedrigere Werte blenden den Effekt teilweise oder "
            "ganz aus, z.B. für Vergleichsrechnungen ohne diesen Abschlag."
        )
        negative_stunden_gewichtung = st.slider(
            "Gewichtung (%)", min_value=0, max_value=100,
            value=int(round(ga.negative_stunden_gewichtung_pct * 100)), step=5,
        )

        st.markdown("**Regel für den Prämienentfall bei negativen Preisen**")
        st.caption(
            "Die Zeitreihen der Szenarien geben die Erzeugungsmenge an, die "
            "in Zeiten negativer Preise anfällt - getrennt nach 6h-Regel "
            "(Prämie entfällt erst ab mindestens 6 Stunden am Stück "
            "negativer Preise) und 1h-Regel (bereits ab 1 Stunde am Stück). "
            "Standard in Österreich ist die 6h-Regel, in Deutschland die "
            "1h-Regel."
        )
        regel_labels = {
            NegativeStundenRegel.SECHS_STUNDEN.value: (
                "6-Stunden-Regel (Österreich, Standard)"
            ),
            NegativeStundenRegel.EINE_STUNDE.value: "1-Stunden-Regel (Deutschland)",
        }
        regel_optionen = [r.value for r in NegativeStundenRegel]
        negative_stunden_regel = st.radio(
            "Regel für negative Preise",
            regel_optionen,
            format_func=lambda v: regel_labels[v],
            index=regel_optionen.index(ga.negative_stunden_regel.value),
            horizontal=True,
            label_visibility="collapsed",
        )

        st.markdown("**Verhalten in Stunden negativer Preise**")
        neg_modus_labels = {
            NegativeStundenModus.ABREGELUNG.value: (
                "Erlöse entfallen vollständig – Anlage wird abgeregelt"
            ),
            NegativeStundenModus.MARKTWERT.value: (
                "Rückfall auf Jahresmarktwert – keine Marktprämie, "
                "Anlage speist weiter ein"
            ),
        }
        neg_modus_optionen = [m.value for m in NegativeStundenModus]
        negative_stunden_modus = st.radio(
            "Negativstunden-Modus",
            neg_modus_optionen,
            format_func=lambda v: neg_modus_labels[v],
            index=neg_modus_optionen.index(ga.negative_stunden_modus.value),
            label_visibility="collapsed",
            help="Abregelung: Für den Anteil negativer Stunden entfallen die "
                 "Erlöse komplett. Rückfall auf Jahresmarktwert: Die Anlage "
                 "speist weiter ein und erhält den Marktwert, nur die "
                 "Marktprämie entfällt. Nach der Förderdauer wirkt der "
                 "Unterschied nur noch im Abregelungs-Modus.",
        )

        edited_szenarien: dict[str, pd.DataFrame] = {}
        if not ga.marktpreisszenarien:
            st.info("Noch kein Marktpreisszenario vorhanden.")
        else:
            tabs = st.tabs([s.name for s in ga.marktpreisszenarien])
            for tab, szenario in zip(tabs, ga.marktpreisszenarien, strict=True):
                with tab:
                    jahre = sorted(
                        set(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
                        | set(szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr)
                        | set(szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr)
                    )
                    kurven_df = pd.DataFrame(
                        {
                            "Kalenderjahr": jahre,
                            "Marktwert Solar (ct/kWh)": [
                                szenario.marktwert_solar_ct_kwh_je_kalenderjahr.get(j)
                                for j in jahre
                            ],
                            "Erzeugungsmenge neg. Stunden 6h (%)": [
                                (
                                    szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.get(
                                        j
                                    )
                                    or 0
                                )
                                * 100
                                for j in jahre
                            ],
                            "Erzeugungsmenge neg. Stunden 1h (%)": [
                                (
                                    szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.get(
                                        j
                                    )
                                    or 0
                                )
                                * 100
                                for j in jahre
                            ],
                        }
                    )
                    st.caption(
                        "Erzeugungsmenge neg. Stunden: Anteil der "
                        "PV-Jahreserzeugung, der in Zeiten negativer Preise "
                        "anfällt - je Regel (6h/1h) eine eigene Zeitreihe. "
                        "Angewendet wird die oben gewählte Regel."
                    )
                    edited_szenarien[szenario.name] = st.data_editor(
                        kurven_df, width="stretch", hide_index=True,
                        num_rows="dynamic", key=f"kurven_editor_{szenario.name}",
                    )

        st.divider()
        st.markdown("**Neues Szenario anlegen**")
        neuer_szenario_name = st.text_input(
            "Name des neuen Szenarios", key="neues_szenario_name",
            placeholder="z.B. Enervis 2026",
        )
        if st.button("Szenario hinzufügen") and neuer_szenario_name.strip():
            if neuer_szenario_name in ga.szenario_namen:
                st.error("Ein Szenario mit diesem Namen existiert bereits.")
            else:
                ga.marktpreisszenarien.append(
                    MarktpreisSzenario(name=neuer_szenario_name.strip())
                )
                services.save_global_assumptions(ga)
                st.rerun()

    # --- Standardbetriebskosten ----------------------------------------------
    with st.expander("Standardbetriebskosten"):
        opex_df = pd.DataFrame(
            [
                {
                    "Position": item.name,
                    "EUR/kWp/Jahr": item.basiswert_eur_kwp,
                    "Index %/Jahr": item.index_pct_pa * 100,
                    "Indexierung ab Jahr": item.indexierung_ab_jahr,
                }
                for item in ga.opex_standard
            ]
        )
        edited_opex = st.data_editor(
            opex_df, width="stretch", hide_index=True, num_rows="dynamic",
            key="opex_editor",
        )
        gemeindeabgabe = st.number_input(
            "Gemeindeabgabe – Vorschlagswert für neue Projekte (€/MWh)",
            min_value=0.0, value=ga.gemeindeabgabe_eur_kwh * 1000, step=0.5,
            help="Produktionsbasierte Abgabe an die Standortgemeinde. Dient nur "
                 "als Vorbelegung beim Anlegen eines neuen Projekts - die "
                 "tatsächlich angewendete Abgabe wird pro Projekt festgelegt "
                 "(im Projektformular unter 'Wirtschaftliche Parameter'), da "
                 "sie je nach Gemeinde unterschiedlich sein kann.",
        )
        st.markdown("**Direktvermarktungskosten**")
        dv_modus_label = st.radio(
            "Bemessung der Direktvermarktungskosten",
            ["Absoluter Betrag (€/MWh)", "Relativ zum Marktwert (%)"],
            index=0
            if ga.direktvermarktung_modus == DirektvermarktungsModus.ABSOLUT
            else 1,
            horizontal=True,
            help="Absolut: fester Betrag je erzeugter MWh (projektspezifisch, "
                 "z.B. 1 €/MWh). Relativ: Anteil am nominalen Jahresmarktwert "
                 "(gilt für alle Projekte, z.B. 10 % vom Marktwert) - die "
                 "Kosten atmen dann mit dem Preisniveau.",
        )
        dv_relativ = dv_modus_label.startswith("Relativ")
        col_dv1, col_dv2 = st.columns(2)
        direktvermarktungskosten = col_dv1.number_input(
            "Vorschlagswert für neue Projekte (€/MWh)",
            min_value=0.0, value=ga.direktvermarktungskosten_eur_kwh * 1000,
            step=0.1,
            disabled=dv_relativ,
            help="Kosten für Bilanzkreis, Prognose, Marktzugang - üblicherweise "
                 "ca. 1 €/MWh. Dient nur als Vorbelegung; tatsächlich "
                 "angewendet wird der projektspezifische Wert. Im Modus "
                 "'Relativ zum Marktwert' ohne Wirkung.",
        )
        dv_pct_marktwert = col_dv2.number_input(
            "Anteil am Marktwert (%)",
            min_value=0.0, max_value=100.0,
            value=ga.direktvermarktung_pct_marktwert * 100, step=0.5,
            disabled=not dv_relativ,
            help="Direktvermarktungskosten = erzeugte kWh × nominaler "
                 "Jahresmarktwert × dieser Anteil. Gilt für alle Projekte; "
                 "die projektspezifischen €/MWh-Werte sind dann ohne Wirkung.",
        )

    # --- Technische Standardannahmen -------------------------------------------
    with st.expander("Technische Standardannahmen", expanded=True):
        st.caption("Gelten für die Produktionsberechnung aller Projekte.")
        col_deg, col_sich = st.columns(2)
        degradation = col_deg.number_input(
            "Degradation (%/Jahr)", min_value=0.0,
            value=ga.degradation_pct_pa * 100, step=0.05,
            help="Jährliche Leistungsminderung der Module.",
        )
        sicherheitsabschlag = col_sich.number_input(
            "Sicherheitsabschlag Produktion (%)", min_value=0.0, max_value=100.0,
            value=ga.sicherheitsabschlag_pct * 100, step=0.5,
            help="Pauschaler Abschlag auf die berechnete Produktion (z.B. für "
                 "Verschattung, Verschmutzung, Ausfallzeiten).",
        )

    # --- Foerderung, Finanzierung ----------------------------------------------
    with st.expander("Förderung, Finanzierung", expanded=True):
        col1, col2, col3 = st.columns(3)
        eag_foerderdauer = col1.number_input(
            "EAG-Förderdauer (Jahre)", min_value=1, value=ga.eag_foerderdauer_jahre
        )
        betriebsdauer = col2.number_input(
            "Betrachtungsdauer (Jahre)", min_value=1, value=ga.betriebsdauer_jahre
        )
        kreditlaufzeit = col3.number_input(
            "Kreditlaufzeit (Jahre)", min_value=1, value=ga.kreditlaufzeit_jahre
        )
        tilgungsart = st.selectbox(
            "Tilgungsart", [art.value for art in TilgungsArt],
            index=0 if ga.tilgungsart == TilgungsArt.ANNUITAET else 1,
        )
        tilgungsfreies_anlaufjahr = st.toggle(
            "Tilgungsfreies Anlaufjahr",
            value=ga.tilgungsfreies_anlaufjahr,
            help="Im ersten Betriebsjahr werden nur Zinsen gezahlt, die "
                 "Tilgung beginnt in Jahr 2. Die Anzahl der Tilgungsraten "
                 "bleibt gleich (der Schuldendienst verlängert sich um ein "
                 "Jahr); dadurch fällt auch im zweiten Jahr der Zins noch "
                 "auf die volle Kreditsumme an.",
        )

    # --- Steuern ---------------------------------------------------------------
    with st.expander("Steuern", expanded=False):
        tax_modus_optionen = [modus.value for modus in TaxModus]
        tax_modus_labels = {
            "pauschal_auf_ebt": "Pauschal auf EBT (vereinfacht, keine AfA)",
            "afa_koerperschaftsteuer": "Körperschaftsteuer mit AfA (realistischer)",
        }
        tax_modus = st.radio(
            "Steuermodus",
            tax_modus_optionen,
            format_func=lambda v: tax_modus_labels[v],
            index=tax_modus_optionen.index(ga.tax_modus.value),
            horizontal=True,
        )

        col4, col5 = st.columns(2)
        steuersatz = col4.number_input(
            "Steuersatz (%)", min_value=0.0, value=ga.steuersatz_pct * 100, step=0.5,
            help="Österreich (KöSt): 23 % (Stand 2026).",
        )
        verlustvortrag_grenze = col5.number_input(
            "Verlustvortrag-Verrechnungsgrenze (%)", min_value=0.0, max_value=100.0,
            value=ga.verlustvortrag_verrechnungsgrenze_pct * 100, step=5.0,
            help="Maximaler Anteil des Gewinns eines Jahres, der mit "
                 "vorgetragenen Verlusten verrechnet werden darf. Österreich "
                 "(KStG): 75 % - mindestens 25 % des Gewinns bleiben also "
                 "immer steuerpflichtig, auch bei hohem Verlustvortrag. Gilt "
                 "unabhängig vom Steuermodus.",
        )

        if tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER.value:
            col6, col7 = st.columns(2)
            afa_nutzungsdauer = col6.number_input(
                "AfA-Nutzungsdauer (Jahre)", min_value=1,
                value=ga.afa_nutzungsdauer_jahre or 20,
                help="Lineare Abschreibungsdauer der Investitionskosten. Für "
                     "PV-Anlagen in Österreich üblich: 20 Jahre.",
            )
            freibetrag = col7.number_input(
                "Freibetrag (€/Jahr)", min_value=0.0,
                value=ga.freibetrag_eur, step=100.0,
            )
        else:
            afa_nutzungsdauer = ga.afa_nutzungsdauer_jahre
            freibetrag = ga.freibetrag_eur
            st.caption(
                "AfA und Freibetrag werden im Pauschalmodus nicht "
                "angewendet. Der Verlustvortrag gilt trotzdem."
            )

    # --- Speichern ---------------------------------------------------------------
    if st.button("Speichern", type="primary"):
        neue_szenarien = []
        for szenario in ga.marktpreisszenarien:
            edited = edited_szenarien.get(szenario.name)
            if edited is None:
                neue_szenarien.append(szenario)
                continue
            neue_szenarien.append(
                MarktpreisSzenario(
                    name=szenario.name,
                    marktwert_solar_ct_kwh_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(r["Marktwert Solar (ct/kWh)"])
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Marktwert Solar (ct/kWh)"])
                    },
                    erzeugungsmenge_negativ_6h_pct_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(
                            r["Erzeugungsmenge neg. Stunden 6h (%)"]
                        )
                        / 100
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Erzeugungsmenge neg. Stunden 6h (%)"])
                    },
                    erzeugungsmenge_negativ_1h_pct_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(
                            r["Erzeugungsmenge neg. Stunden 1h (%)"]
                        )
                        / 100
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Erzeugungsmenge neg. Stunden 1h (%)"])
                    },
                )
            )
        ga.marktpreisszenarien = neue_szenarien
        ga.marktpreis_inflation_pct_pa = marktpreis_inflation / 100
        ga.kosten_inflation_pct_pa = kosten_inflation / 100
        ga.marktpreis_inflation_basisjahr = int(marktpreis_basisjahr)
        ga.negative_stunden_gewichtung_pct = negative_stunden_gewichtung / 100
        ga.negative_stunden_modus = NegativeStundenModus(negative_stunden_modus)
        ga.negative_stunden_regel = NegativeStundenRegel(negative_stunden_regel)

        ga.opex_standard = [
            OpexItem(
                name=r["Position"],
                basiswert_eur_kwp=float(r["EUR/kWp/Jahr"]),
                index_pct_pa=float(r["Index %/Jahr"]) / 100,
                indexierung_ab_jahr=int(r["Indexierung ab Jahr"]),
            )
            for _, r in edited_opex.iterrows()
            if pd.notna(r["Position"])
        ]
        ga.eag_foerderdauer_jahre = int(eag_foerderdauer)
        ga.betriebsdauer_jahre = int(betriebsdauer)
        ga.kreditlaufzeit_jahre = int(kreditlaufzeit)
        ga.degradation_pct_pa = degradation / 100
        ga.sicherheitsabschlag_pct = sicherheitsabschlag / 100
        ga.steuersatz_pct = steuersatz / 100
        ga.tilgungsart = TilgungsArt(tilgungsart)
        ga.tilgungsfreies_anlaufjahr = tilgungsfreies_anlaufjahr
        ga.gemeindeabgabe_eur_kwh = gemeindeabgabe / 1000
        ga.direktvermarktungskosten_eur_kwh = direktvermarktungskosten / 1000
        ga.direktvermarktung_modus = (
            DirektvermarktungsModus.RELATIV_MARKTWERT
            if dv_relativ
            else DirektvermarktungsModus.ABSOLUT
        )
        ga.direktvermarktung_pct_marktwert = dv_pct_marktwert / 100
        ga.tax_modus = TaxModus(tax_modus)
        ga.afa_nutzungsdauer_jahre = (
            int(afa_nutzungsdauer) if afa_nutzungsdauer else None
        )
        ga.freibetrag_eur = float(freibetrag)
        ga.verlustvortrag_verrechnungsgrenze_pct = verlustvortrag_grenze / 100

        services.save_global_assumptions(ga)
        st.success("Globale Annahmen gespeichert.")
        st.rerun()
