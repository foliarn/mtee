# 03 — Explorateur et métadonnées en lecture seule — livraison A


Ce plan d'exécution est un document vivant à maintenir selon [PLANS.md](../PLANS.md), à la racine du dépôt. Il traduit `PLAN.md`, §2 livraison A, §3 navigation et §4.1. Préparé le 2026-09-10 ; aucune fonctionnalité ni validation ci-dessous n'est déclarée réalisée.

## Objectif et résultat observable


L'utilisateur ajoute un dossier dans MTEE, parcourt ses sous-dossiers et retrouve ses morceaux dans des onglets, éventuellement répartis entre deux panneaux. Les vues Table et Artwork affichent les métadonnées existantes et les pochettes. Fermer puis relancer l'application restaure la navigation et les réglages. Ajouter un dossier ne modifie aucun fichier audio.

La table présente Title, Artist, Genre, BPM et Key par défaut ; Duration, Format et Filename sont activables. L'inspecteur suit la sélection et reste replié lors de la première ouverture. Une collection de 10 000 fichiers doit rester navigable pendant son indexation, même si certaines pochettes manquent ou si un disque devient indisponible.

La lecture sonore appartient au plan 04 et l'écriture des tags au plan 05. Cette livraison termine néanmoins l'affichage des tags demandé dès A : Mutagen est utilisé en lecture seule, sans FFmpeg ni ffprobe. Les composants Convert et Listening view déjà maquettés conservent un état explicite d'indisponibilité des fonctions futures.

## Progress


- [x] (2026-09-10) Plan préparé à partir de `PLAN.md` ; développement et mesures à effectuer.
- [ ] Vérifier les prérequis des plans 01 et 02 et consigner la validation des maquettes.
- [ ] Implémenter l'inventaire asynchrone, les racines et les identifiants persistants.
- [ ] Lire les métadonnées et charger les pochettes à la demande.
- [ ] Relier arborescence, onglets, deux panneaux, Table, Artwork et sélection.
- [ ] Persister et restaurer les réglages de navigation.
- [ ] Exécuter tests, parcours Windows, mesure sur 10 000 fichiers et distribution autonome.
- [ ] Mettre à jour les preuves, créer le commit détaillé et confirmer le push.

## Surprises & Discoveries


Aucun résultat d'exécution à ce stade. Lors du développement, noter ici les particularités découvertes : temps de lecture des tags, sensibilité des chemins Windows, fichiers corrompus, consommation mémoire des pochettes et comportement des disques amovibles. Associer chaque constat à une reproduction ou une mesure, pas à une supposition.

## Decision Log


Les décisions initiales suivantes sont proposées par Codex le 2026-09-10 ; les révisions ultérieures préciseront leur auteur.

- 2026-09-10 — Créer le service `MetadataReader` dès cette étape avec Mutagen, installé au socle. Motif : la livraison A exige leur affichage, même si l'édition n'arrive qu'en B.
- 2026-09-10 — Conserver un UUID `track_id` indépendant du chemin. Motif : les opérations physiques ultérieures doivent maintenir la sélection, la file et les références sans recréer les morceaux.
- 2026-09-10 — Énumérer les fichiers par lots et utiliser des vues virtualisées. Motif : la réactivité doit dépendre du contenu visible et non d'un composant QML permanent pour chacun des 10 000 morceaux.
- 2026-09-10 — Fixer une première cible de réactivité mesurable sur la machine de validation : délai de traitement d'une interaction inférieur à 250 ms au percentile 95 pendant le scan. C'est un budget proposé à mesurer et à ajuster explicitement, pas une performance acquise.

## Outcomes & Retrospective


À compléter après exécution : parcours disponibles, mesures de réactivité et mémoire, couverture des formats réellement lus, anomalies restantes et différences avec les maquettes validées. La livraison A n'est terminée qu'après l'essai de la distribution Windows, pas après les seuls tests des modèles.

