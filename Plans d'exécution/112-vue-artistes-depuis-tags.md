# Étape 112 — Vue Artistes du cœur, construite depuis les tags

ExecPlan rédigé le 14 octobre 2026 selon [PLANS.md](../PLANS.md). Référence produit : [PLAN.md](../PLAN.md). Il s'appuie sur l'étape [111](111-retrait-managers-du-coeur.md), qui retire l'Artist manager du cœur, et prépare la v0.1 sans plugins.

## Objectif et résultat observable

La v0.1 remplace l'Artist manager par une vue Artistes en lecture seule, calculée à partir du tag **Artist** des fichiers. Le tag Album Artist est ignoré, et les titres ne créditent aucun remixer. La liste des artistes compte les pistes de chacun ; une page montre les pistes d'un artiste, avec Play et Shuffle. Deux actions de correction, « This is one artist » et « Split into separate artists », sont stockées dans le cœur (pas dans les tables d'un plugin). Elles sont aussi proposées par la question « One artist / Several artists » de l'éditeur de tags, qui écrit dans le même magasin.

Cette étape livre le cœur fonctionnel (règles, migration 026, index, modèles Qt, branchement de l'éditeur de tags) et une maquette QML isolée. La vue réelle n'est branchée ni dans `Main.qml`, ni dans la barre d'activités, et les liens vers un artiste restent inertes : cela attend la validation de la maquette par l'utilisateur.

## Prérequis et état du dépôt

L'étape part de `main` au commit `30b6a6d` (fusion de l'étape 111). Le worktree de travail est `worktree-agent-a62047c0522820ba6`. Le répertoire `vendor/` n'est pas versionné ; `uv sync` a suffi aux tests de cette étape. Les migrations du cœur vont jusqu'à 025 avant l'étape ; la 026 est ajoutée ici. Les numéros 019, 020, 022 et 023 restent propres aux plugins.

## Règles de découpage (domaine pur)

Le module `src/mtee/domain/artist_index.py` contient les règles, sans accès à la base. Une credit est une valeur du tag Artist. Le découpage se fait en trois passes.

1. **Séparateurs forts** : une virgule, `feat.`, `feat`, `ft.` ou `ft` (sans tenir compte de la casse, mot entier) coupe toujours. Les espaces autour sont retirés. Un nom protégé par un choix « This is one artist » n'est jamais coupé à l'intérieur ; le nom le plus long gagne, et seulement lorsqu'il occupe un segment complet.
2. **Jonctions** : `&` (espaces obligatoires de chaque côté) et `x` ou `X` (un espace de chaque côté). Pour chaque jonction, dans l'ordre, les deux noms adjacents tels qu'ils sont découpés à ce stade sont comparés à l'ensemble des **artistes seuls** (`solo_artist_keys`). La jonction est coupée si **au moins un** des deux côtés est seul. Avec trois noms, chaque jonction est décidée séparément : « Chase & Status & Camo » avec « Chase » seul donne « Chase » puis « Status & Camo ». Un segment marqué « split » est coupé à toutes ses jonctions.
3. **Artiste seul** : une piste dont le tag Artist contient exactement une valeur sans séparateur rend ce nom « seul ». Une piste à deux valeurs ne rend aucun nom seul.

Les noms sont comparés avec `normalize_key` (casse et espaces ignorées). Les noms affichés sont choisis par `choose_spelling` parmi les graphies observées.

## Modifications par sous-étape

### 112.1 — Domaine, stockage et index

- `src/mtee/domain/artist_index.py` : règles, `ArtistEntry` (clé, nom, nombre de pistes, segments d'origine), `ArtistIndex` (artistes triés, pistes par artiste, artistes par piste, ensemble des noms seuls), `build_artist_index`, et les deux méthodes `one_artist_credits(key)` et `split_credits(key)` qui indiquent quels crédits une action touche.
- `src/mtee/persistence/migrations/026_artist_credit_overrides.sql` : table `credit_overrides` (`credit_key` clé primaire, `credit_text`, `mode` limité à `one_artist` ou `split`, `updated_at_utc`). Le nom de la table n'a pas le préfixe « artist » : le test de schéma du plugin interdit toute table `artist*` dans une base neuve (voir les découvertes).
- `src/mtee/persistence/credit_override_repository.py` : `set_mode`, `remove`, `modes`, `all`.
- `src/mtee/persistence/library_repository.py` : `artist_credit_rows()` lit `(track_id, valeurs du tag Artist)` pour les pistes présentes dans une racine.
- `src/mtee/services/artist_index_service.py` : `ArtistIndexService`, un `QObject` qui reconstruit l'index dans un travail en arrière-plan. Une demande pendant un calcul marque l'index périmé ; un seul recalcul suivant est lancé. Le signal `indexChanged` est émis sur le thread graphique. Il expose aussi la liste et la suppression des choix (`overrides`, `remove_override`), et implémente le Protocol de l'éditeur de tags.
- `src/mtee/models/artist_index_model.py` : `ArtistListModel` (liste filtrable, `count`, `totalCount`, `rowForKey`) et `ArtistPageModel` (pistes d'un artiste chargées par job, `oneArtistCredits`, `splitCredits`, `makeOneArtist()`, `splitArtist()`). Ces modèles ne sont branchés à aucun QML réel.

### 112.2 — Éditeur de tags

- `src/mtee/services/artist_credit_rules.py` : le Protocol `ArtistCreditRules` a pour méthodes `split(text)`, `needs_choice(text)`, `suggestions(query, limit)` et `record_credit_choice(text, one_artist=...)`. `protected_names()` disparaît, car les choix sont désormais des crédits entiers. `NoArtistCreditRules` garde un comportement sans index : virgule et `feat.` coupent, `&` et `x` ne coupent pas, et la question est posée pour tout séparateur.
- `src/mtee/models/metadata_editor_model.py` : la découpe, les puces de l'éditeur et le résumé passent par `split`. Nouveau slot `creditNeedsChoice(text)`.
- `src/mtee/qml/components/ArtistField.qml` : la question « One artist / Several artists » est posée lorsque `creditNeedsChoice` est vrai ; sinon chaque partie est ajoutée telle quelle.
- `src/mtee/app.py` : `ArtistIndexService` est construit une fois, passé à l'éditeur comme règles, rafraîchi au démarrage, à chaque `libraryChanged` et à chaque `scanFinished`.

### 112.3 — Maquette isolée

- `src/mtee/prototypes/artists_112.py` : modèle jetable sur 19 pistes fictives. Il appelle les vraies fonctions du domaine, n'ouvre aucune base et n'écrit aucune étiquette.
- `src/mtee/qml/prototypes/artists_112/ReviewWindow.qml` : fenêtre autonome avec barre d'activités, volet Artists (recherche, compteur, liste), page d'artiste (Play, Shuffle, actions en menu ou en boutons), liste des pistes et pied de page.
- `scripts/review_artists_112.py` : lanceur, avec `--scenario`, `--variant`, `--open-menu`, `--size`, `--capture`, `--smoke-test`.
- `docs/ux/review-112-artistes.md` : revue en français, points à trancher et parcours. Captures `docs/ux/review-112-artistes-*.png`.

## Vue réelle, liens et tops artistes (sous-étapes 112.4 à 112.6)

Résultat observable en v0.1, plugins désactivés : l'activité **Artists** (icône micro, après Tasks) affiche un volet avec la recherche « Search artists », le compteur « N artists » et la liste alphabétique avec le nombre de pistes. Un clic ouvre la page de l'artiste comme onglet d'éditeur : pochette (artwork de la première piste dans l'ordre de la page), « Artist », le nom, « N tracks · from “…” », Play, Shuffle et le menu « … » qui contient « This is one artist » et « Split into separate artists ». Les pistes sont listées avec les colonnes et comportements de la table existante (double-clic, sélection, menu contextuel).

Le volet et la page reposent sur `WorkspaceModel.artistList`, `artistInfo(key)`, `makeArtistOneArtist(key)`, `splitArtist(key)`, `openArtistPage(key, name)`, `playArtistRows` et `trackArtists`, tous adossés à `ArtistIndexService` (et non au plugin). Les liens du lecteur (`PlayerIsland.qml`), du plein écran, de l'historique, de la file et du menu « … » de lecture passent par `revealTrack`, `revealTrackForEdit`, `openPlayingSource` et `trackArtists` : leur code QML n'a pas changé, seul le côté Python a été branché sur le cœur.

### Décisions de comportement

- Ordre des pistes d'une page : album, puis numéro de piste (premier nombre de la balise, « 3/12 » vaut 3, un numéro absent va en fin), puis titre. Le tri par défaut d'un onglet artiste est `index` croissant, qui vaut cet ordre ; un tri par colonne reste possible. Fonction partagée : `album_track_order` (domaine), utilisée aussi par `ArtistPageModel`.
- Action « This is one artist » ou « Split » : l'action s'applique aux crédits affichés (`artistInfo`), puis la reconstruction de l'index est asynchrone. Au retour de cette reconstruction, si l'artiste de la page n'existe plus, le premier artiste de l'index qui détient un des crédits touchés est ouvert ; les autres restent dans le volet. Si l'artiste existe encore, la page reste ouverte et se recharge si ses pistes ont changé. Exemple : « This is one artist » sur « Status » ouvre « Chase & Status » ; « Split » sur « Camo & Krooked » ouvre « Camo » et laisse « Krooked » dans la liste.
- Un onglet d'artiste dont l'artiste disparaît (retouche de tags, scan) est fermé. Les autres onglets d'artistes ne se rechargent que si la liste de leurs pistes a changé.
- Le sous-titre « from “…” » reprend les crédits dont l'artiste a été détaché (`oneArtistCredits`), comme dans la maquette.
- Onglets d'artistes au démarrage : non restaurés. `_restore_groups` ne garde que les dossiers et playlists, comme avant ; test `test_artists_session.py`.
- Le titre d'un onglet est le nom tel qu'orthographié par l'index (`choose_spelling`).
- Plugin : les pages du plugin (`openArtistPage` avec un identifiant inconnu du cœur mais connu du plugin, `isPluginArtistPage`) gardent leur en-tête `ArtistHeader.qml` et leur chemin d'origine, uniquement lorsque le plugin est attaché (interrupteur de plugin). En v0.1 aucun chemin n'y mène.

### Tops artistes (112.6)

- `read_statistics` reçoit des `CreditRules` (solo, choix « un artiste », choix « découper »), obtenues par `ArtistIndexService.rules()` sur le thread graphique au moment du rafraîchissement. La découpe passe par `CreditRules.split`, qui appelle `split_artist_credit` : aucun algorithme dupliqué.
- Le journal donne le texte d'artiste de chaque événement (`PlayLogRepository.artist_texts`, regroupé par texte, sans découpe en SQL). Chaque texte est découpé ; un artiste reçoit les lectures comptées et le temps écouté de chaque texte qui le nomme, une fois par texte. Classement : lectures comptées décroissantes, puis temps écouté, puis nom. Limite `TOP_LIMIT` (10). Les événements sans artiste sont ignorés.
- `StatisticsModel.followArtistRules` ne relance un comptage que si les règles ont changé depuis le dernier comptage, et seulement si les travaux sont acceptés (sinon une reconstruction terminée pendant l'arrêt lève une erreur).

### Fichiers

- Domaine : `src/mtee/domain/artist_index.py` (`CreditRules`, `album_track_order`, `ArtistIndex.entries`).
- Services : `src/mtee/services/artist_index_service.py` (`rules()`, garde contre l'auto-relance, `split` passe par les règles).
- Persistance : `src/mtee/persistence/play_log_repository.py` (`artist_texts`, `ArtistTextPlays`) ; `persistence/workspace_repository.py` (activité « artists » acceptée).
- Modèles : `src/mtee/models/workspace_model.py` (cœur des artistes : attachement, `artistList`, `artistRevision`, `artistInfo`, actions, `_on_artist_index_changed`, chemins de lecture et de révélation), `models/statistics_model.py` (`top_artists`, `followArtistRules`), `models/artist_index_model.py` (ordre de page), `models/demo_workspace.py` (activité présente, sans volet réel).
- Démarrage : `src/mtee/app.py` (index créé avant les statistiques, `attach_artist_index`, `indexChanged` relié à `followArtistRules`).
- QML : `components/ArtistsPane.qml` (nouveau), `components/ArtistPageHeader.qml` (nouveau), `components/ActivityBar.qml`, `components/SideBar.qml`, `components/TrackListView.qml` (deux lignes : en-tête du cœur ou du plugin).
- Tests : `tests/ui/test_artists_view.py`, `tests/ui/test_artists_session.py`, `tests/ui/artists_support.py` (nouveaux) ; `tests/ui/test_player_island_links.py` (seed sur les étiquettes Artist, mode v0.1) ; `tests/integration/test_statistics_model.py`, `tests/integration/test_artist_index_service.py`, `tests/unit/test_artist_index.py`.
- Vérification : `scripts/validate_artists_112_view.py` (nouveau).

## Commandes et contrôles

Exécutées depuis la racine du worktree.

    uv sync
    uv run pytest -q tests/unit/test_artist_index.py
    uv run pytest -q tests/unit/test_artists_112_prototype.py
    uv run pytest -q tests/unit/test_metadata_editor_staging.py
    uv run pytest -q tests/integration/test_artist_index_service.py
    uv run pytest -q tests/integration/test_database_migrations.py
    uv run pytest -q tests/integration/test_genre_manager_upgrade.py
    uv run pytest -q tests/integration/test_plugin_schema.py
    uv run pytest -q tests/integration/test_track_loudness.py
    uv run pytest -q tests/ui/test_info_panel_staging.py
    uv run python -m mtee --data-dir .local/run-112 --smoke-test
    uv run python scripts/review_artists_112.py --scenario selected --smoke-test
    uv run pytest -q tests/unit/test_artist_index.py
    uv run pytest -q tests/integration/test_artist_index_service.py
    uv run pytest -q tests/integration/test_statistics_model.py
    uv run pytest -q tests/ui/test_artists_view.py
    uv run pytest -q tests/ui/test_artists_session.py
    uv run pytest -q tests/ui/test_player_island_links.py
    uv run pytest -q tests/ui/test_artist_profile_ui.py
    uv run python scripts/validate_artists_112_view.py

Chaque fichier de test est lancé dans son propre processus. Les mesures de performance utilisent un script local (`.local/measure_112.py`, non versionné).

## Critères de recette

- Une base neuve a le schéma 26 et aucune table commençant par `artist`, `track_artist` ou `gm_`.
- Les exemples de la règle (Chase & Status, Camo & Krooked, T & Sugah, Sub Focus & Wilkinson, feat./ft., virgules, trois noms, « This is one artist », « Split into separate artists », casse et espaces, remixer dans un titre) sont couverts par des tests unitaires.
- Les choix survivent à un redémarrage et ne modifient aucun tag.
- L'index d'environ 3 000 pistes se calcule hors du thread graphique en moins de quelques centaines de millisecondes.
- L'éditeur de tags pose la question pour une virgule ou un `&` sans réponse, et écrit la réponse dans le magasin du cœur.
- La maquette s'ouvre hors écran sans avertissement QML dans les scénarios capturés.

## Surprises & Discoveries

- Le test `test_plugin_schema.py` interdit toute table commençant par `artist` dans une base neuve. La table est donc nommée `credit_overrides`, bien que le fichier soit `026_artist_credit_overrides.sql`.
- L'éditeur de tags ne découpait que sur la virgule et le `&` ; sans la règle des artistes seuls, « Chase & Status » était déjà coupé. Le découpage de l'éditeur et celui de la vue utilisent désormais la même fonction.
- Une valeur de tag enregistrée par l'éditeur est une chaîne unique (« Bou, Nikita, the Wicked »). Un choix « This is one artist » doit donc protéger un segment à l'intérieur de la valeur, et non la valeur entière. C'est ce que fait `_strong_segments`.
- Les chemins de l'espace de travail qui suivent un artiste (`trackArtists`, `openArtistPage`, `openArtistView`, `playArtistRows`, `revealTrack` avec `artist:`, `openPlayingSource`, `_artist_rows`) dépendent encore de `self._artist_manager`, donc du plugin. Les rebrancher exige de les réécrire sur `ArtistIndexService` ; il ne suffit pas de réactiver le plugin.
- Le test `tests/ui/test_metadata_editor.py::test_mixed_selection_saves_supported_files_and_reports_the_rest` échoue aussi sur `main` (`30b6a6d`). Constat vérifié avec une copie de l'archive du commit de base, lancée dans son propre répertoire.
- Mesure locale (3 000 pistes synthétiques, 1 590 artistes) : lecture des étiquettes environ 70 ms, calcul de l'index environ 120 ms, sur cette machine.
- **Boucle de reconstruction de l'index, présente sur `main`.** `ConversionQueueModel._on_job_submitted` émet `changed` pour toute tâche soumise, même sans rapport avec la conversion ; `attach_conversion_model` relie ce signal à `libraryChanged`, et `libraryChanged` relance `ArtistIndexService.refresh`, qui soumet une tâche, donc une nouvelle émission. Constat : 339 `libraryChanged` en 4 s et aucune reconstruction terminée (la tâche « Index artists » reste « running » ; le même schéma apparaît sur une copie de `HEAD`). Correction locale : `refresh()` ignore la notification provoquée par sa propre soumission (drapeau `_submitting`), test `test_a_build_does_not_restart_on_its_own_submission`. La cause racine (`_on_job_submitted`) n'est pas corrigée ici : elle relève de la file de conversion.
- **Boucle de rafraîchissement des rôles et des statistiques.** Deux autres retours vers la même boucle ont été écartés : recharger tous les onglets d'artistes à chaque reconstruction (un chargement est une tâche, donc un changement de bibliothèque), et recalculer les statistiques à chaque reconstruction. Le premier ne recharge désormais que les onglets dont la liste de pistes a changé ; le second ne recalcule que si les règles changent (`followArtistRules`).
- `QTest.qWait` garde le verrou d'interpréteur : les threads de travail avancent à peine et la reconstruction de l'index ne finit pas. Attendre avec `QCoreApplication.processEvents()` et un court `time.sleep(0.01)` la fait finir en environ 0,17 s (mesure). Les helpers de test utilisent cette forme.
- **Abandons natifs avec plusieurs runtimes dans un processus.** Un fournisseur d'images (`ArtworkProvider`) ou un scan lit la base pendant sa fermeture : `Fatal Python error: Aborted` ou `access violation`, selon le moment. Constaté aussi sur `HEAD` : `tests/ui/test_player_island_links.py` passe une fois sur deux sur la copie HEAD, et `tests/ui/test_fullscreen_player_100.py` s'arrête après 15 tests sur la copie HEAD. Mitigation retenue pour les fichiers de cette étape : un seul runtime par fichier de test (fixture de module), arrêt qui attend les travaux et les pochettes, puis fermeture. Résultat : `tests/ui/test_artists_view.py`, `tests/ui/test_artists_session.py` et `tests/ui/test_player_island_links.py` passent trois fois sur trois avec cette forme ; la forme précédente (un runtime par test) abandonnait une fois sur deux à trois. La cause de fond (threads de travail qui lisent une base fermée) reste dans l'application et n'est pas corrigée ici.
- `QObject.findChild` ne trouve pas les `AppMenuItem` d'un `Menu` tant qu'il n'est pas ouvert ; l'état `enabled` du menu « … » est donc vérifié sur les faits qu'il lie (`artistInfo`).
- PySide ne convertit pas `Image.status` (`Can't find converter for 'QQuickImageBase::Status'`) : l'attente des pochettes utilise `progress` et `source`, ou un court délai (retenu).
- Rendu hors écran : l'ombre et le masque de pochette (`MultiEffect`) ne s'affichent pas dans les captures, comme pour l'en-tête de playlist (note de mémoire). La source d'image est pourtant bien `image://artwork/…`.
- La consigne cite `_source_label` : cette fonction n'existe pas. Le titre de source des lectures d'artiste est établi par `_playback_source_title`, qui est celle modifiée.
- Des messages `Cannot read property 'demoMode' of null` (et `applicationVersion`, `maximizeHovered`) apparaissent au démontage de la fenêtre : constatés aussi sur `HEAD` avec `scripts/validate_artist_manager_104.py`, non liés à cette étape.

## Decision Log

- 2026-10-14 — Règle « au moins un côté seul » pour `&` et `x`, lecture littérale de la règle validée par l'utilisateur. L'exemple « Sub Focus & Wilkinson » semble suggérer « les deux côtés » ; à confirmer dans la revue (point 1). Le changement est local à `_cut_junctions`.
- 2026-10-14 — Les choix se stockent par crédit entier normalisé (`normalize_key`). Une action de page agit sur les segments d'origine de l'artiste : « This is one artist » vaut pour les segments dont le nom est issu d'une découpe ; « Split » vaut pour un nom contenant lui-même un séparateur.
- 2026-10-14 — Une question « One artist / Several » reste posée pour toute saisie contenant une virgule, `feat.`, `&` ou `x` sans réponse enregistrée (comportement de l'étape 111 conservé, car la réponse est désormais utile à la vue).
- 2026-10-14 — L'index est rafraîchi au démarrage, puis à chaque `libraryChanged` et `scanFinished`. Les demandes multiples sont fusionnées : une seule reconstruction supplémentaire au plus pendant un calcul.
- 2026-10-14 — Les règles par défaut (`NoArtistCreditRules`) restent disponibles pour les tests et les contextes sans index ; `app.py` passe toujours le service du cœur.
- 2026-10-14 — La maquette n'utilise ni base ni tag. Play et Shuffle ne lisent rien. La variante « menu » est affichée par défaut ; la variante « inline » est fournie pour comparaison.
- 2026-10-14 — L'entrée Artists n'est pas ajoutée à `ActivityBar.qml` ni à `Main.qml` avant la validation de la maquette, comme prévu par le plan.
- 2026-10-14 — Trace d'attribution : le commit est signé par le modèle exécutant (Claude Haiku 5.5) selon la consigne système, et non par la mention Opus indiquée dans la consigne de travail.
- 2026-10-14 — Vue réelle : l'entrée Artists est ajoutée à `ActivityBar.qml` après Tasks, comme dans la maquette ; la maquette, sa barre d'état et « Reset choices » ne sont pas reprises. Les actions sont dans le menu « … » uniquement.
- 2026-10-14 — Après une action qui fait disparaître l'artiste de la page, le premier artiste produit est ouvert (ordre alphabétique de l'index) ; les autres restent dans le volet. Si l'artiste existe encore, la page ne change pas. Comportement à confirmer à la recette.
- 2026-10-14 — Ordre des pistes d'une page : album, numéro de piste, titre (tie-break sur l'identifiant). Un tri par colonne de la table reste disponible.
- 2026-10-14 — Pochette d'une page : artwork de la première piste dans cet ordre (solution simple demandée par la consigne), sans édition de pochette.
- 2026-10-14 — Recherche du volet : sous-chaîne sur le nom seulement (maquette).
- 2026-10-14 — Onglets d'artistes non restaurés au démarrage (filtre existant de `_restore_groups`).
- 2026-10-14 — Le plugin garde ses propres pages (`ArtistHeader.qml`, `isPluginArtistPage`) lorsqu'il est attaché et que l'identifiant n'est pas un artiste du cœur ; en v0.1 aucun chemin ne l'atteint. Le test plugin `tests/ui/test_artist_profile_ui.py` passe sans changement.
- 2026-10-14 — Tests des liens du lecteur : le seed passe des tables du plugin aux étiquettes Artist (l'index du cœur ne voit que les étiquettes) ; `Charlie`, sans artiste, affiche désormais « Unknown artist ». Les tests tournent en mode v0.1 (plugins désactivés) ; le test « texte brut sans liens en v0.1 » devient « les liens viennent de l'index du cœur sans plugin ».
- 2026-10-14 — Tops artistes : texte d'artiste du journal, découpé à chaque comptage (pas de découpe en SQL), dédoublonné par texte ; classement par lectures comptées, temps écouté puis nom. Les statistiques ne se recalculent pas sur simple reconstruction de l'index.
- 2026-10-14 — `ArtistPageModel` (non branché) garde son rôle et prend le tri album/numéro de piste, pour rester cohérent avec la page ; sa classe n'est pas utilisée par la vue.

## Progress

- [x] 2026-10-14 — 112.1 : règles pures, index, migration 026, dépôt des choix, service et modèles Qt, avec tests unitaires et d'intégration qui passent.
- [x] 2026-10-14 — 112.2 : Protocol d'éditeur, branchement de `ArtistField.qml` et de `app.py`, tests d'éditeur et d'interface (`test_info_panel_staging`) qui passent.
- [x] 2026-10-14 — Tests de migration et de schéma adaptés à la version 26.
- [x] 2026-10-14 — 112.3 : maquette QML, modèle jetable, lanceur, captures et revue en français livrés.
- [x] 2026-10-14 — Revue utilisateur de la maquette : décisions transmises dans la consigne de la partie vue réelle (règle « au moins un côté seul » conservée, actions dans le menu « … », page après action, ordre album puis numéro de piste, pas de Reset choices).
- [x] 2026-10-14 — 112.4 : vue réelle branchée (activité Artists, volet `ArtistsPane.qml`, page d'artiste `ArtistPageHeader.qml` dans l'onglet, actions du menu « … », navigation après action), tests UI `tests/ui/test_artists_view.py` et `tests/ui/test_artists_session.py`, capture hors écran.
- [x] 2026-10-14 — 112.5 : liens d'artistes rebranchés sur `ArtistIndexService` (lecteur, plein écran, historique, file, menu de lecture), tests `tests/ui/test_player_island_links.py` réécrits sur les étiquettes Artist.
- [x] 2026-10-14 — 112.6 : tops artistes des statistiques (`top_artists`, `CreditRules`), tests d'intégration.
- [ ] Recette interactive sur la collection personnelle (non faite : hors périmètre, aucune collection touchée).
- [ ] Commit sur la branche de travail `worktree-agent-aaed1228f7e279cdf` : fait en fin de tâche, aucun push, aucune fusion (voir Outcomes).

## Outcomes & Retrospective

Résultats observés le 14 octobre 2026, depuis les sources, sur cette machine (Windows 11, Python 3.12.14). Tests lancés un fichier par processus.

- Unitaires : `test_artist_index.py` (52 tests), `test_artists_112_prototype.py` (5), `test_metadata_editor_staging.py` (7), `test_artist_tag_sync.py` (6) passent.
- Intégration : `test_artist_index_service.py` (8), `test_database_migrations.py` (13), `test_genre_manager_upgrade.py` (3), `test_plugin_schema.py` (7), `test_library_repository.py` (3) passent. `test_track_loudness.py` : 1 test passe, 6 sont ignorés (non comparé à `main`).
- Interface : `test_info_panel_staging.py` passe, `test_player_island_links.py` passe. `test_metadata_editor.py` a un échec connu sur `main` (`test_mixed_selection…`, vérifié sur l'archive du commit de base). `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it` échoue déjà sur `main`.
- Démarrage depuis les sources : `uv run python -m mtee --data-dir .local/run-112 --smoke-test` se termine avec le code 0.
- Maquette : `scripts/review_artists_112.py` lancé en mode hors écran pour les scénarios `default`, `selected` (menu et inline), `search` et `after`, sans avertissement QML. Captures relues une à une.
- Non réalisé : essai au pointeur de la maquette ; recette sur la collection personnelle ; paquet Windows (non demandé) ; `pyright`.
- Non vérifié : comportement de l'index après un rafraîchissement déclenché par un vrai scan (seul le chemin `libraryChanged` par ajout de piste est couvert par un test).
- Lint : `ruff check` et `ruff format --check` passent sur les fichiers créés ou modifiés ; une erreur E501 sur une ligne SQL de `library_repository.py` existe sur `main` et n'a pas été modifiée.

### Résultats de la partie vue réelle (14 octobre 2026)

Observés depuis les sources, sur cette machine (Windows 11, Python 3.12.14, PySide6 6.9.3). Un fichier de test par processus. La comparaison avec `main` utilise une extraction de `HEAD` dans `.local/base` (non versionnée), avec son propre environnement.

- Réussis : `test_artist_index.py` (54, dont 2 nouveaux), `test_artist_index_service.py` (9, dont 1 nouveau sur la garde d'auto-relance), `test_statistics_model.py` (10, dont 4 nouveaux sur les tops artistes et la relance), `test_metadata_editor_staging.py` (7), `test_artist_tag_sync.py` (6), `test_artists_112_prototype.py` (5), `test_play_log_repository.py` (9), `test_plugin_schema.py` (7), `test_database_migrations.py` (13), `test_demo_scenarios.py` (19), `test_info_panel_staging.py`, `test_column_selection.py`, `test_track_list_column_resize.py`, `test_track_list_wide_table.py`, `test_artist_profile_ui.py` (plugin, sans changement de test).
- Interface, nouveaux fichiers : `test_artists_view.py` (6 : volet, page avec pochette et ordre, menu, lecture, « This is one artist » puis « Split » avec ouverture du résultat) et `test_artists_session.py` (1 : onglets d'artistes non restaurés). Trois passages sur trois pour le premier.
- Interface, réécrit : `test_player_island_links.py` (8 : liens en mode v0.1 via l'index du cœur). Trois passages sur trois.
- Démarrage : `uv run python -m mtee --data-dir .local/run-118a --smoke-test` se termine avec le code 0.
- Échecs déjà présents sur `HEAD` (vérifiés sur la copie) : `test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`, `test_demo_navigation.py::test_placeholder_activities_show_coming_later`, `test_player_views.py::test_space_goes_to_search_while_a_track_is_playing`, `test_track_drag_98.py::test_list_batch_artwork_batch_and_escape`, `test_playlists_ui.py` (2 « orthline »), `test_metadata_editor.py::test_mixed_selection…`. `test_fullscreen_player_100.py` s'arrête par un abandon natif après 14 à 15 tests, sur `HEAD` comme sur la branche.
- Régression trouvée puis corrigée : `test_artist_profile_ui.py` (page plugin) et un arrêt en erreur de `test_playlist_creation_98.py` (une reconstruction d'index finie pendant l'arrêt déclenchait un comptage de statistiques). Corrigés ; `test_playlist_creation_98.py` passe trois fois sur trois, `test_artist_profile_ui.py` passe.
- Vérification manuelle depuis les sources, offscreen, par `scripts/validate_artists_112_view.py` (collection synthétique de 7 pistes, plugins désactivés) :
  - Volet : « 5 artists » ; Camo & Krooked 1, Chase 4, Status 2, Sub Focus 1, Wilkinson 1. Capture `.local/validation/112-view/01-artists-list.png` (vue lue).
  - Page « Chase » : « Artist », « 4 tracks · from “Chase & Status” », Play, Shuffle, « … » ; pistes dans l'ordre Opening (Alpha 1/9), Hold Tight (Alpha 3), Brand New Day (Brand New 2), Night Drive (Night 1). Capture `02-artist-page.png` (vue lue). La pochette a une source `image://artwork/…`, mais elle ne se dessine pas hors écran (masque `MultiEffect`, comme l'en-tête de playlist) : non vérifiée à l'écran.
  - Menu « … » : « This is one artist » actif, « Split into separate artists » grisé pour Chase. Capture `03-artist-menu.png` (vue lue).
  - Lien du lecteur : « Chase » cliquable sous « Opening » en lecture ; le clic ouvre `artist:chase`. Capture `04-island-link.png` (vue lue).
  - Recherche « cam » : « 1 of 5 artists ». Capture `05-artists-search.png` (non relue ; le compteur a été lu).
  - Messages QML `TypeError … 'demoMode'` et similaires : 8 au démontage de la fenêtre, après le résumé du script (le compteur du script affiche donc 0). Le même motif apparaît sur `HEAD` avec `scripts/validate_artist_manager_104.py`.

Non fait ou non vérifié :

- Essai au pointeur sur la vraie collection et recette de l'utilisateur : non faits. Aucun fichier personnel ni base réelle n'a été lu ou écrit.
- Pochettes réelles et ombre de la carte : non observées à l'écran (rendu hors écran, voir ci-dessus).
- Mode démo (`--demo`) : le bouton Artists y apparaît et ouvre un message « not available in this demo » ; non lancé visuellement.
- Page Profil : les tops artistes sont calculés et testés, leur affichage n'a pas été vérifié à l'écran.
- Performance sur environ 3 000 pistes : non mesurée dans cette partie.
- Paquet Windows : non construit (non demandé). `scripts/build_windows.ps1` et `scripts/smoke_packaged.ps1` n'ont pas été lancés.
- Suites UI complètes : non lancées en bloc (elles abandonnent sur ce poste ; voir les Surprises).
