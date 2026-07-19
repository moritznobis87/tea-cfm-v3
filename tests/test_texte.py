"""
Tests der zentralen Textverwaltung (texte.py): Laden/Zusammenfuehren
der YAML-Dateien je Sprache, Schluessel-Fallback (Zielsprache -> Deutsch
-> Schluesselname), Platzhalter-Formatierung und die Excel-spezifische
Sicht excel_texte() ohne "excel."-Prefix.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

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

    def test_englisch_fehlender_schluessel_faellt_auf_deutsch_zurueck(
        self, tmp_path, monkeypatch
    ):
        """Simuliert eine unvollstaendige Uebersetzung ueber ein
        isoliertes, synthetisches locales-Verzeichnis (unabhaengig vom
        tatsaechlichen Vollstaendigkeitsgrad der ausgelieferten
        Sprachdateien): fehlt ein Schluessel in der Zielsprache, greift
        automatisch der deutsche Text."""
        import texte

        (tmp_path / "de").mkdir()
        (tmp_path / "de" / "test.yaml").write_text(
            "a: Deutscher Text A\nb: Deutscher Text B\n", encoding="utf-8"
        )
        (tmp_path / "xx").mkdir()
        (tmp_path / "xx" / "test.yaml").write_text(
            "a: XX Text A\n", encoding="utf-8"  # 'b' bewusst nicht uebersetzt
        )
        monkeypatch.setattr(texte, "LOCALES_DIR", tmp_path)
        monkeypatch.setenv("TEA_SPRACHE", "xx")
        texte.lade_texte.cache_clear()
        assert texte.txt("test.a") == "XX Text A"
        assert texte.txt("test.b") == "Deutscher Text B"
        texte.lade_texte.cache_clear()

    def test_alle_ausgelieferten_sprachen_vollstaendig(self):
        """Die vier gepflegten Sprachen (de/en/fr/es) uebersetzen jeden
        deutschen Schluessel vollstaendig - kein Schluessel fehlt und
        keine Platzhalter weichen ab (Qualitaetssicherung der
        Uebersetzungsdateien selbst, unabhaengig vom Fallback-
        Mechanismus)."""
        import re

        import yaml

        from texte import LOCALES_DIR, SPRACHEN

        def platzhalter(text: str) -> set[str]:
            return set(re.findall(r"\{(\w+)\}", text))

        for datei in ("oberflaeche", "diagramme", "bericht", "excel"):
            de = yaml.safe_load((LOCALES_DIR / "de" / f"{datei}.yaml").read_text())
            for code in SPRACHEN:
                pfad = LOCALES_DIR / code / f"{datei}.yaml"
                assert pfad.exists(), pfad
                inhalt = yaml.safe_load(pfad.read_text())
                assert set(inhalt) == set(de), f"{code}/{datei}: Schlüssel weichen ab"
                for schluessel, text_de in de.items():
                    assert platzhalter(text_de) == platzhalter(inhalt[schluessel]), (
                        f"{code}/{datei}.{schluessel}: Platzhalter weichen ab"
                    )


class TestSprachdropdownEndToEnd:
    """End-to-End-Tests des Sprach-Dropdowns oben rechts in der
    laufenden Streamlit-App (streamlit_app.py): Umschalten wirkt sofort
    auf Navigation, Buttons und den PDF-Export."""

    _NAV_ERWARTET = {
        "de": ["Portfolio", "Neues Projekt", "Ausschreibung", "Globale Annahmen"],
        "en": ["Portfolio", "New Project", "Auction", "Global Assumptions"],
        "fr": ["Portefeuille", "Nouveau projet", "Appel d'offres",
               "Hypothèses globales"],
        "es": ["Cartera", "Nuevo proyecto", "Subasta", "Supuestos globales"],
    }

    @pytest.mark.parametrize("code", ["de", "en", "fr", "es"])
    def test_dropdown_uebersetzt_navigation(self, code):
        """Jede Sprache einzeln, mit frischer AppTest-Instanz (mehrfaches
        Umschalten in derselben Session ist eine Einschraenkung des
        Streamlit-Testframeworks selbst, nicht der App - siehe
        docs/AppTest format_func caching)."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "streamlit_app.py"),
            default_timeout=300,
        )
        at.run()
        assert not at.exception
        if code != "de":
            knopf = [
                b for b in at.button if b.key == f"sprachauswahl_{code}"
            ][0]
            knopf.click()
            at.run()
            assert not at.exception
        assert at.sidebar.radio[0].options == self._NAV_ERWARTET[code]

    def test_pdf_export_folgt_gewaehlter_sprache(self):
        """Der PDF-Bericht wird in der ueber das Dropdown gewaehlten
        Sprache erzeugt - Button-Label, Kapitelueberschrift und
        Kapitel-8-Fliesstext."""
        import io

        from pypdf import PdfReader
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "streamlit_app.py"),
            default_timeout=300,
        )
        at.run()
        [b for b in at.button if b.key == "sprachauswahl_en"][0].click()
        at.run()
        assert not at.exception

        [b for b in at.button if b.key and b.key.startswith("open_")][0].click()
        at.run()
        assert not at.exception
        pdf_btn = [b for b in at.button if "PDF" in (b.label or "")][0]
        assert pdf_btn.label == "Create PDF report"
        pdf_btn.click()
        at.run(timeout=300)
        assert not at.exception

        pdf_bytes = next(
            v for k, v in at.session_state.filtered_state.items()
            if k.startswith("pdf_bericht_") and v
        )
        text = "\n".join(
            s.extract_text() for s in PdfReader(io.BytesIO(pdf_bytes)).pages
        )
        assert "Management Summary" in text
        assert "EAG Auction Model" in text
        assert "Austria has been awarding the EAG market premium" in text

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


