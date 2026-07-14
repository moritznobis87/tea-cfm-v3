"""Tests fuer Zeitachse, Energieproduktion und Betriebskosten."""

from __future__ import annotations

from datetime import date

import pytest

from engine import OpexItem
from engine.energy import calculate_energy_production
from engine.opex import calculate_opex
from engine.pipeline import resolve_assumptions
from engine.timeline import build_timeline


class TestTimeline:
    def test_jahresstart_januar_hat_volle_prorata(self):
        timeline = build_timeline(date(2027, 1, 1), 3)
        assert len(timeline) == 3
        assert timeline["pro_rata_faktor"].iloc[0] == pytest.approx(1.0)
        assert bool(timeline["ist_letztes_jahr"].iloc[-1]) is True

    def test_unterjaehriger_start_hat_anteiliges_erstes_jahr(self):
        # Start 1. Juli -> zweites Halbjahr = 184 Tage.
        timeline = build_timeline(date(2027, 7, 1), 2)
        assert timeline["pro_rata_faktor"].iloc[0] == pytest.approx(184 / 365)
        assert timeline["pro_rata_faktor"].iloc[1] == pytest.approx(1.0)

    def test_laufzeit_null_wird_abgelehnt(self):
        with pytest.raises(ValueError):
            build_timeline(date(2027, 1, 1), 0)


class TestEnergy:
    def test_produktion_ohne_degradation(self, project, global_assumptions):
        assumptions = resolve_assumptions(project, global_assumptions)
        timeline = build_timeline(date(2027, 1, 1), 3)
        energy = calculate_energy_production(timeline, assumptions)
        # 1.000 kWp * 1.000 kWh/kWp = 1 GWh in jedem vollen Jahr.
        assert energy["produktion_kwh"].tolist() == pytest.approx([1e6, 1e6, 1e6])

    def test_degradation_wirkt_ab_jahr_zwei(self, project, global_assumptions):
        global_assumptions.degradation_pct_pa = 0.005
        assumptions = resolve_assumptions(project, global_assumptions)
        timeline = build_timeline(date(2027, 1, 1), 3)
        energy = calculate_energy_production(timeline, assumptions)
        assert energy["produktion_kwh"].iloc[0] == pytest.approx(1e6)
        assert energy["produktion_kwh"].iloc[1] == pytest.approx(1e6 * 0.995)
        assert energy["produktion_kwh"].iloc[2] == pytest.approx(1e6 * 0.995**2)


class TestOpex:
    def test_indexierung_startet_ab_konfiguriertem_jahr(self):
        timeline = build_timeline(date(2027, 1, 1), 3)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1, 2, 3], "produktion_kwh": [0.0, 0.0, 0.0]})
        items = [
            OpexItem(
                name="Wartung", basiswert_eur_kwp=2.0,
                index_pct_pa=0.02, indexierung_ab_jahr=2,
            )
        ]
        opex = calculate_opex(timeline, items, 1000.0, energy)
        # Jahr 1 und 2: Basis 2.000 €; ab Jahr 3 ein Indexschritt.
        assert opex["Wartung"].iloc[0] == pytest.approx(2000.0)
        assert opex["Wartung"].iloc[1] == pytest.approx(2000.0)
        assert opex["Wartung"].iloc[2] == pytest.approx(2000.0 * 1.02)

    def test_gleichnamige_positionen_werden_addiert(self):
        timeline = build_timeline(date(2027, 1, 1), 1)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1], "produktion_kwh": [0.0]})
        items = [
            OpexItem(name="Pacht", basiswert_eur_kwp=1.0),
            OpexItem(name="Pacht", basiswert_eur_kwp=2.0),
        ]
        opex = calculate_opex(timeline, items, 1000.0, energy)
        assert opex["Pacht"].iloc[0] == pytest.approx(3000.0)
        # Nur EINE Spalte je Bezeichnung (eindeutiger Legendeneintrag).
        assert list(opex.columns).count("Pacht") == 1

    def test_produktionsbasierte_abgaben(self):
        timeline = build_timeline(date(2027, 1, 1), 1)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1], "produktion_kwh": [1e6]})
        opex = calculate_opex(
            timeline, [], 1000.0, energy,
            gemeindeabgabe_eur_kwh=0.002,
            direktvermarktungskosten_eur_kwh=0.001,
        )
        assert opex["gemeindeabgabe_eur"].iloc[0] == pytest.approx(2000.0)
        assert opex["direktvermarktungskosten_eur"].iloc[0] == pytest.approx(1000.0)
        assert opex["opex_gesamt_eur"].iloc[0] == pytest.approx(3000.0)
