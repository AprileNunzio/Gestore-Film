"""Toolkit filesystem: hashing, copia/spostamento con progresso, permessi, date file.

Porta il resto di servizio_io.py (RegistroFile è ora in file_registry.py).
Va inizializzato con configura(registro) prima dell'uso (il registro riceve un
db_path esplicito da AppPaths, invece del vecchio singleton a path relativo bare).
"""
from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import shutil
import time
from ctypes import wintypes
from datetime import datetime
from typing import Callable, Optional

from app.services.file_registry import RegistroFile

_log = logging.getLogger("gestore_film.principale")

_registro: RegistroFile | None = None

ProgressoCallback = Callable[[dict], None]


def configura(registro: RegistroFile) -> None:
    global _registro
    _registro = registro


def _registro_attivo() -> RegistroFile:
    if _registro is None:
        raise RuntimeError("io_service.configura(registro) non è stato chiamato all'avvio")
    return _registro


def calcola_hash_veloce(percorso: str) -> str:
    """SHA-256 di inizio+fine file (hash parziale, non full-file: sufficiente per dedup euristico)."""
    chunk_size = 65536
    h = hashlib.sha256()
    try:
        dim = os.path.getsize(percorso)
        with open(percorso, "rb") as f:
            if dim < chunk_size * 2:
                h.update(f.read())
            else:
                h.update(f.read(chunk_size))
                f.seek(-chunk_size, 2)
                h.update(f.read(chunk_size))
        return h.hexdigest()
    except OSError as e:
        _log.error(f"Errore calcolo hash veloce per {percorso}: {e}")
        return ""


def verifica_esistenza(percorso: str) -> bool:
    return os.path.exists(percorso)


def scansiona_destinazione(percorso_radice: str) -> dict[str, dict]:
    """Mappa nome_file -> {percorso, dimensione} per l'intero albero di percorso_radice."""
    mappa_destinazione: dict[str, dict] = {}
    if not percorso_radice or not os.path.exists(percorso_radice):
        return mappa_destinazione

    try:
        for radice, _dirs, file in os.walk(percorso_radice):
            for nome in file:
                percorso_completo = os.path.join(radice, nome)
                try:
                    dimensione = os.path.getsize(percorso_completo)
                    mappa_destinazione[nome] = {"percorso": percorso_completo, "dimensione": dimensione}
                except OSError:
                    continue
    except OSError as e:
        _log.error(f"Errore durante scansione destinazione {percorso_radice}: {e}")

    return mappa_destinazione


def ha_permesso_scrittura(percorso: str) -> tuple[bool, str]:
    try:
        if os.path.exists(percorso) and not os.path.isdir(percorso):
            try:
                with open(percorso, "a"):
                    pass
                return True, "Permesso sovrascrittura OK"
            except (OSError, PermissionError) as e:
                return False, f"File esistente non accessibile (in uso o permessi insufficienti): {e}"

        target = percorso
        while target and not os.path.exists(target):
            padre = os.path.dirname(target)
            if padre == target or not padre:
                break
            target = padre

        if not target or not os.path.isdir(target):
            return False, f"Directory base non trovata o non raggiungibile: {target}"

        test_file = os.path.join(target, f".permesso_test_{int(time.time())}")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return True, "Permesso OK"
        except (OSError, PermissionError) as e:
            _log.error(f"Test scrittura fallito in {target}: {e}")
            return False, f"Accesso negato alla cartella di rete '{target}'"
    except OSError as e:
        return False, f"Errore diagnostica permessi: {e}"


def _copia_sincrona(sorgente: str, destinazione: str, callback_progresso: Optional[ProgressoCallback] = None) -> None:
    dimensione_totale = os.path.getsize(sorgente)
    dimensione_copiata = 0
    tempo_inizio = time.time()
    chunk_size = 4 * 1024 * 1024

    with open(sorgente, "rb") as f_sorg, open(destinazione, "wb") as f_dest:
        while True:
            buffer = f_sorg.read(chunk_size)
            if not buffer:
                break

            f_dest.write(buffer)
            dimensione_copiata += len(buffer)

            if callback_progresso:
                try:
                    tempo_attuale = time.time()
                    durata = tempo_attuale - tempo_inizio
                    velocita = dimensione_copiata / durata if durata > 0 else 0
                    percentuale = dimensione_copiata / dimensione_totale if dimensione_totale > 0 else 0
                    tempo_rimanente = (dimensione_totale - dimensione_copiata) / velocita if velocita > 0 else 0

                    callback_progresso(
                        {
                            "percentuale": percentuale,
                            "velocita": velocita,
                            "etr": tempo_rimanente,
                            "copiati": dimensione_copiata,
                            "totale": dimensione_totale,
                        }
                    )
                except Exception as e_cb:
                    _log.warning(f"Errore nel callback di progresso: {e_cb}")


