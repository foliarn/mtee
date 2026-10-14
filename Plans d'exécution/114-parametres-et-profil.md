# Étape 114 — Paramètres par catégories et page Profil

ExecPlan vivant. Suivre `PLANS.md` à la racine. Cette étape reprend les paramètres de la v0.1 : catégories réelles, suppression des lignes factices, page Profil (nom affiché, avatar), écran Data & privacy (historique, statistiques, sauvegarde et restauration). Les statistiques affichées dans le profil sont décrites dans l'étape 115.

## Objectif et résultat observable

La page Paramètres reste un onglet de l'éditeur, comme aujourd'hui (`Ctrl+,`). Ses pages sont choisies dans la bande d'onglets sous le titre : General, Library, Playback, Analysis, Keyboard shortcuts, Data & privacy, About. La barre latérale de l'application (Explorer et les autres activités) reste visible et inchangée pendant que les paramètres sont ouverts ; il n'y a pas de liste de catégories dans la page. Chaque réglage réel est rangé à une seule place ; les lignes factices (dossiers, apparence, « Remember the queue » sans effet) disparaissent. Le bouton Profil de la barre d'activité ouvre la page Profil, comme un onglet de l'éditeur, avec le nom affiché (qui remplace « Playlist creator name »), un avatar copié dans le dossier de données et les statistiques d'écoute. Data & privacy vide l'historique du panneau History, réinitialise les statistiques, fait une copie cohérente de la base et planifie une restauration appliquée au prochain démarrage ; chaque action destructive demande confirmation.

Changement de disposition demandé après la revue de maquette (message du coordinateur, reçu pendant l'implémentation) : l'utilisateur ne veut pas de barre de catégories à gauche dans la page Paramètres. La maquette `ReviewWindow.qml` présentait une liste de catégories à gauche ; elle n'est pas reprise. La page réelle garde le style actuel de MTEE (en-tête « Preferences » et « Settings », bande d'onglets en capitales, composants `ToggleRow`, `ChoiceRow`, `StepperRow`, `ValueRow`). La page Profil, elle, suit la maquette approuvée.

## Prérequis et état du dépôt

- Base : `main` à `d0f9233` (fusion des étapes 114-115 avec les maquettes). Dernière migration existante : `026_artist_credit_overrides.sql` ; cette étape n'ajoute aucune migration : le profil et l'état de restauration utilisent la table `settings` et des fichiers dans `<données>/profile` et `<données>/restore`.
- Étape 116 (normalisation) : le plafond de pic et le plafond de gain sont modifiés ici (voir Decision Log et `116-normalisation-volume.md`).
- Étape 112 (règles de découpage des artistes) : non fusionnée au moment de cette étape. La section Library montre les règles déjà enregistrées par la vue Artistes ; le classement des artistes du profil reste vide. Une autre branche travaille sur la vue Artistes et `statistics_model.py` ; cette étape n'y touche pas au-delà de l'affichage de `topArtists`.
- `vendor/` est copié dans le worktree ; `.local/` est ignoré par Git.

## Modifications par zone

Backend (commit `136fba3` et `3bf004d`, antérieurs à cette étape) :

- `src/mtee/services/profile_service.py` : nom affiché (`profile/display_name`), avatar copié dans `<données>/profile`, migration unique de `playlists/creator`.
- `src/mtee/services/data_privacy.py` : sauvegarde (`Database.backup_to`), validation, restauration planifiée puis appliquée au démarrage, réinitialisation des statistiques.
- `src/mtee/models/profile_model.py`, `src/mtee/models/data_privacy_model.py` : modèles Qt. Les travaux longs passent par `JobService`.
- `src/mtee/services/player_service.py`, `src/mtee/models/player_model.py` : `clear_history()` vide les 100 entrées du panneau History ; la file et le journal d'écoute restent.
- `src/mtee/persistence/database.py` : `foreign_migration_names()`.