class TestWeitereSeitenUebersetzt:
    """Stichproben auf Seiten jenseits der Navigation/des PDF-Exports, die
    in einer nachtraeglichen, gruendlicheren Uebersetzungsrunde ergaenzt
    wurden (Formular, Ausschreibungsseite, Globale Annahmen, Sidebar)."""

    @pytest.mark.parametrize(
        "code,nav_code,erwartet",
        [
            ("es", "neu", "Crear nuevo proyecto"),
            ("es", "auktion", "Simulación de subasta EAG"),
            ("fr", "annahmen", "Scénarios de prix de marché"),
            ("en", "neu", "Create new project"),
        ],
    )
    def test_seite_uebersetzt(self, code, nav_code, erwartet, monkeypatch):
        """Sprache ueber TEA_SPRACHE statt Dropdown gesetzt: isoliert die
        eigentliche Frage (rendert die Seite korrekt uebersetzt?) von der
        Dropdown-Rerun-Mechanik, die bereits separat in
        TestSprachdropdownEndToEnd geprueft ist. Zwei Runs kurz
        hintereinander (Dropdown+Rerun mitten im Skript) bringen AppTests
        interne Widget-Serialisierung sonst durcheinander (reines
        Testframework-Artefakt, siehe dortige Erklaerung)."""
        from streamlit.testing.v1 import AppTest

        import texte

        monkeypatch.setenv("TEA_SPRACHE", code)
        texte.lade_texte.cache_clear()
        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "streamlit_app.py"),
            default_timeout=300,
        )
        at.run()
        assert not at.exception
        at.sidebar.radio[0].set_value(nav_code)
        at.run()
        assert not at.exception, at.exception
        texte_ = " ".join(m.value for m in at.markdown if m.value)
        texte_ += " ".join(s.value for s in at.subheader if s.value)
        if at.expander:
            texte_ += " ".join(e.label or "" for e in at.expander)
        assert erwartet in texte_, f"'{erwartet}' nicht gefunden für {code}/{nav_code}"

    def test_sidebar_uebersetzt(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "streamlit_app.py"),
            default_timeout=300,
        )
        at.run()
        assert not at.exception
        [b for b in at.button if b.key == "sprachauswahl_en"][0].click()
        at.run()
        assert not at.exception
        labels = [e.label for e in at.sidebar.expander]
        assert any("Save / restore projects" in (lbl or "") for lbl in labels)
        assert any("Save / restore global assumptions" in (lbl or "") for lbl in labels)


class TestFlaggenIcons:
    """Regressionstest fuer den Wechsel von Emoji-Flaggen (nicht auf
    allen Systemen/Browsern darstellbar, insbesondere Windows) auf
    echte Bild-Icons im Sprach-Popover."""

    def test_vier_flaggendateien_vorhanden_und_gueltig(self):
        from PIL import Image

        from app.config import FLAGS_DIR
        from texte import SPRACHEN

        for eintrag in SPRACHEN.values():
            pfad = FLAGS_DIR / f"{eintrag['flagge']}.png"
            assert pfad.exists(), pfad
            with Image.open(pfad) as bild:
                assert bild.format == "PNG"
                assert bild.width > 0 and bild.height > 0

    def test_popover_zeigt_flaggenbilder_und_schaltet_um(self):
        """5 Bilder im Baum (1 Logo + 4 Flaggen) belegen, dass echte
        Bild-Icons statt Emoji im Popover eingebettet sind; die
        Sprachumschaltung per Button-Klick funktioniert weiterhin."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "streamlit_app.py"),
            default_timeout=300,
        )
        at.run()
        assert not at.exception
        assert len(list(at.image)) == 5

        sprach_buttons = [
            b for b in at.button if b.key and b.key.startswith("sprachauswahl_")
        ]
        assert len(sprach_buttons) == 4
        assert {b.key for b in sprach_buttons} == {
            "sprachauswahl_de", "sprachauswahl_en",
            "sprachauswahl_fr", "sprachauswahl_es",
        }

        [b for b in at.button if b.key == "sprachauswahl_en"][0].click()
        at.run()
        assert not at.exception
        assert "New Project" in at.sidebar.radio[0].options
