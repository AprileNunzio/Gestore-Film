"""Scansione (e rename remoto) su sorgenti FTP. Porta servizio_ftp.py.

Comportamento preservato dall'originale: solo scansione + rename sullo stesso
server. Il trasferimento FTP -> locale non è implementato (OrganizzatoreUniversale
rifiuta esplicitamente lo spostamento di file da sorgente FTP), come nell'app
originale.
"""
from __future__ import annotations

import ftplib
import logging
import os
from typing import Callable, Iterator, Optional
from urllib.parse import unquote, urlparse

_log = logging.getLogger("gestore_film.principale")

LogCallback = Callable[[str], None]


class ServizioFTP:
    def __init__(self, url_completo: str, callback_log: Optional[LogCallback] = None) -> None:
        self.url_completo = url_completo
        parsed = urlparse(url_completo)
        self.host = parsed.hostname
        self.porta = parsed.port or 21
        self.utente = unquote(parsed.username or "anonymous")
        self.password = unquote(parsed.password or "")
        self.root_path = unquote(parsed.path or "/")
        self.sessione: Optional[ftplib.FTP] = None
        self._log_cb = callback_log

    def _notifica(self, msg: str) -> None:
        _log.info(msg)
        if self._log_cb:
            self._log_cb(msg)

    def connetti(self) -> bool:
        try:
            self._notifica(f"Tentativo di connessione a {self.host}...")
            self.sessione = ftplib.FTP()
            self.sessione.connect(self.host, self.porta, timeout=30)
            self.sessione.login(self.utente, self.password)
            self.sessione.set_pasv(True)
            self.sessione.encoding = "utf-8"
            self._notifica("Connesso con successo (Modalità Passiva)")
            return True
        except Exception as e:
            self._notifica(f"Errore connessione: {e}")
            return False

    def chiudi(self) -> None:
        if self.sessione:
            try:
                self.sessione.quit()
            except Exception:
                try:
                    self.sessione.close()
                except Exception:
                    pass

    def scansiona_ricorsiva(self, path_relativa: str = "", estensioni: Optional[set[str]] = None) -> Iterator[dict]:
        target = os.path.join(self.root_path, path_relativa).replace("\\", "/")
        self._notifica(f"Esplorazione cartella remota: {target or '/'}")

        try:
            try:
                items = list(self.sessione.mlsd(target))
            except Exception:
                self._notifica(f"Server non supporta MLSD, uso fallback LIST per {target}")
                yield from self._scansiona_legacy(path_relativa, estensioni)
                return

            for nome, fatti in items:
                if nome in (".", ".."):
                    continue

                percorso_full = os.path.join(target, nome).replace("\\", "/")

                if fatti.get("type") == "dir":
                    sub_path = os.path.join(path_relativa, nome).replace("\\", "/")
                    yield from self.scansiona_ricorsiva(sub_path, estensioni)
                elif fatti.get("type") == "file":
                    ext = os.path.splitext(nome)[1].lower()
                    if not estensioni or ext in estensioni:
                        self._notifica(f"  + Trovato file: {nome}")
                        yield {
                            "percorso": f"ftp://{self.host}{percorso_full}",
                            "percorso_remoto": percorso_full,
                            "nome": nome,
                            "estensione": ext,
                            "dimensione": int(fatti.get("size", 0)),
                        }
        except Exception as e:
            self._notifica(f"Errore scansione FTP MLSD in {target}: {e}")

    def _scansiona_legacy(self, path_relativa: str, estensioni: Optional[set[str]]) -> Iterator[dict]:
        """Fallback con il vecchio comando LIST (per server senza supporto MLSD)."""
        target = os.path.join(self.root_path, path_relativa).replace("\\", "/")
        try:
            self.sessione.cwd(target)
            linee: list[str] = []
            self.sessione.dir(linee.append)
            for linea in linee:
                parti = linea.split()
                if not parti:
                    continue
                is_dir = linea.startswith("d") or "<DIR>" in linea
                nome = " ".join(parti[8:]) if (linea.startswith("d") or linea.startswith("-")) else " ".join(parti[3:])
                if not nome or nome in (".", ".."):
                    continue
                percorso_full = os.path.join(target, nome).replace("\\", "/")

                if is_dir:
                    sub_path = os.path.join(path_relativa, nome).replace("\\", "/")
                    yield from self._scansiona_legacy(sub_path, estensioni)
                else:
                    ext = os.path.splitext(nome)[1].lower()
                    if not estensioni or ext in estensioni:
                        yield {
                            "percorso": f"ftp://{self.host}{percorso_full}",
                            "percorso_remoto": percorso_full,
                            "nome": nome,
                            "estensione": ext,
                        }
        except Exception:
            return

    def crea_directory_ricorsiva(self, path: str) -> None:
        parti = [p for p in path.replace("\\", "/").split("/") if p]
        corrente = "/" if path.startswith("/") else ""

        for p in parti:
            corrente = os.path.join(corrente, p).replace("\\", "/")
            try:
                self.sessione.mkd(corrente)
            except Exception:
                pass

    def sposta_file(self, sorgente: str, destinazione: str) -> bool:
        """Rename sul server FTP (spostamento atomico solo entro lo stesso server)."""
        try:
            dir_dest = os.path.dirname(destinazione).replace("\\", "/")
            self.crea_directory_ricorsiva(dir_dest)
            self.sessione.rename(sorgente.replace("\\", "/"), destinazione.replace("\\", "/"))
            return True
        except Exception as e:
            _log.error(f"Errore RENAME FTP: {sorgente} -> {destinazione} | {e}")
            return False
