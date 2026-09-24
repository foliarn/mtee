# 02 — Prototyper et valider l'interface de MTEE

## Objectif et résultat observable

L'utilisateur peut examiner et manipuler une maquette QML détaillée de l'interface révisée le 24 septembre 2026 — fenêtre sans cadre, barre d'activités, éditeur à onglets, listes de style Spotify, panneau Info/Queue, îlot de lecture, Fullscreen player, Convert, Tasks, Playlists et Settings — avec ses états significatifs, sur son écran réel. La densité, la navigation et les erreurs deviennent vérifiables avant le branchement aux fichiers audio. La décision utilisateur et les ajustements retenus sont consignés avant le début de l'explorateur fonctionnel.

Ce plan vivant suit `PLANS.md` et couvre le jalon distinct de `PLAN.md` §3. Il conserve tous les libellés de l'interface en anglais.

## Progress

- [x] (2026-09-10) Plan de maquettes préparé, aucune maquette ou approbation encore obtenue.
- [x] (2026-09-22) Créer les données fictives et la navigation du prototype.
- [x] (2026-09-22) Produire Browser, Listening view, Convert et leurs états particuliers.
- [x] (2026-09-22) Vérifier les dimensions Qt, le focus prévu par QML, les petites largeurs et reconstruire la distribution Windows du prototype.
- [x] (2026-09-22) Préparer captures et parcours ; la revue utilisateur est prête mais pas encore recueillie.
- [ ] Appliquer les retours et consigner la décision avant tout code fonctionnel.
- [x] (2026-09-22) Mettre à jour le suivi et préparer le commit intermédiaire ; le push reste à confirmer.
- [x] (2026-09-24) Revue 1 obtenue : structure refusée, esquisse utilisateur analysée, décisions consignées dans `PLAN.md` §3, `docs/ux/specification.md` et `docs/ux/review-02.md`.
- [x] (2026-09-24) Palette A — Acid choisie par l'utilisateur.
- [x] (2026-09-24) Jalon R1 — fenêtre sans cadre, barre de titre, barre d'activités et barre latérale.
- [x] (2026-09-24) Jalon R2 — éditeur à onglets, listes de style Spotify, panneau Info/Queue.
- [x] (2026-09-24) Jalon R3 — îlot de lecture et Fullscreen player.
- [x] (2026-09-24) Jalon R4 — Convert, Tasks, Playlists, Settings, Plugins et Profile réservés.
- [x] (2026-09-24) Jalon R5 — scénarios, captures et distribution Windows ; revue 2 prête, décision utilisateur en attente.

## Surprises & Discoveries

Le document produit fournissait une structure et une palette, mais pas encore des maquettes détaillées observées à l'écran. Le prototype QML est maintenant observable ; le confort clavier, la revue utilisateur et les échelles 125 % / 150 % restent à évaluer.

Le contexte du plan 01 ne correspondait pas exactement au dépôt livré : le thème se trouve sous `src/mtee/qml/Mtee/`, et le socle possédait déjà `Main.qml`, `DemoTracksModel` et des composants de base. Le prototype réutilise ces ressources et ajoute `src/mtee/demo/`, `DemoWorkspace`, `qml/components/` et `qml/views/`.

Pendant la première capture, le contexte QML nommé `workspace` s'annulait dans les composants qui déclaraient une propriété du même nom ; les vues affichaient alors un inspecteur vide et une table sans largeur. Le shell garde désormais un alias `demoWorkspace` pour injecter explicitement le même objet dans chaque vue.

À 1280 × 720, la somme des largeurs de la rangée incluait deux espacements en plus des panneaux ; la largeur de la bibliothèque a été corrigée avant de figer les captures.

Révision du 24 septembre 2026 : les éléments créés par `Repeater` et `Loader` ne sont pas des enfants QObject de la fenêtre ; les tests UI parcourent donc l'arbre visuel (`childItems`). Qt maximise une fenêtre sans cadre en la redimensionnant à la zone de travail sans l'état « zoomé » de Windows : le test de position utilise l'état de Qt. À 150 %, la taille de référence 1440 × 900 dépasse la zone de travail (885 px logiques) : la taille initiale est bornée à l'écran disponible. Une superposition du panneau droit sous 1280 px masquait l'îlot : le panneau reste ancré et les colonnes se masquent. Le démarrage de la lecture capturait l'ordre naturel du dossier au lieu de l'ordre trié visible ; corrigé et couvert par un test.

