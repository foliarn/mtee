# Étape 115 — Statistiques d'écoute dans la page Profil

ExecPlan vivant. Suivre `PLANS.md` à la racine. Cette étape affiche les statistiques du journal d'écoute (étape 113) dans la page Profil de l'étape 114, avec des colonnes « Plays » et « Last played » optionnelles dans la liste des morceaux et un bloc « Listening » dans le panneau de détails.

## Objectif et résultat observable

Le profil affiche le temps d'écoute et le nombre de lectures comptées de la période choisie, un graphique du temps d'écoute, et les morceaux et albums les plus joués. La période se choisit parmi **This week** (lundi à dimanche), **This month** (défaut), **This year** et **All time**, en heure locale. Les colonnes « Plays » et « Last played » sont désactivées par défaut ; une fois ajoutées, elles se trient, et le panneau de détails d'un morceau affiche les mêmes deux valeurs.

Hors v0.1 : le récapitulatif annuel « Wrapped », la carte de chaleur heure × jour, et le classement des artistes (étape 112).

## Prérequis et état du dépôt

- Étape 113 livrée : `play_events`, `PlayLogRepository` (`totals`, `top_tracks`, `top_albums`, `daily_listening`, `track_play_stats`, `reset`).
- Étape 114 : page Profil et modèles (voir `114-parametres-et-profil.md`).
- Étape 112 : non fusionnée ; `top_artists()` renvoie une liste vide, marquée `TODO(step 112)`.
- Aucune migration.

## Modifications par zone

Backend (antérieur à cette étape) : `src/mtee/domain/listening_periods.py`, `src/mtee/models/statistics_model.py` (`read_statistics`, `StatisticsModel`), `src/mtee/persistence/play_log_repository.py`.

Cette étape :

