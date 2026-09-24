# 06 — Renommage, déplacement et corbeille — livraison C


Ce plan vivant suit [PLANS.md](../PLANS.md) et traduit `PLAN.md`, §4.4 et les règles de navigation du §3. Préparé le 2026-09-10. Le 2026-09-24, une première tranche Windows a été implémentée et vérifiée par tests automatisés et paquet isolé. Le renommage, le déplacement même volume et l'aperçu de dépôt entre groupes sont disponibles ; la corbeille et l'intervolume restent hors livraison.

## Objectif et résultat observable


L'utilisateur peut renommer, déplacer et mettre à la corbeille les fichiers sélectionnés depuis les menus et raccourcis. Le déplacement entre les deux panneaux affiche sa destination et demande confirmation. Cliquer dans l'arborescence reste une navigation et ne déplace aucun fichier.

Après une opération réussie, les deux panneaux, les métadonnées et la file du lecteur retrouvent le morceau grâce au même UUID, à son nouvel emplacement. Aucune collision de nom n'écrase un fichier. Une corbeille indisponible produit une erreur et laisse la source en place ; MTEE ne propose aucun repli automatique vers une suppression définitive.

Les opérations s'effectuent hors thread UI avec état, progression et résultats par fichier. Un déplacement peut être annulé avant sa publication ou inversé ensuite lorsque les conditions le permettent. Une erreur partielle reste visible et reprenable, sans prétendre qu'un lot entier a réussi.

## Progress


- [x] (2026-09-10) Plan préparé ; implémentation et essais restaient à effectuer.
- [x] (2026-09-24) Vérifier UUID, révisions, accès exclusifs et journaux du plan 05 ; le déplacement conserve l'UUID et utilise `FileAccessCoordinator`.
- [x] (2026-09-24) Définir et tester l'adaptateur Windows sans écrasement : `MoveFileW` sur le même volume, sans repli de suppression.
- [x] (2026-09-24) Implémenter l'aperçu, Rename, le déplacement sur un volume et son journal de reprise.
- [ ] (2026-09-24) Rename/Move sont reliés aux menus et raccourcis ; le dépôt entre deux groupes ouvre l'aperçu Move avec confirmation. Delete n'ouvre qu'une explication ; corbeille non livrée, geste natif non vérifié manuellement.
- [x] (2026-09-24) Maintenir les références et permettre Undo lorsque la destination est inchangée et l'ancien chemin libre.
- [x] (2026-09-24) `uv sync --locked`, Ruff, Pyright, tests unitaires/intégration (128 réussis, 2 ignorés, 1 désélectionné), tests UI par fichier (29 réussis), copie isolée et paquet Windows avec smoke vérifiés.
- [ ] (2026-09-24) Recette manuelle, geste souris, second volume, opérations intervolumes et corbeille native restent à faire ou à implémenter.
- [x] (2026-09-24) Mettre à jour les preuves, committer la tranche et confirmer le push : `7d10b05dad89d9d00141a31cc0851552bbaa2a0d` est présent sur `origin/main`.
- [x] (2026-09-24) Ajouter l'aperçu Move par dépôt entre groupes ; `4da180c7c3d75b64374f1d95331dc944f9e712ff` est présent sur `origin/main` après fetch et comparaison des hashes.

## Surprises & Discoveries


- 2026-09-24 — La lecture système autorisée identifie C: en NTFS et un volume NTFS sans lettre ; seul C: apparaît comme disque logique et le compte n'est pas administrateur. Aucun second volume de recette n'est disponible ; le rapport ne conclut pas sur les déplacements intervolumes.
- 2026-09-24 — La documentation Microsoft de `MoveFileW` exige un nouveau nom libre. Le test Windows de collision après l'aperçu conserve le contenu créé par un autre processus ; le renommage où seule la casse change passe par un nom temporaire unique.
- 2026-09-24 — Une panne injectée après le déplacement natif laisse le chemin de destination et l'ancien enregistrement SQLite visibles comme NeedsRecovery. L'Undo vérifie la révision et l'empreinte avant le retour.
- 2026-09-24 — Les tests UI passent fichier par fichier, mais l'ensemble `tests/ui` dans un seul processus s'est arrêté après le premier test pendant plus de 60 secondes. Il a été interrompu ; ce résultat n'est pas un succès de suite complète.
- 2026-09-24 — Une sonde STA a appelé `IFileOperation` avec `FOFX_RECYCLEONDELETE` sur une copie WAV. HRESULT réussi et aucun abandon, mais la source a disparu et l'espace de noms Shell de la Corbeille est resté vide ; une sauvegarde séparée a restauré le même SHA-256. Pas de binding produit ni de capacité de corbeille activée sans résultat natif fiable par élément et restauration démontrée.
- 2026-09-24 — Le dépôt d'une sélection d'un groupe éditeur sur un onglet dossier distinct appelle la même prévisualisation Move. Le test offscreen appelle la route QML et vérifie la destination ; le geste souris n'a pas été vérifié manuellement.