Cette étape (ajouts et remplacements) :

- `src/mtee/qml/views/SettingsView.qml` : remplacé. Même structure que l'ancienne page (titre, bande d'onglets `settingsTabs`, pages chargées par `visible`, composants de ligne existants). Les sept pages sont des onglets de la bande. Aucune barre de catégories. Les contrôles sont branchés aux modèles réels : `workspace.islandEnabled`, `workspace.previewTabs`, `workspace.playbackSettings`, `workspace.analysisSettings`, `artistRules`, `dataPrivacy`, `workspace.playerModel`, `Qt.application.version`.
- `src/mtee/qml/views/ProfileView.qml` : nouvelle page Profil branchée à `profile` et `statistics`. Les figures sont lues à l'ouverture de la page ; une écoute enregistrée et une réinitialisation la relisent.
- `src/mtee/qml/components/ActivityBar.qml`, `SideBar.qml`, `EditorGroup.qml` : le bouton Profil ouvre un onglet ; l'entrée de barre latérale « coming later » et `PlaceholderPane.qml` (plus utilisé) sont retirés.
- `src/mtee/models/workspace_model.py` : pages de paramètres `SETTINGS_PAGES` (sept pages) ; `openProfile()` ; onglet « Profile » ; colonnes Plays et Last played (voir plan 115) ; détails « Listening » (`infoListening`).
- `src/mtee/models/demo_workspace.py` : mêmes pages et `openProfile()` pour que `--demo` continue de démarrer. Le mode démo n'a ni profil, ni statistiques, ni règles, ni actions de données : la page le dit.
- `src/mtee/models/artist_rules_model.py` : nouveau modèle `artistRules` (liste `rules`, `removeRule(key)`, `message`), branché à `ArtistIndexService.overrides()` et `remove_override()`.
- `src/mtee/app.py` : création de `artistRules` ; `playLogWritten` relit les statistiques (`_refresh_after_listening`, seulement si les tâches acceptent encore) et les colonnes ; `dataPrivacy.finished` relit les statistiques.
- `src/mtee/services/data_privacy.py` : `prune_safety_copies` (voir Decision Log).

## Décisions de réalisation

- **Disposition** : onglets dans la page, pas de barre de catégories (voir ci-dessus).
- **General** ne garde que le réglage d'onglets d'aperçu.
- **Playback** : « Show player island » (déplacé ici depuis General) et « Normalize loudness » avec « Loudness target » (Quiet, Normal, Loud).
- **Library** : liste des règles de nom d'artiste (données réelles, bouton « Remove rule ») ; message de confirmation après suppression.
- **Keyboard shortcuts** : liste en lecture seule de dix-sept raccourcis, relevée dans les sources (`Main.qml`, `TrackListView.qml`, `InfoPanel.qml`, `ExplorerPane.qml`) ; la version de la maquette comptait seize entrées, dont « Delete » reformulé.
- **Data & privacy** : chaque action destructive ouvre une boîte de confirmation (Cancel / action). « Clear listening history » vide seulement le panneau History. « Back up database » et « Restore database » utilisent les `FileDialog` de Qt (le même mécanisme que les playlists) ; QML ne lit jamais le disque. Pour la restauration, la boîte de confirmation s'ouvre après le choix du fichier et avant la planification ; la validation du fichier a lieu à la planification (`dataPrivacy.restoreFrom`), comme avant.
- **Restauration** : seules les trois copies `before-restore-*.sqlite3` les plus récentes sont conservées, après une restauration réussie (`prune_safety_copies`, `KEEP_SAFETY_COPIES = 3`). Les autres fichiers du dossier ne sont pas touchés ; une copie qu'on ne peut pas supprimer reste en place.
- **About** : version lue dans `Qt.application.version`, qui vient de `mtee.__version__` (`app.py`) ; licence « GPL-3.0 » comme demandé. Liste des composants tiers reprise de `THIRD_PARTY_NOTICES.md`. Le bouton « Open the full notices » de la maquette n'est pas repris (aucun ouvreur de fichier dans l'application).
- **Remember the queue** : retiré. La file est toujours restaurée au démarrage ; aucun réglage ne peut la désactiver.
- **Profil** : nom vide = « MTEE » dans les playlists et dans l'en-tête. Avatar copié tel quel et affiché en entier (`PreserveAspectFit`), sans recadrage. Seules les deux tuiles « Listening time » et « Plays » sont affichées (plus de « Listening sessions »).
- **Top artists** : liste vide avec le message « Artist ranking is not available yet. » tant que l'étape 112 n'est pas fusionnée.
- **Mode démo** : aucune donnée réelle n'est lue ; la page Profil et les actions de données indiquent qu'elles ne sont pas disponibles.