def copia_con_progresso(
    sorgente: str, destinazione: str, callback_progresso: Optional[ProgressoCallback] = None
) -> tuple[bool, str]:
    """Copia un file con scrittura atomica (estensione .working) e dedup via hash/dimensione."""
    _log.info(f"Avvio COPIA: {os.path.basename(sorgente)} -> {os.path.basename(destinazione)}")
    dest_working = ""
    try:
        if not os.path.exists(sorgente):
            return False, "File sorgente non trovato"

        hash_file = calcola_hash_veloce(sorgente)
        if _registro_attivo().controlla_esistenza(hash_file):
            return True, "SALTATO (Duplicato per Hash)"

        if os.path.exists(destinazione):
            try:
                if os.path.getsize(sorgente) == os.path.getsize(destinazione):
                    return True, "SALTATO (Duplicato per Dimensione)"
            except OSError:
                pass

        ok, msg = ha_permesso_scrittura(destinazione)
        if not ok:
            _log.error(f"PRE-CHECK FALLITO per {destinazione}: {msg}")
            return False, msg

        if os.path.exists(destinazione):
            try:
                os.remove(destinazione)
            except OSError:
                pass

        dest_working = f"{destinazione}.working"

        _copia_sincrona(sorgente, dest_working, callback_progresso)

        dimensione_totale = os.path.getsize(sorgente)
        if os.path.getsize(dest_working) != dimensione_totale:
            raise IOError(f"Incongruenza dimensione: {os.path.getsize(dest_working)} != {dimensione_totale}")

        try:
            shutil.copystat(sorgente, dest_working)
        except OSError:
            pass

        os.rename(dest_working, destinazione)

        if hash_file:
            _registro_attivo().registra_file(hash_file, 0, "standard")

        return True, "Successo"
    except Exception as e:
        msg_err = str(e)
        _log.error(f"ECCEZIONE I/O durante copia {sorgente} -> {destinazione}: {msg_err}")
        if os.path.exists(destinazione):
            try:
                os.remove(destinazione)
            except OSError:
                pass
        if dest_working and os.path.exists(dest_working):
            try:
                os.remove(dest_working)
            except OSError:
                pass
        return False, msg_err


def sposta_con_progresso(
    sorgente: str, destinazione: str, callback_progresso: Optional[ProgressoCallback] = None
) -> tuple[bool, str]:
    _log.info(f"Avvio SPOSTAMENTO: {os.path.basename(sorgente)} -> {os.path.basename(destinazione)}")
    try:
        if not os.path.exists(sorgente):
            return False, "File sorgente non trovato"

        try:
            os.rename(sorgente, destinazione)
            if callback_progresso:
                sz = os.path.getsize(destinazione)
                callback_progresso({"percentuale": 1.0, "velocita": 0, "etr": 0, "copiati": sz, "totale": sz})

            hash_file = calcola_hash_veloce(destinazione)
            if hash_file:
                _registro_attivo().registra_file(hash_file, 0, "standard")

            return True, "Spostato tramite rename"
        except OSError:
            successo, msg = copia_con_progresso(sorgente, destinazione, callback_progresso)
            if successo and "SALTATO" not in msg:
                try:
                    os.remove(sorgente)
                    return True, "Spostato tramite copia e cancellazione"
                except OSError as e:
                    return True, f"Copiato ma sorgente non rimossa: {e}"
            return successo, msg
    except OSError as e:
        return False, str(e)


