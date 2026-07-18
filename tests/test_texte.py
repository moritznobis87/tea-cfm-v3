"""
Tests der zentralen Textverwaltung (texte.py): Laden/Zusammenfuehren
der YAML-Dateien je Sprache, Schluessel-Fallback (Zielsprache -> Deutsch
-> Schluesselname), Platzhalter-Formatierung und die Excel-spezifische
Sicht excel_texte() ohne "excel."-Prefix.
"""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _frische_sprache():
    """Sprachwahl je Test isolieren (Umgebungsvariable + Cache)."""
    alt = os.environ.get("TEA_SPRACHE")
    yield
    if alt is None:
        os.environ.pop("TEA_SPRACHE", None)
    else:
        os.environ["TEA_SPRACHE"] = alt
    import texte

    texte.lade_texte.cache_clear()


def _setze_sprache(sprache: str | None):
    import texte

    if sprache is None:
        os.environ.pop("TEA_SPRACHE", None)
    else:
        os.environ["TEA_SPRACHE"] = sprache
    texte.lade_texte.cache_clear()
    importlib.reload(texte)
    return texte


class TestSpracheUndFallback:
    def test_standardsprache_deutsch(self):
        t = _setze_sprache(None)
        assert t.aktive_sprache() == "de"
        assert t.txt("oberflaeche.nav_portfolio") == "Portfolio"

    def test_alle_deutschen_dateien_geladen(self):
        t = _setze_sprache("de")
        geladen = t.lade_texte("de")
        for datei in ("oberflaeche", "diagramme", "bericht", "excel"):
            assert any(k.startswith(f"{datei}.") for k in geladen), datei

    def test_englisch_vorhandener_schluessel(self):
        t = _setze_sprache("en")
        assert t.txt("oberflaeche.nav_neues_projekt") == "New Project"

    def test_englisch_fehlender_schluessel_faellt_auf_deutsch_zurueck(self):
        t = _setze_sprache("en")
        # Nur eine Teilmenge ist in locales/en gepflegt (Demo-Datei);
        # alles Weitere muss automatisch aus locales/de kommen.
        assert t.txt("oberflaeche.btn_pdf_bericht") == "PDF-Bericht erstellen"

    def test_voellig_unbekannter_schluessel_liefert_schluessel(self):
        t = _setze_sprache("de")
        assert t.txt("oberflaeche.gibt_es_nicht") == "oberflaeche.gibt_es_nicht"

    def test_nicht_existierende_sprache_faellt_komplett_auf_deutsch(self):
        t = _setze_sprache("xx")
        assert t.txt("oberflaeche.nav_portfolio") == "Portfolio"


class TestPlatzhalter:
    def test_platzhalter_werden_eingesetzt(self):
        t = _setze_sprache("de")
        ergebnis = t.txt("oberflaeche.portfolio_toggle_inaktive", anzahl=3)
        assert "3" in ergebnis and "{anzahl}" not in ergebnis

    def test_ohne_platzhalter_bleibt_text_unveraendert(self):
        t = _setze_sprache("de")
        # Text ohne {..}-Platzhalter: keine Formatierung noetig, auch
        # wenn geschweifte Klammern (z. B. aus Hovertemplates) vorkaemen.
        assert t.txt("oberflaeche.btn_speichern") == "Speichern"

    def test_fehlender_platzhalter_wirft_nicht(self):
        t = _setze_sprache("de")
        # Fail-soft: falscher/fehlender Platzhaltername darf nicht crashen.
        ergebnis = t.txt("oberflaeche.portfolio_toggle_inaktive", falsch=1)
        assert "{anzahl}" in ergebnis


class TestExcelTexte:
    def test_prefix_wird_entfernt(self):
        t = _setze_sprache("de")
        flach = t.excel_texte()
        assert "blatt_uebersicht" in flach
        assert flach["blatt_uebersicht"] == "Übersicht"
        assert not any(k.startswith("excel.") for k in flach)

    def test_verwendung_in_io_ergebnis_excel(self):
        from engine.io_ergebnis_excel import _t

        _setze_sprache("de")
        assert _t("kpi_nennleistung") == "Nennleistung"
        assert "300" in _t("sektion_monte_carlo", n_mc=300)


class TestBerichtKapitel8Ausgelagert:
    """Die zuvor als bekannte Luecke dokumentierten Fliesstext-Absaetze
    aus PDF-Kapitel 8 sind jetzt vollstaendig in bericht.yaml ausgelagert
    und mit Platzhaltern fuer die eingesetzten Kennzahlen versehen."""

    def test_alle_kapitel8_schluessel_vorhanden(self):
        t = _setze_sprache("de")
        schluessel = (
            "abschnitt_auktion_fitting", "auktion_historie_intro",
            "auktion_historie_unterzeichnet", "auktion_historie_wettbewerb",
            "abb_14_caption", "auktion_fitting_intro", "abb_15_caption",
            "modell_verteilungsfamilie", "modell_kalibrierung",
            "modell_punktprognose_intro", "modell_punktprognose_ergebnis",
            "modell_unsicherheit_intro", "modell_zuschlagsdichte_intro",
            "abb_16_caption", "abb_17_caption",
            "tab_3_spalte_wahrscheinlichkeit", "tab_3_spalte_gebotswert",
            "tab_3_caption",
        )
        for s in schluessel:
            text = t.txt(f"bericht.{s}")
            assert text and text != f"bericht.{s}", s

    def test_platzhalter_werden_korrekt_eingesetzt(self):
        t = _setze_sprache("de")
        text = t.txt("bericht.auktion_historie_intro", n_runden=15,
                     erste_datum="12/2022")
        assert "15 Runden seit 12/2022" in text
        text2 = t.txt("bericht.abb_16_caption", grenzzuschlag_ct="6,65 ct/kWh",
                      projektwert_ct="6,50 ct/kWh")
        assert "6,65 ct/kWh" in text2 and "6,50 ct/kWh" in text2

    def test_formel_zeile_platzhalter(self):
        t = _setze_sprache("de")
        text = t.txt("bericht.modell_punktprognose_ergebnis",
                     formel_zeile="Test-Stützstellen: 1 → 2 ct.")
        assert text.endswith("Test-Stützstellen: 1 → 2 ct.")

    def test_report_nutzt_ausgelagerte_texte(self):
        """Der generierte PDF-Bericht enthaelt die ausgelagerten Absaetze
        unveraendert (End-to-End ueber den bestehenden Berichts-Service)."""
        import io

        from pypdf import PdfReader

        from app import services

        _setze_sprache("de")
        pdf = services.build_project_report("template-agri", 0.08)
        text = "\n".join(
            s.extract_text() for s in PdfReader(io.BytesIO(pdf)).pages
        )
        assert "Österreich vergibt die EAG-Marktprämie" in text
        assert "Seit Juli 2025 ist das Bild gekippt" in text
