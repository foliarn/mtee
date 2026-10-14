# Étape 114 — Paramètres par catégories et page Profil

ExecPlan vivant. Suivre `PLANS.md` à la racine. Cette étape reprend les paramètres de la v0.1 : catégories réelles, suppression des lignes factices, page Profil (nom affiché, avatar), écran Data & privacy (historique, statistiques, sauvegarde et restauration). Les statistiques affichées dans le profil sont décrites dans l'étape 115.

## Objectif et résultat observable

La page Paramètres est organisée par catégories : General, Library, Playback, Analysis, Keyboard shortcuts, Data & privacy, About. Chaque réglage réel est rangé à une seule place ; les lignes factices (dossiers, apparence, « Remember the queue » sans effet) disparaissent. Le bouton Profil de la barre d'activité ouvre une page avec le nom affiché (qui remplace « Playlist creator name ») et un avatar copié dans le dossier de données. Data & privacy vide l'historique du panneau History, réinitialise les statistiques, fait une copie cohérente de la base et planifie une restauration appliquée au prochain démarrage.

Une étape 114 n'est livrée que lorsque la revue de maquette est validée. Au moment de cette rédaction, seule la partie backend et la maquette sont prêtes.

## Prérequis et état du dépôt

- Base : `main` à `30b6a6d`. Dernière migration existante : `025_track_loudness.sql`. Cette étape n'ajoute aucune migration : le profil et l'état de restauration utilisent la table `settings` et des fichiers dans `<données>/profile` et `<données>/restore`. Le numéro `027` n'est donc pas consommé.
- Le réglage de normalisation (étape 116) et les analyses (étape 33) sont déjà présents et restent inchangés.
- L'étape 112 (règles de découpage des artistes) n'est pas fusionnée. Ses règles sont seulement représentées par un emplacement dans les statistiques et par une maquette.
- `vendor/` est copié dans le worktree ; `.local/` reste ignoré par Git.

## Modifications par zone

Backend, déjà commité (`136fba3`) :

- `src/mtee/services/profile_service.py` : nom affiché (`profile/display_name`), avatar copié dans `<données>/profile`, migration unique de `playlists/creator`.
- `src/mtee/services/data_privacy.py` : sauvegarde (`Database.backup_to`), validation d'une sauvegarde, restauration planifiée et appliquée au démarrage, réinitialisation des statistiques.
- `src/mtee/models/profile_model.py`, `src/mtee/models/data_privacy_model.py` : modèles Qt. Les travaux longs passent par `JobService`. Le fournisseur d'image `profile` sert l'avatar à QML sans accès direct au fichier.
- `src/mtee/services/player_service.py`, `src/mtee/models/player_model.py` : `clear_history()` vide les 100 entrées du panneau History et sauvegarde la session ; la file et le journal d'écoute restent.
- `src/mtee/app.py` : application de la restauration avant l'ouverture de la base ; création des modèles ; exposition en propriétés de contexte `profile`, `statistics`, `dataPrivacy` (aucune page ne les utilise encore).
- `src/mtee/models/playlists_model.py` : le créateur des playlists lit le nom affiché ; `setCreator` garde sa signature et écrit la même clé.
- `src/mtee/persistence/database.py` : `foreign_migration_names()`, réutilisé par la vérification de l'historique des migrations.

Maquette, à commiter après la revue de cette étape :

- `src/mtee/prototypes/settings_profile_114.py` : données fictives et actions du prototype.
- `src/mtee/qml/prototypes/settings_profile_114/ReviewWindow.qml` : Settings, Profile, Explorer (colonnes optionnelles) et dialogues.
- `scripts/review_settings_profile_114.py` : lancement et captures.
- `docs/ux/review-114-115-parametres-profil-stats.md` et `docs/ux/review-114-115-parametres-profil-stats/` : revue et captures.

## Commandes utilisées

Depuis la racine du worktree :

    uv sync --locked
    uv run pytest -q -p no:cacheprovider tests/unit/test_listening_periods.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_profile_service.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_data_privacy.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_statistics_model.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_profile_and_privacy_models.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_player_play_log.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_player_service.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_database_migrations.py
    uv run ruff check <fichiers touchés> ; uv run ruff format --check <fichiers touchés>
    uv run pyright <nouveaux modules>
    uv run python -m mtee --data-dir .local/run-114 --smoke-test
    uv run python scripts/review_settings_profile_114.py --view settings --category privacy --data-dir .local/validation/114/review

## Critères de recette

