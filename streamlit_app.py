# Changelog

## v4.0 – EAG-Ausschreibungsmodul: Gebotsverteilung & Zuschlagswahrscheinlichkeit (2026-07)

### Neues Modul (Price-Taker-Modell)
- Neue Seite **"Ausschreibung"**: Analyse aller 15 historischen
  EAG-Marktprämienausschreibungen PV (2022–2026, `data/ausschreibungen.yaml`
  aus EAG.xlsx), Prognose der Gebotsverteilung der nächsten Runde und
  Ableitung des empfohlenen Gebots je gewünschter
  Zuschlagswahrscheinlichkeit (50–95 %).
- Statistischer Kern (`engine/auktion.py`): Je Runde wird eine auf
  [0, Preisobergrenze] beschränkte **Beta-Verteilung** über zwei
  Bedingungen kalibriert (mengengewichteter Ø-Zuschlag; Minimum als
  2 %-Quantil). Modellvergleich gegen Kumaraswamy und trunkierte
  Normalverteilung; Leave-one-out-Validierung über die vier
  Wettbewerbsrunden inkl. naiver Basislinie.
- Wettbewerbs-Link datengetrieben: logit(Lage) und ln(Konzentration)
  linear auf ln(Wettbewerbsquote r) regressiert; für überzeichnete
  Runden ist r latent (Gebotsvolumen wird von der OeMAG nicht
  veröffentlicht) und wird aus dem Abstand Grenzzuschlag ↔ Obergrenze
  rückgeschätzt.
- Prognose: 4.000 Auktionswelten (r ~ Lognormal, Residuen-Bootstrap)
  liefern die prädiktive Verteilung des Grenzzuschlags;
  P(Zuschlag | Gebot) = P(Grenzzuschlag > Gebot); Empfehlung =
  (1−Ziel)-Quantil.

### Integration ins Cashflow-Modell
- Der empfohlene Gebotswert wird neuen Projekten automatisch als
  EAG-Zuschlagswert vorbelegt (manuell überschreibbar) und kann per
  Button in ein bestehendes Projekt übernommen werden.
- Monte-Carlo-Tab: neuer Schalter "EAG-Zuschlagswert aus dem
  Ausschreibungsmodell ziehen" – je Lauf wird ein zufälliges
  erfolgreiches Gebot der prognostizierten Auktion gezogen
  (`run_monte_carlo(..., gebot_ziehungen=...)`); der
  Konventionell-Abschlag bleibt erhalten. Alle übrigen Funktionen des
  Cashflow-Modells sind unverändert.
- 17 neue Tests (Regime, Kalibrierbedingungen, Verteilungs-
  eigenschaften, Link-Richtungen, Monotonie, Reproduzierbarkeit,
  MC-Integration); Suite: 115 Tests.

## v3.9 – Bugfix: Download-Dateiname nach Umbenennen (2026-07)

- Behoben: Nach Duplizieren und Umbenennen eines Projekts zeigte der
  PDF- und Excel-Download-Dateiname weiterhin den ursprünglichen Namen
  (z.B. "template-agri_bericht.pdf"), obwohl Berichtstitel und
  Projektname im Dashboard bereits korrekt aktualisiert waren.
- Ursache: Die interne Projekt-ID (Dateiname der YAML-Datei) wird bei
  Anlage/Duplizierung einmalig aus dem Namen abgeleitet und bleibt
  danach bewusst stabil, damit Umbenennen nicht versehentlich die Datei
  wechselt. Die Download-Dateinamen folgten fälschlich dieser
  eingefrorenen ID statt dem aktuellen Namen.
- Fix: PDF- und Excel-Download-Dateinamen werden jetzt bei jedem
  Download frisch aus dem aktuellen Projektnamen abgeleitet
  (`services.slugify()`); die interne ID/Dateiidentität bleibt
  unverändert stabil. 2 neue Tests; Suite: 98 Tests.

## v3.8 – PDF-Ergebnisbericht (2026-07)

- Neuer Button "PDF-Bericht erstellen" im Projekt-Dashboard: erzeugt
  einen herunterladbaren Ergebnisbericht im Gutachtenstil (A4,
  Trianel-Branding, Kopf-/Fußzeilen mit Seitenzahlen, ca. 15 Seiten).
