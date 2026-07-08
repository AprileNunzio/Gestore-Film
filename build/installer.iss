; Script Inno Setup per Gestore Film Portable.
;
; Installa la STESSA cartella prodotta da PyInstaller (build/dist/GestoreFilmPortable)
; dentro %APPDATA%\NunzioTech\Gestore_Film, per-utente e senza privilegi admin
; (PrivilegesRequired=lowest). Non serve nessuna logica speciale nel codice Python
; per distinguere "portable" da "installato": AppPaths risolve sempre tutto
; relativamente alla cartella dell'eseguibile, quindi installare qui equivale
; semplicemente a copiare la build portable in una posizione fissa per-utente
; e aggiungere collegamenti/disinstallazione. La build portable (zip) resta
; comunque distribuita in parallelo per chi preferisce nessuna installazione.
;
; MyAppVersion viene normalmente passato da riga di comando (ISCC /DMyAppVersion=X.Y.Z),
; il valore qui sotto è solo un fallback per compilazioni manuali dall'IDE di Inno Setup.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Gestore Film Portable"
#define MyAppPublisher "NunzioTech"
#define MyAppExeName "GestoreFilmPortable.exe"
#define MyDistDir "..\build\dist\GestoreFilmPortable"

[Setup]
AppId={{09D1C42F-31CC-4057-8BB0-52B408A9C8DC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userappdata}\NunzioTech\Gestore_Film
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=GestoreFilmPortable-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone aggiuntive:"; Flags: unchecked

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Disinstalla {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia {#MyAppName}"; Flags: nowait postinstall skipifsilent