## Decision Log

Décision du 24 septembre 2026, utilisateur (revue 1) : remplacer la structure Browser / Listening view / Convert par l'organisation de l'esquisse `docs/ux/sketches/esquisse-2026-09-24.png` : barre d'activités VS Code, onglets d'éditeur, lignes Spotify, îlot de lecture, Fullscreen player. Double-clic ou Entrée joue ; `Ctrl+I`, `Edit info` ou ⓘ ouvrent l'édition ; `+` signifie Add to playlist ; fenêtre sans cadre à angles droits ; Profile et Plugins sont des boutons réservés sans fonction ; palette Acid : gris neutres, texte blanc, primaire lime `#C6FF1A`, secondaire magenta `#FF2E88`.

Décision du 24 septembre 2026, Claude : Settings s'ouvre comme un onglet d'éditeur ; Convert possède une activité (lots) et un onglet d'éditeur (formulaire) ; Tasks remplace le bandeau `Session tasks`. La vue Artwork reste accessible par `View` pour respecter `PLAN.md` sans figurer dans l'esquisse. Les angles sont à 0 px partout, par cohérence avec la fenêtre, sauf les pastilles.

Décision du 24 septembre 2026, Claude : la barre de titre sans cadre est déplacée et redimensionnée par `QWindow.startSystemMove()` / `startSystemResize()`. Les réglages propres à Windows (désactivation des angles arrondis par `DwmSetWindowAttribute`, `WM_NCHITTEST` pour Snap Layouts sur Maximize) vivent dans un module Python `src/mtee/platform/windows_frame.py` exposé à QML par un objet dédié ; QML n'appelle aucune API système.

Décision du 10 septembre 2026, Codex : employer QML et le thème réel du socle plutôt qu'un prototype web, afin de vérifier les dimensions et interactions sur la technologie de l'application. Les contenus restent fictifs et ne déclenchent aucune opération sur les fichiers de l'utilisateur.

Décision du 10 septembre 2026, Codex : présenter la revue après préparation des trois écrans et des états demandés. Cette revue est explicitement imposée par `PLAN.md` §3 ; ni le bon fonctionnement du prototype ni un test automatisé ne vaut accord utilisateur.

Décision du 22 septembre 2026, Claude : conserver les composants du socle sous `qml/Mtee/` et créer les nouveaux composants partagés sous `qml/components/`, avec les trois vues sous `qml/views/`. Cette organisation évite de mélanger les types du module QML importé avec les maquettes qui restent des fichiers relatifs, tout en conservant le packaging récursif de `qml/`.

Décision du 22 septembre 2026, Claude : faire porter la vérité de l'état de démo par `DemoWorkspace`, plutôt que par des propriétés dispersées dans les vues. Les scénarios sont ainsi testables sans lancer une conversion ou toucher une collection, et une transition de vue conserve sélection, morceau joué et file.

Décision du 22 septembre 2026, Claude : utiliser des captures à 100 % sur l'écran disponible et enregistrer explicitement 125 % / 150 % comme revue restante. La machine de recette fournit `devicePixelRatio=1.0`; elle ne permet pas de déclarer les deux échelles supérieures observées.

## Outcomes & Retrospective

Résultat obtenu le 22 septembre 2026 : huit scénarios QML sont ouvrables avec `--demo --scenario`, Browser propose table, Artwork, dossiers, onglets, inspecteur, multisélection et panneau compact, Listening view conserve une file et masque le lecteur inférieur, et Convert montre ses réglages courants ainsi qu'une erreur relançable. Les captures sont versionnées dans `docs/ux/screenshots/`, les parcours et questions dans `docs/ux/review-02.md`, et la spécification dans `docs/ux/specification.md`.

