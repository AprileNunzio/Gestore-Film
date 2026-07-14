"""Servizio per l'aggiornamento automatico dell'applicazione.

Controlla le release su GitHub, scarica l'asset e applica l'aggiornamento.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

import requests
from packaging import version
from PyQt6.QtCore import QObject, pyqtSignal

from app.core.paths import AppPaths

_log = logging.getLogger("gestore_film.updater")


class UpdateService(QObject):
    aggiornamento_disponibile = pyqtSignal(str, str)  # versione, changelog (body)
    progresso_download = pyqtSignal(int)  # percentuale 0-100
    download_completato = pyqtSignal(str)  # percorso del file scaricato
    errore = pyqtSignal(str)

    def __init__(self, repo_url: str = "AprileNunzio/Gestore-Film", asset_name: str = "Gestore_Film_Portable.exe"):
        super().__init__()
        self.repo_url = repo_url
        self.asset_name = asset_name
        self.current_version = self._leggi_versione_corrente()
        self._url_download_atteso: str = ""

    def _leggi_versione_corrente(self) -> str:
        # Se eseguito come script, la cartella base è quella dove si trova main.py
        # Se eseguito come exe pyinstaller, è sys._MEIPASS o sys.executable
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = AppPaths().base_dir

        version_file = base_dir / "VERSION"
        if version_file.exists():
            return version_file.read_text("utf-8").strip()
        return "0.0.0"

    def controlla_aggiornamenti(self) -> None:
        """Avvia il controllo aggiornamenti in un thread separato."""
        threading.Thread(target=self._controlla_thread, daemon=True).start()

    def _controlla_thread(self) -> None:
        try:
            url = f"https://api.github.com/repos/{self.repo_url}/releases/latest"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            dati = resp.json()

            tag_name = dati.get("tag_name", "").lstrip("v")
            
            if not tag_name:
                return

            if version.parse(tag_name) > version.parse(self.current_version.lstrip("v")):
                # Cerca l'asset corretto
                for asset in dati.get("assets", []):
                    if asset.get("name") == self.asset_name:
                        self._url_download_atteso = asset.get("browser_download_url")
                        self.aggiornamento_disponibile.emit(tag_name, dati.get("body", "Nessun changelog disponibile."))
                        return
                        
                _log.warning(f"Trovata release {tag_name} ma nessun asset corrispondente a {self.asset_name}.")

        except requests.RequestException as e:
            _log.warning(f"Errore nel controllo aggiornamenti: {e}")
        except Exception as e:
            _log.error(f"Errore inatteso controllo aggiornamenti: {e}")

    def scarica_aggiornamento(self) -> None:
        """Avvia il download in un thread separato."""
        if not self._url_download_atteso:
            self.errore.emit("Nessun URL di download valido trovato.")
            return
            
        threading.Thread(target=self._scarica_thread, daemon=True).start()

    def _scarica_thread(self) -> None:
        try:
            resp = requests.get(self._url_download_atteso, stream=True, timeout=15)
            resp.raise_for_status()
            
            total_size = int(resp.headers.get("content-length", 0))
            
            temp_dir = tempfile.gettempdir()
            out_file = os.path.join(temp_dir, f"update_{self.asset_name}")
            
            scaricati = 0
            with open(out_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        scaricati += len(chunk)
                        if total_size > 0:
                            percent = int(scaricati * 100 / total_size)
                            self.progresso_download.emit(percent)
                            
            self.download_completato.emit(out_file)
            
        except Exception as e:
            _log.error(f"Errore durante il download dell'aggiornamento: {e}")
            self.errore.emit(str(e))

    def applica_aggiornamento(self, nuovo_exe_path: str) -> None:
        """Applica l'aggiornamento usando un batch script temporaneo per sostituire l'eseguibile."""
        if not getattr(sys, "frozen", False):
            # Se siamo in ambiente di sviluppo (eseguito via python), non possiamo rimpiazzare l'exe
            self.errore.emit("Impossibile aggiornare: l'app non è in esecuzione come eseguibile compilato (exe).")
            return

        exe_corrente = sys.executable
        cartella_exe = os.path.dirname(exe_corrente)
        nome_exe = os.path.basename(exe_corrente)
        
        bat_path = os.path.join(tempfile.gettempdir(), "update_gestore_film.bat")
        
        script = f"""@echo off
timeout /t 2 /nobreak >nul
move /Y "{nuovo_exe_path}" "{exe_corrente}"
start "" "{exe_corrente}"
del "%~f0"
"""
        with open(bat_path, "w") as f:
            f.write(script)
            
        # Avvia il batch script
        subprocess.Popen(
            [bat_path], 
            creationflags=subprocess.CREATE_NO_WINDOW,
            shell=True
        )
        
        # Termina l'applicazione per sbloccare il file
        sys.exit(0)
