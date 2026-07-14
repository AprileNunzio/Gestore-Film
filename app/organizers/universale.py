"""Orchestratore principale (Facade).
Delega la logica ai micro-servizi: ScannerUniversale, AnalyzerUniversale, FileMoverUniversale, AiMatcherUniversale.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Iterator, Optional

from app.organizers.film import OrganizzatoreFilm
from app.organizers.musica import OrganizzatoreMusica
from app.organizers.serie import OrganizzatoreSerie

from app.organizers.scanner import ScannerUniversale
from app.organizers.analyzer import AnalyzerUniversale
from app.organizers.file_mover import FileMoverUniversale
from app.organizers.ai_matcher import AiMatcherUniversale

LogCallback = Callable[[str], None]
ConflittoCallback = Callable[[dict, dict], None]
IoCallback = Callable[[dict, dict], None]

class OrganizzatoreUniversale:
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self._config_attuale = config or {}
        self.motore_film = OrganizzatoreFilm()
        self.motore_serie = OrganizzatoreSerie()
        self.motore_musica = OrganizzatoreMusica()
        self._log_callback: Optional[LogCallback] = None
        self.motore_film.imposta_callback_log(self._proxy_log)
        self.motore_serie.imposta_callback_log(self._proxy_log)
        self.motore_musica.imposta_callback_log(self._proxy_log)

        self._evento_conflitto = threading.Event()
        self._decisione_conflitto: Optional[str] = None
        self.mappa_destinazione: dict[str, dict[str, Any]] = {}
        self._lock_mappa = threading.Lock()
        self._percorso_sorgente_attuale: Optional[str] = None

    def imposta_callback_log(self, callback: LogCallback) -> None:
        self._log_callback = callback
        self.motore_film.imposta_callback_log(callback)
        self.motore_serie.imposta_callback_log(callback)
        self.motore_musica.imposta_callback_log(callback)

    def _proxy_log(self, msg: str) -> None:
        if self._log_callback:
            self._log_callback(msg)

    def risolvi_conflitto(self, decisione: str) -> None:
        self._decisione_conflitto = decisione
        self._evento_conflitto.set()

    def scansiona_directory(self, percorso: str) -> Iterator[dict[str, Any]]:
        self._percorso_sorgente_attuale = percorso
        yield from ScannerUniversale.scansiona_directory(
            percorso, self._config_attuale, self.mappa_destinazione, self._lock_mappa, self._proxy_log
        )

    def analizza_file(self, info: dict[str, Any], usa_ai: bool = False) -> dict[str, Any]:
        return AnalyzerUniversale.analizza_file(
            info, self._config_attuale, self.motore_film, self.motore_serie, self.motore_musica,
            self.mappa_destinazione, self._lock_mappa, usa_ai
        )

    def sposta_file(
        self,
        r: dict[str, Any],
        target_root: str,
        azione: str,
        pulisci: bool,
        callback_ui_io: Optional[IoCallback] = None,
        callback_ui_conflitto: Optional[ConflittoCallback] = None,
    ) -> dict[str, Any]:
        def ottieni_decisione() -> Optional[str]:
            return self._decisione_conflitto

        def reset_conflitto() -> None:
            self._evento_conflitto.clear()
            self._decisione_conflitto = None

        return FileMoverUniversale.sposta_file(
            r, target_root, azione, pulisci, self._config_attuale,
            self.motore_film, self.motore_serie, self.motore_musica,
            self._percorso_sorgente_attuale, self._evento_conflitto,
            ottieni_decisione, reset_conflitto, callback_ui_io, callback_ui_conflitto
        )

    def costruisci_nome_jellyfin(
        self,
        titolo_it: str,
        match: dict[str, Any],
        info_tecnica: dict[str, Any],
        estensione: str,
        tipo_media: str = "film",
        nome_episodio: str = "",
        stagione: str = "01",
        episodio: str = "01",
    ) -> dict[str, str]:
        if tipo_media == "serie":
            return self.motore_serie.costruisci_nome_jellyfin(match, stagione, episodio, info_tecnica, estensione, nome_episodio)
        if tipo_media == "musica":
            return self.motore_musica.costruisci_nome_jellyfin(match, estensione)
        return self.motore_film.costruisci_nome_jellyfin(titolo_it, match, info_tecnica, estensione)

    def analizza_con_ai(self, r: dict[str, Any], provider: str = "gemini") -> dict[str, Any]:
        return AiMatcherUniversale.analizza_con_ai(
            r, provider, self.motore_film, self.motore_serie, self.motore_musica,
            AnalyzerUniversale._arricchisci_e_controlla,
            self._config_attuale, self.mappa_destinazione, self._lock_mappa
        )
