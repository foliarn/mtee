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

## Decision Log

- 2026-10-14 — Règle « au moins un côté seul » pour `&` et `x`, lecture littérale de la règle validée par l'utilisateur. L'exemple « Sub Focus & Wilkinson » semble suggérer « les deux côtés » ; à confirmer dans la revue (point 1). Le changement est local à `_cut_junctions`.
- 2026-10-14 — Les choix se stockent par crédit entier normalisé (`normalize_key`). Une action de page agit sur les segments d'origine de l'artiste : « This is one artist » vaut pour les segments dont le nom est issu d'une découpe ; « Split » vaut pour un nom contenant lui-même un séparateur.
- 2026-10-14 — Une question « One artist / Several » reste posée pour toute saisie contenant une virgule, `feat.`, `&` ou `x` sans réponse enregistrée (comportement de l'étape 111 conservé, car la réponse est désormais utile à la vue).
- 2026-10-14 — L'index est rafraîchi au démarrage, puis à chaque `libraryChanged` et `scanFinished`. Les demandes multiples sont fusionnées : une seule reconstruction supplémentaire au plus pendant un calcul.
- 2026-10-14 — Les règles par défaut (`NoArtistCreditRules`) restent disponibles pour les tests et les contextes sans index ; `app.py` passe toujours le service du cœur.
- 2026-10-14 — La maquette n'utilise ni base ni tag. Play et Shuffle ne lisent rien. La variante « menu » est affichée par défaut ; la variante « inline » est fournie pour comparaison.
- 2026-10-14 — L'entrée Artists n'est pas ajoutée à `ActivityBar.qml` ni à `Main.qml` avant la validation de la maquette, comme prévu par le plan.
- 2026-10-14 — Trace d'attribution : le commit est signé par le modèle exécutant (Claude Haiku 5.5) selon la consigne système, et non par la mention Opus indiquée dans la consigne de travail.

## Progress

- [x] 2026-10-14 — 112.1 : règles pures, index, migration 026, dépôt des choix, service et modèles Qt, avec tests unitaires et d'intégration qui passent.
- [x] 2026-10-14 — 112.2 : Protocol d'éditeur, branchement de `ArtistField.qml` et de `app.py`, tests d'éditeur et d'interface (`test_info_panel_staging`) qui passent.
- [x] 2026-10-14 — Tests de migration et de schéma adaptés à la version 26.
- [x] 2026-10-14 — 112.3 : maquette QML, modèle jetable, lanceur, captures et revue en français livrés.
- [ ] Revue utilisateur de la maquette et réponse aux points à trancher (`docs/ux/review-112-artistes.md`).
- [ ] Branchement réel de la vue (activité, `Main.qml`, réécriture des chemins d'artistes du workspace) : après validation.
- [ ] Réactivation des liens d'artistes inertes : après validation.
- [ ] Commit sur la branche de travail : à réaliser à la fin de la tâche ; aucun push, aucune fusion.

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
