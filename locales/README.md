# Sprachdateien (locales/)

Alle sichtbaren Texte der Anwendung liegen hier als YAML, aufgeteilt
nach Textgattung – nicht in einer einzigen riesigen Datei, damit
verschiedene Änderungen sich nicht in die Quere kommen (z. B. jemand
tippt UI-Buttons um, während jemand anders am PDF-Berichtstext
schreibt) und damit die Dateien überschaubar bleiben:

| Datei              | Inhalt                                                              | Konsumiert von            |
|--------------------|----------------------------------------------------------------------|----------------------------|
| `oberflaeche.yaml` | Navigation, Buttons, Badges, Abschnittstitel, Hinweistexte der Views | `app/` (Streamlit-Views)   |
| `diagramme.yaml`   | Diagrammtitel, Achsenbeschriftungen, Legendennamen, Annotationen     | `app/components/charts.py` |
| `bericht.yaml`     | Kapitel-/Abschnittsüberschriften des PDF-Berichts                    | `app/report.py`            |
| `excel.yaml`       | Blatt-/Spalten-/Diagrammbeschriftungen des Pipeline-Excel-Exports    | `engine/io_ergebnis_excel.py` |

## Verwendung im Code

```python
from texte import txt

st.button(txt("oberflaeche.btn_loeschen"))
txt("oberflaeche.portfolio_toggle_inaktive", anzahl=3)  # Platzhalter {anzahl}
```

In der Engine-Schicht (kein Streamlit, kein Import aus `app/`) gibt es
den schlanken Wrapper `excel_texte()` bzw. das `_t(...)`-Hilfsfunktion
in `engine/io_ergebnis_excel.py`.

## Eine neue Sprache anlegen

1. Ordner kopieren: `locales/de` → `locales/en` (oder beliebiges
   Kürzel).
2. Werte in den YAML-Dateien übersetzen (Schlüssel unverändert lassen).
3. Aktivieren über die Umgebungsvariable `TEA_SPRACHE=en` (z. B. in
   `.streamlit/secrets.toml`, im Deployment oder lokal vor dem Start).

Eine Übersetzung muss nicht vollständig sein: Fehlt ein Schlüssel in
der Zielsprache, greift automatisch der deutsche Text; fehlt er auch
dort (Tippfehler o. Ä.), wird der Schlüsselname selbst angezeigt statt
eines Absturzes. `locales/en/oberflaeche.yaml` ist bewusst nur
teilweise befüllt und demonstriert genau dieses Verhalten.

## Texte ändern/erweitern

Einfach den Wert in der passenden YAML-Datei bearbeiten – kein
Code-Deployment nötig, kein Python-Wissen erforderlich. Neue Texte
brauchen einen neuen, sprechenden Schlüssel (Konvention:
`bereich_beschreibung`, z. B. `btn_pdf_bericht`) und werden im Code per
`txt("<datei>.<schluessel>")` abgerufen. Texte mit eingesetzten
Kennzahlen (z. B. Bildunterschriften im PDF-Bericht) verwenden
`{platzhalter}` in der YAML-Datei und werden per
`txt("<schluessel>", platzhalter=wert)` aufgerufen – siehe
`bericht.yaml` (Kapitel 8) für ein durchgängiges Beispiel mit mehreren
Absätzen und dynamischen Werten (Rundenanzahl, Daten, Kennzahlen).

Damit sind sämtliche sichtbaren Texte der Anwendung ausgelagert – UI,
Diagramme, PDF-Bericht (inklusive der mehrsätzigen Fließtext-Absätze
in Kapitel 8) und der Excel-Ergebnisexport.
