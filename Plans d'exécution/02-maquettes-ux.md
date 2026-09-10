# 02 — Prototyper et valider les trois espaces de MTEE

## Objectif et résultat observable

L'utilisateur peut examiner et manipuler trois maquettes QML détaillées, Browser, Listening view et Convert, avec leurs états significatifs, sur son écran réel. La densité, la navigation et les erreurs deviennent vérifiables avant le branchement aux fichiers audio. La décision utilisateur et les ajustements retenus sont consignés avant le début de l'explorateur fonctionnel.

Ce plan vivant suit `PLANS.md` et couvre le jalon distinct de `PLAN.md` §3. Il conserve tous les libellés de l'interface en anglais.

## Progress

- [x] (2026-09-10) Plan de maquettes préparé, aucune maquette ou approbation encore obtenue.
- [ ] Créer les données fictives et la navigation du prototype.
- [ ] Produire Browser, Listening view, Convert et leurs états particuliers.
- [ ] Vérifier dimensions, clavier, focus, petites largeurs et packaging.
- [ ] Préparer captures et parcours, puis recueillir la revue utilisateur requise.
- [ ] Appliquer les retours et consigner la décision avant tout code fonctionnel.
- [ ] Mettre à jour le suivi, créer le commit détaillé et confirmer le push.

## Surprises & Discoveries

Le document produit fournit une structure et une palette, mais pas encore des maquettes détaillées observées à l'écran. Le confort à différentes échelles Windows et les variantes visuelles restent à évaluer. Le prototype du présent plan est un livrable futur.

## Decision Log

Décision du 10 septembre 2026, Codex : employer QML et le thème réel du socle plutôt qu'un prototype web, afin de vérifier les dimensions et interactions sur la technologie de l'application. Les contenus restent fictifs et ne déclenchent aucune opération sur les fichiers de l'utilisateur.

Décision du 10 septembre 2026, Codex : présenter la revue après préparation des trois écrans et des états demandés. Cette revue est explicitement imposée par `PLAN.md` §3 ; ni le bon fonctionnement du prototype ni un test automatisé ne vaut accord utilisateur.

## Outcomes & Retrospective

Résultat attendu : maquettes examinables, spécification visuelle actualisée et revue utilisateur enregistrée. État actuel : plan seulement. Inscrire ici les choix retenus, les modifications de la palette ou densité et les éventuels points encore ouverts.

## Contexte et prérequis

Le plan 01 doit fournir une fenêtre PySide6, `src/mtee/qml/theme/Theme.qml`, Geist Sans embarquée, les commandes `--demo`, `--data-dir`, `--smoke-test` et `scripts/build_windows.ps1`. Aucun service d'exploration, lecteur natif ou FFmpeg n'est nécessaire au prototype. Adapter les noms aux fichiers réellement livrés et consigner les écarts dans ce plan.

Créer `src/mtee/demo/scenarios.py` pour les données fictives et `src/mtee/models/demo_workspace.py` pour l'état d'affichage. Les composants visuels restent sous `src/mtee/qml/` ; les états simulés sont injectés par le mode démo. Un scénario est un état reproductible du prototype que l'on ouvre par un argument, afin de revoir exactement une erreur ou une sélection multiple.

## Plan de travail et jalons

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
    uv run python -m mtee --demo --scenario browser
    uv run python -m mtee --demo --scenario browser-inspector
    uv run python -m mtee --demo --scenario browser-split
    uv run python -m mtee --demo --scenario browser-multi
    uv run python -m mtee --demo --scenario browser-no-artwork
    uv run python -m mtee --demo --scenario listening
    uv run python -m mtee --demo --scenario convert
    uv run python -m mtee --demo --scenario convert-error

Fermer une session avant de lancer la suivante, ou utiliser des répertoires de données distincts. Créer `tests/ui/test_demo_navigation.py` et `tests/unit/test_demo_scenarios.py` pour les transitions et l'absence d'accès aux services réels, puis lancer :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/ui/test_demo_navigation.py tests/unit/test_demo_scenarios.py
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --demo --scenario browser

Les tests doivent réussir et le prototype packagé présenter les mêmes scénarios. Consigner le rendu à 100 %, 125 % et 150 % de mise à l'échelle Windows, en indiquant les essais réellement possibles sur le matériel disponible.

## Validation et acceptation

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