- Le lancement sur une base neuve (`--data-dir`) sort avec le code 0.
- Une sauvegarde est vérifiée, ne remplace jamais un fichier existant, et ne modifie pas la base en cours.
- Une restauration n'a aucun effet tant que l'application n'a pas redémarré ; au redémarrage, la base est remplacée et une copie de la base précédente est conservée.
- Un fichier invalide, une base plus récente que la version de l'application, ou un historique de migrations inconnu est refusé avant toute planification.
- Le nom affiché migre une fois depuis `playlists/creator` ; une valeur déjà présente l'emporte.
- L'avatar est une copie : le fichier choisi n'est jamais modifié.
- La maquette s'ouvre sans erreur QML pour chaque catégorie, la page Profil, l'Explorer et les dialogues.

## Reprises et idempotence

- Une sauvegarde interrompue est supprimée par `Database.backup_to` (le fichier partiel ne reste pas) ; une relance crée un nouveau fichier horodaté.
- La restauration s'écrit en deux temps : copie `pending.sqlite3`, puis marqueur `pending.json`. Sans marqueur, la copie est ignorée et supprimée au démarrage. Un marqueur illisible annule la restauration avec un message.
- Au démarrage, la copie de sécurité est faite avant tout remplacement. Les fichiers `-wal` et `-shm` de l'ancienne base sont retirés juste avant le renommage atomique.
- La migration du créateur est idempotente : après la première exécution, la clé héritée est supprimée.

## Interfaces

    ProfileService(settings, profile_dir)
    ProfileService.display_name() -> str ; playlist_creator() -> str
    ProfileService.set_display_name(value) -> str        # ValueError si vide ou > 240
    ProfileService.set_avatar(source: Path) -> Path      # ValueError si format ou taille refusés
    ProfileService.avatar_path() -> Path | None ; clear_avatar()
    ProfileService.migrate_legacy_creator() -> bool

    back_up_database(database, destination) -> Path
    validate_backup(path, *, supported_version, migrations, database_path=None) -> BackupInfo
    stage_restore(source, layout, *, database_path, supported_version, migrations, now) -> PendingRestore
    apply_pending_restore(layout, *, database_path, supported_version, migrations, now) -> RestoreOutcome | None
    cancel_pending_restore(layout) ; read_pending_restore(layout) ; reset_statistics(play_log) -> int

    PlayerService.clear_history() -> int
    PlayerModel.clearHistory() -> int                    # slot Qt

    ProfileModel.setDisplayName(str) ; setAvatarFrom(url) ; clearAvatar() ; signal nameChanged(str)
    DataPrivacyModel.backUpTo(url) ; restoreFrom(url) ; cancelRestore() ; resetStatistics()

## Progress

État au 14 octobre 2026 :

- [x] Backend : profil, migration du créateur, sauvegarde, restauration planifiée et appliquée au démarrage, réinitialisation, vidage de l'historique (commit `136fba3`).
- [x] Tests du backend : 42 tests nouveaux qui passent (voir Outcomes).
- [x] Maquette des paramètres, du profil, des colonnes et des dialogues, avec 17 captures et la revue (`docs/ux/review-114-115-parametres-profil-stats.md`).
- [x] Commit de la maquette sur la branche de travail (référence donnée dans le compte rendu de la tâche).
- [ ] Revue utilisateur de la maquette (choix ouverts listés dans la revue). Rien n'est implémenté dans l'interface avant cette revue.
- [ ] Remplacement de `SettingsView.qml` et branchement de la page Profil : après revue.
- [ ] Publication : non demandée, aucun push effectué.

## Surprises & Discoveries

- « Remember the queue between sessions » n'était relié à rien : une propriété locale de la page, jamais enregistrée. La file est restaurée à chaque démarrage par la session de lecture. La ligne est retirée de la maquette ; la décision reste ouverte (voir revue).
- Le créateur des playlists est affiché dans l'en-tête de chaque playlist (`PlaylistHeader.qml`), et non seulement dans les réglages. Le nom affiché l'alimente donc directement.
- Le menu Library › « Add folder… » était déjà désactivé en v0.1 (`TitleBar.qml`) : la ligne factice correspondante n'a rien à remplacer.
- `tests/ui/test_playlists_ui.py` échoue déjà à la base sur deux cas (`test_create_add_like_search_visible_playback_and_reload`), comme indiqué par la note de base. Le test de `setCreator` qu'il contient n'est pas celui qui échoue.
- La capture hors écran (`QT_QPA_PLATFORM=offscreen`) donne une fonte plus lourde et déclenche des infobulles au premier passage de souris. Les captures finales sont faites à l'écran.

