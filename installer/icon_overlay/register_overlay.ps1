# register_overlay.ps1 — Enregistrement/désenregistrement de l'overlay d'icône
# « lien » de Recherche Documentaire, sans exécuter l'installeur MSI.
#
# Le script compile la DLL COM si elle est absente (csc.exe du framework .NET,
# présent sur tout Windows), la copie avec doclink.ico dans un répertoire
# d'installation, puis enregistre le CLSID et la clé ShellIconOverlayIdentifiers.
#
# Usage :
#   powershell -ExecutionPolicy Bypass -File installer\icon_overlay\register_overlay.ps1            # machine (HKLM, élévation requise)
#   powershell ... -File register_overlay.ps1 -CurrentUser                                             # HKCU, sans élévation
#   powershell ... -File register_overlay.ps1 -Unregister                                             # suppression
#   powershell ... -File register_overlay.ps1 -InstallDir "C:\outil" -SourceDll ".\build\windows"    # DLL précompilée
#
# Après enregistrement : redémarrer l'Explorateur (ou la session) pour que
# l'overlay soit chargé (Windows met les icon overlays en cache au démarrage).

param(
    [switch]$Unregister,
    [switch]$CurrentUser,
    [string]$InstallDir,
    [string]$SourceDll
)

$ErrorActionPreference = "Stop"

$OverlayDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CsFile = Join-Path $OverlayDir "RechercheDocumentaireOverlay.cs"
$IcoFile = Join-Path $OverlayDir "doclink.ico"
$Clsid = "{B4F9A2C1-7E3D-4A8E-9C2F-1D5E6A7B8C9D}"
$OverlayName = "RechercheDocumentaireLink"
$CsProj = "RechercheDocumentaire.DocumentLinkOverlay"

function Write-Info($msg) { Write-Host "[overlay] $msg" }

# --- Racine registre selon le mode ---
$Root = if ($CurrentUser) { "HKCU:" } else { "HKLM:" }
$ClassesRoot = if ($CurrentUser) { "HKCU:\Software\Classes" } else { "HKLM:\Software\Classes" }
if (-not $CurrentUser -and -not ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Le mode machine (HKLM) requiert une session elevuee (executer en administrateur) ou utiliser -CurrentUser."
}

# --- Désenregistrement ---
if ($Unregister) {
    Write-Info "Suppression de l'enregistrement..."
    # ShellIconOverlayIdentifiers vit sous Software\Microsoft\Windows\... pour HKLM et HKCU ;
    # on nettoie les deux racines ainsi que les deux CLSID possibles.
    $paths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\$OverlayName",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\$OverlayName"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Info "supprime : $p" }
    }
    foreach ($root in @("HKLM:\SOFTWARE\Classes\CLSID\$Clsid", "HKCU:\SOFTWARE\Classes\CLSID\$Clsid")) {
        if (Test-Path $root) { Remove-Item $root -Recurse -Force; Write-Info "supprime : $root" }
    }
    Write-Info "Desenregistrement termine. Redemarrez l'Explorateur pour purger le cache."
    exit 0
}

# --- Répertoire d'installation ---
if (-not $InstallDir) {
    $InstallDir = if ($CurrentUser) {
        Join-Path $env:LOCALAPPDATA "RechercheDocumentaire"
    } else {
        Join-Path $env:ProgramData "RechercheDocumentaire"
    }
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

$DllPath = Join-Path $InstallDir "RechercheDocumentaireOverlay.dll"

# --- DLL : copie précompilée ou compilation à la volée ---
if ($SourceDll -and (Test-Path $SourceDll)) {
    Write-Info "Copie de la DLL precompilee : $SourceDll"
    Copy-Item $SourceDll $DllPath -Force
} elseif (Test-Path $DllPath) {
    Write-Info "DLL existante reutilisee : $DllPath"
} else {
    Write-Info "Compilation de l'overlay via csc.exe..."
    $csc = Get-ChildItem "C:\Windows\Microsoft.NET\Framework64\v*\csc.exe" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $csc) { throw "csc.exe introuvable ; fournissez une DLL via -SourceDll." }
    & $csc.FullName /nologo /target:library /platform:x64 /optimize+ /out:$DllPath $CsFile
    if ($LASTEXITCODE -ne 0) { throw "csc a echoue (code $LASTEXITCODE)" }
    Write-Info "DLL compilee : $DllPath"
}
Copy-Item $IcoFile (Join-Path $InstallDir "doclink.ico") -Force

# --- Enregistrement COM ---
Write-Info "Enregistrement ($Root)..."
$clsidKey = "$ClassesRoot\CLSID\$Clsid"
New-Item -Path $clsidKey -Force | Out-Null
Set-ItemProperty -Path $clsidKey -Name "(default)" -Value $CsProj
New-Item -Path "$clsidKey\InprocServer32" -Force | Out-Null
Set-ItemProperty -Path "$clsidKey\InprocServer32" -Name "(default)" -Value $DllPath
Set-ItemProperty -Path "$clsidKey\InprocServer32" -Name "ThreadingModel" -Value "Apartment"

$overlayBase = if ($CurrentUser) {
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers"
} else {
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers"
}
New-Item -Path $overlayBase -Force | Out-Null
$overlayKey = "$overlayBase\$OverlayName"
New-Item -Path $overlayKey -Force | Out-Null
Set-ItemProperty -Path $overlayKey -Name "(default)" -Value $Clsid

Write-Info "Overlay enregistre :"
Write-Info "  CLSID  : $clsidKey"
Write-Info "  Overlay: $overlayKey"
Write-Info "  DLL    : $DllPath"
Write-Info "Redemarrez l'Explorateur (taskkill /f /im explorer.exe ; start explorer.exe) ou la session."
