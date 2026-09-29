# 31 — Inbox MTEE : ingestion des captures SoundCloud

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il fait entrer dans MTEE les captures produites par l'extension du [plan 30](30-soundcloud-extension.md) selon le contrat `capture.json` v1 du [cadrage 29](29-soundcloud-cadrage.md). Il commence après la clôture du plan 28, avec au moins une capture réelle disponible et une maquette validée.

**État au 2026-09-29 : reporté par l'utilisateur.** L'extension du plan 30 télécharge seulement dans `Downloads/Songs` ; l'intégration à MTEE sera reprise plus tard. Le dossier de captures prévu ci-dessous devient `Downloads/Songs`, avec les manifestes dans `Songs/_mtee/` (voir le plan 29). Le tri du plan 32 étant abandonné, l'Inbox ne sera plus une étape de tri. À la reprise, réviser ce plan pour une simple ingestion de ce dossier comme racine avec provenance, et consigner cette révision.

## Objectif et résultat observable

Dans Settings, l'utilisateur choisit le dossier `MTEE Inbox` (proposé par défaut sous son dossier Téléchargements). MTEE détecte les nouvelles captures complètes, sans blocage de l'interface, et les montre dans une vue `Inbox` : titre, artiste, voie (`SoundCloud`, `Droploud`, `Hypeddit`, `Bandcamp`), date de capture, format, durée, BPM et Key des tags s'ils existent. Un compteur signale les captures non triées. Les morceaux se jouent comme n'importe quelle liste. `Open source page` ouvre la page SoundCloud d'origine dans le navigateur par défaut.

Une capture illisible (manifeste invalide, schéma inconnu, fichier manquant, taille différente) apparaît comme `Needs attention` avec la raison ; elle n'est ni supprimée ni modifiée.

## Contexte et prérequis

Lire le plan 29, `docs/integrations/soundcloud-capture.md`, `docs/architecture/overview.md`, puis `src/mtee/services/library_scanner.py`, `src/mtee/persistence/library_repository.py`, `src/mtee/persistence/database.py`, `src/mtee/services/jobs.py`, `src/mtee/models/folder_tree_model.py` et `src/mtee/models/workspace_model.py`.

Les couches restent celles de `overview.md` : QML ne lit ni le dossier ni les manifestes ; un service Python le fait dans un travail `JobService`, et le modèle Qt est mis à jour sur le thread graphique. Le dossier Inbox est enregistré comme racine de bibliothèque de type particulier, afin de réutiliser scanner, `track_id`, `SourceRevision`, pochettes et lecture, sans le mélanger à l'arborescence des dossiers de collection.

Les métadonnées du manifeste sont des observations de provenance. Elles ne sont pas écrites dans les tags du fichier. Une commande explicite `Use page title/artist` peut être proposée plus tard par le chemin d'édition existant (plan 05), avec l'enregistrement habituel et l'annulation ; elle n'est pas dans ce plan sauf demande.

## Plan de travail et jalons

### Jalon 31.1 — Maquette

Ajouter à `docs/ux/review-ux-ui-2026-09.md` (ou à un dossier dédié si la revue UX/UI est close) les états : Inbox vide, Inbox avec captures, capture `Needs attention`, compteur dans la barre d'activités ou dans l'Explorer, réglage du dossier dans Settings. Choix à trancher par l'utilisateur : activité dédiée `Inbox` dans la barre d'activités, ou entrée `Inbox` épinglée en tête de l'Explorer. Consigner la décision avant le code QML.

### Jalon 31.2 — Lecture et validation des manifestes

Créer `src/mtee/domain/capture.py` (types purs `CaptureManifest`, `CaptureFile`, `CaptureRoute`, `CaptureProblem`) et `src/mtee/services/capture_inbox.py` :

- lecture d'un dossier de capture : présence de `capture.json`, JSON valide, `schema == "mtee.capture/1"`, identifiant conforme au nom du dossier, fichiers déclarés présents, taille égale à `size_bytes` ;
- refus des noms de fichiers sortant du dossier (`..`, chemins absolus, flux alternatifs NTFS) ;
- ignorance des dossiers sans manifeste et des fichiers `.crdownload` ;
- traitement des archives selon la décision 29.3-7 : si l'extraction est retenue, extraction dans un sous-dossier de la même capture, sans écrasement, avec limites de taille totale et de nombre d'entrées, refus des chemins sortants ; l'archive d'origine est conservée.

