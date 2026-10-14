# Étape 113 — Journal d'écoute permanent (backend, sans interface)

ExecPlan vivant rédigé et réalisé le 2026-10-14. Suivre `PLANS.md` à la racine. Cette étape prépare les statistiques d'écoute de la v0.1 (affichées plus tard dans la page Profil, étape 115). Elle ne livre aucune interface.

## Objectif et résultat observable

Chaque écoute est ajoutée une fois, de façon permanente, dans une table `play_events`. Une écoute dure du début de la lecture audible jusqu'à sa fin ; le temps réellement entendu (`heard_ms`) exclut les pauses, les chargements et les sauts de position. Une écoute compte comme **lecture** dès 30 s entendues, ou jusqu'à la fin pour un morceau plus court que 30 s. Toutes les écoutes sont conservées, y compris les écoutes partielles, afin que le temps d'écoute total soit exact.

Observable depuis les sources : après lecture, pause, reprise, passage au suivant, arrêt et fermeture, la table contient une ligne par écoute, avec les bons temps et le bon indicateur `counted`. Les requêtes de statistiques (totaux, morceaux, albums, jours, nombre de lectures par morceau) répondent à partir de ces lignes. La remise à zéro efface les écoutes et garde l'identifiant de l'installation.

Le journal n'est pas l'historique de 100 entrées du panneau History, qui reste inchangé.

## Prérequis et état du dépôt

- Base : commit `a073f1d` sur la branche `worktree-agent-a7a3c34f7241a5c65`. La dernière migration était `023_genre_artist_decisions.sql`.
- Le contrat `TimeRange` existe déjà (`src/mtee/domain/time.py`) ; le journal utilise des instants `ClockReading` (microsecondes monotones et heure UTC), car le besoin est différent (instant, pas plage audio).
- `vendor/` (libmpv) est copié dans le worktree pour les essais réels ; il reste ignoré par Git.
- Aucune étape précédente n'est requise pour la donnée, mais la page Profil (étape 115) lira les requêtes décrites ici.

## Modifications par zone

Domaine pur, sans Qt ni base : `src/mtee/domain/play_log.py`. Il contient la règle de comptage (`is_counted_play`, seuil `COUNTING_THRESHOLD_US` = 30 s), l'état de l'écoute ouverte (`PlayTracker`), les types `ClockReading`, `PlayedTrack`, `PlayEvent` et `ListeningPeriod`. Le tracker n'appelle jamais une horloge : l'appelant fournit chaque instant.

Migration : `src/mtee/persistence/migrations/024_play_events.sql`. Table `play_events` (une ligne par écoute, `event_id` UUID), trois index (`started_at_utc`, `(track_id, started_at_utc)`, `(album, started_at_utc)`) et un déclencheur qui refuse toute mise à jour (`play_events_append_only`). La seule suppression autorisée est `reset`.

Persistance : `src/mtee/persistence/play_log_repository.py`. Écriture (`insert_events`), requêtes (`totals`, `top_tracks`, `top_albums`, `daily_listening`, `track_play_stats`), remise à zéro (`reset`), et identifiant d'installation (`load_or_create_device_id`, stocké dans la table `settings` sous la clé `play_log.device_id`).

Service : `src/mtee/services/player_service.py`. Les points d'accroche sont décrits dans « Décision Log » et dans le résumé ci-dessous. L'écriture passe par l'exécuteur d'un seul thread déjà utilisé pour la sauvegarde de session ; l'interface n'attend pas l'écriture, sauf à la fermeture.

Câblage : `src/mtee/app.py` appelle `attach_play_log` après `attach_session`, avec l'identifiant d'installation.

Points d'accroche dans le service :
- ouverture d'un morceau (`_open_index`, avant le chargement natif) : elle ferme l'écoute précédente sans complétion, ce qui couvre suivant, précédent, choix dans la file, répétition d'un titre et relecture ;
- `loaded`, `pause` natif, `pause()` et `resume()` : ils commandent l'horloge d'écoute ;
- `seek()` : il accroche l'horloge à l'instant du saut, sans ajouter la portion sautée ;
- `_restart_current()` (Précédent vers le début) : il termine l'écoute courante et en ouvre une nouvelle sur le même morceau ;
- fin de morceau (`_on_eof`) : écoute terminée (`completed=True`) ;
- arrêt (`stop_and_release`), fin de file (`_finish`), erreur (`_fail`) : écoute terminée sans complétion ;
- fermeture (`close`) : l'écoute ouverte est écrite avant l'arrêt du moteur natif.