## Contexte et prérequis


Le dépôt est actuellement documentaire. Les chemins `src/mtee/...`, `tests/...` et `scripts/...` cités ci-dessous sont des fichiers à créer ou à compléter lors de l'exécution des plans, pas des composants déjà disponibles. Le [plan 01](01-socle-technique.md) doit auparavant fournir Python 3.12, uv, PySide6, Mutagen, SQLite, `JobService`, le démarrage `python -m mtee`, le thème et le packaging Windows. Le [plan 02](02-maquettes-ux.md) doit avoir obtenu et consigné la validation distincte des maquettes requise par `PLAN.md` §3.

Le socle place les données utilisateur via `QStandardPaths` ; `--data-dir` permet une base isolée et `--demo` présente des données fictives sans accès aux fichiers utilisateur. `--smoke-test` quitte après la disponibilité de la fenêtre. Pour ce plan, les données de validation vont dans `.local/validation/03`, et les sources d'essai dans `.local/fixtures/03` ; ces chemins sont ignorés par Git.

Un `track_id` est un UUID créé une fois dans SQLite. Une `SourceRevision` immuable contient `size_bytes`, `mtime_ns`, `file_id` facultatif et `generation` persistée. Cette révision détecte les changements ordinaires ; elle n'est ni une identité ni une preuve cryptographique du contenu. Une racine indisponible conserve ses enregistrements avec un état indisponible. Un déplacement extérieur ambigu ne doit pas être attribué silencieusement à un autre morceau.

L'interface demeure en anglais, à 1440 × 900 comme base et avec les couleurs, Geist Sans embarquée, dimensions et états de focus de `PLAN.md` §3. QML ne fait aucun accès au système de fichiers : il utilise des modèles Qt et demande des opérations aux services Python.

## Plan de travail et jalons


### Jalon 1 — Inventaire et lecture des fichiers


Créer `src/mtee/services/library_scanner.py` pour parcourir uniquement les racines choisies. Une extension reconnue constitue une candidature ; Mutagen confirme ce qu'il peut lire. Un fichier non reconnu ou endommagé garde un statut explicite et n'est pas présenté comme correctement analysé. Les dossiers, points de jonction et liens symboliques demandent une politique explicite : ne pas suivre les liens de répertoire dans ce premier parcours, afin d'éviter cycles et sorties imprévues de la racine.

Créer `src/mtee/persistence/library_repository.py`, contenant `TrackRepository`, et ajouter une migration pour racines, emplacements et disponibilité après sauvegarde SQLite cohérente. Dédupliquer une même racine et un même emplacement selon les règles de chemins Windows, tout en conservant la casse originale pour l'affichage. L'ouverture d'une racine parent puis d'un enfant ne doit pas produire deux UUID pour le même emplacement connu. Ne pas regrouper automatiquement des fichiers distincts qui partagent taille et date.

Le scan et les lectures Mutagen passent par `JobService`, avec identifiant de requête, annulation coopérative et résultats par lots bornés. Une navigation plus récente invalide les résultats tardifs de l'ancienne requête. Les insertions de lignes et signaux des modèles Qt reviennent sur le thread de l'interface ; aucun worker ne modifie un modèle QML directement.

### Jalon 2 — Métadonnées et pochettes


Créer `src/mtee/services/metadata_reader.py` pour rendre `MetadataSnapshot` et `TechnicalInfo`, définis dans `src/mtee/domain/metadata.py`. Conserver distincts titre, artiste, album, genre, BPM, tonalité, durée interne en microsecondes, conteneur et codec connu. Une valeur manquante reste absente ; le Filename peut servir de libellé de secours sans être enregistré comme titre. Les résultats calculés, encore inexistants à ce stade, ne remplacent pas les tags source.

