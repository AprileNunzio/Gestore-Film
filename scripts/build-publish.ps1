<#
.SYNOPSIS
    Build completa + pubblicazione: bump versione, build locale (PyInstaller
    + installer + zip), commit del bump, tag, push, e release GitHub con gli
    artefatti allegati. Richiede una working tree pulita e `gh` autenticato.

.PARAMETER Bump
    Parte di versione da incrementare: patch (default), minor, major.
#>
param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch"
)

$ErrorActionPreference = "Stop"
$radiceProgetto = Split-Path -Parent $PSScriptRoot
Set-Location $radiceProgetto

$statoGit = git status --porcelain
if ($statoGit) {
    throw "Ci sono modifiche non committate. Fai commit o stash prima di pubblicare una release."
}

& "$PSScriptRoot\build-local.ps1" -Bump $Bump
if ($LASTEXITCODE -ne 0) { throw "Build locale fallita, pubblicazione annullata" }

$versione = (Get-Content "$radiceProgetto\VERSION" -Raw).Trim()

Write-Output "==> Commit del bump di versione"
git add VERSION package.json
git commit -m "Bump versione a $versione"

Write-Output "==> Tag v$versione"
git tag "v$versione"

Write-Output "==> Push commit e tag"
git push origin main
git push origin "v$versione"

Write-Output "==> Creazione release GitHub v$versione"
$setupExe = "$radiceProgetto\build\installer_output\GestoreFilmPortable-Setup-$versione.exe"
$portableZip = "$radiceProgetto\build\installer_output\GestoreFilmPortable-Portable-$versione.zip"
gh release create "v$versione" "$setupExe" "$portableZip" --title "v$versione" --generate-notes
if ($LASTEXITCODE -ne 0) { throw "Creazione release GitHub fallita" }

Write-Output ""
Write-Output "==> Pubblicata release v$versione"