## Commandes utilisées

Depuis la racine du worktree :

    uv sync --locked
    uv run pytest -p no:cacheprovider tests/unit/test_play_log.py tests/integration/test_play_log_repository.py tests/unit/test_player_play_log.py
    uv run ruff check <fichiers touchés>
    uv run pyright <fichiers touchés>
    uv run python -m mtee --data-dir .local/run-113 --smoke-test

Vérification réelle, depuis les sources, sur des fichiers WAV synthétiques générés dans `.local/run-113-media` (`.local/make_fixtures_113.py`) :

    uv run python -I .local/drive_113.py .local/run-113 .local/run-113-media
    uv run python -I .local/inspect_113.py .local/run-113
    uv run python -I .local/query_113.py .local/run-113

Le dossier `.local/` n'est pas versionné ; la base réelle de l'utilisateur n'a pas été touchée.

## Critères de recette

- Une écoute de 40 s, pausée 3 s et reprise, puis entendue 35 s au total, est comptée et a `heard_ms` proche de 35 000.
- Un morceau de 6 s joué jusqu'à sa fin est compté ; une écoute arrêtée après 2 s ne l'est pas.
- Une fermeture pendant la lecture écrit l'écoute en cours avec le temps entendu jusqu'alors.
- Les requêtes renvoient les mêmes totaux que la somme des lignes.

## Reprises et idempotence

L'écriture est un `INSERT` par écoute, avec un UUID unique : une reprise ne duplique pas une ligne déjà écrite. La migration est transactionnelle comme les autres ; une base déjà à 023 reçoit seulement 024 après sauvegarde. Si l'application s'arrête brutalement, l'écoute ouverte n'est pas écrite (voir Decision Log).

## Interfaces

    PlayTracker.open(track, now, *, playing) -> PlayEvent | None
    PlayTracker.set_playing(playing, now) -> None
    PlayTracker.checkpoint(now) -> None
    PlayTracker.close(now, *, completed) -> PlayEvent | None
    is_counted_play(heard_us, duration_us, completed) -> bool

    PlayLogRepository(database)
    PlayLogRepository.insert_events(events, device_id) -> int
    PlayLogRepository.totals(period=ALL_TIME) -> ListeningTotals
    PlayLogRepository.top_tracks(period=ALL_TIME, limit=50) -> list[TrackRank]
    PlayLogRepository.top_albums(period=ALL_TIME, limit=50) -> list[AlbumRank]
    PlayLogRepository.daily_listening(period=ALL_TIME, *, zone=None) -> list[DailyListening]
    PlayLogRepository.track_play_stats(track_ids, period=ALL_TIME) -> dict[str, TrackPlayStats]
    PlayLogRepository.reset() -> int
    load_or_create_device_id(settings) -> str

    PlayerService(..., clock=None)            # clock: Callable[[], ClockReading], pour les tests
    PlayerService.attach_play_log(repository, device_id)

## Progress

État au 2026-10-14 :

- [x] Lecture de `AGENTS.md`, `PLANS.md` et des fichiers de lecture du lecteur, de la persistance et de l'application.
- [x] Migration `024_play_events.sql` (table, index, déclencheur append-only).
- [x] Règle de comptage et tracker d'écoute purs (`domain/play_log.py`).
- [x] Dépôt : écriture, requêtes, remise à zéro, identifiant d'installation.
- [x] Points d'accroche dans `PlayerService`, horloge injectable, câblage dans `app.py`.
- [x] Tests unitaires du comptage et du tracker sur horloge factice (11 tests).
- [x] Tests du dépôt sur base temporaire, dont le découpage par lots et la fenêtre (9 tests).
- [x] Tests du lecteur avec le faux moteur, sur horloge factice (5 tests), dont une mutation volontaire (voir Outcomes).
- [x] Mise à jour des expectations de version de schéma (23 vers 24) dans les tests de migration.
- [x] Vérification réelle depuis les sources avec libmpv et des WAV synthétiques (voir Outcomes).
- [ ] Interface : hors périmètre de cette étape.
- [ ] Commit et push : commit local sur la branche de travail ; aucun push demandé.

