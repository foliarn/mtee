# 05 — Édition manuelle des métadonnées — livraison B, partie 2


Ce plan vivant applique [PLANS.md](../PLANS.md) et `PLAN.md`, §3 « Sélection, lecture et édition » et §4.3. Il complète la livraison B après le lecteur. Préparé le 2026-09-10 ; aucune écriture audio, validation ou publication n'est déclarée effectuée.

## Objectif et résultat observable


L'utilisateur corrige Title, Artist, Album, Genre, Date, Comment, Track number, BPM et Key dans l'inspecteur ou Fullscreen player. Valider un champ ou quitter son focus enregistre ce champ. L'interface montre Saving, puis Saved uniquement après vérification ; une erreur montre Could not save et conserve la saisie. Une action Undo restaure la valeur antérieure lorsque la source n'a pas changé depuis l'opération concernée.

Une sélection multiple expose Mixed values pour les champs divergents. Une modification explicite applique seulement ce champ aux UUID de la sélection capturée au début de l'édition. Les propriétés techniques restent en lecture seule ; les formats et champs qui ne peuvent pas être écrits sans perte restent désactivés avec une explication.

Les tags inconnus, les pochettes et les champs non modifiés sont conservés. Les tags source restent distincts des résultats d'analyse futurs et des corrections de ces résultats. Aucun FFmpeg ni ffprobe n'est ajouté dans cette livraison B.

## Progress


- [x] (2026-09-10) Plan préparé ; développement et tests d'écriture restent à réaliser.
- [ ] Vérifier les contrats des plans 01, 03 et 04 et préparer les copies de test.
- [ ] Établir la matrice de champs et capacités d'écriture par format.
- [ ] Implémenter le journal, les écritures sérialisées, la vérification et les conflits.
- [ ] Relier autosauvegarde, sélection multiple et Undo aux deux vues.
- [ ] Tester pertes évitées, verrouillages, pannes, redémarrage et distribution Windows.
- [ ] Actualiser les preuves et journaux, créer le commit puis vérifier son push.

## Surprises & Discoveries


Aucun comportement observé à ce stade. Ajouter ici les changements de version ID3 imposés par la bibliothèque, limites des atomes MP4, différences entre commentaires multiples, permissions Windows et comportement de libmpv lorsqu'un fichier est ouvert. Chaque constat doit citer le format, la version Mutagen et une reproduction sur fixture autorisée.

## Decision Log


Les décisions initiales suivantes sont proposées par Codex le 2026-09-10 ; les révisions ultérieures préciseront leur auteur.

- 2026-09-10 — Réutiliser Mutagen déjà installé en lecture seule depuis A et ajouter des adaptateurs d'écriture explicites. Motif : l'affichage et la sauvegarde doivent partager la même interprétation des champs.
- 2026-09-10 — Écrire d'abord une copie temporaire voisine, la relire, puis remplacer la source avec un adaptateur Windows et un journal de reprise. Motif : un échec Mutagen ne doit pas laisser la seule copie source partiellement modifiée.
- 2026-09-10 — Autoriser des résultats individuels pour une sélection multiple. Motif : plusieurs fichiers ne forment pas une transaction atomique ; l'interface doit indiquer précisément les réussites et les erreurs.
- 2026-09-10 — Traiter Undo comme une nouvelle écriture vérifiée, soumise au contrôle de révision. Motif : annuler ne doit pas écraser une modification extérieure plus récente.
- 2026-09-10 — Désactiver provisoirement une écriture dont la conservation des données annexes n'est pas démontrée, en consignant le cas dans la matrice. Motif : une capacité doit être prouvée par format et version, pas déduite du seul fait que Mutagen ouvre le fichier.

## Outcomes & Retrospective


À compléter après exécution avec la matrice réellement disponible, les opérations vérifiées après redémarrage, les scénarios de reprise démontrés et les restrictions restantes. Un champ désactivé pour préserver des données doit être indiqué comme non pris en charge, jamais comme une édition réussie.

## Contexte et prérequis


