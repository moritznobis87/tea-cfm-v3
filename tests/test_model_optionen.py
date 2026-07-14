"""
Tests fuer die konfigurierbaren Modelloptionen:
- Gemeindeabgabe ueber die GESAMTE Projektlaufzeit (Regressionstest)
- Tilgungsfreies Anlaufjahr (On/Off)
- Negativstunden-Modus: Abregelung vs. Rueckfall auf Jahresmarktwert
"""

from __future__ import annotations

from datetime import date

import pytest

from engine import NegativeStundenModus, TilgungsArt, run_valuation
from engine.financing import calculate_financing
from engine.kpis import npv_at
from engine.timeline import build_timeline


class TestGemeindeabgabeVolleLaufzeit:
    def test_abgabe_faellt_in_jedem_betriebsjahr_an(self, project, global_assumptions):
        """Regressionstest: Die Gemeindeabgabe (hier 2 €/MWh) wird in JEDEM
        Jahr der Betriebsdauer auf die Produktion gezahlt - vom ersten bis
        zum letzten Betriebsjahr, unabhaengig von Foerder- oder
        Kreditlaufzeit."""
        result = run_valuation(project, global_assumptions)
        df = result.cashflow.data
        betriebsjahre = df[df["jahr"] >= 1]
        assert len(betriebsjahre) == global_assumptions.betriebsdauer_jahre
        # 1 GWh/Jahr x 2 €/MWh = 2.000 €/Jahr, in jedem einzelnen Jahr.
        assert betriebsjahre["gemeindeabgabe_eur"].tolist() == pytest.approx(
            [2000.0] * global_assumptions.betriebsdauer_jahre
        )
        # Auch im allerletzten Betriebsjahr (nach Foerder- UND Kreditende).
        assert betriebsjahre["gemeindeabgabe_eur"].iloc[-1] == pytest.approx(2000.0)


class TestTilgungsfreiesAnlaufjahr:
    def _fin(self, tilgungsfrei: bool, art: TilgungsArt = TilgungsArt.LINEAR):
        timeline = build_timeline(date(2027, 1, 1), 25)
        return calculate_financing(
            timeline, 1_000_000.0, 0.2, 0.04, 20, art,
            tilgungsfreies_anlaufjahr=tilgungsfrei,
        )

    def test_jahr_1_nur_zinsen(self):
        fin = self._fin(True)
        assert fin["tilgung_eur"].iloc[0] == pytest.approx(0.0)
        assert fin["zinsen_eur"].iloc[0] == pytest.approx(800_000 * 0.04)
        assert fin["schuldendienst_eur"].iloc[0] == pytest.approx(800_000 * 0.04)

    def test_jahr_2_zins_noch_auf_voller_kreditsumme(self):
        """Weil Jahr 1 ungetilgt bleibt, ist der Jahresanfangsstand in
        Jahr 2 noch die volle Kreditsumme - genau die Zinsstruktur aus dem
        Referenz-Excel (zweimal voller Zins hintereinander)."""
        fin = self._fin(True)
        assert fin["zinsen_eur"].iloc[1] == pytest.approx(fin["zinsen_eur"].iloc[0])
        assert fin["zinsen_eur"].iloc[2] < fin["zinsen_eur"].iloc[1]

    def test_kredit_wird_trotzdem_vollstaendig_getilgt(self):
        for art in (TilgungsArt.LINEAR, TilgungsArt.ANNUITAET):
            fin = self._fin(True, art)
            assert fin["tilgung_eur"].sum() == pytest.approx(800_000.0)
            # Raten laufen in den Jahren 2..21 (20 Raten), danach nichts mehr.
            assert (fin["tilgung_eur"].iloc[1:21] > 0).all()
            assert fin["darlehensstand_eop_eur"].iloc[20] == pytest.approx(
                0.0, abs=1e-6
            )
            assert (fin["schuldendienst_eur"].iloc[21:] == 0.0).all()

    def test_schalter_aus_entspricht_bisherigem_verhalten(self):
        mit = self._fin(False)
        assert mit["tilgung_eur"].iloc[0] == pytest.approx(40_000.0)
        assert mit["darlehensstand_eop_eur"].iloc[19] == pytest.approx(0.0, abs=1e-6)

    def test_wirkung_auf_projekt_irr(self, project, global_assumptions):
        """Die Verschiebung der ersten Rate ans Laufzeitende erhoeht die
        Equity-IRR (frueher Cashflow wiegt in der IRR am schwersten)."""
        basis = run_valuation(project, global_assumptions).kpis.equity_irr
        global_assumptions.tilgungsfreies_anlaufjahr = True
        mit_anlaufjahr = run_valuation(project, global_assumptions).kpis.equity_irr
        assert mit_anlaufjahr > basis