## Decision Log


Les décisions initiales suivantes sont proposées par Codex le 2026-09-10 ; toute évolution doit conserver date, auteur et motif.

- 2026-09-10 — Limiter ces commandes aux fichiers audio sélectionnés. Motif : renommer récursivement des dossiers ajouterait des risques et n'est pas requis pour la première gestion physique de la collection.
- 2026-09-10 — Prévisualiser les chemins source/destination avant un déplacement et confirmer systématiquement celui entre panneaux. Motif : l'utilisateur doit pouvoir distinguer navigation et mutation.
- 2026-09-10 — Garantir l'absence d'écrasement dans l'opération native, au-delà d'un simple test préalable d'existence. Motif : une autre application peut créer le même nom entre la prévisualisation et l'exécution.
- 2026-09-10 — Utiliser un journal durable par fichier pour les mouvements, notamment entre volumes. Motif : une opération disque et une transaction SQLite ne peuvent pas constituer une transaction atomique commune.
- 2026-09-10 — Exposer une capacité de corbeille stricte, vérifiée sur Windows. Motif : une bibliothèque qui efface définitivement lorsque le recyclage échoue ne satisfait pas `PLAN.md`.
- 2026-09-24 — Livrer Rename et Move sur le seul volume accessible, avec `MoveFileW` et aucun binding supplémentaire. Motif : l'API refuse la destination déjà existante et le protocole couvre les déplacements atomiques sur le même volume ; la preuve intervolume manque.
- 2026-09-24 — Laisser Move to trash indisponible après l'échec de l'expérience native `IFileOperation` ; conserver l'absence de binding COM produit. Motif : la copie a disparu sans élément Shell observable ni restauration démontrée.
- 2026-09-24 — Raccorder `FileActionsMenu` au menu contextuel de la liste et charger le dialogue depuis `Main.qml`, plutôt que de modifier `EditorArea.qml`. Motif : les actions appartiennent aux morceaux sélectionnés dans `TrackListView` et les raccourcis sont gérés à la fenêtre ; l'aperçu conserve une liste d'UUID immuable.
- 2026-09-24 — Vérifier l'existence et la révision d'un fichier à l'écriture du lot de scan. Motif : un lot ancien qui arrive après Move ne doit pas recréer l'ancien chemin comme un nouvel UUID.

## Outcomes & Retrospective


La tranche livrée comprend l'aperçu, le renommage, le déplacement sur le même volume, le journal de reprise, les résultats par fichier, l'annulation d'un lot entre deux fichiers, la vérification d'un lot de scan ancien, l'Undo conditionnel et l'ouverture de l'aperçu Move après dépôt entre groupes. Les tests Windows confirment la conservation de l'UUID, la casse seule, l'absence d'écrasement et la visibilité d'une panne après le déplacement. Le parcours UI simulé relie le dépôt à la même prévisualisation confirmée. La migration 005 crée le journal dans la base et le paquet autonome le charge au schéma 5.

La phase ne satisfait pas encore le plan entier : déplacement intervolume avec copie et reprise, recyclage réel et restauration, erreurs de support/permissions/espace, test pendant lecture mpv, geste drag-and-drop réel et recette manuelle restent non validés. Le dépôt entre groupes ouvre un aperçu et demande confirmation, mais son geste n'a pas été vérifié manuellement. La corbeille et l'intervolume ne sont pas annoncés comme livrés. Le rapport [`docs/validation/06-fichiers.md`](../docs/validation/06-fichiers.md) distingue les preuves exécutées des limites.

## Contexte et prérequis


