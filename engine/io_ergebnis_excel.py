"""
Ergebnis-Export der gesamten Projekt-Pipeline als Excel-Arbeitsmappe:
ein Uebersichtsblatt plus je Projekt ein eigener Reiter mit allen
Dashboard-Auswertungen als NATIVE Excel-Diagramme (openpyxl-Charts,
keine Bilder) - jeweils mit dem Datengeruest als Tabelle daneben, so
dass die Diagramme in Excel voll editierbar bleiben.

Reine Werte-Ausgabe (Ergebnisbericht, keine Eingabezellen/Formeln);
Schrift Arial, deutsche Beschriftungen.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

from .analytics import (
    MC_STANDARD_SIGMAS,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
)
from .models import AnlagenTyp, GlobalAssumptions, PVProject
from .pipeline import run_valuation
from .sensitivity import run_eag_sensitivity

_FONT = "Arial"
_INK = "143530"
_BRAND = "BE172B"
_WASH = "F1F3F2"

_F_TITEL = Font(name=_FONT, size=14, bold=True, color=_INK)
_F_H2 = Font(name=_FONT, size=11, bold=True, color=_INK)
_F_KOPF = Font(name=_FONT, size=9, bold=True, color="FFFFFF")
_F_TEXT = Font(name=_FONT, size=9)
_FILL_KOPF = PatternFill("solid", fgColor=_INK)
_FILL_KPI = PatternFill("solid", fgColor=_WASH)

_EUR = "#,##0"
_CT = "0.00"
_PCT = "0.0%"

#: Diagrammgroesse (Zellenraster) und Spalte, in der Diagramme haengen.
_CHART_BREITE = 15.5
_CHART_HOEHE = 8.2
_CHART_SPALTE = "J"


def _stil(chart, titel: str, y_titel: str = "") -> None:
    chart.title = titel
    chart.style = 10
    chart.height = _CHART_HOEHE
    chart.width = _CHART_BREITE
    if y_titel:
        chart.y_axis.title = y_titel
    chart.y_axis.numFmt = "#,##0"


def _schreibe_tabelle(ws, zeile: int, df: pd.DataFrame,
                      formate: dict[str, str] | None = None) -> tuple[int, int]:
    """Schreibt einen DataFrame ab `zeile` (Spalte A) mit Kopfzeile;
    liefert (kopfzeile, letzte_zeile)."""
    formate = formate or {}
    for j, spalte in enumerate(df.columns, start=1):
        zelle = ws.cell(row=zeile, column=j, value=str(spalte))
        zelle.font = _F_KOPF
        zelle.fill = _FILL_KOPF
        zelle.alignment = Alignment(horizontal="center")
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        for j, spalte in enumerate(df.columns, start=1):
            wert = r[spalte]
            if isinstance(wert, (np.floating, np.integer)):
                wert = wert.item()
            zelle = ws.cell(row=zeile + i, column=j, value=wert)
            zelle.font = _F_TEXT
            if spalte in formate:
                zelle.number_format = formate[spalte]
    return zeile, zeile + len(df)


def _sektion(ws, zeile: int, titel: str) -> int:
    ws.cell(row=zeile, column=1, value=titel).font = _F_H2
    return zeile + 1


def _haenge_chart(ws, chart, anker_zeile: int) -> None:
    ws.add_chart(chart, f"{_CHART_SPALTE}{anker_zeile}")


def _naechste_zeile(tab_ende: int, anker: int) -> int:
    """Naechster Sektionsstart: unter Tabelle UND Diagramm (~17 Zeilen)."""
    return max(tab_ende, anker + 17) + 2


def _linien_chart(ws, kopf: int, ende: int, spalten: list[int],
                  titel: str, y_titel: str) -> LineChart:
    chart = LineChart()
    _stil(chart, titel, y_titel)
    for c in spalten:
        chart.add_data(
            Reference(ws, min_col=c, min_row=kopf, max_row=ende),
            titles_from_data=True,
        )
    chart.set_categories(Reference(ws, min_col=1, min_row=kopf + 1, max_row=ende))
    return chart


def _balken_chart(ws, kopf: int, ende: int, spalten: list[int], titel: str,
                  y_titel: str, gestapelt: bool = False,
                  horizontal: bool = False) -> BarChart:
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    if gestapelt:
        chart.grouping = "stacked"
        chart.overlap = 100
    _stil(chart, titel, y_titel)
    for c in spalten:
        chart.add_data(
            Reference(ws, min_col=c, min_row=kopf, max_row=ende),
            titles_from_data=True,
        )
    chart.set_categories(Reference(ws, min_col=1, min_row=kopf + 1, max_row=ende))
    return chart


def _blattname(name: str, vergeben: set[str]) -> str:
    for zeichen in "[]:*?/\\":
        name = name.replace(zeichen, " ")
    name = name.strip()[:28] or "Projekt"
    kandidat, i = name, 2
    while kandidat in vergeben:
        kandidat = f"{name[:25]} ({i})"
        i += 1
    vergeben.add(kandidat)
    return kandidat


# ---------------------------------------------------------------------------
# Projektblatt
# ---------------------------------------------------------------------------


def _projektblatt(ws, project: PVProject, ga: GlobalAssumptions,
                  n_mc: int) -> None:
    result = run_valuation(project, ga)
    df = result.cashflow.data
    kpis = result.kpis
    betrieb = df[df["jahr"] >= 1]

    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 30
    for sp in "BCDEFGH":
        ws.column_dimensions[sp].width = 14

    typ = "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"
    titel = ws.cell(row=1, column=1, value=f"{project.name} ({typ})"
                    + ("" if project.aktiv else " – INAKTIV"))
    titel.font = _F_TITEL

    # --- KPI-Block ---
    kpi_paare = [
        ("Nennleistung", project.nennleistung_kwp, "#,##0 \"kWp\""),
        ("EAG-Zuschlagswert", project.eag_zuschlagswert_ct_kwh, "0.00 \"ct/kWh\""),
        ("CAPEX gesamt", kpis.capex_total_eur, _EUR + " €"),
        ("Eigenkapital", kpis.eigenkapital_eur, _EUR + " €"),
        ("EK-Rendite (IRR)", kpis.equity_irr, _PCT),
        ("NPV", kpis.npv_eur, _EUR + " €"),
        ("DSCR (Minimum)", kpis.dscr_min, "0.00"),
        ("Amortisation", kpis.payback_jahre, "0.0 \"Jahre\""),
    ]
    for i, (name, wert, fmt) in enumerate(kpi_paare):
        z = 3 + i
        ws.cell(row=z, column=1, value=name).font = _F_TEXT
        ws.cell(row=z, column=1).fill = _FILL_KPI
        zelle = ws.cell(row=z, column=2, value=wert)
        zelle.font = Font(name=_FONT, size=9, bold=True)
        zelle.fill = _FILL_KPI
        zelle.number_format = fmt

    zeile = 13

    # --- 1. Verguetung & Marktwert ---
    zeile = _sektion(ws, zeile, "Vergütung und Marktwert (ct/kWh)")
    t = betrieb[["jahr", "marktwert_nominal_ct_kwh", "verguetungssatz_ct_kwh"]]
    t = t.rename(columns={"jahr": "Jahr",
                          "marktwert_nominal_ct_kwh": "Marktwert (nominal)",
                          "verguetungssatz_ct_kwh": "Vergütungssatz"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t, {
        "Marktwert (nominal)": _CT, "Vergütungssatz": _CT})
    chart = _linien_chart(ws, kopf, ende, [2, 3],
                          "Vergütung und Marktwert", "ct/kWh")
    chart.y_axis.numFmt = "0.00"
    _haenge_chart(ws, chart, kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 2. Erloesstruktur ---
    zeile = _sektion(ws, zeile, "Erlösstruktur (€/Jahr)")
    t = betrieb[["jahr", "erloes_markt_eur", "erloes_praemie_eur"]].rename(
        columns={"jahr": "Jahr", "erloes_markt_eur": "Markterlös",
                 "erloes_praemie_eur": "Marktprämie"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t,
                                   {"Markterlös": _EUR, "Marktprämie": _EUR})
    _haenge_chart(ws, _balken_chart(ws, kopf, ende, [2, 3],
                                    "Erlösstruktur", "€/Jahr", gestapelt=True),
                  kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 3. Gesamt-Cashflow (Kombi Balken + kumulierte Linie) ---
    zeile = _sektion(ws, zeile, "Gesamt-Cashflow (€/Jahr)")
    t = df[["jahr", "cf_gesamt_eur", "cf_kumuliert_eur"]].rename(
        columns={"jahr": "Jahr", "cf_gesamt_eur": "Cashflow",
                 "cf_kumuliert_eur": "Kumuliert"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t,
                                   {"Cashflow": _EUR, "Kumuliert": _EUR})
    balken = _balken_chart(ws, kopf, ende, [2], "Gesamt-Cashflow", "€")
    linie = LineChart()
    linie.add_data(Reference(ws, min_col=3, min_row=kopf, max_row=ende),
                   titles_from_data=True)
    balken += linie
    _haenge_chart(ws, balken, kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 4. Betriebskosten (gestapelt) ---
    zeile = _sektion(ws, zeile, "Betriebskosten (€/Jahr)")
    opex_spalten = list(result.cashflow.opex_posten) + [
        "gemeindeabgabe_eur", "direktvermarktungskosten_eur"]
    opex_spalten = [c for c in opex_spalten if c in betrieb.columns]
    t = betrieb[["jahr"] + opex_spalten].rename(columns={
        "jahr": "Jahr", "gemeindeabgabe_eur": "Gemeindeabgabe",
        "direktvermarktungskosten_eur": "Direktvermarktung"})
    kopf, ende = _schreibe_tabelle(
        ws, zeile, t, {c: _EUR for c in t.columns if c != "Jahr"})
    _haenge_chart(ws, _balken_chart(
        ws, kopf, ende, list(range(2, len(t.columns) + 1)),
        "Betriebskosten", "€/Jahr", gestapelt=True), kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 5. Finanzierung ---
    zeile = _sektion(ws, zeile, "Kapitaldienst und DSCR")
    t = betrieb[["jahr", "zinsen_eur", "tilgung_eur", "dscr"]].rename(
        columns={"jahr": "Jahr", "zinsen_eur": "Zinsen",
                 "tilgung_eur": "Tilgung", "dscr": "DSCR"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t, {
        "Zinsen": _EUR, "Tilgung": _EUR, "DSCR": "0.00"})
    _haenge_chart(ws, _balken_chart(ws, kopf, ende, [2, 3],
                                    "Kapitaldienst", "€/Jahr", gestapelt=True),
                  kopf)
    dscr_chart = _linien_chart(ws, kopf, ende, [4], "DSCR-Verlauf", "DSCR")
    dscr_chart.y_axis.numFmt = "0.00"
    ws.add_chart(dscr_chart, f"{_CHART_SPALTE}{kopf + 18}")
    zeile = max(_naechste_zeile(ende, kopf), kopf + 37)

    # --- 6. NPV-Kurve ---
    zeile = _sektion(ws, zeile, "Kapitalwert nach Diskontsatz")
    t = result.npv_curve.rename(columns={
        "diskontsatz_pct": "Diskontsatz", "npv_eur": "NPV"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t,
                                   {"Diskontsatz": _PCT, "NPV": _EUR})
    _haenge_chart(ws, _linien_chart(ws, kopf, ende, [2],
                                    "NPV nach Diskontsatz", "€"), kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 7. Sensitivitaet (Tornado) ---
    zeile = _sektion(ws, zeile, "Sensitivität der EK-Rendite (±10 %)")
    tornado = run_tornado(project, ga).sort_values("spanne")
    t = tornado[["name", "irr_runter", "irr_rauf"]].rename(columns={
        "name": "Treiber", "irr_runter": "IRR −10 %", "irr_rauf": "IRR +10 %"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t, {
        "IRR −10 %": _PCT, "IRR +10 %": _PCT})
    chart = _balken_chart(ws, kopf, ende, [2, 3],
                          "Sensitivität EK-Rendite", "IRR", horizontal=True)
    chart.y_axis.numFmt = "0.0%"
    _haenge_chart(ws, chart, kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 8. EAG-Sensitivitaet ---
    zeile = _sektion(ws, zeile, "Sensitivität EAG-Zuschlagswert")
    sens = run_eag_sensitivity(project, ga)
    t = sens[["eag_zuschlagswert_ct_kwh", "equity_irr", "npv_eur"]].rename(
        columns={"eag_zuschlagswert_ct_kwh": "Zuschlagswert (ct/kWh)",
                 "equity_irr": "EK-Rendite", "npv_eur": "NPV"})
    kopf, ende = _schreibe_tabelle(ws, zeile, t, {
        "Zuschlagswert (ct/kWh)": _CT, "EK-Rendite": _PCT, "NPV": _EUR})
    chart = LineChart()
    _stil(chart, "EK-Rendite nach Zuschlagswert", "IRR")
    chart.add_data(Reference(ws, min_col=2, min_row=kopf, max_row=ende),
                   titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=kopf + 1, max_row=ende))
    chart.y_axis.numFmt = "0.0%"
    _haenge_chart(ws, chart, kopf)
    zeile = _naechste_zeile(ende, kopf)

    # --- 9. Monte Carlo (Histogramm aus Klassen) ---
    zeile = _sektion(ws, zeile, f"Monte-Carlo-Simulation ({n_mc} Läufe, "
                     "Standard-Streuungen)")
    mc = run_monte_carlo(project, ga, n_laeufe=n_mc,
                         sigmas=dict(MC_STANDARD_SIGMAS))
    irr = mc.irr[~np.isnan(mc.irr)]
    p10, p50, p90 = (float(np.percentile(irr, q)) for q in (10, 50, 90))
    kanten = np.linspace(irr.min(), irr.max(), 16)
    haeufig, _ = np.histogram(irr, bins=kanten)
    t = pd.DataFrame({
        "EK-Rendite (Klassenmitte)": (kanten[:-1] + kanten[1:]) / 2,
        "Anzahl Läufe": haeufig,
    })
    kopf, ende = _schreibe_tabelle(ws, zeile, t, {
        "EK-Rendite (Klassenmitte)": _PCT})
    _haenge_chart(ws, _balken_chart(ws, kopf, ende, [2],
                                    "Verteilung der EK-Rendite",
                                    "Anzahl Läufe"), kopf)
    for i, (name, wert) in enumerate(
        (("P10", p10), ("Median", p50), ("P90", p90))
    ):
        ws.cell(row=ende + 2 + i, column=1, value=name).font = _F_TEXT
        z = ws.cell(row=ende + 2 + i, column=2, value=wert)
        z.font = _F_TEXT
        z.number_format = _PCT
    zeile = _naechste_zeile(ende + 5, kopf)

    # --- 10. Szenarienvergleich ---
    zeile = _sektion(ws, zeile, "Marktpreisszenarien im Vergleich")
    vergleich = run_scenario_comparison(project, ga)
    kz = vergleich.kennzahlen.rename(columns={
        "szenario": "Szenario", "equity_irr": "EK-Rendite",
        "npv_eur": "NPV", "erloes_summe_eur": "Erlöse gesamt"})
    kz = kz[[c for c in ("Szenario", "EK-Rendite", "NPV", "Erlöse gesamt")
             if c in kz.columns]]
    kopf, ende = _schreibe_tabelle(ws, zeile, kz, {
        "EK-Rendite": _PCT, "NPV": _EUR, "Erlöse gesamt": _EUR})
    chart = _balken_chart(ws, kopf, ende, [2], "EK-Rendite je Szenario", "IRR")
    chart.y_axis.numFmt = "0.0%"
    _haenge_chart(ws, chart, kopf)


# ---------------------------------------------------------------------------
# Uebersichtsblatt + Gesamtexport
# ---------------------------------------------------------------------------


def pipeline_ergebnis_excel(
    projekte: list[tuple[PVProject, str]],
    ga: GlobalAssumptions,
    n_mc: int = 300,
) -> bytes:
    """Erstellt die Ergebnis-Arbeitsmappe: Blatt 'Übersicht' plus je
    Projekt ein Reiter mit allen Auswertungen als native Excel-
    Diagramme. `projekte`: Liste (Projekt, gewuenschter Blattname)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Übersicht"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 30
    for sp in "BCDEFGHI":
        ws.column_dimensions[sp].width = 14
    ws.cell(row=1, column=1, value="TEA PV-Projektbewertung – "
            "Pipeline-Ergebnisse").font = _F_TITEL

    zeilen = []
    ergebnisse: list[tuple[PVProject, str]] = []
    vergeben = {"Übersicht"}
    for project, wunschname in projekte:
        kpis = run_valuation(project, ga).kpis
        zeilen.append({
            "Projekt": project.name,
            "Typ": ("Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV
                    else "Konventionell"),
            "Aktiv": "ja" if project.aktiv else "nein",
            "kWp": project.nennleistung_kwp,
            "CAPEX (€)": kpis.capex_total_eur,
            "Eigenkapital (€)": kpis.eigenkapital_eur,
            "EK-Rendite": kpis.equity_irr,
            "NPV (€)": kpis.npv_eur,
            "DSCR min": kpis.dscr_min,
        })
        ergebnisse.append((project, _blattname(wunschname, vergeben)))

    uebersicht = pd.DataFrame(zeilen)
    kopf, ende = _schreibe_tabelle(ws, 3, uebersicht, {
        "kWp": "#,##0", "CAPEX (€)": _EUR, "Eigenkapital (€)": _EUR,
        "EK-Rendite": _PCT, "NPV (€)": _EUR, "DSCR min": "0.00"})
    chart = BarChart()
    chart.type = "col"
    _stil(chart, "EK-Rendite je Projekt", "IRR")
    chart.add_data(Reference(ws, min_col=7, min_row=kopf, max_row=ende),
                   titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=kopf + 1,
                                   max_row=ende))
    chart.y_axis.numFmt = "0.0%"
    ws.add_chart(chart, f"A{ende + 3}")
    ws.cell(row=ende + 21, column=1,
            value="Je Projekt ein eigener Reiter mit allen Auswertungen; "
                  "alle Diagramme sind native Excel-Diagramme und über die "
                  "danebenstehenden Tabellen editierbar.").font = _F_TEXT

    for project, blatt in ergebnisse:
        _projektblatt(wb.create_sheet(blatt), project, ga, n_mc)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