Le contexte initial du dépôt est documentaire. Les fichiers mentionnés sont des livrables futurs. Les [plans 01](01-socle-technique.md), [03](03-explorateur.md) et [04](04-lecteur.md) doivent fournir Python 3.12, uv, SQLite, Mutagen, les modèles Qt, l'explorateur, le lecteur commun, `MetadataReader` et `FileAccessCoordinator` dans `services/file_access.py`. Avant cette implémentation, les maquettes doivent avoir été validées au [plan 02](02-maquettes-ux.md) ; leurs états Saving, Saved, Could not save et Mixed values guident ce travail.

`track_id` est un UUID durable ; le repository résout son emplacement au moment de l'opération. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` représente l'observation du fichier, avec génération persistée augmentée après mutation MTEE. Pour les écritures critiques, compléter ce contrôle par SHA-256 calculé en flux ; taille et date ne garantissent pas seules un contenu identique.

`FileAccessCoordinator` arbitre un accès exclusif par UUID contre lecture native, autres éditions et futurs jobs. L'inspecteur suit les UUID sélectionnés ; Fullscreen player suit `playing_track_id`. L'état d'un brouillon conserve ses UUID cibles même si la sélection ou le morceau joué change avant la fin de la sauvegarde.

Les tests travaillent sur des copies sous `.local/fixtures/05` ou dans les répertoires temporaires de pytest. La base de recette utilise `--data-dir .local/validation/05`, distincte des données utilisateur dans `QStandardPaths`. `--demo` ne permet pas de valider une écriture réelle. Les migrations SQLite utilisent la sauvegarde cohérente et les transactions du socle.

