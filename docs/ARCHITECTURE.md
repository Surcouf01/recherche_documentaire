# Architecture — Recherche Documentaire

## 1. Objectif

L'outil « Recherche Documentaire » facilite la recherche de documents par
**catégorie** et par **tags**. Un document copié dans le répertoire `Documents`
est automatiquement :

1. **classé** dans une catégorie (CamemBERT) — Facture, Philosophie, Religion,
   Photo, Vidéo, Ordonnance, Résultat, Autre ;
2. **taggé** — destinataire (`recipient`), émetteur (`emetteur`), date
   principale (`YYYYMM`) ;
3. **indexé** dans une base SQLite cachée ;
4. **exposé** dans une arborescence de liens `Categories/<Catégorie>/<Tag>/`
   pointant vers le fichier physique, ce qui permet de retrouver un document
   *nativement dans l'explorateur*, sans interface de recherche ;
5. **interrogeable** via une interface de recherche (combinaisons catégorie +
   tags + mots-clés).

Un **agent IA courriel** complète le dispositif : il scrute la messagerie
personnelle, détecte les factures, les convertit en PDF (aspect original
conservé, pièces jointes aplaties) et les dépose dans `Documents` — déclenchant
ainsi le même pipeline d'indexation.

## 2. Vue d'ensemble des modules

```
recherche_doc/
├── __init__.py          # Taxonomie : catégories, synonymes, règles de tags
├── config.py            # Chargement YAML (sync + mail)
├── classifier.py        # Classification CamemBERT + repli lexical
├── tagger.py            # Extraction des tags, construction des noms
├── extractors.py        # Extraction de texte (PDF, DOCX, images, ...)
├── database.py          # SQLite cachée (files + FTS5 + settings)
├── pipeline.py          # Orchestration : classifier → tagger → DB → liens
├── links.py             # Création des liens (symlink/hardlink/copie)
├── sync_engine.py       # Moteurs de synchro (local + factory Windows)
├── windows_provider.py  # Provider Cloud Sync Engine (CfApi via ctypes)
├── search/explorer_plugin.py  # Plugin explorateur : verbe + registre HKCU
├── app.py               # Point d'entrée service (MSI)
├── cli.py               # CLI : index, watch, search, gui, mail-run, import-eml
├── search/
│   ├── engine.py        # Recherche SQL (filtres) + FTS5 (plein texte)
│   ├── ui.py            # UI Tkinter + squelette plugin explorateur
│   ├── gui_app.py       # Point d'entrée GUI (MSI)
│   └── explorer_hook.py # Entrée du plugin explorateur
└── email_agent/
    ├── eml.py           # Parsing .eml / IMAP (corps, pièces jointes)
    ├── pdf.py           # Courriel → PDF (corps + pièces jointes aplaties)
    └── agent.py         # Agent : scrutation IMAP, classification, import
```

## 3. Choix techniques