- Aufbau: Deckblatt mit Logo, Projektsteckbrief und Disclaimer ·
  Inhaltsverzeichnis · Management Summary mit KPI-Kacheln und
  Kernaussagen · Ergebnisrechnung (Wertbrücke, Cashflow-Tabelle) ·
  Erlöse & Förderung (Vergütungssatz/Marktwert, Markterlös vs. Prämie) ·
  Finanzierung (DSCR, Schuldenprofil, Kapital-/Investitionsstruktur,
  NPV-Kurve) · Sensitivität (Tornado, EAG-Varianten, Break-even-Gebot) ·
  Risikoanalyse (Monte Carlo, 400 Läufe mit dokumentierten
  Standardparametern) · Szenarienvergleich · Annex A (vollständig
  aufgelöste Annahmen, OPEX- und CAPEX-Positionen) · Annex B (alle
  verwendeten Zeitreihen: Marktwerte real/nominal, Erzeugungsmengen
  6h/1h, Marktwertübersicht aller Szenarien).
- NPV, LCOE und MC-NPV im Bericht folgen dem im Dashboard gewählten
  Diskontsatz; Zielrendite für Break-even und Erfolgswahrscheinlichkeit:
  8,0 %. Diagramme als hochauflösende Grafiken im Markenstil
  (druckfähig); Bericht wird beim Bearbeiten des Projekts automatisch
  invalidiert.
- Technik: reiner Generator ohne Streamlit-Abhängigkeit
  (app/report.py, ReportLab + Matplotlib – neue Abhängigkeiten in
  requirements.txt); 3 neue Tests (Struktur, Kapitel, Metadaten);
  Suite: 96 Tests.

## v3.7 – Investkosten: Widmung & Genehmigung (2026-07)

- Zwei neue Positionen in den Investkosten (Details), direkt nach der
  Trasse: **Widmung** (Vorbelegung 1 €/kWp bzw. 10.000 € im
  Absolut-Modus) und **Genehmigung** (8 €/kWp bzw. 80.000 €). Die
  Vorbelegung folgt damit erstmals der gewählten Eingabe-Einheit statt
  aus dem Absolutwert abgeleitet zu werden.
- Beide Positionen fließen in CAPEX-Summe, Finanzierung, KPI-Kachel und
  den Investitionsstruktur-Donut ein und sind Teil des
  Excel-Roundtrips (ältere Projekt-Exporte ohne die Spalten laden mit
  0 €).
- Bestehende Projekte bleiben unverändert (beide Positionen 0 €).

## v3.6 – Szenario-Reihenfolge & EAG-Default (2026-07)

- Szenario-Reihenfolge: alle Aurora-Szenarien zuerst (Aurora 6/26 bleibt
  Standard-Vorauswahl), Enervis 2025 ans Ende – gilt für Szenario-Tabs,
  Projektauswahl und Excel-Export.
- EAG-Zuschlagswert: Vorbelegung für neue Projekte jetzt 6,5 ct/kWh
  (vorher 7,2); die beiden Template-Projekte wurden ebenfalls auf
  6,5 ct/kWh gesetzt. Bestehende eigene Projekte bleiben unverändert.

## v3.5 – Negativmengen je Regel (6h/1h) & Aurora 6/26 (2026-07)

### Fachlich
- Die Größe heißt jetzt korrekt **"Erzeugungsmenge neg. Stunden"**: der
  Anteil der PV-Jahreserzeugung, der in Zeiten negativer Preise anfällt
  (nicht der Stundenanteil).
- Jedes Marktpreisszenario führt zwei getrennte Zeitreihen: **6h-Regel**
  (Prämienentfall erst ab mindestens 6 Stunden am Stück negativer
  Preise; Standard Österreich/EAG) und **1h-Regel** (bereits ab 1 Stunde
  am Stück; Regelung Deutschland). Global wählbar unter Globale
  Annahmen → Marktpreisszenarien; Standard: 6h.
- Neues Standardszenario **Aurora 6/26** (Marktwerte und getrennte
  6h/1h-Negativmengen 2027–2060 aus der Marktpreisstudie; 2025/2026 mit
  den 2027-Werten aufgefüllt). Es steht an erster Stelle und ist damit
  die Vorauswahl für neue Projekte; bestehende Projekte behalten ihr
  zugewiesenes Szenario.
- Bestehende Szenarien: die bisherige (einzelne) Zeitreihe wurde in
  beide Regel-Spalten übernommen.

### Kompatibilität
- Ältere YAML-Datenstände und Excel-Importe mit nur einer
  Negativ-Spalte ("Anteil neg. Stunden (%)") laden weiter: der Wert
  wird automatisch für beide Regeln übernommen.
