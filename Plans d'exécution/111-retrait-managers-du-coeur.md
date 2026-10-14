# Étape 111 — Retirer l'Artist manager et le Genre Manager du cœur

ExecPlan rédigé le 14 octobre 2026 selon [PLANS.md](../PLANS.md). Référence produit : [PLAN.md](../PLAN.md). Il prépare la version publique v0.1, livrée sans plugins. Il s'appuie sur le [plan 110](110-plugin-genre-manager.md) (Genre Manager en plugin) et précède l'étape 112, qui ajoute une vue Artistes du cœur construite à partir des tags.

## Objectif et résultat observable

Dans la version v0.1, MTEE ne montre ni Plugins, ni Artist manager, ni Genre Manager. La barre d'activités ne contient plus d'entrée « artists ». Une installation neuve ne crée aucune table d'artistes ni de Genre Manager. Une base créée par l'ancienne version, jusqu'à la migration 023 incluse, s'ouvre sans perte de données et conserve ses tables. L'éditeur de tags enregistre le champ Artist en n'écrivant que les tags ; la question « One artist / Several artists » reste posée lorsqu'un crédit contient une virgule ou un `&`. Les liens vers une page d'artiste sont inertes dans l'interface du cœur, en attendant l'étape 112.

Le code des deux plugins reste dans le dépôt et se charge lorsque l'interrupteur `PLUGIN_UI_ENABLED` vaut `True`. Le plugin platform (installation, suppression, téléchargement) n'est pas construit.

## Prérequis et état du dépôt

L'étape part de la branche `worktree-agent-a22a42d870b4332b0`, créée à partir de `a073f1d` (« feat(genre-manager): deliver native classification and safe organization »). Le worktree de base utilisé pour les comparaisons de tests est un worktree temporaire détaché à `a073f1d`. Les migrations 019, 020, 022 et 023 existent dans `src/mtee/persistence/migrations/` avant l'étape. Le répertoire `vendor/` a été copié depuis le dépôt principal ; il n'est pas versionné.

Les décisions de conception sont identifiées comme telles dans le journal de décisions. Les constats observés sont listés dans les découvertes.

## Modifications par sous-étape

### 111.1 — Migrations propres aux plugins

Le fichier `src/mtee/persistence/database.py` distingue désormais les scripts du cœur (`migrations/`, versions 001 à 018) et les ensembles propres aux plugins. Les quatre scripts 019, 020, 022 et 023 sont déplacés, sans modification de leur contenu, vers `src/mtee/plugins/artist_manager/migrations/` et `src/mtee/plugins/genre_manager/migrations/`. La table `PLUGIN_OWNED_MIGRATIONS` associe chaque version à son plugin et à son nom. Le cœur accepte un enregistrement de ces versions seulement avec le nom sous lequel il a été appliqué ; il ne les exécute jamais.

La méthode `Database.migrate()` ne lance que les scripts du cœur qui ne figurent pas dans `schema_migrations`. Le numéro de schéma supporté est le plus élevé entre les scripts du cœur et les versions des plugins, de sorte qu'une base de l'ancienne version (schéma 23) reste ouverte. La méthode `Database.migrate_plugin(plugin_id, scripts)` applique les scripts en attente d'un plugin après une sauvegarde cohérente si le fichier contient déjà des données, et refuse tout script non enregistré. `PRAGMA user_version` ne peut plus diminuer : un script de plugin peut porter un numéro inférieur à la version déjà atteinte.

La fonction `prepare_plugin_schema(database, plugin_id)` de `src/mtee/plugins/registry.py` applique d'abord les dépendances du plugin. Le Genre Manager exige l'Artist manager, car `gm_artist_contributions` référence `artists`. Les repositories `ArtistRepository` et `GenreManagerRepository` appellent cette fonction à leur ouverture : les tables d'un plugin n'existent donc que là où le plugin est chargé.

### 111.2 — Déplacement de l'Artist manager

Les modules suivants sont déplacés dans `src/mtee/plugins/artist_manager/` avec `git mv` : `repository.py` (ancien `persistence/artist_repository.py`), `profile.py`, `folder_genres.py`, `folder_genre_service.py`, `file_service.py`, `identification.py`, `service.py` et `models.py`. Les chemins d'import de `src`, `tests` et `scripts` sont mis à jour. Les helpers purs de `domain/artists.py` restent dans le cœur, comme demandé. Les fichiers QML restent dans `qml/components/` et `qml/views/`, où vivent déjà les `Genre*.qml` : `Main.qml` charge ces dossiers par import de répertoire. Aucun dossier QML propre au plugin n'a été créé, pour rester cohérent avec le Genre Manager.

