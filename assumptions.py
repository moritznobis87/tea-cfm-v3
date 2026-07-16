"""
KPI-Kachelzeile mit dynamischer Schriftgroesse.

Anforderung: Lange Werte (z.B. "1.234.567 €") duerfen nicht abgeschnitten
werden. Die Schrift wird deshalb per JavaScript so weit verkleinert, bis
der laengste Wert der Zeile vollstaendig passt - und zwar fuer ALLE
Kacheln einer Gruppe EINHEITLICH (gemeinsamer Skalierungsfaktor = Minimum
ueber alle Kacheln), damit die Zeile nicht unruhig wirkt. Die aktuelle
Standardgroesse ist als Maximum fixiert; bei kurzen Werten waechst die
Schrift also nicht darueber hinaus.

Technik: Streamlit kann Schriftgroessen nicht selbst an Textbreiten
anpassen; ein kleines Skript (ueber components.html, unsichtbarer iframe)
misst im Eltern-Dokument scrollWidth vs. clientWidth der Wert-Elemente
einer Gruppe und setzt die gemeinsame Groesse. Es laeuft erneut bei
Fensteraenderung und nach dem Laden der Webfonts.
"""

from __future__ import annotations

import html
import json

import streamlit as st

#: Maximale (= bisherige) Schriftgroesse der KPI-Werte in rem.
KPI_MAX_FONT_REM = 2.0
#: Untergrenze, damit extrem lange Werte nicht unlesbar klein werden.
KPI_MIN_FONT_REM = 0.85

_FIT_SCRIPT = """
<script>
(function() {
    const GROUP = %(group)s;
    const P = window.parent;
    const doc = P.document;
    const rem = parseFloat(P.getComputedStyle(doc.documentElement).fontSize) || 16;
    const MAX = %(max_rem)f * rem;
    const MIN = %(min_rem)f * rem;

    function fit() {
        const els = doc.querySelectorAll(
            '.kpi-value[data-kpi-group="' + GROUP + '"]'
        );
        if (!els.length) return;
        // 1) Auf Maximalgroesse zuruecksetzen, dann messen.
        els.forEach(el => { el.style.fontSize = MAX + "px"; });
        let factor = 1;
        els.forEach(el => {
            const avail = el.clientWidth, need = el.scrollWidth;
            if (avail > 0 && need > 0) factor = Math.min(factor, avail / need);
        });
        // 2) EIN gemeinsamer Faktor fuer die ganze Gruppe.
        const size = Math.max(MIN, Math.floor(MAX * factor * 100) / 100);
        els.forEach(el => { el.style.fontSize = size + "px"; });
    }

    fit();
    P.requestAnimationFrame(fit);
    setTimeout(fit, 150);
    setTimeout(fit, 600);
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(fit);

    // Resize-Listener nur einmal pro Gruppe registrieren (Reruns erzeugen
    // neue iframes; fit() fragt das DOM jedes Mal frisch ab, der alte
    // Listener bleibt daher gueltig).
    const key = "__kpiFit_" + GROUP;
    if (!P[key]) {
        P[key] = true;
        P.addEventListener("resize", function () {
            clearTimeout(P[key + "_t"]);
            P[key + "_t"] = setTimeout(fit, 120);
        });
    }
})();
</script>
"""


def render_kpi_row(items: list[tuple[str, str]], group: str) -> None:
    """Rendert eine Zeile von KPI-Kacheln.

    items: Liste von (Beschriftung, formatierter Wert).
    group: Gruppenschluessel - alle Kacheln derselben Gruppe erhalten die
           gleiche (automatisch eingepasste) Schriftgroesse.
    """
    kacheln = "".join(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value" data-kpi-group="{html.escape(group)}">'
        f"{html.escape(value)}</div>"
        f"</div>"
        for label, value in items
    )
    st.markdown(
        f'<div class="kpi-row">{kacheln}</div>', unsafe_allow_html=True
    )
    st.iframe(
        _FIT_SCRIPT
        % {
            "group": json.dumps(group),
            "max_rem": KPI_MAX_FONT_REM,
            "min_rem": KPI_MIN_FONT_REM,
        },
        height=1,
    )