Créer `src/mtee/services/artwork_service.py` et `src/mtee/models/artwork_provider.py` : extraction sur demande, redimensionnement hors thread UI et cache de vignettes borné indexé par `track_id`, `SourceRevision` et taille demandée. Proposer 128 Mio de cache mémoire et consigner la valeur effectivement retenue. Rejeter proprement une image indécodable ou excessivement grande avant de l'afficher. Employer l'illustration neutre validée ; aucune recherche de pochette sur Internet.

Les fichiers dont les tags ont plusieurs valeurs conservent cette information dans le snapshot. L'affichage de Genre, BPM et Key utilise une correspondance par famille de format documentée dans `docs/metadata-mapping.md`. Le futur écrivain du plan 05 réutilisera cette correspondance ; cette étape n'appelle jamais `save()` sur un objet Mutagen.

### Jalon 3 — Navigation complète


Créer `src/mtee/models/folder_tree_model.py`, `track_list_model.py` et `workspace_model.py`, puis brancher les composants du plan 02 : `src/mtee/qml/components/ExplorerPane.qml`, `TabGroup.qml`, `TrackTable.qml`, `ArtworkGrid.qml`, `MetadataInspector.qml` et `src/mtee/qml/views/BrowserView.qml`. Une liste visible se fonde sur des rôles Qt stables comprenant au minimum UUID, libellés, disponibilité et référence de pochette. Utiliser TableView et GridView avec réutilisation de délégués, et un modèle d'arbre chargé à la demande.

Un clic sélectionne ; Ctrl et Shift étendent la sélection ; l'inspecteur suit le panneau actif. Conserver `selected_track_ids` séparé d'un futur `playing_track_id`. Un double-clic peut émettre `activationRequested(track_id, ordered_track_ids)` ; avant le plan 04, indiquer explicitement que le lecteur n'est pas disponible. La liste ordonnée transmise est un instantané, destiné à empêcher une reconstruction silencieuse de la file lors d'un tri ultérieur.

Les onglets retiennent dossier, mode Table/Artwork et sélection. Deux groupes au maximum coexistent. L'action de division et le changement de panneau actif sont accessibles au clavier. Réduire la fenêtre replie les panneaux et montre un groupe sans supprimer les onglets masqués. Le retour à une largeur suffisante restaure leur état.

La recherche de cette étape filtre les libellés affichés du dossier courant ; elle ne prétend pas fournir la recherche combinée du plan 10. Rendre les colonnes triables, redimensionnables et réordonnables, avec un tri déterministe pour les valeurs égales et manquantes. Les pochettes restent une image par fichier, sans regroupement par album.

### Jalon 4 — Session persistante et livraison A


Créer `src/mtee/persistence/workspace_repository.py` et sa migration versionnée pour racines, onglets, disposition, ordre et largeur des colonnes, panneau actif et mode de vue. Sauvegarder sans bloquer l'interface ; une session invalide revient à une disposition sûre avec message diagnostique. Restaurer les chemins absents comme indisponibles et permettre leur réouverture après reconnexion.

Créer les tests ci-dessous et une fixture générant 10 000 petits WAV valides via la bibliothèque standard Python. Ce corpus vérifie l'échelle et la navigation ; ajouter un petit corpus réel avec tags et pochettes pour vérifier les lecteurs Mutagen. Enregistrer provenance et droits des échantillons dans `tests/fixtures/audio/manifest.json`, sans incorporer de musique personnelle au dépôt.

## Étapes concrètes


Depuis la racine `C:\Users\flori\Desktop\dev\MTEE`, vérifier les prérequis et lancer l'environnement existant :

    uv sync --locked
    uv run python -m mtee --demo --data-dir .local/validation/03-demo --smoke-test

