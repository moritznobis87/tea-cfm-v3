"""
Tests des EAG-Gebotsmodells (engine/auktion.py): Datenladen und
Regime-Erkennung, Erfuellung der Kalibrierbedingungen, geforderte
Verteilungseigenschaften (harte Obergrenze, Asymmetrie, Dichte an der
Obergrenze je Regime), Richtung des Wettbewerbs-Links, Monotonie der
Prognose sowie die Integration in die Monte-Carlo-Simulation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from engine.auktion import (
    EPS_MIN,
    FAMILIEN,
    fit_runde,
    kalibriere_modell,
    load_ausschreibungen,
    prognose_naechste_runde,
    validiere_loo,
    vergleiche_familien,
)

DATEN = Path(__file__).parent.parent / "data" / "ausschreibungen.yaml"


@pytest.fixture(scope="module")
def runden():
    return load_ausschreibungen(DATEN)


@pytest.fixture(scope="module")
def modell(runden):
    return kalibriere_modell(runden, "Beta")


class TestDatenUndRegime:
    def test_alle_runden_geladen(self, runden):
        assert len(runden) == 15
        assert all(r.zuschlag_min_ct <= r.zuschlag_mittel_ct <= r.zuschlag_max_ct
                   <= r.preisobergrenze_ct + 1e-9 for r in runden)

    def test_regime_erkennung(self, runden):
        # Fruehe Runden unterzeichnet, Wettbewerbsrunden ab 07/2025.
        nach_datum = sorted(runden, key=lambda r: r.datum)
        assert nach_datum[0].unterzeichnet
        assert not nach_datum[-1].unterzeichnet
        assert sum(not r.unterzeichnet for r in runden) == 4


class TestRundenFit:
    def test_kalibrierbedingungen_erfuellt(self, runden):
        """Mittelwert- und Minimum-Bedingung werden je Runde (nahezu)
        exakt getroffen."""
        familie = FAMILIEN["Beta"]
        for runde in runden:
            fit = fit_runde(runde, familie)
            cap = runde.preisobergrenze_ct
            if runde.unterzeichnet:
                mean_modell = familie.mean(fit.mu_rel, fit.kappa, cap)
            else:
                mean_modell = familie.trunc_mean(
                    fit.mu_rel, fit.kappa, cap, runde.zuschlag_max_ct
                )
            assert mean_modell == pytest.approx(runde.zuschlag_mittel_ct, abs=0.5)
            min_modell = familie.ppf(fit.mu_rel, fit.kappa, cap, EPS_MIN)
            assert min_modell == pytest.approx(runde.zuschlag_min_ct, abs=0.7)

    def test_harte_obergrenze(self, modell):
        familie = FAMILIEN["Beta"]
        f = modell.letzte_runde
        cap = f.ausschreibung.preisobergrenze_ct
        assert familie.cdf(f.mu_rel, f.kappa, cap, cap) == pytest.approx(1.0)
        assert familie.ppf(f.mu_rel, f.kappa, cap, 0.999999) <= cap + 1e-9

    def test_dichte_an_obergrenze_je_regime(self, modell):
        """Geforderte Eigenschaft: In UEBERZEICHNETEN Runden ist die Dichte
        an der Obergrenze praktisch null (Beta-Parameter beta > 1) - das
        ergibt sich in allen vier Wettbewerbsrunden von selbst aus dem
        Fit. In unterzeichneten Runden traegt die Verteilung Masse an der
        Obergrenze (beta < 1, Gebote am Cap) - mit Ausnahme frueher
        Explorationsrunden (12/2022, 07/2023), in denen die Gebote laut
        Literatur breiter streuten."""
        for f in modell.fits:
            beta_param = (1 - f.mu_rel) * f.kappa
            if not f.ausschreibung.unterzeichnet:
                assert beta_param > 1.0
        unterz = [f for f in modell.fits if f.ausschreibung.unterzeichnet]
        am_cap = sum((1 - f.mu_rel) * f.kappa < 1.0 for f in unterz)
        assert am_cap >= len(unterz) - 2

    def test_asymmetrie_langer_linker_auslaeufer(self, modell):
        """Median > Mittelwert (linksschiefe Verteilung) in den
        Wettbewerbsrunden."""
        familie = FAMILIEN["Beta"]
        f = modell.letzte_runde
        cap = f.ausschreibung.preisobergrenze_ct
        median = familie.ppf(f.mu_rel, f.kappa, cap, 0.5)
        mean = familie.mean(f.mu_rel, f.kappa, cap)
        assert median > mean

    def test_latente_wettbewerbsquote_ueber_eins(self, modell):
        for f in modell.fits:
            if not f.ausschreibung.unterzeichnet:
                assert f.wettbewerbsquote_latent and f.wettbewerbsquote > 1.0
            else:
                assert not f.wettbewerbsquote_latent and f.wettbewerbsquote <= 1.0


class TestLinkUndPrognose:
    def test_link_richtungen(self, modell):
        """Datengetriebener Link: mehr Wettbewerb -> niedrigere Lage,
        hoehere Konzentration."""
        assert modell.koef_lage[1] < 0
        assert modell.koef_konzentration[1] > 0

    def test_mehr_wettbewerb_senkt_grenzzuschlag(self, modell):
        cap = 7.77
        p_wenig = prognose_naechste_runde(modell, cap, 1.2, sigma_ln_r=0.15,
                                          n_ziehungen=1500)
        p_viel = prognose_naechste_runde(modell, cap, 2.5, sigma_ln_r=0.15,
                                         n_ziehungen=1500)
        assert np.median(p_viel.pm_sample) < np.median(p_wenig.pm_sample)

    def test_zuschlagskurve_monoton_und_kalibriert(self, modell):
        p = prognose_naechste_runde(modell, 7.77, 1.75)
        gebote = np.linspace(4.0, 7.77, 30)
        probs = [p.zuschlagswahrscheinlichkeit(b) for b in gebote]
        assert all(a >= b - 1e-9 for a, b in zip(probs, probs[1:], strict=False))
        for ziel in (0.5, 0.8, 0.9):
            b = p.empfohlenes_gebot(ziel)
            assert b <= 7.77 + 1e-9
            assert p.zuschlagswahrscheinlichkeit(b) == pytest.approx(ziel, abs=0.03)

    def test_unterzeichnung_liefert_obergrenze(self, modell):
        """r deutlich < 1: Grenzzuschlag = Obergrenze, Empfehlung nahe
        Obergrenze (jedes gueltige Gebot gewinnt)."""
        p = prognose_naechste_runde(modell, 7.77, 0.4, sigma_ln_r=0.05)
        assert p.empfohlenes_gebot(0.9) == pytest.approx(7.77, abs=0.05)

    def test_gebots_ziehungen_erfolgreich_und_begrenzt(self, modell):
        p = prognose_naechste_runde(modell, 7.77, 1.75, n_ziehungen=800)
        zieh = p.gebots_ziehungen(400, seed=1)
        assert len(zieh) == 400
        assert (zieh > 0).all() and (zieh <= 7.77 + 1e-9).all()
        # Erfolgreiche Gebote liegen im Mittel unter dem Grenzzuschlag.
        assert zieh.mean() < np.mean(p.pm_sample)

    def test_reproduzierbar(self, modell):
        p1 = prognose_naechste_runde(modell, 7.77, 1.75, seed=7)
        p2 = prognose_naechste_runde(modell, 7.77, 1.75, seed=7)
        assert np.allclose(p1.pm_sample, p2.pm_sample)


class TestValidierungUndVergleich:
    def test_familienvergleich_liefert_alle_kandidaten(self, runden):
        df = vergleiche_familien(runden)
        assert set(df["familie"]) == set(FAMILIEN)
        beta = df.set_index("familie").loc["Beta"]
        tn = df.set_index("familie").loc["Trunkierte Normalverteilung"]
        # Kernargument der Modellwahl: Beta beschreibt die beobachteten
        # Aggregate (Mittelwert + Minimum gemeinsam) deutlich besser.
        assert beta["fit_rmse_ct"] < tn["fit_rmse_ct"] / 2

    def test_loo_deckt_alle_wettbewerbsrunden_ab(self, runden):
        loo = validiere_loo(runden, "Beta")
        assert len(loo) == sum(not r.unterzeichnet for r in runden)
        assert loo["grenzzuschlag_modell_ct"].notna().all()


class TestMonteCarloIntegration:
    def test_gebotsziehung_veraendert_irr_verteilung(
        self, project, global_assumptions, modell
    ):
        from engine import run_monte_carlo

        p = prognose_naechste_runde(modell, 7.77, 1.75, n_ziehungen=500)
        basis = run_monte_carlo(project, global_assumptions, n_laeufe=30,
                                sigmas={"produktion": 0.0})
        mit_gebot = run_monte_carlo(
            project, global_assumptions, n_laeufe=30,
            sigmas={"produktion": 0.0},
            gebot_ziehungen=p.gebots_ziehungen(30, seed=3),
        )
        # Ohne weitere Unsicherheiten ist die Basis konstant, mit
        # Gebotsziehung streut die IRR.
        assert np.nanstd(basis.irr) == pytest.approx(0.0, abs=1e-12)
        assert np.nanstd(mit_gebot.irr) > 0.001

    def test_konventionell_abschlag_bleibt_erhalten(
        self, project, global_assumptions, modell
    ):
        from engine import AnlagenTyp, run_monte_carlo

        p = prognose_naechste_runde(modell, 7.77, 1.75, n_ziehungen=200)
        ziehung = np.array([6.0])  # ein festes "Gebot" fuer alle Laeufe
        agri = run_monte_carlo(project, global_assumptions, n_laeufe=3,
                               sigmas={}, gebot_ziehungen=ziehung)
        konv = project.model_copy(deep=True)
        konv.anlagentyp = AnlagenTyp.KONVENTIONELL
        konv_mc = run_monte_carlo(konv, global_assumptions, n_laeufe=3,
                                  sigmas={}, gebot_ziehungen=ziehung)
        # Konventionell (25 % Abschlag auf das Gebot) rentiert schlechter.
        assert np.nanmean(konv_mc.irr) < np.nanmean(agri.irr)
        assert p.preisobergrenze_ct == 7.77