## Commandes utilisées

Depuis la racine du worktree :

    uv sync --locked
    uv run pytest -q -p no:cacheprovider tests/unit/test_loudness_gain.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_data_privacy.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_listening_columns.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_artist_rules_model.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_settings_profile_ui.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_playback_normalization_ui.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_analysis_ui.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_demo_navigation.py
    uv run ruff check <fichiers touchés> ; uv run ruff format --check <fichiers touchés>
    QT_QPA_PLATFORM=offscreen uv run python -m mtee --demo --data-dir .local/run-118b-demo --smoke-test
    QT_QPA_PLATFORM=offscreen uv run python -m mtee --data-dir .local/run-118b-smoke --smoke-test
    uv run python .local/review_118b.py     (captures hors écran, non versionnées)

## Critères de recette

- Le lancement sur une base neuve (`--data-dir`) et en mode `--demo` sort avec le code 0. Constaté (voir Outcomes).
- Chaque onglet de Settings s'affiche, la barre latérale de l'application reste visible. Constaté par test et capture.
- Une sauvegarde est vérifiée, ne remplace jamais un fichier existant, et ne modifie pas la base en cours. Constaté par les tests du plan (étape 114, antérieure).
- Une restauration n'a aucun effet tant que l'application n'a pas redémarré ; au redémarrage, la base est remplacée, une copie de la base précédente est gardée, et seules les trois dernières copies de sécurité subsistent. Constaté par test d'intégration ; le parcours graphique complet n'a pas été rejoué (voir Limites).
- Un fichier invalide, une base plus récente, ou un historique de migrations inconnu est refusé avant toute planification. Constaté antérieurement.
- Le nom affiché migre une fois depuis `playlists/creator`. Constaté antérieurement.
- L'avatar est une copie : le fichier choisi n'est jamais modifié. Constaté antérieurement ; le choix graphique du fichier n'est pas rejoué.

## Reprises et idempotence

- Une sauvegarde interrompue est supprimée par `Database.backup_to` ; une relance crée un nouveau fichier horodaté.
- La restauration s'écrit en deux temps : copie `pending.sqlite3`, puis marqueur `pending.json`. Sans marqueur, la copie est ignorée et supprimée au démarrage.
- Au démarrage, la copie de sécurité est faite avant tout remplacement ; les fichiers `-wal` et `-shm` de l'ancienne base sont retirés juste avant le renommage atomique. La purge des anciennes copies n'a lieu qu'après ce renommage réussi.
- La migration du créateur est idempotente.

