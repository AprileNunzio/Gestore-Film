"""Entry point di Gestore Film Portable.

Porta main.py di Script_Film: bootstrap dell'app, caricamento config/secrets,
wiring dei servizi, costruzione della finestra principale. A differenza
dell'originale (Flet, bootstrap con ft.run(main)), qui si usa QApplication.

L'excepthook globale viene installato PRIMA di costruire la QApplication,
cosi' anche un errore durante il bootstrap stesso finisce in error_log.txt e
mostra un QMessageBox invece di un traceback grezzo in console o un crash
silenzioso (direttiva Fase 2 del progetto).
"""
from __future__ import annotations

import sys

from app.core.app_state import AppState
from app.core.config import ConfigManager
from app.core.logging_setup import LoggingSetup, install_excepthook
from app.core.paths import AppPaths
from app.core.recent_paths import RecentPathsStore
from app.core.secrets import carica_api_keys


def _configura_servizi(paths: AppPaths, api_keys) -> None:
    from app.services import (
        acoustid_service,
        db_cache,
        ffmpeg_service,
        file_registry,
        gemini_service,
        io_service,
        metadata_service,
        openai_service,
        tmdb_service,
    )

    io_service.configura(file_registry.RegistroFile(paths.registry_db_file))
    tmdb_service.configura(db_cache.DatabaseCache(paths.cache_db_file), api_keys.tmdb, api_keys.tmdb_lingua)
    ffmpeg_service.configura(paths.ffprobe_exe)
    gemini_service.configura(api_keys.gemini)
    openai_service.configura(api_keys.openai)
    acoustid_service.configura(api_keys.acoustid, paths.fpcalc_exe)
    metadata_service.configura(api_keys.tmdb_lingua)


def main() -> int:
    paths = AppPaths()
    logging_setup = LoggingSetup(paths)
    install_excepthook(paths, logging_setup.principale)

    api_keys = carica_api_keys(paths)
    _configura_servizi(paths, api_keys)

    from PyQt6.QtWidgets import QApplication

    from app.services.job_queue import crea_code
    from app.ui import theme
    from app.ui.main_window import MainWindow, VoceNavigazione
    from app.ui.screens.percorsi_screen import crea_schermata_percorsi
    from app.ui.screens.scansione_screen import crea_schermata_scansione

    app = QApplication(sys.argv)
    app.setApplicationName("Gestore Film Portable")
    theme.applica_tema(app, theme.rileva_tema_sistema())

    config_manager = ConfigManager(paths)
    config = config_manager.carica()
    recenti = RecentPathsStore(paths)

    stato = AppState(
        sorgente=config_manager.ultimo_percorso_usato(),
        percorsi=dict(config["destinazioni"]),
        automazione=dict(config["automazione"]),
        approvazione_manuale=dict(config["approvazione_manuale"]),
    )

    coda_analisi, coda_io = crea_code()

    schermata_percorsi = crea_schermata_percorsi(stato, config_manager, recenti)
    schermata_scansione = crea_schermata_scansione(stato, coda_analisi, coda_io)

    voci = [
        VoceNavigazione("Percorsi", schermata_percorsi, icona="📁"),
        VoceNavigazione("Scansione", schermata_scansione, icona="🔍"),
        VoceNavigazione("Approvazione", None, icona="✅", abilitata=False),
        VoceNavigazione("Code", None, icona="📋", abilitata=False),
        VoceNavigazione("Pulizia Archivio", None, icona="🗂️", abilitata=False),
        VoceNavigazione("Automazione", None, icona="⚡", abilitata=False),
        VoceNavigazione("Impostazioni", None, icona="⚙️", abilitata=False),
        VoceNavigazione("Trickplay", None, icona="🎞️", abilitata=False),
    ]

    def _puo_chiudere() -> tuple[bool, str]:
        attive = coda_analisi.operazioni_attive + coda_io.operazioni_attive
        if schermata_scansione.controller.scansione_in_corso or attive > 0:
            return False, "Scansione o trasferimenti in corso."
        return True, ""

    finestra = MainWindow(voci, puo_chiudere=_puo_chiudere)

    def _al_avvio_scansione_richiesto() -> None:
        finestra.vai_a_indice(1)
        schermata_scansione.controller.avvia_scansione()

    schermata_percorsi.controller.richiesta_avvio_scansione.connect(_al_avvio_scansione_richiesto)

    finestra.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
