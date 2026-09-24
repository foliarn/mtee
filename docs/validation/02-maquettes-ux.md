# Validation 02 — maquettes UX

## Révision 2 — 24 septembre 2026

État : prototype révisé selon l'esquisse utilisateur, revue 2 à obtenir. Les
sections suivantes, de « Environnement » à « Limites », décrivent le premier
prototype du 22 septembre, refusé en revue 1.

### Réalisation

- Fenêtre sans cadre à angles droits : `TitleBar.qml` (logo, menus File,
  Edit, View, Help, commandes de fenêtre) et `src/mtee/platform/windows_frame.py`
  (styles natifs, `WM_NCCALCSIZE`, `WM_NCHITTEST`, bouton Maximize natif pour
  Snap Layouts, `DWMWCP_DONOTROUND`).
- Barre d'activités (Explorer, Playlists, Convert, Tasks, Plugins, Profile,
  Settings), barre latérale redimensionnable, Plugins et Profile inertes.
- Éditeur à onglets, deux groupes, lignes de style Spotify (pochette générée,
  titre et artiste, album, genre, BPM, pastille Camelot, durée, ⓘ, +), tri
  par en-tête, vue Artwork, menu contextuel, menu Add to playlist.
- Panneau droit Info / Queue, îlot de lecture, Fullscreen player avec
  waveform fictive, Convert et Settings en onglets, Tasks.
- Palette Acid dans `Theme.qml` ; 41 icônes dessinées pour MTEE, teintées par
  `IconProvider` (`image://icon/<nom>/<couleur>`).
- Douze scénarios déterministes ; `DemoWorkspace` réécrit (onglets, sélection,
  file capturée dans l'ordre visible, aléatoire, répétition, sauvegarde
  simulée avec échec, Retry et Undo, playlists en mémoire).

### Commandes exécutées et résultats observés

    uv run ruff check src tests scripts        → All checks passed
    uv run ruff format --check src tests       → aucun fichier à reformater
    uv run pyright                             → 0 erreur
    uv run pytest                              → 109 passed
    pwsh -File scripts/build_windows.ps1       → build terminé, code 0
    pwsh -File scripts/smoke_packaged.ps1      → code 0
    MTEE.exe --demo --scenario explorer|fullscreen|convert-error|settings --smoke-test → code 0

Après le dernier ajustement QML (taille initiale bornée à l'écran), la
distribution a été reconstruite le 24 septembre 2026 : build en code 0,
`smoke_packaged.ps1` en code 0 et les douze scénarios packagés lancés avec
`--smoke-test` quittent tous avec le code 0.

Le chargement des douze scénarios ne produit aucun avertissement QML. Les
captures de [docs/ux/screenshots](../ux/screenshots/) ont été produites avec la
plateforme Windows de Qt, à `devicePixelRatio=1.5` (écran à 150 %), en
1440 × 900, 1280 × 720 et 1024 × 768 ; le pointeur réel est ignoré pendant la
capture. Une capture de l'exécutable packagé confirme le rendu des icônes et
de la palette.

Contrôle natif sur une vraie fenêtre (Windows 11, 150 %) : styles
`WS_THICKFRAME`, `WS_CAPTION` et `WS_MAXIMIZEBOX` présents, préférence d'angle
lue à 1 (pas d'arrondi), `WM_NCHITTEST` renvoie 13 au coin haut gauche, 10 au
bord gauche, 2 sur la zone de titre, 1 sur les menus et le bouton Close, 9 sur
Maximize et 17 au coin bas droit. Maximisée, la zone cliente occupe exactement
la zone de travail (2240 × 1328 px physiques) sans débordement.

### Limites

- Le menu Snap Layouts au survol de Maximize repose sur le code 9 vérifié
  ci-dessus ; son apparition, le glisser vers les bords et le redimensionnement
  à la souris restent à confirmer à la main pendant la revue 2.
- Les échelles 100 % et 125 % n'ont pas été observées sur cette machine.
- Lecture, écriture des tags, conversion et playlists restent simulées.

État au 22 septembre 2026 : prototype terminé, revue utilisateur à obtenir.

## Environnement

- Windows 11 Professionnel 10.0.26200, AMD64.
- Python 3.12.14 dans l'environnement uv.
- PySide6 6.9.3, Qt Quick/QML.
- Échelle observée pendant la recette : 100 %, `devicePixelRatio=1.0`.

## Réalisation

Le prototype ajoute `DemoWorkspace` et huit scénarios déterministes. Ils
injectent uniquement des dictionnaires en mémoire dans les vues ; aucun accès
à la collection, Mutagen, libmpv ou FFmpeg n'est réalisé. Browser, Listening
view et Convert partagent le thème et les composants du socle.

Les captures de référence sont sous [docs/ux/screenshots](../ux/screenshots/).
Elles couvrent les huit scénarios ainsi que les tailles 1024 × 768 et 1280 ×
720. La capture réelle a été faite avec la plateforme Windows de Qt, car la
plateforme `offscreen` ne fournit pas de police exploitable.

## Commandes exécutées

Depuis la racine du dépôt :

    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m ruff format --check .
    .\.venv\Scripts\python.exe -m pyright
    .\.venv\Scripts\python.exe -m pytest tests/unit/test_demo_scenarios.py tests/ui/test_demo_navigation.py

Les huit scénarios ont aussi été ouverts avec `--smoke-test` et ont quitté avec
le code 0. Les tests de l'étape ajoutent les scénarios déterministes, la
séparation de leur état mutable et la navigation Qt entre les trois espaces.

## Résultats observés

- Browser affiche dossiers, onglets, table, sélection, ligne en lecture et
  lecteur inférieur.
- Browser multi affiche trois sélections, `Mixed values` et l'erreur de
  sauvegarde simulée.
- La vue compacte à 1024 × 768 replie l'explorateur et conserve la table.
- Listening view masque le lecteur inférieur, conserve la file et montre la
  progression classique.
- Convert distingue l'entrée en erreur, le message d'action et la conservation
  de la source.
- Aucun recouvrement ou texte coupé n'a été retenu dans les captures finales
  1440 × 900, 1280 × 720 et 1024 × 768 ; l'inspecteur devient défilable lorsque
  la hauteur est faible.

## Limites

La revue clavier et la mise à l'échelle 125 % / 150 % n'ont pas encore été
effectuées par l'utilisateur. La décision produit est donc ouverte. La
conversion, la lecture, l'écriture des métadonnées et le dossier de sortie
restent des simulations de maquette.
