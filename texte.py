"""
Zentrale Textverwaltung (Sprachdateien).

Alle sichtbaren Texte der Anwendung liegen in YAML-Dateien unter
locales/<sprache>/ und sind dort nach Textgattung aufgeteilt:

    oberflaeche.yaml  Kurze UI-Texte: Navigation, Buttons, Labels,
                      Abschnittstitel, Hilfe- und Hinweistexte der Views
    diagramme.yaml    Diagrammtitel, Achsen, Legenden, Hover-Texte
    bericht.yaml      Freitext des PDF-Berichts (Kapitel, Absaetze,
                      Abbildungs-/Tabellenunterschriften)
    excel.yaml        Beschriftungen des Excel-Ergebnisexports

Zugriff ueber txt("<datei>.<schluessel>", platzhalter=wert). Platzhalter
stehen in den Texten als {name} (inkl. Formatangaben wie {wert:,.2f});
Texte ohne uebergebene Platzhalter werden unveraendert zurueckgegeben,
so dass geschweifte Klammern (z. B. Plotly-Hovertemplates) unkritisch
sind.

Sprachwahl: Umgebungsvariable TEA_SPRACHE (Standard "de"). Eine
Uebersetzung entsteht durch Kopieren des Ordners locales/de nach z. B.
locales/en und Uebersetzen der Werte; fehlende Schluessel fallen
automatisch auf Deutsch zurueck, ganz fehlende Schluessel liefern den
Schluesselnamen (fail-soft, kein Absturz durch Luecken).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
STANDARD_SPRACHE = "de"


def aktive_sprache() -> str:
    return os.environ.get("TEA_SPRACHE", STANDARD_SPRACHE).strip() or STANDARD_SPRACHE


@lru_cache(maxsize=4)
def lade_texte(sprache: str) -> dict[str, str]:
    """Laedt alle YAML-Dateien einer Sprache in einen flachen Namensraum
    '<dateistamm>.<schluessel>' -> Text."""
    texte: dict[str, str] = {}
    ordner = LOCALES_DIR / sprache
    if not ordner.is_dir():
        return texte
    for datei in sorted(ordner.glob("*.yaml")):
        inhalt = yaml.safe_load(datei.read_text(encoding="utf-8")) or {}
        for schluessel, wert in inhalt.items():
            texte[f"{datei.stem}.{schluessel}"] = str(wert)
    return texte


def txt(schluessel: str, /, **platzhalter) -> str:
    """Liefert den Text zum Schluessel in der aktiven Sprache; faellt je
    Schluessel auf Deutsch und zuletzt auf den Schluessel selbst
    zurueck. Platzhalter werden per str.format eingesetzt."""
    sprache = aktive_sprache()
    text = lade_texte(sprache).get(schluessel)
    if text is None and sprache != STANDARD_SPRACHE:
        text = lade_texte(STANDARD_SPRACHE).get(schluessel)
    if text is None:
        return schluessel
    if platzhalter:
        try:
            return text.format(**platzhalter)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def excel_texte() -> dict[str, str]:
    """Beschriftungen fuer den Excel-Ergebnisexport (Engine-Schicht):
    Schluessel ohne Dateiprefix, wie von engine.io_ergebnis_excel
    erwartet."""
    prefix = "excel."
    sprache = aktive_sprache()
    zusammen = dict(lade_texte(STANDARD_SPRACHE))
    if sprache != STANDARD_SPRACHE:
        zusammen.update(lade_texte(sprache))
    return {
        k[len(prefix):]: v for k, v in zusammen.items() if k.startswith(prefix)
    }
