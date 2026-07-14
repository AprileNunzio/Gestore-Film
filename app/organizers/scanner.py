import logging
import os
import threading
from pathlib import Path
from typing import Any, Iterator, Callable

from app.core.config import ESTENSIONI_AUDIO, ESTENSIONI_VIDEO
from app.services import io_service

_log_anomalie = logging.getLogger("gestore_film.anomalie")

class ScannerUniversale:
    """Micro-servizio responsabile unicamente della scansione dei file."""

    @staticmethod
    def scansiona_directory(
        percorso: str,
        config: dict[str, Any],
        mappa_destinazione: dict[str, Any],
        lock_mappa: threading.Lock,
        callback_log: Callable[[str], None]
    ) -> Iterator[dict[str, Any]]:
        
        # Scansione asincrona destinazione per dedup
        def _esegui_scansione_destinazione_async() -> None:
            for tipo in ("film", "serie", "musica"):
                perc = config.get("destinazioni", {}).get(tipo)
                if perc:
                    mappa_parziale = io_service.scansiona_destinazione(perc)
                    with lock_mappa:
                        mappa_destinazione.update(mappa_parziale)
                        
        threading.Thread(target=_esegui_scansione_destinazione_async, daemon=True).start()
        
        est_tutte = ESTENSIONI_VIDEO.union(ESTENSIONI_AUDIO)

        if percorso.lower().startswith("ftp://"):
            from app.services.ftp_service import ServizioFTP
            ftp = ServizioFTP(percorso, callback_log=callback_log)
            if ftp.connetti():
                yield from ftp.scansiona_ricorsiva(estensioni=est_tutte)
                ftp.chiudi()
            return

        try:
            for radice, _dirs, file in os.walk(percorso):
                for nome in file:
                    est = Path(nome).suffix.lower()
                    if est in est_tutte:
                        yield {"percorso": os.path.join(radice, nome), "nome": nome, "estensione": est}
        except OSError as e:
            msg = f"Errore scansione directory {percorso}: {e}"
            if callback_log: callback_log(msg)
            _log_anomalie.error(msg)