class TestNegativeStundenModus:
    @pytest.fixture
    def ga_mit_negstunden(self, global_assumptions):
        szenario = global_assumptions.marktpreisszenarien[0]
        for jahr in szenario.anteil_negativer_stunden_pct_je_kalenderjahr:
            szenario.anteil_negativer_stunden_pct_je_kalenderjahr[jahr] = 0.10
        return global_assumptions

    def test_abregelung_entzieht_komplette_verguetung(
        self, project, ga_mit_negstunden
    ):
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        df = run_valuation(project, ga_mit_negstunden).cashflow.data
        # Jahr 1: 1 GWh x 90 % x 7 ct = 63.000 €.
        assert df.loc[df["jahr"] == 1, "erloes_eur"].iloc[0] == pytest.approx(63_000.0)

    def test_marktwert_modus_verguetet_negstunden_zum_marktwert(
        self, project, ga_mit_negstunden
    ):
        """Anlage laeuft weiter: 90 % der Menge zum Foerdersatz (7 ct),
        10 % zum Jahresmarktwert (4 ct) - entspricht exakt der
        Spread-Formel des Referenz-Excels:
        Produktion x Satz - Produktion x Anteil x (Satz - Marktwert)."""
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        df = run_valuation(project, ga_mit_negstunden).cashflow.data
        erwartet = 1e6 * (0.9 * 7.0 + 0.1 * 4.0) / 100
        assert df.loc[df["jahr"] == 1, "erloes_eur"].iloc[0] == pytest.approx(erwartet)
        spread_formel = 1e6 * 7.0 / 100 - 1e6 * 0.10 * (7.0 - 4.0) / 100
        assert erwartet == pytest.approx(spread_formel)

    def test_nach_foerderdauer_wirkt_nur_noch_abregelung(
        self, project, ga_mit_negstunden
    ):
        """Nach der Foerderdauer ist der Satz ohnehin der Marktwert: Im
        MARKTWERT-Modus gibt es dann keinen Abzug mehr, im
        ABREGELUNG-Modus entfaellt die Menge weiterhin."""
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        voll = run_valuation(project, ga_mit_negstunden).cashflow.data
        jahr21_voll = voll.loc[voll["jahr"] == 21, "erloes_eur"].iloc[0]
        assert jahr21_voll == pytest.approx(1e6 * 4.0 / 100)

        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        abgeregelt = run_valuation(project, ga_mit_negstunden).cashflow.data
        jahr21_ab = abgeregelt.loc[abgeregelt["jahr"] == 21, "erloes_eur"].iloc[0]
        assert jahr21_ab == pytest.approx(1e6 * 0.9 * 4.0 / 100)

    def test_marktwert_modus_erhoeht_irr(self, project, ga_mit_negstunden):
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        irr_ab = run_valuation(project, ga_mit_negstunden).kpis.equity_irr
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        irr_mw = run_valuation(project, ga_mit_negstunden).kpis.equity_irr
        assert irr_mw > irr_ab


class TestNpvAt:
    def test_npv_at_standardsatz_entspricht_kpi(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        assert npv_at(result.cashflow, 0.08) == pytest.approx(result.kpis.npv_eur)

    def test_npv_at_liegt_auf_der_npv_kurve(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        for _, row in result.npv_curve.iloc[::5].iterrows():
            assert npv_at(result.cashflow, row["diskontsatz_pct"]) == pytest.approx(
                row["npv_eur"]
            )


class TestIoRoundtripNeueFelder:
    def test_excel_roundtrip_mit_nicht_defaults(self, global_assumptions):
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        global_assumptions.tilgungsfreies_anlaufjahr = True
        global_assumptions.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        geladen = excel_to_global_assumptions(
            global_assumptions_to_excel(global_assumptions)
        )
        assert geladen.tilgungsfreies_anlaufjahr is True
        assert geladen.negative_stunden_modus == NegativeStundenModus.MARKTWERT

    def test_yaml_roundtrip_mit_nicht_defaults(self, global_assumptions, tmp_path):
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        global_assumptions.tilgungsfreies_anlaufjahr = True
        global_assumptions.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(global_assumptions, pfad)
        geladen = load_global_assumptions_yaml(pfad)
        assert geladen == global_assumptions