## Surprises & Discoveries

- `tests/integration/test_playback_repository.py::test_migration_from_17_keeps_data_and_creates_consistent_backup` échoue déjà à la base `a073f1d` (il attend la liste `[18, 19, 20, 22]`, alors que la migration 023 existe). Constaté en exportant HEAD dans `.local/base-113` et en lançant le même test : même échec. Non corrigé ici.
- Les échecs suivants existent aussi à la base, à l'identique : `tests/unit/test_conversion_queue.py::test_advanced_settings_cycle_only_available_output_values`, `tests/unit/test_icon_provider.py::test_every_icon_renders_in_the_requested_colour`, `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`, trois tests de `tests/integration/test_playlist_exchange.py` (absence de `Context.report_items`), `tests/ui/test_player_views.py::test_space_goes_to_search_while_a_track_is_playing` (délai), `tests/ui/test_playback_queue_ui.py::test_queue_panel_shows_distinct_upcoming_occurrences`, `tests/ui/test_playlists_ui.py` (deux cas). `tests/ui/test_fullscreen_player_100.py` se termine par une trace de faulthandler à la base comme sur la branche.
- Le test `tests/integration/test_mpv_playback.py` affiche `Windows fatal exception: code 0xe24c4a02` à la base comme sur la branche ; les deux tests passent.
- Lors de la vérification réelle, l'écoute du morceau de 6 s est enregistrée à 5 781 ms, et non 6 000 ms. Cause non vérifiée : la fin de fichier est signalée par libmpv quand le décodage est terminé, alors que la sortie audio peut encore jouer un court tampon. Écart de l'ordre de 0,2 s, sans effet sur la règle de 30 s.
- Une substitution de texte dans l'éditeur a supprimé une espace de fin de ligne dans les tests de migration ; corrigée avant le commit et vérifiée par `ruff format --check`.

## Decision Log

- 2026-10-14, agent Claude (étape 113) : `track_id` est une colonne texte sans clé étrangère vers `tracks`. Les statistiques survivent ainsi à la suppression d'une entrée de bibliothèque, et une future synchronisation n'a pas besoin de la bibliothèque locale.
- 2026-10-14 : une écoute commence au premier instant où le morceau est réellement audible (`loaded` ou reprise), et non à l'ouverture du morceau. Une session restaurée en pause ne crée donc pas une ligne au démarrage.
- 2026-10-14 : une écoute sans temps entendu (chargement échoué, arrêt immédiat) n'est pas écrite. Une écoute qui a été entendue même 1 ms est écrite, avec `counted = 0`.
- 2026-10-14 : temps d'écoute mesuré par l'horloge monotone, par états de lecture (pas par position). Un saut ne peut donc pas ajouter la portion sautée ; `seek()` ferme seulement la portion en cours.
- 2026-10-14 : la fin de l'écoute (`ended_at_utc`) est le début plus la durée écoulée, pauses comprises. Elle reste cohérente même si l'horloge murale change.
- 2026-10-14 : `counted` est calculé à la fermeture. Un morceau de moins de 30 s compte à la fin lue (`completed`), sinon le seuil de 30 s suffit. Un morceau de durée inconnue n'est pas considéré comme court.
- 2026-10-14 : une écriture par écoute, dans l'exécuteur unique de sauvegarde (pas de lot). Suffisant pour le volume d'une session ; la fermeture attend les écritures en cours.
- 2026-10-14 : une écriture en erreur est journalisée au niveau ERROR et n'est pas remontée à l'interface ; le message « Could not save playback session » serait trompeur. Limite connue : une perte silencieuse côté utilisateur est possible jusqu'à une éventuelle interface de contrôle.
- 2026-10-14 : l'écoute ouverte est perdue en cas d'arrêt brutal (crash, coupure). Seule la fermeture normale écrit la ligne en cours ; une écriture périodique aurait ajouté du trafic sans demande explicite.
- 2026-10-14 : horodatages stockés en texte UTC à largeur fixe (`YYYY-MM-DDTHH:MM:SS.ffffffZ`) pour que SQLite compare dans l'ordre chronologique.
- 2026-10-14 : déclencheur `play_events_append_only` qui refuse `UPDATE`. La suppression reste possible, réservée à `reset`.
- 2026-10-14 : `top_tracks` ne retient que les morceaux ayant au moins une lecture comptée ; le tri est lectures comptées, puis temps d'écoute, puis identifiant. Le titre, l'artiste, l'album et le chemin viennent de l'écoute la plus récente.
- 2026-10-14 : `top_albums` regroupe par texte du tag album, sans tenir compte de l'artiste ; les albums vides sont exclus. Un regroupement plus fin relève de l'étape 112 (règles de découpage des artistes).
- 2026-10-14 : `track_play_stats` renvoie `counted_plays` (lectures comptées), `sessions` (toutes les écoutes) et `last_played` (début de la dernière écoute, comptée ou non). Une seule requête par lot de 400 identifiants.
- 2026-10-14 : `daily_listening` regroupe par jour civil local du début de l'écoute (fuseau par défaut de la machine, ou `zone` fourni) ; les jours sans écoute ne sont pas renvoyés. Une écoute qui traverse minuit est attribuée à son jour de départ.
- 2026-10-14 : identifiant d'installation stocké dans `settings` sous `play_log.device_id`, créé une fois, régénéré seulement si la valeur stockée n'est pas un UUID valide.
- 2026-10-14 : aucune interface ; `top_artists` absent, comme demandé (étape 115).
- 2026-10-14 : `tests/integration/test_database_migrations.py` et `tests/integration/test_genre_manager_upgrade.py` : expectations de version mises à 24, car elles pinnaient la version courante. Aucune autre assertion modifiée.

