# register_overlay.ps1 — Enregistrement/désenregistrement de l'overlay d'icône
# « lien » de Recherche Documentaire, sans exécuter l'installeur MSI.
#
# Le script compile la DLL COM native (C++) si elle est absente (cl.exe d'un
# prompt VS x64 ou g++ MinGW), la copie avec doclink.ico dans un répertoire
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
$CppFile = Join-Path $OverlayDir "RechercheDocumentaireOverlay.cpp"
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

    Write-Info "Compilation de l'overlay natif (C++)..."
    # Le shell moderne refuse de charger le CLR .NET dans explorer.exe pour les
    # extensions tierces : l'overlay est desormais une DLL native. Compilation
    # via cl.exe (prompt VS x64) ou g++ (MinGW) sur le PATH ; un compilateur C++
    # n'est pas livre avec Windows, contrairement a csc.
    $cl = Get-Command cl.exe -ErrorAction SilentlyContinue
    $gpp = Get-Command g++.exe -ErrorAction SilentlyContinue
    if ($cl) {
        # /MT : lier le CRT statiquement. Par defaut cl utilise /MD et la DLL
        # depend alors de vcruntime140.dll/msvcp140.dll ; si le processus hote
        # (explorer.exe) ne les resolve pas, le chargement echoue avec
        # 0x800401F9 CO_E_ERRORINDLL. Une extension shell doit etre autonome.
        & cl.exe /nologo /LD /MT /O2 /EHsc $CppFile /Fe:$DllPath
        if ($LASTEXITCODE -ne 0) { throw "cl a echoue (code $LASTEXITCODE) ; lancez depuis un prompt VS x64." }
    } elseif ($gpp) {
        # -static : la DLL ne doit dependre d'aucune DLL runtime MinGW
        # (libstdc++-6.dll, libgcc_s_*.dll) ; explorer.exe ne les trouverait
        # pas dans son chemin de recherche et le chargement echouerait.
        & g++.exe -static -static-libgcc -static-libstdc++ -shared -O2 -std=c++11 -o $DllPath $CppFile
        if ($LASTEXITCODE -ne 0) { throw "g++ a echoue (code $LASTEXITCODE)" }
    } else {
        throw "Aucun compilateur C++ (cl.exe ou g++) trouve. Ouvrez un prompt VS x64, ou compilez RechercheDocumentaireOverlay.cpp et fournissez la DLL via -SourceDll."
    }
    Write-Info "DLL compilee : $DllPath"
    # Verifier l'architecture de la DLL : explorer.exe est 64 bits et refuse
    # silencieusement une DLL 32 bits. Lecture du champ Machine de l'en-tete PE.
    try {
        $bytes = [IO.File]::ReadAllBytes($DllPath)
        $peOff = [BitConverter]::ToInt32($bytes, 0x3C)
        $machine = [BitConverter]::ToUInt16($bytes, $peOff + 4)
        if ($machine -ne 0x8664) {
            throw ("DLL compilee en 32 bits (machine=0x{0:X4}) : explorer.exe 64 bits ne peut pas la charger. Utilisez un toolchain x64 (prompt VS x64 ou mingw-w64 x86_64)." -f $machine)
        }
        Write-Info "Architecture DLL : x64 (OK)"
    } catch { throw }
Copy-Item $IcoFile (Join-Path $InstallDir "doclink.ico") -Force

# --- Enregistrement COM ---
Write-Info "Enregistrement ($Root)..."
function Ensure-RegistryKey($path) {
    # New-Item -Force tente de supprimer une clé existante (et échoue si elle a
    # des sous-clés, ex. les overlays OneDrive) : on ne crée que si absente.
    if (-not (Test-Path $path)) { New-Item -Path $path | Out-Null }
}

$clsidKey = "$ClassesRoot\CLSID\$Clsid"
Ensure-RegistryKey $clsidKey
Set-ItemProperty -Path $clsidKey -Name "(default)" -Value $CsProj
# DLL native : InprocServer32 pointe directement sur la DLL (pas de mscoree).
Ensure-RegistryKey "$clsidKey\InprocServer32"
$inproc = "$clsidKey\InprocServer32"
Set-ItemProperty -Path $inproc -Name "(default)" -Value $DllPath
Set-ItemProperty -Path $inproc -Name "ThreadingModel" -Value "Apartment"

$overlayBase = if ($CurrentUser) {
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers"
} else {
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers"
}
Ensure-RegistryKey $overlayBase
$overlayKey = "$overlayBase\$OverlayName"
Ensure-RegistryKey $overlayKey
Set-ItemProperty -Path $overlayKey -Name "(default)" -Value $Clsid

Write-Info "Overlay enregistre :"
Write-Info "  CLSID  : $clsidKey"
Write-Info "  Overlay: $overlayKey"
Write-Info "  DLL    : $DllPath"
Write-Info "Redemarrez l'Explorateur (taskkill /f /im explorer.exe ; start explorer.exe) ou la session."