def rimuovi_directory_vuote_ricorsivo(percorso: str, radice_stop: Optional[str] = None) -> None:
    try:
        if not percorso or not os.path.isdir(percorso):
            return

        if radice_stop:
            radice_stop_abs = os.path.abspath(radice_stop)
            percorso_abs = os.path.abspath(percorso)
            if not percorso_abs.startswith(radice_stop_abs) or percorso_abs == radice_stop_abs:
                return

        if not os.listdir(percorso):
            os.rmdir(percorso)
            padre = os.path.dirname(percorso)
            rimuovi_directory_vuote_ricorsivo(padre, radice_stop)
    except (OSError, PermissionError):
        pass


def sposta_directory_con_progresso(
    sorgente: str, destinazione: str, callback_progresso: Optional[Callable[[dict], None]] = None
) -> tuple[bool, str]:
    _log.info(f"Spostamento directory: {sorgente} -> {destinazione}")
    try:
        if not os.path.exists(sorgente):
            return False, "Cartella sorgente non trovata"

        if os.path.exists(destinazione):
            return False, "Cartella destinazione già esistente (conflitto)"

        os.makedirs(os.path.dirname(destinazione), exist_ok=True)

        try:
            shutil.move(sorgente, destinazione)
            if callback_progresso:
                callback_progresso({"percentuale": 1.0, "stato": "Completato"})
            return True, "Spostata correttamente"
        except OSError as e:
            _log.error(f"Errore durante spostamento cartella: {e}")
            return False, str(e)
    except OSError as e:
        return False, str(e)


def imposta_data_file(percorso: str, data_iso: str) -> None:
    """Imposta data modifica/accesso/creazione (Windows) di un file o directory da una stringa Y-M-D."""
    if not data_iso or not data_iso.strip():
        return
    try:
        dt = datetime.strptime(data_iso[:10], "%Y-%m-%d")
        timestamp = dt.replace(hour=12).timestamp()

        os.utime(percorso, (timestamp, timestamp))

        if os.name == "nt":
            epoch_diff = 116444736000000000
            file_time = int((timestamp * 10000000) + epoch_diff)
            creation_time = wintypes.FILETIME(file_time & 0xFFFFFFFF, file_time >> 32)

            file_flag_backup_semantics = 0x02000000
            file_share_read = 1
            file_share_write = 2
            open_existing = 3
            file_write_attributes = 0x0100

            handle = ctypes.windll.kernel32.CreateFileW(
                percorso,
                file_write_attributes,
                file_share_read | file_share_write,
                None,
                open_existing,
                file_flag_backup_semantics,
                None,
            )

            if handle not in (None, -1):
                ctypes.windll.kernel32.SetFileTime(handle, ctypes.byref(creation_time), None, ctypes.byref(creation_time))
                ctypes.windll.kernel32.CloseHandle(handle)
                _log.info(f"Data di creazione {data_iso[:10]} applicata a: {percorso}")
            else:
                _log.warning(f"Impossibile ottenere l'handle per applicare la data a: {percorso}")

    except Exception as e:
        _log.warning(f"Errore non fatale durante l'impostazione data su {percorso}: {e}")

def imposta_data_attuale(percorso: str) -> None:
    """Imposta data modifica/accesso/creazione (Windows) di un file o directory al momento attuale."""
    try:
        timestamp = time.time()
        os.utime(percorso, (timestamp, timestamp))

        if os.name == "nt":
            epoch_diff = 116444736000000000
            file_time = int((timestamp * 10000000) + epoch_diff)
            creation_time = wintypes.FILETIME(file_time & 0xFFFFFFFF, file_time >> 32)

            file_flag_backup_semantics = 0x02000000
            file_share_read = 1
            file_share_write = 2
            open_existing = 3
            file_write_attributes = 0x0100

            handle = ctypes.windll.kernel32.CreateFileW(
                percorso,
                file_write_attributes,
                file_share_read | file_share_write,
                None,
                open_existing,
                file_flag_backup_semantics,
                None,
            )

            if handle not in (None, -1):
                ctypes.windll.kernel32.SetFileTime(handle, ctypes.byref(creation_time), None, ctypes.byref(creation_time))
                ctypes.windll.kernel32.CloseHandle(handle)
                _log.info(f"Data di creazione (ATTUALE) applicata a: {percorso}")
            else:
                _log.warning(f"Impossibile ottenere l'handle per applicare la data a: {percorso}")
    except Exception as e:
        _log.warning(f"Errore non fatale durante l'impostazione data attuale su {percorso}: {e}")