## Outcomes & Retrospective

Constats observés (commandes et résultats réels) :

- Tests unitaires et d'intégration nouveaux : 25 tests (`test_play_log.py` 11, `test_play_log_repository.py` 9, `test_player_play_log.py` 5), tous réussis. Suite précédente du lecteur (`test_player_service.py`, `test_playback_queue.py`, `test_playback_session.py`, `test_mpv_playback.py`) : réussie, sauf les échecs préexistants listés plus haut.
- Mutation contrôlée : désactiver le redémarrage d'écoute dans `_restart_current` fait échouer `test_seek_and_previous_to_start_begin_a_new_listening` (`ValueError: not enough values to unpack`). La modification a été annulée ensuite.
- Ruff (vérification et format) et pyright : aucune erreur sur les fichiers touchés.
- Lancement depuis les sources : `uv run python -m mtee --data-dir .local/run-113 --smoke-test` sort avec le code 0 sur une base neuve (schéma 24).
- Vérification réelle avec libmpv (sortie audio par défaut) et les WAV synthétiques : six actions (lecture 5 s, pause 3 s, reprise 30 s, suivant jusqu'à la fin de B, relecture de A arrêtée après 2 s, lecture de B puis fermeture à 1,5 s). Quatre lignes écrites, toutes avec le même identifiant d'installation et un UUID distinct :
  - A : 35 000 ms, comptée (la pause de 3 s est exclue : écart de début à fin de 38 s) ;
  - B : 5 781 ms, comptée (morceau de 6 s joué jusqu'à la fin) ;
  - A : 2 000 ms, non comptée ;
  - B : 1 500 ms, non comptée (écrite à la fermeture pendant la lecture).
  Les requêtes renvoient des totaux cohérents avec ces lignes (44 281 ms, 2 lectures comptées, 4 écoutes).

Limites, non vérifiées ou hors périmètre :

- L'interface n'a pas été pilotée : la lecture a été commandée par `PlayerService` directement, sans clics dans la fenêtre. Le câblage de `app.py` est exercé seulement par le lancement `--smoke-test`.
- Aucun contrôle sous Windows propre ni dans l'EXE ; aucun build demandé ni lancé.
- Une écoute interrompue par une coupure n'est pas écrite (décision ci-dessus).
- Aucune synchronisation, aucun agrégat par artiste, aucune page de statistiques.
- Les écritures en erreur ne sont visibles que dans les journaux.