### 111.3 — Interrupteur et entrées masquées

Le fichier `src/mtee/plugins/registry.py` contient la constante `PLUGIN_UI_ENABLED = False` et la fonction `plugin_ui_enabled()`. Lorsque l'interrupteur est éteint, `app.py` n'attache ni la fabrique du Genre Manager, ni l'Artist manager, et ne construit pas le service d'identification des artistes. Le cœur ne crée donc aucun repository d'artistes. Le workspace expose `pluginUiEnabled` et `artistManager` (nul en v0.1). `ActivityBar.qml` masque le bouton Plugins selon cette propriété ; l'entrée « artists » est retirée. `SideBar.qml` ne contient plus le volet de l'Artist manager. À l'ouverture d'un état sauvegardé, une activité absente ou désactivée revient à Explorer (`_known_activity`).

### 111.4 — Éditeur de tags découplé

Le Protocol `ArtistCreditRules` de `src/mtee/services/artist_credit_rules.py` fournit `protected_names()`, `suggestions()` et `record_credit_choice()`. L'implémentation par défaut `NoArtistCreditRules` ne protège aucun nom, ne suggère rien et n'enregistre aucun choix. `MetadataEditorModel` reçoit `artist_rules` ; l'enregistrement d'une sauvegarde n'appelle plus `sync_tags`, et le signal `artistsSynced` est supprimé. Un nouveau slot `recordCreditChoice(text, one_artist)` reçoit la réponse « One artist » ou « Several artists », que `ArtistField.qml` transmet avant d'appliquer son choix. La question reste posée car `splitPreview` ne connaît aucun nom protégé en v0.1.

`AnalysisModel` n'importe plus le service d'identification : il dépend du Protocol local `ArtistCohort`, qui ne reçoit rien en v0.1.

### 111.5 — Liens d'artistes inertes

Voir la liste ci-dessous. Les appels restent en place ; ils ne produisent aucun lien en v0.1.

## Appels de lien vers un artiste rendus inertes

- `components/PlayerIsland.qml` : `workspace.trackArtists(track.id)` renvoie une liste vide faute de gestionnaire ; la rangée de liens est donc masquée et le nom plain text s'affiche. Appel `workspace.openArtistPage(...)` ligne 133 : jamais atteint.
- `views/FullscreenPlayer.qml` : `workspace.openPlayingSource()` ; sa branche « artist » ne s'exécute que si un gestionnaire est attaché.
- `models/workspace_model.py` : `openArtistView`, `openArtistPage` et `playArtistRows` ne font rien sans gestionnaire ; `trackArtists`, `revealTrack` (source `artist:`), `openPlayingSource` et `_source_label` ne consultent le gestionnaire que s'il est attaché.
- `components/HistoryList.qml`, `components/QueueList.qml`, `components/PlayingTrackMenu.qml` : `revealTrack` et `revealTrackForEdit` ; le chemin « artist » est inerte.
- Les vues plugin (`ArtistManagerPane.qml`, `views/ArtistsView.qml`, `views/ArtistReviewView.qml`, `components/ArtistHeader.qml`) ne sont plus atteignables depuis l'interface en v0.1.

`components/TrackRow.qml`, `components/InfoPanel.qml` et `components/FullscreenArtistCard.qml` n'ont pas de lien vers un artiste : rien à rendre inerte.

## Commandes et contrôles

Les commandes ci-dessous ont été exécutées depuis la racine du worktree.

    uv sync --locked
    uv run pytest -q tests/unit
    uv run pytest -q tests/integration/test_plugin_schema.py tests/integration/test_database_migrations.py tests/integration/test_genre_manager_upgrade.py
    uv run python .local/run_each.py tests/integration
    uv run python .local/run_each.py tests/ui
    uv run python .local/verify_111.py .local/run-111
    uv run python .local/verify_111.py .local/run-111-old --legacy
    uv run ruff check src tests scripts

Le fichier `.local/run_each.py` lance chaque fichier de test dans son propre processus, car `tests/ui` plante lorsqu'il est exécuté en un seul bloc sur cette machine. Le fichier `.local/verify_111.py` démarre le runtime réel hors écran sur un répertoire de données fourni.

## Critères de recette

