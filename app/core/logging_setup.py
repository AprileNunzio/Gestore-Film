"""Logging su file rotanti + gestore globale degli errori non catturati.

Porta logger.py di Script_Film (5 logger rotanti, ancorati ad AppPaths) e
aggiunge install_excepthook(): a differenza dell'originale (che logga soltanto
e lascia l'utente davanti a un errore silenzioso o a un traceback in console),
qui ogni eccezione non gestita viene sia loggata in error_log.txt sia mostrata
con un QMessageBox comprensibile.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from types import TracebackType

from app.core.paths import AppPaths

_FORMATO = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 2

_NOMI_LOG = {
    "principale": "app.log",
    "approvazione": "in_approvazione.log",
    "non_fatti": "non_fatti.log",
    "non_riconosciuti": "non_riconosciuti.log",
    "anomalie": "anomalie.log",
}


class LoggingSetup:
    """Configura e mantiene i 5 logger rotanti dell'app."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._loggers: dict[str, logging.Logger] = {}
        self._configura_tutti()

    def _configura_logger(self, nome: str, file_log: str) -> logging.Logger:
        logger = logging.getLogger(f"gestore_film.{nome}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            self._paths.logs_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                self._paths.logs_dir / file_log,
                encoding="utf-8",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
            )
            handler.setFormatter(_FORMATO)
            logger.addHandler(handler)
        return logger

    def _configura_tutti(self) -> None:
        for nome, file_log in _NOMI_LOG.items():
            self._loggers[nome] = self._configura_logger(nome, file_log)

    @property
    def principale(self) -> logging.Logger:
        return self._loggers["principale"]

    @property
    def approvazione(self) -> logging.Logger:
        return self._loggers["approvazione"]

    @property
    def non_fatti(self) -> logging.Logger:
        return self._loggers["non_fatti"]

    @property
    def non_riconosciuti(self) -> logging.Logger:
        return self._loggers["non_riconosciuti"]

    @property
    def anomalie(self) -> logging.Logger:
        return self._loggers["anomalie"]

    def svuota_tutti_i_log(self) -> None:
        for logger in self._loggers.values():
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
        if self._paths.logs_dir.is_dir():
            for f in self._paths.logs_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass
        self._configura_tutti()


def install_excepthook(paths: AppPaths, logger: logging.Logger) -> None:
    """Sostituisce sys.excepthook. Va installato prima di costruire la QApplication."""

    def _handler(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        testo_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            logger.error("Errore non gestito:\n%s", testo_traceback)
        except Exception:
            pass
        try:
            with open(paths.error_log_file, "a", encoding="utf-8") as f:
                f.write(testo_traceback + "\n")
        except OSError:
            pass

        _mostra_dialog_errore(testo_traceback, paths)

    sys.excepthook = _handler


def _mostra_dialog_errore(dettagli: str, paths: AppPaths) -> None:
    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance()
    creato_qui = False
    if app is None:
        app = QApplication(sys.argv)
        creato_qui = True

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Errore imprevisto")
    box.setText(
        "Si è verificato un errore imprevisto.\n"
        f"I dettagli sono stati salvati in {paths.error_log_file.name}, "
        "accanto all'eseguibile."
    )
    box.setDetailedText(dettagli)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()

    if creato_qui:
        app.quit()
