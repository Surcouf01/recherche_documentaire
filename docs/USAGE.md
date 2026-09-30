# Guide d'utilisation — Recherche Documentaire

## 1. Installation

### Plugin de l'explorateur Windows

Après installation du MSI, le menu contextuel de tout lecteur (clic droit)
propose **« Recherche Documentaire... »**. La commande lance l'interface de
recherche **pré-filtrée sur le dossier visité** : si vous cliquez depuis
`R:\Categories\Facture\Dupont\`, la catégorie `Facture` et le tag `Dupont`
sont déjà sélectionnés. Gestion manuelle :

```bat
RechercheDocumentaireSearch.exe --register   :: répare/enregistre le verbe
RechercheDocumentaireSearch.exe --unregister :: supprime le verbe
RechercheDocumentaireSearch.exe --status     :: état d'enregistrement
```

En mode développement (Python non figé) : `python -m recherche_doc.search.explorer_plugin --register`.

### Depuis le MSI (Windows)

```bat
:: Installation avec assistant graphique
RechercheDocumentaire-<version>-win64.msi

:: Installation silencieuse configurée
msiexec /i RechercheDocumentaire-<version>-win64.msi /qn ^
  QUICKCONNECT_ID=monid NAS_LOGIN=user NAS_PASSWORD=secret ^
  NAS_DOCUMENTS_DIR="/volume1/docs/Documents" DRIVE_LETTER=R: ^
  IMAP_URL=imap.example.com MAIL_LOGIN=moi@example.com MAIL_PASSWORD=secret ^
  LAST_RUN=2025-01-01
```

Le MSI installe dans `Program Files\RechercheDocumentaire` : le moteur
(`RechercheDocumentaire.exe`), l'interface de recherche
(`RechercheDocumentaireSearch.exe`), `config.example.yaml`, et crée le
répertoire caché `.docsearch` pour la base SQLite. Des raccourcis menu
Démarrer sont créés.

### Depuis les sources (développement)

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # renseigner NAS / messagerie
```

## 2. Configuration (config.yaml)

```yaml
sync:
  nas_quickconnect_id: "monidquickconnect"   # ID QuickConnect Synology
  nas_login: "utilisateur_nas"
  nas_password: "motdepasse_nas"
  nas_documents_dir: "/volume1/docs/Documents"
  drive_letter: "R:"                          # lettre de drive à monter
  db_dir: null                                # défaut : répertoire caché
  local_root: "./drive_root"                  # racine locale (simu/tests)

mail:
  imap_url: "imap.example.com"
  login: "prenom.nom@example.com"
  password: "motdepasse_messagerie"
  documents_dir: "./drive_root/Documents"
  last_run: null        # date de dernier run ; défaut : 30 jours en arrière
```

Sécurité : le mot de passe peut être passé par variable d'environnement pour
éviter de le stocker en clair (remplacer la valeur par `env:NAS_PASSWORD` et
exporter `NAS_PASSWORD`). **Ne jamais committer `config.yaml`.**

## 3. Utilisation quotidienne

### Principes

- Déposez vos documents dans **`Documents/`** (noms originaux conservés) ;
- le moteur les indexe automatiquement : catégorie + tags + date ;
- retrouvez-les **sans recherche** en naviguant :
  `Categories/<Catégorie>/<Tag>/` (ex. `Categories/Facture/Dupont/`) ;
- ou via l'interface de recherche (filtres + plein texte).

### Commandes

```bash
# Indexer tous les fichiers existants de Documents/
python -m recherche_doc.cli index config.yaml

# Démarrer le moteur de synchro (surveille Documents/ en continu)
python -m recherche_doc.cli watch config.yaml

# Recherche
python -m recherche_doc.cli search config.yaml -c Facture -t Dupont -d 202403
python -m recherche_doc.cli search config.yaml -k facture        # plein texte

# Interface graphique de recherche
python -m recherche_doc.cli gui config.yaml

# Agent courriel : scruter la messagerie et sauvegarder les factures
python -m recherche_doc.cli mail-run config.yaml

# Importer un fichier .eml local (pipeline complet)
python -m recherche_doc.cli import-eml config.yaml message.eml
```

