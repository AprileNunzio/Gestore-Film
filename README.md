# Gestore Film Portable

Riorganizzatore automatico di film, serie TV e musica in una libreria in stile Jellyfin (film/serie con `[tmdbid-N]` e decadi, musica per artista/album), con identificazione via TMDB/Gemini/ChatGPT/MusicBrainz/AcoustID e analisi tecnica via ffmpeg.

Migrazione di un'app precedente (`Script_Film`, Python + Flet) verso un'applicazione desktop Windows in **PyQt6**, distribuita sia come **eseguibile portable singolo** sia come **installer** (Inno Setup) — entrambi usano gli stessi dati utente in `%APPDATA%\NunzioTech\GestoreFilmPortable`, cosi' config/cache/chiavi API sopravvivono a un aggiornamento dell'eseguibile invece di richiedere di riconfigurare tutto ad ogni nuova versione.

> **Stato attuale.** Tutte le 9 schermate (Dashboard, Percorsi, Scansione, Approvazione, Code, Pulizia Archivio, Automazione, Impostazioni, Trickplay) sono complete e cablate in `main.py`, con l'intero layer di business logic (`servizi`/`organizzatori` di `Script_Film` portati con type hints e alcuni bug corretti). L'interfaccia usa un design system a token condivisi ([app/ui/design_tokens.py](app/ui/design_tokens.py)) e i componenti [qfluentwidgets](https://qfluentwidgets.com/): tema scuro vivace con un colore di accento distinto per categoria/schermata (`design_tokens.CATEGORIA`), finestra sempre massimizzata, barra di navigazione responsive (si riduce a sole icone sotto i 900px). Completa la catena di packaging (PyInstaller + wrapper npm per bump versione automatico).

## Installazione

Scarica l'ultima release da **[Releases](https://github.com/AprileNunzio/Gestore-Film/releases/latest)**. Due varianti disponibili:

- **Portable** (`Gestore_Film_Portable.exe`): esegui direttamente, nessuna installazione. Puoi spostarlo o portarlo su una chiavetta USB.
- **Installer** (`GestoreFilmPortable-Setup-X.Y.Z.exe`): installa in `%APPDATA%\NunzioTech\GestoreFilmPortable`, nessun privilegio amministratore richiesto, crea collegamenti Start Menu/Desktop e un disinstallatore.

In entrambi i casi i dati (config, cache, log, database, chiavi API) vengono creati/letti in `%APPDATA%\NunzioTech\GestoreFilmPortable`, non accanto all'eseguibile: le due varianti condividono la stessa configurazione.

## Requisiti

- Windows 10/11
- Python 3.12 (solo per lo sviluppo — l'utente finale non deve installare nulla)
- I binari `ffmpeg.exe`/`ffprobe.exe` (ffmpeg "essentials" build per Windows) copiati in `ffmpeg/bin/` — **non versionati in git** perché superano le dimensioni consigliate per un repository (~100 MB l'uno). Scaricali da [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (build "essentials", licenza LGPL) e copia `ffmpeg.exe`/`ffprobe.exe` in `ffmpeg/bin/`.
- Per compilare (facoltativo se lavori solo sul codice): [Node.js](https://nodejs.org/) (solo come runner comodo per gli script di build, **il progetto non ha nessuna dipendenza Node/npm**), [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`) per l'installer, `gh` CLI autenticato per pubblicare release.

## Sviluppo

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt
.venv\Scripts\python main.py
```

Le chiavi API (TMDB, Gemini, OpenAI, AcoustID) si inseriscono dalla schermata **Impostazioni** dell'app (salvate in `%APPDATA%\NunzioTech\GestoreFilmPortable\settings.json`, applicate subito senza riavvio). In sviluppo puoi anche seminarle da un file `.env` nella root del progetto (copia `.env.example`) — usato solo come fallback per i campi lasciati vuoti in Impostazioni. Nessuna chiave è obbligatoria per l'avvio: le funzionalità che le richiedono si disattivano semplicemente se la chiave manca.

## Build

Il progetto è Python puro — `package.json` esiste solo come **wrapper comodo** attorno agli script PowerShell in `scripts/` (nessuna dipendenza da installare, `npm install` non serve):

```powershell
npm run build:local     # bump patch di VERSION, build PyInstaller (onefile) + installer Inno Setup — solo in locale
npm run build:publish   # come sopra + commit del bump, tag git, push, release GitHub con entrambi gli eseguibili allegati
npm run version:bump    # solo il bump di versione (usa -- --Parte minor|major per non incrementare la patch)
```

`build:local` produce `dist/Gestore_Film_Portable.exe` (singolo file, nessuna cartella `_internal/` da distribuire insieme) e `installer_output/GestoreFilmPortable-Setup-X.Y.Z.exe`. Tutti i dati dell'app (config, cache, log, database, chiavi API) vengono creati in `%APPDATA%\NunzioTech\GestoreFilmPortable`, mai accanto all'eseguibile o nella cartella da cui viene lanciato — vedi `app/core/paths.py::AppPaths`. `build:publish` richiede una working tree pulita e `gh` già autenticato — **push e release sono operazioni pubbliche**, eseguilo solo quando vuoi davvero pubblicare. Il push del tag fa scattare anche [.github/workflows/build.yml](.github/workflows/build.yml), che ricompila l'eseguibile onefile in CI (senza installer, CI non ha Inno Setup) e lo allega alla medesima release.

Equivalente manuale, senza npm/PowerShell:

```powershell
.venv\Scripts\python -m PyInstaller --distpath dist --workpath build --noconfirm Gestore_Film_Portable.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "/DMyAppVersion=$(Get-Content VERSION)" installer\installer.iss
```

## Architettura

```
app/
  core/        # path portable, config, logging + dialog d'errore, stato condiviso
  services/     # integrazioni esterne (TMDB, Gemini, OpenAI, MusicBrainz, AcoustID, ffmpeg, watchdog, FTP) + motore job Qt
  organizers/   # logica di business per film/serie/musica + orchestratore universale
  ui/           # finestra principale (qfluentwidgets), design system a token, schermate PyQt6, componenti/widget riusabili
ffmpeg/bin/     # ffmpeg.exe/ffprobe.exe (da scaricare separatamente, vedi sopra)
Gestore_Film_Portable.spec  # spec PyInstaller (eseguibile onefile)
installer/      # script Inno Setup (installer/installer.iss)
scripts/        # script PowerShell richiamati dagli npm script (bump versione, build, publish)
VERSION         # numero di versione, fonte di verità (rispecchiato in package.json ad ogni bump)
```

Principi seguiti nella migrazione (vedi commenti nei singoli moduli per i dettagli):
- **Nessun path assoluto o legato alla cwd**: tutto risolto tramite `app/core/paths.py::AppPaths`, che distingue tra esecuzione da sorgente e da eseguibile PyInstaller (`sys.frozen`) e separa gli asset portati con l'app (`base_dir`: ffmpeg/bin, resources, `.env` di sviluppo) dai dati utente (`dati_dir` in `%APPDATA%\NunzioTech\GestoreFilmPortable`: config, cache, log, chiavi API).
- **Nessun aggiornamento della UI da thread di background**: ogni comunicazione worker→UI passa da segnali Qt collegati a *bound method* di QObject sul thread GUI (mai lambda/funzioni anonime, che romperebbero la marshalizzazione automatica tra thread — vedi `app/services/job_queue.py`).
- **Errori mai silenziosi**: un `sys.excepthook` globale (`app/core/logging_setup.py`) logga ogni eccezione non gestita in `error_log.txt` e mostra un `QMessageBox` comprensibile, anche per errori durante l'avvio.

## Licenza

Il progetto usa [PyQt6-Fluent-Widgets](https://qfluentwidgets.com/) per l'interfaccia, distribuita sotto **GPLv3** (licenza commerciale disponibile a pagamento per chi non vuole i vincoli GPL). Di conseguenza l'intero progetto è **GPL-3.0-or-later**: se distribuisci una build di questa app, il codice sorgente deve restare disponibile sotto gli stessi termini.

## Roadmap

- [x] Portare le schermate rimanenti (Approvazione, Pulizia Archivio, Automazione, Trickplay)
- [x] Nuovo Monitor Code Attive Enterprise (telemetria, UI avanzata, FSM)
- [x] Redesign completo della UI su design system a token + qfluentwidgets (fullscreen, responsive, tema scuro vivace con accenti colorati per categoria)
- [ ] Tema chiaro alternativo (opzionale, non pianificato)
- [x] Installer Inno Setup accanto alla build portable, dati condivisi in `%APPDATA%`
- [ ] Auto-update automatico da GitHub Releases
- [x] Bump automatico di versione (locale e in pubblicazione) via `npm run build:local`/`build:publish`
- [x] Workflow GitHub Actions per build+release automatiche al push di un tag/release (`.github/workflows/build.yml`)