Contrôles réalisés : ruff, format, Pyright et les tests du prototype passent ; les huit scénarios quittent avec le code 0 en `--smoke-test` ; captures réelles produites à 1440 × 900, 1280 × 720 et 1024 × 768. La distribution Windows a été reconstruite après cette passe de maquette ; les scénarios packagés `browser` et `convert-error` quittent avec le code 0. La vérification sur une machine Windows propre reste ouverte.

La revue utilisateur reste obligatoire et non obtenue. Aucune décision de palette, de densité ou de vocabulaire n'est présentée comme validée ; l'étape 03 ne doit pas commencer avant la réponse consignée dans `docs/ux/review-02.md`.

Note de révision — 2026-09-22, Claude : prototype, scénarios, captures, spécification et dossier de revue ajoutés ; revue utilisateur explicitement laissée en attente.

Résultat de la revue 1, 24 septembre 2026 : la structure du prototype est refusée ; les composants de données fictives (`DemoWorkspace`, scénarios, champs Saving/Saved/Mixed values, erreur de conversion) restent réutilisables. Le jalon n'est pas validé ; la révision R1 à R5 ci-dessous le rouvre.

Note de révision — 2026-09-24, Claude : intégration de l'esquisse utilisateur, nouveaux jalons R1 à R5, nouveaux scénarios et critères.

Résultat de la révision, 24 septembre 2026 : R1 à R5 réalisés. Douze scénarios, fenêtre sans cadre native sous Windows, 109 tests passants, ruff et Pyright propres, distribution Windows reconstruite et scénarios packagés quittant avec le code 0. Preuves dans `docs/validation/02-maquettes-ux.md`, captures dans `docs/ux/screenshots/`, parcours dans `docs/ux/review-02.md`. Distribution reconstruite après le dernier ajustement QML : les douze scénarios packagés quittent avec le code 0. La revue 2 reste à obtenir ; l'étape 03 ne commence pas avant sa décision.

## Contexte et prérequis

Le plan 01 doit fournir une fenêtre PySide6, `src/mtee/qml/theme/Theme.qml`, Geist Sans embarquée, les commandes `--demo`, `--data-dir`, `--smoke-test` et `scripts/build_windows.ps1`. Aucun service d'exploration, lecteur natif ou FFmpeg n'est nécessaire au prototype. Adapter les noms aux fichiers réellement livrés et consigner les écarts dans ce plan.

Créer `src/mtee/demo/scenarios.py` pour les données fictives et `src/mtee/models/demo_workspace.py` pour l'état d'affichage. Les composants visuels restent sous `src/mtee/qml/` ; les états simulés sont injectés par le mode démo. Un scénario est un état reproductible du prototype que l'on ouvre par un argument, afin de revoir exactement une erreur ou une sélection multiple.

## Plan de travail et jalons

### Révision du 24 septembre 2026

Les jalons R1 à R5 remplacent les jalons 1 à 4 ci-dessous, conservés comme historique du premier prototype. La référence visuelle est `docs/ux/specification.md` (révision 2) ; `PLAN.md` §3 décrit la structure. Réutiliser `DemoWorkspace`, `load_scenario`, `FieldEditor.qml` et les données fictives ; remplacer `BrowserView.qml`, `ListeningView.qml`, les onglets supérieurs et le bandeau de tâches.

**R1 — Fenêtre et navigation.** Créer `qml/components/TitleBar.qml`, `ActivityBar.qml`, `SideBar.qml` et le module `src/mtee/platform/windows_frame.py`. Fenêtre sans cadre, menus `File`, `Edit`, `View` fictifs, commandes de fenêtre, déplacement, double-clic de maximisation, redimensionnement par les bords, angles droits sous Windows 11 et Snap Layouts. Les activités Plugins et Profile affichent `Coming later`. Appliquer la palette Acid dans `Theme.qml`.

**R2 — Éditeur et édition.** Créer `EditorArea.qml`, `EditorTabs.qml`, `TrackList.qml` (lignes Spotify, en-tête de dossier, pastilles Camelot, `+`, ⓘ au survol) et `RightPanel.qml` avec Info et Queue. Double-clic et Entrée jouent fictivement ; `Ctrl+I`, `Edit info` et ⓘ ouvrent Info. Conserver les états Saving, Saved, Could not save, Retry, Undo et Mixed values. Deux groupes au maximum ; vue Artwork accessible par `View`.

