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
from app.core.secrets import ApiKeys, applica_api_keys, carica_api_keys


def _api_keys_effettive(paths: AppPaths, config: dict) -> ApiKeys:
    """Chiavi da settings.json (inserite in Impostazioni) con fallback al
    `.env` di sviluppo per ogni campo lasciato vuoto."""
    da_env = carica_api_keys(paths)
    da_settings = config.get("api_keys", {})
    return ApiKeys(
        tmdb=da_settings.get("tmdb") or da_env.tmdb,
        gemini=da_settings.get("gemini") or da_env.gemini,
        openai=da_settings.get("openai") or da_env.openai,
        acoustid=da_settings.get("acoustid") or da_env.acoustid,
        lingua_default=da_settings.get("lingua_default") or da_env.lingua_default,
        tmdb_lingua=da_settings.get("tmdb_lingua") or da_env.tmdb_lingua,
    )


def _configura_servizi(paths: AppPaths, api_keys: ApiKeys) -> None:
    from app.services import ffmpeg_service, file_registry, io_service, trickplay_service

    io_service.configura(file_registry.RegistroFile(paths.registry_db_file))
    ffmpeg_service.configura(paths.ffprobe_exe)
    trickplay_service.configura(paths.ffmpeg_exe, paths.ffprobe_exe)
    applica_api_keys(paths, api_keys)


def main() -> int:
    paths = AppPaths()
    logging_setup = LoggingSetup(paths)
    install_excepthook(paths, logging_setup.principale)

    config_manager = ConfigManager(paths)
    config = config_manager.carica()
    api_keys = _api_keys_effettive(paths, config)
    _configura_servizi(paths, api_keys)

    from PyQt6.QtWidgets import QApplication
    from qfluentwidgets import FluentIcon

    from app.services.job_queue import crea_code
    from app.ui import theme
    from app.ui.main_window import MainWindow, VoceNavigazione
    from app.ui.screens.impostazioni_screen import crea_schermata_impostazioni
    from app.ui.screens.percorsi_screen import crea_schermata_percorsi
    from app.ui.screens.scansione_screen import crea_schermata_scansione
    from app.ui.screens.dashboard_screen import crea_schermata_dashboard

    app = QApplication(sys.argv)
    app.setApplicationName("Gestore Film Portable")
    app.setQuitOnLastWindowClosed(False)
    theme.applica_tema(app, "dark")

    recenti = RecentPathsStore(paths)

    stato = AppState(
        sorgente=config_manager.ultimo_percorso_usato(),
        percorsi=dict(config["destinazioni"]),
        automazione=dict(config["automazione"]),
        approvazione_manuale=dict(config["approvazione_manuale"]),
    )

    coda_analisi, coda_io = crea_code()

    schermata_dashboard = crea_schermata_dashboard(stato, coda_analisi, coda_io)
    schermata_percorsi = crea_schermata_percorsi(stato, config_manager, recenti)
    schermata_scansione = crea_schermata_scansione(stato, coda_analisi, coda_io)

    from app.ui.screens.approvazione_screen import crea_schermata_approvazione
    schermata_approvazione = crea_schermata_approvazione(stato, coda_analisi, coda_io)
    
    from app.ui.screens.code_screen import crea_schermata_code
    schermata_code = crea_schermata_code(stato, coda_analisi, coda_io)
    
    schermata_impostazioni = crea_schermata_impostazioni(stato, config_manager, paths, api_keys)

    from app.ui.screens.pulizia_archivio_screen import crea_schermata_pulizia_archivio
    schermata_pulizia = crea_schermata_pulizia_archivio(stato, coda_io)
    
    from app.ui.screens.automazione_screen import crea_schermata_automazione
    schermata_automazione = crea_schermata_automazione(stato, config_manager)
    
    from app.ui.screens.trickplay_screen import crea_schermata_trickplay
    schermata_trickplay = crea_schermata_trickplay(stato)

    voci = [
        VoceNavigazione("Dashboard", schermata_dashboard, icona=FluentIcon.HOME),
        VoceNavigazione("Percorsi", schermata_percorsi, icona=FluentIcon.FOLDER),
        VoceNavigazione("Scansione", schermata_scansione, icona=FluentIcon.SEARCH),
        VoceNavigazione("Approvazione", schermata_approvazione, icona=FluentIcon.ACCEPT),
        VoceNavigazione("Code", schermata_code, icona=FluentIcon.MENU),
        VoceNavigazione("Pulizia Archivio", schermata_pulizia, icona=FluentIcon.BROOM),
        VoceNavigazione("Automazione", schermata_automazione, icona=FluentIcon.ROBOT),
        VoceNavigazione("Impostazioni", schermata_impostazioni, icona=FluentIcon.SETTING),
        VoceNavigazione("Trickplay", schermata_trickplay, icona=FluentIcon.VIDEO),
    ]
    indice_impostazioni = 7

    def _puo_chiudere() -> tuple[bool, str]:
        attive = coda_analisi.operazioni_attive + coda_io.operazioni_attive
        if schermata_scansione.controller.scansione_in_corso or attive > 0:
            return False, "Scansione o trasferimenti in corso."
        return True, ""

    from app.services.update_service import UpdateService
    update_service = UpdateService()
    finestra = MainWindow(voci, puo_chiudere=_puo_chiudere, update_service=update_service)

    def _al_avvio_scansione_richiesto() -> None:
        finestra.vai_a_indice(2)  # Era 1, ora Scansione è alla 2
        schermata_scansione.controller.avvia_scansione()

    def _alla_richiesta_configurazione() -> None:
        finestra.vai_a_indice(indice_impostazioni)

    schermata_percorsi.controller.richiesta_avvio_scansione.connect(_al_avvio_scansione_richiesto)
    schermata_percorsi.controller.richiesta_configurazione.connect(_alla_richiesta_configurazione)
    schermata_impostazioni.controller.richiesta_ritorno_scansione.connect(_al_avvio_scansione_richiesto)

    finestra.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