- Une base neuve a le schéma 18 et aucune table commençant par `artist`, `track_artist` ou `gm_`.
- Une base construite par l'ancienne version jusqu'à 023 s'ouvre au schéma 23, conserve ses lignes et n'ouvre pas de sauvegarde superflue.
- Au démarrage, la barre d'activités n'a ni « artists » ni « plugins ».
- L'éditeur de tags enregistre un champ Artist sans écrire dans la base d'artistes, et propose « One artist / Several artists ».
- Les tests modifiés pour les plugins passent lorsque l'interrupteur est activé par le test lui-même.

## Surprises & Discoveries

- Les scripts 019 et 020 et les tables qu'ils créent sont utilisés aussi par le Genre Manager (`gm_artist_contributions` référence `artists`, et `artist_attribution` lit les tables d'artistes). Une dépendance entre plugins est donc nécessaire ; elle est traitée par `requires`.
- `_restore_groups` ne conservait déjà que les onglets de dossiers et de playlists : les onglets d'artistes et de Genre Manager ne reviennent donc pas après un redémarrage. Seule l'activité sauvegardée devait être corrigée.
- Le fichier `scripts/clean_orphan_artists.py` lit la base avec SQL brut et ne migre jamais ; seuls les tests qui préparent une base doivent charger le plugin.
- Plusieurs tests d'intégration et d'interface écrivaient directement dans les tables d'artistes après une simple migration du cœur ; ils chargent désormais le plugin en ouvrant son repository.
- `tests/unit/test_conversion_queue.py`, `tests/unit/test_icon_provider.py`, `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`, `tests/integration/test_mpv_playback.py` (plantage natif) et plusieurs tests d'interface échouent déjà au commit de base `a073f1d`, comme la comparaison des Outcomes le montre.

## Decision Log

- 2026-10-14 — Les scripts de plugin gardent leurs numéros globaux (019, 020, 022, 023). Une base existante les contient déjà avec ces numéros ; les renommer aurait exigé une migration de la table d'historique. Un futur plugin utilisera de nouveaux numéros, enregistrés dans `PLUGIN_OWNED_MIGRATIONS`.
- 2026-10-14 — Les enregistrements de plugin restent dans `schema_migrations`, au lieu d'une table séparée : les bases existantes les contiennent déjà et ne doivent pas être modifiées.
- 2026-10-14 — La sélection des scripts du cœur passe des numéros de version à l'ensemble des versions enregistrées. Un script de plugin peut porter un numéro inférieur à `user_version`, et une telle lacune ne doit pas empêcher l'application d'un script du cœur.
- 2026-10-14 — Les tables d'un plugin sont créées à l'ouverture de son repository, et non au démarrage de l'application. Cela garantit qu'un plugin non chargé ne crée rien, sans ajouter de code d'activation.
- 2026-10-14 — Les fichiers QML des plugins restent dans `qml/components` et `qml/views`, comme ceux du Genre Manager, car `Main.qml` charge ces dossiers par import de répertoire. Déplacer ces fichiers n'apporterait rien.
- 2026-10-14 — L'entrée « artists » est retirée de la barre d'activités, comme demandé. Le gestionnaire d'artistes n'a donc plus d'entrée visible même lorsque l'interrupteur est activé ; le retour de cette vue relève de l'étape 112.
- 2026-10-14 — Le bouton Plugins reste dans le code et se masque avec l'interrupteur. Les tests qui ont besoin des plugins activent `PLUGIN_UI_ENABLED` par monkeypatch.
- 2026-10-14 — L'éditeur de tags n'écrit plus dans le catalogue d'artistes. La règle par défaut ne protège aucun nom et n'enregistre aucun choix ; la question « One artist / Several » est donc posée à chaque virgule ou `&`. Le magasin réel relève de l'étape 112.
- 2026-10-14 — La constante `PLUGIN_UI_ENABLED` vit dans `registry.py` : c'est le seul interrupteur. `app.py`, `WorkspaceModel` et `DemoWorkspace` le lisent.
- 2026-10-14 — Le paquet PyInstaller reçoit les deux dossiers `migrations` des plugins dans `packaging/mtee.spec`. Aucun build n'a été lancé, car la demande ne porte pas sur le packaging.

## Progress

