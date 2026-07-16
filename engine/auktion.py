"""
Gebotsmodell fuer die oesterreichischen EAG-Marktpraemienausschreibungen
Photovoltaik (Price-Taker-Sicht).

Fachlicher Rahmen (Webrecherche, Stand 07/2026):
- Pay-as-Bid mit Gebotspreisreihung: Gebote werden aufsteigend gereiht und
  bis zur ausgeschriebenen Menge bezuschlagt; jeder Gewinner erhaelt seinen
  eigenen Gebotswert als anzulegenden Wert (EAG §§ 18 ff., OeMAG/
  EAG-Abwicklungsstelle, pvaustria.at). Hoechstpreis per Verordnung
  (2026/2027: 7,77 ct/kWh), Gebote darueber sind ungueltig.
- Die Auktionsliteratur (Haufe/Ehrhart 2018; Kreiss et al. 2017; Welisch/
  Kreiss 2019) beschreibt fuer Pay-as-Bid genau das in den Daten sichtbare
  Muster: Bieter "shaden" ihre Gebote knapp unter den erwarteten
  Grenzzuschlag; bei schwachem Wettbewerb liegen die Gebote nahe der
  Preisobergrenze, mit steigendem Wettbewerb sinken und verdichten sie sich.

Datenlage (data/ausschreibungen.yaml, 15 Runden 2022-2026):
- Je Runde nur AGGREGATE der bezuschlagten Gebote (min / mengengewichteter
  Mittelwert / max) plus Mengen. Einzelgebote werden nicht veroeffentlicht,
  daher scheiden KDE/GMM auf Rohgeboten aus - es bleibt die Anpassung
  parametrischer, auf [0, Preisobergrenze] BESCHRAENKTER Familien ueber
  Momenten-/Quantilbedingungen.
- "nicht bezuschlagte Leistung" ist unerfuellte ausgeschriebene Menge:
  Runden mit Hoechstzuschlag = Obergrenze und grosser Restmenge waren
  UNTERZEICHNET (alle gueltigen Gebote bezuschlagt -> die Aggregate
  beschreiben die volle Gebotsverteilung). Ab 07/2025 ist der
  Hoechstzuschlag < Obergrenze und die Restmenge ~0: UEBERZEICHNET; das
  eingereichte Gebotsvolumen wird von der OeMAG nicht veroeffentlicht,
  der Ueberzeichnungsgrad ist daher LATENT und wird aus dem Abstand
  Grenzzuschlag/Obergrenze rueckgeschaetzt.

Modellkern:
1. Je Runde wird eine beschraenkte Verteilungsfamilie ueber zwei robuste
   Bedingungen angepasst: (a) mengengewichteter Mittelwert der
   bezuschlagten Gebote, (b) beobachtetes Minimum als niedriges Quantil
   (EPS_MIN, dokumentierte Annahme). Fuer ueberzeichnete Runden ist (a)
   der trunkierte Erwartungswert unterhalb des Grenzzuschlags.
2. Familienvergleich (Beta, Kumaraswamy, trunkierte Normalverteilung)
   ueber die Rekonstruktion nicht gefitteter Groessen und Leave-one-out.
3. Wettbewerbs-Link: Lage (mittleres Gebot relativ zur Obergrenze, Logit)
   und Konzentration (log) werden linear auf ln(Wettbewerbsquote r =
   Gebotsmenge/ausgeschriebene Menge) regressiert - datengetrieben aus
   allen 15 Runden; Residuen liefern die Prognoseunsicherheit.
4. Prognose der naechsten Runde: Ziehungen von r (Lognormal um die
   Nutzererwartung) und Regressionsresiduen ergeben die praedik­tive
   Verteilung des GRENZZUSCHLAGSWERTS p_m. Als Price-Taker gilt:
   Zuschlagswahrscheinlichkeit(Gebot b) = P(p_m > b); das empfohlene
   Gebot fuer Zielwahrscheinlichkeit z ist das (1-z)-Quantil von p_m.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import optimize, stats

# Annahme (dokumentiert): Das veroeffentlichte Minimum der Zuschlagswerte
# entspricht etwa dem 2%-Quantil aller Gebote (Groessenordnung 40-80
# Gebote je Runde; das guenstigste Gebot gewinnt immer). Die Ergebnisse
# reagieren nur schwach auf diese Annahme (Quantil im linken Auslaeufer).
EPS_MIN = 0.02

#: Toleranz (ct/kWh), innerhalb derer der Hoechstzuschlag als "an der
#: Obergrenze" gilt.
_CAP_TOLERANZ_CT = 0.02


# ---------------------------------------------------------------------------
# Datenmodell + Laden
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ausschreibung:
    datum: date
    ausgeschrieben_mw: float
    bezuschlagt_mw: float
    zuschlag_min_ct: float
    zuschlag_mittel_ct: float
    zuschlag_max_ct: float
    preisobergrenze_ct: float

    @property
    def rest_mw(self) -> float:
        return self.ausgeschrieben_mw - self.bezuschlagt_mw

    @property
    def unterzeichnet(self) -> bool:
        """Unterzeichnet/gerade geraeumt: Der Hoechstzuschlag liegt (bis
        auf Rundung) an der Obergrenze - das Gebotsvolumen hat also nicht
        ausgereicht, um die Grenze zu druecken; alle gueltigen Gebote bis
        zur Obergrenze wurden bezuschlagt und die veroeffentlichten
        Aggregate beschreiben die VOLLE Gebotsverteilung. Der Grenzfall
        04/2025 (Hoechstzuschlag 8,97 bei Obergrenze 8,98, Rest 1,5 MW)
        faellt bewusst in dieses Regime: r = bezuschlagt/ausgeschrieben
        ~ 0,99 liefert einen Datenpunkt exakt an der Regimegrenze."""
        return self.zuschlag_max_ct >= self.preisobergrenze_ct - _CAP_TOLERANZ_CT

    @property
    def wettbewerbsquote_beobachtet(self) -> float | None:
        """r = Gebotsmenge / ausgeschriebene Menge. Nur fuer unterzeichnete
        Runden beobachtbar (dort Gebotsmenge = bezuschlagte Menge)."""
        if self.unterzeichnet:
            return self.bezuschlagt_mw / self.ausgeschrieben_mw
        return None


def load_ausschreibungen(path: str | Path) -> list[Ausschreibung]:
    daten = yaml.safe_load(Path(path).read_text())
    return [
        Ausschreibung(
            datum=date.fromisoformat(str(z["datum"])),
            ausgeschrieben_mw=float(z["ausgeschrieben_mw"]),
            bezuschlagt_mw=float(z["bezuschlagt_mw"]),
            zuschlag_min_ct=float(z["zuschlag_min_ct"]),
            zuschlag_mittel_ct=float(z["zuschlag_mittel_ct"]),
            zuschlag_max_ct=float(z["zuschlag_max_ct"]),
            preisobergrenze_ct=float(z["preisobergrenze_ct"]),
        )
        for z in daten["ausschreibungen"]
    ]


def ausschreibungen_dataframe(runden: list[Ausschreibung]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datum": [r.datum for r in runden],
            "ausgeschrieben_mw": [r.ausgeschrieben_mw for r in runden],
            "bezuschlagt_mw": [r.bezuschlagt_mw for r in runden],
            "zuschlag_min_ct": [r.zuschlag_min_ct for r in runden],
            "zuschlag_mittel_ct": [r.zuschlag_mittel_ct for r in runden],
            "zuschlag_max_ct": [r.zuschlag_max_ct for r in runden],
            "preisobergrenze_ct": [r.preisobergrenze_ct for r in runden],
            "unterzeichnet": [r.unterzeichnet for r in runden],
        }
    )


# ---------------------------------------------------------------------------
# Verteilungsfamilien auf [0, Obergrenze]
# ---------------------------------------------------------------------------
# Einheitliche Parametrisierung ueber (mu_rel, kappa):
#   mu_rel  = Erwartungswert / Obergrenze  in (0, 1)   -> Lage
#   kappa   = Konzentration > 0                        -> Streuung (invers)
# Damit sind Familien direkt vergleichbar und der Wettbewerbs-Link ist
# familienunabhaengig formulierbar.


class _Familie:
    name: str = ""

    def dist(self, mu_rel: float, kappa: float, cap: float):
        raise NotImplementedError

    def mean(self, mu_rel: float, kappa: float, cap: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).mean())

    def trunc_mean(self, mu_rel, kappa, cap, oben: float) -> float:
        """E[b | b <= oben] via numerischer Integration der Quantilfunktion
        (stabil fuer alle Familien)."""
        d = self.dist(mu_rel, kappa, cap)
        q_oben = float(d.cdf(oben))
        if q_oben <= 1e-9:
            return 0.0
        u = np.linspace(1e-6, q_oben - 1e-9, 400)
        return float(np.mean(d.ppf(u)))

    def ppf(self, mu_rel, kappa, cap, q: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).ppf(q))

    def cdf(self, mu_rel, kappa, cap, x: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).cdf(x))

    def pdf(self, mu_rel, kappa, cap, x: np.ndarray) -> np.ndarray:
        return self.dist(mu_rel, kappa, cap).pdf(x)


class FamilieBeta(_Familie):
    """Skalierte Beta auf [0, cap]: a = mu_rel*kappa, b = (1-mu_rel)*kappa.
    Natuerlich beschraenkt, beliebig schief; fuer mu_rel -> 1 und kappa
    moderat entsteht genau das erwartete Bild (Masse nahe der Obergrenze,
    langer linker Auslaeufer); Dichte an der Obergrenze -> 0 sobald
    (1-mu_rel)*kappa > 1."""

    name = "Beta"

    def dist(self, mu_rel, kappa, cap):
        return stats.beta(mu_rel * kappa, (1 - mu_rel) * kappa, loc=0, scale=cap)


class FamilieKumaraswamy(_Familie):
    """Kumaraswamy auf [0, cap] (F(x) = 1-(1-(x/cap)^a)^b): der Beta sehr
    aehnlich, mit analytischer Quantilfunktion. Interne Umrechnung von
    (mu_rel, kappa) auf (a, b) numerisch ueber die Momentbedingung."""

    name = "Kumaraswamy"

    @staticmethod
    def _mean_ab(a: float, b: float) -> float:
        from scipy.special import gammaln

        return float(b * np.exp(gammaln(1 + 1 / a) + gammaln(b) - gammaln(1 + 1 / a + b)))

    def _ab(self, mu_rel: float, kappa: float) -> tuple[float, float]:
        # kappa steuert a (Konzentration links), b wird auf den Mittelwert
        # kalibriert. mu_rel wird von Randwerten ferngehalten, damit die
        # Nullstellensuche stets ein Vorzeichenwechsel-Intervall hat.
        mu_rel = float(np.clip(mu_rel, 1e-4, 1 - 1e-4))
        a = max(kappa * mu_rel, 0.05)

        def f(log_b):
            return self._mean_ab(a, float(np.exp(log_b))) - mu_rel

        lo, hi = -8.0, 10.0
        if f(lo) <= 0:            # Mittelwert selbst bei b->0 unter Ziel
            return a, float(np.exp(lo))
        if f(hi) >= 0:
            return a, float(np.exp(hi))
        log_b = optimize.brentq(f, lo, hi)
        return a, float(np.exp(log_b))

    class _Dist:
        def __init__(self, a, b, cap):
            self.a, self.b, self.cap = a, b, cap

        def cdf(self, x):
            z = np.clip(np.asarray(x, dtype=float) / self.cap, 0, 1)
            return 1 - (1 - z**self.a) ** self.b

        def ppf(self, q):
            q = np.asarray(q, dtype=float)
            return self.cap * (1 - (1 - q) ** (1 / self.b)) ** (1 / self.a)

        def pdf(self, x):
            z = np.clip(np.asarray(x, dtype=float) / self.cap, 1e-12, 1 - 1e-12)
            return (
                self.a * self.b * z ** (self.a - 1)
                * (1 - z**self.a) ** (self.b - 1) / self.cap
            )

        def mean(self):
            u = np.linspace(1e-6, 1 - 1e-6, 800)
            return float(np.mean(self.ppf(u)))

    def dist(self, mu_rel, kappa, cap):
        a, b = self._ab(mu_rel, kappa)
        return self._Dist(a, b, cap)


class FamilieTruncNormal(_Familie):
    """Auf [0, cap] trunkierte Normalverteilung - bewusst als (symmetrische)
    Vergleichsbasis: sie kann die harte Obergrenze abbilden, aber keinen
    langen linken Auslaeufer bei gleichzeitig hoher Konzentration rechts."""

    name = "Trunkierte Normalverteilung"

    def dist(self, mu_rel, kappa, cap):
        mu = mu_rel * cap
        sigma = cap / max(kappa, 1e-6)
        a, b = (0 - mu) / sigma, (cap - mu) / sigma
        return stats.truncnorm(a, b, loc=mu, scale=sigma)


class FamilieInvGammaGespiegelt(_Familie):
    """An der Y-Achse gespiegelte und an die Preisobergrenze verschobene
    Inverse-Gamma-Verteilung: Gebot b = Obergrenze - Y mit
    Y ~ InvGamma(a, scale). Die Dichte faellt rechts zur Obergrenze sehr
    steil auf null (alle Ableitungen verschwinden dort) und laeuft nach
    links langsam aus (schwerer linker Auslaeufer) - exakt das fuer
    Pay-as-Bid unter Wettbewerb erwartete Bild: hoechste Dichte knapp
    unter dem erwarteten Grenzzuschlag. Parametrisierung: kappa =
    Formparameter a (Konzentration), Lage ueber E[b] = mu_rel * cap.
    Einschraenkung: Masse DIREKT an der Obergrenze (Gebote am Cap, wie in
    unterzeichneten Runden beobachtet) kann diese Familie prinzipbedingt
    nicht abbilden."""

    name = "Gespiegelte Inverse Gamma"

    class _Dist:
        def __init__(self, a, scale, cap):
            self.ig = stats.invgamma(a, scale=scale)
            self.cap = cap

        def cdf(self, x):
            return self.ig.sf(self.cap - np.asarray(x, dtype=float))

        def ppf(self, q):
            # Gebote sind physikalisch >= 0: extrem schwere linke
            # Auslaeufer werden am Nullpunkt gekappt.
            return np.maximum(self.cap - self.ig.isf(np.asarray(q, dtype=float)), 0.0)

        def pdf(self, x):
            return self.ig.pdf(self.cap - np.asarray(x, dtype=float))

        def mean(self):
            return max(self.cap - float(self.ig.mean()), 0.0)

    def dist(self, mu_rel, kappa, cap):
        a = max(float(kappa), 1.1)          # Erwartungswert existiert fuer a > 1
        scale = cap * (1 - float(np.clip(mu_rel, 1e-4, 1 - 1e-4))) * (a - 1)
        return self._Dist(a, max(scale, 1e-9), cap)


FAMILIEN: dict[str, _Familie] = {
    f.name: f
    for f in (
        FamilieBeta(),
        FamilieKumaraswamy(),
        FamilieTruncNormal(),
        FamilieInvGammaGespiegelt(),
    )
}


# ---------------------------------------------------------------------------
# Fit je Ausschreibung
# ---------------------------------------------------------------------------


@dataclass
class RundenFit:
    ausschreibung: Ausschreibung
    familie: str
    mu_rel: float
    kappa: float
    wettbewerbsquote: float          # beobachtet (unterzeichnet) oder latent
    wettbewerbsquote_latent: bool
    fit_residuum: float              # Restfehler der beiden Bedingungen


def fit_runde(runde: Ausschreibung, familie: _Familie) -> RundenFit:
    """Passt (mu_rel, kappa) an zwei Bedingungen an:
    (a) mengengewichteter Mittelwert der bezuschlagten Gebote,
    (b) Minimum der Zuschlagswerte als EPS_MIN-Quantil ALLER Gebote
        (das guenstigste Gebot gewinnt immer).
    Ueberzeichnete Runden nutzen fuer (a) den unterhalb des Grenzzuschlags
    trunkierten Erwartungswert; die Wettbewerbsquote ergibt sich dort als
    latenter Wert r = 1 / F(Grenzzuschlag)."""
    cap = runde.preisobergrenze_ct

    def residuen(theta):
        mu_rel = 1 / (1 + np.exp(-theta[0]))          # Logit-Ruecktransform
        kappa = float(np.exp(theta[1]))
        if runde.unterzeichnet:
            mean_soll = familie.mean(mu_rel, kappa, cap)
        else:
            mean_soll = familie.trunc_mean(mu_rel, kappa, cap, runde.zuschlag_max_ct)
        r1 = mean_soll - runde.zuschlag_mittel_ct
        r2 = familie.ppf(mu_rel, kappa, cap, EPS_MIN) - runde.zuschlag_min_ct
        return [r1, r2]

    start = np.array([np.log(0.85 / 0.15), np.log(8.0)])
    loesung = optimize.least_squares(
        residuen, start, method="trf", max_nfev=400,
        bounds=([-8.0, np.log(1.05)], [8.0, np.log(800.0)]),
    )
    mu_rel = float(1 / (1 + np.exp(-loesung.x[0])))
    kappa = float(np.exp(loesung.x[1]))

    if runde.unterzeichnet:
        r = runde.bezuschlagt_mw / runde.ausgeschrieben_mw
        latent = False
    else:
        q_grenz = familie.cdf(mu_rel, kappa, cap, runde.zuschlag_max_ct)
        r = 1.0 / max(q_grenz, 1e-6)
        latent = True

    return RundenFit(
        ausschreibung=runde, familie=familie.name, mu_rel=mu_rel, kappa=kappa,
        wettbewerbsquote=float(r), wettbewerbsquote_latent=latent,
        fit_residuum=float(np.sqrt(np.mean(np.array(residuen(loesung.x)) ** 2))),
    )


# ---------------------------------------------------------------------------
# Wettbewerbs-Link + kalibriertes Modell
# ---------------------------------------------------------------------------


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


@dataclass
class AuktionsModell:
    """Kalibriertes Gesamtmodell: je Runde gefittete Verteilungen plus der
    datengetriebene Link von Lage/Konzentration auf die Wettbewerbsquote."""

    familie_name: str
    fits: list[RundenFit]
    koef_lage: tuple[float, float]        # logit(mu_rel) = a + b*ln(r)
    koef_konzentration: tuple[float, float]  # ln(kappa)   = c + d*ln(r)
    residuen_lage: np.ndarray
    residuen_konzentration: np.ndarray
    # Lokales Trendmodell fuer die Prognose (Verankerung an der letzten
    # Runde): mittlere Rundenaenderung der transformierten Parameter in
    # den Wettbewerbsrunden (Bieterlernen) und deren Streuung.
    drift_lage: float = 0.0
    drift_konzentration: float = 0.0
    sd_lage: float = 0.35
    sd_konzentration: float = 0.35

    @property
    def familie(self) -> _Familie:
        return FAMILIEN[self.familie_name]

    @property
    def letzte_runde(self) -> RundenFit:
        return max(self.fits, key=lambda f: f.ausschreibung.datum)

    def parameter_bei(self, r: float, res_lage: float = 0.0,
                      res_kappa: float = 0.0) -> tuple[float, float]:
        x = np.log(max(r, 1e-3))
        mu_rel = 1 / (1 + np.exp(-(self.koef_lage[0] + self.koef_lage[1] * x + res_lage)))
        kappa = float(np.exp(self.koef_konzentration[0]
                             + self.koef_konzentration[1] * x + res_kappa))
        return float(mu_rel), max(kappa, 1.05)


def kalibriere_modell(
    runden: list[Ausschreibung], familie_name: str = "Beta"
) -> AuktionsModell:
    familie = FAMILIEN[familie_name]
    fits = [fit_runde(r, familie) for r in runden]

    x = np.log([f.wettbewerbsquote for f in fits])
    y_lage = _logit([f.mu_rel for f in fits])
    y_kappa = np.log([f.kappa for f in fits])
    b_l, a_l = np.polyfit(x, y_lage, 1)
    b_k, a_k = np.polyfit(x, y_kappa, 1)

    # Drift/Streuung aus den aufeinanderfolgenden Wettbewerbsrunden
    # (relevantes Regime fuer die Prognose). Fallback bei zu wenigen
    # Runden: kein Drift, konservative Streuung.
    wett = sorted(
        (f for f in fits if not f.ausschreibung.unterzeichnet),
        key=lambda f: f.ausschreibung.datum,
    )
    d_lage = np.diff(_logit([f.mu_rel for f in wett])) if len(wett) >= 2 else np.array([])
    d_konz = np.diff(np.log([f.kappa for f in wett])) if len(wett) >= 2 else np.array([])

    def _drift_sd(deltas: np.ndarray) -> tuple[float, float]:
        """Sparsamste belastbare Annahme bei erst drei beobachteten
        Rundenaenderungen (davon ein Regime-Eintrittssprung 07->10/2025):
        RANDOM WALK - Drift 0, d.h. die zentrale Prognosewelt entspricht
        exakt der letzten Runde (nur um Wettbewerbsquote und Obergrenze
        angepasst). Die STREUUNG der beobachteten Rundenaenderungen geht
        als Prognoseunsicherheit ein; nach oben begrenzt, da die
        Rundenschwankung der Fit-Parameter auch Kalibrierrauschen
        enthaelt (die Konzentration kappa ist aus Aggregaten nur grob
        identifiziert)."""
        if len(deltas) == 0:
            return 0.0, 0.35
        sd = np.std(deltas, ddof=1) if len(deltas) > 1 else 0.35
        return 0.0, float(np.clip(sd, 0.15, 0.8))

    drift_l, sd_l = _drift_sd(d_lage)
    drift_k, sd_k = _drift_sd(d_konz)

    return AuktionsModell(
        familie_name=familie_name,
        fits=fits,
        koef_lage=(float(a_l), float(b_l)),
        koef_konzentration=(float(a_k), float(b_k)),
        residuen_lage=y_lage - (a_l + b_l * x),
        residuen_konzentration=y_kappa - (a_k + b_k * x),
        drift_lage=drift_l,
        drift_konzentration=drift_k,
        sd_lage=sd_l,
        sd_konzentration=sd_k,
    )


# ---------------------------------------------------------------------------
# Familienvergleich + Validierung (Leave-one-out)
# ---------------------------------------------------------------------------


def vergleiche_familien(runden: list[Ausschreibung]) -> pd.DataFrame:
    """Bewertet jede Familie über zwei Kriterien:
    1. rekonstruktion_max: Bei unterzeichneten Runden ist der hoechste
       Zuschlagswert = Obergrenze, d.h. die Familie muss dort rechts noch
       spuerbare Masse tragen (P(b > 0.99*cap) >= 1/50 Geboten). Gemessen
       wird der Anteil verletzter Runden.
    2. loo_rmse_pm: Leave-one-out ueber die ueberzeichneten Runden -
       Prognosefehler des Grenzzuschlagswerts bei gegebener Wettbewerbs-
       quote (RMSE in ct/kWh).
    Zusaetzlich: mittleres Fit-Residuum der beiden Kalibrierbedingungen."""
    zeilen = []
    ueberzeichnet = [r for r in runden if not r.unterzeichnet]
    for name in FAMILIEN:
        modell = kalibriere_modell(runden, name)
        fit_rmse = float(np.mean([f.fit_residuum for f in modell.fits]))

        verletzt = 0
        unterz = [f for f in modell.fits if f.ausschreibung.unterzeichnet]
        for f in unterz:
            cap = f.ausschreibung.preisobergrenze_ct
            masse_oben = 1 - FAMILIEN[name].cdf(f.mu_rel, f.kappa, cap, 0.99 * cap)
            if masse_oben < 1 / 50:
                verletzt += 1

        fehler = []
        for raus in ueberzeichnet:
            rest = [r for r in runden if r is not raus]
            m = kalibriere_modell(rest, name)
            r_latent = fit_runde(raus, FAMILIEN[name]).wettbewerbsquote
            mu_rel, kappa = m.parameter_bei(r_latent)
            pm_prognose = FAMILIEN[name].ppf(
                mu_rel, kappa, raus.preisobergrenze_ct, min(1.0, 1 / r_latent)
            )
            fehler.append(pm_prognose - raus.zuschlag_max_ct)
        zeilen.append(
            {
                "familie": name,
                "fit_rmse_ct": round(fit_rmse, 4),
                "cap_masse_verletzt": f"{verletzt}/{len(unterz)}",
                "loo_rmse_pm_ct": round(float(np.sqrt(np.mean(np.square(fehler)))), 3),
            }
        )
    return pd.DataFrame(zeilen)


def validiere_loo(runden: list[Ausschreibung], familie_name: str) -> pd.DataFrame:
    """Leave-one-out je ueberzeichneter Runde: Prognose von Grenzzuschlag,
    Mittelwert und Minimum aus den uebrigen Runden (bei gegebener
    Wettbewerbsquote) - plus naive Basislinie 'bisheriger Ansatz'
    (Fortschreibung des letzten beobachteten Hoechstzuschlags)."""
    familie = FAMILIEN[familie_name]
    zeilen = []
    ueberzeichnet = [r for r in runden if not r.unterzeichnet]
    sortiert = sorted(runden, key=lambda r: r.datum)
    for raus in ueberzeichnet:
        rest = [r for r in runden if r is not raus]
        modell = kalibriere_modell(rest, familie_name)
        r_latent = fit_runde(raus, familie).wettbewerbsquote
        mu_rel, kappa = modell.parameter_bei(r_latent)
        cap = raus.preisobergrenze_ct
        q = min(1.0, 1 / r_latent)
        vorher = [r for r in sortiert if r.datum < raus.datum]
        naiv = vorher[-1].zuschlag_max_ct if vorher else np.nan
        zeilen.append(
            {
                "datum": raus.datum,
                "grenzzuschlag_ist_ct": raus.zuschlag_max_ct,
                "grenzzuschlag_modell_ct": round(familie.ppf(mu_rel, kappa, cap, q), 2),
                "grenzzuschlag_naiv_ct": naiv,
                "mittel_ist_ct": raus.zuschlag_mittel_ct,
                "mittel_modell_ct": round(
                    familie.trunc_mean(mu_rel, kappa, cap,
                                       familie.ppf(mu_rel, kappa, cap, q)), 2),
                "min_ist_ct": raus.zuschlag_min_ct,
                "min_modell_ct": round(familie.ppf(mu_rel, kappa, cap, EPS_MIN), 2),
            }
        )
    return pd.DataFrame(zeilen)


def validiere_einschritt(runden: list[Ausschreibung],
                          familie_name: str) -> pd.DataFrame:
    """Rollierender Ein-Schritt-Backtest der VERANKERTEN Prognose ueber
    die Wettbewerbsrunden: Fuer jede Runde wird das Modell nur auf den
    davor liegenden Runden kalibriert und der Grenzzuschlag als
    Punktprognose (zentrale Welt, r der Zielrunde gegeben) vorhergesagt -
    im Vergleich zur naiven Fortschreibung des letzten Hoechstzuschlags
    (der bisherigen Praxis)."""
    familie = FAMILIEN[familie_name]
    sortiert = sorted(runden, key=lambda r: r.datum)
    zeilen = []
    for i, ziel in enumerate(sortiert):
        if ziel.unterzeichnet or i == 0:
            continue
        vorher = sortiert[:i]
        modell = kalibriere_modell(vorher, familie_name)
        anker = modell.letzte_runde
        r_ziel = fit_runde(ziel, familie).wettbewerbsquote
        dlnr = np.log(r_ziel) - np.log(anker.wettbewerbsquote)
        th_l = (_logit(np.array([anker.mu_rel]))[0]
                + modell.koef_lage[1] * dlnr + modell.drift_lage)
        th_k = (np.log(anker.kappa)
                + modell.koef_konzentration[1] * dlnr
                + modell.drift_konzentration)
        mu_rel = float(1 / (1 + np.exp(-np.clip(th_l, -8, 8))))
        kappa = float(np.clip(np.exp(th_k), 1.05, 800.0))
        q = min(1.0, 1.0 / r_ziel)
        pm_prog = (ziel.preisobergrenze_ct if q >= 1.0
                   else familie.ppf(mu_rel, kappa, ziel.preisobergrenze_ct, q))
        zeilen.append({
            "datum": ziel.datum,
            "grenzzuschlag_ist_ct": ziel.zuschlag_max_ct,
            "grenzzuschlag_modell_ct": round(pm_prog, 2),
            "grenzzuschlag_naiv_ct": vorher[-1].zuschlag_max_ct,
            "mittel_ist_ct": ziel.zuschlag_mittel_ct,
            "mittel_modell_ct": round(
                familie.trunc_mean(mu_rel, kappa, ziel.preisobergrenze_ct,
                                   pm_prog), 2),
            "min_ist_ct": ziel.zuschlag_min_ct,
            "min_modell_ct": round(
                familie.ppf(mu_rel, kappa, ziel.preisobergrenze_ct, EPS_MIN), 2),
        })
    return pd.DataFrame(zeilen)


# ---------------------------------------------------------------------------
# Prognose der naechsten Ausschreibung (Price-Taker)
# ---------------------------------------------------------------------------


@dataclass
class GebotsPrognose:
    """Praediktive Verteilung des Grenzzuschlagswerts p_m der naechsten
    Runde plus reprasentative Gebotsdichte (fuer die Visualisierung)."""

    preisobergrenze_ct: float
    wettbewerbsquote_erwartet: float
    sigma_ln_r: float
    pm_sample: np.ndarray               # Ziehungen des Grenzzuschlags
    dichte_x: np.ndarray
    dichte_y: np.ndarray                # Dichte ALLER Gebote (Mischung)
    dichte_zuschlag_y: np.ndarray | None = None  # Dichte der ZUSCHLAGSWERTE
    gebot_mittel_ct: float = 0.0        # Ø der prognostizierten Zuschlagswerte
    gebot_median_ct: float = 0.0
    gebot_quantile: dict[int, float] = field(default_factory=dict)
    _modell: AuktionsModell | None = None
    _param_sample: np.ndarray | None = None   # (n, 2): mu_rel, kappa je Ziehung

    def zuschlagswahrscheinlichkeit(self, gebot_ct: float) -> float:
        """P(Zuschlag | Gebot) = P(Grenzzuschlag > Gebot) - Price-Taker."""
        return float(np.mean(self.pm_sample > gebot_ct))

    def empfohlenes_gebot(self, zielwahrscheinlichkeit: float) -> float:
        """Hoechstes Gebot, das die Zielwahrscheinlichkeit gerade noch
        erreicht: (1 - z)-Quantil der Grenzzuschlags-Verteilung."""
        z = float(np.clip(zielwahrscheinlichkeit, 0.01, 0.999))
        return float(np.quantile(self.pm_sample, 1 - z))

    def gebots_ziehungen(self, n: int, seed: int = 42) -> np.ndarray:
        """Zufaellige ERFOLGREICHE Gebote der prognostizierten Auktion (fuer
        die Monte-Carlo-Simulation des Cashflow-Modells): je Ziehung eine
        Auktionswelt (r, Parameter) und darin ein Gebot unterhalb des
        jeweiligen Grenzzuschlags."""
        assert self._modell is not None and self._param_sample is not None
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(self.pm_sample), size=n)
        familie = self._modell.familie
        werte = np.empty(n)
        for i, j in enumerate(idx):
            mu_rel, kappa = self._param_sample[j]
            q_max = familie.cdf(mu_rel, kappa, self.preisobergrenze_ct,
                                self.pm_sample[j])
            u = rng.uniform(1e-6, max(q_max, 2e-6))
            werte[i] = familie.ppf(mu_rel, kappa, self.preisobergrenze_ct, u)
        return werte


def prognose_naechste_runde(
    modell: AuktionsModell,
    preisobergrenze_ct: float,
    wettbewerbsquote_erwartet: float,
    sigma_ln_r: float = 0.25,
    n_ziehungen: int = 4000,
    seed: int = 42,
) -> GebotsPrognose:
    """Prognose als lokales Trendmodell, VERANKERT an der letzten Runde:
    Die Kernfrage ist, wie weit die naechste Verteilung von der letzten
    Ausschreibung abweicht - nicht, welches Niveau eine ueber alle
    (ueberwiegend unterzeichneten) Runden gemittelte Regression liefert.

    Je Auktionswelt:
      ln r ~ N(ln r_erwartet, sigma)
      logit(mu_rel) = logit(mu_rel_letzte) + b_lage*(ln r - ln r_letzte)
                      + Drift_Wettbewerbsrunden + eps
      ln(kappa)     analog.
    Die Steigungen b stammen aus der Gesamthistorie (einzige Quelle fuer
    den r-Effekt ueber beide Regime), Drift und Streuung aus den
    aufeinanderfolgenden WETTBEWERBSRUNDEN (Bieterlernen; Haufe/Ehrhart
    2018). Grenzzuschlag p_m = F^{-1}(min(1, 1/r)); nur bei r <= 1
    (Unterzeichnung) liegt p_m an der Obergrenze - bei anhaltender
    Ueberzeichnung traegt die Dichte dort praktisch keine Masse.
    """
    rng = np.random.default_rng(seed)
    familie = modell.familie
    cap = preisobergrenze_ct
    anker = modell.letzte_runde
    th_lage_0 = float(_logit(np.array([anker.mu_rel]))[0])
    th_konz_0 = float(np.log(anker.kappa))

    # Bei erwarteter Ueberzeichnung (r > 1) werden Unterzeichnungs-Welten
    # ausgeschlossen (links bei r = 1 trunkierte Lognormalverteilung):
    # die anhaltend hohe Nachfrage ("enormes Interesse", EAG-Abwicklungs-
    # stelle 07/2026) macht ein Zurueckfallen unter die ausgeschriebene
    # Menge unplausibel - Gebote an der Obergrenze treten dann nicht auf.
    mu_ln = np.log(wettbewerbsquote_erwartet)
    if wettbewerbsquote_erwartet > 1.0:
        untergrenze = (0.0 - mu_ln) / sigma_ln_r
        ln_r = stats.truncnorm.rvs(untergrenze, np.inf, loc=mu_ln,
                                   scale=sigma_ln_r, size=n_ziehungen,
                                   random_state=rng)
    else:
        ln_r = rng.normal(mu_ln, sigma_ln_r, n_ziehungen)
    r_zieh = np.exp(ln_r)
    dlnr = ln_r - np.log(anker.wettbewerbsquote)
    eps_l = rng.normal(0.0, modell.sd_lage, n_ziehungen)
    eps_k = rng.normal(0.0, modell.sd_konzentration, n_ziehungen)

    pm = np.empty(n_ziehungen)
    params = np.empty((n_ziehungen, 2))
    for i in range(n_ziehungen):
        th_l = th_lage_0 + modell.koef_lage[1] * dlnr[i] + modell.drift_lage + eps_l[i]
        th_k = (th_konz_0 + modell.koef_konzentration[1] * dlnr[i]
                + modell.drift_konzentration + eps_k[i])
        mu_rel = float(1 / (1 + np.exp(-np.clip(th_l, -8, 8))))
        kappa = float(np.clip(np.exp(th_k), 1.05, 800.0))
        params[i] = (mu_rel, kappa)
        q = min(1.0, 1.0 / r_zieh[i])
        pm[i] = cap if q >= 1.0 else familie.ppf(mu_rel, kappa, cap, q)

    # Dichten der ZENTRALEN Prognosewelt (eine einzelne Auktion, nicht
    # die ueber Parameterunsicherheit verschmierte Mischung - die
    # Unsicherheit steckt in der p_m-Verteilung und wird im Chart als
    # Band gezeigt). Zuschlagswerte = Gebotsdichte am zentralen
    # Grenzzuschlag abgeschnitten und renormiert: hoechste Dichte knapp
    # unterhalb des Grenzzuschlags, steiler Abfall nach rechts, langsam
    # auslaufender linker Rand - das ist die Verteilung, die die OeMAG-
    # Aggregate (min/Ø/max der Zuschlagswerte) beschreiben.
    dlnr_c = float(np.log(wettbewerbsquote_erwartet)
                   - np.log(anker.wettbewerbsquote))
    th_l_c = th_lage_0 + modell.koef_lage[1] * dlnr_c + modell.drift_lage
    th_k_c = (th_konz_0 + modell.koef_konzentration[1] * dlnr_c
              + modell.drift_konzentration)
    mu_c = float(1 / (1 + np.exp(-np.clip(th_l_c, -8, 8))))
    ka_c = float(np.clip(np.exp(th_k_c), 1.05, 800.0))
    d = familie.dist(mu_c, ka_c, cap)
    q_c = min(1.0, 1.0 / wettbewerbsquote_erwartet)
    pm_c = cap if q_c >= 1.0 else float(d.ppf(q_c))

    x = np.linspace(0.01 * cap, cap * (1 - 1e-4), 500)
    dichte_alle = np.asarray(d.pdf(x), dtype=float)
    dichte_zuschlag = dichte_alle * (x <= pm_c) / max(q_c, 1e-6)

    # Kennzahlen der prognostizierten Zuschlagswerte (zentrale Welt).
    quantile = {q: float(d.ppf(q / 100 * q_c)) for q in (5, 25, 50, 75, 95)}
    mittel_zuschlag = familie.trunc_mean(mu_c, ka_c, cap, pm_c)

    return GebotsPrognose(
        preisobergrenze_ct=cap,
        wettbewerbsquote_erwartet=wettbewerbsquote_erwartet,
        sigma_ln_r=sigma_ln_r,
        pm_sample=pm,
        dichte_x=x,
        dichte_y=dichte_alle,
        dichte_zuschlag_y=dichte_zuschlag,
        gebot_mittel_ct=float(mittel_zuschlag),
        gebot_median_ct=quantile[50],
        gebot_quantile=quantile,
        _modell=modell,
        _param_sample=params,
    )