- `src/mtee/qml/views/ProfileView.qml` : page réelle (remplace la maquette dans l'application). Sélecteur de période, deux tuiles (« Listening time », « Plays »), graphique, trois classements (« Top tracks », « Top artists », « Top albums »), texte de définition. Le sélecteur démarre sur « This month ».
- `src/mtee/persistence/workspace_repository.py` : colonnes `playCount` (« Plays ») et `lastPlayed` (« Last played ») ajoutées à `COLUMN_OPTIONS`, cachées par défaut. Pour une disposition enregistrée avant ces colonnes, elles restent cachées (règle dans `_validated_column_preferences`).
- `src/mtee/models/workspace_model.py` :
  - `_with_play_stats` ajoute à chaque ligne `playCount`, `lastPlayedNs` et `lastPlayedText` ;
  - les statistiques sont lues dans la tâche qui charge les lignes du dossier, par une requête groupée (`track_play_stats`), seulement si une colonne est visible ou si le tri les utilise ; elles sont lues avant le tri ;
  - `refreshPlayStats()` relit les onglets affichés après une écoute enregistrée ou l'affichage d'une colonne ;
  - `_listening_details` et `infoListening` donnent les lignes « Plays » et « Last played » du morceau sélectionné ;
  - `_sort_rows` trie les deux colonnes (un morceau jamais joué vient en dernier, comme les autres cases vides).
- `src/mtee/domain/play_log.py` : `format_listened_at` (date et heure locales, « — » si aucune écoute).
- `src/mtee/qml/components/TrackRow.qml` : valeurs des deux colonnes (le compteur 0 s'affiche « 0 »).
- `src/mtee/qml/components/InfoPanel.qml` : section « Listening » après « File ».
- `src/mtee/services/player_service.py` : signal `playLogWritten`, émis dans le thread graphique après l'enregistrement réussi d'une écoute.
- `src/mtee/app.py` : `playLogWritten` relit les statistiques (si la tâche accepte encore) et les colonnes.

## Décisions de réalisation

- **Plays** compte les écoutes comptées (30 s, ou fin d'un morceau de moins de 30 s). **Last played** est la date de la dernière écoute, toutes écoutes confondues.
- **Colonnes** : affichées dans le menu « Choose columns » ; cachées par défaut. Les colonnes ne sont pas proposées dans les playlists (`playlistOptions`).
- **Tri** : pris en charge, comme la maquette le montrait ; le tri lit les chiffres après la requête groupée.
- **Panneau de détails** : section « Listening » séparée de « File », car ces valeurs ne sont pas des propriétés du fichier. Lecture synchrone d'un morceau (index `(track_id, started_at_utc)`), très courte.
- **Période** : « This month » par défaut ; statistiques relues à chaque ouverture de la page, après une écoute enregistrée et après une réinitialisation.
- **Graphique** : par jour pour la semaine et le mois, par mois pour l'année et toute la durée. Les libellés sont placés à la position de leur barre.

## Commandes utilisées

    uv run pytest -q -p no:cacheprovider tests/unit/test_listening_periods.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_listening_columns.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_statistics_model.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_profile_and_privacy_models.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_play_log_repository.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_play_log.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_settings_profile_ui.py
    uv run pytest -q -p no:cacheprovider tests/ui/test_column_selection.py
    uv run ruff check <fichiers touchés> ; uv run ruff format --check <fichiers touchés>
    uv run python .local/review_118b.py     (captures hors écran, non versionnées)

## Critères de recette

- Une écoute comptée de 45 s, récente, donne `countedPlays = 1` et `listeningMs = 45 000` pour « This month ». Constaté par `test_the_profile_page_reads_the_real_statistics`.
- Une écoute de plus de deux ans est exclue de « This month » et comptée dans « All time ». Constaté par les tests des périodes (étape 115, antérieure).
- La semaine a sept compartiments. Constaté antérieurement.
- Un résultat d'une demande précédente n'écrase pas la période affichée. Constaté antérieurement.
- Le classement des artistes est vide sans erreur. Constaté.
- Une colonne « Plays » cachée n'entraîne aucune lecture des écoutes ; affichée, elle donne 1 au morceau écouté et 0 aux autres, et « Last played » donne la date locale. Constaté par `test_the_listening_columns_and_details_show_the_play_log` et les tests unitaires.
- Le panneau de détails d'un morceau donne « Plays » et « Last played ». Constaté par test sur la propriété `infoListening` ; la section n'est pas visible sur la capture (voir Outcomes).

## Reprises et idempotence

Les statistiques et les colonnes sont des lectures : une relance recalcule. Une lecture échouée laisse l'état précédent et renseigne `error`. Une tâche refusée à l'arrêt de l'application est ignorée sans erreur.

## Interfaces

    calendar_period(kind: str, now: datetime) -> ListeningPeriod     # week | month | year | all
    listening_buckets(kind, now, daily) -> list[ListeningBucket]
    read_statistics(play_log, kind, now) -> StatisticsSnapshot
    top_artists(period) -> list                                       # TODO(step 112)
    StatisticsModel.setPeriod(kind) ; refresh()
    format_listened_at(instant: datetime | None) -> str
    WorkspaceModel.attach_play_log(repository) ; refreshPlayStats() ; infoListening
    PlayerService.playLogWritten (signal, thread graphique)

## Progress

État au 14 octobre 2026 :

- [x] Périodes calendaires et compartiments du graphique (antérieur).
- [x] Lecture des statistiques et modèle Qt avec tâches de fond (antérieur).
- [x] Page Profil réelle branchée à `statistics` ; période « This month » par défaut ; tuiles « Listening time » et « Plays ».
- [x] Colonnes « Plays » et « Last played », cachées par défaut, triables, lues par requête groupée hors thread graphique.
- [x] Panneau de détails : section « Listening ».
- [x] Mise à jour après écoute enregistrée (signal `playLogWritten`) et après réinitialisation.
- [ ] Classement des artistes réel : dépend de l'étape 112.
- [ ] Revue visuelle à l'écran de la section « Listening » du panneau de détails (capture faite, section hors cadre).

## Surprises & Discoveries

- Le premier regroupement des compartiments écrasait une ligne d'un même jour au lieu de la sommer ; corrigé (antérieur).
- Les colonnes de la liste avaient un format de disposition enregistré qui ne connaissait pas les nouvelles colonnes : elles seraient apparues. La règle de `_validated_column_preferences` les garde cachées pour ces dispositions.
- Une écoute enregistrée pendant l'arrêt n'a plus de tâche possible ; voir les décisions de l'étape 114.
- Le menu des colonnes est une fenêtre séparée, non capturée par une capture de la fenêtre principale.
- Un élément du menu de colonnes (`columnOptions.filter`) n'existe pas en démo ; constat antérieur, voir l'étape 114.

## Decision Log

- 2026-10-14 : la période par défaut est « This month ».
- 2026-10-14 : « Plays » compte les écoutes comptées ; « Last played » ne tient pas compte du comptage.
- 2026-10-14 : le graphique « All time » groupe par mois, les autres périodes par jour.
- 2026-10-14 : le classement des artistes est vide plutôt que recalculé ici.
- 2026-10-14 : **ajout** — le tri par « Plays » et « Last played » est pris en charge (la maquette le montrait ; le brief ne le précisait pas). Choix le plus simple : le tri réutilise la requête groupée déjà faite pour l'affichage.
- 2026-10-14 : **ajout** — colonnes cachées par défaut, y compris pour les dispositions enregistrées avant leur création.
- 2026-10-14 : **ajout** — le panneau de détails affiche « Plays » et « Last played » dans une section « Listening » séparée de « File » (voir étape 114).
- 2026-10-14 : les statistiques passent par `JobService` ; la relecture après écoute est ignorée si l'application ferme.

## Outcomes & Retrospective

Constats observés (commandes réelles, 14 octobre 2026) :

- `test_listening_periods.py` (antérieur) : tests des périodes ; `test_statistics_model.py` et `test_play_log_repository.py`, `test_play_log.py`, `test_profile_and_privacy_models.py` : réussis.
- `test_listening_columns.py` : 8 tests réussis (affichage de « Last played », tri, détails, colonnes cachées par défaut, dispositions anciennes).
- `test_settings_profile_ui.py` : réussi, dont la lecture réelle des statistiques dans l'application (une écoute comptée) et la liste des règles.
- Une revue hors écran (`.local/run-118b-shots/`) : `profile-month`, `profile-week`, `profile-all` et `explorer-play-columns` ; `explorer-details-listening` montre le panneau mais pas la section « Listening », placée sous « File ».
- Totaux de la revue : 32 écoutes comptées sur 40 générées, identiques à la tuile « Plays » de toute la durée.

Limites :

- Les statistiques affichées dans la revue viennent d'écoutes insérées directement dans la base ; le chemin `PlayerService.playLogWritten` n'a pas été rejoué par une vraie lecture audio dans la revue.
- Le classement des artistes reste vide tant que l'étape 112 n'est pas fusionnée.
- Le fuseau horaire de la machine de recette n'a pas été changé pour tester le passage à l'heure d'été.
