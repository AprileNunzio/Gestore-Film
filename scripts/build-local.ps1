<#
.SYNOPSIS
    Build locale completa: bump patch della versione, build PyInstaller
    (eseguibile onefile, stesso schema del workflow GitHub Actions in
    .github/workflows/build.yml) + installer Inno Setup (installer/installer.iss).
    Non tocca git ne' GitHub — per quello vedi build-publish.ps1 (npm run build:publish).

.PARAMETER Bump
    Parte di versione da incrementare prima della build: patch (default), minor, major.
#>
param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch"
)

$ErrorActionPreference = "Stop"
$radiceProgetto = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $radiceProgetto ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Venv non trovato in .venv\. Crealo prima con: py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements-build.txt"
}

Write-Output "==> Bump versione ($Bump)"
$versione = & "$PSScriptRoot\bump-version.ps1" -Parte $Bump | Select-Object -Last 1

Write-Output "==> Build PyInstaller (versione $versione)"
& $venvPython -m PyInstaller --distpath "$radiceProgetto\dist" --workpath "$radiceProgetto\build" --noconfirm "$radiceProgetto\Gestore_Film_Portable.spec"
if ($LASTEXITCODE -ne 0) { throw "Build PyInstaller fallita" }

Write-Output "==> Compilazione installer (Inno Setup)"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc)) {
    throw "ISCC.exe (Inno Setup 6) non trovato. Installalo con: winget install JRSoftware.InnoSetup"
}
New-Item -ItemType Directory -Force -Path "$radiceProgetto\installer_output" | Out-Null
& $iscc "/DMyAppVersion=$versione" "$radiceProgetto\installer\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Compilazione installer fallita" }

Write-Output ""
Write-Output "==> Fatto. Versione ${versione}:"
Get-ChildItem "$radiceProgetto\dist" | Select-Object Name, @{N = "SizeMB"; E = { [math]::Round($_.Length / 1MB, 1) } }
Get-ChildItem "$radiceProgetto\installer_output" | Select-Object Name, @{N = "SizeMB"; E = { [math]::Round($_.Length / 1MB, 1) } }