### Interface graphique

1. Sélectionnez une **catégorie** (liste déroulante) ;
2. saisissez des **tags** séparés par des virgules (`Dupont, 202403`) ;
3. éventuellement une **date** `YYYYMM` ;
4. cliquez **Rechercher** (filtres) ou utilisez **Recherche plein texte** ;
5. double-cliquez un résultat pour ouvrir le document (si la racine locale
   est accessible).

### Service Windows (post-MSI)

```bat
RechercheDocumentaire.exe --mode all      :: sync + agent courriel
RechercheDocumentaire.exe --mode sync     :: moteur de synchro seul
RechercheDocumentaire.exe --mode mail     :: agent courriel seul
RechercheDocumentaire.exe --scan-once     :: une scrutation de diagnostic
```

## 4. Catégories et tags reconnus

**Catégories** : Facture, Philosophie, Religion, Photo, Vidéo, Ordonnance,
Résultat, Autre.

**Tags** :

| Tag | Source | Exemple de valeur |
|---|---|---|
| `recipient` | destinataire du document | `Dupont` |
| `emetteur` | émetteur/expéditeur | `CliniqueBarcelonaIvf` |
| `date` | date principale du document | `202403` (`YYYYMM`) |

Nom généré dans les vues :
`<Catégorie><Recipient><Emetteur><YYYYMM>(_N)?.<ext>` —
ex. `FactureDupontCliniqueBarcelonaIvf202403.pdf`, ou
`Facture202403_2.pdf` en cas de doublon.

## 5. Arborescence produite

```
R:/ (ou local_root)
├── Documents/                                  # fichiers physiques
│   ├── Facture_CliniqueBarcelonaIvf_202403.pdf
│   └── resultat_lab.txt
├── Categories/
│   ├── Facture/
│   │   ├── FactureDupontCliniqueBarcelonaIvf202403.pdf   # lien
│   │   ├── Dupont/
│   │   │   └── FactureDupontCliniqueBarcelonaIvf202403.pdf   # lien
│   │   ├── CliniqueBarcelonaIvf/
│   │   │   └── FactureDupontCliniqueBarcelonaIvf202403.pdf   # lien
│   │   └── 202403/
│   │       └── FactureDupontCliniqueBarcelonaIvf202403.pdf   # lien
│   └── Resultat/
│       └── ...
└── .docsearch/                                 # caché
    └── index.db                               # SQLite (catégories, tags, FTS)
```

## 6. Agent courriel de factures

- Scrute la **boîte IMAP** depuis la date de dernier run (persistée dans la
  base après chaque passage) ;
- classifie chaque courriel avec **le même classifieur** que le moteur de
  synchro (cohérence garantie) ;
- les courriels « Facture » sont convertis en **PDF** : le corps conserve
  l'aspect original du courriel, les pièces jointes sont **aplaties** en pages
  supplémentaires du même PDF ;
- le PDF est déposé dans `Documents/` → indexation automatique ;
- `import-eml` reproduit le même pipeline sur un fichier `.eml` local.

## 7. Tests

```bash
python -m unittest discover -s tests   # 15 tests
```

## 8. Dépannage

| Symptôme | Cause probable / action |
|---|---|
| Aucun résultat en recherche | base vide : lancer `index` ; vérifier `db_dir` |
| Liens non créés (copies à la place) | système de fichiers sans symlink (FAT32, privilège manquant) : repli copie automatique |
| Catégorie « Autre » systématique | texte non extractible (scan/image sans OCR) : brancher un OCR dans `extractors.py` |
| Agent courriel ne trouve rien | `last_run` trop ancien/lointain ; vérifier IMAP ; les dossiers autres que INBOX ne sont pas scrutés |
| Drive non monté (Windows) | CfApi requiert le provider (voir `windows_provider.py`) ; sinon utiliser `local_root` |