- Excel-Export der Globalen Annahmen enthält jetzt beide Spalten sowie
  die gewählte Regel; der aufgelöste Parametersatz im Annahmen-Tab
  weist die Regel aus.
- 7 neue Tests (Regelwirkung auf Erlöse/IRR, exakte Kurvenwahl,
  Legacy-Migration, Excel-Roundtrip, Aurora-6/26-Stützwerte); Suite:
  90 Tests.

## v3.4 – Kompaktere Übersicht (2026-07)

- KPI-Kachel "Investitionsvolumen" heißt jetzt "CAPEX"; die Leiste zeigt
  damit exakt: EK-Rendite, NPV, Min. DSCR, CAPEX, LCOE.
- Portfolio-Analytik (Rendite-Risiko-Landkarte, Ranking,
  Vergleichstabelle) liegt jetzt in einem zuklappbaren Bereich
  (Standard: eingeklappt) – die Pipelineübersicht startet kompakt.
- Hinweis: Cashflow-Sparkline und Payback waren bereits seit v3.2 aus
  den Projektkarten entfernt.

## v3.3 – Trianel-Rot erzwingen (2026-07)

- Ursache des hellen Streamlit-Rots (#FF4B4B): .streamlit/config.toml
  wird von Streamlit nur gelesen, wenn die App aus dem Projektordner
  gestartet wird. Die Theme-Optionen (primaryColor #BE172B, Inter als
  Fließ- und Überschriftenschrift) werden jetzt zusätzlich zur Laufzeit
  im Einstiegspunkt gesetzt und gelten damit unabhängig vom
  Startverzeichnis.
- CSS-Fallback für die sichtbarsten Akzentflächen (Primary-Buttons,
  Button-Hover/-Fokus, Tab-Akzentlinie, Slider-Griff und -Wertlabel,
  Links), damit auch der allererste Seitenaufbau nie im Standard-Rot
  erscheint.

## v3.2 – Aufgeräumte Kennzahlen & Direktvermarktungs-Modus (2026-07)

### Direktvermarktungskosten: absolut oder relativ zum Marktwert
- Neuer globaler Modus (Globale Annahmen → Betriebskosten): **Absoluter
  Betrag** (wie bisher, projektspezifisch in €/MWh, z.B. 1 €/MWh) oder
  **Relativ zum Marktwert** (globaler Prozentsatz, z.B. 10 % vom
  nominalen Jahresmarktwert je erzeugter kWh – die Kosten atmen mit dem
  Preisniveau).
- Im Relativ-Modus blendet das Projektformular die €/MWh-Eingabe aus und
  zeigt stattdessen den wirksamen Prozentsatz; der gespeicherte
  Projektwert bleibt für einen späteren Moduswechsel erhalten.
- Modus und Prozentsatz sind Teil des YAML- und Excel-Roundtrips
  (bestehende Dateien laden unverändert mit Modus "absolut").
- Fünf neue Tests (exakte Jahresformel, Unverändertheit des
  Absolut-Modus, IRR-Wirkung, YAML- und Excel-Roundtrip).

### Aufgeräumte Kennzahlen
- Projekt-Dashboard: eine KPI-Leiste mit EK-Rendite, NPV, min. DSCR,
  Investitionsvolumen und LCOE; entfernt: Payback, Eigenkapitaleinsatz,
  spezifisches Invest, Erzeugung Jahr 1, Erlöse gesamt.
- Projektkarten im Portfolio: ohne Cashflow-Sparkline und ohne Payback
  (Name, Typ-Badge, Leistung, IBN, EK-Rendite, EK-Einsatz).
- Letztes verbliebenes Icon im Projektformular entfernt.

## v3.1 – Design-Korrekturen (2026-07)

- Zurück zu Trianel-Rot als einzigem Markenakzent: Kopfzeilen-Band und
  KPI-Kachel-Akzent wieder in Rot statt Farbverlauf; Bernstein-Töne aus
  allen Diagrammen entfernt (Erlös-Split grün/neutral, Monte-Carlo-Fächer
  in Ink-Tönung, Heatmap rot/neutral/grün).
- Schriftart durchgängig Inter (fixiert über .streamlit/config.toml,
  primaryColor #BE172B); Space Grotesk entfernt.
- Tabs wieder im Streamlit-Standard (Akzentlinie in primaryColor) statt
  dunkel hinterlegter Pills.
- Abschnittstitel ohne Marker; sämtliche Icons/Emojis aus Navigation,
  Tabs, Buttons und Hinweistexten entfernt (Trianel-Logo/-Favicon bleibt).
- Standard-Zielrendite in Heatmap, Gebotsassistent und Monte-Carlo-
  Erfolgswahrscheinlichkeit: 8,0 %.

## v3.0 – Analyse-Studio & Sonnenband-Design (2026-07)

### Neue Fachfunktionen (engine/analytics.py)
- **Monte-Carlo-Simulation**: gleichzeitige Variation von Ertrag,
  Marktwert-Niveau, CAPEX und OPEX (Normalverteilung, einstellbare
  Sigmas, fester Seed, 200–1000 Läufe). Ergebnisse: IRR-Verteilung
  (P10/P50/P90), NPV-Verteilung, Erfolgswahrscheinlichkeit gegen eine
  Ziel-Rendite, P10–P90-Fächer des kumulierten Equity-Cashflows.
- **Tornado-Analyse**: Einzelvariation von sieben Werttreibern (±10 %)
  mit Wirkung auf die EK-Rendite, sortiert nach Spannweite.
- **IRR-Heatmap**: EK-Rendite über ein 7×7-Raster zweier frei wählbarer
  Treiber, divergierende Farbskala um die Ziel-IRR.
- **Gebotsassistent**: Break-even-EAG-Zuschlagswert (anzulegender Wert)
  für eine Ziel-EK-Rendite – Untergrenze für ein Auktionsgebot
  (Nullstellensuche per brentq, defensiv bei nicht berechenbarer IRR).
- **LCOE**: Stromgestehungskosten (diskontierte Vollkosten je
  diskontierter kWh, Act/365 analog XNPV).
- **Szenarienvergleich**: identisches Projekt über alle hinterlegten
  Marktpreisszenarien (IRR, NPV, kumulierte Cashflows).
- Erlös-Zeitreihe zusätzlich exakt aufgeteilt in **Markterlös** und
  **Marktprämie** (beide Negativstunden-Modi); `produktion_kwh` ist
  jetzt Teil der Cashflow-Zeitreihe (auch im Excel-Export).
- `run_valuation_from_assumptions()`: Bewertung direkt aus einem (ggf.
  mutierten) EffectiveAssumptions-Satz, optional ohne NPV-Kurve –
  Grundlage für die vielen Bewertungsläufe der Analytik.

### Neue UI
- **Projekt-Dashboard mit 7 Tabs**: Cashflow (inkl. Wertbrücke/
  Waterfall), Erlöse (Vergütungssatz vs. Marktwert, Markterlös vs.
  Prämie), Finanzierung (DSCR, Schuldenprofil, Kapital-/CAPEX-Donuts,
  NPV-Kurve), Sensitivität (Tornado, Heatmap, Gebotsassistent,
  EAG-Varianten), Monte Carlo (mit explizitem Start-Button, da Tabs
  eager rendern), Szenarien, Annahmen.
- **Zweite KPI-Leiste**: Payback, LCOE, spezifisches Invest,
  Erzeugung Jahr 1, Erlöse gesamt.
- **Portfolio-Analytik**: Rendite-Risiko-Landkarte (Bubble-Chart),
  Projekt-Ranking, Vergleichstabelle als Tabs; Projektkarten mit
  Cashflow-**Sparkline** (inline SVG), Typ-Badge und
  Auswahl-Hervorhebung.

### Design ("Sonnenband")
- Neue Dreiklang-Palette: Trianel-Rot (Interaktion), Solar-Bernstein
  (Erzeugung/Erlöse), Tannengrün-Ink (Finanzen/Struktur); Signatur-
  Verlaufband in Kopfzeile und KPI-Kacheln.
- Display-Schrift Space Grotesk (Überschriften, KPI-Werte, tabellarische
  Ziffern), Pill-Tabs, Hover-Mikrointeraktionen (mit
  prefers-reduced-motion-Fallback), Hero-Kopfzeile mit Untertitel.
- Plotly-Template v2: einheitliche Serienfarben, x-unified-Hover in
  Zeitreihen, divergierende Heatmap-Skala.

### Qualität
- 18 neue Tests (Analytik-Engine, Erlös-Split, Reproduzierbarkeit der
  Monte-Carlo-Simulation, Break-even-Zielerreichung, LCOE-Monotonie);
  Suite: 78 Tests, ruff clean.
- Analytik-Ergebnisse werden wie Bewertungen auf Datei-mtimes und
  Parameter gecacht und bei jedem Speichern/Löschen invalidiert.


## 2.2.0 – Neue Standards und Branding

- **Negativstunden-Modus**: „Rückfall auf Jahresmarktwert" ist jetzt der
  Standard und steht in der Auswahl an erster Stelle; „Abregelung"
  bleibt als Option erhalten. Die Engine-Einheitstests rechnen weiterhin
  explizit mit Abregelung (härteste Annahme, handgerechnete Werte).
- **Standard-Diskontsatz 8 %**: gilt konsistent für die NPV-KPI-Kachel
  (Voreinstellung des Eingabefelds), die KPI-Berechnung der Engine, die
  Portfoliotabelle („NPV bei 8 %") und den Excel-Export.
- **Logo/Favicon**: neues Trianel-Logo im Kopfbereich; für den
  Browser-Tab wird eine automatisch beschnittene, quadratische
  Logovariante erzeugt (assets/favicon.png), damit das Logo im Tab
  nicht in Leerfläche verschwindet.
- `st.components.v1.html` durch `st.iframe` ersetzt (Streamlit-
  Deprecation ab 06/2026); ausgelieferte global_assumptions.yaml
  enthält die neuen Felder jetzt explizit.

## 2.1.0 – Konfigurierbare Modelloptionen, KPI-Auto-Fit, NPV-Diskontsatz

Validiert gegen das Referenz-Excel „Tool_TEA_Buchkirchen.xlsm" (Blatt
Silber): Mit aktiviertem tilgungsfreiem Anlaufjahr und Marktwert-Modus
reproduziert die Engine dessen Zinsreihe auf den Cent und die Equity-IRR
bis auf 0,14 Prozentpunkte (Rest: dokumentierte Konventionsunterschiede).

### Engine
- **Negativstunden-Modus** (Globale Annahmen, umschaltbar):
  „Abregelung" – Erlöse entfallen für den Anteil negativer Stunden
  vollständig (bisheriges Verhalten, Standard) – oder „Rückfall auf
  Jahresmarktwert" – die Anlage speist weiter ein, nur die Marktprämie
  entfällt. Nach der Förderdauer wirkt nur noch der Abregelungs-Modus.
- **Tilgungsfreies Anlaufjahr** (On/Off in den Kreditoptionen): Jahr 1
  nur Zinsen, Tilgung ab Jahr 2 bei unveränderter Ratenzahl; dadurch
  fällt auch im zweiten Jahr der Zins noch auf die volle Kreditsumme an.
- Neuer Helfer `engine.kpis.npv_at()`: exakter XNPV für beliebige
  Diskontsätze (keine Interpolation zwischen Kurvenpunkten nötig).
- Gemeindeabgabe: Regressionstest ergänzt, der absichert, dass die
  Abgabe (z.B. 2 €/MWh) in **jedem** Jahr der gesamten Betriebsdauer auf
  die Produktion gezahlt wird – das war bereits das Verhalten der Engine.
- Beide neuen Optionen in YAML- und Excel-IO (Blatt „Einstellungen":
  `negative_stunden_modus`, `tilgungsfreies_anlaufjahr` als JA/NEIN).

### Oberfläche
- **KPI-Kacheln mit dynamischer Schriftgröße**: Lange Werte werden nicht
  mehr abgeschnitten. Ein Skript misst die Wertbreiten und verkleinert
  die Schrift – pro Kachelgruppe (5 Projekt-KPIs bzw. Portfolio-Zeile)
  mit EINEM gemeinsamen Faktor, damit alle Kacheln identisch aussehen.
  Die bisherige Größe ist als Maximum fixiert; Reaktion auf
  Fenstergröße und Font-Laden inklusive.
- **NPV-Diskontsatz einstellbar** (0–10 %, Eingabefeld direkt über der
  KPI-Leiste): Die NPV-Kachel rechnet exakt zum eingegebenen Satz
  (XNPV) statt zu interpolieren; die Einstellung gilt app-weit, damit
  Projekte zum selben Satz verglichen werden.
- Neue Schalter in den Globalen Annahmen (Negativstunden-Modus als
  Auswahl mit Erklärtexten, tilgungsfreies Anlaufjahr als Toggle);
  beide erscheinen auch im „Annahmen"-Tab jedes Projekt-Dashboards.
- `.streamlit/config.toml`: Inter als App-Schriftart (Theme-Konfiguration).

### Tests
- 14 neue Tests (60 gesamt): Gemeindeabgabe-Regression, tilgungsfreies
  Anlaufjahr (Zinsstruktur, vollständige Tilgung, IRR-Wirkung),
  Negativstunden-Modi inkl. Äquivalenz zur Spread-Formel des
  Referenz-Excels, `npv_at`-Konsistenz mit KPI und NPV-Kurve,
  IO-Roundtrips der neuen Felder, aktualisierte UI-Smoke-Tests
  (KPI-Kacheln, NPV-Eingabe wirkt auf die Kachelbeschriftung).

## 2.0.0 – Restrukturierung zu einer Programm-Bibliothek

Fachlich identische Ergebnisse (alle Berechnungen numerisch unverändert),
aber vollständig neue Struktur, Qualitätssicherung und Oberfläche.

### Architektur
- Der 1.200-Zeilen-Monolith `streamlit_app.py` wurde in eine
  UI-Schicht (`app/`) mit Views, Komponenten, Services, Theme und
  Formatierung zerlegt; der Entry-Point enthält nur noch Konfiguration
  und Navigation.
- Neue Service-Schicht (`app/services.py`) als einzige Brücke zwischen
  UI und Engine – inkl. Bewertungs-Cache auf Datei-mtimes: Die
  Portfolioseite rechnet Projekte nur noch bei tatsächlichen Änderungen
  neu statt bei jedem Streamlit-Rerun.
- `engine/__init__.py` definiert jetzt die vollständige öffentliche API
  (inkl. `MarktpreisSzenario`, `CashflowTimeseries`).

### Qualitätssicherung (neu)
- 46 Tests: Engine-Einheitstests mit handgerechneten Erwartungswerten
  (EAG-Prämienlogik, Verlustvortrag-Verrechnungsgrenze, Annuität/linear,
  Indexierung, Clamping), End-to-End-Pipeline, YAML-/Excel-Roundtrips,
  Formatierung/Slugs sowie UI-Smoke-Tests (Streamlit AppTest).
- `pyproject.toml` mit Projektmetadaten, Ruff- und Pytest-Konfiguration;
  GitHub-Actions-CI (Lint + Tests auf Python 3.11/3.12); Makefile.
- Ruff-sauber (u.a. `zip(..., strict=...)` durchgängig).

### Engine
- Robustere XIRR-Suche: Das Suchintervall wird schrittweise erweitert
  (10 → 100 → 1000), statt bei extremen Cashflows `None` zu liefern.
- Neue Kennzahl `eigenkapital_eur` (EK-Einsatz im Jahr 0) in `KPIs`.

### Usability
- Projekte können jetzt **dupliziert** und (mit Bestätigung)
  **gelöscht** werden; Projekt-IDs entstehen per Slugify mit
  Umlaut-Transliteration und Kollisions-Laufnummern statt naivem
  `lower().replace(" ", "-")`.
- **Cashflow-Export als Excel** direkt aus dem Projekt-Dashboard
  (Blätter „Cashflow" + „KPIs").
- Portfolioseite mit aggregierten Kennzahlen (Leistung,
  Investitionsvolumen, Ø EK-Rendite) und sortierbarer
  Vergleichstabelle inkl. spezifischer Investkosten (€/kWp).
- Neuer Dashboard-Tab **„Annahmen"**: der vollständig aufgelöste
  Parametersatz jeder Berechnung (Transparenz/Nachvollziehbarkeit).
- Cashflow-Übersichtstabelle mit sprechenden deutschen Spaltentiteln.

### Oberfläche
- Design-Token-System (`app/theme.py`): eine Farbquelle für CSS und
  Diagramme, Trianel-Rot als Akzent, KPI-Kacheln mit Markenkante,
  Karten-Hover, Header-Linie.
- Zentrales Plotly-Template: einheitliche Typografie, Legenden, Margins
  und **deutsche Zahlenformate auch in Achsen und Hovern**
  (`separators=",."`).
- Durchgängig deutsche Zahlenformatierung in der gesamten App
  (`app/formatting.py`): `7,43 %`, `1.234.567 €`, `1,25x` – statt
  gemischter US-/DE-Formate und `str.replace`-Hacks.

### Entfernt/ersetzt
- Direkte YAML-/Pfad-Zugriffe aus der UI (jetzt ausschließlich über
  Services), globales `st.cache_data.clear()` (jetzt gezielte
  Cache-Invalidierung).
