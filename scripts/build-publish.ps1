<#
.SYNOPSIS
    Build completa + pubblicazione: bump versione, build locale (PyInstaller
    onefile + installer Inno Setup), commit del bump, tag, push, e release
    GitHub con entrambi gli artefatti allegati. Richiede una working tree
    pulita e `gh` autenticato.

    Nota: il push del tag v$versione fa scattare anche
    .github/workflows/build.yml, che ricompila l'eseguibile onefile in CI e lo
    allega alla stessa release alla pubblicazione (l'installer resta solo
    locale, CI non ha Inno Setup) — i due eseguibili onefile (locale e CI)
    sono equivalenti, questo script pubblica quello locale senza attendere CI.

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
$exePath = "$radiceProgetto\dist\Gestore_Film_Portable.exe"
$setupExe = "$radiceProgetto\installer_output\GestoreFilmPortable-Setup-$versione.exe"
gh release create "v$versione" "$exePath" "$setupExe" --title "v$versione" --generate-notes
if ($LASTEXITCODE -ne 0) { throw "Creazione release GitHub fallita" }

Write-Output ""
Write-Output "==> Pubblicata release v$versione"