**R3 — Lecture.** Créer `PlayerIsland.qml` et `FullscreenPlayer.qml`. L'îlot flotte au-dessus de l'éditeur, se masque par `View › Player island`, ouvre Queue et Fullscreen player. Fullscreen player garde la barre d'activités, masque le reste, affiche la source, la pochette, l'identité, un emplacement de waveform avec progression et le transport ; `Esc` restaure l'état.

**R4 — Activités secondaires.** Adapter `ConvertView.qml` en onglet d'éditeur et créer la barre latérale Convert (lots), `TasksPane.qml`, `PlaylistsPane.qml` fictif et `SettingsView.qml` (au minimum l'affichage de l'îlot).

**R5 — Revue 2.** Mettre à jour les scénarios, les tests, les captures à 1440 × 900, 1280 × 720 et 1024 × 768, la distribution Windows et `docs/ux/review-02.md`, puis présenter la revue 2.

Scénarios de la révision : `explorer`, `explorer-info`, `explorer-split`, `explorer-multi`, `explorer-no-artwork`, `playing-queue`, `fullscreen`, `convert`, `convert-error`, `tasks`, `playlists`, `settings`. Les anciens noms (`browser`, `listening`…) sont retirés.

### Historique — premier prototype (22 septembre 2026)

### Jalon 1 — Dessiner Browser et la disposition

Créer `qml/views/BrowserView.qml`, `qml/components/ExplorerPane.qml`, `TabGroup.qml`, `TrackTable.qml`, `ArtworkGrid.qml`, `MetadataInspector.qml` et `PlayerBar.qml`. Le socle `Main.qml` assemble un explorateur à gauche, deux groupes d'onglets au maximum au centre, un inspecteur replié par défaut et le lecteur en bas. Les onglets sont fermables et la division verticale sépare les groupes côte à côte.

La vue Table affiche d'abord Title, Artist, Genre, BPM et Key ; Duration, Format et Filename sont activables. Simuler tri, redimensionnement et réorganisation de colonnes. La vue Artwork affiche une entrée par fichier avec pochette, titre et artiste ; une illustration neutre remplace la pochette absente. Créer un jeu fictif avec chemins accentués, titres longs, tags manquants et sélections multiples. Distinguer visuellement survol, sélection, lecture et focus clavier.

La taille de référence est 1440 × 900, police 14 px, lignes de table 36 px et palette du socle. Tester aussi 1024 × 768 et 1280 × 720 comme cas de recette proposés. Quand deux groupes ne tiennent plus, replier les panneaux secondaires et montrer un groupe à la fois avec un contrôle pour retrouver l'autre ; conserver ses onglets et sa sélection. Aucun écran ne perd son contenu lors de ce changement.

### Jalon 2 — Donner un comportement cohérent à Listening view

Créer `qml/views/ListeningView.qml`. Afficher grande pochette, titre, artiste, métadonnées éditables fictives et barre de progression occupant l'espace de la future waveform. La waveform sera réellement ajoutée au plan 08 ; aucun calcul audio n'est attendu ici. Un bouton Listening view bascule vers cet espace, masque le lecteur inférieur et conserve le même état fictif de morceau, de position et de file.

Le retour restaure les onglets, la division et la sélection. Un clic change la sélection, un double-clic désigne le morceau fictivement joué. L'inspecteur suit la sélection, Listening view le morceau joué. La file est un instantané de l'ordre au lancement : modifier un tri ne la reconstruit pas. Espace agit sur lecture/pause sauf pendant la saisie.

Simuler l'enregistrement à validation du champ ou perte de focus, avec Saving, Saved et Could not save. Une erreur conserve la saisie et offre Retry ; Undo restaure la valeur précédente. En sélection multiple, Mixed values n'est jamais écrit comme une valeur : modifier un seul champ ne change que celui-ci dans les fiches fictives. Ces interactions préparent leur implémentation, sans toucher un fichier réel.

### Jalon 3 — Maquetter Convert et les erreurs

