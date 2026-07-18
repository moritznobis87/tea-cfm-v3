"""
PDF-Ergebnisbericht ("Gutachten") fuer ein Einzelprojekt.

Aufbau: Deckblatt mit Logo und Projektsteckbrief, Inhaltsverzeichnis,
Management Summary, Kapitel Ergebnisrechnung / Erloese / Finanzierung /
Sensitivitaet / Risiko (Monte Carlo) / Szenarienvergleich sowie ein
Annex mit dem vollstaendig aufgeloesten Parametersatz und allen
verwendeten Zeitreihen.

Bewusst OHNE Streamlit-Import gehalten: build_pdf_report() ist eine reine
Funktion (Eingaben -> PDF-Bytes) und damit direkt testbar. Diagramme
werden mit Matplotlib im Markenstil gerendert und als hochaufloesende
Grafiken eingebettet; Zahlenformate kommen aus app.formatting (deutsche
Notation, konsistent zur App).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.formatting import (
    fmt_ct_kwh,
    fmt_dscr,
    fmt_eur,
    fmt_kwp,
    fmt_number,
    fmt_pct,
)
from engine import (
    AnlagenTyp,
    GlobalAssumptions,
    NegativeStundenModus,
    NegativeStundenRegel,
    PVProject,
)
from engine.analytics import MC_STANDARD_SIGMAS, MonteCarloResult, SzenarioVergleich
from texte import txt

# ---------------------------------------------------------------------------
# Markenstil (identische Hex-Werte wie app.theme.Colors; hier ohne
# Streamlit-Import dupliziert, damit der Bericht headless erzeugbar bleibt)
# ---------------------------------------------------------------------------

BRAND = "#BE172B"
INK = "#143530"
INK_SOFT = "#2E5A52"
MUTED = "#5B6B66"
LINE = "#E1E8E5"
WASH = "#F6F9F8"
POSITIVE = "#2E7D32"
NEGATIVE = "#C0392B"
NEUTRAL = "#8AA6A0"
SERIES = [INK, BRAND, NEUTRAL, POSITIVE, INK_SOFT]

_SEITE_B, _SEITE_H = A4
_RAND_L, _RAND_R, _RAND_O, _RAND_U = 2.0 * cm, 2.0 * cm, 2.3 * cm, 2.0 * cm
_INHALT_B = _SEITE_B - _RAND_L - _RAND_R
_CHART_B_CM = 16.5

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 8.5,
        "axes.edgecolor": LINE,
        "axes.labelcolor": INK,
        "axes.titlesize": 9,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": LINE,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "figure.dpi": 100,
    }
)


def _de(zahl: float, nachkomma: int = 0) -> str:
    return fmt_number(zahl, nachkomma)


def _eur_achse(werte_max: float):
    """Achsenformatierer: € in T€ oder Mio. € je nach Groessenordnung."""
    if abs(werte_max) >= 2_000_000:
        return FuncFormatter(lambda v, _: _de(v / 1e6, 1)), "Mio. €"
    return FuncFormatter(lambda v, _: _de(v / 1e3, 0)), "T€"


def _fig(hoehe_cm: float = 6.6) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(_CHART_B_CM / 2.54, hoehe_cm / 2.54))
    for seite in ("top", "right"):
        ax.spines[seite].set_visible(False)
    return fig, ax


def _fig_zu_bild(fig: plt.Figure, breite_cm: float = _CHART_B_CM) -> Image:
    puffer = io.BytesIO()
    fig.tight_layout(pad=0.6)
    fig.savefig(puffer, format="png", dpi=200)
    plt.close(fig)
    puffer.seek(0)
    b_pt = breite_cm * cm
    h_pt = b_pt * fig.get_size_inches()[1] / fig.get_size_inches()[0]
    return Image(puffer, width=b_pt, height=h_pt)


# ---------------------------------------------------------------------------
# Diagramme
# ---------------------------------------------------------------------------


def _chart_gesamt_cashflow(df: pd.DataFrame) -> Image:
    fig, ax = _fig()
    fmt, einheit = _eur_achse(df["cf_kumuliert_eur"].abs().max())
    farben = [POSITIVE if v >= 0 else NEGATIVE for v in df["cf_gesamt_eur"]]
    ax.bar(df["jahr"], df["cf_gesamt_eur"], color=farben, width=0.72,
           label="Cashflow p.a.")
    ax2 = ax.twinx()
    ax2.plot(df["jahr"], df["cf_kumuliert_eur"], color=INK, linewidth=1.6,
             label="Kumuliert (rechte Achse)")
    ax2.axhline(0, color=MUTED, linewidth=0.8, linestyle=":")
    ax2.spines["top"].set_visible(False)
    ax2.grid(False)
    ax.yaxis.set_major_formatter(fmt)
    ax2.yaxis.set_major_formatter(fmt)
    ax.set_ylabel(f"Cashflow p.a. ({einheit})")
    ax2.set_ylabel(f"Kumuliert ({einheit})")
    ax.set_xlabel("Jahr (0 = Investition)")
    linien = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    namen = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(linien, namen, loc="lower right")
    return _fig_zu_bild(fig)


def _chart_wertbruecke(df: pd.DataFrame) -> Image:
    posten = [
        ("Umsatz-\nerlöse", float(df["erloes_eur"].sum())),
        ("Betriebs-\nkosten", -float(df["opex_gesamt_eur"].sum())),
        ("Zinsen", -float(df["zinsen_eur"].sum())),
        ("Steuern", -float(df["steuer_eur"].sum())),
        ("Investition", float(df["cf_invest_eur"].sum())),
        ("Kredit-\naufnahme", float(df.loc[df["jahr"] == 0, "cf_finanzierung_eur"].iloc[0])),
        ("Tilgung", -float(df["tilgung_eur"].sum())),
    ]
    fig, ax = _fig(6.2)
    fmt, einheit = _eur_achse(posten[0][1])
    laufend = 0.0
    for i, (_name, wert) in enumerate(posten):
        farbe = POSITIVE if wert >= 0 else NEGATIVE
        ax.bar(i, wert, bottom=laufend, color=farbe, width=0.62)
        laufend += wert
        ax.plot([i + 0.31, i + 0.69], [laufend, laufend], color=MUTED,
                linewidth=0.7, linestyle=":")
    ax.bar(len(posten), laufend, color=INK, width=0.62)
    ax.annotate(f"{_de(laufend / 1e6, 2)} Mio. €",
                (len(posten), laufend), textcoords="offset points",
                xytext=(0, 4), ha="center", color=INK, fontsize=8.5,
                fontweight="bold")
    ax.set_xticks(range(len(posten) + 1))
    ax.set_xticklabels([n for n, _ in posten] + ["Equity-\nCashflow"], fontsize=7.5)
    ax.yaxis.set_major_formatter(fmt)
    ax.set_ylabel(f"Summe Laufzeit ({einheit})")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    return _fig_zu_bild(fig)


def _chart_verguetung(df: pd.DataFrame, zuschlag_ct: float, dauer: int) -> Image:
    betrieb = df[df["jahr"] >= 1]
    fig, ax = _fig()
    ax.plot(betrieb["jahr"], betrieb["marktwert_nominal_ct_kwh"], color=NEUTRAL,
            linewidth=1.4, label="Marktwert Solar (nominal)")
    ax.plot(betrieb["jahr"], betrieb["verguetungssatz_ct_kwh"], color=INK,
            linewidth=1.8, label="Vergütungssatz")
    ax.fill_between(
        betrieb["jahr"], betrieb["marktwert_nominal_ct_kwh"],
        betrieb["verguetungssatz_ct_kwh"], color=NEUTRAL, alpha=0.25,
        label="Marktprämie",
    )
    ax.axhline(zuschlag_ct, color=BRAND, linewidth=1.1, linestyle="--",
               label="EAG-Zuschlagswert (nominal fix)")
    ax.axvline(dauer + 0.5, color=MUTED, linewidth=0.9, linestyle=":")
    ax.annotate("Förderende", (dauer + 0.5, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(4, -10), color=MUTED,
                fontsize=7.5)
    ax.set_xlabel("Betriebsjahr")
    ax.set_ylabel("ct/kWh")
    ax.legend(loc="upper left", ncol=2)
    return _fig_zu_bild(fig)


def _chart_erloes_split(df: pd.DataFrame) -> Image:
    betrieb = df[df["jahr"] >= 1]
    fig, ax = _fig()
    fmt, einheit = _eur_achse(betrieb["erloes_eur"].max())
    ax.bar(betrieb["jahr"], betrieb["erloes_markt_eur"], color=POSITIVE,
           width=0.72, label="Markterlös")
    ax.bar(betrieb["jahr"], betrieb["erloes_praemie_eur"],
           bottom=betrieb["erloes_markt_eur"], color=NEUTRAL, width=0.72,
           label="Marktprämie (EAG)")
    ax.yaxis.set_major_formatter(fmt)
    ax.set_ylabel(f"Erlöse ({einheit})")
    ax.set_xlabel("Betriebsjahr")
    ax.legend(loc="upper right")
    return _fig_zu_bild(fig)


def _chart_dscr(df: pd.DataFrame) -> Image:
    dscr = df.dropna(subset=["dscr"])
    fig, ax = _fig(5.8)
    farben = [POSITIVE if v >= 1 else NEGATIVE for v in dscr["dscr"]]
    ax.bar(dscr["jahr"], dscr["dscr"], color=farben, width=0.7)
    ax.axhline(1.0, color=BRAND, linewidth=1.1, linestyle="--")
    ax.annotate("Deckungsgrenze 1,0x", (dscr["jahr"].iloc[0], 1.0),
                textcoords="offset points", xytext=(0, 5), color=BRAND,
                fontsize=7.5)
    ax.set_xlabel("Betriebsjahr")
    ax.set_ylabel("DSCR (x)")
    return _fig_zu_bild(fig)


def _chart_schuldenprofil(df: pd.DataFrame, fremdkapital: float) -> Image:
    betrieb = df[df["jahr"] >= 1]
    restschuld = (fremdkapital - betrieb["tilgung_eur"].cumsum()).clip(lower=0)
    fig, ax = _fig(5.8)
    fmt, einheit = _eur_achse(fremdkapital)
    ax.fill_between(betrieb["jahr"], restschuld, color=INK, alpha=0.12)
    ax.plot(betrieb["jahr"], restschuld, color=INK, linewidth=1.6,
            label="Restschuld")
    ax.bar(betrieb["jahr"], betrieb["zinsen_eur"], color=BRAND, width=0.7,
           label="Zinsen")
    ax.bar(betrieb["jahr"], betrieb["tilgung_eur"],
           bottom=betrieb["zinsen_eur"], color=NEUTRAL, width=0.7,
           label="Tilgung")
    ax.yaxis.set_major_formatter(fmt)
    ax.set_ylabel(einheit)
    ax.set_xlabel("Betriebsjahr")
    ax.legend(loc="upper right")
    return _fig_zu_bild(fig)


def _chart_strukturen(ek: float, fk: float, capex_posten: dict[str, float]) -> Image:
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(_CHART_B_CM / 2.54, 5.6 / 2.54)
    )
    ax1.pie(
        [max(ek, 0), max(fk, 0)], labels=["Eigenkapital", "Fremdkapital"],
        colors=[INK, NEUTRAL], autopct=lambda p: f"{_de(p, 0)} %",
        textprops={"fontsize": 8, "color": INK},
        wedgeprops={"width": 0.42, "edgecolor": "white"}, startangle=90,
    )
    ax1.set_title("Kapitalstruktur", color=INK)
    aktiv = {k: v for k, v in capex_posten.items() if v > 0}
    palette = (SERIES + [MUTED, "#6C3483", "#B9770E"])[: len(aktiv)]
    ax2.pie(
        list(aktiv.values()), labels=list(aktiv.keys()), colors=palette,
        autopct=lambda p: f"{_de(p, 0)} %" if p >= 4 else "",
        textprops={"fontsize": 7.5, "color": INK},
        wedgeprops={"width": 0.42, "edgecolor": "white"}, startangle=90,
    )
    ax2.set_title("Investitionsstruktur", color=INK)
    return _fig_zu_bild(fig)


def _chart_npv_kurve(npv_curve: pd.DataFrame, irr: float | None) -> Image:
    fig, ax = _fig(5.8)
    fmt, einheit = _eur_achse(npv_curve["npv_eur"].abs().max())
    ax.plot(npv_curve["diskontsatz_pct"] * 100, npv_curve["npv_eur"],
            color=INK, linewidth=1.8)
    ax.axhline(0, color=MUTED, linewidth=0.8, linestyle=":")
    if irr is not None and 0 <= irr <= 0.10:
        ax.axvline(irr * 100, color=BRAND, linewidth=1.1, linestyle="--")
        ax.annotate(f"IRR {fmt_pct(irr)}", (irr * 100, 0),
                    textcoords="offset points", xytext=(6, 8), color=BRAND,
                    fontsize=8)
    ax.yaxis.set_major_formatter(fmt)
    ax.set_xlabel("Diskontsatz (%)")
    ax.set_ylabel(f"NPV ({einheit})")
    return _fig_zu_bild(fig)


def _chart_tornado(tornado_df: pd.DataFrame) -> Image:
    basis = (tornado_df["irr_basis"].iloc[0] or 0) * 100
    fig, ax = _fig(6.4)
    y = np.arange(len(tornado_df))
    for i, (_, zeile) in enumerate(tornado_df.iterrows()):
        runter = (zeile["irr_runter"] or 0) * 100
        rauf = (zeile["irr_rauf"] or 0) * 100
        ax.barh(i, runter - basis, left=basis, color=NEGATIVE, height=0.55)
        ax.barh(i, rauf - basis, left=basis, color=POSITIVE, height=0.55)
    ax.axvline(basis, color=INK, linewidth=1.4)
    ax.set_yticks(y)
    ax.set_yticklabels(tornado_df["name"], fontsize=8)
    ax.set_xlabel("EK-Rendite (%) bei Variation des Treibers um ±10 %")
    ax.annotate(f"Basis {_de(basis, 2)} %", (basis, len(tornado_df) - 0.2),
                textcoords="offset points", xytext=(4, 4), color=INK,
                fontsize=8, fontweight="bold")
    return _fig_zu_bild(fig)


def _chart_eag_varianten(sens_df: pd.DataFrame) -> Image:
    fig, ax = _fig(5.6)
    irr = [(v or 0) * 100 for v in sens_df["equity_irr"]]
    farben = [BRAND if v == "Basis" else NEUTRAL for v in sens_df["variante"]]
    ax.bar(sens_df["variante"], irr, color=farben, width=0.6)
    for i, wert in enumerate(irr):
        ax.annotate(f"{_de(wert, 2)} %", (i, wert), textcoords="offset points",
                    xytext=(0, 3), ha="center", fontsize=7.5, color=INK)
    ax.set_ylabel("EK-Rendite (%)")
    ax.set_xlabel("EAG-Zuschlagswert-Variante")
    return _fig_zu_bild(fig)


def _chart_mc_histogramm(mc: MonteCarloResult, p10: float, p50: float,
                         p90: float) -> Image:
    fig, ax = _fig(5.8)
    ax.hist(mc.irr_gueltig * 100, bins=32, color=NEUTRAL,
            edgecolor="white", linewidth=0.4)
    for wert, name, farbe in [(p10, "P10", NEGATIVE), (p50, "P50", INK),
                              (p90, "P90", POSITIVE)]:
        ax.axvline(wert * 100, color=farbe, linewidth=1.1, linestyle="--")
        ax.annotate(f"{name} {fmt_pct(wert)}", (wert * 100, ax.get_ylim()[1]),
                    textcoords="offset points", xytext=(2, -10), color=farbe,
                    fontsize=7.5)
    ax.set_xlabel("EK-Rendite (%)")
    ax.set_ylabel("Anzahl Läufe")
    return _fig_zu_bild(fig)


def _chart_mc_faecher(mc: MonteCarloResult) -> Image:
    fig, ax = _fig()
    fmt, einheit = _eur_achse(np.abs(mc.kum_p90).max())
    ax.fill_between(mc.jahre, mc.kum_p10, mc.kum_p90, color=INK, alpha=0.10,
                    label="P10–P90")
    ax.fill_between(mc.jahre, mc.kum_p25, mc.kum_p75, color=INK, alpha=0.20,
                    label="P25–P75")
    ax.plot(mc.jahre, mc.kum_p50, color=INK, linewidth=1.8, label="Median")
    ax.axhline(0, color=MUTED, linewidth=0.8, linestyle=":")
    ax.yaxis.set_major_formatter(fmt)
    ax.set_ylabel(f"Kumulierter Equity-Cashflow ({einheit})")
    ax.set_xlabel("Jahr")
    ax.legend(loc="upper left")
    return _fig_zu_bild(fig)


def _chart_szenarien(vergleich: SzenarioVergleich) -> Image:
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(_CHART_B_CM / 2.54, 6.0 / 2.54),
        gridspec_kw={"width_ratios": [1, 1.5]},
    )
    kz = vergleich.kennzahlen
    irr = [(v or 0) * 100 for v in kz["equity_irr"]]
    ax1.bar(range(len(kz)), irr, color=SERIES[: len(kz)], width=0.6)
    ax1.set_xticks(range(len(kz)))
    ax1.set_xticklabels(kz["szenario"], rotation=30, ha="right", fontsize=7)
    ax1.set_ylabel("EK-Rendite (%)")
    for i, wert in enumerate(irr):
        ax1.annotate(f"{_de(wert, 1)}", (i, wert), textcoords="offset points",
                     xytext=(0, 2), ha="center", fontsize=7, color=INK)
    ax1.grid(axis="x", visible=False)
    kum = vergleich.kum_cashflows
    fmt, einheit = _eur_achse(kum.drop(columns="jahr").abs().max().max())
    for i, spalte in enumerate([c for c in kum.columns if c != "jahr"]):
        ax2.plot(kum["jahr"], kum[spalte], color=SERIES[i % len(SERIES)],
                 linewidth=1.4, label=spalte)
    ax2.axhline(0, color=MUTED, linewidth=0.8, linestyle=":")
    ax2.yaxis.set_major_formatter(fmt)
    ax2.set_ylabel(f"Kum. Equity-CF ({einheit})")
    ax2.set_xlabel("Jahr")
    ax2.legend(fontsize=6.5, loc="upper left")
    for a in (ax1, ax2):
        for seite in ("top", "right"):
            a.spines[seite].set_visible(False)
    return _fig_zu_bild(fig)


def _formel(latex: str, fontsize: float = 11.5) -> Image:
    """Rendert eine mathematische Formel (Matplotlib-Mathtext, LaTeX-
    Syntax) als zentriertes Bild in Textfarbe."""
    fig = plt.figure(figsize=(6.6, 0.6))
    fig.patch.set_alpha(0.0)
    fig.text(0.5, 0.5, latex, ha="center", va="center",
             fontsize=fontsize, color=INK)
    puffer = io.BytesIO()
    fig.savefig(puffer, format="png", dpi=220, bbox_inches="tight",
                pad_inches=0.05, transparent=True)
    plt.close(fig)
    puffer.seek(0)
    from reportlab.lib.utils import ImageReader

    b_px, h_px = ImageReader(puffer).getSize()
    puffer.seek(0)
    b_pt = min(b_px * 72.0 / 220.0, _INHALT_B * 0.94)
    bild = Image(puffer, width=b_pt, height=b_pt * h_px / b_px)
    bild.hAlign = "CENTER"
    return bild


def _chart_auktion_fits(modell) -> Image:
    """Gefittete Gebotsverteilungen aller historischen Runden
    (Farbverlauf alt -> neu; unterzeichnete Runden gestrichelt)."""
    def _mix(c1: str, c2: str, t: float) -> str:
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(
            f"{round(a[i] + (b[i] - a[i]) * t):02x}" for i in range(3)
        )

    fits = sorted(modell.fits, key=lambda f: f.ausschreibung.datum)
    familie = modell.familie
    fig, ax = _fig(6.8)
    for i, f in enumerate(fits):
        cap = f.ausschreibung.preisobergrenze_ct
        x = np.linspace(0.02 * cap, cap * (1 - 1e-4), 300)
        d = familie.dist(f.mu_rel, f.kappa, cap)
        farbe = _mix(NEUTRAL, BRAND, i / max(len(fits) - 1, 1))
        ax.plot(
            x, d.pdf(x), color=farbe, linewidth=1.4,
            linestyle=":" if f.ausschreibung.unterzeichnet else "-",
            label=f.ausschreibung.datum.strftime("%m/%y")
            + ("*" if f.ausschreibung.unterzeichnet else ""),
        )
    ax.set_xlabel("Gebotswert (ct/kWh)")
    ax.set_ylabel("Wahrscheinlichkeitsdichte")
    ax.legend(loc="upper left", ncol=3, fontsize=6.2,
              title="* unterzeichnet", title_fontsize=6.2)
    return _fig_zu_bild(fig)


def _chart_auktion_kurve(prognose, projekt_wert_ct: float) -> Image:
    """Wert-Wahrscheinlichkeits-Kurve der Prognose (Pendant zum Tool):
    P(Zuschlag | Gebot) mit Einordnung des Projektwerts."""
    fig, ax = _fig(6.2)
    x = np.linspace(0.4 * prognose.preisobergrenze_ct,
                    prognose.preisobergrenze_ct, 250)
    y = [prognose.zuschlagswahrscheinlichkeit(b) * 100 for b in x]
    ax.plot(x, y, color=INK, linewidth=1.8)
    p_projekt = prognose.zuschlagswahrscheinlichkeit(projekt_wert_ct) * 100
    ax.axvline(projekt_wert_ct, color=MUTED, linewidth=0.9, linestyle=":")
    ax.axhline(p_projekt, color=MUTED, linewidth=0.9, linestyle=":")
    ax.plot([projekt_wert_ct], [p_projekt], "o", color=BRAND, markersize=6,
            markeredgecolor="white", markeredgewidth=1.2)
    ax.annotate(f"Projektwert: {p_projekt:,.0f} %",
                (projekt_wert_ct, p_projekt), textcoords="offset points",
                xytext=(8, 8), fontsize=7.5, color=BRAND)
    ax.set_xlabel("Eigenes Gebot (ct/kWh)")
    ax.set_ylabel("Zuschlagswahrscheinlichkeit (%)")
    ax.set_ylim(0, 104)
    return _fig_zu_bild(fig)


def _chart_auktion_historie(df) -> Image:
    fig, ax = _fig(6.4)
    x = pd.to_datetime(df["datum"])
    ax.plot(x, df["preisobergrenze_ct"], color=BRAND, linewidth=1.2,
            linestyle="--", label="Preisobergrenze")
    ax.plot(x, df["zuschlag_max_ct"], color=INK, linewidth=1.8, marker="o",
            markersize=3, label="Höchster Zuschlag")
    ax.plot(x, df["zuschlag_mittel_ct"], color=INK_SOFT, linewidth=1.6,
            marker="o", markersize=3, label="Ø Zuschlag (gewichtet)")
    ax.plot(x, df["zuschlag_min_ct"], color=NEUTRAL, linewidth=1.2,
            marker="o", markersize=3, label="Niedrigster Zuschlag")
    wett = df[~df["unterzeichnet"]]
    if not wett.empty:
        ax.axvspan(pd.to_datetime(wett["datum"].min()),
                   pd.to_datetime(df["datum"].max()), color=WASH, zorder=0)
        ax.annotate("Wettbewerbsphase", (pd.to_datetime(wett["datum"].min()),
                    ax.get_ylim()[0] + 0.2), fontsize=7.5, color=MUTED)
    ax.set_ylabel("ct/kWh")
    ax.legend(loc="lower left", ncol=2)
    return _fig_zu_bild(fig)


def _chart_auktion_dichte(prognose, projekt_wert_ct: float) -> Image:
    fig, ax = _fig(6.2)
    ax.plot(prognose.dichte_x, prognose.dichte_y, color=MUTED, linewidth=1.2,
            linestyle=":", label="Alle Gebote")
    ax.plot(prognose.dichte_x, prognose.dichte_zuschlag_y, color=INK,
            linewidth=1.8, label="Zuschlagswerte")
    ax.fill_between(prognose.dichte_x, prognose.dichte_zuschlag_y,
                    color=INK, alpha=0.12)
    if len(prognose.pm_sample) > 1:
        ax.axvspan(float(np.percentile(prognose.pm_sample, 10)),
                   float(np.percentile(prognose.pm_sample, 90)),
                   color=NEUTRAL, alpha=0.18)
    ax.axvline(prognose.preisobergrenze_ct, color=BRAND, linewidth=1.2,
               linestyle="--")
    ax.annotate("Obergrenze", (prognose.preisobergrenze_ct, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(-4, -10), ha="right",
                color=BRAND, fontsize=7.5)
    ax.axvline(projekt_wert_ct, color=POSITIVE, linewidth=1.4)
    ax.annotate("Projektwert", (projekt_wert_ct, ax.get_ylim()[1] * 0.85),
                textcoords="offset points", xytext=(4, 0), color=POSITIVE,
                fontsize=7.5)
    ax.set_xlabel("Gebotswert (ct/kWh)")
    ax.set_ylabel("Wahrscheinlichkeitsdichte")
    ax.legend(loc="upper left")
    return _fig_zu_bild(fig)


# ---------------------------------------------------------------------------
# Dokumentgeruest (Deckblatt, Kopf-/Fusszeile, Inhaltsverzeichnis)
# ---------------------------------------------------------------------------

_STYLE_H1 = ParagraphStyle(
    "BerichtH1", fontName="Helvetica-Bold", fontSize=15, leading=19,
    textColor=colors.HexColor(INK), spaceBefore=6, spaceAfter=10,
)
_STYLE_H2 = ParagraphStyle(
    "BerichtH2", fontName="Helvetica-Bold", fontSize=11, leading=14,
    textColor=colors.HexColor(INK), spaceBefore=12, spaceAfter=5,
)
_STYLE_TEXT = ParagraphStyle(
    "BerichtText", fontName="Helvetica", fontSize=9, leading=13.5,
    textColor=colors.HexColor("#20302C"), spaceAfter=6,
)
_STYLE_CAPTION = ParagraphStyle(
    "BerichtCaption", fontName="Helvetica-Oblique", fontSize=7.8, leading=10.5,
    textColor=colors.HexColor(MUTED), spaceBefore=2, spaceAfter=10,
)
_STYLE_TOC = ParagraphStyle(
    "TocEintrag", fontName="Helvetica", fontSize=10, leading=16,
    textColor=colors.HexColor(INK),
)


class _Kapitel(Paragraph):
    """H1 mit Nummer, Markenlinie und Registrierung im Inhaltsverzeichnis."""

    def __init__(self, nummer: str, titel: str):
        super().__init__(f"{nummer}&nbsp;&nbsp;&nbsp;{titel}", _STYLE_H1)
        self._toc_text = f"{nummer}   {titel}"

    def draw(self):
        super().draw()
        self.canv.setStrokeColor(colors.HexColor(BRAND))
        self.canv.setLineWidth(1.6)
        self.canv.line(0, -3, 46, -3)
        self.canv.setStrokeColor(colors.HexColor(LINE))
        self.canv.setLineWidth(0.8)
        self.canv.line(46, -3, self.width, -3)


class _BerichtDoc(BaseDocTemplate):
    def __init__(self, puffer, projekt_name: str, **kw):
        super().__init__(puffer, pagesize=A4, leftMargin=_RAND_L,
                         rightMargin=_RAND_R, topMargin=_RAND_O,
                         bottomMargin=_RAND_U, **kw)
        self._projekt_name = projekt_name
        frame = Frame(_RAND_L, _RAND_U, _INHALT_B,
                      _SEITE_H - _RAND_O - _RAND_U, id="inhalt")
        self.addPageTemplates([
            PageTemplate(id="deckblatt", frames=[frame], onPage=lambda c, d: None),
            PageTemplate(id="inhalt", frames=[frame], onPage=self._kopf_fuss),
        ])

    def _kopf_fuss(self, canv, doc):
        canv.saveState()
        y = _SEITE_H - 1.35 * cm
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(colors.HexColor(MUTED))
        canv.drawString(_RAND_L, y, "Wirtschaftlichkeitsanalyse")
        canv.drawRightString(_SEITE_B - _RAND_R, y, self._projekt_name)
        canv.setStrokeColor(colors.HexColor(BRAND))
        canv.setLineWidth(1.2)
        canv.line(_RAND_L, y - 4, _RAND_L + 46, y - 4)
        canv.setStrokeColor(colors.HexColor(LINE))
        canv.setLineWidth(0.7)
        canv.line(_RAND_L + 46, y - 4, _SEITE_B - _RAND_R, y - 4)

        canv.setStrokeColor(colors.HexColor(LINE))
        canv.line(_RAND_L, 1.35 * cm, _SEITE_B - _RAND_R, 1.35 * cm)
        canv.setFont("Helvetica", 7.5)
        canv.drawString(_RAND_L, 1.0 * cm, "TEA PV-Projektbewertung")
        canv.drawCentredString(_SEITE_B / 2, 1.0 * cm,
                               date.today().strftime("%d.%m.%Y"))
        canv.drawRightString(_SEITE_B - _RAND_R, 1.0 * cm,
                             f"Seite {doc.page}")
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, _Kapitel):
            self.notify("TOCEntry", (0, flowable._toc_text, self.page))


# ---------------------------------------------------------------------------
# Tabellenbausteine
# ---------------------------------------------------------------------------


def _tabelle(daten: list[list[str]], breiten: list[float] | None = None,
             kopf: bool = True, schrift: float = 8.0,
             zahlen_ab_spalte: int = 1) -> Table:
    tabelle = Table(daten, colWidths=breiten, repeatRows=1 if kopf else 0)
    stil = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), schrift),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#20302C")),
        ("ALIGN", (zahlen_ab_spalte, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.HexColor(INK)),
        ("ROWBACKGROUNDS", (0, 1 if kopf else 0), (-1, -1),
         [colors.white, colors.HexColor(WASH)]),
    ]
    if kopf:
        stil += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor(INK)),
        ]
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def _kennzahlen_kacheln(paare: list[tuple[str, str]]) -> Table:
    """Fuenf KPI-'Kacheln' in einer Reihe - Pendant zur KPI-Leiste der App."""
    labels = [p[0] for p in paare]
    werte = [p[1] for p in paare]
    breite = _INHALT_B / len(paare)
    tabelle = Table([labels, werte], colWidths=[breite] * len(paare))
    tabelle.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(MUTED)),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 12.5),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor(INK)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(WASH)),
        ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(BRAND)),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.HexColor(LINE)),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    return tabelle


# ---------------------------------------------------------------------------
# Berichtsdaten und Hauptfunktion
# ---------------------------------------------------------------------------


@dataclass
class ReportInputs:
    """Alle vorberechneten Bausteine des Berichts (die App liefert sie aus
    ihren gecachten Services, Tests direkt aus der Engine)."""

    project: PVProject
    global_assumptions: GlobalAssumptions
    result: object                     # engine.ValuationResult
    tornado: pd.DataFrame
    eag_sensitivitaet: pd.DataFrame
    monte_carlo: MonteCarloResult
    szenarien: SzenarioVergleich
    break_even_ct: float | None
    lcoe_ct: float | None
    npv_eur: float
    diskontsatz_pct: float             # fuer NPV/LCOE/MC-NPV
    ziel_irr_pct: float = 0.08
    logo_path: Path | None = None
    # Optionales EAG-Ausschreibungsmodell: dict mit "df" (Historie),
    # "prognose" (GebotsPrognose, Momentum-Modus), "formel_zeile" (Text
    # mit eingesetzten Stuetzstellen). None -> Kapitel entfaellt.
    auktion: dict | None = None


def build_pdf_report(inputs: ReportInputs) -> bytes:
    p = inputs.project
    ea = inputs.result.effective_assumptions
    df = inputs.result.cashflow.data
    kpis = inputs.result.kpis
    heute = date.today().strftime("%d.%m.%Y")
    typ = "Agri-PV" if p.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"

    puffer = io.BytesIO()
    doc = _BerichtDoc(puffer, projekt_name=p.name, title=f"Wirtschaftlichkeitsanalyse {p.name}",
                      author="TEA PV-Projektbewertung")
    story: list = []

    # ------------------------------------------------------------------ Deckblatt
    story.append(Spacer(1, 1.2 * cm))
    if inputs.logo_path and Path(inputs.logo_path).exists():
        from PIL import Image as PILImage

        with PILImage.open(inputs.logo_path) as logo:
            seiten_verhaeltnis = logo.height / logo.width
        logo_b = 4.6 * cm
        bild = Image(str(inputs.logo_path), width=logo_b,
                     height=logo_b * seiten_verhaeltnis)
        bild.hAlign = "LEFT"
        story.append(bild)
    story.append(Spacer(1, 2.4 * cm))
    story.append(Paragraph(
        "Wirtschaftlichkeitsanalyse",
        ParagraphStyle("DeckTitel", fontName="Helvetica-Bold", fontSize=26,
                       leading=31, textColor=colors.HexColor(INK)),
    ))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        p.name,
        ParagraphStyle("DeckProjekt", fontName="Helvetica-Bold", fontSize=17,
                       leading=22, textColor=colors.HexColor(BRAND)),
    ))
    story.append(Spacer(1, 0.15 * cm))
    linie = Table([[""]], colWidths=[_INHALT_B], rowHeights=[3])
    linie.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 2.2, colors.HexColor(BRAND)),
    ]))
    story.append(linie)
    story.append(Spacer(1, 1.0 * cm))

    steckbrief = [
        ["Anlagentyp", typ, "Marktpreisszenario", ea.marktpreisszenario_name],
        ["Nennleistung", fmt_kwp(p.nennleistung_kwp), "EAG-Zuschlagswert",
         fmt_ct_kwh(p.eag_zuschlagswert_ct_kwh)
         + (f" (effektiv {fmt_ct_kwh(p.eag_zuschlagswert_effektiv_ct_kwh)})"
            if p.anlagentyp == AnlagenTyp.KONVENTIONELL else "")],
        ["Inbetriebnahme", f"{p.inbetriebnahme_monat:02d}/{p.inbetriebnahme_jahr}",
         "Betrachtungszeitraum", f"{ea.betriebsdauer_jahre} Betriebsjahre"],
        ["Spezifischer Ertrag",
         f"{_de(p.vollbenutzungsstunden_kwh_kwp)} kWh/kWp",
         "Regel negative Preise",
         "6-Stunden-Regel (Österreich)"
         if ea.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN
         else "1-Stunden-Regel (Deutschland)"],
    ]
    deck_tabelle = Table(steckbrief, colWidths=[3.6 * cm, 4.6 * cm, 4.2 * cm,
                                                _INHALT_B - 12.4 * cm])
    deck_tabelle.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor(MUTED)),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(INK)),
        ("TEXTCOLOR", (3, 0), (3, -1), colors.HexColor(INK)),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    story.append(deck_tabelle)
    story.append(Spacer(1, 7.2 * cm))
    story.append(Paragraph(
        f"Stand: {heute} · Erstellt mit TEA PV-Projektbewertung · "
        f"Berechnungsgrundlage: EAG-Marktprämienmodell (gleitende "
        f"Marktprämie), nominale Cashflow-Rechnung",
        _STYLE_CAPTION,
    ))
    story.append(Paragraph(
        "Indikative Modellrechnung auf Basis der in Annex A und B "
        "dokumentierten Annahmen. Diese Unterlage dient der internen "
        "Entscheidungsvorbereitung; sie ist kein Angebot und keine Anlage-, "
        "Steuer- oder Rechtsberatung. Die Ergebnisse hängen wesentlich von "
        "den getroffenen Annahmen ab, insbesondere von Marktpreisprognosen "
        "und regulatorischen Rahmenbedingungen.",
        _STYLE_CAPTION,
    ))
    story.append(NextPageTemplate("inhalt"))
    story.append(PageBreak())

    # ---------------------------------------------------------- Inhaltsverzeichnis
    story.append(Paragraph("Inhalt", _STYLE_H1))
    toc = TableOfContents()
    toc.levelStyles = [_STYLE_TOC]
    story.append(toc)
    story.append(PageBreak())

    # ------------------------------------------------------- Management Summary
    story.append(_Kapitel("1", txt("bericht.kapitel_1_titel")))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_kennzahlen_kacheln([
        ("EK-RENDITE (IRR)", fmt_pct(kpis.equity_irr)),
        (f"NPV BEI {_de(inputs.diskontsatz_pct * 100, 1)} %",
         fmt_eur(inputs.npv_eur)),
        ("MIN. DSCR", fmt_dscr(kpis.dscr_min)),
        ("CAPEX", fmt_eur(kpis.capex_total_eur)),
        ("LCOE", fmt_ct_kwh(inputs.lcoe_ct) if inputs.lcoe_ct is not None
         else "n/a"),
    ]))
    story.append(Spacer(1, 0.35 * cm))

    betrieb = df[df["jahr"] >= 1]
    erloes_gesamt = float(betrieb["erloes_eur"].sum())
    praemie_gesamt = float(betrieb["erloes_praemie_eur"].sum())
    praemien_anteil = praemie_gesamt / erloes_gesamt if erloes_gesamt else 0.0
    irr_delta = (kpis.equity_irr or 0) - inputs.ziel_irr_pct
    dscr_ok = kpis.dscr_min is not None and kpis.dscr_min >= 1.0
    mc = inputs.monte_carlo
    prob_ziel = mc.wahrscheinlichkeit_irr_ueber(inputs.ziel_irr_pct)

    summary_text = (
        f"Das Projekt {p.name} ({typ}, {fmt_kwp(p.nennleistung_kwp)}, "
        f"Inbetriebnahme {p.inbetriebnahme_monat:02d}/{p.inbetriebnahme_jahr}) "
        f"erreicht auf Basis des Marktpreisszenarios "
        f"„{ea.marktpreisszenario_name}“ eine Eigenkapitalrendite von "
        f"<b>{fmt_pct(kpis.equity_irr)}</b> und liegt damit "
        f"{_de(abs(irr_delta) * 100, 2)} Prozentpunkte "
        f"{'über' if irr_delta >= 0 else 'unter'} der Zielrendite von "
        f"{_de(inputs.ziel_irr_pct * 100, 1)} %. Der Kapitalwert bei einem "
        f"Diskontsatz von {_de(inputs.diskontsatz_pct * 100, 1)} % beträgt "
        f"{fmt_eur(inputs.npv_eur)}. "
        f"Der Schuldendienst ist über die gesamte Kreditlaufzeit "
        f"{'gedeckt (min. DSCR ' + fmt_dscr(kpis.dscr_min) + ')' if dscr_ok else 'NICHT durchgängig gedeckt (min. DSCR ' + fmt_dscr(kpis.dscr_min) + ')'}. "
        f"Über die Betriebsdauer stammen {fmt_pct(praemien_anteil, 1)} der "
        f"Erlöse aus der EAG-Marktprämie. In der Monte-Carlo-Simulation "
        f"({mc.n_laeufe} Läufe) wird die Zielrendite in "
        f"{fmt_pct(prob_ziel, 0)} der Läufe erreicht."
    )
    story.append(Paragraph(summary_text, _STYLE_TEXT))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph(txt("bericht.abschnitt_cashflow_vermoegen"), _STYLE_H2))
    story.append(_chart_gesamt_cashflow(df))
    story.append(Paragraph(
        "Abb. 1: Jährlicher Gesamt-Cashflow (Balken) und kumulierter "
        "Equity-Cashflow (Linie). Jahr 0 = Investitionszeitpunkt.",
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # ------------------------------------------------------------ Ergebnisrechnung
    story.append(_Kapitel("2", txt("bericht.kapitel_2_titel")))
    story.append(Paragraph(txt("bericht.abschnitt_wertbruecke"), _STYLE_H2))
    story.append(_chart_wertbruecke(df))
    story.append(Paragraph(
        "Abb. 2: Von den Umsatzerlösen der gesamten Betriebsdauer über "
        "Betriebskosten, Zinsen, Steuern und Finanzierung zum kumulierten "
        "Equity-Cashflow.",
        _STYLE_CAPTION,
    ))

    story.append(Paragraph(txt("bericht.abschnitt_cashflow_uebersicht"), _STYLE_H2))
    zeilen = [["Jahr", "Erlöse", "Betriebs-\nkosten", "Zinsen", "Steuer",
               "CF gesamt", "CF kumuliert"]]
    for _, r in df.iterrows():
        zeilen.append([
            str(int(r["jahr"])),
            _de(r["erloes_eur"]), _de(r["opex_gesamt_eur"]),
            _de(r["zinsen_eur"]), _de(r["steuer_eur"]),
            _de(r["cf_gesamt_eur"]), _de(r["cf_kumuliert_eur"]),
        ])
    zeilen.append(["Σ", _de(df["erloes_eur"].sum()),
                   _de(df["opex_gesamt_eur"].sum()),
                   _de(df["zinsen_eur"].sum()), _de(df["steuer_eur"].sum()),
                   _de(df["cf_gesamt_eur"].sum()), "—"])
    story.append(_tabelle(zeilen, breiten=[1.4 * cm] + [(_INHALT_B - 1.4 * cm) / 6] * 6,
                          schrift=7.2))
    story.append(Paragraph(
        "Tab. 1: Alle Beträge in €. Vollständige Zeitreihe inkl. AfA, "
        "Verlustvortrag und Tilgung über den Excel-Export der App.",
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # -------------------------------------------------------------------- Erloese
    story.append(_Kapitel("3", txt("bericht.kapitel_3_titel")))
    story.append(Paragraph(txt("bericht.abschnitt_verguetung_marktwert"), _STYLE_H2))
    story.append(_chart_verguetung(df, ea.eag_zuschlagswert_effektiv_ct_kwh,
                                   ea.eag_foerderdauer_jahre))
    story.append(Paragraph(
        "Abb. 3: Gleitende Marktprämie nach EAG: Vergütet wird das Maximum "
        "aus Marktwert und (nominal fixem) EAG-Zuschlagswert; die Fläche "
        "zwischen den Kurven ist die Marktprämie. Nach dem Förderende trägt "
        "der Markt allein.",
        _STYLE_CAPTION,
    ))
    story.append(Paragraph(txt("bericht.abschnitt_markterloes_praemie"), _STYLE_H2))
    story.append(_chart_erloes_split(df))
    story.append(Paragraph(
        f"Abb. 4: Aufteilung der Erlöse. Über die Gesamtlaufzeit stammen "
        f"{fmt_pct(praemien_anteil, 1)} der Erlöse "
        f"({fmt_eur(praemie_gesamt)}) aus der Marktprämie.",
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # ---------------------------------------------------------------- Finanzierung
    story.append(_Kapitel("4", txt("bericht.kapitel_4_titel")))
    fremdkapital = ea.capex_total_eur * (1 - ea.eigenkapitalquote_pct)
    eigenkapital = ea.capex_total_eur * ea.eigenkapitalquote_pct
    story.append(Paragraph(
        f"Finanzierungsstruktur: {fmt_pct(ea.eigenkapitalquote_pct, 0)} "
        f"Eigenkapital ({fmt_eur(eigenkapital)}), "
        f"{fmt_pct(1 - ea.eigenkapitalquote_pct, 0)} Fremdkapital "
        f"({fmt_eur(fremdkapital)}) zu {fmt_pct(ea.fremdkapitalzins_pct)} über "
        f"{ea.kreditlaufzeit_jahre} Jahre ({ea.tilgungsart.value}"
        f"{', tilgungsfreies Anlaufjahr' if ea.tilgungsfreies_anlaufjahr else ''}).",
        _STYLE_TEXT,
    ))
    if not df.dropna(subset=["dscr"]).empty:
        story.append(Paragraph(txt("bericht.abschnitt_dscr"), _STYLE_H2))
        story.append(_chart_dscr(df))
        story.append(Paragraph(
            f"Abb. 5: DSCR je Betriebsjahr der Kreditlaufzeit; minimaler Wert "
            f"{fmt_dscr(kpis.dscr_min)}.",
            _STYLE_CAPTION,
        ))
        story.append(Paragraph(txt("bericht.abschnitt_schuldenprofil"), _STYLE_H2))
        story.append(_chart_schuldenprofil(df, fremdkapital))
        story.append(Paragraph(
            "Abb. 6: Restschuld (Fläche) sowie Zinsen und Tilgung "
            "(Schuldendienst) über die Kreditlaufzeit.",
            _STYLE_CAPTION,
        ))
    capex = p.capex
    story.append(_chart_strukturen(eigenkapital, fremdkapital, {
        "EPC": capex.epc_eur, "Netzanschluss": capex.netzanschluss_eur,
        "Trasse": capex.trasse_eur, "Widmung": capex.widmung_eur,
        "Genehmigung": capex.genehmigung_eur,
        "Sonstige": capex.sonstige_extern_eur, "AGM": capex.agm_eur,
        "M&A": capex.m_and_a_eur, "Pönale/Puffer": capex.poenale_puffer_eur,
    }))
    story.append(Paragraph("Abb. 7: Kapital- und Investitionsstruktur.",
                           _STYLE_CAPTION))
    story.append(Paragraph(txt("bericht.abschnitt_npv_diskontsatz"), _STYLE_H2))
    story.append(_chart_npv_kurve(inputs.result.npv_curve, kpis.equity_irr))
    story.append(Paragraph(
        "Abb. 8: NPV-Kurve; die Nullstelle entspricht per Definition der "
        "EK-Rendite (IRR).",
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # ---------------------------------------------------------------- Sensitivitaet
    story.append(_Kapitel("5", txt("bericht.kapitel_5_titel")))
    story.append(Paragraph(txt("bericht.abschnitt_tornado"), _STYLE_H2))
    story.append(_chart_tornado(inputs.tornado))
    story.append(Paragraph(
        "Abb. 9: Wirkung der Einzelvariation jedes Werttreibers um ±10 % "
        "auf die EK-Rendite (alle übrigen Annahmen konstant), sortiert nach "
        "Spannweite. Grün: Verbesserung, Rot: Verschlechterung gegenüber "
        "der Basis.",
        _STYLE_CAPTION,
    ))
    story.append(Paragraph(txt("bericht.abschnitt_eag_varianten"), _STYLE_H2))
    story.append(_chart_eag_varianten(inputs.eag_sensitivitaet))
    if inputs.break_even_ct is None:
        be_text = (
            f"Die Zielrendite von {_de(inputs.ziel_irr_pct * 100, 1)} % ist "
            f"im untersuchten Gebotsbereich (bis 15 ct/kWh) nicht erreichbar."
        )
    elif inputs.break_even_ct <= 0.5:
        be_text = (
            f"Die Zielrendite von {_de(inputs.ziel_irr_pct * 100, 1)} % wird "
            f"bereits ohne nennenswerte Prämie erreicht – der Marktwert "
            f"trägt das Projekt allein."
        )
    else:
        puffer_ct = p.eag_zuschlagswert_ct_kwh - inputs.break_even_ct
        be_text = (
            f"Break-even-Gebot: Für eine Zielrendite von "
            f"{_de(inputs.ziel_irr_pct * 100, 1)} % ist ein anzulegender "
            f"Wert von mindestens <b>{fmt_ct_kwh(inputs.break_even_ct)}</b> "
            f"erforderlich. Gegenüber dem angesetzten Zuschlagswert von "
            f"{fmt_ct_kwh(p.eag_zuschlagswert_ct_kwh)} besteht damit ein "
            f"{'Puffer' if puffer_ct >= 0 else 'Fehlbetrag'} von "
            f"{fmt_ct_kwh(abs(puffer_ct))}."
        )
    story.append(Paragraph(
        "Abb. 10: EK-Rendite bei Variation des EAG-Zuschlagswerts um "
        "±5 % / ±10 %. " + be_text,
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # ------------------------------------------------------------------- Risiko
    story.append(_Kapitel("6", txt("bericht.kapitel_6_titel")))
    irr_gueltig = mc.irr_gueltig
    p10, p50, p90 = (float(np.percentile(irr_gueltig, q)) for q in (10, 50, 90))
    sigma_namen = {
        "produktion": "Spezifischer Ertrag", "marktwert": "Marktwert-Niveau",
        "capex": "Investitionskosten", "opex": "Betriebskosten",
    }
    sigma_text = ", ".join(
        f"{sigma_namen[k]} ±{_de(s * 100, 0)} %"
        for k, s in MC_STANDARD_SIGMAS.items()
    )
    story.append(Paragraph(
        f"Simultane Zufallsvariation der wesentlichen Werttreiber über "
        f"{mc.n_laeufe} vollständige Bewertungsläufe "
        f"(Normalverteilung um die Basisannahme; Standardabweichungen: "
        f"{sigma_text}; fester Startwert für Reproduzierbarkeit).",
        _STYLE_TEXT,
    ))
    story.append(_kennzahlen_kacheln([
        ("P10 (KONSERVATIV)", fmt_pct(p10)),
        ("P50 (MEDIAN)", fmt_pct(p50)),
        ("P90 (OPTIMISTISCH)", fmt_pct(p90)),
        (f"P(IRR ≥ {_de(inputs.ziel_irr_pct * 100, 1)} %)",
         fmt_pct(prob_ziel, 0)),
        (f"NPV-MEDIAN ({_de(inputs.diskontsatz_pct * 100, 1)} %)",
         fmt_eur(float(np.median(mc.npv)))),
    ]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_chart_mc_histogramm(mc, p10, p50, p90))
    story.append(Paragraph("Abb. 11: Verteilung der EK-Rendite.", _STYLE_CAPTION))
    story.append(_chart_mc_faecher(mc))
    story.append(Paragraph(
        "Abb. 12: Bandbreite des kumulierten Equity-Cashflows (inneres Band "
        "P25–P75, äußeres Band P10–P90, Linie = Median).",
        _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    # ------------------------------------------------------------------ Szenarien
    story.append(_Kapitel("7", txt("bericht.kapitel_7_titel")))
    story.append(Paragraph(
        f"Identisches Projekt, gerechnet über alle hinterlegten "
        f"Marktpreisszenarien; dem Projekt zugewiesen ist "
        f"„{ea.marktpreisszenario_name}“.",
        _STYLE_TEXT,
    ))
    story.append(_chart_szenarien(inputs.szenarien))
    story.append(Paragraph(
        "Abb. 13: EK-Rendite je Szenario (links) und kumulierter "
        "Equity-Cashflow im Zeitverlauf (rechts).",
        _STYLE_CAPTION,
    ))
    kz = inputs.szenarien.kennzahlen
    zeilen = [["Szenario", "EK-Rendite",
               f"NPV bei {_de(inputs.diskontsatz_pct * 100, 1)} %",
               "Erlöse gesamt"]]
    for _, r in kz.iterrows():
        zeilen.append([r["szenario"], fmt_pct(r["equity_irr"]),
                       fmt_eur(r["npv_eur"]), fmt_eur(r["erloes_gesamt_eur"])])
    story.append(_tabelle(zeilen, breiten=[4.5 * cm] +
                          [(_INHALT_B - 4.5 * cm) / 3] * 3))
    story.append(Paragraph("Tab. 2: Kennzahlen je Marktpreisszenario.",
                           _STYLE_CAPTION))
    story.append(PageBreak())

    # ------------------------------------------------------- Ausschreibung
    if inputs.auktion is not None:
        auk = inputs.auktion
        prognose_a = auk["prognose"]
        modell_a = auk.get("modell")
        df_a = auk["df"]
        story.append(_Kapitel("8", txt("bericht.kapitel_8_titel")))

        # --- 8.1 Historie (ausfuehrlich) ---
        story.append(Paragraph(txt("bericht.abschnitt_auktion_historie"), _STYLE_H2))
        n_runden = len(df_a)
        erste = df_a["datum"].min()
        letzte_r = df_a.sort_values("datum").iloc[-1]
        story.append(Paragraph(
            txt("bericht.auktion_historie_intro", n_runden=n_runden,
                erste_datum=erste.strftime("%m/%Y")),
            _STYLE_TEXT,
        ))
        story.append(Paragraph(
            txt("bericht.auktion_historie_unterzeichnet"), _STYLE_TEXT,
        ))
        story.append(Paragraph(
            txt("bericht.auktion_historie_wettbewerb",
                grenzzuschlag_ct=fmt_ct_kwh(letzte_r["zuschlag_max_ct"]),
                letzte_datum=letzte_r["datum"].strftime("%m/%Y")),
            _STYLE_TEXT,
        ))
        story.append(_chart_auktion_historie(df_a))
        story.append(Paragraph(
            txt("bericht.abb_14_caption", n_runden=n_runden), _STYLE_CAPTION,
        ))

        # --- 8.2 Fitting der Verteilungsfunktionen ---
        story.append(Paragraph(
            txt("bericht.abschnitt_auktion_fitting"), _STYLE_H2,
        ))
        r_latent_txt = f"{modell_a.letzte_runde.wettbewerbsquote:.2f}".replace(".", ",")
        story.append(Paragraph(
            txt("bericht.auktion_fitting_intro", wettbewerbsquote=r_latent_txt),
            _STYLE_TEXT,
        ))
        story.append(_chart_auktion_fits(modell_a))
        story.append(Paragraph(txt("bericht.abb_15_caption"), _STYLE_CAPTION))

        # --- 8.3 Modellbeschreibung mit Formeln ---
        story.append(Paragraph(txt("bericht.abschnitt_auktion_modell"), _STYLE_H2))
        story.append(Paragraph(txt("bericht.modell_verteilungsfamilie"), _STYLE_TEXT))
        story.append(_formel(
            r"$f_Y(y)=\dfrac{\beta^{\alpha}}{\Gamma(\alpha)}\,"
            r"y^{-\alpha-1}e^{-\beta/y},\qquad "
            r"f_B(b)=f_Y(P_{max}-b),\quad b\leq P_{max}$"
        ))
        story.append(Paragraph(txt("bericht.modell_kalibrierung"), _STYLE_TEXT))
        story.append(_formel(
            r"$\mathrm{E}[\,b\mid b\leq p_m\,]=\bar{m},"
            r"\qquad F_B(b_{min})=\varepsilon,"
            r"\qquad r=\dfrac{1}{F_B(p_m)}$"
        ))
        story.append(Paragraph(txt("bericht.modell_punktprognose_intro"), _STYLE_TEXT))
        story.append(_formel(
            r"$\Delta^{(k)}_{t}=\Delta^{(k-1)}_{t}-\Delta^{(k-1)}_{t-1},"
            r"\qquad \widehat{\Delta}^{(m)}_{t+1}=\Delta^{(m)}_{t}$"
        ))
        story.append(_formel(
            r"$\widehat{\Delta}^{(k)}_{t+1}=\Delta^{(k)}_{t}"
            r"+\lambda_k\,\widehat{\Delta}^{(k+1)}_{t+1},"
            r"\qquad \hat{x}_{t+1}=x_{t}+\widehat{\Delta}^{(1)}_{t+1}$"
        ))
        story.append(Paragraph(
            txt("bericht.modell_punktprognose_ergebnis",
                formel_zeile=auk.get("formel_zeile", "")),
            _STYLE_TEXT,
        ))
        story.append(Paragraph(txt("bericht.modell_unsicherheit_intro"), _STYLE_TEXT))
        story.append(_formel(
            r"$p_m\sim\left.\mathcal{N}(\hat{p}_m,\,\sigma^2)"
            r"\right|_{(0{,}5;\;P_{max})},\qquad "
            r"\mathrm{P}(\mathrm{Zuschlag}\mid b)=\mathrm{P}(p_m>b),"
            r"\qquad b(z)=Q_{1-z}(p_m)$"
        ))
        story.append(Paragraph(txt("bericht.modell_zuschlagsdichte_intro"), _STYLE_TEXT))
        story.append(_formel(
            r"$f(\,b\mid b\leq p_m\,)"
            r"=\dfrac{f_B(b)\;\mathbf{1}\{b\leq p_m\}}{F_B(p_m)}$"
        ))

        # --- 8.4 Prognose der naechsten Runde (beide Plots) ---
        story.append(Paragraph(txt("bericht.abschnitt_auktion_prognose"), _STYLE_H2))
        story.append(_chart_auktion_dichte(
            prognose_a, p.eag_zuschlagswert_ct_kwh,
        ))
        story.append(Paragraph(
            txt("bericht.abb_16_caption",
                grenzzuschlag_ct=fmt_ct_kwh(prognose_a.grenzzuschlag_zentral_ct),
                projektwert_ct=fmt_ct_kwh(p.eag_zuschlagswert_ct_kwh)),
            _STYLE_CAPTION,
        ))
        story.append(_chart_auktion_kurve(
            prognose_a, p.eag_zuschlagswert_ct_kwh,
        ))
        story.append(Paragraph(
            txt("bericht.abb_17_caption", wahrscheinlichkeit_pct=fmt_pct(
                prognose_a.zuschlagswahrscheinlichkeit(p.eag_zuschlagswert_ct_kwh), 0
            )),
            _STYLE_CAPTION,
        ))
        gebote_zeilen = [[
            txt("bericht.tab_3_spalte_wahrscheinlichkeit"),
            txt("bericht.tab_3_spalte_gebotswert"),
        ]]
        for z in (0.50, 0.60, 0.70, 0.80, 0.90, 0.95):
            gebote_zeilen.append([
                f"{z * 100:.0f} %",
                fmt_ct_kwh(prognose_a.empfohlenes_gebot(z)),
            ])
        story.append(_tabelle(gebote_zeilen,
                              breiten=[_INHALT_B / 2, _INHALT_B / 2]))
        story.append(Paragraph(txt("bericht.tab_3_caption"), _STYLE_CAPTION))
        story.append(PageBreak())

    # ---------------------------------------------------------------- Annex A
    story.append(_Kapitel("A", txt("bericht.kapitel_a_titel")))
    story.append(Paragraph(
        "Vollständig aufgelöster Parametersatz dieser Berechnung "
        "(Projektmaske zusammengeführt mit den Globalen Annahmen).",
        _STYLE_TEXT,
    ))
    ga = inputs.global_assumptions
    dv_relativ = str(ga.direktvermarktung_modus.value) == "relativ_marktwert"
    annahmen = [
        ["Parameter", "Wert", "Parameter", "Wert"],
        ["Nennleistung", fmt_kwp(ea.nennleistung_kwp),
         "Eigenkapitalquote", fmt_pct(ea.eigenkapitalquote_pct, 0)],
        ["Spezifischer Ertrag",
         f"{_de(ea.vollbenutzungsstunden_kwh_kwp)} kWh/kWp",
         "Fremdkapitalzins", fmt_pct(ea.fremdkapitalzins_pct)],
        ["Degradation", f"{fmt_pct(ea.degradation_pct_pa)} p.a.",
         "Kreditlaufzeit",
         f"{ea.kreditlaufzeit_jahre} Jahre ({ea.tilgungsart.value})"],
        ["Sicherheitsabschlag", fmt_pct(ea.sicherheitsabschlag_pct),
         "Tilgungsfreies Anlaufjahr",
         "Ja" if ea.tilgungsfreies_anlaufjahr else "Nein"],
        ["Betrachtungsdauer", f"{ea.betriebsdauer_jahre} Jahre",
         "Steuermodus / Steuersatz",
         f"{ea.tax_modus.value} / {fmt_pct(ea.steuersatz_pct, 0)}"],
        ["EAG-Zuschlag (effektiv)",
         fmt_ct_kwh(ea.eag_zuschlagswert_effektiv_ct_kwh),
         "AfA-Nutzungsdauer", f"{ga.afa_nutzungsdauer_jahre} Jahre"],
        ["Förderdauer", f"{ea.eag_foerderdauer_jahre} Jahre",
         "CAPEX gesamt", fmt_eur(ea.capex_total_eur)],
        ["Inflation Marktwerte",
         f"{fmt_pct(ea.marktpreis_inflation_pct_pa)} p.a. "
         f"ab {ea.marktpreis_inflation_basisjahr}",
         "Gemeindeabgabe", f"{_de(p.gemeindeabgabe_eur_mwh, 2)} €/MWh"],
        ["Regel negative Preise",
         "6h (Österreich)" if ea.negative_stunden_regel
         == NegativeStundenRegel.SECHS_STUNDEN else "1h (Deutschland)",
         "Direktvermarktung",
         f"{fmt_pct(ga.direktvermarktung_pct_marktwert, 0)} vom Marktwert"
         if dv_relativ
         else f"{_de(p.direktvermarktungskosten_eur_mwh, 2)} €/MWh"],
        ["Gewichtung neg. Stunden",
         fmt_pct(ea.negative_stunden_gewichtung_pct, 0),
         "Negativstunden-Modus",
         "Abregelung" if ea.negative_stunden_modus
         == NegativeStundenModus.ABREGELUNG else "Rückfall auf Marktwert"],
        ["Pacht", f"{_de(p.pacht_eur_kwp_jahr, 2)} €/kWp/Jahr",
         "Kosteninflation",
         f"{fmt_pct(ea.kosten_inflation_pct_pa)} p.a. "
         f"(Pacht, Gemeindeabgabe, Direktvermarktung)"],
    ]
    story.append(_tabelle(annahmen, breiten=[4.1 * cm, 4.35 * cm, 4.1 * cm,
                                             4.35 * cm], schrift=7.6))
    story.append(Paragraph("Tab. A-1: Aufgelöste Annahmen.", _STYLE_CAPTION))

    story.append(Paragraph(txt("bericht.abschnitt_opex_positionen"), _STYLE_H2))
    opex_zeilen = [["Position", "€/kWp/Jahr", "Index %/Jahr", "Index ab Jahr",
                    "Start Betriebsjahr"]]
    for item in ea.opex_items:
        opex_zeilen.append([
            item.name, _de(item.basiswert_eur_kwp, 2),
            _de(item.index_pct_pa * 100, 2), str(item.indexierung_ab_jahr),
            str(item.start_betriebsjahr),
        ])
    story.append(_tabelle(opex_zeilen, breiten=[5.5 * cm] +
                          [(_INHALT_B - 5.5 * cm) / 4] * 4, schrift=7.6))
    story.append(Paragraph(
        "Tab. A-2: Standardbetriebskosten zzgl. produktionsabhängiger "
        "Positionen (Gemeindeabgabe, Direktvermarktung) und Pacht.",
        _STYLE_CAPTION,
    ))

    capex_zeilen = [["Position", "Betrag (€)", "€/kWp"]]
    for name, wert in [
        ("EPC", capex.epc_eur), ("Netzanschluss", capex.netzanschluss_eur),
        ("Trasse", capex.trasse_eur), ("Widmung", capex.widmung_eur),
        ("Genehmigung", capex.genehmigung_eur),
        ("Sonstige extern", capex.sonstige_extern_eur),
        ("AGM", capex.agm_eur), ("M&A", capex.m_and_a_eur),
        ("Pönale + Puffer", capex.poenale_puffer_eur),
    ]:
        capex_zeilen.append([
            name, _de(wert),
            _de(wert / p.nennleistung_kwp, 1) if p.nennleistung_kwp else "—",
        ])
    capex_zeilen.append(["Summe", _de(capex.summe_eur),
                         _de(capex.summe_eur / p.nennleistung_kwp, 1)
                         if p.nennleistung_kwp else "—"])
    story.append(Paragraph(txt("bericht.abschnitt_capex"), _STYLE_H2))
    story.append(_tabelle(capex_zeilen, breiten=[6 * cm, 5.5 * cm, 5.4 * cm],
                          schrift=7.6))
    story.append(Paragraph("Tab. A-3: Investitionskosten nach Position.",
                           _STYLE_CAPTION))
    story.append(PageBreak())

    # ---------------------------------------------------------------- Annex B
    story.append(_Kapitel("B", txt("bericht.kapitel_b_titel")))
    szenario = next(
        s for s in ga.marktpreisszenarien
        if s.name == ea.marktpreisszenario_name
    )
    basis = ea.marktpreis_inflation_basisjahr
    inflation = ea.marktpreis_inflation_pct_pa
    story.append(Paragraph(
        f"Verwendetes Marktpreisszenario „{szenario.name}“: Marktwerte real "
        f"(Preisbasis {basis}) und nominal (inflationiert mit "
        f"{fmt_pct(inflation)} p.a.) sowie Erzeugungsmengen in Stunden "
        f"negativer Preise je Regel. Angewendet wird die "
        f"{'6h' if ea.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN else '1h'}-Zeitreihe.",
        _STYLE_TEXT,
    ))
    jahre = sorted(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
    ts_zeilen = [["Kalender-\njahr", "Marktwert real\n(ct/kWh)",
                  "Marktwert nominal\n(ct/kWh)",
                  "Menge negativ 6h\n(% der Erzeugung)",
                  "Menge negativ 1h\n(% der Erzeugung)"]]
    for jahr in jahre:
        real = szenario.marktwert_solar_ct_kwh_je_kalenderjahr[jahr]
        nominal = real * (1 + inflation) ** (jahr - basis)
        ts_zeilen.append([
            str(jahr), _de(real, 3), _de(nominal, 3),
            _de((szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.get(jahr) or 0) * 100, 1),
            _de((szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.get(jahr) or 0) * 100, 1),
        ])
    story.append(_tabelle(ts_zeilen, breiten=[2.3 * cm] +
                          [(_INHALT_B - 2.3 * cm) / 4] * 4, schrift=6.9))
    story.append(Paragraph(
        "Tab. B-1: Zeitreihen des verwendeten Szenarios.", _STYLE_CAPTION,
    ))
    story.append(PageBreak())

    story.append(Paragraph("Marktwerte aller hinterlegten Szenarien (real)",
                           _STYLE_H2))
    alle_jahre = sorted({
        j for s in ga.marktpreisszenarien
        for j in s.marktwert_solar_ct_kwh_je_kalenderjahr
    })
    kopf = ["Kalenderjahr"] + [s.name for s in ga.marktpreisszenarien]
    mw_zeilen = [kopf]
    for jahr in alle_jahre:
        mw_zeilen.append([str(jahr)] + [
            _de(s.marktwert_solar_ct_kwh_je_kalenderjahr.get(jahr, float("nan")), 3)
            if jahr in s.marktwert_solar_ct_kwh_je_kalenderjahr else "—"
            for s in ga.marktpreisszenarien
        ])
    n_spalten = len(kopf)
    story.append(_tabelle(mw_zeilen, breiten=[2.6 * cm] +
                          [(_INHALT_B - 2.6 * cm) / (n_spalten - 1)] * (n_spalten - 1),
                          schrift=6.9))
    story.append(Paragraph(
        "Tab. B-2: Marktwert Solar (real, ct/kWh) je Szenario – Grundlage "
        "des Szenarienvergleichs in Kapitel 7.",
        _STYLE_CAPTION,
    ))

    doc.multiBuild(story)
    return puffer.getvalue()
