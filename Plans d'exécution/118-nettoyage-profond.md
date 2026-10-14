# 118 — Nettoyage approfondi du code

## Statut et résultat attendu

Ce plan porte l'étape 8 du MVP v0.1 : remettre le code dans un état lisible et maintenable avant la publication du dépôt, sans changer le comportement de l'application. À la fin, `ruff check`, `ruff format --check` et `pyright` passent sans erreur sur `src`, `tests` et `scripts`. Les tests échouant aujourd'hui sont corrigés ou isolés avec une raison écrite. Le code mort, les prototypes et les outils ponctuels sont sortis du paquet de production. Les plus gros fichiers sont découpés en modules à responsabilité unique.

Préparé le 2026-10-14 à partir de `main` (`f7c5b1a`). Les phases 1 (état de référence) et 2 (code mort et prototypes) sont exécutées. Les décisions de l'utilisateur sur la phase 2 sont appliquées (voir le Decision Log). La phase 1b est faite, sauf un plantage natif avec plusieurs runtimes. Les phases 3 à 6 restent à faire.

## Organisation du travail

Le travail est réparti entre trois niveaux de modèles. Claude Opus 5.5 (architecte) fixe la stratégie, relit chaque diff, vérifie les conclusions des sous-agents dans le code et conduit le découpage des monolithes. Claude Sonnet 5.5 fait l'essentiel des modifications fichier par fichier et relance les tests après chaque fichier. Claude Haiku 5.5 fait les balayages volumineux : imports, symboles inutilisés, classement de listes et lecture de journaux d'outils. Aucune conclusion d'un sous-agent n'est appliquée sans contre-vérification dans le code.

Contraintes reprises de `AGENTS.md` et `PLANS.md` : aucun renommage de symbole lié à Qt/QML (slots, propriétés, signaux, rôles, propriétés de contexte) ; écritures testées sur des copies ; pas de build Windows automatique ; un commit détaillé par phase, puis push vers `origin`.

## Phase 1 — État de référence (exécutée le 2026-10-14)

Environnement : Windows 11 Pro, Python 3.12.14, PySide6 6.9.3, uv. Outils déclarés dans `pyproject.toml` : pytest + pytest-qt, ruff (`E F I N UP B SIM RUF`, 100 colonnes), pyright en mode `standard`. La CI (`.github/workflows/ci.yml`) exécute `ruff check .`, `ruff format --check .`, `pyright`, `pytest`, le smoke-test depuis les sources, puis le build. Sur l'état actuel, la CI ne peut pas passer : pyright et pytest échouent.

### Lint et format

    uv run ruff check src tests scripts       → 20 erreurs (18 E501, 1 SIM105, 1 I001)
    uv run ruff format --check src tests scripts → 14 fichiers à reformater

`ruff check .` remonte 180 erreurs, car il inclut les worktrees d'agents non suivies sous `.claude/worktrees/`. Il faudra exclure ces dossiers dans `[tool.ruff]` (`extend-exclude`) ou supprimer les worktrees.

### Types

    uv run pyright → 209 erreurs (52 dans src, 157 dans tests)

Règles principales : `reportArgumentType` 63, `reportOptionalMemberAccess` 35, `reportAttributeAccessIssue` 29, `reportOperatorIssue` 18, `reportIndexIssue` 16, `reportMissingImports` 14 (tests important `scripts/` sans chemin configuré). Fichiers les plus touchés : `tests/unit/test_artist_manager_contract.py` 38, `src/mtee/plugins/artist_manager/models.py` 20, `src/mtee/models/conversion_queue_model.py` 16.

### Tests

La suite complète plante en fin d'exécution (comportement connu). Elle est donc lancée fichier par fichier, avec `QT_QPA_PLATFORM=offscreen` : 146 fichiers, 128 verts, 18 en échec ou en plantage.