- [x] 2026-10-14 — Lire les règles, le registre, la base de données, les migrations 019 à 023, le Genre Manager et les dépendances de l'Artist manager.
- [x] 2026-10-14 — 111.1 : déplacer les quatre scripts de plugin, ajouter `PLUGIN_OWNED_MIGRATIONS`, `migrate_plugin` et `prepare_plugin_schema`, puis brancher les repositories.
- [x] 2026-10-14 — 111.2 : déplacer les modules de l'Artist manager et mettre à jour les imports de `src`, `tests` et `scripts`.
- [x] 2026-10-14 — 111.3 : ajouter l'interrupteur, masquer le bouton Plugins, retirer l'entrée « artists » et normaliser l'activité sauvegardée.
- [x] 2026-10-14 — 111.4 : introduire `ArtistCreditRules`, découpler l'éditeur de tags, conserver la question One/Several et rendre l'analyse indépendante du service d'identification.
- [x] 2026-10-14 — 111.5 : rendre inertes les appels de lien vers un artiste et les lister.
- [x] 2026-10-14 — Adapter les tests de migration, d'import et d'interface ; ajouter `test_plugin_schema.py` et `test_plugins_hidden.py`.
- [x] 2026-10-14 — Vérifier au démarrage, depuis les sources, une base neuve et une base construite jusqu'à 023.
- [x] 2026-10-14 — Comparer les tests unitaires, d'intégration et d'interface, fichier par fichier, avec un worktree temporaire détaché à `a073f1d` ; corriger les régressions propres à cette étape.
- [x] 2026-10-14 — Committer le code et les tests sur la branche de travail (commit local `d32b64d`). Aucun push, aucune fusion dans `main`.

## Outcomes & Retrospective

Résultats observés le 14 octobre 2026, depuis les sources, sur cette machine (Windows 11, Python 3.12.14, PySide6 6.9.3, rendu hors écran). Les fichiers de test sont lancés un par un, car `tests/ui` et plusieurs fichiers d'intégration plantent en bloc sur cette machine.

- Unitaires : tout passe, sauf trois échecs déjà présents au commit de base : `test_conversion_queue.py::test_advanced_settings_cycle_only_available_output_values`, `test_icon_provider.py::test_every_icon_renders_in_the_requested_colour` et `test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`.
- Intégration : passent, dont `test_plugin_schema.py` (7 tests) et `test_database_migrations.py`, `test_genre_manager_upgrade.py`, `test_genre_artist_contributions.py` adaptés. Échecs déjà présents au base : `test_playback_repository.py::test_migration_from_17…` et trois tests de `test_playlist_exchange.py`. `test_mpv_playback.py` se termine par une violation d'accès native au base comme sur la branche.
- Interface : aucune régression de fond observée. Les tests qui dépendaient de l'entrée Artist manager ou des liens d'artistes ont été adaptés : `test_artist_profile_ui.py` (le compte des dossiers de la barre latérale n'est plus vérifié, la vue catalogue l'reste), `test_info_panel_staging.py` (la sauvegarde n'alimente plus le catalogue), `test_player_island_links.py` (plugins activés, plus un test de l'état v0.1), `test_genre_manager_workflow.py` (plugin activé). Ces tests passent sur la branche. Les échecs et plantages restants existent déjà au base (`test_analysis_ui`, `test_browser_navigation`, `test_convert_view`, `test_demo_navigation::test_placeholder_activities_show_coming_later`, `test_incremental_scan_and_scroll`, `test_metadata_editor::test_mixed_selection…`, `test_playback_queue_ui`, `test_player_views`, `test_playlists_ui`, `test_track_drag_98`) ; `test_fullscreen_player_100.py` plante aussi au base, dans un thread de tâche de playlists, à l'arrêt.
- Un plantage natif à l'arrêt, dans le thread d'événements de libmpv, est apparu une fois sur `test_genre_manager_workflow.py` ; les trois relances suivantes ont réussi.
- Démarrage manuel depuis les sources (`.local/verify_111.py`, hors écran) sur une base neuve : aucune entrée « artists » ni « plugins » visible (capture contrôlée), aucune table `artist*`, `track_artist*` ou `gm_*`, `user_version` 18, aucun avertissement QML.
- Démarrage sur une base construite avec les scripts de l'ancienne version jusqu'à 023 et contenant un artiste : `user_version` 23, toutes les tables et la ligne d'artiste conservées, aucun avertissement QML.
- Non vérifié : les essais audibles, le ressenti au pointeur, la recette sur une machine Windows propre et le paquet `dist/MTEE.exe` (aucun build lancé, la demande ne porte pas sur le packaging). Le paquet PyInstaller n'a donc pas été contrôlé avec les nouveaux dossiers `migrations` des plugins.
- Non réalisé : une recette interactive du bouton de la barre d'activités et de la boîte « One artist / Several artists » au pointeur. Les deux sont couverts par les tests d'interface qui passent.