| Sujet | Choix | Justification |
|---|---|---|
| Classification | **CamemBERT** (`camembert-base`, fine-tunable) | Exigé par la spécification ; modèle FR de référence. `DocumentClassifier` accepte un modèle fine-tuné `CamembertForSequenceClassification` ; à défaut, repli lexical pondéré par synonymes (déterministe, testable sans GPU) |
| Cohérence sync/courriel | **même classifieur, même taxonomie** partagés | Garantit qu'un courriel classé « Facture » par l'agent le sera aussi par le plugin Cloud Sync Engine (exigence explicite de la spec) |
| Base de données | **SQLite** (+ FTS5) | Libre, embarquée, sans serveur, requête plein texte native. Stockée dans un répertoire **caché** (préfixe `.`) |
| Sync Windows | **Cloud Sync Engine API (CfApi)** via **ctypes** (`windows_provider.py`) | Extension du système de fichiers montée sur une lettre de drive ; enregistrement du sync root (`CfRegisterSyncRoot`), connexion (`CfConnectSyncRoot`), création de placeholders (`CfCreatePlaceholders`), hydratation à la demande (`CfHydratePlaceholder`) ; répertoires virtuels Catégorie/Tag natifs dans l'explorateur. *Statut : implémenté, non testé hors Windows — les appels nécessitent un système de fichiers NTFS et un runner Windows* |
| Plugin explorateur | **Verbe shell** (`search/explorer_plugin.py`) + clé WiX dans le MSI | Commande « Recherche Documentaire... » au menu contextuel des lecteurs (HKCU, sans élévation) ; `%V` passe le dossier visité → pré-filtrage catégorie/tag de la GUI ; enregistré par le MSI et auto-réparé au premier lancement (`--register/--unregister/--status`) |
| Liens | symlink POSIX / hardlink Windows (repli copie) | Point N vers 1 fichier physique ; en mode CfApi, les entrées Catégorie/Tag sont des entrées virtuelles du provider |
| Extraction texte | pypdf, OOXML (zip), EXIF | Multi-format sans dépendances lourdes ; extensible |
| PDF courriels | reportlab + pypdf | Corps rendu en pages PDF (mise en forme d'origine si convertisseur HTML disponible), pièces jointes converties puis **aplaties** en pages supplémentaires |
| GUI | Tkinter | Standard, aucune dépendance ; opère aussi bien standalone que compagnon du drive |
| Packaging | PyInstaller + **WiX v3** (MSI) | Installation per-machine silencieuse, properties MSI mappées sur `config.yaml` |

## 4. Diagramme de séquence — import d'un document

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant SE as SyncEngine (CfApi / Local)
    participant P as IndexingPipeline
    participant C as DocumentClassifier (CamemBERT)
    participant T as Tagger
    participant DB as DocumentDB (SQLite)
    participant L as Links

    U->>SE: Copie du fichier dans Documents/
    SE->>P: process_file(path)
    P->>P: extract_text(fichier)
    P->>C: classify(texte)
    C-->>P: (catégorie, confiance)
    P->>T: extract_tags(texte)
    T-->>P: {recipient, emetteur, date}
    P->>T: build_filename(catégorie, tags, _N)
    T-->>P: "FactureDupontClinique202403.pdf"
    P->>DB: upsert_file(filename, catégorie, tags)
    P->>L: lien Categories/<Cat>/<Nom>
    P->>L: lien Categories/<Cat>/<Tag>/<Nom>  (pour chaque tag)
    L-->>P: ok
    P-->>SE: résumé (catégorie, tags, lien)
    Note over DB: index consultable par l'interface de recherche
```

## 5. Diagramme de séquence — agent courriel

```mermaid
sequenceDiagram
    autonumber
    participant A as EmailInvoiceAgent
    participant IMAP as Messagerie (IMAP SSL)
    participant DB as DocumentDB
    participant C as DocumentClassifier
    participant PDF as EmailToPdf
    participant P as IndexingPipeline

    A->>DB: get_setting("mail_last_run")
    A->>IMAP: search SINCE last_run
    IMAP-->>A: liste de courriels
    loop pour chaque courriel
        A->>A: parse_eml(RFC822)
        A->>C: classify(courriel)
        alt catégorie = Facture
            A->>PDF: email_to_pdf(corps + PJ aplaties)
            PDF-->>A: Facture_*.pdf dans Documents/
            A->>P: process_file(pdf, tags prédéfinis)
            Note over P: même pipeline que la brique sync
        else autre catégorie
            A->>A: ignoré
        end
    end
    A->>DB: set_setting("mail_last_run", maintenant)
```

## 6. Diagramme de classes

```mermaid
classDiagram
    class SyncConfig {
        +nas_quickconnect_id
        +nas_login
        +nas_password
        +nas_documents_dir
        +drive_letter
        +db_dir
        +local_root
        +documents_dir
        +db_path
    }
    class MailConfig {
        +imap_url
        +login
        +password
        +documents_dir
        +last_run
    }
    class DocumentClassifier {
        -model_path
        +classify(text) (catégorie, confiance)
        +classify_batch(texts)
    }
    class Tagger {
        +extract_tags(text, filename, date)
        +build_filename(catégorie, tags, ext, counter)
        +dedupe_filename(base, existing)
    }
    class DocumentDB {
        +path
        +upsert_file(...)
        +get_file(filename)
        +delete_file(filename)
        +list_all()
        +set_setting(k, v)
        +get_setting(k)
    }
    class IndexingPipeline {
        -documents_dir
        -categories_dir
        -db
        -classifier
        +process_file(path, text?, tags_override?)
        +index_existing()
        +remove_file(filename)
    }
    class BaseSyncEngine {
        <<abstract>>
        +on_file_created(path)
    }
    class LocalSyncEngine {
        -_known
        +scan_once() int
        +run()
        +stop()
    }
    class WindowsSyncEngine {
        +start()
    }
    class SearchEngine {
        +search(category?, tags?, query?, date?)
        +search_fulltext(query)
        +list_categories()
    }
    class SearchUI {
        +launch()
    }
    class EmailInvoiceAgent {
        -cfg
        -db
        -pipeline
        -classifier
        +process_eml(path) Optional~str~
        +run() List~str~
    }
    class ParsedEmail {
        +subject
        +from_name
        +from_addr
        +to_addrs
        +date
        +body_text
        +body_html
        +attachments
        +full_text
    }

    IndexingPipeline --> DocumentClassifier : utilise
    IndexingPipeline --> Tagger : utilise (module)
    IndexingPipeline --> DocumentDB : écrit
    IndexingPipeline --> Links : crée liens
    BaseSyncEngine <|-- LocalSyncEngine
    BaseSyncEngine <|-- WindowsSyncEngine
    BaseSyncEngine --> IndexingPipeline : déclenche
    LocalSyncEngine ..> SyncConfig : configuré par
    WindowsSyncEngine ..> SyncConfig : configuré par
    SearchEngine --> DocumentDB : interroge
    SearchUI --> SearchEngine : utilise
    EmailInvoiceAgent --> DocumentClassifier : classifie
    EmailInvoiceAgent --> IndexingPipeline : déclenche
    EmailInvoiceAgent --> MailConfig : configuré par
    EmailInvoiceAgent ..> ParsedEmail : produit
    EmailInvoiceAgent ..> SyncConfig : même racine
```

## 7. Flux de données et invariant

- **Source de vérité** : le fichier physique dans `Documents/` (nom original).
- **Index** : la base SQLite fait foi pour catégorie/tags/date/personnes.
- **Vues** : `Categories/<Catégorie>/[<Tag>/]` ne contiennent que des liens
  vers la source de vérité — jamais de copie de référence (repli copie
  uniquement si le système de fichiers refuse les liens).
- **Nommage** dans les vues : `<Catégorie><Recipient><Emetteur><YYYYMM>(_N)?.<ext>`
  (extension d'origine conservée, compteur d'unicité `_N`).

## 8. Points d'extension

| Extension | Comment |
|---|---|
| Nouvelle catégorie | ajouter à `CATEGORIES` + `CATEGORY_SYNONYMS` (`__init__.py`) ou fine-tuner le modèle et fournir `model_path` |
| Nouveau tag | ajouter une regex à `TAG_RULES`/`tagger.py` puis étendre `build_filename` |
| Nouveau format de fichier | ajouter un extracteur à `extractors.py` |
| Convertisseur HTML→PDF haute fidélité | brancher `_html_to_pdf_bytes` (`email_agent/pdf.py`) sur weasyprint/wkhtmltopdf |
| Autre messagerie (Graph, POP3) | implémenter un `run()` alternatif dans `EmailInvoiceAgent` |