## Interfaces

    ProfileService(settings, profile_dir)
    ProfileService.display_name() -> str ; playlist_creator() -> str
    ProfileService.set_display_name(value) -> str        # ValueError si > 240
    ProfileService.set_avatar(source: Path) -> Path      # ValueError si format ou taille refusés
    ProfileService.avatar_path() -> Path | None ; clear_avatar()

    back_up_database(database, destination) -> Path
    validate_backup(path, *, supported_version, migrations, database_path=None) -> BackupInfo
    stage_restore(source, layout, *, database_path, supported_version, migrations, now) -> PendingRestore
    apply_pending_restore(layout, *, database_path, supported_version, migrations, now) -> RestoreOutcome | None
    prune_safety_copies(layout, *, keep=KEEP_SAFETY_COPIES) -> list[Path]
    cancel_pending_restore(layout) ; read_pending_restore(layout) ; reset_statistics(play_log) -> int

    PlayerService.clear_history() -> int ; PlayerService.playLogWritten (signal, thread graphique)
    PlayerModel.clearHistory() -> int                    # slot Qt
    ProfileModel.setDisplayName(str) ; setAvatarFrom(url) ; clearAvatar()
    DataPrivacyModel.backUpTo(url) ; restoreFrom(url) ; cancelRestore() ; resetStatistics()
    ArtistRulesModel(index: ArtistIndexService) ; rules ; removeRule(key) ; message
    WorkspaceModel.openProfile() ; openSettings() ; setSettingsPageForGroup(group, page)  # pages : SETTINGS_PAGES

## Progress

État au 14 octobre 2026 (réalisé dans le worktree `agent-a5905697ef7e24783`, branche `worktree-agent-a5905697ef7e24783`) :