Préexistants : ils échouent déjà à `30b6a6d` (fusion de l'étape 111), vérifié dans une worktree temporaire supprimée ensuite.

- `tests/integration/test_conversion_ffmpeg.py` : 8 échecs (texte de pochette).
- `tests/integration/test_playback_repository.py::test_migration_from_17_keeps_data_and_creates_consistent_backup`.
- `tests/integration/test_playlist_exchange.py` : 3 échecs.
- `tests/unit/test_conversion_queue.py` : 2 échecs.
- `tests/unit/test_icon_provider.py::test_every_icon_renders_in_the_requested_colour`.
- UI, chacun 1 ou 2 échecs (`waitUntil` expiré ou assertion) : `test_browser_navigation`, `test_convert_view`, `test_incremental_scan_and_scroll`, `test_metadata_editor`, `test_playback_queue_ui`, `test_player_views`, `test_playlists_ui` (2), `test_track_drag_98`.
- `tests/unit/test_workspace_model.py` : échec à `30b6a6d`, plantage natif dans `waitUntil` sur `main`.
- `tests/ui/test_fullscreen_player_100.py` : plantage natif aux deux commits.

Différents de `30b6a6d` :

- `tests/ui/test_application_smoke.py` et `tests/ui/test_track_list_column_resize.py` : violation d'accès native pendant `waitUntil`, avec le thread d'événements libmpv actif (`mpv_backend.py:281`). Ils passent à `30b6a6d`, puis ont aussi passé sur `main` lors d'une seconde série de tests. Il s'agit donc de plantages natifs intermittents, pas d'une régression déterministe. `tests/ui/test_analysis_ui.py` plante de la même façon dans 3 exécutions sur 5 sur `HEAD`. `uv run python -m mtee --smoke-test` réussit, avec et sans `offscreen`.
- `tests/unit/test_plugins_hidden.py` : 2 échecs (`'artists' == 'explorer'`). Le test attend encore l'absence d'activité Artists, alors que l'étape 112 l'a rendue au cœur. Test obsolète.

Journaux bruts : dossier temporaire de session, non versionné.

## Phase 2 — Code mort et prototypes (inventaire exécuté, décisions en attente)

Deux balayages Haiku : graphe d'imports AST, vulture à 60 %, ruff F401/F841/F811 ; puis références QML, icônes, prototypes et scripts. Les résultats ci-dessous ont été recontrôlés par `git grep` sur `src`, `tests`, `scripts` et `packaging`.

### Code mort avéré (zéro référence hors définition)

Aucun module Python orphelin. Ruff F401/F841/F811 : aucun résultat.

Fonctions et constantes sans appelant (vulture 60 %, contrôlé par `git grep -w`) :

- `src/mtee/persistence/database.py` : `open_database`, `applied_versions`.
- `src/mtee/persistence/library_repository.py` : `mark_root_unavailable`, `copy_location_in_transaction`, `registered_roots_for`.
- `src/mtee/plugins/artist_manager/repository.py` : `DONE_STATES`, `UNFINISHED_APPLY`, `set_category`, `confirmed_credit_names`.
- `src/mtee/plugins/artist_manager/file_service.py` : `unfinished_track_ids`.
- `src/mtee/models/artwork_provider.py` : `cached_bytes` (propriété Python, non Qt).
- `src/mtee/models/demo_workspace.py` : `scenarioNames` (non décoré, absent du QML).
- `src/mtee/models/folder_tree_model.py` : `invalidate_root`.
- `src/mtee/services/metadata_adapters/id3.py` : `_validate_patch`.

QML et ressources :

- `src/mtee/qml/components/WaveformPreview.qml` : zéro référence. Le plan 100 le décrit comme un placeholder non utilisé.
- `src/mtee/qml/components/ArtistManagerPane.qml` : zéro référence depuis l'étape 111.
- `src/mtee/resources/icons/clock.svg` : aucun nom d'icône correspondant. `pin.svg` figurait aussi dans l'inventaire, à tort : `PlaylistsPane.qml:72` l'utilise. Il est conservé.
- `src/mtee/models/demo_tracks_model.py` : créé à chaque démarrage (`app.py:182`) et exposé comme `tracksModel` (`app.py:397`), mais lu par aucun QML ni Python. C'est un second jeu de données de démonstration, distinct de `src/mtee/demo/library.py`.

### Prototypes dans le paquet de production

Aucun n'est atteignable depuis `mtee.app` ou la CLI. `packaging/mtee.spec` copie tout `src/mtee/qml`, donc les fichiers QML de prototype sont embarqués dans l'EXE.

- `src/mtee/prototypes/` (`artists_112.py`, `genre_manager_110.py`, `settings_profile_114.py`, 1 328 lignes).
- `src/mtee/qml/prototypes/` (trois `ReviewWindow.qml`, 3 243 lignes).
- Utilisateurs : `scripts/review_artists_112.py`, `review_genre_manager_110.py`, `review_settings_profile_114.py`, `measure_genre_manager_110.py`, ainsi que `tests/unit/test_artists_112_prototype.py` et `tests/ui/test_genre_manager_110_prototype.py`.

### Code de plugin masqué dans l'arbre du cœur

Avec `PLUGIN_UI_ENABLED = False` (`plugins/registry.py:28`), ces vues ne sont pas atteignables en v0.1, mais elles vivent dans `src/mtee/qml/views` et `components` : `ArtistsView`, `ArtistReviewView`, `GenreManagerView` et ses quatre pages, `ArtistActionDialog`, `ArtistConfirmDialog`, `ArtistEditDialog`, `ArtistListView`, `ArtistReviewTrackList`, `CheckLine`, `ArtistProfileDialog`, `FilterChip`, `PluginsPane` et l'icône `arrow-left`. Ce n'est pas du code mort : c'est une frontière de plugin incomplète, qui relève de v0.2.

### Scripts

Sur 42 fichiers suivis dans `scripts/`, 5 servent au build et à la CI, 4 sont des outils de développement génériques et 15 sont des scripts de revue, de validation ou de mesure liés à une étape numérotée. Les 18 autres sont des outils pour la collection personnelle (enrichissement d'artistes, `artist-pilot-web/`, nettoyage d'orphelins, genres depuis les dossiers) : 10 scripts, la migration SQL et les 7 fichiers de `artist-pilot-web/`. Huit tests unitaires importent ces outils, ce qui produit une partie des erreurs `reportMissingImports` de pyright.

### Hygiène du dépôt

- Huit worktrees d'agents sous `.claude/worktrees/`, toutes fusionnées dans `main` et propres. La worktree Codex `codex/artists-mapping-103` a deux commits non fusionnés.
- `fonts.py` préfère « Geist Sans », qui n'est pas livrée. La police d'affichage réelle est Plus Jakarta Sans, et le README des polices est périmé (voir phase 4).

## Phases suivantes (non commencées)

### Phase 1b — Rétablir une base verte

Avant toute modification du code, corriger ou isoler les échecs listés plus haut. Sonnet traite chaque fichier de test et Opus relit les diffs. Le test obsolète `test_plugins_hidden` passe en premier. Opus mène ensuite l'enquête sur les plantages natifs intermittents (arrêt du thread libmpv pendant `waitUntil` et à la fermeture), qui empêchent aussi la suite complète de s'exécuter d'un bloc. Viennent enfin les échecs préexistants. Chaque test isolé reçoit un marqueur `xfail(strict=True)` motivé, jamais un `skip` silencieux. Les erreurs `reportMissingImports` des tests sur `scripts/` sont réglées par la décision prise sur ces scripts.

### Phase 3 — Formatage et lint automatiques

Haiku : `ruff check --fix`, `ruff format`, exclusion de `.claude/` et `.codex/`. Sonnet : les 18 E501 et le SIM105 restants, à la main. Suite de tests relancée fichier par fichier.

### Phase 4 — Nettoyage sémantique, module par module

Sonnet travaille fichier par fichier, avec les tests après chaque fichier ; Opus relit les diffs. Cibles mesurées :

- 81 `except Exception` dans `src` (17 dans `player_service.py`, 8 dans `metadata_editor_model.py`, 7 dans `media_transport.py`) et 10 `contextlib.suppress(Exception)`. Chaque cas est soit restreint à des exceptions précises, soit conservé avec une raison écrite : frontière libmpv/WinRT, slot Qt qui ne doit pas lever.
- 52 erreurs pyright dans `src`, puis 157 dans `tests`. 15 `# type: ignore`, dont 13 dans `demo_workspace.py`.
- Commentaires de narration et blocs de code commentés.
- `fonts.py` (Geist absente) et doublons de données de démonstration.

### Phase 5 — Découpage des monolithes

Conduit par Opus, avec une façade de délégation pour ne pas toucher aux liaisons QML. Des tests de caractérisation sont écrits avant chaque extraction si la couverture manque.

- `src/mtee/models/workspace_model.py` : 3 676 lignes, une classe, 269 méthodes, 124 slots, 64 propriétés. Sections déjà marquées : propriétés, requêtes, artistes du cœur, racines et scans, actions de mise en page, sélection, rafraîchissement des dossiers.
- `src/mtee/models/demo_workspace.py` (1 487), `src/mtee/services/player_service.py` (1 198), `src/mtee/persistence/library_repository.py` (1 134), `src/mtee/models/metadata_editor_model.py` (1 077).
- QML : `TrackListView.qml` (1 297) et `SettingsView.qml` (1 080).
- `plugins/artist_manager/repository.py` (1 487) reste hors v0.1, comme le reste du code de plugin.

#### Plan détaillé de découpage de `workspace_model.py` (établi le 2026-10-15)

État mesuré : 3 679 lignes, une classe `WorkspaceModel`, 269 méthodes, 124 slots, 64 propriétés et 21 signaux, liés au QML. La couverture de ligne par les 32 fichiers de test qui touchent le modèle est de 77 % (`COVERAGE_CORE=sysmon`, `coverage run` par fichier puis `combine`). Couverture par section :

| Section | Couverture |
|---|---|
| Propriétés et navigation | 79 % |
| Requêtes | 59 % |
| Artistes du cœur | 73 % |
| Corbeille, déplacement, analyse | 67 % |
| Lignes des onglets et arbre des dossiers | 84 % |
| Racines, scans, action sur une piste de l'explorateur | 58 % |
| Actions de mise en page | 77 % |
| Sélection et lecture | 64 % |
| Internes | 85 % |
| Rafraîchissement des dossiers et session | 83 % |
| Fonctions de module | 78 % |

Règles :
- `WorkspaceModel` reste la façade unique du QML. Les noms, types, signaux et arités des slots et propriétés ne changent pas.
- Chaque extraction devient un module de `src/mtee/models/`, avec des dépendances explicites passées au constructeur, sans référence au modèle entier. Le corps des slots délègue au collaborateur.
- Une section couverte à moins de 80 % reçoit des tests de caractérisation avant d'être extraite.
- Une étape égale un commit, après la relance fichier par fichier de tous les tests qui touchent le modèle.

Ordre initial, du moins risqué au plus risqué : fonctions de module, écriture de la session, historique de navigation, artistes du cœur, racines et scans. Révisé le 2026-10-15 après les deux premières étapes :

1. Fait : les fonctions de module (tri des lignes, codes Camelot, colonnes d'écoute, références de dossier, chemins locaux, préférences de colonnes) sont dans `src/mtee/models/workspace_rows.py`, avec des tests directs (`tests/unit/test_workspace_rows.py`). L'AST de la classe est identique à celui d'avant, aux renommages près. Une variable locale `with_play_stats` de `_request_track_rows`, qui masquait la fonction du même nom après renommage (détecté par pyright), devient `add_play_stats`.
2. Annulé : l'écriture de la session, extraite dans un `QObject` enfant (`WorkspaceSessionWriter`, minuterie et exécuteur), faisait planter `tests/unit/test_preview_tabs.py` de façon intermittente. Mesures :
   - avec l'extraction : 3 exécutions plantées sur 6, puis 4 sur 8 avec le collaborateur sans parent Qt ;
   - sur `HEAD` : 0 sur 12 ;
   - avec l'étape 1 seule : 0 sur 6, deux fois.

   La violation d'accès survient dans la boucle d'événements de pytest-qt, sans autre thread Python vivant. Plusieurs `WorkspaceModel` vivent dans le même processus (aucun n'est libéré, même après `gc.collect()`), et leurs minuteries ou travailleurs survivent à leur test. C'est la même famille que l'arrêt avec plusieurs runtimes. Cause exacte non établie ; l'extraction est retirée.
3. Abandonné : l'historique de navigation. Rejouer un pas d'historique réécrit une quinzaine d'états propres à la façade (groupes, onglet actif, activité, plein écran, panneau droit, page de réglages, vue de l'onglet, sélection, ancres, défilement). Un collaborateur aurait besoin du modèle entier : ce serait déplacer l'objet-dieu, pas le découper. La navigation reste avec la mise en page.

Stratégie révisée : un cœur pur et une coquille impérative. Sont extraites les fonctions de décision non triviales (pures et testées directement), tandis que la façade garde l'état et ses mutations. Aucun `QObject` portant des minuteries ou des threads n'est sorti du modèle tant que le problème de durée de vie des objets Qt avec plusieurs instances n'est pas résolu (tâche proposée séparément). Prochaines candidates :
- la décision qui suit une reconstruction de l'index des artistes (artiste à ouvrir, onglets à fermer, à renommer ou à recharger), depuis `_on_artist_index_changed` ;
- les calculs de `_request_track_rows` et du tri des dossiers ;
- le classement des événements de rafraîchissement des dossiers.

Restent dans la façade : la mise en page (onglets, groupes, colonnes, scission), cœur du modèle, et les délégations courtes vers le lecteur, les playlists et l'éditeur.

Monolithes suivants, à replanifier une fois `workspace_model.py` traité : `demo_workspace.py` (1 487 lignes, qui reproduit l'API QML de la façade pour le mode démo), `player_service.py` (1 198), `library_repository.py` (1 134), `metadata_editor_model.py` (1 077), `TrackListView.qml` (1 297) et `SettingsView.qml` (1 080).

### Phase 6 — Vérification finale et bilan

Lint, types, tests fichier par fichier, `--smoke-test` depuis les sources et parcours manuel. Bilan chiffré : lignes supprimées, fichiers déplacés, erreurs résolues, recommandations restantes.

## Reprise et incidents

Le relevé de référence se refait avec la boucle fichier par fichier : `uv run pytest <fichier> -q -p no:cacheprovider`, avec `QT_QPA_PLATFORM=offscreen`. Comparer avec `30b6a6d` dans une worktree temporaire détachée, en lançant pytest avec `PYTHONPATH=<worktree>/src` et le Python de `.venv`, puis supprimer la worktree. Ne jamais utiliser `git stash`.

## Progress

- [x] 2026-10-14 — Phase 1 : outils identifiés ; ruff, format, pyright et tests fichier par fichier relevés ; échecs classés en préexistants ou récents par comparaison avec `30b6a6d`.
- [x] 2026-10-14 — Phase 2 : deux balayages Haiku, résultats recontrôlés par `git grep`.
- [x] 2026-10-14 — Décisions utilisateur sur la phase 2 (voir le Decision Log).
- [x] 2026-10-14 — Phase 2 appliquée : huit worktrees d'agents fusionnées supprimées avec leurs branches ; `.claude`, `.codex` et `.agents` exclus de ruff ; code mort et prototypes supprimés (Sonnet) ; scripts déplacés dans `scripts/archive/` (Sonnet) ; diffs relus et contrôles relancés (Opus). Bilan : 66 fichiers touchés, 40 insertions, 6 349 suppressions.
- [x] 2026-10-14 — Commit et push de la phase 2 (`3a37242`).
- [x] 2026-10-14 — Phase 1b : les échecs d'assertion sont tous corrigés ; quatre défauts du code sont corrigés ; la cause principale des plantages natifs est trouvée et corrigée. Il reste une forme de plantage, avec plusieurs runtimes dans un même processus (voir ci-dessous).
- [ ] Plantage avec plusieurs runtimes dans un même processus (`test_fullscreen_player_100.py`, `test_playlists_ui.py`) : enquête native à mener séparément.
- [x] 2026-10-14 — Phase 3 : `ruff check --fix` et `ruff format` (Haiku), puis les 8 E501 et le SIM105 restants à la main (Sonnet), avec relecture d'Opus. `ruff check .` et `ruff format --check .` passent.
- [x] 2026-10-14 — Phase 4 :
  - tests de caractérisation de `TrashModel` et `TrashService` (Sonnet) ;
  - classement des 97 gestionnaires larges (Haiku), puis passe sur les exceptions selon la politique décidée par Opus (Sonnet) ;
  - `pyright` ramené à 0 sur `src` et sur `tests` (deux agents Sonnet) ;
  - relecture des diffs (Opus).
- [x] 2026-10-14 — Trois défauts de la corbeille corrigés à la demande de l'utilisateur, avant la phase 5 (voir le Decision Log).
- [x] 2026-10-15 — Phase 5, étape 1 : fonctions de module de `workspace_model.py` déplacées dans `workspace_rows.py`. L'étape 2 (écriture de la session) a été annulée après une régression native, et l'étape 3 (navigation) abandonnée. La stratégie est révisée dans le plan détaillé.
- [ ] Phase 5, suite selon la stratégie révisée ; phase 6.

## Surprises & Discoveries

- La CI ne peut pas passer sur `main` : 209 erreurs pyright et des tests en échec.
- `ruff check .` analyse les worktrees d'agents non suivies (180 erreurs au lieu de 20).
- Trois fichiers de test sont cassés par les étapes 112 et 114-116, dont deux plantages natifs. L'application démarre pourtant correctement en `--smoke-test`.
- `DemoTracksModel` est instancié en production sans être lu.
- Les fichiers QML de prototype sont embarqués dans l'EXE, car le spec copie tout l'arbre `qml`.
- L'inventaire comptait `pin.svg` comme inutilisé, à tort. Sonnet a relevé son usage avant la suppression : une contre-vérification reste nécessaire même après un `git grep`.
- `Id3WaveAdapter._validate_patch` n'était plus appelé. La détection des champs ambigus passe désormais par `domain/tag_conflicts.py` et `AnalysisService`.
- `scripts/archive/validate_artist_manager_104.py` ne fonctionne plus depuis l'étape 111 : `workspace.artistManager` vaut `None` quand les plugins sont désactivés. Il n'a pas été réparé (script archivé).
- `scripts/archive/artist-pilot-web/AUTOMATION.md` contient un chemin personnel (`C:/Users/...`), déjà présent avant le déplacement, à traiter à l'étape du dépôt public. Le commentaire de `plugins/artist_manager/migrations/020_artist_enrichment.sql` cite encore l'ancien chemin du script SQL. Il est laissé tel quel, pour ne pas toucher une migration.

- Phase 1b, cause des plantages intermittents. Le libmpv embarqué charge ses scripts Lua intégrés (OSC, console, stats, ytdl, etc.). LuaJIT signale ses erreurs internes par l'exception SEH `0xE24C4A02`, rattrapée normalement dans libmpv. Le `faulthandler` de Python, activé par pytest, écrit pourtant les piles de tous les threads à chaque occurrence. Lire la pile d'un thread qui exécute du Python à ce moment provoque la violation d'accès (le vidage s'interrompt au milieu d'une ligne). Preuve sur un reproducteur de 30 cycles de création et fermeture : 9 processus plantés sur 12 avec faulthandler et les scripts ; 0 sur 5 sans faulthandler ; 0 sur 12 avec faulthandler et les scripts désactivés. Cette explication concerne les plantages en test. Elle ne prouve rien sur le plantage utilisateur R05 du plan 06b : l'application n'active pas faulthandler.
- Une seconde forme subsiste. `Fatal Python error: Aborted` survient dans le thread principal, pendant `processEvents`, quand plusieurs runtimes complets sont créés puis fermés dans un même processus. Chaque test pris seul passe. Cela reste vrai avec les contrôles média remplacés par `NullMediaTransport`, sans faulthandler et avec l'arrêt réel `_shutdown` dans l'aide de test. Le plan 112 l'avait relevée (threads qui lisent une base fermée). Aucun message Qt avant l'arrêt : un débogueur natif est nécessaire.
- Défauts du code trouvés par les tests en échec, puis corrigés :
  - `WorkspaceModel.setSearch` : le premier caractère tapé dans une recherche d'onglet d'aperçu était perdu. `_keep()` émettait `layoutChanged` avant la capture de l'état de groupe, et le champ relisait une requête vide.
  - `WorkspaceModel.customPlaylistOrder` : l'état de vue du groupe n'était pas recapturé, donc la playlist restait filtrée ou triée.
  - `PlaylistExchange` : l'export plantait (`KeyError: 'filename'`) sur une entrée indisponible sans nom de fichier, et le libellé de progression de l'import lisait `filename` hors du `snapshot`.
  - Icônes `heart`, `heart-filled` et `pin` : couleurs codées en dur au lieu de `currentColor`, ce qui rendait inopérantes les couleurs voulues par l'îlot et le plein écran (plan 100).
- Les autres échecs venaient de tests obsolètes : chargements devenus asynchrones (`91ebb38`), migrations des plugins sorties du cœur (`d32b64d`), préférences de colonnes globales et tri par date de création (`fbc7d02`), panneau Queue repris (`69baca8`), contexte de rapport `report_items` (`f732720`), activité Artists rendue au cœur (étape 112).

- Phase 4. Les tests de caractérisation de la corbeille ont empêché une régression pendant la même phase. Restreindre aux erreurs SQLite les `except` qui suivent un recyclage réussi faisait déclarer « failed » un fichier déjà dans la Corbeille. Ces deux gestionnaires restent larges, avec un commentaire qui explique pourquoi.
- Défauts trouvés par les nouveaux tests de la corbeille, non corrigés (en attente de décision) :
  - `trash_service.py:365` : `ctypes.FormatError(result & 0xFFFFFFFF)` lève `OverflowError` pour tout HRESULT négatif, et le message d'erreur devient « OverflowError: Python int too large… ». Vérifié : `FormatError(result)` (signé) renvoie le texte Windows. Diagnostic seulement : l'échec reste un échec et rien n'est supprimé.
  - `trash_model.py:179/:182/:313` : un échec de préparation ou de soumission passe à l'état « result » sans émettre `dialogRequested`, alors que `TrashDialog.qml` ne s'ouvre que sur ce signal.
  - `jobs.py:28` : `PARTIAL_ERROR_CODES` ne contient pas `trash_partial_failure`. Le message du job est donc préfixé « _TrashBatchError: ».
  - `trash_model.py:99` : `selectedCount` hors confirmation renvoie la taille de la demande, conflits compris.
  - `trash_model.py:217` : `_waiting_for_release` n'est pas remis à zéro par une nouvelle demande (sans effet aujourd'hui).
  - Une annulation entre `journal.prepare` et `finish` laisse une ligne `prepared`, présentée comme « interrupted » au démarrage suivant.
- Annulations converties en échec ou en succès, laissées en l'état pour décision : les boucles d'enregistrement et d'annulation de `metadata_editor_model.py` produisent des lignes « Save stopped » ou « Undo stopped », et le job se termine en succès. `metadata_editor_model.py` (récupération) et `workspace_model.py` (préparation de file) signalent une annulation comme une erreur. Une annulation arrivée pendant qu'une résolution de conflit est encore en file laisse la ligne « working ».
- La journalisation n'a aucun gestionnaire configuré. Les avertissements ajoutés partent sur stderr, invisible dans l'EXE fenêtré, et `logs/` reste vide. Configurer un fichier de journal serait une fonctionnalité : à proposer, non ajoutée.
- Piste pour l'arrêt avec plusieurs runtimes : sans `shiboken6.delete` et `gc.collect()` explicites à la fin d'une fixture, un passage du ramasse-miettes pendant le `processEvents` d'un test suivant faisait planter l'interpréteur (violation d'accès dépendant de l'ordre), observé en écrivant les tests de la corbeille.

## Decision Log

- 2026-10-14 (Opus) — Tests lancés fichier par fichier : la suite complète plante à la fermeture.
- 2026-10-14 (Opus) — `30b6a6d` sert de point de comparaison : c'est la dernière fusion avant les vagues 2 et 3.
- 2026-10-14 (Opus) — Les vues de plugin masquées ne sont pas classées comme code mort. Leur déplacement relève de la frontière de plugin (v0.2), sauf décision contraire de l'utilisateur.
- 2026-10-14 (Opus) — Aucune suppression sans accord explicite. Les propositions sont soumises à l'utilisateur.
- 2026-10-14 (utilisateur) — Code mort avéré : supprimé.
- 2026-10-14 (utilisateur) — Prototypes 110, 112 et 114 : supprimés, avec leurs quatre scripts de revue ou de mesure et leurs deux tests. Les dossiers de revue de `docs/` et l'historique Git en gardent la trace.
- 2026-10-14 (utilisateur) — Scripts ponctuels et outils de collection : déplacés dans `scripts/archive/`. Restent dans `scripts/` les scripts de build et de CI, ainsi que `create_audio_fixtures.py`, `create_browser_fixture.py`, `diagnose_windows_runtime.py` et `capture_ux_scenario.py`.
- 2026-10-14 (utilisateur) — Les huit worktrees d'agents fusionnées sont supprimées. La worktree Codex `codex/artists-mapping-103` n'est pas touchée.
- 2026-10-14 (Opus) — `extraPaths = ["scripts/archive"]` dans `[tool.pyright]` : les tests des outils archivés importent ces scripts, et pyright doit les résoudre.

- 2026-10-14 (Opus) — Les scripts Lua intégrés de libmpv sont désactivés (`osc`, `ytdl`, `load-*`). MTEE n'utilise ni sortie vidéo, ni OSD, ni console, ni URL. On corrige la cause plutôt que de désactiver faulthandler, conformément à R05 (« désactiver faulthandler n'est pas un correctif »). Test de non-régression : `tests/integration/test_mpv_lua_exceptions.py`. Sans le correctif, il échoue 3 fois sur 3 ; avec, il passe 3 fois sur 3.
- 2026-10-14 (Opus) — Les défauts du code sont corrigés plutôt que marqués `xfail`. Ce sont de petites corrections qui rétablissent l'intention documentée, chacune prouvée par le test qui échouait. Changement visible : dans l'îlot et le plein écran, le cœur « non aimé » prend désormais les couleurs `iconColor` et `hoverColor` déjà déclarées. Dans les listes, il garde l'apparence d'avant (gris, rose quand il est aimé) et blanchit au survol.
- 2026-10-14 (Opus) — `tests/ui/test_fullscreen_player_100.py` ferme désormais ses runtimes par `_shutdown`, comme l'application. Cela ne suffit pas à supprimer l'arrêt, mais retire un écart de comportement entre le test et l'application.
- 2026-10-14 (Opus) — Aucun `xfail` ajouté : il ne reste aucun échec d'assertion, et un arrêt du processus ne peut pas être marqué `xfail`.

- 2026-10-14 (Opus) — Politique des exceptions :
  - les captures silencieuses gardent leur repli mais journalisent (warning, ou debug pour les cas attendus ou fréquents) ;
  - `BaseException` sans relance devient `Exception` (`playlist_exchange.py`, qui transformait `KeyboardInterrupt` en `ValueError`, et `workspace_model.py`) ;
  - la clause redondante de `player_service.py` est fusionnée ;
  - restriction seulement avec preuve (`process.wait()` → `OSError`) ;
  - restent larges, avec la raison en commentaire : les analyseurs de fichiers audio (mutagen), les frontières natives (libmpv, WinRT, COM, FFmpeg), les gardes de job ou de slot qui signalent déjà l'erreur, les nettoyages sur un chemin d'échec, et la sauvegarde de sécurité avant restauration.
- 2026-10-14 (Opus) — Correction de comportement : une annulation de résolution de conflit de tags se termine « cancelled » et non plus « failed », et la ligne redevient réessayable. Test ajouté dans `tests/unit/test_tag_conflicts_model.py`.
- 2026-10-14 (Opus) — Typage sans échappatoire :
  - les types Qt passés en chaîne (`"QVariantMap"`) deviennent `dict`/`list`, comme dans le reste du cœur ;
  - les lectures de `Property` en Python passent par des méthodes privées (src) ou `cast` (tests) ;
  - l'écart de stub `QImage.save(..., "PNG")` est contourné par `QImageWriter`, dont la sortie est identique octet pour octet.

  Aucun `# type: ignore` ajouté : il y en a toujours 53, dont 13 dans `demo_workspace.py`, à traiter avec la phase 5.

- 2026-10-14 (utilisateur) — Défauts de la corbeille à corriger avant la phase 5. L'annulation (éditeur de métadonnées, préparation de file) et la journalisation sont reportées.
  - `_check_hresult` passe le HRESULT signé à `ctypes.FormatError`. Un échec du Shell porte donc le texte Windows au lieu d'`OverflowError`. Le repli hexadécimal reste non signé.
  - Une erreur de préparation émet `dialogRequested` : la boîte de dialogue s'ouvre en état « result » avec le message, comme lorsqu'aucun fichier n'est recyclable. Une annulation par l'utilisateur n'ouvre rien.
  - `trash_partial_failure` rejoint `PARTIAL_ERROR_CODES`. Un lot recyclé en partie s'affiche « Completed with errors », et le message n'est plus préfixé par le nom de la classe.
  - Les tests de caractérisation qui figeaient ces défauts affirment désormais le comportement corrigé.

## Outcomes & Retrospective

Phase 4, contrôles du 2026-10-14 :

- `pyright` : de 181 à 0 erreur (`src` 50 → 0, `tests` 131 → 0). `ruff check .` et `ruff format --check .` propres (451 fichiers).
- 78 nouveaux tests de la corbeille, couvrant 100 % des lignes de `trash_model.py` et de `trash_service.py` (mesure `COVERAGE_CORE=sysmon`). Aucun appel réel à la Corbeille Windows : le Shell et COM sont simulés.
- Tests fichier par fichier : 145 fichiers sur 147 passent, soit 1 123 tests réussis et 3 ignorés. Les deux autres sont les arrêts connus avec plusieurs runtimes (`test_fullscreen_player_100.py`, `test_playlists_ui.py`).
- `--smoke-test` : code 0. Build Windows non lancé ; aucun parcours interactif.

Phase 3, contrôles du 2026-10-14 :

- `ruff check .` : de 20 erreurs à 0. `ruff format --check .` : de 14 fichiers à 0 (449 fichiers formatés).
- Invariance vérifiée par comparaison des AST avec `HEAD`. Les fichiers seulement reformatés ont un AST identique. `conversion_service.py` diffère par l'ordre de deux imports `mutagen` (I001). `conversion_queue_model.py` diffère par `contextlib.suppress(RuntimeError)` à la place du `try/except/pass`, et par le lambda `before_publish` devenu une fonction locale `record_verified_output`, avec les mêmes paramètres et la même fermeture. Les chaînes coupées gardent leur valeur exacte.
- Tests passés, fichier par fichier : conversion (file d'attente, FFmpeg, vue Convert), échange de playlists, file de lecture, playlists UI (2 fois sur 2 après un arrêt multi-runtime connu), glisser-déposer, artwork, décodage, base de données, contrôles média. `--smoke-test` : code 0. `pyright` : 181, sans changement.
- Couverture manquante relevée : aucun test ne charge `TrashModel` ni `TrashService`. Leurs AST sont inchangés, mais la phase 4 doit écrire des tests de caractérisation avant de les modifier.

Phase 1b, contrôles du 2026-10-14 :

- Tests fichier par fichier : 143 fichiers sur 145 passent, soit 1 041 tests réussis et 2 ignorés. `test_fullscreen_player_100.py` s'arrête au 13ᵉ test environ. `test_playlists_ui.py` passe 2 fois sur 3 ; chacun de ses deux cas passe seul.
- Fichiers autrefois sujets aux plantages : 4 exécutions sur 4 réussies, sans violation d'accès, pour `test_analysis_ui`, `test_application_smoke`, `test_track_list_column_resize` et `test_workspace_model`.
- `ruff check .` : 20 erreurs. `ruff format --check` : 14 fichiers. `pyright` : 181 erreurs. Aucune variation.
- Non fait : parcours interactif de la recherche et de l'ordre personnalisé dans l'application. Build Windows non lancé.

Phase 2, contrôles du 2026-10-14 :

- `ruff check .` : de 180 à 20 erreurs ; les 20 restantes sont les mêmes qu'avant sur le code suivi.
- `ruff format --check` : 14 fichiers à reformater, sans changement.
- `pyright` : de 209 à 181 erreurs, sans aucune nouvelle erreur.
- Tests fichier par fichier : aucun nouvel échec ; les échecs connus sont inchangés.
- Les neuf fichiers de test des outils archivés passent.
- `--smoke-test` depuis les sources : code de sortie 0.
- Non fait : parcours interactif de l'application, sans objet pour des suppressions de code inatteignable. Build Windows non lancé.
