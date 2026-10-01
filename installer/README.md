# Installeur MSI — Recherche Documentaire

## Contenu

- `recherche_documentaire.wxs` — manifeste WiX v3 : installation per-machine
  dans `Program Files\RechercheDocumentaire`, base de données dans le
  répertoire caché `.docsearch`, raccourcis menu Démarrer (interface de
  recherche + lancement du moteur),MajorUpgrade, CustomAction d'écriture de
  `config.yaml`, case à cocher « Lancer le moteur de synchro » en fin
  d'installation.
- `write_config.vbs` — CustomAction MSI (deferred, elevated) qui génère
  `config.yaml` à partir des propriétés MSI.
- `build_msi.ps1` — build complet : installation des dépendances, freeze
  PyInstaller (moteur console + GUI Tkinter), compilation `candle` + `light`.
- `License.rtf` — licence affichée par l'assistant MSI.

## Build local (Windows)

```powershell
# Prérequis : Python 3.12+, WiX Toolset v3.14 (https://wixtoolset.org)
powershell -ExecutionPolicy Bypass -File installer\build_msi.ps1 -Version 0.1.0
# => dist\RechercheDocumentaire-0.1.0-win64.msi
```

## Build CI (GitHub Actions)

`.github/workflows/build-msi.yml` :

1. job `tests` (ubuntu) : installe tk/tcl + xvfb, dépendances CPU torch,
   exécute `python -m unittest discover -s tests` ;
2. job `build-msi` (windows-latest, dépend du job tests) : installe WiX 3.14
   en silence, exécute `build_msi.ps1` (version issue du tag `vX.Y.Z`,
   sinon `0.1.0`), publie l'artefact `RechercheDocumentaire-msi` et, pour
   les tags `v*`, crée une Release GitHub avec le MSI en pièce jointe.

Déclencheurs : push sur `main`, PR, tags `v*`, et `workflow_dispatch`.

## Installation silencieuse avec configuration

```bat
msiexec /i RechercheDocumentaire-0.1.0-win64.msi /qn ^
  DRIVE_LETTER=R: ^
  IMAP_URL=imap.example.com MAIL_LOGIN=moi@example.com MAIL_PASSWORD=secret ^
  LAST_RUN=2025-01-01
```

Toute propriété absente est laissée vide ; l'utilisateur peut aussi éditer
`config.yaml` (copié depuis `config.example.yaml`) après installation.

## Enregistrement de l'overlay d'icône sans installeur

L'overlay « lien » (badge des liens sous `Categories/`) peut être enregistré
sans exécuter le MSI :

```bat
:: Machine (HKLM) — session administrateur
powershell -ExecutionPolicy Bypass -File installer\icon_overlay\register_overlay.ps1

:: Utilisateur courant (HKCU) — sans élévation
powershell -ExecutionPolicy Bypass -File installer\icon_overlay\register_overlay.ps1 -CurrentUser

:: DLL précompilée (ex. issue du build) et répertoire d'installation
powershell ... -File register_overlay.ps1 -SourceDll "build\windows\RechercheDocumentaireOverlay.dll" -InstallDir "C:\outil"

:: Désenregistrement
powershell -ExecutionPolicy Bypass -File installer\icon_overlay\register_overlay.ps1 -Unregister
```

Sans `-SourceDll`, le script compile `RechercheDocumentaireOverlay.cs` à la
volée avec `csc.exe` (framework .NET, présent sur tout Windows). Après
enregistrement, redémarrez l'Explorateur (`taskkill /f /im explorer.exe` puis
`start explorer.exe`) ou la session : Windows charge les icon overlays au
démarrage de l'Explorateur.