- [x] Backend : profil, migration du créateur, sauvegarde, restauration planifiée, réinitialisation, vidage de l'historique (commits antérieurs `136fba3`, `3bf004d`).
- [x] Restauration de bout en bout sur une base temporaire (antérieure) et conservation des trois dernières copies de sécurité (test d'intégration de cette étape).
- [x] Settings : sept pages dans l'onglet, sans barre de catégories, avec les composants existants de MTEE.
- [x] Playback : île du lecteur et normalisation (plan 116) ; General ne garde que les onglets d'aperçu.
- [x] Library : règles de nom d'artiste, depuis le magasin réel, avec suppression.
- [x] Keyboard shortcuts : liste lue dans les sources.
- [x] Data & privacy : confirmations, sauvegarde et restauration par `FileDialog`, historique, statistiques.
- [x] About : version, licence GPL-3.0 (demandée), composants tiers.
- [x] Profile : page branchée à `profile` et `statistics`, ouverte par le bouton Profil de la barre d'activité.
- [x] Retrait de « Remember the queue », des lignes factices et de `PlaceholderPane.qml`.
- [x] Tests : nouveaux fichiers et tests mis à jour (voir Outcomes).
- [ ] Revue utilisateur de la version réelle des pages (les captures ci-dessous sont des rendus hors écran, à voir à l'écran).
- [ ] Parcours graphique non rejoué : boîtes de fichiers, restauration, effacement de l'historique sur une vraie écoute.
- [ ] Publication : non demandée, aucun push effectué.

## Surprises & Discoveries

- Une méthode QML (`workspace.settingsPageForGroup(...)`) n'est pas un lien suivi : la page ne se mettait pas à jour au changement d'onglet. Corrigé en relisant la valeur à `layoutChanged`.
- Un signal de stockage d'écoute émis depuis le thread de sauvegarde, relié directement à une fonction Python, aurait tourné dans ce thread. Corrigé : le signal passe par un slot du thread graphique.
- Une écoute enregistrée pendant l'arrêt de l'application demandait une tâche après la fermeture : `RuntimeError`. Corrigé : la relecture des statistiques n'a lieu que si `JobService` accepte encore des tâches.
- Les figures « Plays » et « Last played » des colonnes sont lues dans la tâche de chargement de la liste, une requête groupée. La colonne du panneau de détails passe par une requête indexée sur un morceau (index `(track_id, started_at_utc)`), faite de façon synchrone car elle est très courte ; à surveiller si le panneau est très sollicité.
- L'écran de test de l'historique (`0 of 100 entries`) reste à 0 tant qu'aucune écoute n'a été faite dans la session : le bouton « Clear history » est désactivé dans ce cas, comme prévu.
- Le menu des colonnes est une fenêtre séparée : il n'apparaît pas dans une capture de la fenêtre principale. Non capturé.

## Decision Log

- 2026-10-14, agent : aucune migration. Le profil est dans `settings` ; la restauration est dans `<données>/restore`.
- 2026-10-14 : le créateur des playlists lit la clé du nom affiché ; `PlaylistsModel.setCreator` est conservé.
- 2026-10-14 : « Clear listening history » vide le panneau History (session de lecture), pas le journal d'écoute.
- 2026-10-14 : la restauration est planifiée, puis appliquée au démarrage avant l'ouverture de la base, après une copie de sécurité de la base actuelle.
- 2026-10-14 : **révisé** : les copies de sécurité `before-restore-*.sqlite3` ne sont plus conservées indéfiniment. Après une restauration réussie, seules les trois plus récentes restent (décision demandée par le brief).
- 2026-10-14 : toute sauvegarde est écrite en mode journal `DELETE`, pour être un fichier unique.
- 2026-10-14 : l'avatar est copié octet par octet après validation (format reconnu par Qt, 10 Mo au plus) ; affiché en entier, sans recadrage.
- 2026-10-14 : le nom affiché est vide par défaut ; les playlists affichent « MTEE ».
- 2026-10-14 : les statistiques sont lues par une tâche `JobService` ; chaque demande porte un numéro de génération.
- 2026-10-14 : le classement des artistes renvoie une liste vide, marquée `TODO(step 112)`.
- 2026-10-14 : les modèles `profile`, `statistics`, `dataPrivacy`, `artistRules` sont créés dans `app.py` et exposés en propriétés de contexte ; le mode démo n'en crée aucun.
- 2026-10-14 : **révisé** — disposition des Settings : onglets dans la page, pas de barre de catégories à gauche (demande de l'utilisateur après revue de la maquette, transmise par le coordinateur). La maquette `ReviewWindow.qml` n'est pas reprise pour les paramètres.
- 2026-10-14 : **révisé** — la page Profil reste celle de la maquette, ouverte comme un onglet par le bouton Profil (pas une activité de la barre latérale ; `profile` n'est plus une activité).
- 2026-10-14 : About affiche « GPL-3.0 » comme demandé par le brief. Constat à trancher par l'auteur : `THIRD_PARTY_NOTICES.md` indique qu'aucune licence n'est encore attribuée à MTEE, et `LICENSES/` ne contient pas de texte GPL. Non modifié ici.
- 2026-10-14 : Keyboard shortcuts : dix-sept entrées relevées dans les sources (liste et formulation dans `SettingsView.qml`) ; « Delete » est indiqué « Explorer only » parce que son raccourci n'est actif que dans l'Explorateur.
- 2026-10-14 : la restauration dans le dialogue n'affiche pas le détail de la sauvegarde (nombre de morceaux, version de schéma) : cela demanderait une validation asynchrone avant la confirmation. Le détail reste dans le message après planification.
- 2026-10-14 : attribution du commit. Le brief demandait `Co-Authored-By: Claude Opus 5.5` ; le rappel d'attribution fourni avec la session demande `Claude Haiku 5.5`, qui est le modèle réellement utilisé. Le commit porte la ligne demandée par le brief ; à corriger si nécessaire.

## Outcomes & Retrospective

Constats observés (commandes réelles, 14 octobre 2026, environnement Windows 11, Qt hors écran, base de test) :

- Tests de cette étape, tous réussis : `test_loudness_gain.py` 18 ; `test_data_privacy.py` 15 (dont 3 nouveaux sur la conservation) ; `test_listening_columns.py` 8 (nouveau) ; `test_artist_rules_model.py` 4 (nouveau) ; `test_settings_profile_ui.py` 6 (nouveau, interface réelle et démo) ; `test_playback_normalization_ui.py` ; `test_analysis_ui.py` ; `test_demo_navigation.py` ; `test_demo_scenarios.py` ; `test_plugins_hidden.py` ; `test_column_selection.py` ; `test_info_panel_staging.py` ; `test_info_panel_messages.py` ; `test_player_island_links.py` ; `test_tag_conflicts_ui.py` ; `test_track_list_pointer.py` ; `test_track_hover.py` ; `test_player_service.py` ; `test_player_play_log.py` ; `test_playback_queue.py` ; `test_mpv_gain.py` ; `test_statistics_model.py` ; `test_profile_and_privacy_models.py` ; `test_play_log_repository.py` ; `test_database_migrations.py`.
- Échecs présents aussi sur le commit de base `d0f9233` (vérifié en exportant ce commit dans un dossier séparé, sans toucher au worktree) : `test_player_views.py::test_space_goes_to_search_while_a_track_is_playing` ; `test_browser_navigation.py::test_live_window_indexes_and_navigates_a_nested_folder` ; `test_track_list_column_resize.py` (arrêt par segmentation) ; `test_fullscreen_player_100.py` (sortie avec code 3) ; `test_incremental_scan_and_scroll.py::test_rescan_reuses_unchanged_metadata_and_keeps_track_84_in_view`. `test_workspace_model.py` : l'échec connu `test_navigation_keeps_each_panel_selection_and_restores_it` est le seul échec relevé.
- Non relancés dans cette étape : `test_playlists_ui.py`, `test_metadata_editor.py`, `test_convert_view.py`, les suites d'intégration complètes ; les échecs connus de la liste de base n'ont donc pas été réexaminés.
- Lancement : `--demo --smoke-test` code 0 ; base neuve `--data-dir .local/run-118b-smoke --smoke-test` code 0 ; aucun avertissement QML dans les journaux de la revue hors écran.
- `ruff check` et `ruff format --check` : propres sur les fichiers touchés.
- Captures hors écran (`.local/run-118b-shots/`, non versionnées, données générées dans `.local/run-118b`) : `settings-general`, `settings-library`, `settings-playback`, `settings-analysis`, `settings-shortcuts`, `settings-privacy`, `settings-about`, `settings-privacy-reset-statistics-dialog`, `profile-month`, `profile-week`, `profile-all`, `explorer-play-columns`, `explorer-details-listening`. Chaque capture montre la barre latérale de l'application à gauche. Constat sur la capture de la page Paramètres : la bande d'onglets tient sur une ligne, en capitales, comme dans l'ancienne page. Dans la capture `explorer-details-listening`, la section « Listening » n'est pas visible : elle est sous la section « File », et il faut faire défiler le panneau. Le contenu est vérifié par le test `infoListening`, pas à l'écran.
- Constat sur la capture `explorer-play-columns` : avec le panneau de droite ouvert, les colonnes Plays et Last played sont coupées par la largeur ; la liste défile horizontalement, comportement existant pour les colonnes larges.
- Profil : 32 écoutes comptées sur 40 générées (un sur cinq non comptée) ; la tuile « Plays » et la liste des morceaux concordent avec ce total ; le classement d'artistes affiche le message d'attente.

Limites :

- Non joué à l'écran : les boîtes de choix de fichier (avatar, sauvegarde, restauration), la confirmation « Clear history » (désactivée, aucune écoute dans la session de revue), l'annulation d'une restauration planifiée, la mise à jour du profil après une écoute réelle lue par le lecteur (le chemin `playLogWritten` est câblé mais la revue a inséré les écoutes directement dans la base).
- La restauration de bout en bout (copie de sécurité puis démarrage) reste celle vérifiée antérieurement ; la purge des trois copies est couverte par test d'intégration, pas par un démarrage réel.
- Le paquet Windows n'a pas été construit ni testé (non demandé).
- Licence : voir Decision Log.
- `TrackListView.qml` : `columnOptions.filter` est appelé alors que la démo ne fournit pas ce modèle ; un avertissement apparaît dans les tests de la démo. Constat antérieur, non comparé au commit de base.
