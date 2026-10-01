# 101 — Sélection, sidebar, file et historique, tâches, couleur du plein écran et playlists

## Statut et résultat attendu

Plan préparé le 1er octobre 2026 à partir d'une liste de retours de l'utilisateur et de quatre séries de réponses. Il est destiné à un agent d'exécution (Claude Sonnet) qui ne dispose pas de la conversation : tout ce qui est nécessaire est écrit ici, avec les fichiers, les contrats, les pièges connus et l'ordre des jalons.

À la fin du plan, l'utilisateur obtient :

1. une désélection complète : un clic dans le vide ne laisse plus le contour vert de la ligne « courante » ;
2. un menu « Add to playlist » (bouton + des pistes, de l'île et du plein écran) compact, validé sur maquette ;
3. des dossiers qui se mettent à jour quand des fichiers y sont ajoutés, supprimés ou renommés pendant que MTEE est ouvert (diff à l'ouverture et surveillance des dossiers affichés) ;
4. un panneau droit avec trois onglets `Info`, `Queue` et `History`, où Queue et History reprennent la présentation de la file de la page 2 du plein écran (validée sur maquette) ; un historique persistant de 100 écoutes ;
5. des tâches lisibles : compteur `42/129`, élément en cours, temps écoulé et estimation, annulation, effacement des tâches terminées et détail des échecs, dans une page complète en plus du résumé de la sidebar ;
6. une couleur de carte du plein écran fidèle à la couleur dominante de la pochette, sans exception pour le blanc, le gris ou le noir, avec un texte qui passe en sombre sur une carte claire ;
7. un clic simple sur un dossier de l'Explorer qui ouvre sa page sans le déplier, et un double-clic qui le déplie ou le replie ;
8. un en-tête de playlist calqué sur Spotify (disposition, typographie, pochette arrondie et ombrée plus grande), aux couleurs de MTEE, sans toucher aux boutons Play et Shuffle.

Le plan contient une **porte de revue** : l'agent réalise la maquette en premier, exécute tous les autres jalons, puis **s'arrête** avant d'implémenter le panneau Queue/History et le menu « Add to playlist ». Ces deux jalons (101.9 et 101.10) ne commencent qu'après l'accord explicite de l'utilisateur sur la maquette.

## Vocabulaire

- **Groupe** : un panneau d'éditeur (vue simple ou divisée), indexé par `groupIndex` dans `WorkspaceModel`.
- **Occurrence** : une entrée de file `QueueEntry` avec son `entry_id` propre ; deux occurrences peuvent désigner le même morceau.
- **Historique d'écoute** : liste des morceaux joués, distincte de l'historique de navigation Back/Forward du plan 99 (`src/mtee/domain/navigation_history.py`), qui n'est pas concerné ici.
- **Rafraîchissement de dossier** : diff non récursif entre le contenu réel d'un dossier et la base, appliqué sans relancer le scan complet de la racine.
- **Couleur d'accent** : couleur de la carte principale du plein écran, calculée depuis la pochette du morceau joué.
- **Porte de revue** : point d'arrêt obligatoire décrit dans « Ordre des jalons ».

## Demande transcrite (1er octobre 2026)

L'utilisateur a listé, en substance :

1. Cliquer dans le vide devrait désélectionner complètement ; c'est fait à moitié, l'outline vert de sélection reste à l'écran.
2. Le menu qui s'ouvre au clic sur « + » est beaucoup trop gros.
3. Si une musique est ajoutée dans un dossier pendant que l'application est ouverte, le dossier ne se met pas à jour (watcher permanent, ou diff rapide à l'ouverture).
4. Reprendre le système de file de la page 2 du plein écran et l'implémenter dans la sidebar droite à la place de la file actuelle.
5. Reprendre le même système pour l'historique, en nouvel onglet à droite de Queue dans la même sidebar, au lieu du texte sous « Up next ».
6. Menu Tasks à revoir : difficile de suivre ce qui se passe (pendant une analyse on ne sait pas « XX/129 », il n'y a qu'une barre) ; en faire une page complète en plus du menu de la sidebar.
7. La couleur choisie par le plein écran n'est pas forcément la bonne ; revoir ce système.
8. Sidebar gauche : cliquer sur un dossier ne doit pas le déplier sauf clic sur la flèche ; clic simple ouvre sa page ; double-clic le déplie.
9. Playlists : « ça ne va pas du tout » ; titre un poil plus grand avec la police d'affichage ; copier Spotify sauf les couleurs, sans toucher aux boutons Play et Shuffle.

Consignes de l'utilisateur sur le plan lui-même : pas de tests UI demandés à l'agent ; seulement des maquettes pour le menu Queue/History et pour le menu « + ».

## Réponses de l'utilisateur

| # | Question | Réponse retenue |
|---|---|---|
| R1 | Quel menu « + » est trop gros ? | Le popup « Add to playlist » (`src/mtee/qml/components/AddToPlaylistMenu.qml`), ouvert depuis les pistes, l'île et le plein écran. Le menu « + » de la sidebar Playlists n'est pas concerné. |
| R2 | Mise à jour des dossiers | Diff rapide à chaque ouverture d'un dossier **et** `QFileSystemWatcher` sur les dossiers affichés dans les onglets, avec temporisation et attente de la fin des copies. Pas de nouvelle dépendance. |
| R3 | Clic sur une entrée d'historique | Comme la file : clic sur la pochette = lecture immédiate (la file et les ajouts manuels sont conservés) ; menu « … » / clic droit : `Add to queue`, `Go to folder`/`Go to playlist`, `Edit info`. Pas de glisser-déposer. |
| R4 | Rétention de l'historique | Persistant entre les sessions, 100 entrées. |
| R5 | Contenu de la page Tasks | Tout : compteur X/N et élément en cours ; temps écoulé et estimation ; annulation et « Clear finished » ; détail des échecs par élément. |
| R6 | Page Tasks et sidebar | La sidebar garde un résumé compact (avec X/N) et un bouton « Open Tasks page » ; la page complète s'ouvre comme onglet d'éditeur (comme Settings/Convert) et participe à l'historique Back/Forward. |
| R7 | Défauts de la couleur | « Une pochette blanche qui donne une carte grise, pareil pour le noir, c'est bizarre : ne pas faire d'exceptions » ; « un petit détail l'emporte sur la couleur dominante » ; « incohérent entre pochettes ». |
| R8 | Carte claire | Vraie couleur dominante (blanc/crème pour une pochette blanche, quasi-noir pour une noire) ; texte, icônes et waveform passent en sombre quand le fond est clair. Pas d'assombrissement forcé. |
| R9 | « Copier Spotify sauf les couleurs » | Disposition Spotify, palette MTEE, pas de dégradé tiré de la pochette. Boutons Play/Shuffle inchangés. |
| R10 | Pochette de l'en-tête de playlist | Coins arrondis et ombre comme Spotify, **et plus grande**. |
| R11 | Comportement du menu « Add to playlist » | Bascule immédiate, comme aujourd'hui (un clic ajoute ou retire, une coche confirme). |
| R12 | Ligne de méta de playlist | Style Spotify : `<créateur en gras> • 8 tracks, 34 min 26 sec` (`1 hr 12 min` au-delà d'une heure). |
| R13 | Après les maquettes | **S'arrêter** : ne pas coder le panneau Queue/History ni le menu « + » avant l'accord de l'utilisateur sur la maquette. Les autres jalons peuvent être faits. |
| R14 | Modifications non commitées présentes | L'agent les commite d'abord, telles quelles, dans un commit de base séparé. |
| R15 | Double-clic sur un dossier | Bascule : déplie un dossier replié, replie un dossier déplié. |

## Consignes d'exécution pour l'agent

Lire ce plan en entier avant de commencer, puis `AGENTS.md` et `PLANS.md`. L'interface est en anglais ; la documentation et les messages de commit sont en français.

**Tests et vérifications autorisés.** Sur demande expresse de l'utilisateur, ne créer, ne modifier et ne lancer **aucun test UI** : rien dans `tests/ui/`, aucune capture analysée, aucun pilotage de l'application à la souris ou au clavier, aucune inspection visuelle. Sont autorisés et attendus : les tests unitaires dans `tests/unit/` (pytest, pytest-qt avec `qtbot` pour des objets Qt non visuels), Ruff, le formatage, Pyright sur les fichiers Python modifiés, et le chargement non interactif du QML :

    uv run python -m mtee --data-dir .local/validation/101 --smoke-test

Ce chargement ne vaut pas recette ; il détecte seulement les erreurs QML au chargement (syntaxe, types, imports). Lire aussi la sortie console de ce lancement : un avertissement QML `ReferenceError`/`TypeError` est à corriger. La recette visuelle appartient à l'utilisateur (voir « Matrice de recette utilisateur »).

**Ne jamais** lancer `scripts/build_windows.ps1` ni `scripts/smoke_packaged.ps1`.

**Git.** Ne jamais utiliser `git stash`, `git reset --hard`, `git checkout -- <fichier>` ni un push forcé. Ajouter les fichiers par chemins explicites, jamais `git add .` ni un répertoire entier. Ne jamais commiter `.agents/`, `.codex/`, `skills-lock.json`, `graphify-out/`, `.code-review-graph/`, `.local/`, `build/`, `dist/`. Avant chaque commit : `git status --short`, `git diff --cached --check`, `git diff --cached`. Écrire le message dans un fichier temporaire de `$env:TEMP` (here-string PowerShell non interpolée) puis `git commit --file`. Après chaque jalon : `git fetch origin`, `git log --oneline --left-right HEAD...origin/main`, `git push origin main`, puis comparer `git rev-parse HEAD` et `git rev-parse origin/main`.

**Échecs préexistants.** Ces tests échouaient déjà avant ce plan et ne doivent pas être attribués à un changement sans comparaison : `tests/unit/test_conversion_queue.py` (réglages avancés), `tests/unit/test_icon_provider.py`, `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`, ainsi qu'une violation d'accès intermittente dans un worker SQLite et un plantage natif à la fermeture de libmpv. Lancer les tests unitaires ciblés de chaque jalon ; pour juger un échec, le relancer sur le commit précédent dans un `git worktree` temporaire (copier `vendor/` si FFmpeg est nécessaire), jamais par stash.

**Pièges Qt/PySide connus (PySide6 6.9.3).** `ClippingRectangle` n'existe pas dans cette installation ; pour arrondir une image, utiliser `MultiEffect` avec `maskEnabled` comme la pochette de `src/mtee/qml/views/FullscreenPlayer.qml` (élément `coverFrame`). `MultiEffect` fonctionne nativement mais n'est pas rendu par le moteur logiciel hors écran. `Shortcut` attend `PgDown`/`PgUp`, pas `PageDown`. Une liste Python lue élément par élément depuis QML est quadratique : exposer des modèles `QAbstractListModel` pour les listes longues. Les longues commandes heredoc Bash contenant du Python ou du QML échouent parfois ; écrire ces fichiers avec l'outil d'écriture de fichiers.

**Mode démo.** `src/mtee/models/demo_workspace.py` (`DemoWorkspace`) doit continuer à charger toutes les vues avec `--demo`. Toute nouvelle propriété ou slot utilisé par QML doit exister dans `DemoWorkspace` ou être protégé côté QML par `typeof ... === "function"` / un test de propriété, comme le code existant le fait déjà.

**Noms d'objets.** Les tests UI existants (non exécutés ici) recherchent des `objectName`. Avant de renommer ou supprimer un élément QML, chercher son `objectName` dans `tests/ui/` et conserver la valeur quand c'est possible. Si un élément est supprimé, consigner dans le rapport de validation les tests UI concernés.

**Graph de code.** `AGENTS.md` recommande les outils MCP `code-review-graph` pour situer les appelants ; si ces outils ne sont pas disponibles, utiliser la recherche textuelle. Le code source fait toujours foi.

## État du dépôt constaté le 1er octobre 2026

Base : commit `01ecd55` (`feat(navigation): finish plan 99 history and empty selection`) sur `main`.

**Modifications non commitées présentes** (travail de l'utilisateur, à commiter en 101.0) : `.gitignore`, `AGENTS.md`, `THIRD_PARTY_NOTICES.md`, `docs/validation/99-controles-lecture-file-navigation.md`, `src/mtee/qml/Main.qml`, `src/mtee/qml/Mtee/LineSlider.qml`, `src/mtee/qml/Mtee/Theme.qml`, `src/mtee/qml/components/MarqueeText.qml`, `src/mtee/qml/components/PlayerIsland.qml`, `src/mtee/qml/components/TransportControls.qml`, `src/mtee/qml/components/WaveformView.qml`, `src/mtee/qml/views/FullscreenPlayer.qml`, et les fichiers non suivis `LICENSES/PlusJakartaSans-OFL.txt`, `src/mtee/resources/fonts/PlusJakartaSans-Bold.ttf`, `src/mtee/resources/fonts/PlusJakartaSans-ExtraBold.ttf`. Ces changements ajoutent notamment à `Theme.qml` les propriétés `displayFontFamily: "Plus Jakarta Sans"` et `displayFontWeight: Font.ExtraBold`, utilisées par le titre du plein écran. `src/mtee/fonts.py` enregistre automatiquement tous les `.ttf` de `src/mtee/resources/fonts/`. Les éléments non suivis `.agents/`, `.codex/` et `skills-lock.json` sont des configurations d'outils de l'utilisateur : ne jamais les commiter.

**Contour vert après désélection.** Dans `src/mtee/qml/components/TrackListView.qml`, chaque `TrackRow` reçoit `current: view.activeFocus && list.currentIndex === index` (vers la ligne 717) ; `TrackRow.qml` dessine alors un cadre `Theme.focus` (vers la ligne 71). `press()` fixe `list.currentIndex = index` et donne le focus à la vue. Les gestionnaires de vide appellent `workspace.clearSelection(groupIndex)`, qui vide la sélection mais ne remet jamais `list.currentIndex` à `-1` ; la vue garde le focus, donc le cadre reste.

**Menu « Add to playlist ».** `AddToPlaylistMenu.qml` est un `Popup` de 350 × jusqu'à 520 px, marge interne 16, titre 16 px, champ de recherche de 38 px en 16 px, lignes de 68 px avec pochette 48 px et nom en 18 px, intertitres de 15 px, bouton `Close` en pied. Il est ouvert par `TrackListView.openPlaylistMenu()`, par l'île (`PlayerIsland.qml`, bouton `add-playlist`) et par le plein écran. Sa logique (tri « Saved in » / « Recently updated », état partiel, `togglePlaylist`, `addToNewPlaylist`, fermeture sur `playlistCreated`) est correcte et doit être conservée.

**Dossiers.** Aucun watcher n'existe. `WorkspaceModel._start_root_scan()` (vers la ligne 1523 de `src/mtee/models/workspace_model.py`) relance un scan récursif complet de la racine, lancé au démarrage (`resumeRoots`, discret) ou par `rescanRoot`. `LibraryScanner.scan()` (`src/mtee/services/library_scanner.py`) parcourt récursivement. `LibraryRepository.finish_scan()` marque absents (`present=0`) les fichiers et dossiers non vus dans la génération de scan, uniquement si le scan est complet. Un onglet de dossier affiche les seuls fichiers directs du dossier (`_folder_filter` dans `src/mtee/persistence/library_repository.py`, non récursif). Ouvrir un dossier (`openFolder` → `_open_folder`) ne relit jamais le disque.

**File et historique.** Deux implémentations coexistent : `src/mtee/qml/components/PlaybackQueueView.qml` (panneau droit, via `QueuePanel.qml`, avec poignée `||`, « Now playing » en texte, « Up next », et « History » en texte simple dans le pied) et `src/mtee/qml/components/FullscreenQueueCard.qml` (page 2 du plein écran : « Now playing » fixe en haut, sections « Next in queue » / « Next from: <source> », lignes de 56 px avec pochette, survol avec icône lecture, bouton « … », glisser-déposer, menu `Remove from queue` / `Go to folder|playlist` / `Edit info`). L'historique est `PlayerService._history_ids` (`src/mtee/services/player_service.py`), en mémoire, limité à 20, alimenté dans `_open_index` quand l'occurrence courante change ; il n'est pas enregistré dans la session persistée (`src/mtee/persistence/playback_repository.py`, JSON `version: 1` sans historique). `RightPanel.qml` n'a que deux onglets `info` et `queue` ; `WorkspaceModel` n'accepte que ces deux valeurs (lignes ~139, ~2239, ~2253), comme `DemoWorkspace.showRightPanel` (~973) et `NavigationLocation.right_tab`.

**Tâches.** `JobStatus` (`src/mtee/domain/jobs.py`) ne porte qu'un libellé, un état, une fraction de progression et une erreur. `JobContext.report_progress` est la seule remontée. L'analyse (`AnalysisService.run_batch`, `src/mtee/services/analysis_service.py`) est un seul job pour N morceaux qui publie `somme des progressions / N`. `JobsListModel` (`src/mtee/models/jobs_model.py`) n'expose ni compteur, ni horodatage, ni annulation, ni effacement. `TasksPane.qml` affiche conflits de tags puis jobs avec une ligne de progression.

**Couleur d'accent.** `accent_from_image()` (`src/mtee/services/cover_palette.py`) réduit l'image en 64 × 64, ignore les pixels peu saturés (saturation < 0,25) ou extrêmes (valeur hors [0,20 ; 0,95]), découpe le reste en 576 cases HSV (36 teintes × 4 saturations × 4 valeurs), choisit la case maximisant « nombre de pixels × saturation moyenne », puis assombrit la couleur jusqu'à un contraste 4,5:1 avec le blanc. Conséquences observées par l'utilisateur : une grande zone dont les nuances se répartissent sur plusieurs cases perd contre un petit détail saturé concentré dans une case ; une pochette blanche, grise ou noire ne donne pas d'accent (`None`) et retombe sur la carte grise `Theme.fsFallbackCard` ; de légères variations d'image changent la case gagnante. `CoverAccentModel` (`src/mtee/models/cover_accent_model.py`) calcule hors du thread graphique et expose `baseColor`, `darkColor`, `hasAccent` ; `PlayerModel.accent` renvoie le `PlayerModel` lui-même quand aucun modèle d'accent n'est attaché (il doit donc exposer les mêmes propriétés de repli). `FullscreenPlayer.qml` peint la carte en dégradé `shownBase` → `shownDark` et utilise du blanc codé en dur pour le texte, les icônes et la waveform.

**Explorer.** Dans `src/mtee/qml/components/ExplorerPane.qml`, un clic sur le nom d'un dossier appelle `toggleFolder` s'il est replié puis `openFolder` ; un clic sur la flèche bascule seulement ; le double-clic rappelle `openFolder`.

**En-tête de playlist.** `src/mtee/qml/components/PlaylistHeader.qml` : pochette carrée 208 px (164 px sous 800 px de large), « PLAYLIST » en capitales au-dessus, titre en police d'interface Bold 52 px (36 px), description, ligne `créateur · N tracks · m:ss` ancrée en bas, Play (56 px, rond, couleur primaire) et Shuffle sous la pochette, filet de séparation en bas. La hauteur de l'en-tête est codée dans `TrackListView.qml` (`heading.height: view.isPlaylist ? (width < 800 ? 286 : 330) : 92`). Le résumé vient de `PlaylistsModel.details()` (`src/mtee/models/playlists_model.py`, clés `summary` construites vers les lignes 208 et 218).

## Ordre des jalons et porte de revue

Exécuter dans cet ordre, avec un commit et un push par jalon :

1. 101.0 — Base de travail (commit des modifications en cours).
2. 101.1 — Maquettes Queue/History et « Add to playlist », dossier de revue.
3. 101.2 — Désélection complète.
4. 101.3 — Clic et double-clic des dossiers de l'Explorer.
5. 101.4 — Rafraîchissement des dossiers.
6. 101.5 — Historique d'écoute persistant (service et données, sans interface).
7. 101.6 — Tâches détaillées et page Tasks.
8. 101.7 — Couleur d'accent du plein écran.
9. 101.8 — En-tête de playlist façon Spotify.
10. **PORTE DE REVUE** : s'arrêter, mettre à jour `Progress`, commiter/pousser, puis rendre compte à l'utilisateur en lui demandant de valider la maquette 101.1. Ne pas commencer 101.9 ni 101.10 sans un accord explicite, consigné dans le `Decision Log`. Un silence n'est pas un accord.
11. 101.9 — Panneau droit Queue et History (après accord).
12. 101.10 — Menu « Add to playlist » compact (après accord).
13. 101.11 — Clôture : rapport de validation, index, suivi.

Si l'utilisateur demande des changements sur la maquette, les appliquer à la maquette, mettre à jour le dossier de revue, et attendre un nouvel accord.

## Jalons

### 101.0 — Base de travail

But : isoler le travail en cours de l'utilisateur dans un commit à part, sans le modifier.

Étapes, depuis la racine du dépôt :

    git status --short
    git diff --stat
    git log --oneline -5

Comparer la liste avec « Modifications non commitées présentes » ci-dessus. Si l'utilisateur a déjà commité tout ou partie, ne traiter que ce qui reste. Si de nouveaux fichiers inconnus apparaissent, ne pas les commiter et les signaler dans `Surprises & Discoveries`. Relire le diff pour vérifier l'absence de secret, de chemin personnel ou de donnée de collection. Ne modifier aucun contenu.

Indexer explicitement : `.gitignore`, `AGENTS.md`, `THIRD_PARTY_NOTICES.md`, `docs/validation/99-controles-lecture-file-navigation.md`, `src/mtee/qml/Main.qml`, `src/mtee/qml/Mtee/LineSlider.qml`, `src/mtee/qml/Mtee/Theme.qml`, `src/mtee/qml/components/MarqueeText.qml`, `src/mtee/qml/components/PlayerIsland.qml`, `src/mtee/qml/components/TransportControls.qml`, `src/mtee/qml/components/WaveformView.qml`, `src/mtee/qml/views/FullscreenPlayer.qml`, `LICENSES/PlusJakartaSans-OFL.txt`, `src/mtee/resources/fonts/PlusJakartaSans-Bold.ttf`, `src/mtee/resources/fonts/PlusJakartaSans-ExtraBold.ttf`. Si le plan 101 et la ligne d'index ne sont pas encore commités, les commiter dans un commit documentaire séparé.

Contrôle : le smoke-test QML ci-dessus. S'il échoue à cause de ce travail en cours, ne pas le corriger dans ce commit : commiter quand même la base (c'est l'état de l'utilisateur), consigner l'erreur, puis la corriger dans un commit distinct `fix(ui): ...` avant 101.1.

Modèle de commit :

    chore(ui): enregistrer la police d'affichage et les retouches en cours du lecteur

    Commit de base avant le plan 101. Contient, sans modification, le travail
    en cours de l'utilisateur : police Plus Jakarta Sans (Bold, ExtraBold) et sa
    licence OFL, propriétés displayFontFamily/displayFontWeight du thème, île et
    plein écran retouchés, notices et consignes AGENTS.md.

    Contrôles : smoke-test QML <résultat réel>.

### 101.1 — Maquettes Queue/History et « Add to playlist »

But : donner à l'utilisateur deux maquettes interactives, sans données réelles, à valider avant 101.9 et 101.10.

Fichiers à créer, sur le modèle de `docs/ux/mockups/Queue99Review.qml`, `scripts/review_queue_99.py` et `docs/ux/review-99-queue.md` (les lire d'abord) :

- `docs/ux/mockups/RightPanel101Review.qml` : maquette du panneau droit.
- `docs/ux/mockups/PlaylistMenu101Review.qml` : maquette du menu « Add to playlist ».
- `scripts/review_101.py` : lanceur avec `--scene <nom>` (et `--capture` facultatif), qui enregistre les polices (`mtee.fonts.register_fonts`, `resolve_ui_family`), le fournisseur d'icônes (`mtee.models.icon_provider.IconProvider`) et le module QML `Mtee` exactement comme `scripts/review_queue_99.py`.
- `docs/ux/review-101-file-historique-menu.md` : dossier de revue en français (« À examiner », « Parcours interactif », « Limites et décision attendue »).

Les maquettes utilisent uniquement des tableaux QML en mémoire : pochettes générées (`CoverArt` avec `pattern`), titres fictifs, aucun accès au disque ni au service audio. Elles importent `Mtee` pour réutiliser `Theme`, `CoverArt`, `Icon`, `IconButton`, `SectionLabel`, `ThinScrollBar`, `AppMenu`, `AppMenuItem`, `TextButton`.

**Maquette du panneau droit.** Fenêtre 1280 × 800 avec, à droite, un panneau de 320 px (`Theme.rightPanelWidth`) de couleur `Theme.sidebar` et un filet gauche `Theme.separator`, comme `RightPanel.qml`. En-tête de 36 px (`Theme.tabHeight`) avec trois onglets `INFO`, `QUEUE`, `HISTORY` au style exact de `RightPanel.qml` (capitales 11 px DemiBold, interlettrage 1,1, soulignement primaire de 2 px sous l'onglet actif) et le bouton de fermeture. L'onglet Info peut rester un simple aplat.

Onglet Queue, transposition de `FullscreenQueueCard.qml` à une colonne étroite :

- marges latérales de 12 px (au lieu de 20 dans la carte), pas de fond de carte ;
- bloc fixe « Now playing » (`SectionLabel`, 34 px) puis la ligne du morceau courant : pochette 44 px avec voile noir 45 % et icône pause/lecture blanche 18 px, titre en `Theme.primary` 14 px, artiste en `Theme.textSecondary` 12 px ;
- liste défilante avec intertitres « Next in queue » (ajouts manuels) et « Next from: Deep Focus » (suite du contexte), 13 px gras `Theme.textSecondary`, 34 px de haut ;
- lignes de 56 px : pochette 44 px (voile et icône lecture au survol), titre 14 px, artiste 12 px, bouton « … » (icône `more` 18 px) visible au survol à droite ; survol en `Theme.selection` ;
- au moins huit lignes, dont deux occurrences du même titre et une ligne indisponible (opacité 0,6, « Unavailable » en `Theme.danger`) ;
- scènes : `queue` (repos), `queue-hover` (une ligne survolée), `queue-drag` (ligne tenue surlignée et trait d'insertion primaire de 3 px, avant relâchement), `queue-menu` (menu ouvert : `Remove from queue`, `Go to playlist`, `Edit info`), `queue-empty` (« Nothing next. »).

Onglet History, mêmes composants visuels :

- intertitre unique « Recently played » ;
- lignes identiques à celles de la file, du plus récent au plus ancien, sans glisser-déposer ; survol : pochette avec icône lecture ; bouton « … » ;
- au moins douze lignes, dont un titre présent deux fois et une ligne indisponible ;
- scènes : `history`, `history-menu` (menu : `Add to queue`, `Go to folder`, `Edit info`), `history-empty` (« Nothing played yet. ») ;
- **variante à soumettre**, scène `history-times` : même liste avec, à droite de chaque ligne au repos, l'heure relative d'écoute (« 3 min ago », « Yesterday ») en `Theme.textMuted` 12 px, remplacée par le bouton « … » au survol. Cette variante n'est **pas** demandée : le dossier de revue la présente comme une proposition à accepter ou refuser. Sans accord explicite, 101.9 ne l'implémente pas.

**Maquette du menu « Add to playlist ».** Fond 1280 × 800 avec une liste de pistes factice et le menu ouvert sous un bouton `add-playlist`. Proposition à présenter :

- largeur 300 px, hauteur au plus 420 px, marge interne 12 px, fond `Theme.surface`, rayon 8, bordure `Theme.separator` (inchangés) ;
- titre « Add to playlist » 13 px DemiBold `Theme.textSecondary` ;
- champ de recherche de 30 px, texte 13 px, icône `search` 14 px à gauche, placeholder « Search playlists », fond `Theme.chrome`, bordure `Theme.focus` au focus ;
- rangée « New playlist » de 40 px : carré 32 px `Theme.selection` avec icône `plus` 16 px, libellé 13 px ;
- intertitres « Saved in » et « Recently updated » au style `SectionLabel` (11 px), 26 px de haut ;
- lignes de 44 px : `PlaylistCover` 32 px, nom 13 px `Theme.textPrimary`, sous-ligne « N tracks » 11 px `Theme.textMuted` (le chemin de dossier éventuel en préfixe), icône 16 px à droite : `check` en `Theme.primary` si enregistré, `minus` si partiel, `add-playlist` en `Theme.textMuted` sinon ; survol `Theme.selection` ;
- pas de bouton `Close` : Échap ou un clic à l'extérieur ferment (le dossier de revue le signale comme changement) ;
- scènes : `menu` (8 playlists, 2 enregistrées), `menu-search` (filtre « deep »), `menu-partial` (multisélection avec un état partiel), `menu-empty` (aucune playlist : seule la rangée « New playlist »), `menu-compare` (menu actuel reproduit à ses tailles réelles à côté de la proposition).

Les maquettes doivent réagir au survol et au clic (bascule de coche, filtre de recherche, ouverture des menus, déplacement de ligne en mémoire) pour que l'utilisateur puisse les essayer. `--capture` peut produire des PNG dans `docs/ux/review-101-2026-10-01/` ; c'est facultatif, et l'agent n'analyse pas ces images (ce n'est pas un test).

Commande à documenter dans le dossier de revue :

    uv run python scripts/review_101.py --scene queue

Contrôle autorisé : le lanceur s'ouvre et se ferme sans avertissement QML dans la console pour chaque scène (`--capture` ou un délai de fermeture automatique, au choix de l'agent). Commit `docs(ux): maquettes de revue du panneau Queue/History et du menu Add to playlist (plan 101.1)`, push, puis **continuer** avec 101.2 sans attendre.

### 101.2 — Désélection complète

But : après un clic dans le vide, aucune ligne ne garde le cadre vert.

Dans `src/mtee/qml/components/TrackListView.qml` :

1. Ajouter sur la racine `FocusScope` un gestionnaire `onSelectionIdsChanged` qui, quand `selectionIds.length === 0`, remet `list.currentIndex = -1` (et `grid.currentIndex = -1` si la `GridView` utilise un index courant).
2. Rendre la condition du cadre indépendante de cet ordre d'évaluation : `current: view.activeFocus && list.currentIndex === index && view.selectionIds.length > 0`.
3. Vérifier que la navigation clavier reste correcte après désélection : la touche Bas part de `focusedIndex()` (qui renvoie -1 sans sélection) ; s'assurer que la première pression sélectionne la première ligne au lieu de rester sans effet, en lisant le gestionnaire `Keys` existant (vers les lignes 329–350) et en corrigeant seulement si le comportement est cassé.

Chercher les autres cadres pilotés par un index courant (`grep -n "current:" src/mtee/qml`) : Explorer, playlists, file. Les surbrillances du dossier actif (`activeFolder`) ou de la playlist ouverte ne sont pas des sélections et restent inchangées.

Pas de test Python possible (QML pur). Critère : en lisant le code, toute voie qui vide la sélection (`clearSelection`, changement d'onglet, navigation Back) aboutit à `currentIndex === -1` ou à `selectionIds.length === 0`, donc à `current === false`. Smoke-test QML. Commit `fix(selection): effacer le contour de ligne courante a la deselection (plan 101.2)`.

### 101.3 — Clic et double-clic des dossiers de l'Explorer

But : clic simple = ouvrir la page du dossier sans le déplier ; flèche = déplier/replier ; double-clic = déplier/replier.

Dans `src/mtee/qml/components/ExplorerPane.qml`, `MouseArea rowMouse` :

- `onClicked` sur un dossier : si le clic est sur la flèche (`event.x < chevron.x + chevron.width + 2`), `toggleFolder` ; sinon **seulement** `openFolder(row.modelData.id)` (supprimer l'appel à `toggleFolder` qui dépliait).
- `onDoubleClicked` sur un dossier : `pane.workspace.toggleFolder(row.modelData.id)` quand `row.modelData.hasChildren` est vrai, et ne plus rappeler `openFolder` (le premier clic l'a déjà fait). Qt émet `clicked` pour le premier clic puis `doubleClicked` pour le second : un double-clic sur le nom ouvre puis bascule ; un double-clic sur la flèche bascule deux fois, ce qui équivaut à deux clics et reste cohérent.
- Les fichiers gardent leur comportement (clic = sélection, double-clic = lecture).
- Mettre à jour le commentaire d'en-tête du fichier.

`toggleFolder` ne crée pas d'entrée d'historique de navigation (contrat du plan 99) ; ne pas changer cela. Vérifier que `DemoWorkspace.toggleFolder` existe (ligne ~1012). Smoke-test QML. Commit `fix(explorer): ouvrir un dossier au clic et le deplier au double-clic (plan 101.3)`.

### 101.4 — Rafraîchissement des dossiers

But : un fichier ajouté, supprimé ou renommé dans un dossier apparaît ou disparaît dans son onglet sans rescan manuel, que l'onglet soit déjà ouvert ou ouvert ensuite.

Contrat général : un rafraîchissement porte sur **un** dossier et ses enfants **directs** (fichiers audio et sous-dossiers), comme l'onglet. Il ne modifie jamais `scan_generation` et ne relance pas le scan complet. Il est ignoré si un scan complet de la même racine est en cours (ce scan couvrira le changement). Il s'exécute dans un job caché du `JobService`, hors du thread graphique. Il ne supprime jamais rien du disque ; « supprimé » signifie `present=0` en base, exactement comme `finish_scan`.

**Scanner.** Dans `src/mtee/services/library_scanner.py`, ajouter `LibraryScanner.list_directory(root: Path | str, relative: str) -> DirectoryListing`, avec `DirectoryListing(entries: tuple[ScanEntry, ...], folders: tuple[str, ...], issues: tuple[ScanIssue, ...], complete: bool)`. Il liste le seul dossier `root/relative`, sans récursion, avec exactement les mêmes filtres que `scan()` : liens symboliques ignorés, fichiers temporaires de conversion (`_MTEE_CONVERSION_TEMP`) ignorés, extensions `AUDIO_SUFFIXES`, chemins relatifs à la racine en POSIX, `SourceRevision.observe`. Extraire la classification d'un `os.DirEntry` dans une fonction privée partagée par `scan()` et `list_directory()` pour éviter deux filtres divergents. Si le dossier est illisible ou absent, renvoyer `complete=False` avec l'issue, sans entrée.

**Dépôt.** Dans `src/mtee/persistence/library_repository.py`, lire d'abord intégralement `upsert_locations`, `unchanged_paths`, `upsert_folders` et `finish_scan`. Ajouter :

- `current_generation(root_id: str) -> int` ;
- `reconcile_folder(root_id: str, relative: str, *, present_files: Sequence[str], present_folders: Sequence[str], generation: int) -> list[str]` : dans une seule transaction, si `scan_generation` vaut toujours `generation`, marquer `present=0` les `root_tracks` dont `parent_relative_path == relative` et dont `relative_path` n'est pas dans `present_files`, ainsi que les `library_folders` dont `parent_relative_path == relative` absents de `present_folders` ; renvoyer les dossiers parents modifiés (au moins `relative` si quelque chose a changé). Si la génération a changé, ne rien faire et renvoyer `[]`.

Pour les fichiers nouveaux ou modifiés, réutiliser `unchanged_paths`, la lecture de métadonnées (`self._reader.read(path)` comme dans `_start_root_scan`) et `upsert_locations(root_id, records, generation)` ; pour les sous-dossiers, `upsert_folders(root_id, folders, generation)`. Ces fonctions conservent l'identité des morceaux et leurs règles existantes (déplacements, `file_id`) ; ne pas les dupliquer.

**Stabilité des copies.** Un fichier en cours de copie a une taille qui change. Dans le job, après la première liste, réobserver `SourceRevision` des entrées nouvelles ou modifiées après 500 ms (`context.sleep(0.5)`, annulable). Une entrée dont la révision a changé est **instable** : ne pas l'insérer cette fois et marquer le résultat `unstable=True`. Ne pas la marquer absente non plus (la laisser hors de `reconcile_folder` en l'ajoutant à `present_files` si elle était déjà connue).

**Surveillance.** Créer `src/mtee/services/folder_watch.py` avec `FolderWatchService(QObject)` : il possède un `QFileSystemWatcher`, expose `set_watched(paths: Iterable[str])` (ajoute/retire la différence), un plafond de 32 chemins, et un signal `folderChanged(str)` émis après une temporisation de 1 200 ms par chemin (un `QTimer` à coup unique par chemin, relancé à chaque événement `directoryChanged`). Un `addPath` refusé (lecteur amovible, réseau) est ignoré avec un journal de niveau debug. `close()` vide le watcher. Le service vit sur le thread graphique.

**WorkspaceModel.** Dans `src/mtee/models/workspace_model.py` :

- ajouter un signal interne `folderRefreshed(str root_id, str relative, object payload)` connecté en `QueuedConnection`, sur le modèle de `batchReady`/`_on_scan_batch` (lire ces fonctions et `_refresh_library`, vers la ligne 2663) ;
- `_request_folder_refresh(root_id, relative)` : ignorer si la racine est inconnue ou si un job de scan complet de cette racine est actif ; s'il y a déjà un rafraîchissement en cours pour ce dossier, mémoriser une demande en attente et la relancer à la fin ; sinon soumettre un job `visible=False`, libellé « Refresh folder », qui fait liste → stabilité → lecture → `upsert_*` → `reconcile_folder`, puis émet `folderRefreshed` avec `{"folders": [...], "unstable": bool, "issues": [...]}` ;
- `_on_folder_refreshed` : appeler `_refresh_library(root_id, set(folders) | {relative})` pour recharger les lignes des onglets concernés, invalider et recharger la branche de l'arbre si elle est dépliée (`self._folder_model.invalidate_branch(folder_id)` puis `_request_folder_branch`) ; si `unstable`, reprogrammer un rafraîchissement dans 2 s, au plus 15 fois de suite par dossier (compteur remis à zéro au premier résultat stable) ;
- déclencheurs : `_open_folder` (ouverture ou réactivation de l'onglet), `activateTab` sur un onglet de dossier, retour de l'application au premier plan (`QGuiApplication.applicationStateChanged` vers `Qt.ApplicationActive`, pour tous les onglets de dossier visibles), et `FolderWatchService.folderChanged` ;
- `_sync_folder_watches()` : construire l'ensemble des chemins absolus (`root["path"]` + `relative`) des onglets de dossier **actifs** de chaque groupe et appeler `set_watched` ; l'appeler après chaque changement de disposition (`openFolder`, `activateTab`, fermeture d'onglet, division/fusion, ajout/retrait de racine, restauration au démarrage) ;
- fermeture : arrêter le watcher avant la fermeture des services.

`DemoWorkspace` n'a pas de disque : aucun changement requis, sauf si une interface commune l'impose.

**Tests unitaires** (pas de test UI) :

- `tests/unit/test_library_scanner.py` : `list_directory` liste fichiers audio directs et sous-dossiers, ignore les fichiers non audio et le temporaire de conversion, ne descend pas dans les sous-dossiers, renvoie `complete=False` sur dossier absent.
- `tests/unit/test_folder_refresh.py` (nouveau) : base temporaire (`Database` sur `tmp_path`), racine ajoutée, scan complet initial via le scanner existant ; puis ajout d'un fichier → présent après rafraîchissement ; suppression → `present=0` ; renommage ; sous-dossier ajouté puis retiré ; dossier voisin intact ; `scan_generation` inchangé ; génération changée entre-temps → `reconcile_folder` ne fait rien. Les fichiers audio peuvent être produits par `scripts/create_audio_fixtures.py` ou les fixtures existantes (lire `tests/unit/test_library_scanner.py` pour la méthode en place).
- `tests/unit/test_folder_watch.py` (nouveau, `qtbot`) : création d'un fichier dans un dossier surveillé → un seul `folderChanged` après la temporisation malgré plusieurs écritures ; `set_watched` retire bien un chemin ; plafond respecté.
- `tests/unit/test_workspace_model.py` : ouvrir un dossier soumet un rafraîchissement ; après ajout d'un fichier et rafraîchissement, `trackModelForTab(...)` contient la nouvelle ligne. Utiliser les assistants déjà présents dans ce fichier.

Commandes :

    uv run pytest tests/unit/test_library_scanner.py tests/unit/test_folder_refresh.py tests/unit/test_folder_watch.py tests/unit/test_workspace_model.py
    uv run ruff check src/mtee/services/library_scanner.py src/mtee/services/folder_watch.py src/mtee/persistence/library_repository.py src/mtee/models/workspace_model.py
    uv run pyright src/mtee/services/library_scanner.py src/mtee/services/folder_watch.py src/mtee/persistence/library_repository.py

Commit `feat(library): rafraichir les dossiers ouverts et surveiller les dossiers affiches (plan 101.4)`.

### 101.5 — Historique d'écoute persistant

But : un historique de 100 écoutes, conservé entre les sessions, exposé à QML comme modèle, avec lecture immédiate et ajout à la file. Aucune interface dans ce jalon (elle arrive en 101.9).

**Domaine.** Créer `src/mtee/domain/playback_history.py` :

- `HistoryEntry` (dataclass gelée) : `history_id: str` (UUID4 texte), `track_id: str`, `snapshot: Mapping[str, Any]`, `source: str`, `source_title: str`, `played_at_utc: str` (ISO 8601, secondes) ;
- `PlaybackHistory` (dataclass gelée) : `entries: tuple[HistoryEntry, ...]` du plus récent au plus ancien, `HISTORY_LIMIT = 100`, méthode `record(entry) -> PlaybackHistory` qui ajoute en tête et tronque à 100, `validate()` (identifiants uniques, longueur ≤ 100), `find(history_id)`.

Règle d'enregistrement : conserver la règle actuelle de `_open_index` — un morceau entre dans l'historique quand l'occurrence courante change (passage au suivant, au précédent, `playEntry`, nouveau contexte, lecture depuis l'historique). Un redémarrage de la même occurrence (Repeat one, Précédent qui revient au début) n'ajoute rien. Ajouter aussi le morceau courant quand la file se termine (fin de lecture sans suivant) : lire `_on_eof` et `_finish` pour placer l'ajout. La restauration de session au démarrage n'ajoute rien. Les doublons sont autorisés (chaque écoute est une entrée).

**Service.** Dans `src/mtee/services/player_service.py` : remplacer `_history_ids` par un `PlaybackHistory` ; `history_rows()` renvoie, pour chaque entrée, le snapshot fusionné avec `_track_rows[track_id]` s'il existe, plus `historyId`, `trackId`, `playedAt`, `source`, `sourceTitle` et `available` (même fonction `_available` que la file) ; mettre à jour `PlaybackState.history` (identifiants, 100 au plus) et `_trim_track_rows` (vers la ligne 869) pour retenir tous les morceaux de l'historique. Ajouter :

- `play_history_entry(history_id: str) -> bool` : crée une nouvelle occurrence du morceau (origine `manual`, snapshot de l'entrée, source de l'entrée) et la rend courante **sans toucher** à `upcoming` ni au contexte ; l'ancienne occurrence courante passe dans `past` (et donc dans l'historique). Ajouter dans `src/mtee/domain/playback_queue.py` une opération pure `QueueState.insert_current(entry: QueueEntry) -> QueueState` (past + ancien courant, courant = entrée, upcoming inchangé, révision incrémentée, `validate()` respecté), puis ouvrir le courant comme `play_entry` le fait. Refuser (`False`) une entrée inconnue ou indisponible.
- `enqueue_history_entry(history_id: str) -> tuple[str, ...]` : délègue à `enqueue_tracks([track_id], source=..., source_title=..., tracks=[snapshot])`.

**Persistance.** Dans `src/mtee/persistence/playback_repository.py` : `PlaybackSession` gagne `history: tuple[HistoryEntry, ...] = ()` ; `_encode` écrit `version: 2` avec une clé `history` (liste d'objets `history_id`, `track_id`, `snapshot` filtré par `_snapshot`, `source`, `source_title`, `played_at_utc`) ; `_decode` accepte `1` (historique vide) et `2`, valide chaque champ (types, UUID, ISO), tronque au-delà de 100, et rejette les autres versions comme aujourd'hui. Pas de migration SQL : la colonne JSON existante suffit. `PlayerService` inclut l'historique dans l'instantané sauvegardé (vers la ligne 121) et le restaure dans `attach_session`, en alimentant `_track_rows` depuis les snapshots.

**Modèle Qt.** Créer `src/mtee/models/playback_history_model.py` : `PlaybackHistoryModel(QAbstractListModel)` sur le modèle de `src/mtee/models/playback_queue_model.py` (rôle `modelData`, propriété `count`, rafraîchi sur `queueChanged` et `stateChanged`, réinitialisation seulement si les lignes changent). Dans `src/mtee/models/player_model.py` : propriétés `historyModel` et `hasHistoryModel` (constante vraie), slots `playHistoryEntry(str) -> bool` et `enqueueHistoryEntry(str)`. Garder la propriété `history` (liste) pour la compatibilité. Dans `DemoWorkspace`, exposer l'équivalent minimal (liste en mémoire alimentée par les lectures de démo, `hasHistoryModel` faux) pour que 101.9 fonctionne en démo.

**Tests unitaires** :

- `tests/unit/test_playback_history.py` (nouveau) : ordre récent d'abord, troncature à 100, doublons conservés, `validate`.
- `tests/unit/test_playback_queue_state.py` : `insert_current` (avec et sans courant, ajouts manuels en attente conservés, révision).
- `tests/unit/test_player_service.py` : enregistrement sur suivant/précédent/`playEntry`, rien sur Repeat one ; fin de file ; `play_history_entry` garde `upcoming` ; `enqueue_history_entry` ajoute en FIFO ; entrée indisponible refusée.
- Aller-retour de session : écrire une session v2 puis la relire ; relire une session v1 existante (historique vide) ; JSON invalide rejeté. Placer ces cas dans le fichier de test qui couvre déjà `PlaybackRepository` (le chercher avec `grep -rn PlaybackRepository tests/unit`), sinon dans `tests/unit/test_playback_repository.py`.

Commit `feat(player): historique d'ecoute persistant de 100 entrees (plan 101.5)`.

### 101.6 — Tâches détaillées et page Tasks

But : savoir à tout moment ce que fait chaque tâche, combien il en reste, depuis quand, et pourquoi certains éléments ont échoué.

**Domaine** (`src/mtee/domain/jobs.py`). Ajouter à `JobStatus` : `completed: int | None = None`, `total: int | None = None`, `detail: str = ""`, `started_at: float | None = None`, `finished_at: float | None = None` (secondes epoch, `time.time()`), `failures: tuple[JobItemFailure, ...] = ()`, avec `JobItemFailure(name: str, message: str)`. Valider : `total >= 0`, `0 <= completed`, `completed <= total` quand les deux sont présents. Ajouter la fonction pure `remaining_seconds(status: JobStatus, now: float) -> float | None` : `None` si la tâche n'est pas en cours ou sans départ ; sinon, avec `completed > 0` et `total`, `écoulé / completed × (total − completed)` ; à défaut, avec `0 < progress < 1`, `écoulé / progress × (1 − progress)` ; `None` pendant les 3 premières secondes pour éviter une estimation absurde.

**Service** (`src/mtee/services/jobs.py`). `JobContext` gagne `report_items(completed: int, total: int | None, detail: str = "")` (met aussi `progress = completed / total` quand `total > 0` et qu'aucune progression plus fine n'est publiée par la tâche dans le même intervalle ; documenter la règle retenue), `report_detail(text: str)`, `report_failure(name: str, message: str)` (plafond de 500 échecs conservés, compteur total des échecs dans `detail` si dépassement). `JobService` regroupe ces publications comme la progression (minuterie de 100 ms existante), pose `started_at` dans `start()` et `finished_at` dans `finish()` et `shutdown()`, et ajoute `clear_finished() -> list[JobId]` qui retire les tâches terminales visibles de `_statuses` et émet un nouveau signal `jobsCleared(list)`.

**Modèle** (`src/mtee/models/jobs_model.py`). Nouveaux rôles : `completed` (-1 si inconnu), `total` (-1 si inconnu), `detail`, `startedAt`, `finishedAt`, `elapsedSeconds`, `remainingSeconds` (-1 si inconnu), `failures` (liste de `{name, message}`), `failureCount`, `canCancel` (état `queued` ou `running`). Propriétés `activeCount`, `finishedCount`. Slots `cancel(jobId: str)` (via `JobService.cancel`, erreur ignorée si la tâche n'existe plus) et `clearFinished()`. Une minuterie d'une seconde, active seulement quand `activeCount > 0`, émet `dataChanged` sur les rôles `elapsedSeconds` et `remainingSeconds` des lignes actives. Gérer `jobsCleared` par `beginRemoveRows`/`endRemoveRows`.

**Producteurs à instrumenter** (lire chaque site avant de le modifier ; ne pas changer leurs libellés existants sans raison) :

- Analyse : `AnalysisService.run_batch` reçoit `report_items: Callable[[int, int, str], None]` et `report_failure: Callable[[str, str], None]` (valeurs par défaut sans effet). À chaque morceau terminé, incrémenter un compteur protégé par le verrou existant et publier `(terminés, total, nom de fichier du dernier morceau commencé)` ; à chaque `report.ok` faux, publier l'échec avec le nom de fichier. Le nom de fichier vient du dépôt (`LibraryRepository.track(track_id)["filename"]` ou équivalent déjà disponible dans le service). `AnalysisModel` (`src/mtee/models/analysis_model.py`, vers la ligne 100) branche ces rappels sur le `JobContext`.
- Indexation : dans `_start_root_scan`, `report_items(fichiers vus, None, dossier courant)` à chaque lot ; issues du scan → `report_failure(chemin, message)`.
- Corbeille (`src/mtee/models/trash_model.py`, ~270), sauvegarde et annulation de métadonnées (`src/mtee/models/metadata_editor_model.py`, ~476 et ~553), import/export de playlists (`src/mtee/services/playlist_exchange.py`) : remplacer ou compléter `report_progress((index + 1) / total)` par `report_items(index + 1, total, nom)` et publier les échecs par élément quand le code les connaît déjà.
- Conversion (`src/mtee/models/conversion_queue_model.py`) : publier au moins `detail` (nom du fichier) ; compteur si la tâche traite plusieurs fichiers.

**Page Tasks.** `WorkspaceModel.openTasks()` (nouveau slot) ouvre l'onglet spécial `tasks:` intitulé « Tasks », comme `openSettings()` (`_open_special_tab`, capture et enregistrement de navigation). Chercher toutes les listes de types d'onglets spéciaux (`grep -n '"settings"\|"convert"\|settings:\|convert:' src/mtee`) dans `workspace_model.py`, `navigation_history.py`, la restauration des onglets au démarrage et `EditorGroup.qml`, et y ajouter `tasks` pour que l'onglet se restaure et participe à Back/Forward. `EditorGroup.qml` : icône d'onglet `tasks` et composant `TasksView`. `DemoWorkspace.openTasks()` équivalent. Ajouter une entrée « Tasks page » dans le menu de la barre de titre (`TitleBar.qml`, à côté de l'entrée « Tasks » existante, ligne ~186).

Créer `src/mtee/qml/views/TasksView.qml`, fond `Theme.editor`, contenu centré d'une largeur maximale de 900 px :

- en-tête comme celui d'un dossier : `SectionLabel` « Tasks », titre 28 px Bold, résumé « 2 running · 1 queued · 5 finished » en `Theme.textSecondary` ; à droite `TextButton` « Clear finished » activé si `finishedCount > 0` ;
- section « Tag conflicts (N) » réutilisant la ligne de conflit existante ;
- section « Running » (en cours et en attente), puis « Finished » (terminées, plus récentes d'abord) ;
- carte de tâche : ligne 1 libellé 14 px DemiBold, à droite état (« Running », « Queued », « Succeeded », « Failed », « Cancelled », « Interrupted » via `stateLabel`) et bouton `IconButton` `close` « Cancel » si `canCancel` ; ligne 2 en `Theme.textSecondary` 13 px, coupure au milieu : « 42 / 129 · Artist - Title.flac » si le total est connu, « 1 234 files · Folder/Sub » sinon, ou `detail` seul ; `ProgressLine` ; ligne 3 en `Theme.textMuted` 12 px : « Elapsed 2:14 · About 3 min left », ou « Finished in 4:02 », « Failed after 0:12 », « Cancelled after 1:03 » ; message d'erreur du job en `Theme.danger` ; si `failureCount > 0`, une ligne cliquable « 3 items failed » avec chevron qui déplie une liste (`ListView` de 240 px au plus) « nom — message » avec icône `alert` en `Theme.danger`.

Factoriser : déplacer les composants `ConflictRow` et `TaskRow` de `TasksPane.qml` dans `src/mtee/qml/components/TaskConflictRow.qml` et `src/mtee/qml/components/TaskRow.qml` (avec une propriété `compact`) partagés par la sidebar et la page. Formater les durées (`m:ss`, `h:mm:ss`, « About N min left », « Less than a minute left ») dans une fonction JavaScript unique du composant `TaskRow`.

`TasksPane.qml` (sidebar) : sous l'en-tête, un `TextButton` « Open Tasks page » qui appelle `openTasks()` ; conflits inchangés ; tâches actives en version compacte (libellé, ligne « 42/129 · élément » coupée au milieu, `ProgressLine`, petit bouton Cancel) ; au plus trois tâches terminées, puis « N more in the Tasks page ». Le badge de `ActivityBar.qml` ne change pas.

**Tests unitaires** :

- `tests/unit/test_jobs.py` : `report_items`/`report_detail`/`report_failure` (validation, plafond), horodatages, `clear_finished`, `remaining_seconds` (cas compteur, cas fraction, cas inconnu, 3 premières secondes) ; `JobsListModel` (rôles, `cancel`, `clearFinished`, retrait des lignes).
- Analyse : `run_batch` publie des compteurs croissants jusqu'à `total` et un échec par morceau en erreur, avec un analyseur factice (lire les tests existants qui appellent `run_batch` ou `AnalysisService` pour réutiliser leurs doublures).
- `tests/unit/test_workspace_model.py` : `openTasks` ouvre `tasks:`, Back revient à la page précédente, l'onglet se restaure après rechargement de l'état.

Commit `feat(tasks): compteurs, duree, annulation, echecs et page Tasks (plan 101.6)`.

### 101.7 — Couleur d'accent du plein écran

But : la carte prend la couleur qui couvre réellement la pochette, de façon stable, y compris blanc, gris ou noir ; le texte reste lisible en passant en sombre sur une carte claire.

**Algorithme** (réécrire `src/mtee/services/cover_palette.py`, fonction pure sur `QImage`, NumPy seulement) :

1. Réduire l'image à 64 × 64 (lissage) et convertir chaque pixel de sRGB vers OKLab (linéarisation sRGB, matrices OKLab publiées par Björn Ottosson ; L dans [0, 1]).
2. Histogramme 3D déterministe : L par pas de 0,08, a et b par pas de 0,03. Pour chaque case : effectif et moyenne OKLab.
3. Regroupement glouton déterministe : trier les cases par effectif décroissant (égalités départagées par l'indice de case) ; chaque case rejoint le premier groupe dont la moyenne pondérée est à une distance euclidienne OKLab inférieure à 0,09, sinon elle crée un groupe ; la moyenne du groupe est mise à jour en pondérant par l'effectif. Ce regroupement réunit les nuances d'une même grande zone, ce qui corrige « un petit détail l'emporte ».
4. Score de chaque groupe : `part × (1 + 0,35 × min(1, C / 0,12))`, où `part` est la fraction de pixels du groupe et `C = √(a² + b²)` la chroma OKLab. La part domine ; la légère prime de chroma ne départage que des zones de taille comparable (45 % gris contre 40 % rouge → rouge ; 70 % blanc contre 10 % rouge → blanc).
5. `base` = moyenne du meilleur groupe, reconvertie en sRGB et bornée à [0, 1]. **Aucun assombrissement, aucune exception** : une pochette blanche donne une base blanche, une noire une base quasi-noire, une grise une base grise.
6. `dark` = même couleur OKLab avec `L × 0,78` (bas du dégradé de la carte).
7. `foreground` : `#FFFFFF` ou `#0A0A0A` (`Theme.textOnColor`), celui dont le plus petit contraste WCAG avec `base` et avec `dark` est le plus élevé. `light` = vrai si `foreground` est sombre.
8. Résultat : dataclass gelée `CoverAccent(base: str, dark: str, foreground: str, light: bool)` en `#RRGGBB`. `None` seulement pour une image nulle. Une piste sans pochette (image générée) reste sans accent : c'est l'absence de pochette, pas une exception de couleur.

Conserver `contrast_with_white` si d'autres modules l'utilisent (vérifier par recherche), sinon la généraliser en `contrast_ratio(c1, c2)`. Documenter l'algorithme et ses constantes dans la docstring et dans `Decision Log`.

**Modèle.** `CoverAccentModel` (`src/mtee/models/cover_accent_model.py`) stocke un `CoverAccent | None` et expose `baseColor`, `darkColor`, `foregroundColor`, `isLight`, `hasAccent`. `PlayerModel` (repli quand aucun modèle d'accent n'est attaché) expose aussi `foregroundColor` (`"#FFFFFF"`) et `isLight` (`false`). Même chose pour le lecteur de `DemoWorkspace` s'il fournit `accent`.

**QML** (`src/mtee/qml/views/FullscreenPlayer.qml`, et seulement les éléments posés **sur la carte** colorée) :

- propriétés `onCard` (= `accent.foregroundColor` si accent, sinon `"#FFFFFF"`), `onCardStrong` (88 % d'opacité), `onCardSoft` (62 %), `onCardFaint` (35 %), animées par `ColorAnimation` de `Theme.fsAccentFade` comme `shownBase` ;
- remplacer les blancs codés en dur de la carte (`Qt.rgba(1, 1, 1, 0.88)`, `Qt.rgba(1, 1, 1, 0.62)`, `"#FFFFFF"` des icônes, survols et du bouton lecture) par ces propriétés ; le bouton lecture de la carte reste un disque `onCard` avec une icône `shownDark`, ce qui s'inverse naturellement sur une carte claire ;
- `WaveformView.qml` : ajouter `playedColor`, `unplayedColor`, `hoverAheadColor` et `playheadColor`, avec les valeurs du thème par défaut ; le plein écran passe `onCard`, `onCardFaint`, `onCardSoft`, `onCard` ;
- `TransportControls.qml`, si elle est posée sur la carte : propriété de couleur de premier plan, défaut inchangé ailleurs ;
- l'île, la page 2 et le reste de l'application ne changent pas.

**Tests unitaires** (`tests/unit/test_cover_palette.py` à réécrire, `tests/unit/test_cover_accent_model.py` à compléter) : aplat blanc → base ≈ `#FFFFFF`, `light` vrai, premier plan sombre ; aplat noir → base quasi-noire, premier plan blanc ; aplat gris moyen → base grise ; 70 % blanc + 20 % gris clair + 10 % rouge → base claire ; 45 % gris + 40 % rouge → rouge ; grande zone bleue en dégradé de nuances + 8 % de jaune saturé → bleu (régression « petit détail ») ; même image deux fois → résultat identique ; image bruitée de ±3 niveaux → distance OKLab entre résultats < 0,05 (stabilité) ; `dark` plus sombre que `base` ; contraste du premier plan ≥ 4,5 sur `base` pour ces aplats. Le modèle expose les nouvelles propriétés et garde le cache par `(track_id, generation)`.

Commit `fix(fullscreen): couleur dominante fidele a la pochette et texte adapte au fond (plan 101.7)`.

### 101.8 — En-tête de playlist façon Spotify

But : reprendre la disposition de l'en-tête de playlist de Spotify, en couleurs MTEE, sans toucher aux boutons Play et Shuffle.

**Thème** (`src/mtee/qml/Mtee/Theme.qml`) : `playlistCoverLarge: 240`, `playlistCoverCompact: 192`, `playlistCoverRadius: 6`, `playlistTitleLarge: 64`, `playlistTitleCompact: 44`, `playlistTitleMin: 32`.

**Données** (`src/mtee/models/playlists_model.py`) : ajouter dans `details()` (playlists et Liked tracks) les clés `trackCount` et `metaText`, sans changer `summary` (utilisé par la sidebar). `metaText` vient d'une fonction pure `format_playlist_meta(count: int, seconds: int) -> str` dans un module de domaine (par exemple `src/mtee/domain/durations.py`) : « 1 track », « 8 tracks, 34 min 26 sec », « 3 tracks, 10 min 43 sec », « 25 tracks, 1 hr 12 min », « 0 tracks » sans durée. `DemoWorkspace` fournit les mêmes clés.

**QML** (`src/mtee/qml/components/PlaylistHeader.qml`, réécriture de la disposition ; garder les `objectName` `playlistCoverHover`, `playlistTitleText`, `playlistPlay`, `playlistShuffle`) :

- pochette en x = 24, y = 24, de `playlistCoverLarge` (240) ou `playlistCoverCompact` (192) sous 800 px de large ; coins arrondis de 6 px par masque `MultiEffect` (reprendre le motif `coverFrame` de `FullscreenPlayer.qml`) appliqué à `PlaylistCover` (y compris la mosaïque de quatre pochettes) ; ombre douce par `MultiEffect` (`shadowEnabled`, couleur noire, opacité ~0,5, flou ~0,8, décalage vertical 8) sur un conteneur ; le voile « Change cover » au survol suit les mêmes coins ;
- bloc de texte à droite (x = pochette + 24), **aligné en bas sur le bas de la pochette** (colonne ancrée sur `cover.bottom`), espacement 8 px :
  1. « Playlist » en 13 px DemiBold `Theme.textPrimary`, casse normale, affiché aussi pour Liked tracks ;
  2. titre en `Theme.displayFontFamily`, poids `Theme.displayFontWeight`, `playlistTitleLarge`/`playlistTitleCompact`, `fontSizeMode: Text.HorizontalFit` avec `minimumPixelSize: Theme.playlistTitleMin`, une ligne, élision à droite au-delà, interlettrage légèrement négatif (environ −2 % de la taille) ; clic = édition (sauf Liked tracks), comme aujourd'hui ;
  3. description en 14 px `Theme.textSecondary`, deux lignes au plus, masquée si vide (sans laisser d'espace) ;
  4. ligne de méta : créateur en 13 px DemiBold `Theme.textPrimary`, « • », puis `metaText` en 13 px `Theme.textSecondary` ;
- rangée d'actions sous la pochette (marge de 24 px) : Play et Shuffle **identiques** (mêmes tailles, couleurs, icônes, infobulles, actions) ;
- supprimer le filet de séparation en bas de l'en-tête (l'en-tête de colonnes garde le sien) ;
- aucun dégradé ni couleur tirée de la pochette : fond `Theme.editor`.

Dans `TrackListView.qml` : la hauteur de l'en-tête de playlist suit la nouvelle disposition (24 + pochette + 24 + 56 de rangée Play + 24 ; exposer `implicitHeight` dans `PlaylistHeader` et l'utiliser plutôt que les constantes 286/330) ; les commandes de droite (recherche, List, Artwork, colonnes) sont centrées verticalement sur le bouton Play. L'en-tête des dossiers ne change pas.

**Tests unitaires** : `format_playlist_meta` (singulier, minutes et secondes, heures, zéro) ; `details()` renvoie `trackCount` et `metaText` pour une playlist et pour Liked tracks (fichier de tests des playlists existant).

Commit `feat(playlists): en-tete facon Spotify avec titre en police d'affichage (plan 101.8)`.

### Porte de revue

Mettre à jour `Progress` (cases réellement terminées), `Surprises & Discoveries` et `Decision Log`, commiter et pousser. Puis rendre compte à l'utilisateur : jalons livrés et leurs contrôles réels, commande d'ouverture des maquettes, points à vérifier visuellement (voir la matrice), et demande explicite de validation de la maquette 101.1 (y compris la variante `history-times` et la suppression du bouton `Close`). **Arrêter l'exécution ici.**

### 101.9 — Panneau droit Queue et History (après accord)

But : le panneau droit présente la file comme la page 2 du plein écran, et l'historique dans un nouvel onglet, conformément à la maquette validée.

**Factorisation** (une seule implémentation pour le plein écran et le panneau) :

- `src/mtee/qml/components/QueueTrackRow.qml` : visuel d'une ligne extrait de `QueueRow` de `FullscreenQueueCard.qml` (pochette avec voile et icône, titre, artiste, bouton « … », états survol/indisponible/courant), avec signaux `coverClicked()`, `rowDoubleClicked()`, `menuRequested(var anchor, real x, real y)` et propriétés `rowData`, `current`, `playing`, `previewHovered`, `horizontalPadding`.
- `src/mtee/qml/components/QueueList.qml` : bloc fixe « Now playing », `ListView` à sections, glisser-déposer, menu d'occurrence, état vide, gestion d'Échap pendant un glissement ; propriétés `workspace`, `horizontalPadding`, `wheelGuard` (vrai dans le plein écran pour ne pas changer de page à la molette, faux dans le panneau), `listObjectName`.
- `FullscreenQueueCard.qml` devient une `FullscreenCard` « Queue » contenant `QueueList` avec `listObjectName: "fullscreenQueueList"` (`Main.qml` s'en sert dans `queueListFocused()`), en conservant tous les `objectName` actuels (`queueRow_<id>`, `queueCurrentRow`, `queueSection_<section>`, `queueEmpty`, `queueRemove`, `queueGoTo`, `queueEditInfo`, `queueWheelGuard`, `queueCoverButton`, `queueRowMore`, `queueCoverIcon`, `queueRowTitle`, `queueNowPlaying`).
- `src/mtee/qml/components/HistoryList.qml` : intertitre et lignes `QueueTrackRow` sur `player.hasHistoryModel ? player.historyModel : player.history` ; clic pochette ou double-clic → `playHistoryEntry(historyId)` ; menu `Add to queue` (`enqueueHistoryEntry`), `Go to folder`/`Go to playlist` (`workspace.revealTrack(trackId, source)`), `Edit info` (`workspace.revealTrackForEdit(trackId, source)`) ; ligne indisponible : lecture et `Add to queue` désactivés ; état vide « Nothing played yet. ». Heure relative seulement si l'utilisateur a validé la variante `history-times`.

**Panneau** : `QueuePanel.qml` héberge `QueueList` (marges 12 px, pas de garde de molette) ; nouveau `HistoryPanel.qml` héberge `HistoryList` ; `RightPanel.qml` ajoute l'onglet `{ key: "history", label: "History" }` et le composant correspondant. Supprimer `PlaybackQueueView.qml` et son historique en texte ; consigner dans le rapport que `tests/ui/test_playback_queue_ui.py` vise `playbackQueueView`, `queueEntry_<id>` et `removeQueueAction` et devra être adapté (ne pas modifier `tests/ui/`).

**Modèles** : accepter `history` partout où `info`/`queue` sont validés (`workspace_model.py` ~139, ~2239, ~2253 ; `demo_workspace.py` ~973 ; `NavigationLocation.right_tab`) ; ajouter « History » au menu de la barre de titre à côté de « Queue » (`TitleBar.qml` ~203, `toggleRightPanel("history")`). Le bouton file de l'île continue d'ouvrir Queue.

**Tests unitaires** : `tests/unit/test_workspace_model.py` — `showRightPanel("history")` accepté, persistant, restauré, et compatible avec Back/Forward ; valeur inconnue toujours ramenée à `info`. Smoke-test QML en mode normal et en `--demo`.

Commit `feat(queue): panneau Queue repris du plein ecran et onglet History (plan 101.9)`.

### 101.10 — Menu « Add to playlist » compact (après accord)

Réécrire la présentation de `src/mtee/qml/components/AddToPlaylistMenu.qml` selon la maquette validée, en gardant intacte sa logique (`choices`, `holdsAll`, état partiel, `localIds`, `togglePlaylist`, `addToNewPlaylist`, fermeture sur `playlistCreated`, positionnement dans l'overlay borné à la fenêtre) et les `objectName` `playlistMenuSearch` et `playlistMenuEntry_<id>`. Placer les dimensions dans `Theme.qml` (`playlistMenuWidth`, `playlistMenuMaxHeight`, `playlistMenuRow`, `playlistMenuCover`). Recalculer la hauteur à partir des nouvelles tailles. Le champ de recherche prend le focus à l'ouverture ; Échap ferme. Les trois appelants (liste de pistes, île, plein écran) ne changent pas. Smoke-test QML. Commit `feat(playlists): menu Add to playlist compact (plan 101.10)`.

### 101.11 — Clôture

Créer `docs/validation/101-retours-sidebar-file-taches-playlists.md` : commandes réellement exécutées et leurs résultats, versions (Python, PySide6), échecs préexistants retrouvés, tests UI touchés par les suppressions, et la matrice de recette utilisateur ci-dessous marquée « à vérifier par l'utilisateur ». Mettre à jour les quatre sections de suivi et la ligne d'index dans `Plans d'exécution/README.md`. Commit `docs(validation): rapport du plan 101 et cloture du suivi (plan 101.11)`, push.

## Interfaces ajoutées ou modifiées

| Élément | Fichier | Contrat |
|---|---|---|
| `LibraryScanner.list_directory` | `src/mtee/services/library_scanner.py` | Liste non récursive, mêmes filtres que `scan` |
| `LibraryRepository.current_generation`, `reconcile_folder` | `src/mtee/persistence/library_repository.py` | Absences des enfants directs, gardées par la génération |
| `FolderWatchService` | `src/mtee/services/folder_watch.py` | `set_watched`, `folderChanged` temporisé, plafond 32 |
| `HistoryEntry`, `PlaybackHistory` | `src/mtee/domain/playback_history.py` | 100 entrées, récent d'abord |
| `QueueState.insert_current` | `src/mtee/domain/playback_queue.py` | Nouveau courant, `upcoming` inchangé |
| `PlayerService.play_history_entry`, `enqueue_history_entry` | `src/mtee/services/player_service.py` | Lecture immédiate, ajout FIFO |
| Session `version: 2` | `src/mtee/persistence/playback_repository.py` | Lit v1 et v2, écrit v2 |
| `PlaybackHistoryModel`, `historyModel`, `playHistoryEntry`, `enqueueHistoryEntry` | `src/mtee/models/` | Modèle Qt de l'historique |
| `JobStatus` étendu, `JobItemFailure`, `remaining_seconds` | `src/mtee/domain/jobs.py` | Compteurs, horodatages, échecs |
| `JobContext.report_items/report_detail/report_failure`, `JobService.clear_finished` | `src/mtee/services/jobs.py` | Publication regroupée à 100 ms |
| Rôles et slots de `JobsListModel` | `src/mtee/models/jobs_model.py` | `cancel`, `clearFinished`, durées |
| `WorkspaceModel.openTasks`, onglet `tasks:` | `src/mtee/models/workspace_model.py` | Page restaurable, navigable |
| `CoverAccent`, `accent_from_image` | `src/mtee/services/cover_palette.py` | Dominante OKLab sans exception |
| `foregroundColor`, `isLight` | `CoverAccentModel`, `PlayerModel` | Premier plan de la carte |
| `trackCount`, `metaText`, `format_playlist_meta` | `playlists_model.py`, domaine | Méta façon Spotify |
| Onglet `history` du panneau droit | `RightPanel.qml`, `WorkspaceModel` | Valeur persistée et navigable |

## Matrice de recette utilisateur

Ces cas sont visuels ou physiques : l'agent ne les exécute pas et les reporte dans le rapport comme à vérifier par l'utilisateur.

| Cas | Action | Résultat attendu |
|---|---|---|
| U1 | Sélectionner une ligne, cliquer sous la dernière ligne puis dans la sidebar vide | Plus aucun fond ni cadre vert ; la touche Bas sélectionne la première ligne |
| U2 | Clic simple sur un dossier replié de l'Explorer | La page s'ouvre, le dossier reste replié |
| U3 | Double-clic sur ce dossier, puis à nouveau | Il se déplie, puis se replie ; la page reste ouverte |
| U4 | Copier un gros fichier audio dans un dossier ouvert | La ligne apparaît après la fin de la copie, sans rescan |
| U5 | Supprimer puis renommer un fichier d'un dossier ouvert | La ligne disparaît puis réapparaît sous le nouveau nom |
| U6 | Ajouter un fichier dans un dossier fermé puis l'ouvrir | La ligne est présente dès l'ouverture (ou presque aussitôt) |
| U7 | Lancer une analyse de 100+ morceaux | Compteur X/N, fichier en cours, temps écoulé, estimation ; Cancel arrête |
| U8 | Page Tasks, « Clear finished », échecs dépliés | Terminées retirées ; liste des échecs lisible |
| U9 | Pochettes blanche, noire, grise, colorée avec petit détail vif | Carte blanche/noire/grise/couleur dominante ; texte lisible, sombre sur carte claire |
| U10 | Ouvrir une playlist avec et sans description | Disposition Spotify, titre ajusté, méta « • 8 tracks, 34 min 26 sec », Play/Shuffle inchangés |
| U11 | Panneau droit Queue puis History | Mêmes lignes que le plein écran ; clic pochette lit ; menus corrects |
| U12 | Fermer et rouvrir MTEE après plusieurs écoutes | L'historique est conservé |
| U13 | Bouton + d'une piste | Menu compact conforme à la maquette, bascule immédiate |

## Reprise, risques et incidents

Chaque jalon est commité séparément : une reprise commence au premier jalon non coché de `Progress`, après `git status --short` et `git log --oneline -10`. Si le smoke-test échoue après un jalon, corriger avant de passer au suivant. Si un contrat de ce plan s'avère impossible avec le code réel (par exemple `upsert_locations` qui exige une génération de scan en cours), décrire la preuve dans `Surprises & Discoveries`, choisir la variante la plus proche qui respecte le contrat utilisateur, et la consigner dans `Decision Log`. Ne jamais remplacer silencieusement la persistance de l'historique par de la mémoire, la page Tasks par la seule sidebar, ou la couleur dominante par une couleur de repli.

Risques identifiés : `QFileSystemWatcher` peut manquer des événements sur certains lecteurs (le retour au premier plan et l'ouverture couvrent ce cas) ; un rafraîchissement concurrent d'un scan complet est volontairement ignoré ; un historique de 100 snapshots augmente un peu la taille du JSON de session (quelques dizaines de Ko au plus) ; la prime de chroma de l'accent est un réglage proposé, à ajuster si l'utilisateur le demande.

## Progress

- [x] 2026-10-01 — Plan préparé à partir de la demande et de quatre séries de réponses ; état du dépôt relevé au commit `01ecd55`.
- [ ] 101.0 — Base de travail commitée et poussée.
- [ ] 101.1 — Maquettes et dossier de revue.
- [ ] 101.2 — Désélection complète.
- [ ] 101.3 — Clic et double-clic de l'Explorer.
- [ ] 101.4 — Rafraîchissement des dossiers.
- [ ] 101.5 — Historique d'écoute persistant.
- [ ] 101.6 — Tâches détaillées et page Tasks.
- [ ] 101.7 — Couleur d'accent.
- [ ] 101.8 — En-tête de playlist.
- [ ] Porte de revue : compte rendu envoyé, accord de l'utilisateur sur la maquette.
- [ ] 101.9 — Panneau Queue et History.
- [ ] 101.10 — Menu « Add to playlist » compact.
- [ ] 101.11 — Rapport de validation et clôture.

## Surprises & Discoveries

2026-10-01 — Le contour vert persistant ne vient pas de la sélection mais de l'index courant de la `ListView`, jamais remis à zéro par `clearSelection` (`TrackListView.qml`, propriété `current` des lignes).

2026-10-01 — L'historique du panneau Queue est limité à 20 entrées en mémoire ; la session persistée du plan 99 ne le contient pas.

2026-10-01 — L'algorithme d'accent rejette tout pixel de saturation inférieure à 0,25 : les pochettes achromatiques n'ont jamais d'accent, d'où la carte grise de repli constatée par l'utilisateur.

## Decision Log

2026-10-01 — Utilisateur : réponses R1 à R15 transcrites ci-dessus.

2026-10-01 — Préparation : le rafraîchissement est non récursif, comme le contenu d'un onglet de dossier, et réutilise les fonctions d'upsert du scan complet pour conserver l'identité des morceaux. Le retour de l'application au premier plan déclenche aussi un rafraîchissement des dossiers visibles, pour couvrir les événements manqués par le watcher.

2026-10-01 — Préparation : l'historique est conservé dans le JSON de session existant (version 2) plutôt que dans une nouvelle table, la session étant déjà sauvegardée de façon séquentielle et validée.

2026-10-01 — Préparation : la lecture depuis l'historique insère une nouvelle occurrence courante sans toucher à la suite, pour respecter « la file et les ajouts manuels sont conservés ».

2026-10-01 — Préparation : l'accent est calculé en OKLab avec regroupement des nuances et une légère prime de chroma ; constantes proposées, ajustables après recette.

2026-10-01 — Préparation : l'heure relative dans History est une proposition soumise dans la maquette, non une exigence.

## Outcomes & Retrospective

Non commencé. À remplir à la porte de revue puis à la clôture.

## Notes de révision

2026-10-01 — Création du plan.