Tests : `tests/unit/test_capture_manifest.py` avec fixtures synthétiques dans `tests/fixtures/capture_inbox/` (manifeste valide, champ manquant, schéma inconnu, fichier absent, taille divergente, nom malveillant, archive piégée si l'extraction est retenue).

### Jalon 31.3 — Provenance en base

Ajouter la prochaine migration libre (au moment de la rédaction : `015_capture_inbox.sql`), transactionnelle et précédée de la sauvegarde habituelle :

    capture_sources(
      capture_id TEXT PRIMARY KEY,
      track_id TEXT REFERENCES tracks,      NULL tant que le fichier n'est pas catalogué
      schema TEXT NOT NULL,
      platform TEXT NOT NULL,
      page_url TEXT NOT NULL,
      route_kind TEXT NOT NULL,
      gate_url TEXT,
      track_title TEXT,
      artist_display TEXT,
      captured_at_utc TEXT NOT NULL,
      ingested_at_utc TEXT NOT NULL,
      status TEXT NOT NULL,                 'inbox' | 'needs_attention' | 'triaged' | 'dismissed'
      problem TEXT
    )

Adapter les noms de tables réels du catalogue après lecture de `002_library.sql`. Créer `src/mtee/persistence/capture_repository.py`. L'ingestion est idempotente : un `capture_id` déjà connu n'est pas dupliqué ; un manifeste modifié après ingestion est signalé, pas réappliqué. Une capture dont le fichier a été déplacé hors de MTEE suit les règles de disparition existantes du scanner.

Tests : `tests/integration/test_capture_ingestion.py` sur une base temporaire et une copie de dossier Inbox : ingestion, réingestion, capture incomplète devenue complète, manifeste invalide, base migrée depuis la version 014 sur copie.

### Jalon 31.4 — Détection et vue Inbox

Surveiller le dossier avec `QFileSystemWatcher` et un balayage de secours périodique borné (les notifications Windows peuvent être perdues ou regroupées). Chaque déclenchement soumet un travail d'ingestion annulable ; les déclenchements rapprochés sont regroupés. Les résultats passent au modèle par signal, avec une génération pour ignorer les réponses périmées.

Créer `src/mtee/models/inbox_model.py` (rôles de liste de morceaux plus provenance et statut) et la vue QML retenue au jalon 31.1, en réutilisant `TrackListView.qml` si ses colonnes le permettent. Actions de ce plan : lecture, `Open source page` (via un service Python qui ouvre l'URL `https://soundcloud.com/...` validée, jamais une URL arbitraire du manifeste), `Show in folder` (service existant `shell_reveal`), `Dismiss` (masque la capture de l'Inbox sans toucher au fichier). La mise à la corbeille réutilise le chemin corbeille existant et sa confirmation.

Tests : `tests/ui/test_inbox_view.py` avec pytest-qt et le profil `--demo` enrichi de captures fictives.

### Jalon 31.5 — Recette et distribution

Depuis la racine du dépôt :

    uv sync --locked
    uv run python -m compileall -q src/mtee
    uv run pytest tests/unit/test_capture_manifest.py tests/integration/test_capture_ingestion.py tests/ui/test_inbox_view.py
    uv run python -m mtee --demo --data-dir .local/validation/31-demo --smoke-test
    uv run python -m mtee --data-dir .local/validation/31-live
    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1 -DataDir .local/validation/31-packaged

Parcours manuel : avec l'extension du plan 30, capturer un morceau pendant que MTEE est ouvert, puis un autre pendant qu'il est fermé ; vérifier leur apparition, la lecture, la provenance, `Open source page`, une capture corrompue à la main (sur copie) et le redémarrage. Consigner dans `docs/validation/31-soundcloud-inbox.md`.

## Validation et acceptation

Accepté lorsque les tests ciblés passent, que la migration s'applique sur une copie de base réelle sans perte, que les captures réelles apparaissent sans gel de l'interface, que les captures invalides restent intactes et expliquées, que le paquet Windows passe son smoke test et le parcours manuel.

## Reprise et réexécution

L'ingestion ne modifie jamais les fichiers de l'Inbox ; elle peut être relancée à volonté. Une migration échouée restaure la sauvegarde selon la procédure du socle. Changer de dossier Inbox conserve les provenances déjà ingérées ; les captures de l'ancien dossier restent cataloguées tant que leurs fichiers existent.

## Interfaces et dépendances

`CaptureInboxService.scan(inbox_path, context) -> IngestionReport` ; `CaptureRepository.upsert(manifest, track_id)`, `.pending()`, `.set_status(capture_id, status)`. `InboxModel` expose `count`, `needsAttentionCount` et les actions ci-dessus. Aucune nouvelle dépendance Python n'est prévue ; `json`, `zipfile` et `QFileSystemWatcher` suffisent.

## Preuves et livraison Git

    git status --short
    git diff --check
    git add -- src/mtee/domain/capture.py src/mtee/services/capture_inbox.py src/mtee/persistence/capture_repository.py src/mtee/persistence/migrations/015_capture_inbox.sql src/mtee/models/inbox_model.py src/mtee/qml tests/unit/test_capture_manifest.py tests/integration/test_capture_ingestion.py tests/ui/test_inbox_view.py tests/fixtures/capture_inbox docs/validation/31-soundcloud-inbox.md "Plans d'exécution/31-soundcloud-inbox-mtee.md"
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step31-commit.txt'
    @'
    feat(inbox): ingest SoundCloud captures with provenance

    Changes: <manifest validation, migration, watcher, Inbox view and actions>
    Validation: <tests, migration on copy, real captures, packaged smoke test>
    Limits: <archive handling, watcher fallback interval, open points>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Adapter la liste `git add` aux fichiers QML réellement modifiés. Pousser selon `PLANS.md`.

## Progress

- [x] 2026-09-29 — Plan préparé ; attend 28, 30 et une capture réelle.
- [x] 2026-09-29 — Reporté par l'utilisateur ; à réviser avant reprise.
- [ ] Maquette Inbox validée (31.1).
- [ ] Lecture et validation des manifestes (31.2).
- [ ] Migration et dépôt de provenance (31.3).
- [ ] Surveillance et vue Inbox (31.4).
- [ ] Recette, distribution, rapport, commit et push (31.5).

## Surprises & Discoveries

Non observé à ce stade.

## Decision Log

2026-09-29 — Claude — L'Inbox est une racine de bibliothèque particulière plutôt qu'un mécanisme parallèle. Motif : réutiliser scanner, identités, lecture et pochettes ; le tri devient un déplacement entre racines connues.

2026-09-29 — Claude — Les données de page restent des observations de provenance. Motif : séparation métadonnées écrites / données externes exigée par `AGENTS.md` et appliquée au plan 14.

2026-09-29 — Utilisateur — Reporter l'intégration MTEE ; se limiter pour l'instant au téléchargement par l'extension.

## Outcomes & Retrospective

À compléter après exécution.

Note de révision — 2026-09-29, Claude : création du plan.