Créer `qml/views/ConvertView.qml` avec liste d'entrées, ajout fictif de fichiers ou de la sélection, formats, codec, qualité, fréquence, canaux, profondeur si pertinente, dossier de sortie et commandes de lot. Les réglages supplémentaires sont dans Advanced. Afficher progression par entrée, résumé du lot, Cancel pending et Open output folder. Ce dernier reste simulé dans la démo.

Utiliser des combinaisons fictives explicitement marquées comme démonstration, sans prétendre refléter les capacités d'un FFmpeg non installé. Une erreur de sortie permet de comprendre quelle entrée a échoué et comment la relancer. L'original est conservé et un nom déjà présent n'est jamais présenté comme écrasé silencieusement. Préparer un état `convert-error` avec message lisible, progression partielle et action Retry.

### Jalon 4 — Préparer et obtenir la revue

Ajouter à l'entrée applicative `--scenario` avec les valeurs `browser`, `browser-inspector`, `browser-split`, `browser-multi`, `browser-no-artwork`, `listening`, `convert`, `convert-error`, utilisables avec `--demo`. Créer `docs/ux/review-02.md` décrivant les parcours et les décisions attendues, `docs/ux/specification.md` pour les règles résultantes et des captures de référence sous `docs/ux/screenshots/`. Ne versionner que des données et images fictives dont la redistribution est permise.

Examiner le prototype et corriger les chevauchements, textes coupés et focus invisibles avant la présentation. L'utilisateur examine densité sur son écran, équilibre pochette/progression/métadonnées, commandes en panneau divisé, sauvegarde automatique et options/erreurs de conversion. Enregistrer sa réponse datée, puis appliquer les changements et présenter les points modifiés si nécessaire. La validation ouvre l'étape 03 ; si elle n'est pas donnée, documenter le prototype terminé et la revue en attente sans déclarer le jalon validé.

## Étapes concrètes

Depuis `C:/Users/flori/Desktop/dev/MTEE`, après création des composants et du sélecteur de scénarios :

    uv sync --locked
    uv run python -m mtee --demo --scenario explorer
    uv run python -m mtee --demo --scenario explorer-info
    uv run python -m mtee --demo --scenario explorer-split
    uv run python -m mtee --demo --scenario explorer-multi
    uv run python -m mtee --demo --scenario explorer-no-artwork
    uv run python -m mtee --demo --scenario playing-queue
    uv run python -m mtee --demo --scenario fullscreen
    uv run python -m mtee --demo --scenario convert
    uv run python -m mtee --demo --scenario convert-error
    uv run python -m mtee --demo --scenario tasks
    uv run python -m mtee --demo --scenario playlists
    uv run python -m mtee --demo --scenario settings

Les captures de référence se régénèrent avec `uv run python scripts/capture_ux_scenario.py <scénario> docs/ux/screenshots/<scénario>.png [largeur hauteur]`.

Fermer une session avant de lancer la suivante, ou utiliser des répertoires de données distincts. Créer `tests/ui/test_demo_navigation.py` et `tests/unit/test_demo_scenarios.py` pour les transitions et l'absence d'accès aux services réels, puis lancer :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/ui/test_demo_navigation.py tests/unit/test_demo_scenarios.py tests/unit/test_windows_frame.py tests/unit/test_icon_provider.py
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --demo --scenario explorer

Les tests doivent réussir et le prototype packagé présenter les mêmes scénarios. Consigner le rendu à 100 %, 125 % et 150 % de mise à l'échelle Windows, en indiquant les essais réellement possibles sur le matériel disponible.

## Validation et acceptation

Pour la révision du 24 septembre 2026 : les douze scénarios sont ouvrables ; la fenêtre sans cadre se déplace, se redimensionne, s'ancre et garde des angles droits ; chaque activité change la barre latérale, Plugins et Profile restant inertes ; double-clic et Entrée jouent sans ouvrir Info ; `Ctrl+I`, `Edit info` et ⓘ ouvrent Info sans lancer la lecture ; l'îlot ne masque aucune ligne et disparaît dans Fullscreen player ; `Esc` restaure onglets, division, panneau droit et sélection. Les critères ci-dessous restent valables en remplaçant Browser par Explorer et Listening view par Fullscreen player.

