# Gestore Film Portable

Riorganizzatore automatico di film, serie TV e musica in una libreria in stile Jellyfin (film/serie con `[tmdbid-N]` e decadi, musica per artista/album), con identificazione via TMDB/Gemini/ChatGPT/MusicBrainz/AcoustID e analisi tecnica via ffmpeg.

Migrazione di un'app precedente (`Script_Film`, Python + Flet) verso un'applicazione desktop Windows in **PyQt6**, distribuita sia come **build portable** (nessuna installazione, dati accanto all'eseguibile) sia come **installer** (per chi preferisce un'installazione tradizionale).

> **Stato attuale: walking skeleton.** Sono complete le schermate **Percorsi** e **Scansione**, l'intero layer di business logic (`servizi`/`organizzatori` di `Script_Film` portati con type hints e alcuni bug corretti), il redesign UI (tema chiaro/scuro, finestra sempre massimizzata, layout responsive) e la catena di packaging (PyInstaller + installer). Le altre schermate (Approvazione, Code, Pulizia Archivio, Automazione, Impostazioni, Trickplay) sono voci di navigazione disabilitate, in attesa di essere portate una alla volta.

## Installazione

Scarica l'ultima release da **[Releases](https://github.com/AprileNunzio/Gestore-Film/releases/latest)**. Sono disponibili due varianti, stessa build:

- **Installer** (`GestoreFilmPortable-Setup-X.Y.Z.exe`): installa in `%APPDATA%\NunzioTech\Gestore_Film`, nessun privilegio amministratore richiesto, crea collegamenti Start Menu/Desktop e un disinstallatore.
- **Portable** (`GestoreFilmPortable-Portable-X.Y.Z.zip`): scompatta ed esegui `GestoreFilmPortable.exe`, nessuna installazione, tutti i dati restano accanto all'eseguibile — puoi spostare la cartella o portarla su una chiavetta USB.

## Requisiti

- Windows 10/11
- Python 3.12 (solo per lo sviluppo — l'utente finale non deve installare nulla)
- I binari `ffmpeg.exe`/`ffprobe.exe` (ffmpeg "essentials" build per Windows) copiati in `ffmpeg/bin/` — **non versionati in git** perché superano le dimensioni consigliate per un repository (~100 MB l'uno). Scaricali da [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (build "essentials", licenza LGPL) e copia `ffmpeg.exe`/`ffprobe.exe` in `ffmpeg/bin/`.

## Sviluppo

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt
.venv\Scripts\python main.py
```

Le chiavi API (TMDB, Gemini, OpenAI, AcoustID) vanno in un file `.env` nella root del progetto — copia `.env.example` e compila le tue chiavi. Nessuna è obbligatoria per l'avvio: le funzionalità che le richiedono si disattivano semplicemente se la chiave manca.

## Build

```powershell
# Build portable (PyInstaller --onedir)
.venv\Scripts\python -m PyInstaller --distpath build\dist --workpath build\work --noconfirm build\gestore_film.spec
```

Produce `build/dist/GestoreFilmPortable/` — cartella autosufficiente (`--onedir`, layout flat senza `_internal/`) pronta per essere copiata/zippata e distribuita. Tutti i dati (config, cache, log, database) vengono creati accanto a `GestoreFilmPortable.exe`, mai nella cartella da cui viene lanciato.

Per generare anche l'installer, serve [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`):

```powershell
$version = (Get-Content VERSION).Trim()
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "/DMyAppVersion=$version" build\installer.iss
```

Produce `build/installer_output/GestoreFilmPortable-Setup-X.Y.Z.exe`. Lo script (`build/installer.iss`) impacchetta la stessa cartella `build/dist/GestoreFilmPortable/` prodotta da PyInstaller — non serve nessuna build separata né logica applicativa diversa tra le due distribuzioni: installare equivale semplicemente a copiare la build portable in `%APPDATA%\NunzioTech\Gestore_Film` e aggiungere collegamenti/disinstallazione.

## Architettura

```
app/
  core/        # path portable, config, logging + dialog d'errore, stato condiviso
  services/     # integrazioni esterne (TMDB, Gemini, OpenAI, MusicBrainz, AcoustID, ffmpeg, watchdog, FTP) + motore job Qt
  organizers/   # logica di business per film/serie/musica + orchestratore universale
  ui/           # finestra principale, tema chiaro/scuro (theme.py), schermate PyQt6, widget riusabili
ffmpeg/bin/     # ffmpeg.exe/ffprobe.exe (da scaricare separatamente, vedi sopra)
build/          # spec PyInstaller + script installer Inno Setup
VERSION         # numero di versione, fonte di verità per build/gestore_film.spec e build/installer.iss
```

Principi seguiti nella migrazione (vedi commenti nei singoli moduli per i dettagli):
- **Nessun path assoluto o legato alla cwd**: tutto risolto tramite `app/core/paths.py::AppPaths`, che distingue tra esecuzione da sorgente e da eseguibile PyInstaller (`sys.frozen`).
- **Nessun aggiornamento della UI da thread di background**: ogni comunicazione worker→UI passa da segnali Qt collegati a *bound method* di QObject sul thread GUI (mai lambda/funzioni anonime, che romperebbero la marshalizzazione automatica tra thread — vedi `app/services/job_queue.py`).
- **Errori mai silenziosi**: un `sys.excepthook` globale (`app/core/logging_setup.py`) logga ogni eccezione non gestita in `error_log.txt` e mostra un `QMessageBox` comprensibile, anche per errori durante l'avvio.

## Roadmap

- [ ] Portare le schermate rimanenti (Approvazione, Code, Pulizia Archivio, Automazione, Impostazioni, Trickplay)
- [x] Redesign completo della UI (fullscreen, responsive, light/dark)
- [ ] Auto-update automatico da GitHub Releases
- [x] Installer (distribuzione parallela alla build portable)
- [ ] Bump automatico di versione e pubblicazione release via CI ad ogni build