## Decision Log

- 2026-10-14, agent Claude : aucune migration. Le profil est dans `settings` (`profile/display_name`, `profile/avatar_file`) ; la restauration est dans `<données>/restore`. Motif : il n'y a aucune donnée relationnelle à interroger, et une migration ajouterait une sauvegarde et des tests de schéma sans bénéfice visible.
- 2026-10-14 : le créateur des playlists lit la clé du nom affiché ; `PlaylistsModel.setCreator` est conservé (il est appelé par `tests/ui/test_playlists_ui.py`) et écrit la même clé.
- 2026-10-14 : « Clear listening history » vide le panneau History (session de lecture), pas le journal d'écoute. Motif : le brief l'appelle « 100-entry history ».
- 2026-10-14 : la restauration n'est jamais appliquée pendant que l'application tourne. Elle est planifiée, puis appliquée au démarrage avant l'ouverture de la base, après une copie de sécurité de la base actuelle. Une copie qui échoue annule la restauration plutôt que de remplacer la base sans sauvegarde.
- 2026-10-14 : les copies de sécurité (`before-restore-*.sqlite3`) ne sont jamais supprimées automatiquement ; la politique de conservation reste à décider.
- 2026-10-14 : l'avatar est copié octet par octet après validation (format image reconnu par Qt, 10 Mo au plus). Pas de recadrage ni de réduction, pour que le fichier reste celui de l'utilisateur.
- 2026-10-14 : le nom affiché est vide par défaut ; les playlists affichent « MTEE » dans ce cas, comme avant.
- 2026-10-14 : les statistiques sont lues par une tâche `JobService` ; chaque demande porte un numéro de génération, et un résultat ancien est ignoré.
- 2026-10-14 : le classement des artistes renvoie une liste vide, marquée `TODO(step 112)`. Il ne réimplémente pas le découpage.
- 2026-10-14 : les modèles sont créés dans `app.py` et exposés en propriétés de contexte, sans page qui les utilise. Motif : permettre le branchement après revue sans toucher de nouveau au démarrage.
- 2026-10-14 : attribution du commit. Le brief demandait `Co-Authored-By: Claude Opus 5.5` ; le rappel d'attribution fourni avec la session demande `Claude Haiku 5.5`, qui est le modèle réellement utilisé. Le commit porte la ligne Haiku ; à corriger si le brief est retenu.

## Outcomes & Retrospective

Constats observés (commandes réelles, 14 octobre 2026) :

- Tests nouveaux, tous réussis : `test_listening_periods.py` 10, `test_profile_service.py` 10, `test_data_privacy.py` 12, `test_statistics_model.py` 5, `test_profile_and_privacy_models.py` 4, et un test ajouté à `test_player_play_log.py` (6 au total dans ce fichier).
- Non régression : `test_player_service.py` (71 réussis), `test_play_log.py` (11), `test_play_log_repository.py` (9), `test_playback_history.py` (3), `test_database_migrations.py` (13), `test_genre_manager_upgrade.py` (3) réussissent.
- `tests/ui/test_playlists_ui.py` : deux cas en échec (`test_create_add_like_search_visible_playback_and_reload[False/True]`), présents à la base `30b6a6d` selon la note de base ; l'échec se produit après le passage sur `setCreator`, à une recherche de texte.
- `uv run python -m mtee --data-dir .local/run-114 --smoke-test` sort avec le code 0 (base neuve, schéma 25 inchangé).
- Ruff (vérification et format) et pyright : aucune erreur sur les fichiers nouveaux ou touchés.
- Maquette : 17 captures produites, chargement sans erreur QML pour chaque catégorie, la page Profil, l'Explorer et les dialogues. Un script de vérification local (dans `.local/`, non versionné) appelle les actions du prototype (catégorie, période, règle, dialogues, colonnes, nom, avatar) et confirme leurs effets : « prototype slots OK ».

Limites :

- Les clics dans la fenêtre ne sont pas rejoués automatiquement ; le comportement au pointeur reste à vérifier à la revue.
- La restauration n'a pas été essayée sur une vraie base de l'utilisateur, ni sur une base copiée à travers un redémarrage réel de l'application. Les tests passent par les fonctions de service et une base temporaire.
- Le paquet Windows n'a pas été construit ni testé, comme demandé.
