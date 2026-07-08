<#
.SYNOPSIS
    Incrementa la versione del progetto (file VERSION, fonte di verita') e la
    rispecchia in package.json (usato solo come wrapper npm, non pubblicato
    su npm — vedi package.json).

.PARAMETER Parte
    Quale parte del semver incrementare: patch (default), minor, major.
#>
param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Parte = "patch"
)

$ErrorActionPreference = "Stop"
$radiceProgetto = Split-Path -Parent $PSScriptRoot
$fileVersion = Join-Path $radiceProgetto "VERSION"
$filePackageJson = Join-Path $radiceProgetto "package.json"

$versioneAttuale = (Get-Content $fileVersion -Raw).Trim()
$componenti = $versioneAttuale.Split(".")
if ($componenti.Count -ne 3) {
    throw "VERSION non e' nel formato X.Y.Z: '$versioneAttuale'"
}
[int]$major, [int]$minor, [int]$patch = $componenti

switch ($Parte) {
    "major" { $major++; $minor = 0; $patch = 0 }
    "minor" { $minor++; $patch = 0 }
    "patch" { $patch++ }
}

$nuovaVersione = "$major.$minor.$patch"
Set-Content -Path $fileVersion -Value $nuovaVersione -NoNewline

# Sostituzione mirata della riga "version" invece di un round-trip
# ConvertFrom-Json/ConvertTo-Json, che reimpagina l'intero file con una
# formattazione non standard (doppi spazi prima dei due punti, apici
# escapati come ') — cosi' il resto del file resta invariato.
$contenutoPackageJson = Get-Content $filePackageJson -Raw
$contenutoPackageJson = $contenutoPackageJson -replace '"version":\s*"[^"]*"', "`"version`": `"$nuovaVersione`""
Set-Content -Path $filePackageJson -Value $contenutoPackageJson -NoNewline

Write-Output "Versione: $versioneAttuale -> $nuovaVersione"
Write-Output $nuovaVersione