Après chaque jalon, créer les tests correspondants : `tests/unit/test_library_scanner.py`, `test_metadata_reader.py`, `test_workspace_model.py`, `tests/integration/test_library_repository.py`, `test_scan_recovery.py` et `tests/ui/test_browser_navigation.py`. Les tests utilisent des répertoires temporaires et une base isolée. Ajouter `scripts/create_browser_fixture.py` avec `--output` et `--count`, qui refuse un dossier de sortie déjà non vide.

    uv run python scripts/create_browser_fixture.py --output .local/fixtures/03 --count 10000
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_library_scanner.py tests/unit/test_metadata_reader.py tests/unit/test_workspace_model.py tests/integration/test_library_repository.py tests/integration/test_scan_recovery.py tests/ui/test_browser_navigation.py
    uv run python -m mtee --data-dir .local/validation/03

Dans l'application réelle, ajouter `.local/fixtures/03` avec Add folder. Enregistrer les mesures dans `docs/validation/03-explorateur.md`, puis construire et ouvrir la distribution :

    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/03-package

## Validation et acceptation


Les tests d'inventaire couvrent chemins accentués, racines imbriquées, doublons de racine, dossiers vides, liens en cycle, accès refusé, annulation et fichiers corrompus. Les tests de repository démontrent qu'un rescan conserve les UUID, qu'une déconnexion ne purge pas les références et qu'une restauration de session retrouve l'ordre des colonnes.

Les tests UI démontrent qu'une sélection ne déclenche aucune opération sur le fichier, qu'un changement de panneau n'efface pas l'autre sélection et que Table/Artwork présentent les mêmes UUID. Un double-clic émet l'ordre visible sans conserver de dépendance au tri mutable. Capturer Browser, inspecteur ouvert, deux panneaux, sélection multiple, pochette absente et fenêtre étroite ; comparer aux maquettes validées.

Mesurer le délai d'interaction durant le scan de 10 000 WAV, le délai jusqu'aux premières lignes, la durée totale du scan, le pic mémoire et la croissance mémoire après trois allers-retours Table/Artwork. Consigner CPU, RAM, disque et version Windows ; ne pas confondre 10 000 lignes synthétiques en mémoire avec 10 000 fichiers réellement énumérés. La cible de 250 ms au percentile 95 doit être évaluée, et tout écart expliqué avant de déclarer la livraison terminée.

Déconnecter uniquement un support d'essai ou injecter l'erreur dans un adaptateur ; ne pas manipuler un disque contenant le travail utilisateur. Réconnecter et rescanner sans perte de réglages. Comparer les empreintes des petits fichiers audio de test avant et après tous les parcours : elles doivent être identiques, puisque cette étape ne doit rien écrire dans les sources.

Valider la distribution sur Windows sans Python installé ni accès au réseau. Ouvrir l'explorateur, ajouter le corpus autorisé, voir tags et pochettes, fermer puis rouvrir. Une validation manuelle non effectuée doit rester marquée non effectuée dans les preuves.

## Reprise et réexécution


Un scan interrompu reprend par nouvel inventaire des racines ; les enregistrements déjà présents sont mis à jour sans dupliquer les UUID. Marquer un scan complet seulement après son dernier lot afin de ne pas déclarer absents les fichiers d'une racine dont le scan a échoué. Les caches peuvent être recalculés ; les chemins et préférences doivent rester persistants.

Réutiliser `--data-dir` pour tester les migrations, puis choisir un nouveau répertoire pour comparer à une installation propre. Ne pas effacer la base utilisateur pour résoudre un test. Le générateur de fixtures refuse d'écraser son dossier ; créer un autre dossier de validation si nécessaire. Un échec d'accès laisse la racine visible avec une action de réessai.

## Interfaces et dépendances


`LibraryScanner.scan(root_id, request_id, cancel_token)` produit des lots `ScanEntry(path, revision, status)` et un résultat final distinguant succès, annulation et erreur. `TrackRepository.upsert_location(...)` rend un UUID connu pour un emplacement connu ; `mark_root_unavailable(...)` ne supprime aucune piste. Aligner les noms exacts sur le socle et consigner tout changement de contrat.

