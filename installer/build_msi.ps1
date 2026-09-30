# Build de l'installeur MSI « Recherche Documentaire » (Windows).
# Prérequis : Python 3.12+ et WiX Toolset v3 (candle/light dans le PATH,
#             ou $env:WIX / $env:WIX_BIN_DIR).
# Usage : powershell -ExecutionPolicy Bypass -File installer\build_msi.ps1 [-Version 0.1.0]

param(
    [string]$Version = "0.1.0",
    [switch]$SkipInstaller   # construit seulement les executables PyInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot "build\windows"
$DistDir = Join-Path $ProjectRoot "dist"
$MsiName = "RechercheDocumentaire-$Version-win64.msi"

if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

Write-Host "==> Installation des dependances Python"
python -m pip install --upgrade pip
python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
python -m pip install pyinstaller pywin32

$AppPy = Join-Path $ProjectRoot "recherche_doc\app.py"
$GuiPy = Join-Path $ProjectRoot "recherche_doc\search\gui_app.py"

Write-Host "==> Freeze PyInstaller : moteur de synchro"
$AppSpec = Join-Path $BuildDir "app.spec"
@"
# -*- mode: python ; coding: utf-8 -*-
a = Analysis([r"$AppPy"],
             pathex=[r"$ProjectRoot"],
             datas=[],
             hiddenimports=["recherche_doc.windows_provider"],
             excludes=["tkinter"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas,
          name="RechercheDocumentaire", console=True, exclude_binaries=False)
"@ | Set-Content -Encoding ASCII $AppSpec
python -m PyInstaller --noconfirm --clean --workpath "$BuildDir\work" --distpath $BuildDir $AppSpec

Write-Host "==> Freeze PyInstaller : interface de recherche (GUI Tkinter)"
$GuiSpec = Join-Path $BuildDir "gui.spec"
@"
# -*- mode: python ; coding: utf-8 -*-
a = Analysis([r"$GuiPy"],
             pathex=[r"$ProjectRoot"],
             datas=[],
             hiddenimports=["recherche_doc.search.ui"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas,
          name="RechercheDocumentaireSearch", console=False, exclude_binaries=False)
"@ | Set-Content -Encoding ASCII $GuiSpec
python -m PyInstaller --noconfirm --clean --workpath "$BuildDir\work" --distpath $BuildDir $GuiSpec

Copy-Item (Join-Path $ProjectRoot "config.example.yaml") $BuildDir

if ($SkipInstaller) {
    Write-Host "==> -SkipInstaller : executables seulement dans $BuildDir"
    exit 0
}

$WixBin = if ($env:WIX_BIN_DIR) { $env:WIX_BIN_DIR }
          elseif ($env:WIX) { Join-Path $env:WIX "bin" }
          else { "" }
function Resolve-WixTool($tool) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($cmd) { return $tool }
    if ($WixBin -and (Test-Path (Join-Path $WixBin "$tool.exe"))) {
        return (Join-Path $WixBin "$tool.exe")
    }
    throw "WiX Toolset v3 introuvable : installez WiX 3.14 ou definissez WIX/WIX_BIN_DIR"
}

Write-Host "==> Compilation WiX : candle"
$WxsObj = Join-Path $BuildDir "recherche_documentaire.wixobj"
$WxsPath = Join-Path $PSScriptRoot "recherche_documentaire.wxs"
& (Resolve-WixTool "candle") `
    -nologo `
    -arch x64 `
    "-dProductVersion=$Version" `
    "-dBuildDir=$BuildDir" `
    "-dProjectRoot=$ProjectRoot" `
    -out $WxsObj `
    $WxsPath
if ($LASTEXITCODE -ne 0) { throw "candle a echoue (code $LASTEXITCODE)" }

Write-Host "==> Edition de lien WiX : light"
$MsiPath = Join-Path $DistDir $MsiName
& (Resolve-WixTool "light") `
    -nologo `
    -ext WixUIExtension `
    -ext WixUtilExtension `
    -out $MsiPath `
    $WxsObj
if ($LASTEXITCODE -ne 0) { throw "light a echoue (code $LASTEXITCODE)" }

Write-Host "==> MSI produit : $MsiPath"
