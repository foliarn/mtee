# Étape 115 — Statistiques d'écoute dans la page Profil

ExecPlan vivant. Suivre `PLANS.md` à la racine. Cette étape affiche les statistiques du journal d'écoute (étape 113) dans la page Profil de l'étape 114, avec une colonne « Plays » et une colonne « Last played » optionnelles dans la liste des morceaux et dans les détails.

## Objectif et résultat observable

Le profil affiche le temps d'écoute total, le nombre de lectures, le nombre de sessions d'écoute, les morceaux, artistes et albums les plus joués, et un graphique du temps d'écoute. La période se choisit parmi **This week** (lundi à dimanche), **This month**, **This year** et **All time**, en heure locale. Les colonnes « Plays » et « Last played » peuvent être ajoutées à la liste des morceaux ; elles se retrouvent aussi dans les détails d'un morceau.

Hors v0.1 : le récapitulatif annuel « Wrapped » et la carte de chaleur heure × jour de la semaine ne sont pas construits.

## Prérequis et état du dépôt

- Étape 113 livrée : `play_events`, `PlayLogRepository` (`totals`, `top_tracks`, `top_albums`, `daily_listening`, `track_play_stats`, `reset`).
- Étape 114 : backend du profil et de la maquette (voir `Plans d'exécution/114-parametres-et-profil.md`).
- Étape 112 : règles de découpage des artistes, non fusionnée. Le classement des artistes reste vide tant qu'elle n'est pas fusionnée.
- Aucune migration n'est ajoutée ; `027` n'est pas utilisé.

## Modifications par zone

Backend, commité avec l'étape 114 (`136fba3`) :

- `src/mtee/domain/listening_periods.py` : périodes calendaires en heure locale (semaine à partir du lundi), compartiments du graphique (jour pour semaine et mois, mois pour année et toute la durée).
- `src/mtee/models/statistics_model.py` : fonction `read_statistics` (un seul passage pour la période), modèle Qt `StatisticsModel` (propriétés `period`, `periodLabel`, `loading`, `listeningMs`, `countedPlays`, `sessions`, `topTracks`, `topAlbums`, `topArtists`, `series`), calculs en tâche de fond, résultats périmés ignorés.
- `top_artists()` renvoie une liste vide, marquée `TODO(step 112)`.

Maquette, à revoir avec l'étape 114 :

- Profil avec le sélecteur de période, trois indicateurs, le graphique et les trois classements (`src/mtee/qml/prototypes/settings_profile_114/ReviewWindow.qml`).
- Explorateur avec les colonnes optionnelles et le menu « Columns » (même fichier).

Restant, après revue :

- Branchement du modèle `statistics` dans la page Profil réelle.
- Colonnes « Plays » et « Last played » dans `TrackListView` et `TrackRow` (détails) : nouvelles colonnes lues depuis `PlayLogRepository.track_play_stats`.
- Remplacement du classement des artistes vide par la vraie liste, à l'étape 112.

## Commandes utilisées

    uv run pytest -q -p no:cacheprovider tests/unit/test_listening_periods.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_statistics_model.py
    uv run pytest -q -p no:cacheprovider tests/unit/test_play_log.py
    uv run pytest -q -p no:cacheprovider tests/integration/test_play_log_repository.py
    uv run ruff check <fichiers touchés>
    uv run pyright src/mtee/domain/listening_periods.py src/mtee/models/statistics_model.py

    uv run python scripts/review_settings_profile_114.py --view profile --period all --data-dir .local/validation/114/review

## Critères de recette

- Une écoute de 35 s (comptée) et une écoute de 2 s (non comptée), toutes deux récentes, donnent `sessions = 2`, `listeningMs = 37 000` et `countedPlays = 1` pour « This week » et « This month ».
- Une écoute de plus de deux ans est exclue de ces périodes et comptée dans « All time ».
- La semaine a exactement sept compartiments, dont les jours sans écoute, et leur somme égale le temps total de la période.
- Un résultat d'une demande précédente n'écrase pas la période affichée.
- Le classement des artistes est vide sans erreur.