`MetadataReader.read(path, revision)` rend un snapshot immuable, des caractéristiques techniques et les capacités connues par format. `ArtworkService.request(track_id, revision, size)` renvoie un résultat asynchrone associé à la même révision. Un résultat périmé ne doit pas remplacer les données d'une source plus récente.

`WorkspaceModel` expose onglets, groupes, sélection active et `activationRequested(track_id, ordered_track_ids)`. `JobService` conserve les états du socle `queued`, `running`, `succeeded`, `failed`, `cancelled` ; une interruption non volontaire utilise `failed` avec code `interrupted`. SQLite est le seul stockage durable applicatif de cette étape ; les lectures audio et images restent hors thread UI. Aucune dépendance ffprobe, FFmpeg, analyse ou réseau n'est ajoutée.

## Preuves et livraison Git


Mettre à jour Progress, Outcomes & Retrospective et `docs/validation/03-explorateur.md` avec commandes, résultats réels, mesures et limites. Documenter les formats effectivement lus et les captures pertinentes. Les fichiers audio de validation privés, `.local`, caches et `dist` ne sont pas suivis. Cette étape est committée après ces mises à jour ; un résultat de push ou son hash ne doit pas être inventé dans le commit qui le précède.

Vérifier que le dépôt utilise `origin` vers `https://github.com/foliarn/mtee.git` et la branche `main`, selon le plan 00. Ajouter uniquement les chemins réellement modifiés par cette étape, après revue ; adapter la liste si le socle leur a donné d'autres noms.

    git status --short
    git diff --check
    git add -- src/mtee/domain/metadata.py src/mtee/services/library_scanner.py src/mtee/services/metadata_reader.py src/mtee/services/artwork_service.py src/mtee/models/artwork_provider.py src/mtee/models/folder_tree_model.py src/mtee/models/track_list_model.py src/mtee/models/workspace_model.py src/mtee/persistence/library_repository.py src/mtee/persistence/workspace_repository.py src/mtee/qml/components/ExplorerPane.qml src/mtee/qml/components/TabGroup.qml src/mtee/qml/components/TrackTable.qml src/mtee/qml/components/ArtworkGrid.qml src/mtee/qml/components/MetadataInspector.qml src/mtee/qml/views/BrowserView.qml tests/unit/test_library_scanner.py tests/unit/test_metadata_reader.py tests/unit/test_workspace_model.py tests/integration/test_library_repository.py tests/integration/test_scan_recovery.py tests/ui/test_browser_navigation.py tests/fixtures/audio/manifest.json scripts/create_browser_fixture.py docs/metadata-mapping.md docs/validation/03-explorateur.md "Plans d'exécution/03-explorateur.md"
    git diff --cached --check
    git diff --cached

Ajouter séparément les migrations et le raccordement dans `src/mtee/app.py`. Si un fichier partagé contient des changements étrangers à l'étape, effectuer un staging ciblé par morceaux avant de poursuivre. Construire le message avec une here-string PowerShell non interpolée et adapter les validations à ce qui a effectivement réussi :

    $mteeCommitMessage = @'
    feat(explorer): add persistent folder browsing and read-only metadata

    Changes: asynchronous library scans, stable track references, lazy artwork,
    Table and Artwork views, two tab groups and restored workspace preferences.
    Validation: record exact automated checks, 10000-file measurements and
    Windows package walkthrough in docs/validation/03-explorateur.md.
    Limits: metadata remains read-only; playback and conversion follow later.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-03-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Les deux révisions doivent concorder après le fetch. En cas de divergence ou de refus du push, inspecter les commits distants et suivre la reprise du plan 00, sans push forcé. Rapporter séparément le hash vérifié et le résultat du push ; ne cocher la livraison Git qu'après cette vérification.

Note de révision — 2026-09-10, Codex : création du plan et alignement avec les composants QML du plan 02 ; lecture Mutagen créée dès A, identité stable et mesures de réactivité explicitement prévues.