Relire la [documentation Mutagen](https://mutagen.readthedocs.io/en/latest/index.html), son [API MP4](https://mutagen.readthedocs.io/en/latest/api/mp4.html) et la documentation des familles effectivement retenues lors de l'implémentation. Le remplacement Windows doit respecter les attributs et les échecs décrits par [ReplaceFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew) ; ne pas ignorer des erreurs de fusion de permissions.

## Plan de travail et jalons


### Jalon 1 — Correspondance et capacités


Créer `src/mtee/domain/metadata_edit.py`, `src/mtee/services/metadata_adapters/` et compléter `docs/metadata-mapping.md`. Pour chaque famille, documenter valeur affichée, clé native, type, valeurs multiples, valeur absente, suppression explicite, capacité de lecture et d'écriture. Conserver les données natives nécessaires à une écriture limitée au champ demandé ; ne pas reconstruire tous les tags à partir des seuls champs visibles.

La matrice initiale à confirmer sur fixtures comprend ID3 pour MP3, WAV et AIFF : TIT2, TPE1, TALB, TCON, TDRC, COMM, TRCK, TBPM et TKEY. Pour FLAC, Ogg/Vorbis et Opus, utiliser les commentaires TITLE, ARTIST, ALBUM, GENRE, DATE, COMMENT, TRACKNUMBER, BPM et INITIALKEY. Lire une variante telle que KEY sans la supprimer automatiquement ; des alias contradictoires doivent être signalés ou leur règle rendue explicite.

Pour MP4 contenant AAC ou ALAC, vérifier `©nam`, `©ART`, `©alb`, `©gen`, `©day`, `©cmt`, `trkn` et `tmpo`. Le BPM entier de MP4 ne doit pas arrondir silencieusement une valeur décimale. L'écriture de Key via un atome libre tel que `----:com.apple.iTunes:initialkey` reste désactivée jusqu'à démonstration d'un aller-retour fiable ; préciser alors son caractère conventionnel et non universel. AAC brut reste en lecture seule tant qu'aucune écriture fiable de ses tags n'est démontrée.

Préserver le total de pistes lorsque seul le numéro est changé. Garder le texte original des tonalités sans imposer une notation musicale ; la date accepte les formes partielles documentées sans convertir silencieusement une valeur non reconnue. Une valeur vide ne signifie suppression qu'après modification explicite. Les champs multiples montrent leur contenu ; remplacer leur valeur est une action du champ ciblé, jamais un nettoyage général du fichier.

Pour ID3, conserver la version existante lorsque l'adaptateur sait le faire sans perdre de frames ; tester v2.3 et v2.4 séparément. Préserver tous les commentaires de langues ou descriptions différentes et modifier seulement le slot affiché. Si le slot est ambigu, rendre le choix explicite ou le champ non éditable. Une nouvelle date ne doit pas effacer les autres dates non concernées.

### Jalon 2 — Écriture protégée et historique


Créer `src/mtee/services/metadata_writer.py`, contenant `MetadataEditService` qui orchestre les adaptateurs d'écriture, `src/mtee/services/file_replacement.py` et `src/mtee/persistence/metadata_history_repository.py`, avec migration pour opérations, anciennes/nouvelles valeurs, révisions, statut et chemins des fichiers temporaires propres à l'opération. L'historique enregistre les valeurs modifiées ; il ne stocke pas une copie opaque de toute la collection.

Pour une requête, capturer UUID, patch de champs explicitement modifiés, révision attendue et identifiant de brouillon. Obtenir le verrou exclusif, résoudre à nouveau le chemin, vérifier disponibilité, révision et empreinte attendue. Si une autre application a changé le fichier, suspendre l'opération avec Conflict et proposer Reload ; conserver le brouillon jusqu'au choix de l'utilisateur, sans réessai automatique qui écraserait le nouveau contenu.

Créer un temporaire unique dans le dossier source, en conservant un suffixe utilisable par l'adaptateur et en refusant tout écrasement. Copier la source, appliquer seulement le patch via Mutagen, fermer puis relire le temporaire. Vérifier les valeurs demandées, les tags non ciblés et les octets des pochettes. Les normalisations de représentation autorisées doivent être limitées, testées et documentées ; une différence inconnue interrompt la publication.

Réexaminer la source juste avant publication, puis utiliser l'adaptateur Windows de remplacement avec sauvegarde de récupération et conservation des attributs pris en charge. Le remplacement modifie l'identité physique éventuelle du fichier sans modifier son UUID applicatif. Des liens multiples ou un système de fichiers dont les garanties ne sont pas connues rendent l'opération indisponible jusqu'à test, avec explication ; ne pas basculer vers une écriture directe plus risquée.

Après publication, relire le chemin final, contrôler les valeurs et enregistrer la nouvelle `SourceRevision` avec génération augmentée, le snapshot et l'historique en transaction SQLite. Saved exige cette vérification et la persistance de l'opération. Une erreur après remplacement mais avant mise à jour SQLite reste un état de reprise identifié, avec relecture ; ne pas prétendre que le fichier est resté inchangé.

### Jalon 3 — Autosauvegarde et sélection multiple


Créer `src/mtee/models/metadata_editor_model.py`, compléter `src/mtee/qml/components/InfoPanel.qml` et `src/mtee/qml/views/FullscreenPlayer.qml` des plans précédents, puis compléter `src/mtee/qml/components/FieldEditor.qml`. Chaque champ possède valeur lue, brouillon, numéro de version, capacité et état d'enregistrement. Entrée et perte de focus déclenchent une seule requête par version ; chaque frappe ne déclenche aucune écriture.

Une sauvegarde lente n'empêche pas une nouvelle saisie : conserver la dernière version de brouillon et sérialiser les intentions par UUID. Un retour ancien ne remet pas Saved sur une valeur plus récente non enregistrée. Un changement de sélection valide le champ en cours contre ses anciennes cibles avant d'afficher les nouvelles ; il ne redirige pas la requête vers la nouvelle sélection.

Mixed values est un état de présentation, jamais un texte envoyé au writer. Un patch multisélection ne contient que les champs explicitement changés. L'interface affiche nombre de fichiers réussis, ignorés car incapables et en erreur ; les erreurs gardent leur brouillon et Retry ne rejoue que les opérations concernées. Ne pas annoncer un succès global si un fichier a échoué.

Si le fichier est joué et ne peut pas être muté, afficher Busy et conserver la saisie. Une action explicite Stop playback and save peut demander au lecteur de libérer le handle, puis recommencer le contrôle de révision. Le service d'écriture n'arrête jamais le lecteur sans cette action. Le lecteur met ensuite à jour les métadonnées visibles via le snapshot validé.

### Jalon 4 — Undo et reprise après interruption


Ajouter `MetadataEditService.undo(operation_id)`. Reprendre les anciennes valeurs des seuls champs concernés et vérifier que l'état actuel correspond encore à celui laissé par l'opération. Appliquer une nouvelle écriture contrôlée puis enregistrer le lien avec l'opération annulée. Pour une sélection multiple, présenter les résultats par fichier ; une annulation partielle reste explicite.

Au démarrage, inspecter les opérations non terminées du journal. Distinguer temporaire non publié, remplacement effectué et DB non confirmée, ainsi que sauvegarde de récupération conservée. Relire les fichiers et leurs empreintes avant de proposer une reprise. Une restauration ne remplace jamais une modification extérieure récente et ne nettoie que des chemins appartenant à l'opération vérifiée.

## Étapes concrètes


Depuis la racine du dépôt, vérifier l'environnement puis créer les adaptateurs et leurs tests avant d'activer les champs QML :

    uv sync --locked

Créer `tests/unit/test_metadata_mapping.py`, `test_metadata_edit_service.py`, `tests/integration/test_metadata_roundtrip.py`, `test_metadata_recovery.py` et `tests/ui/test_metadata_editor.py`. Étendre le manifeste des fixtures avec tags inconnus, plusieurs commentaires et pochettes ; les tests copient ces originaux avant toute mutation. Prévoir des points d'injection d'échec après chaque changement de phase du journal.

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_metadata_mapping.py tests/unit/test_metadata_edit_service.py tests/integration/test_metadata_roundtrip.py tests/integration/test_metadata_recovery.py tests/ui/test_metadata_editor.py
    uv run python -m mtee --data-dir .local/validation/05

Dans l'application, ajouter uniquement des copies du corpus, corriger un champ puis plusieurs sélections, quitter et rouvrir avec le même `--data-dir`. Documenter les résultats avant la recette du paquet :

    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/05-package

## Validation et acceptation


La matrice de `docs/validation/05-metadonnees.md` donne, pour chaque famille et champ, lecture initiale, modification, suppression explicite, relecture après redémarrage et Undo. Les tags inconnus, les autres commentaires, les pochettes et les champs non ciblés doivent conserver leur contenu. Ajouter un contrôle de décodage sur les copies modifiées avec le lecteur du plan 04 pour détecter un fichier rendu illisible.

Les tests UI vérifient qu'une frappe seule ne déclenche pas d'écriture, qu'Entrée suivie de perte de focus n'écrit pas deux fois, que Mixed values n'est jamais enregistré, et qu'un retour asynchrone ancien ne valide pas le nouveau brouillon. Tester modification d'un champ d'une sélection mixte sans changement des autres champs, puis transition de sélection pendant Saving.

Injecter fichier verrouillé, attribut lecture seule, permission insuffisante, disque absent, manque d'espace, erreur Mutagen et conflit extérieur entre lecture et validation. Could not save conserve la saisie, sans faux Saved ; la source originale reste récupérable. Tester aussi panne après remplacement et avant commit SQLite : la reprise doit décrire l'état réel et éviter une seconde écriture aveugle.

Tester Undo immédiatement, après redémarrage et après modification extérieure. Les deux premiers cas restaurent les anciennes valeurs si la révision attendue demeure valable ; le troisième suspend l'annulation et garde le fichier extérieur intact. Sur le morceau joué, vérifier Busy puis l'action explicite d'arrêt et sauvegarde.

Exécuter le même parcours principal dans la distribution Windows sans Python préinstallé et hors réseau. Les essais Windows sur permissions et remplacement natif doivent être réellement exécutés ; des mocks ne suffisent pas à cocher cette preuve. Ne pas déclarer la livraison B terminée tant que les limitations d'écriture ne sont pas lisibles dans l'interface et le rapport.

## Reprise et réexécution


Chaque requête possède un identifiant d'opération idempotent. Si son résultat s'est perdu, consulter son journal et relire le fichier au lieu de lancer une nouvelle sauvegarde. Une réexécution de test repart d'une copie fraîche ; elle ne mutile pas progressivement le corpus de référence.

Conserver les fichiers temporaires et sauvegardes dont l'état est incertain. Les nettoyer seulement après vérification de l'appartenance à l'opération et confirmation de la source finale. Ne jamais supprimer récursivement un dossier source pour résoudre un test. Une base de recette neuve complète les tests de migration et de reprise sur la base existante ; elle ne les remplace pas.

## Interfaces et dépendances


`MetadataPatch` distingue champs inchangés, valeur explicite et suppression explicite. `MetadataCapabilities` décrit chaque champ pour le format et la version de tags observés. `MetadataEditService.submit(track_ids, patch, expected_revisions, draft_id)` renvoie des résultats par UUID : Saved, Conflict, Busy, Unsupported ou Failed, avec révision et snapshot confirmés quand disponibles.

`MetadataAdapter.read`, `capabilities`, `apply_patch` et `verify_preserved_data` isolent chaque famille native. `FileReplacement.publish(temp_path, destination, backup_path)` fournit un résultat décrivant les chemins effectivement présents, y compris en échec. `MetadataHistoryRepository` persiste les phases de l'opération et les valeurs avant/après ; `undo` réutilise le même chemin de sauvegarde.

`FileAccessCoordinator` et `JobService` sérialisent les opérations par UUID hors thread UI. Les états de jobs restent `queued`, `running`, `succeeded`, `failed`, `cancelled` ; les statuts métier de sauvegarde décrivent une opération distincte, et un travail interrompu utilise `failed` avec code `interrupted`. Les modèles reçoivent `MetadataChanged(track_id, snapshot, revision)` uniquement après confirmation. Les analyses futures écouteront `SourceChanged` pour invalider leurs caches sans écraser les valeurs manuelles. Mutagen reste la bibliothèque de tags ; aucune dépendance d'analyse ou de conversion n'est nécessaire.

## Preuves et livraison Git


Avant le commit, actualiser Progress, les décisions, Outcomes & Retrospective, la matrice des tags et `docs/validation/05-metadonnees.md`. Indiquer commandes, résultats observés, versions, cas non exécutés et captures des états importants. Les fichiers source personnels, copies mutées, sauvegardes et bases locales restent hors Git.

Sur `main` et avec `origin` vérifié vers `https://github.com/foliarn/mtee.git`, examiner puis indexer seulement les changements de cette étape ; adapter les chemins si le socle a organisé autrement ses composants.

    git status --short
    git diff --check
    git add -- src/mtee/domain/metadata_edit.py src/mtee/services/metadata_adapters src/mtee/services/metadata_writer.py src/mtee/services/file_replacement.py src/mtee/persistence/metadata_history_repository.py src/mtee/models/metadata_editor_model.py src/mtee/qml/components/InfoPanel.qml src/mtee/qml/components/FieldEditor.qml src/mtee/qml/views/FullscreenPlayer.qml tests/unit/test_metadata_mapping.py tests/unit/test_metadata_edit_service.py tests/integration/test_metadata_roundtrip.py tests/integration/test_metadata_recovery.py tests/ui/test_metadata_editor.py tests/fixtures/audio/manifest.json docs/metadata-mapping.md docs/validation/05-metadonnees.md "Plans d'exécution/05-metadonnees.md"
    git diff --cached --check
    git diff --cached

Ajouter par chemins ou morceaux les migrations, raccordements à Fullscreen player et services partagés effectivement modifiés. Remplacer les lignes de validation proposées ci-dessous par le résultat réel, puis créer le message sans interpolation PowerShell :

    $mteeCommitMessage = @'
    feat(metadata): add verified field editing and conflict-aware undo

    Changes: format-specific field mappings, serialized writes, readback,
    recovery journal, autosave states and explicit multi-selection patches.
    Validation: record roundtrip, preserved tags/artwork, failure recovery,
    UI and standalone Windows results in docs/validation/05-metadonnees.md.
    Limits: unsupported fields stay read-only; source conflicts require reload.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-05-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Vérifier que les hashes local et distant concordent après fetch. Un échec réseau ou une divergence se traite selon le plan 00 sans push forcé ni nouveau commit factice. Rapporter le hash confirmé après publication ; ne pas le préremplir dans ce plan ou dans son propre commit.

Note de révision — 2026-09-10, Codex : création du plan ; adaptateurs de tags explicites, journal de reprise, brouillons liés aux UUID et composants QML partagés avec les étapes précédentes.