Les huit scénarios sont directement ouvrables. Browser possède les colonnes et commandes demandées ; l'inspecteur est fermé au départ ; les deux groupes se retrouvent après réduction et restauration de la fenêtre. La grille ne regroupe pas les morceaux par album. À tout instant, sélection et lecture peuvent viser deux morceaux distincts.

Passer de Browser à Listening view puis revenir conserve position fictive, file, onglets, division et sélection ; le lecteur inférieur n'est pas dupliqué. Saisir dans un champ et appuyer sur Espace ne déclenche pas la lecture. Un scénario de sauvegarde échouée garde le texte et ne montre pas Saved ; la multisélection conserve les champs non modifiés. La conversion en erreur reste compréhensible sans journal technique.

Les tests démontrent surtout les transitions et l'isolation du mode démo, sans imposer une comparaison pixel à pixel fragile. La recette humaine vérifie dimensions, lisibilité, clavier et mise à l'échelle. Le critère final est une revue utilisateur explicitement consignée dans `docs/ux/review-02.md`, avec les ajustements intégrés à la spécification. Un accord partiel identifie les points acceptés et ceux restant ouverts.

## Reprise et réexécution

Chaque scénario recrée un état fictif connu, sans persistance dans la collection réelle. Les corrections visuelles modifient les composants partagés et leurs captures de référence après examen. Si une interaction de démonstration diverge du produit, corriger scénario et spécification ensemble. Ne pas employer les stubs de démo comme preuve du bon fonctionnement futur d'un service audio.

Une revue en attente n'empêche pas de terminer les maquettes, de corriger leurs défauts ou de pousser un commit intermédiaire. Elle empêche seulement de considérer le jalon comme validé et de commencer l'explorateur fonctionnel dépendant. Ne pas demander une revue sur des captures manquantes ou des écrans incomplets.

## Interfaces et dépendances

`DemoWorkspace` expose dossiers, onglets, sélection, morceau joué, file, état des champs et état des conversions aux vues. `load_scenario(name)` remplace l'ensemble par un état déterministe. Les actions de démonstration restent en mémoire ; elles n'appellent pas `MetadataWriter`, un système de fichiers, libmpv ou FFmpeg.

Les vues partagent le thème et les composants avec la future application, mais reçoivent leurs données par modèles. PySide6 suffit au prototype et pytest-qt aux essais Qt. Le mode réel du socle demeure disponible ; sa construction Windows inclut aussi les ressources de démonstration et leurs licences.

## Preuves et livraison Git

Créer `docs/validation/02-maquettes-ux.md` avec parcours réalisés, captures, dimensions, échelles, limites et référence de la décision utilisateur. Mettre le plan à jour et vérifier les fichiers fictifs avant indexation :

    git status --short
    git diff --check
    git add -- src/mtee tests/ui/test_demo_navigation.py tests/unit/test_demo_scenarios.py docs/ux docs/validation/02-maquettes-ux.md "Plans d'exécution/02-maquettes-ux.md"
    git diff --cached --check
    git diff --cached

Après une revue effectivement validée, adapter ce message aux changements et preuves réels ; utiliser un sujet « préparer » pour un commit intermédiaire en attente de revue :

    $message = @'
    feat(ux): valider les maquettes QML de navigation écoute et conversion

    Ajouter les trois écrans et les états inspecteur, panneau divisé,
    multisélection, absence de pochette et erreur de conversion.
    Simuler sélection, lecture, sauvegarde et file sans accès aux fichiers réels.
    Intégrer les retours de revue dans la spécification visuelle versionnée.

    Validation : préciser les scénarios, essais clavier et échelles Windows,
    tests de transitions et date de la décision utilisateur obtenue.
    Limites : données fictives, lecture et conversion non implémentées.
    '@
    $messagePath = Join-Path $env:TEMP 'mtee-02-commit.txt'
    Set-Content -LiteralPath $messagePath -Value $message -Encoding utf8
    git commit --file $messagePath
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Confirmer l'égalité des hashes avant d'annoncer le push. Les conflits et pannes réseau suivent la procédure de `PLANS.md`, sans force. Ne pas consigner son propre hash dans le commit.

Note de révision — 2026-09-10, Codex : création du jalon de revue autonome pour préserver l'exigence de validation visuelle avant développement fonctionnel.
