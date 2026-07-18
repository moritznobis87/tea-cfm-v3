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