## Reprises et idempotence

Les statistiques sont des lectures : une relance recalcule la période. Une lecture échouée laisse l'état précédent et renseigne `error` ; la période choisie reste active.

## Interfaces

    calendar_period(kind: str, now: datetime) -> ListeningPeriod     # kind: week | month | year | all
    listening_buckets(kind, now, daily) -> list[ListeningBucket]
    read_statistics(play_log, kind, now) -> StatisticsSnapshot
    top_artists(period) -> list                                       # TODO(step 112)
    StatisticsModel(play_log, jobs, parent=None, *, clock=None)
    StatisticsModel.setPeriod(kind) ; refresh()

## Progress

État au 14 octobre 2026 :

- [x] Périodes calendaires et compartiments du graphique (`domain/listening_periods.py`), 10 tests.
- [x] Fonction de lecture des statistiques et modèle Qt avec tâches de fond, 5 tests.
- [x] Maquette du profil (sélecteur, indicateurs, graphique, classements) et des colonnes optionnelles, dans la revue 114-115.
- [ ] Colonnes « Plays » et « Last played » dans la liste réelle et dans les détails : après revue.
- [ ] Branchement dans la page Profil réelle : après revue.
- [ ] Classement des artistes réel : dépend de l'étape 112.

## Surprises & Discoveries

- Le premier passage de regroupement des compartiments écrasait une ligne d'un même jour au lieu de la sommer : le test de la semaine avec deux lignes du même jour l'a montré (2 500 + 500 ms attendus, soit 3 000 ; 500 ms lus). Le dépôt ne renvoie qu'une ligne par jour, mais la fonction ne doit pas en dépendre ; corrigé en sommant par clé.
- Les graphiques de toute la durée affichaient trente-quatre libellés de mois qui se chevauchaient. Les libellés sont désormais placés à la position de leur barre, un sur six ; le format est court (« Jan '24 »).
- Le fuseau local est obtenu par `datetime(...).astimezone()` sur une date naïve : Python applique le décalage de cette date, donc l'heure d'été est respectée. Les tests calculent leurs bornes de la même façon, ce qui ne prouve que la cohérence, pas le fuseau de la machine de recette.

## Decision Log

- 2026-10-14, agent Claude : la période par défaut est « This month ». À confirmer à la revue.
- 2026-10-14 : « Plays » compte les écoutes comptées ; « Listening sessions » compte toutes les écoutes. Libellés à confirmer à la revue.
- 2026-10-14 : le graphique « All time » groupe par mois, les autres périodes par jour. Motif : trente-quatre mois de barres journalières seraient illisibles.
- 2026-10-14 : le classement des artistes est vide plutôt que recalculé ici : l'étape 112 apporte les règles de découpage.
- 2026-10-14 : les statistiques passent par `JobService` (pas de thread ad hoc) ; l'état reste sur le thread graphique.

## Outcomes & Retrospective

Constats observés (commandes réelles, 14 octobre 2026) :

- `test_listening_periods.py` : 10 tests réussis (semaine à partir du lundi, dimanche, décembre, toute la durée, valeurs invalides, compartiments de la semaine, du mois, de l'année et de toute la durée).
- `test_statistics_model.py` : 5 tests réussis (périodes et totaux sur une base temporaire, classement vide, période inconnue refusée, modèle via tâche en ligne, résultat périmé ignoré).
- `test_play_log.py` (11) et `test_play_log_repository.py` (9) réussissent, sans modification.
- Maquette : captures du profil par semaine, mois et toute la durée, et du profil étroit (1100 × 760) sans débordement visible (`docs/ux/review-114-115-parametres-profil-stats/`).

Limites :

- Les classements et le graphique affichés dans la maquette sont fictifs ; les totaux de la maquette ne sont pas calculés à partir d'écoutes réelles.
- Le fuseau horaire de la machine de recette n'a pas été changé pour tester le passage à l'heure d'été.
- Les colonnes dans la vraie liste de morceaux ne sont pas encore construites.
