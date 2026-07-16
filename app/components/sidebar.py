"""
Sidebar-Komponente: Sichern/Wiederherstellen von Projekten und Globalen
Annahmen ueber Excel-Dateien.

Hintergrund: Streamlit Cloud hat kein dauerhaftes Dateisystem - neu
angelegte Projekte gehen bei einem Reboot/Redeploy verloren, wenn sie
nicht im GitHub-Repo liegen. Der Excel-Down-/Upload ist der bewusst
einfache Sicherungsweg (und fuer tabellarische Daten wie Preiskurven
ohnehin das bequemere Bearbeitungsformat als YAML).
"""

from __future__ import annotations

import streamlit as st

from app import services
from app.config import PROJECTS_DIR
from engine.io_excel import (
    excel_to_global_assumptions,
    excel_to_projects,
    global_assumptions_to_excel,
    projects_to_excel,
)
from engine.io_yaml import load_project_yaml

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render_import_export() -> None:
    with st.sidebar.expander("Projekte sichern / wiederherstellen"):
        st.caption(
            "Als Excel-Datei herunterladen und ins Repo committen, um "
            "Projekte dauerhaft zu sichern - oder zuvor gesicherte Projekte "
            "wieder hochladen (eine Zeile pro Projekt)."
        )

        st.markdown("**Herunterladen**")
        projects_dict = services.list_project_files()
        if projects_dict:
            alle_projekte = [load_project_yaml(p) for p in projects_dict.values()]
            st.download_button(
                "Alle Projekte als Excel",
                data=projects_to_excel(alle_projekte),
                file_name="projekte.xlsx",
                mime=_XLSX_MIME,
                width="stretch",
            )
        else:
            st.caption("Keine Projekte vorhanden.")

        st.markdown("**Hochladen**")
        uploaded_projekte = st.file_uploader(
            "Excel-Datei (.xlsx, eine Zeile pro Projekt)",
            type=["xlsx"], key="project_upload",
        )
        if uploaded_projekte and st.button(
            "Hochgeladene Projekte speichern", type="primary", width="stretch"
        ):
            try:
                importierte = excel_to_projects(uploaded_projekte.getvalue())
                for project in importierte:
                    services.save_project(project, PROJECTS_DIR / f"{project.id}.yaml")
                st.success("Gespeichert: " + ", ".join(p.name for p in importierte))
                st.rerun()
            except Exception as exc:
                st.error(f"Fehler beim Einlesen der Excel-Datei: {exc}")

    with st.sidebar.expander("Globale Annahmen sichern / wiederherstellen"):
        st.caption(
            "Als Excel-Datei (3 Tabellenblätter: Preiskurven, Betriebskosten, "
            "Einstellungen) - bequemer zu bearbeiten als die YAML-Datei direkt."
        )

        st.markdown("**Herunterladen**")
        st.download_button(
            "Globale Annahmen als Excel",
            data=global_assumptions_to_excel(services.get_global_assumptions()),
            file_name="globale_annahmen.xlsx",
            mime=_XLSX_MIME,
            width="stretch",
        )

        st.markdown("**Hochladen**")
        uploaded_ga = st.file_uploader(
            "Excel-Datei (.xlsx)", type=["xlsx"], key="global_assumptions_upload",
        )
        if uploaded_ga and st.button(
            "Hochgeladene Excel-Datei übernehmen", type="primary", width="stretch"
        ):
            try:
                neue_ga = excel_to_global_assumptions(uploaded_ga.getvalue())
                services.save_global_assumptions(neue_ga)
                st.success("Globale Annahmen aus Excel-Datei übernommen.")
                st.rerun()
            except Exception as exc:
                st.error(f"Fehler beim Einlesen der Excel-Datei: {exc}")
