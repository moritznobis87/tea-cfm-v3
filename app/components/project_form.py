"""
Die Projektmaske als wiederverwendbare Komponente - identisch fuer
Neuanlage und Bearbeitung.

Designentscheidung Einheiten-Umschalter:
Die Umschalter fuer Investkosten (€/kWp <-> €) und Pacht (€/kWp/Jahr <->
€/ha/Jahr) liegen bewusst AUSSERHALB von st.form(...): Formular-Inhalte
aktualisieren sich in Streamlit erst beim Absenden, Umschalter ausserhalb
loesen dagegen einen sofortigen Rerun aus, damit Beschriftungen und
Werte unmittelbar umspringen.

Designentscheidung stabile Widget-Keys:
Beim Einheiten-Wechsel schreibt DIESE Komponente den passend
umgerechneten Wert direkt in den Session-State, BEVOR das Widget im
aktuellen Run instanziiert wird - es gibt also je Feld genau EIN Widget
mit stabilem Key, nicht zwei alternative Widgets je Einheit. Widgets, die
zwischen Runs erscheinen/verschwinden, sind in Streamlit ein bekanntes
Risikomuster fuer inkonsistentes Formularverhalten.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app import services
from app.config import MONATE
from engine import AnlagenTyp, CapexBreakdown, PVProject

#: EPC-Vorbelegung je Anlagentyp in €/kWp (Erfahrungswerte 2025/26).
EPC_DEFAULT_EUR_KWP = {"Agri-PV": 520.0, "Konventionell": 430.0}


def render_project_form(
    existing: PVProject | None, form_key: str
) -> PVProject | None:
    """Rendert die Projektmaske.

    Ohne `existing` = Neuanlage (sinnvolle Defaults), mit `existing` =
    Bearbeiten (vorausgefuellt, gleiche id). Gibt das neue/aktualisierte
    PVProject zurueck, wenn abgeschickt wurde, sonst None.
    """
    st.markdown("**Technische Anlagenparameter**")
    col1, col2, col3 = st.columns(3)
    nennleistung_kwp = col1.number_input(
        "Leistung (kWp)", min_value=0.0,
        value=existing.nennleistung_kwp if existing else 5000.0,
        step=100.0, key=f"{form_key}_leistung_live",
    )
    vollbenutzungsstunden = col2.number_input(
        "Vollbenutzungsstunden (kWh/kWp)", min_value=0.0,
        value=existing.vollbenutzungsstunden_kwh_kwp if existing else 1050.0,
        step=10.0, key=f"{form_key}_vbh_live",
    )
    anlagentyp_options = ["Agri-PV", "Konventionell"]
    anlagentyp_index = (
        1 if existing and existing.anlagentyp == AnlagenTyp.KONVENTIONELL else 0
    )
    anlagentyp_label = col3.radio(
        "Anlagentyp", anlagentyp_options, index=anlagentyp_index,
        horizontal=True, key=f"{form_key}_typ_live",
    )

    col_ibn1, col_ibn2 = st.columns(2)
    inbetriebnahme_jahr = col_ibn1.number_input(
        "Inbetriebnahme – Jahr", min_value=2000, max_value=2100,
        value=existing.inbetriebnahme_jahr if existing else datetime.now().year + 1,
        step=1, key=f"{form_key}_ibn_jahr_live",
    )
    inbetriebnahme_monat_label = col_ibn2.selectbox(
        "Inbetriebnahme – Monat", MONATE,
        index=(existing.inbetriebnahme_monat - 1) if existing else 0,
        key=f"{form_key}_ibn_monat_live",
    )
    inbetriebnahme_monat = MONATE.index(inbetriebnahme_monat_label) + 1
    st.caption(
        "ℹ️ Bestimmt das erste (anteilige) Betriebsjahr, die Cashflow-Daten "
        "und ab welchem Kalenderjahr die Marktpreiskurve des gewählten "
        "Szenarios (siehe unten) verwendet wird."
    )

    st.markdown("**Investkosten**")
    capex_defaults = existing.capex if existing else CapexBreakdown()
    capex_einheit = st.radio(
        "Einheit", options=["€/kWp", "€"], horizontal=True,
        key=f"{form_key}_capex_einheit",
    )

    # Der EPC-Default haengt vom Anlagentyp ab. Ein Anlagentyp-Wechsel muss
    # den vorbelegten Wert deshalb ebenfalls neu triggern, sonst bleibt der
    # beim ersten Rendern gesetzte Session-State-Wert stehen (gleiche
    # Problematik wie beim Einheiten-Wechsel, siehe Modulkopf).
    anlagentyp_mode_key = f"{form_key}_anlagentyp_prev"
    anlagentyp_changed = st.session_state.get(anlagentyp_mode_key) != anlagentyp_label
    st.session_state[anlagentyp_mode_key] = anlagentyp_label
    if anlagentyp_changed and not existing:
        st.session_state.pop(f"{form_key}_epc", None)

    capex_mode_key = f"{form_key}_capex_mode_prev"
    capex_mode_changed = st.session_state.get(capex_mode_key) != capex_einheit
    st.session_state[capex_mode_key] = capex_einheit

    def capex_feld(col, label: str, default_abs_eur: float, key_suffix: str) -> float:
        key = f"{form_key}_{key_suffix}"
        if capex_mode_changed or key not in st.session_state:
            if capex_einheit == "€/kWp":
                st.session_state[key] = (
                    round(default_abs_eur / nennleistung_kwp, 1)
                    if nennleistung_kwp
                    else 0.0
                )
            else:
                st.session_state[key] = default_abs_eur
        einheit_label = "€/kWp" if capex_einheit == "€/kWp" else "€"
        schritt = 1.0 if capex_einheit == "€/kWp" else 1000.0
        eingabe = col.number_input(
            f"{label} ({einheit_label})", min_value=0.0, step=schritt, key=key,
        )
        return eingabe * nennleistung_kwp if capex_einheit == "€/kWp" else eingabe

    st.markdown("**Pacht**")
    pacht_einheit = st.radio(
        "Einheit", options=["€/ha/Jahr", "€/kWp/Jahr"], horizontal=True,
        key=f"{form_key}_pacht_einheit",
    )
    pacht_mode_key = f"{form_key}_pacht_mode_prev"
    pacht_mode_changed = st.session_state.get(pacht_mode_key) != pacht_einheit
    st.session_state[pacht_mode_key] = pacht_einheit

    global_assumptions = services.get_global_assumptions()

    with st.form(form_key, clear_on_submit=False):
        name = st.text_input(
            "Projektname",
            value=existing.name if existing else "",
            placeholder="z.B. Sonnenfeld Agri-PV",
            key=f"{form_key}_name",
        )

        st.markdown("**Wirtschaftliche Parameter**")
        col5, col6, col7, col8 = st.columns(4)
        fk_zins = col5.number_input(
            "Fremdkapitalzins (%)", min_value=0.0,
            value=existing.fremdkapitalzins_pct * 100 if existing else 4.2,
            step=0.1, key=f"{form_key}_fkzins",
        )
        ek_anteil = col6.number_input(
            "Eigenkapitalanteil (%)", min_value=0.0, max_value=100.0,
            value=existing.eigenkapitalquote_pct * 100 if existing else 20.0,
            step=1.0, key=f"{form_key}_ekanteil",
        )
        eag_zuschlag = col7.number_input(
            "EAG-Zuschlagswert (ct/kWh)", min_value=0.0,
            value=existing.eag_zuschlagswert_ct_kwh if existing else 7.2,
            step=0.1, key=f"{form_key}_eag",
        )
        gemeindeabgabe_default = (
            existing.gemeindeabgabe_eur_mwh
            if existing
            else global_assumptions.gemeindeabgabe_eur_kwh * 1000
        )
        gemeindeabgabe_mwh = col8.number_input(
            "Gemeindeabgabe (€/MWh)", min_value=0.0,
            value=gemeindeabgabe_default, step=0.5,
            key=f"{form_key}_gemeindeabgabe",
        )
        col9, _, _, _ = st.columns(4)
        direktvermarktung_default = (
            existing.direktvermarktungskosten_eur_mwh
            if existing
            else global_assumptions.direktvermarktungskosten_eur_kwh * 1000
        )
        direktvermarktungskosten_mwh = col9.number_input(
            "Direktvermarktungskosten (€/MWh)", min_value=0.0,
            value=direktvermarktung_default, step=0.1,
            key=f"{form_key}_direktvermarktung",
            help="Kosten für Bilanzkreis, Prognose, Marktzugang - "
                 "üblicherweise ca. 1 €/MWh (0,1 ct/kWh).",
        )
        if anlagentyp_label == "Konventionell":
            st.caption(
                f"ℹ️ Konventionell: automatischer Abschlag von 25 % wird angewendet "
                f"→ effektiv {eag_zuschlag * 0.75:.2f} ct/kWh"
            )

        szenario_namen = global_assumptions.szenario_namen or ["Aurora 10/25"]
        default_szenario = existing.marktpreisszenario if existing else szenario_namen[0]
        szenario_index = (
            szenario_namen.index(default_szenario)
            if default_szenario in szenario_namen
            else 0
        )
        marktpreisszenario = st.selectbox(
            "Marktpreisszenario", szenario_namen, index=szenario_index,
            key=f"{form_key}_marktpreisszenario",
            help="Bestimmt die Marktwert-Solar- und Anteil-negativer-Stunden-"
                 "Kurve für dieses Projekt (siehe Globale Annahmen).",
        )

        if pacht_einheit == "€/ha/Jahr":
            flaeche_key = f"{form_key}_flaeche"
            if pacht_mode_changed or flaeche_key not in st.session_state:
                st.session_state[flaeche_key] = (
                    existing.projektflaeche_ha
                    if existing and existing.projektflaeche_ha
                    else 10.0
                )
            flaeche_ha = st.number_input(
                "Projektfläche (ha)", min_value=0.01, step=0.5, key=flaeche_key,
            )

            pacht_ha_key = f"{form_key}_pacht_ha"
            if pacht_mode_changed or pacht_ha_key not in st.session_state:
                st.session_state[pacht_ha_key] = (
                    round(
                        existing.pacht_eur_kwp_jahr
                        * existing.nennleistung_kwp
                        / flaeche_ha,
                        0,
                    )
                    if existing and flaeche_ha
                    else 500.0
                )
            pacht_eur_ha = st.number_input(
                "Pacht (€/ha/Jahr)", min_value=0.0, step=10.0, key=pacht_ha_key,
            )
            pacht_eur_kwp_jahr = (
                pacht_eur_ha * flaeche_ha / nennleistung_kwp
                if nennleistung_kwp
                else 0.0
            )
        else:
            pacht_kwp_key = f"{form_key}_pacht_kwp"
            if pacht_mode_changed or pacht_kwp_key not in st.session_state:
                st.session_state[pacht_kwp_key] = (
                    existing.pacht_eur_kwp_jahr if existing else 4.0
                )
            pacht_eur_kwp_jahr = st.number_input(
                "Pacht (€/kWp/Jahr)", min_value=0.0, step=0.1, key=pacht_kwp_key,
            )
            flaeche_ha = existing.projektflaeche_ha if existing else None

        st.markdown("**Investkosten (Details)**")
        epc_default_eur_kwp = EPC_DEFAULT_EUR_KWP[anlagentyp_label]
        c1, c2, c3, c4 = st.columns(4)
        epc = capex_feld(
            c1, "EPC",
            capex_defaults.epc_eur
            if existing
            else nennleistung_kwp * epc_default_eur_kwp,
            "epc",
        )
        netzanschluss = capex_feld(
            c2, "Netzanschluss",
            capex_defaults.netzanschluss_eur if existing else nennleistung_kwp * 50.0,
            "netz",
        )
        trasse = capex_feld(
            c3, "Trasse",
            capex_defaults.trasse_eur if existing else nennleistung_kwp * 40.0,
            "trasse",
        )
        sonstige_extern = capex_feld(
            c4, "Sonstige Extern",
            capex_defaults.sonstige_extern_eur if existing else 40000.0,
            "sonst",
        )
        c5, c6, c7 = st.columns(3)
        agm = capex_feld(
            c5, "AGM", capex_defaults.agm_eur if existing else 30000.0, "agm",
        )
        m_and_a = capex_feld(
            c6, "M&A", capex_defaults.m_and_a_eur if existing else 20000.0, "ma",
        )
        poenale = capex_feld(
            c7, "Pönale + Puffer",
            capex_defaults.poenale_puffer_eur if existing else 35000.0,
            "poenale",
        )

        button_label = (
            "Änderungen speichern" if existing else "Projekt anlegen und berechnen"
        )
        submitted = st.form_submit_button(button_label, type="primary")

    if not submitted:
        return None
    if not name.strip():
        st.error("Bitte einen Projektnamen angeben.")
        return None

    project_id = existing.id if existing else services.make_project_id(name)
    return PVProject(
        id=project_id,
        name=name.strip(),
        inbetriebnahme_jahr=inbetriebnahme_jahr,
        inbetriebnahme_monat=inbetriebnahme_monat,
        anlagentyp=AnlagenTyp.AGRI_PV
        if anlagentyp_label == "Agri-PV"
        else AnlagenTyp.KONVENTIONELL,
        nennleistung_kwp=nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=vollbenutzungsstunden,
        pacht_eur_kwp_jahr=pacht_eur_kwp_jahr,
        projektflaeche_ha=flaeche_ha,
        fremdkapitalzins_pct=fk_zins / 100,
        eigenkapitalquote_pct=ek_anteil / 100,
        eag_zuschlagswert_ct_kwh=eag_zuschlag,
        gemeindeabgabe_eur_mwh=gemeindeabgabe_mwh,
        direktvermarktungskosten_eur_mwh=direktvermarktungskosten_mwh,
        marktpreisszenario=marktpreisszenario,
        capex=CapexBreakdown(
            epc_eur=epc,
            netzanschluss_eur=netzanschluss,
            trasse_eur=trasse,
            sonstige_extern_eur=sonstige_extern,
            agm_eur=agm,
            m_and_a_eur=m_and_a,
            poenale_puffer_eur=poenale,
        ),
    )
