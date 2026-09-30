# Recherche Documentaire

Outil de référencement documentaire : indexation automatique de documents par
**catégorie** et **tags**, recherche rapide, agent IA de sauvegarde de factures,
et installeur MSI intégré au pipeline GitHub Actions.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — objectifs, choix techniques,
  diagrammes de séquence et de classes, points d'extension
- [Cloud Sync Engine API (CfApi)](docs/CFAPI.md) — concepts, cycle de vie
  du sync root, callbacks, signatures, intégration dans l'outil
- [Guide d'utilisation](docs/USAGE.md) — installation (MSI/sources),
  configuration, commandes, arborescence, dépannage
- [Installeur MSI](installer/README.md) — build local et CI GitHub Actions

Outil de référencement documentaire : indexation automatique de documents par
**catégorie** et **tags**, recherche rapide, et agent IA de sauvegarde de factures
reçues par courriel.

## Briques

1. **Moteur de synchro** (`recherche_doc/sync_engine.py`) — intégration Windows
   *Cloud Sync Engine API* (CfApi) montée sur une lettre de drive (`R:` par
   défaut), connectée au NAS Synology via QuickConnect. Tout fichier copié dans
   le répertoire `Documents` déclenche le pipeline d'indexation. Un moteur de
   simulation locale (`LocalSyncEngine`) permet l'usage/test hors Windows.
2. **Configuration YAML** (`config.example.yaml`) — ID QuickConnect, login,
   mot de passe NAS, répertoire `Documents` mappé, lettre de drive ; pour
   l'agent courriel : URL/login/mot de passe IMAP, répertoire `Documents`
   cible, date de dernier run.
3. **Arborescence de liens** — chaque fichier apparaît dans
   `Categories/<Catégorie>/` et dans `Categories/<Catégorie>/<Tag>/`, sous
   forme de liens vers le fichier physique dans `Documents` (noms originaux
   conservés). Les répertoires catégorie/tag sont en lecture seule pour
   l'utilisateur (création de liens uniquement).
4. **Classification CamemBERT** (`recherche_doc/classifier.py`) — catégories :
   Facture, Philosophie, Religion, Photo, Vidéo, Ordonnance, Résultat, Autre.
   Fournir un modèle fine-tuné (`DOC_CLASSIFIER_MODEL` ou `model_path`) ;
   à défaut, repli lexical pondéré. **Même classifieur** pour l'agent
   courriel et le plugin sync → cohérence garantie.
5. **Interface de recherche** (`recherche_doc/search/`) — par combinaison
   catégorie + tags, par date (`YYYYMM`), et recherche plein texte (SQLite
   FTS5). Fournie en application Tkinter (`gui`) et en squelette de plugin
   de l'explorateur Windows (`ExplorerSearchPane`, déclenché à la visite du
   drive).
6. **Nommage** — nom concaténé dans les répertoires tag :
   `<Catégorie><Recipient><Emetteur><YYYYMM>(_N)?.<ext>` (ex.
   `FactureDupontCliniqueBarcelonaIvf202403.pdf`), avec compteur
   d'unicité `_N`.
7. **Tags** — destinataire (`recipient`), émetteur (`emetteur`), date
   principale (`YYYYMM`, avec compteur `_Counter` si besoin).
8. **Base de données** — SQLite (libre, cachée : répertoire préfixé `.`),
   tables `files` + index FTS5 + `settings` (date de dernier run).
9. **Agent IA courriel** (`recherche_doc/email_agent/`) — scrute la
   messagerie IMAP depuis la date de dernier run, classe les courriels
   (CamemBERT), convertit les factures en PDF (aspect original du courriel
   conservé, pièces jointes aplaties en pages supplémentaires), sauvegarde
   dans `Documents` (déclenche le pipeline d'import). Peut aussi importer
   directement un fichier `.eml` du filesystem.

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

```bash
cp config.example.yaml config.yaml   # puis renseigner NAS / messagerie

# Indexer les fichiers existants de Documents
python -m recherche_doc.cli index config.yaml

# Démarrer le moteur de synchro (surveille Documents)
python -m recherche_doc.cli watch config.yaml

# Recherche console
python -m recherche_doc.cli search config.yaml -c Facture -t Dupont -d 202403
python -m recherche_doc.cli search config.yaml -k facture

# Interface graphique de recherche
python -m recherche_doc.cli gui config.yaml

# Agent courriel : scruter la messagerie (factures -> PDF -> Documents)
python -m recherche_doc.cli mail-run config.yaml

# Import d'un fichier .eml local (pipeline complet)
python -m recherche_doc.cli import-eml config.yaml message.eml
```

## Tests

```bash
python -m unittest discover -s tests
```

## Notes Windows

- `windows_provider.py` : squelette CfApi (cldapi.dll) — enregistrement du
  sync root, hydration des placeholders, déclenchement du pipeline.
- `search/ui.py::ExplorerSearchPane` : enregistrement d'une commande shell
  visible dans l'explorateur sur le drive monté.
