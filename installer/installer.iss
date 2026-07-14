; Installer Inno Setup per Gestore Film Portable.
;
; Installa il singolo eseguibile onefile prodotto da Gestore_Film_Portable.spec
; nella stessa cartella AppData che l'app usa gia' per i propri dati
; (app/core/paths.py::AppPaths.dati_dir) -- exe e dati convivono li',
; cosi' non serve alcun privilegio di amministratore (PrivilegesRequired=lowest)
; e l'app installata legge/scrive esattamente dove si aspetta.
;
; Richiede la versione passata da riga di comando: ISCC.exe /DMyAppVersion=X.Y.Z installer.iss

#define MyAppName "Gestore Film Portable"
#define MyAppPublisher "NunzioTech"
#define MyAppExeName "Gestore_Film_Portable.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userappdata}\{#MyAppPublisher}\GestoreFilmPortable
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer_output
OutputBaseFilename=GestoreFilmPortable-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone aggiuntive:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Disinstalla {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia {#MyAppName}"; Flags: nowait postinstall skipifsilent