Le dépôt initial contient une spécification et des plans. Les chemins ci-dessous désignent les futurs livrables. Le [plan 05](05-metadonnees.md) et ses prérequis doivent fournir l'application Windows, l'explorateur à deux panneaux, SQLite, `TrackRepository`, `JobService`, `PlayerService`, les écritures de tags sérialisées et `FileAccessCoordinator` dans `services/file_access.py`. Avant cette étape, les maquettes du [plan 02](02-maquettes-ux.md) doivent avoir fixé et validé la distinction entre survol, sélection et lecture.

Un `track_id` est un UUID immuable, distinct de son chemin. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` constate l'état d'une source ; l'identifiant de fichier natif peut changer lors d'un mouvement entre volumes. Augmenter la génération après mutation connue de MTEE, sans créer un nouveau UUID. Un SHA-256 calculé en flux complète les contrôles avant les opérations critiques ; il ne devient pas l'identifiant du morceau.

`FileAccessCoordinator` accorde une mutation exclusive par UUID et rend Busy en présence d'un lecteur ou d'un job incompatible. Les métadonnées non enregistrées doivent finir ou être explicitement abandonnées avant un déplacement. Les commandes QML n'utilisent ni `shutil`, ni un chemin directement modifiable, ni un shell : elles demandent au service une opération sur une sélection capturée de UUID.

Les données de recette vont dans `.local/validation/06` avec `--data-dir`. Les sources de test sont des copies situées dans `.local/fixtures/06` et sur un second volume d'essai pour les cas intervolumes. `--demo` ne réalise aucune mutation utilisateur et ne suffit pas à valider cette étape. Sauvegarder la base SQLite de manière cohérente avant les migrations de schéma.

Le contrat de corbeille s'appuie sur la documentation officielle [IFileOperation::SetOperationFlags](https://learn.microsoft.com/fr-fr/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags), qui distingue recyclage, gestion des erreurs et enregistrement pour annulation. Vérifier au moment d'implémenter les flags réellement supportés et les résultats natifs, y compris l'état d'opération interrompue ; un code de retour initial favorable ne prouve pas que chaque fichier a été recyclé.

## Plan de travail et jalons


### Jalon 1 — Prévisualisation et adaptateur Windows


Créer `src/mtee/domain/file_operations.py`, `src/mtee/services/file_operation_service.py` et `src/mtee/services/platform/windows_file_ops.py`. `preview` résout les UUID, révisions et chemins absolus, vérifie disponibilité, capacités, collision et destination, puis rend un objet immuable avec identifiant et date. Avant exécution, refaire les vérifications : une prévisualisation n'est pas un verrou sur le système de fichiers.

Valider les noms Windows : nom vide, noms réservés, séparateurs, point ou espace final et changement de suffixe audio. L'action Rename modifie le nom de base en affichant clairement le suffixe ; un suffixe ne convertit pas le contenu. Un changement de casse seul utilise, si nécessaire, un nom temporaire unique et un journal permettant de reprendre l'étape intermédiaire.

Le protocole `PlatformFileOps` fournit renommage sans remplacement, publication sans remplacement, copie vérifiée, suppression de la seule source d'un déplacement vérifié et recyclage strict. Les opérations internes manipulent des chemins et handles dont l'identité a été contrôlée ; ne pas suivre aveuglément un lien remplacé entre validation et action. Les garanties Windows sont implémentées dans cet adaptateur, sans prétendre avoir validé Linux ou macOS.

Conduire une courte expérience native avant le raccordement UI : collision créée après preview, nom accentué, fichier verrouillé et corbeille indisponible. Pour la corbeille, utiliser `IFileOperation` avec recyclage demandé explicitement, arrêt sur erreur et contrôle du résultat par élément. Évaluer un binding COM Windows tel que `comtypes`, puis verrouiller celui qui passe ces essais dans `pyproject.toml` et `uv.lock`. Si la garantie de non-suppression ne peut pas être démontrée, la commande reste désactivée pour ce volume.

### Jalon 2 — Renommer et déplacer avec reprise


Créer `src/mtee/persistence/file_operation_repository.py` et la migration contenant opération, UUID, source, destination, révision/empreinte attendues, fichiers temporaires propres et phase. Les phases distinguent Prepared, Copying, DestinationPublished, SourceRemoved, Completed, Cancelled, Failed et NeedsRecovery. Le journal ne marque une opération terminée qu'après vérification du disque et transaction de mise à jour des références.

Sur le même volume, demander un déplacement natif qui échoue si la destination existe. Ne pas combiner « vérifier puis écraser » avec `replace`. Relire le nouvel emplacement et son identité après succès, conserver le UUID et mettre à jour le repository. Une erreur de mise à jour SQLite après le déplacement laisse un état NeedsRecovery avec les deux chemins connus, au lieu de tenter un retour susceptible d'écraser une création extérieure.

Entre volumes, copier dans un temporaire unique du volume cible, suivre la progression en octets et calculer une empreinte SHA-256 en flux. Fermer et vérifier taille, empreinte et attributs pris en charge, puis publier le nom final sans écrasement. Vérifier encore que la source est celle prévue avant de retirer uniquement cette source : utiliser le handle ou les garanties natives définies par l'adaptateur pour éviter une substitution de chemin.

Si le retrait de la source échoue, conserver les deux copies et signaler un déplacement incomplet. Le UUID reste rattaché à la source tant que le déplacement n'est pas finalisé ; le journal réserve la destination afin que le scanner ne lui crée pas silencieusement un second UUID. La reprise doit expliquer les deux emplacements et proposer seulement des actions compatibles avec leurs révisions actuelles.

Après réussite, émettre `TrackLocationChanged(track_id, old_path, new_path, revision)`. Les onglets et la file gardent leur UUID, le reader de métadonnées résout le nouveau chemin et les caches liés à l'emplacement se mettent à jour. Le changement de génération invalide conservativement les caches basés sur `SourceRevision`, même si le contenu sonore n'a pas changé ; une optimisation future devra prouver l'équivalence plutôt que la supposer.

### Jalon 3 — Menus, panneaux et corbeille


Créer `src/mtee/models/file_operation_model.py`, `src/mtee/qml/components/FileActionsMenu.qml` et `FileOperationDialog.qml`, puis les relier à `src/mtee/qml/components/EditorArea.qml` existant. Relier Rename à F2 et Move to trash à Delete lorsque le navigateur possède le focus ; ces raccourcis n'interceptent pas les champs de saisie. Les commandes désignent les UUID sélectionnés au moment de leur déclenchement, pas une sélection modifiable pendant l'exécution.

Le menu Move et le déplacement entre panneaux affichent fichiers, chemin source, destination absolue lisible, collisions et fichiers occupés. Le glisser-déposer ne démarre la mutation qu'après confirmation de cette prévisualisation. Un clic dans l'arbre ou un changement d'onglet ne crée aucune opération. Pour les lots, afficher résultats individuels et progression sans bloquer la navigation.

Avant la corbeille, présenter les fichiers concernés et l'action Move to trash. Appeler uniquement le recyclage strict de l'adaptateur ; ne jamais invoquer `unlink`, `remove`, `rmtree` ou un shell comme solution de repli à son échec. La suppression de source interne à un mouvement intervolume vérifié est une opération différente, inaccessible depuis la commande corbeille.

Après recyclage confirmé par élément, conserver le UUID et marquer sa source Trashed ou indisponible dans le repository ; ne pas effacer l'historique et les références de file. Un élément recyclé encore présent dans la file est visible comme indisponible et ne doit pas faire planter Next. La restauration depuis la corbeille système n'est promise comme Undo MTEE que si son adaptateur fournit un identifiant de restauration fiable et que cette capacité a été testée.

Pour un morceau joué, montrer Busy et offrir une action explicite Stop playback and continue. Après libération du handle, réévaluer la prévisualisation avant mutation. Si le lecteur peut conserver un fichier ouvert après renommage sur un volume donné, ne pas extrapoler ce comportement aux autres volumes ou à la corbeille.

### Jalon 4 — Annulation, reprise et références


`cancel(operation_id)` annule les travaux encore en attente et interrompt une copie avant publication ; la source reste présente. Après publication et retrait de source, l'action Undo move est une opération inverse distincte. Elle vérifie l'existence et la révision de la destination, l'absence de collision à l'ancien emplacement et les permissions avant d'effectuer le retour sans écrasement.

Au démarrage, inspecter les opérations incomplètes. Comparer les chemins, identités, révisions et empreintes enregistrés pour distinguer source seule, temporaire, deux copies et destination seule. Ne pas déduire l'état d'un seul booléen SQLite. Finaliser les références après preuve ou exposer NeedsRecovery ; aucun nettoyage automatique ne supprime un fichier dont l'appartenance à l'opération est incertaine.

Vérifier dans l'explorateur à deux panneaux que la sélection, l'inspecteur et la file suivent le UUID après succès, y compris après redémarrage. Les métadonnées historiques restent rattachées au même morceau. Les futures playlists et dérivations réutiliseront ces identifiants sans avoir à être construits à cette étape.

## Étapes concrètes


Exécuter toutes les commandes depuis la racine du dépôt. Installer le verrou existant, puis après le choix du binding Windows verrouiller et réinstaller la dépendance validée :

    uv sync --locked

Créer `tests/unit/test_file_operation_preview.py`, `test_file_operation_service.py`, `tests/integration/test_file_moves.py`, `test_file_operation_recovery.py`, `test_windows_trash.py` et `tests/ui/test_file_actions.py`. Déclarer `windows_file_ops` comme marqueur de tests natifs. Les tests automatisés de corbeille utilisent des fichiers temporaires précisément identifiés, jamais une collection utilisateur.

    uv sync --locked
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_file_operation_preview.py tests/unit/test_file_operation_service.py tests/integration/test_file_moves.py tests/integration/test_file_operation_recovery.py tests/ui/test_file_actions.py
    uv run pytest -m windows_file_ops tests/integration/test_windows_trash.py
    uv run python -m mtee --data-dir .local/validation/06

Préparer via le gestionnaire de fichiers des copies sur deux volumes d'essai et sélectionner ces dossiers dans MTEE. Consigner leurs types de volumes, sans exposer de chemin personnel, dans `docs/validation/06-fichiers.md`. Tester ensuite le paquet :

    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/06-package

## Validation et acceptation


Tester renommage simple, accents, casse seule, nom invalide, nom réservé et collision créée après prévisualisation. Les tests prouvent que le fichier préexistant à destination conserve son empreinte. Naviguer dans l'arborescence puis changer d'onglet ne déclenche aucun appel de mutation. Le déplacement entre panneaux attend sa confirmation et montre la bonne destination.

Tester mouvement dans un volume et entre deux volumes, copie longue annulée, manque d'espace, permissions insuffisantes, disque déconnecté et incident injecté entre chaque phase. Après tout échec, le rapport indique quels fichiers existent et où ; une opération incomplète n'est pas affichée comme Completed. La reprise après redémarrage garde les données et retrouve un état cohérent sans action destructive implicite.

Après mouvement réussi, vérifier UUID inchangé, nouvelle révision, métadonnées et historique conservés, sélection actualisée dans les deux panneaux et file du lecteur encore résoluble. Tester Busy sur le morceau joué, puis arrêt explicite et reprise de l'action. Vérifier qu'une autosauvegarde de tags et un déplacement du même UUID ne s'exécutent pas simultanément.

La corbeille est validée par présence réelle de la copie d'essai dans la corbeille système et possibilité de restauration via Windows. Forcer une indisponibilité de corbeille dans l'adaptateur, puis la tester sur un support réellement non pris en charge lorsqu'il est disponible : MTEE affiche l'échec et la source reste présente. Un test simulé de cet incident ne remplace pas la preuve du recyclage natif normal.

Undo move rétablit l'emplacement lorsque les conditions sont inchangées. Si un autre fichier occupe l'ancien nom ou si le fichier déplacé a été modifié extérieurement, Undo refuse d'écraser et explique le conflit. Ne pas annoncer une restauration depuis la corbeille comme disponible si elle n'a pas été implémentée et testée.

Le paquet Windows doit reproduire au minimum renommage, déplacement avec confirmation, recyclage et erreur de collision sur des copies, sans Python ni dépendance COM présente par hasard dans l'environnement. L'interface reste navigable pendant la copie ; relever les délais d'interaction avec le même protocole que le plan 03. Les plateformes non testées restent hors bilan de compatibilité.

## Reprise et réexécution


Une opération possède un identifiant unique ; relancer après un résultat perdu commence par consulter le journal et inspecter le disque, pas par répéter aveuglément le déplacement. Un mouvement déjà achevé peut être confirmé à partir de ses preuves sans recopier son fichier. Une destination inconnue ou modifiée requiert une résolution explicite.

Les chemins temporaires sont créés à l'intérieur de la destination autorisée avec noms uniques. Avant leur nettoyage, vérifier leur chemin absolu, leur rattachement à l'opération et leur identité ; limiter l'action au fichier visé. Conserver source et destination lorsqu'une reprise ne peut pas prouver quelle copie retirer. Pour un nouveau test, utiliser des copies fraîches et une base de recette identifiée.

## Interfaces et dépendances


`FileOperationService.preview(kind, track_ids, destination_or_name)` rend `FileOperationPreview` avec chemins résolus, révisions, capacités et conflits. `execute(preview_id)`, `cancel(operation_id)` et `undo_move(operation_id)` rendent des résultats par UUID, phase et code d'erreur lisible. Le service revalide les préconditions avant toute mutation et ne reçoit jamais une commande shell.

`PlatformFileOps.move_no_replace`, `publish_no_replace`, `copy_verified` et `trash_strict` isolent Windows. L'adaptateur COM s'initialise et se termine dans son thread approprié ; ses callbacks sont convertis en messages vers `JobService`, jamais en mutations QML. `FileOperationRepository` conserve les phases et preuves utiles à la reprise ; `TrackRepository` confirme les changements d'emplacement en transaction.

`FileAccessCoordinator` coordonne mutations et lecture par UUID. `JobService` garde `queued`, `running`, `succeeded`, `failed`, `cancelled` ; les phases Prepared à NeedsRecovery appartiennent au journal métier, et une interruption de job devient `failed` avec code `interrupted`. `TrackLocationChanged` met à jour modèles et file ; `SourceChanged` porte la nouvelle révision. Ajouter uniquement le binding natif effectivement retenu et verrouillé. Conversion, FFmpeg/ffprobe, playlists et portage ne sont pas introduits par cette étape.

## Preuves et livraison Git


Mettre à jour ce plan, le rapport `docs/validation/06-fichiers.md`, la documentation des dépendances natives et les résultats par volume avant de committer. Inclure les cas de panne et limites d'Undo réellement observés. Les copies audio, journaux locaux, bases et fichiers de corbeille ne sont pas des livrables Git.

Sur `main`, avec `origin` vérifié vers `https://github.com/foliarn/mtee.git`, inspecter puis indexer les changements propres à cette étape ; adapter les chemins seulement après lecture du code réel.

    git status --short
    git diff --check
    git add -- pyproject.toml uv.lock src/mtee/domain/file_operations.py src/mtee/services/file_operation_service.py src/mtee/services/platform/windows_file_ops.py src/mtee/persistence/file_operation_repository.py src/mtee/models/file_operation_model.py src/mtee/qml/components/FileActionsMenu.qml src/mtee/qml/components/FileOperationDialog.qml src/mtee/qml/components/EditorArea.qml tests/unit/test_file_operation_preview.py tests/unit/test_file_operation_service.py tests/integration/test_file_moves.py tests/integration/test_file_operation_recovery.py tests/integration/test_windows_trash.py tests/ui/test_file_actions.py docs/native-dependencies.md docs/validation/06-fichiers.md "Plans d'exécution/06-fichiers.md"
    git diff --cached --check
    git diff --cached

Ajouter séparément les migrations et adaptations réelles de repository, lecteur et packaging ; éviter d'embarquer des modifications étrangères dans les services partagés. Adapter les contrôles du message aux résultats réels, puis utiliser cette here-string PowerShell non interpolée :

    $mteeCommitMessage = @'
    feat(files): add verified moves, renaming and strict recycle-bin actions

    Changes: destination previews, no-overwrite native operations, per-file
    recovery journal, stable references and conditional move undo.
    Validation: record collision, interruption, cross-volume, playback-lock
    and standalone Windows checks in docs/validation/06-fichiers.md.
    Limits: unavailable recycle bins fail safely; undo depends on unchanged paths.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-06-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Confirmer l'égalité des hashes après fetch avant de cocher la publication. Un push refusé se reprend selon le plan 00, sans forcer ni réécrire l'historique distant. Le hash confirmé est rapporté après l'opération ; ne pas le fabriquer dans les preuves enregistrées avant le commit.

Note de révision — 2026-09-10, Codex : création du plan ; opérations sans écrasement, corbeille stricte, reprise intervolumes et maintien des UUID préparés avec les contrats du socle.
