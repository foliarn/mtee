# 100 — Refonte du Fullscreen player et de sa waveform

## Statut et résultat attendu

Ce plan décrit la refonte complète du Fullscreen player de MTEE : une carte principale colorée d'après la pochette, une waveform détaillée à barres avec survol et scrub audio, deux « pages » séparées par une transition animée sans état intermédiaire, et une seconde page contenant une carte Artiste provisoire, une carte Track details et une carte Queue. Il est destiné à une exécution ultérieure par un modèle d'exécution (Sonnet 5.5). Sa préparation n'autorise pas l'implémentation : le jalon 100.0 prépare une maquette qui doit être validée par l'utilisateur avant tout code fonctionnel.

L'objectif fixé par l'utilisateur est que l'interface corresponde **exactement** à ses attentes. En conséquence : ne rien ajouter qui ne figure pas dans les décisions ci-dessous, ne rien retirer sans décision, et soumettre toute ambiguïté découverte pendant l'exécution à l'utilisateur au lieu de l'interpréter. Toutes les valeurs numériques de ce document (tailles, couleurs, durées, seuils) sont des **valeurs initiales de maquette** ; les valeurs définitives sont celles retenues lors de la revue 100.0 et consignées dans le Decision Log.

Sources lues le 1er octobre 2026 : `AGENTS.md`, `PLANS.md`, `Plans d'exécution/README.md`, les plans 98 et 99, et les sources du dépôt au commit `a22273b`. Les réponses de l'utilisateur sont transcrites dans ce document, qui permet donc l'exécution sans l'historique de la conversation. Le croquis de l'utilisateur et les captures SoundCloud et Spotify de référence ne sont pas versionnés ; leur contenu utile est décrit dans la section « Références visuelles ».

## Vocabulaire

- **Plein écran** : la vue `FullscreenPlayer.qml`, affichée quand `workspace.fullscreen` est vrai. Ce n'est pas le plein écran de la fenêtre Windows.
- **Page 1 / page 2** : les deux positions de défilement du plein écran. Aucun état intermédiaire stable n'existe.
- **Carte principale** : le grand rectangle arrondi de la page 1 (titre, artiste, genre, waveform, Play, cœur, +, …, pochette).
- **Île** : le composant existant `PlayerIsland.qml` (le « classic player bar » du croquis).
- **Tête de lecture** : la position audio réelle, dessinée par une ligne verticale.
- **Position survolée** : l'abscisse de la souris sur la waveform, sans clic.
- **Scrub** : l'interaction clic maintenu sur la waveform, pendant laquelle le son suit la souris.
- **Barre** : un trait vertical arrondi de la waveform. Une barre regroupe plusieurs points stockés.
- **Couleur d'accent** : la couleur extraite de la pochette de la piste jouée.

## Références visuelles (non versionnées)

**Croquis page 1** : à gauche, la barre d'activités actuelle (sidebar repliée) ; en haut, la barre de titre actuelle. En haut à gauche de la zone, « Playing from folder » puis le nom du dossier. En haut à droite, l'icône de sortie du plein écran. Au centre, une carte arrondie : en haut à gauche le titre, puis l'artiste, puis le genre ; dessous la waveform, avec à sa droite deux temps empilés séparés par un trait (position au-dessus, durée au-dessous) ; en bas à gauche un gros bouton Play rond. À droite de la carte, une pochette carrée. En bas au centre, l'île. En bas à droite, une flèche vers le bas dans un cercle.

**Croquis page 2** : en haut, le bas de la carte principale dépasse encore ; en haut à droite, l'icône de sortie et une flèche vers le haut. Deux cartes arrondies : à gauche une carte Artiste large, à droite une carte Queue. L'île reste en bas, fixe et flottante.

**Capture SoundCloud** : waveform en barres fines, espacées, arrondies. Partie jouée blanche à gauche, partie non jouée grise à droite. Au survol, la zone entre la tête de lecture et la souris prend une teinte intermédiaire. À droite, le temps courant au-dessus et la durée au-dessous. La zone assombrie sous la ligne médiane (commentaires et avatars) n'est **pas** à reproduire. Les variations de niveau sont nettement visibles, y compris dans les passages forts.

**Capture Spotify (file)** : en-tête « Titre en cours de lecture » avec la ligne courante (pochette à gauche, titre en couleur d'accent, artiste gris, bouton « … » à droite), puis « À suivre dans : Titres likés » suivi de lignes pochette + titre + artiste. Au survol, la ligne s'éclaircit et la pochette affiche un voile avec une icône Play. L'onglet « Écoutés récemment » et le bouton de fermeture ne sont **pas** à reproduire.

## Décisions confirmées par l'utilisateur

Les numéros renvoient aux deux séries de questions du 1er octobre 2026. Ils servent de références dans les jalons.

### Structure de l'écran

| Réf. | Décision |
|---|---|
| S1 | La barre d'activités reste visible à gauche ; la sidebar est masquée (comportement actuel inchangé). |
| S2 | Cliquer une icône de la barre d'activités quitte le plein écran et ouvre la sidebar. `WorkspaceModel.setActivity()` le fait déjà : vérifier, ne pas réécrire. |
| S3 | La barre de titre (contrôles de fenêtre Windows) ne change pas. |
| S4 | L'île est visible en plein écran, fixe et flottante sur les deux pages, avec le **même contenu** qu'en mode normal. |
| S5 | Les doublons (Play de la carte et Play de l'île, waveform et barre de progression de l'île) sont voulus. |
| S6 | En plein écran, le bouton plein écran de l'île devient « Exit fullscreen ». |
| S7 | En plein écran, le bouton Queue de l'île fait défiler vers la page 2. Un second clic remonte en page 1. Le bouton est actif (surligné) en page 2. |
| S8 | En haut à droite, il ne reste que l'icône de sortie. Les boutons actuels « Edit track tags » et « Queue and history » sont supprimés, ainsi que l'éditeur de tags latéral du plein écran. |
| S9 | Échap et F11 continuent de quitter le plein écran. |
| S10 | « Playing from folder/playlist » et le nom de la source restent en haut à gauche de la page 1. Seul le **nom** de la source est cliquable : il quitte le plein écran et ouvre ce dossier ou cette playlist. Ce bloc n'est pas visible en page 2. |
| S11 | Sans piste chargée, le plein écran affiche seulement un texte du type `Play a track`, sans carte ni page 2. |

### Carte principale

| Réf. | Décision |
|---|---|
| C1 | La carte principale est arrondie. L'île reste à angles droits. |
| C2 | Largeur maximale généreuse, carte centrée, marges visibles sur les côtés. La pochette disparaît quand la fenêtre devient trop étroite. |
| C3 | Pochette carrée, coins arrondis, non cliquable. Sans pochette : le motif de remplacement actuel de `CoverArt`. |
| C4 | Couleur de la carte : couleur « vibrante » de la pochette (la plus saturée parmi les couleurs fréquentes). |
| C5 | Remplissage en dégradé, de la couleur d'accent vers une version plus sombre. |
| C6 | Si la couleur est trop claire pour du texte blanc, elle est assombrie automatiquement. Le texte reste blanc. |
| C7 | Changement de piste : fondu de couleur animé, environ 1 seconde. |
| C8 | La couleur d'accent ne s'applique qu'à la carte principale et au gros bouton Play. |
| C9 | Sans pochette, ou avec une pochette sans couleur exploitable : un gris qui se détache du fond gris actuel, avec une ombre discrète sur les côtés (« 5 % max ») pour un effet flottant. |
| C10 | Le fond de page reste le gris actuel `Theme.editor`. |
| C11 | Titre trop long : défilement automatique (marquee). |
| C12 | Artiste(s) : texte brut du tag, non cliquable. |
| C13 | Genre vide : la ligne est masquée. Aucune autre information (BPM, tonalité, album, année) dans la carte principale. |
| C14 | Disposition de la rangée du bas : `| Play ........................ cœur  +  … | pochette`. Le cœur, le + et le « … » sont alignés horizontalement sur l'axe vertical du bouton Play, juste à gauche du coin inférieur gauche de la pochette. Les proportions du croquis sont indicatives. |
| C15 | Cœur = Liked tracks existants (`workspace.isLiked`/`toggleLike`). Plein et rose `Theme.secondary` quand la piste est aimée. |
| C16 | + = menu `AddToPlaylistMenu` existant, comme dans l'île, avec l'icône `check` quand la piste est déjà dans une playlist. |
| C17 | Le « … » ouvre un menu contenant : Edit info, Add to playlist…, Convert…, Analyze, Re-analyze, Show in Explorer. |
| C18 | « Edit info » quitte le plein écran, ouvre la source d'origine de la piste (dossier ou playlist), sélectionne la piste et ouvre le panneau Info. La sélection précédente est remplacée. |
| C19 | Aucune autre commande de transport dans la carte : seulement Play. |
| C20 | Play est un cercle plein. Sa couleur doit s'accorder avec la carte (blanc ou noir selon) : à choisir en revue de maquette. |
| C21 | Les états d'erreur de lecture et de waveform en génération ou indisponible sont laissés au choix du plan (voir contrat « États de la carte »). |

### Waveform

| Réf. | Décision |
|---|---|
| W1 | Barres **symétriques** autour de la ligne médiane, dans les deux sens. La capture SoundCloud ne sert qu'au style des barres et du survol. |
| W2 | Épaisseur et espacement : trois variantes à comparer dans la maquette, choix en revue. |
| W3 | Le nombre de barres dépend de la largeur affichée : espacement constant. |
| W4 | Extrémités des barres arrondies. |
| W5 | Hauteur : plus petite que sur le croquis, plus grande que l'actuelle (84 px de tracé). Valeur fixée en revue. |
| W6 | Partie jouée blanche. Partie non jouée grise, un peu plus foncée que sur SoundCloud. |
| W7 | Survol à droite de la tête de lecture : les barres entre la tête de lecture et la souris prennent une teinte intermédiaire. Survol à gauche : les barres sont blanches jusqu'à la souris, puis grises au-delà, même si la tête de lecture est plus loin. |
| W8 | Survoler sans cliquer ne déplace que la coloration et le temps affiché, jamais la tête de lecture ni le son. |
| W9 | Hauteurs calculées sur l'énergie (RMS) avec **normalisation par piste**, pour que les drops gardent leur nuance. Moins de barres qu'aujourd'hui, plus espacées. |
| W10 | Toutes les waveforms existantes seront recalculées. L'utilisateur lancera une analyse générale. |
| W11 | La waveform n'existe que dans le plein écran. |
| W12 | À droite de la waveform : deux temps empilés et séparés par un trait. En haut, le temps survolé pendant un survol ou un scrub, sinon la position de lecture ; en bas, la durée totale. |
| W13 | Suppression du badge de temps flottant qui suit la tête de lecture, de la ligne « 0:00 … durée » sous la waveform et du texte `Click waveform to seek`. |
| W14 | La tête de lecture est une ligne verticale fine sur toute la hauteur. Pas de ligne fantôme au survol. |

### Scrub

| Réf. | Décision |
|---|---|
| G1 | Un simple clic place la lecture à ce point et **joue immédiatement**, même si la piste était en pause. |
| G2 | Clic maintenu sans bouger : la lecture continue normalement depuis le point pressé. La coloration reste sous la souris, la ligne de tête de lecture avance. |
| G3 | Clic maintenu en bougeant : le son suit la souris, au plus environ toutes les 100 ms. Au-delà d'une vitesse seuil, le son est coupé ; il reprend quand la souris ralentit. |
| G4 | Au relâchement, la lecture joue, y compris si elle était en pause avant l'appui. Si la souris n'a pas bougé depuis le dernier repositionnement, rien d'autre ne se passe. |
| G5 | Clic maintenu, souris sortie par la gauche : la position est bloquée au début. Sortie par la droite : la position est bloquée à la fin, en silence ; le passage au morceau suivant a lieu **au relâchement** hors de la zone. Si la souris revient dans la zone avant le relâchement, rien n'est sauté. |
| G6 | Échap pendant un scrub n'a pas de rôle particulier. |
| G7 | Latence acceptée : « aussi instantané que possible », mesurée et consignée. |

### Pages et transition

| Réf. | Décision |
|---|---|
| P1 | Un cran de molette déclenche le passage complet et animé. Un seuil s'applique au pavé tactile. PageDown/PageUp et les flèches bas/haut changent aussi de page. |
| P2 | Animation d'environ 350 ms en décélération, réglée plus tard. |
| P3 | Flèche vers le bas en bas à droite de la page 1, flèche vers le haut en haut à droite de la page 2, sous l'icône de sortie. Toujours visibles, sans animation. |
| P4 | En page 2, environ 32 px du bas de la carte principale restent visibles en haut, sous un dégradé sombre (« vignette »). Cette zone n'est pas cliquable. |
| P5 | La molette au-dessus de la liste Queue ne fait défiler que la liste, jamais la page. |
| P6 | Rouvrir le plein écran ramène toujours en page 1. |
| P7 | En page 2, un changement de piste laisse la vue en page 2. |

### Page 2

| Réf. | Décision |
|---|---|
| D1 | Carte Artiste : placeholder uniquement. Aucune donnée, aucun lien, aucune image d'artiste n'est implémenté. |
| D2 | Carte Track details incluse : BPM, tonalité, format, bitrate, date, genre « etc. », et le **dossier d'origine**, jamais le chemin complet. La liste définitive est arrêtée en revue (voir le contrat de la carte). |
| D3 | Carte Queue : « Now playing » puis les morceaux à venir, sans historique. |
| D4 | Deux sections comme Spotify : `Next in queue` pour les ajouts manuels (masquée si vide), puis `Next from: <source>` pour la suite du contexte. |
| D5 | Ligne : pochette à gauche, titre, artiste dessous. Reproduire la capture Spotify, sans « Écoutés récemment ». |
| D6 | Un clic sur la pochette d'une ligne la joue. Au survol, la pochette reçoit le même voile avec icône Play que sur Spotify. |
| D7 | Clic droit : `Remove from queue`, ouvrir la piste dans son dossier ou sa playlist d'origine, voir ses tags (Edit info, même règle que C18). Le glisser-déposer de réordonnancement du plan 99 est disponible dans cette carte. |
| D8 | Disposition en colonnes à fixer en revue ; empilement sur fenêtre étroite. Cartes de page 2 **neutres**, non teintées. |
| D9 | Aucune autre carte que Artiste (placeholder), Track details et Queue. |

## Préparation et état du dépôt

Lire ce plan entièrement, puis `AGENTS.md`, `PLANS.md`, `PLAN.md` (addenda UX), le plan `99-controles-lecture-file-navigation.md` (contrats de file) et le plan `98-playlists-glisser-deposer-play-pause.md` (voile de pochette et bouton Play des listes). Lire aussi `33-analyse-audio.md` pour le stockage de la waveform et `28-ux-ui-waveforms.md` pour l'historique du rendu actuel.

À la préparation, la branche `main` est alignée sur `origin/main` (`a22273b`). `.gitignore`, `AGENTS.md`, `.agents/`, `.codex/` et `skills-lock.json` contiennent du travail extérieur. Plusieurs fichiers du plan 98 sont modifiés et non commités : `workspace_model.py`, `playlists_model.py`, `TrackRow.qml`, `TrackListView.qml`, `PlaylistsPane.qml`, etc. Ne jamais indexer, réécrire ni remiser (`git stash` est interdit dans ce dépôt) ce travail. Réinspecter Git au début de chaque jalon.

**Dépendance au plan 99.** La carte Queue (jalon 100.6) repose sur l'identité d'occurrence et les commandes de file du plan 99 : `entryId`, `origin`, `available`, `current` dans le modèle de file, `PlayerModel.playEntry()`, `removeQueueEntry()` et `moveQueueEntry()`. À la préparation, seule la maquette de 99 est commitée ; l'utilisateur indique que 99 sera livré avant l'exécution de 100. Au début de 100.6, vérifier que les jalons 99.1 et 99.3 sont cochés et que ces interfaces existent dans le code. Sinon, s'arrêter après 100.5 et le signaler. Les jalons 100.0 à 100.5 ne dépendent pas de 99. Le plan 99 peut avoir modifié `FullscreenPlayer.qml` ou les vues Queue : relire leur état réel avant de les réécrire.

Commencer l'exploration par le graphe code-review-graph (le mettre à jour si son SHA diffère de HEAD), puis lire les sources exactes. Le graphe ne prouve aucun comportement.

### Sources existantes vérifiées

| Fichier | Fait observé et rôle dans ce plan |
|---|---|
| `src/mtee/qml/views/FullscreenPlayer.qml` | Vue actuelle : pochette centrée, titre, artiste, éditeur de tags latéral (`fullscreenMetadataEditor`), boutons info/queue/sortie, `WaveformView`, ligne de temps, erreurs, `TransportControls`, volume. Elle est **réécrite** par ce plan. |
| `src/mtee/qml/components/WaveformView.qml` | Trois Canvas (fond, partie jouée recadrée, ligne), badge flottant `timeTag`, texte d'aide. Il lit `waveform.samples`, soit des paires float32 (low, high), et appelle `waveform.seekRatio()` au clic. Il est **réécrit** en conservant `objectName: "waveformView"`. Aucun autre fichier ne l'utilise. |
| `src/mtee/qml/components/WaveformPreview.qml` | Placeholder non utilisé. Hors périmètre : ne pas le modifier. |
| `src/mtee/qml/Main.qml` | `islandVisible` exclut le plein écran ; F11 et Échap sont gérés ici ; `FullscreenPlayer` reçoit `metadataEditor`. |
| `src/mtee/qml/components/PlayerIsland.qml` | Pochette cliquable vers le plein écran, bouton `add-playlist`/`check`, transport, `LineSlider` de progression, boutons queue, volume et plein écran. |
| `src/mtee/qml/components/TrackContextMenu.qml` | Menu de liste qui agit sur la **sélection** (`targetIds()`, `addSelectionToConvert()`). Il n'est pas réutilisable tel quel pour la piste jouée. |
| `src/mtee/qml/components/AddToPlaylistMenu.qml` | Menu d'ajout à une playlist, piloté par `trackIds`. Il est réutilisé. |
| `src/mtee/qml/Mtee/Theme.qml` | Seul emplacement des couleurs et tailles. `radius: 0`, `primary` lime `#C6FF1A`, `secondary` rose `#FF2E88`, `editor` `#18181B`, `islandHeight`, `islandMargin`. |
| `src/mtee/qml/Mtee/CoverArt.qml` | Pochette réelle par `image://artwork/<id>/<generation>/<taille>` ou motif de remplacement. |
| `src/mtee/models/artwork_provider.py`, `services/artwork_service.py` | Décodage des pochettes hors thread UI : `ArtworkService.thumbnail(path, size)` renvoie une `QImage`. `library.artwork_source(track_id)` fournit le chemin et la révision. |
| `src/mtee/domain/waveform.py` | `WaveformPoints(duration_us, lows, highs)`, `WAVEFORM_POINTS = 1200`, sérialisation `<hh>`, `packed()` en float32. |
| `src/mtee/domain/analysis.py` | `WAVEFORM_ALGORITHM_VERSION = 1`. |
| `src/mtee/services/analysis/features.py` | `_add_waveform()` accumule le min et le max de tranches de 20 ms (`WAVEFORM_BIN_FRAMES`), stéréo entrelacée. |
| `src/mtee/services/analysis/waveform.py` | `reduce_waveform()` réduit les tranches à 1200 points par `minimum.reduceat` et `maximum.reduceat`. |
| `src/mtee/persistence/analysis_repository.py` | `save_waveform()` et `load_waveform()` ; une ligne dont la version diffère est ignorée, donc recalculée. Il n'y a pas de migration à écrire pour changer le format du BLOB. |
| `src/mtee/services/analysis_service.py` | `pending(force=False)` ne teste que l'analyse BPM/tonalité (`is_current`) : une waveform périmée n'y déclenche aucun recalcul. |
| `src/mtee/services/audio_analyzer.py` | `analyze()` sans tempo ni tonalité ne calcule que la waveform. |
| `src/mtee/models/waveform_model.py` | Charge la waveform stockée ou lance son calcul (job invisible) ; propriétés `state`, `progress`, `error`, `samples` ; slots `retry()` et `seekRatio()`. |
| `src/mtee/services/player_service.py` | `seek()` borne la position et publie `seeking` ; `set_volume()` et `toggle_mute()` publient l'état ; un timer de position tourne à 100 ms. |
| `src/mtee/services/mpv_backend.py` | `seek` utilise `absolute+exact`. |
| `src/mtee/models/player_model.py` | Façade Qt : `playingId`, `playingTrack`, `playingSource`, `playingSourceKind`, `playingSourceTitle`, `position`, `playbackDuration`, `seekable`, `status`. |
| `src/mtee/models/workspace_model.py` | `setActivity()` quitte déjà le plein écran ; `setFullscreen()`, `openFolder()`, `openPlaylist()`, `selectExplorerTrack()`, `selectTrack()`, `showRightPanel()`, `showInExplorer()` (Explorateur Windows), `analyzeTracks()`, `addSelectionToConvert()`, `openConvert()`, `isLiked()`, `toggleLike()`, `playlistsContaining()`. |
| `src/mtee/persistence/library_repository.py` | La ligne de piste contient `title`, `artist`, `album`, `genre`, `bpmText`, `key`, `keyCamelot`, `format`, `codec`, `bitrateText`, `sampleRate`, `bitsPerSample`, `duration`, `size`, `year`, `path`, `coverUrl`. |
| `src/mtee/resources/icons/` | Les icônes nécessaires existent : `arrow-down`, `arrow-up`, `heart`, `heart-filled`, `more`, `add-playlist`, `check`, `play`, `pause`, `exit-fullscreen`, `queue`. |
| `src/mtee/models/demo_workspace.py` | Façade de démonstration : toute nouvelle propriété ou tout nouveau slot lu par QML doit y exister pour que `--demo` reste chargeable. |

Tests existants à lire et à adapter : `tests/ui/test_fullscreen_waveform.py`, `tests/ui/test_player_views.py`, `tests/ui/test_demo_navigation.py`, `tests/unit/test_waveform_points.py`, `tests/integration/test_analysis_repository.py`, ainsi que les tests d'analyse (`tests/unit/test_analysis*`, `tests/integration/test_analysis*`, à localiser). Exécuter ceux qui concernent le plein écran avant toute modification, pour distinguer les échecs préexistants. D'après les notes du plan 33, certains tests UI et natifs échouent déjà sur un HEAD propre.

## Contrats techniques

Les paragraphes de cette section sont des décisions de planification, pas des demandes de l'utilisateur. Ils rendent les décisions ci-dessus implémentables et testables. Toute adaptation est consignée dans le Decision Log.

### Constantes de réglage

Toutes les valeurs visuelles sont centralisées dans `Theme.qml`, dans une section commentée `// Fullscreen player (plan 100)`. Les valeurs du tableau sont des valeurs initiales ; la revue 100.0 fixe les valeurs définitives, qui sont reportées ici et dans `Theme.qml`.

| Constante `Theme` | Valeur initiale | Rôle |
|---|---|---|
| `fsCardRadius` | 16 | Rayon de la carte principale et des cartes de page 2 |
| `fsCardMaxWidth` | 1400 | Largeur maximale de la carte principale |
| `fsSideMargin` | 48, ou 6 % de la largeur si plus grand | Marge latérale minimale de la carte |
| `fsCardPadding` | 28 | Marge intérieure de la carte |
| `fsCoverHideWidth` | 820 | Largeur de carte en dessous de laquelle la pochette est masquée |
| `fsTitleSize` | 34 | Taille du titre, gras |
| `fsArtistSize` | 18 | Taille de l'artiste |
| `fsGenreSize` | 13 | Taille du genre |
| `fsMarqueeSpeed` / `fsMarqueePause` | 40 px/s / 2000 ms | Défilement du titre |
| `fsFallbackCard` | `#26262B` | Gris de carte sans couleur d'accent (C9) |
| `fsShadowOpacity` | 0.05 | Intensité de l'ombre de la carte sans couleur d'accent (C9) |
| `fsAccentFade` | 1000 ms | Fondu de couleur (C7) |
| `fsPlaySize` | 56 | Diamètre du bouton Play |
| `fsActionIconSize` / `fsActionSpacing` | 22 / 8 | Cœur, +, … |
| `waveBarWidth` / `waveBarGap` | variantes A 2/1, B 3/2, C 4/2 | W2 |
| `waveHeight` | 128 | Hauteur totale du tracé (W5) |
| `waveMinBar` | 2 | Hauteur minimale d'une barre, silence compris |
| `waveGamma` | 1.6 (variantes 1.0 / 1.6 / 2.2) | Courbe de hauteur (voir « Niveaux de barres ») |
| `wavePlayed` | `#FFFFFF` | W6 |
| `waveUnplayed` | `#7C7C82` | W6, un peu plus foncé que SoundCloud |
| `waveHoverAhead` | `#B9B9BF` | W7, teinte intermédiaire |
| `wavePlayheadWidth` | 2 | W14 |
| `waveTimeColumn` | 48 | Largeur de la colonne des deux temps (W12) |
| `fsPageDuration` | 350 ms, `Easing.OutCubic` | P2 |
| `fsWheelThreshold` | 120 (angleDelta) ou 60 px (pixelDelta) cumulés | P1 |
| `fsPageCooldown` | 200 ms après la fin de l'animation | Évite un double passage dû à l'inertie |
| `fsPeek` | 32 | Hauteur de carte visible en page 2 (P4) |
| `fsVignetteHeight` | 96 | Hauteur du dégradé sombre (P4) |
| `fsQueueRowHeight` / `fsQueueCover` | 56 / 44 | Lignes de la carte Queue |

Les seuils du scrub (100 ms entre deux repositionnements, 2000 px/s pour couper le son, 80 ms de lenteur pour reprendre, vitesse mesurée sur les 60 dernières ms) sont des constantes Python du domaine de scrub. Ils sont ajustés à l'écoute avec l'utilisateur en 100.3.

### Données de waveform : énergie RMS (W9, W10)

Passer `WAVEFORM_ALGORITHM_VERSION` à `2` dans `src/mtee/domain/analysis.py`. Les lignes version 1 sont alors ignorées par `load_waveform()` et recalculées à la demande : aucune migration SQL.

Dans `features.py`, accumuler en plus, pour chaque tranche de 20 ms, la somme des carrés des échantillons (tous canaux confondus) et le nombre d'échantillons. Exposer `waveform_sumsq` et `waveform_count` dans les features, à côté de `waveform_low` et `waveform_high`. Le découpage doit rester indépendant de la taille des blocs PCM : le test existant `test_bins_do_not_depend_on_how_the_stream_is_cut` est étendu à ces deux tableaux.

Dans `analysis/waveform.py`, `reduce_waveform()` reçoit aussi ces tableaux. Pour chaque point : `rms = sqrt(sum(sumsq) / sum(count))` sur les tranches regroupées, via `np.add.reduceat`, puis mise à l'échelle entière `0..32767`.

`WaveformPoints` reçoit un champ `rms: tuple[int, ...]` de même longueur que `lows`, chaque valeur dans `0..32767`. Le format de stockage devient `<hhH` (6 octets par point). `from_bytes` refuse toute taille non multiple de 6 ; une ancienne ligne n'est jamais relue grâce au contrôle de version. `packed()` et `samples()` disparaissent s'ils ne servent plus qu'à l'ancien `WaveformView` : le vérifier par recherche, puis adapter les tests.

L'analyse générale annoncée par l'utilisateur doit recalculer les waveforms sans exiger « Re-analyze ». Modifier `AnalysisService.pending(force=False)` : une piste est aussi en attente quand sa waveform stockée est absente ou d'une autre version. Dans `run_batch`, une piste dont l'analyse BPM/tonalité est à jour mais la waveform périmée est traitée par `analyze()` **sans** tempo ni tonalité. Seule sa waveform est alors enregistrée : aucune écriture de tags, aucune modification de BPM ou de tonalité, et les corrections manuelles restent intactes. Tester ces deux cas.

### Niveaux de barres

Créer `src/mtee/domain/waveform_levels.py` avec une fonction pure :

    bar_levels(points: WaveformPoints, bar_count: int, gamma: float) -> list[float]

Chaque barre couvre une plage contiguë de points (`floor(i * n / bar_count)` à `floor((i + 1) * n / bar_count)`, au moins un point). Son énergie vaut `sqrt(mean(rms²))` sur cette plage. On normalise ensuite par l'énergie maximale **de la piste** (W9), avec un maximum qui vaut 1. On applique `level = (energy / max) ** gamma`, puis on borne à `[0, 1]`. Une piste entièrement silencieuse donne des niveaux nuls. Si `bar_count` dépasse le nombre de points, chaque barre prend un point et la liste contient `n` valeurs.

Le gamma supérieur à 1 accentue les écarts dans les passages forts : deux sections qui diffèrent de 3 dB donnent des hauteurs nettement distinctes. C'est la réponse au constat « les drops sont saturés ». Le gamma retenu est fixé en revue.

`WaveformModel` expose `levels` (`QByteArray` de float32, un par barre) avec le signal `levelsChanged`, et le slot `setBarCount(int)`. Le calcul numpy se fait sur le thread Qt : 1200 points prennent moins d'une milliseconde, à mesurer dans un test de performance simple. Recalculer à chaque changement de points ou de nombre de barres. QML lit `levels` en `Float32Array`, comme aujourd'hui pour `samples`, sans liste Python. Le gamma est une constante Python unique, `WAVEFORM_DISPLAY_GAMMA`, que `Theme` ne duplique pas.

### Rendu de la waveform (W1–W8, W12–W14)

Réécrire `WaveformView.qml` sans changer son `objectName` : un `Canvas` pour les barres, une ligne de tête de lecture et une colonne des temps à droite. Nombre de barres : `floor((largeurTracé + gap) / (barWidth + gap))`, transmis à `waveform.setBarCount()` quand la largeur change (debounce de 50 ms). Chaque barre est un rectangle arrondi (`ctx.roundedRect`, rayon égal à la moitié de la largeur), centré verticalement. Sa hauteur vaut `max(waveMinBar, level × waveHeight)`, soit la même extension vers le haut et vers le bas (W1).

Couleur de la barre `i`, avec `x` son centre, `p` l'abscisse de la tête de lecture et `h` l'abscisse survolée ou pressée (nulle hors survol) :

| Situation | Barres blanches `wavePlayed` | Barres intermédiaires `waveHoverAhead` | Barres grises `waveUnplayed` |
|---|---|---|---|
| Pas de survol | `x ≤ p` | aucune | `x > p` |
| Survol, `h > p` | `x ≤ p` | `p < x ≤ h` | `x > h` |
| Survol, `h ≤ p` | `x ≤ h` | aucune | `x > h` |

Pendant un scrub, `h` est la position pressée (G2). La ligne de tête de lecture (`wavePlayheadWidth`, blanche, pleine hauteur) est toujours dessinée en `p`, même pendant un survol ou un scrub. Aucune ligne n'est dessinée en `h` (W14). Le Canvas n'est repeint qu'aux changements de `levels`, de `p` (tick de 100 ms), de `h` et de taille. Mesurer le temps de repeinte à 1440 px et le consigner. S'il dépasse 8 ms, découper en deux Canvas (fond et superposition) avant toute autre optimisation.

Colonne des temps à droite (W12) : deux textes alignés à droite, séparés par un trait horizontal de 1 px sur la ligne médiane. En haut, `formatTime(h)` en survol ou en scrub, sinon la position ; en bas, la durée. Chiffres tabulaires. Le format `m:ss`, ou `h:mm:ss` au-delà d'une heure, reprend l'actuel `formatTime`.

Supprimer `timeTag`, le texte d'aide du bas et toute ligne de temps sous la waveform (W13). Quand `seekable` est faux, la waveform s'affiche sans survol ni scrub, avec le curseur flèche.

### Scrub (G1–G7)

Créer le domaine pur `src/mtee/domain/scrub.py` avec une classe `ScrubSession`, sans Qt. Elle reçoit des événements horodatés en millisecondes et renvoie des **commandes** que la façade exécute, ce qui la rend entièrement testable. Ses entrées :

    press(ratio, t_ms)         # ratio brut, peut être < 0 ou > 1
    move(ratio, t_ms)
    tick(t_ms)                 # appelé par un QTimer de 20 ms pendant le scrub
    release(ratio, t_ms)

Ses commandes : `Seek(ratio)`, `Silence(on: bool)`, `EnsurePlaying`, `Next`. Règles :

- `press` émet `Seek(clamp(ratio))`, puis `EnsurePlaying` (G1). Avec un ratio initial supérieur à 1, bloquer à 1, en silence.
- `move` enregistre la position et calcule la vitesse sur les 60 dernières ms. Au-dessus de 2000 px/s (seuil exprimé en ratio par seconde, converti avec la largeur transmise à la création), émettre `Silence(True)` une seule fois et ne plus émettre de `Seek`. Sous le seuil pendant 80 ms consécutives (vérifié par `tick`), émettre `Seek` à la position courante puis `Silence(False)`. Hors silence, émettre un `Seek` au plus toutes les 100 ms, et seulement si la position a changé depuis le dernier `Seek` ; `tick` émet le `Seek` différé.
- Ratio inférieur à 0 : bloqué à 0 (G5, gauche). Ratio supérieur à 1 : état « au-delà de la fin », avec `Silence(True)` et aucun `Seek` (un seek à la durée provoquerait la fin du morceau et un changement de piste pendant le maintien). Revenir sous 1 lève cet état selon les règles ordinaires.
- `release` avec un ratio supérieur à 1 : `Silence(False)` puis `Next` (G5). Sinon, si la position a changé depuis le dernier `Seek` émis, émettre `Seek` à la position de relâchement ; puis `Silence(False)` si nécessaire et `EnsurePlaying` (G4). Maintien immobile puis relâchement : aucun `Seek` supplémentaire (G2, G4).

Façade Qt : `PlayerModel` expose `scrubPress(ratio, widthPx)`, `scrubMove(ratio)` et `scrubRelease(ratio)`, ainsi que la propriété `scrubbing`. Les horodatages viennent d'un `QElapsedTimer` côté Python, pas de QML. Exécution des commandes : `Seek` appelle `PlayerService.seek()` ; `EnsurePlaying` appelle la reprise existante si le statut n'est pas Playing ; `Next` appelle `next()`.

`Silence` utilise un nouveau `PlayerService.set_transient_silence(bool)`. Il appelle `backend.set_volume(0)` ou restaure le volume effectif (0 si l'utilisateur a coupé le son, sinon `state.volume`), **sans publier** `muted` ni `volume` : l'icône de volume de l'île ne bouge pas. Tout chargement de piste, `close()` ou erreur lève le silence transitoire.

QML : un `MouseArea` sur le tracé, `hoverEnabled`, `preventStealing: true`, qui transmet `mouse.x / width` sans borner, pour que les sorties à gauche et à droite soient vues pendant le maintien. Seul le clic gauche est accepté ; clic droit et molette ne font rien sur la waveform (la molette sert au changement de page).

Mesurer en 100.3 la latence entre `Seek` et le son réel sur WAV, FLAC et MP3 synthétiques, puis la consigner (G7). Ne pas changer le mode `absolute+exact` sans mesure montrant un gain et sans décision consignée.

### Couleur d'accent (C4–C9)

Créer `src/mtee/services/cover_palette.py`, une fonction pure sur `QImage` :

    accent_from_image(image: QImage) -> tuple[str, str] | None   # (base, dark) en "#RRGGBB"

Algorithme initial, ajustable en revue :

1. Réduire l'image à 64×64.
2. Quantifier chaque pixel en HSV : teinte en 36 cases, saturation et valeur en 4 cases chacune.
3. Ignorer les pixels de saturation inférieure à 0,25, ou de valeur hors de `[0,20 ; 0,95]`.
4. Retenir la case qui maximise `nombre_de_pixels × saturation_moyenne`. Si les pixels retenus représentent moins de 5 % de l'image, renvoyer `None` (repli C9).
5. `base` est la couleur moyenne de la case. L'assombrir par pas de 5 % de valeur jusqu'à un contraste d'au moins 4,5:1 avec le blanc (luminance relative WCAG).
6. `dark` est `base` avec une valeur HSV multipliée par 0,55.

Créer `src/mtee/models/cover_accent_model.py` (`CoverAccentModel`), rattaché au `PlayerModel` sous la propriété `accent`. Il écoute le changement de piste et calcule sur un worker (`QThreadPool` ou `JobService` invisible, selon le mécanisme le plus proche déjà utilisé pour les tâches courtes) : `library.artwork_source()`, `ArtworkService.thumbnail(path, 64)`, puis `accent_from_image()`. Un compteur de requête ignore les résultats d'une piste qui n'est plus jouée. Le cache LRU en mémoire de 256 entrées est indexé par `(track_id, generation)`, sans persistance en base : le calcul prend quelques millisecondes. Propriétés : `baseColor`, `darkColor` (chaînes) et `hasAccent`. Sans accent : `Theme.fsFallbackCard` pour les deux couleurs, et l'ombre C9 est activée.

QML : les deux arrêts du dégradé de la carte ont un `Behavior on color { ColorAnimation { duration: Theme.fsAccentFade } }` (C7). L'ombre utilise `QtQuick.Effects` (`MultiEffect` ou `RectangularShadow`). Vérifier d'abord qu'il s'importe avec `PySide6-Essentials` 6.9 ; sinon, dessiner l'ombre avec des rectangles dégradés, et consigner ce choix.

### États de la carte (C21, S11)

- Aucune piste : pas de carte, pas de page 2, pas de flèches. Un texte centré `Play a track`, en `Theme.textSecondary` à 16 px. La molette et les touches de page sont inertes. L'icône de sortie reste.
- Waveform en génération : barres au niveau `waveMinBar` en `waveUnplayed` sur toute la largeur, avec au centre le texte `Generating waveform · NN%` en `Theme.textMuted`. La colonne des temps reste affichée.
- Waveform indisponible : même fond, avec au centre le message d'erreur (ou `Waveform unavailable`) et un bouton fantôme `Retry` qui appelle `waveform.retry()`.
- Erreur de lecture (`status === "Error"`) : la zone de waveform est remplacée par le message en `Theme.danger` (élidé) suivi des boutons icône Retry et Next existants. Le reste de la carte est inchangé.

### Carte principale : disposition (C1–C3, C11–C20)

Rangée haute : titre (`MarqueeText`), artiste (`Unknown artist` si vide, comme aujourd'hui), genre masqué si vide. Puis la waveform et sa colonne de temps sur toute la largeur de la zone gauche. En bas : Play à gauche ; cœur, + et … à droite de la zone gauche, sur le même axe vertical que le centre de Play (C14). La pochette occupe la droite : carrée, de côté égal à la hauteur intérieure de la carte, coins arrondis, et masquée sous `fsCoverHideWidth` (C2). La zone gauche prend alors toute la largeur et les trois icônes restent au bord droit de la carte.

Créer `src/mtee/qml/components/MarqueeText.qml`. Quand le texte tient, il est statique. Sinon, il défile vers la gauche à `fsMarqueeSpeed` jusqu'à afficher sa fin, marque une pause de `fsMarqueePause`, revient au début à la même vitesse, puis marque de nouveau une pause. Le cycle repart au changement de texte. Le contenu est découpé (`clip`) dans la largeur disponible.

Bouton Play : cercle plein de `fsPlaySize`. L'icône `play` ou `pause` dépend de l'état du lecteur, jamais du survol ; un clic appelle `togglePlay`. Sa couleur suit la variante retenue en revue (C20) :

- A : cercle blanc, icône couleur `darkColor` ;
- B : cercle noir, icône blanche ;
- C : cercle `baseColor` éclairci, icône noire.

Cœur : icône `heart` ou `heart-filled`, couleur `Theme.secondary` si la piste est aimée, sinon blanc atténué. Le clic appelle `workspace.toggleLike(playingId)` (C15). + : même logique que l'île, `add-playlist`/`check`, qui ouvre `AddToPlaylistMenu` avec `[playingId]` (C16).

Créer `src/mtee/qml/components/PlayingTrackMenu.qml`, qui cible toujours `playingId` et jamais la sélection (C17). Ses entrées, dans l'ordre :

| Entrée | Action |
|---|---|
| `Edit info` | `workspace.revealTrackForEdit(playingId, playingSource)` (C18) |
| `Add to playlist…` | `AddToPlaylistMenu` avec `[playingId]` |
| `Convert…` | `workspace.addTracksToConvert([playingId])`, puis `openConvert()`, avec sortie du plein écran |
| `Analyze` / `Re-analyze` | `workspace.analyzeTracks([playingId], false/true)` ; on reste en plein écran |
| `Show in Explorer` | `workspace.showInExplorer(playingId)`, qui ouvre l'Explorateur Windows ; on reste en plein écran |

Nouveaux slots de `WorkspaceModel`, aussi présents dans `DemoWorkspace` :

- `revealTrackForEdit(trackId, source)` : quitte le plein écran. Si `source` est `folder:<id>`, appelle `selectExplorerTrack(trackId, id)`. Si c'est `playlist:<id>` et que la playlist existe, l'ouvre et sélectionne la ligne de ce morceau, en convertissant `trackId` vers l'identité de ligne attendue par la playlist, sans déduplication abusive (voir le plan 99). Sinon, ouvre le dossier du fichier dans la bibliothèque. Enfin, `showRightPanel("info")`. Aucune lecture n'est lancée.
- `revealTrack(trackId, source)` : même logique, sans ouvrir Info. Il sert à D7.
- `addTracksToConvert(ids)` : `conversion_model.add_tracks(localTrackIds(ids))`.
- `openPlayingSource()` : quitte le plein écran et ouvre le dossier ou la playlist de `playingSource` (S10).
- La propriété `fullscreenPage` (0 ou 1) et le slot `setFullscreenPage(int)`. `setFullscreen(True)` remet la page à 0 (P6). La propriété n'est pas persistée.

### Plein écran, île et pages (S1–S11, P1–P7)

`Main.qml` : retirer `!ws.fullscreen` de `islandVisible` ; l'île passe au-dessus de `FullscreenPlayer` (z). Ne plus transmettre `metadataEditor` à `FullscreenPlayer`.

`PlayerIsland.qml`, en plein écran seulement :

- le bouton plein écran prend l'icône `exit-fullscreen`, l'infobulle `Exit fullscreen (Esc)`, et son clic appelle `setFullscreen(false)` ;
- le bouton Queue bascule `fullscreenPage` entre 0 et 1, avec `active` égal à `fullscreenPage === 1` (S7) ;
- le clic sur la pochette ne fait rien.

Hors plein écran, l'île ne change pas.

Réécrire `FullscreenPlayer.qml` en trois couches :

1. **Défilement** : un `Item` avec `clip: true` contient une colonne dont le `y` vaut `-offset`. `offset` vaut 0 en page 1. En page 2, il vaut `bas_de_carte − fsPeek − marge_haute`, où `bas_de_carte` est l'ordonnée du bas de la carte principale dans la colonne. `Behavior on offset { NumberAnimation { duration: Theme.fsPageDuration; easing.type: Easing.OutCubic } }`. Aucun `Flickable` interactif : le glisser à la souris ne fait pas défiler.
2. **Page 1** (hauteur de la vue) : bloc « Playing from » en haut à gauche, dont seul le nom est un bouton texte appelant `openPlayingSource()` ; puis la carte principale, centrée verticalement dans la hauteur disponible au-dessus de l'île (`Theme.islandHeight + 2 × Theme.islandMargin`).
3. **Page 2** : elle commence sous la carte. Sa hauteur est `hauteur_vue − fsPeek − marge_haute − réserve_île`.
4. **Surcouches fixes**, qui ne défilent pas : l'icône de sortie en haut à droite ; la flèche haute sous celle-ci, visible en page 2 ; la flèche basse en bas à droite de la page 1, alignée sur le centre vertical de l'île ; en page 2, un dégradé `Theme.editor` opaque vers transparent sur `fsVignetteHeight`, avec un `MouseArea` qui absorbe les clics sur la zone de la carte encore visible (P4).

Changement de page : un `WheelHandler` ou `MouseArea.onWheel` sur la vue cumule `angleDelta.y` ou `pixelDelta.y`. Au seuil `fsWheelThreshold`, il appelle `setFullscreenPage(0|1)`, remet le cumul à zéro et ignore la molette jusqu'à la fin de l'animation plus `fsPageCooldown`. Les événements dont la position tombe dans la liste de la carte Queue ne sont pas traités (P5) : la liste les consomme, y compris en butée, ce qu'il faut tester. Touches (P1) : `PageDown` et `Down` vers la page 2, `PageUp` et `Up` vers la page 1, via des `Shortcut` actifs seulement en plein écran, quand `textInputFocused()` est faux et que le focus n'est pas dans la liste Queue (qui garde ses flèches). Les flèches à l'écran appellent `setFullscreenPage`. `offset` suit `fullscreenPage`, y compris quand le changement vient de l'île.

`offset` est recalculé au redimensionnement sans animation, pour ne jamais laisser la vue entre deux pages. En page 2, un changement de piste qui modifie la hauteur de la carte recalcule aussi `offset` et la vue reste en page 2 (P7).

### Page 2 : cartes (D1–D9)

Cartes neutres : fond `Theme.surface`, rayon `fsCardRadius`, en-tête en `Theme.fontSizeTitle` gras. La disposition initiale, à valider en revue (D8), dépend de la largeur de contenu disponible :

- **Large** (au moins 1100 px) : colonne gauche de 58 % avec la carte Artiste en haut (40 % de la hauteur) et la carte Track details en dessous (60 %) ; colonne droite de 42 % occupée par la carte Queue sur toute la hauteur ; écart de 20 px.
- **Étroit** : une rangée haute de hauteur fixe (180 px), avec Artiste et Track details côte à côte ; la carte Queue dessous occupe le reste. La page 2 n'a jamais de défilement propre.

`FullscreenArtistCard.qml` (D1) : en-tête `Artist`, le texte brut du tag artiste en 18 px et une ligne atténuée `Artist details will come later.`. Aucun lien, aucune image, aucune action.

`FullscreenTrackDetailsCard.qml` (D2) : une grille de deux colonnes, libellé gris et valeur blanche, alimentée par `playingTrack`. La liste de départ est donnée ci-dessous. En revue, l'utilisateur coche les champs à garder parmi ceux-ci et parmi les candidats affichés dans la maquette : `Album`, `Duration`, `Sample rate` (`sampleRate`), `Bit depth` (`bitsPerSample` si > 0), `Size` (`size`). Une valeur absente s'affiche `—`. Le dossier n'est pas cliquable.

| Libellé | Source |
|---|---|
| `BPM` | `bpmText` |
| `Key` | `key` et `keyCamelot` avec la pastille `Theme.camelotColor`, comme dans les listes |
| `Genre` | `genre` |
| `Date` | `year` |
| `Format` | `format` en majuscules, `codec` s'il diffère |
| `Bitrate` | `bitrateText` |
| `Folder` | nom du dossier parent de `path`, jamais le chemin |

`FullscreenQueueCard.qml` (D3–D7), sur le même modèle de file que le panneau Queue livré par 99 :

- Sections : `Now playing` (ligne courante) ; `Next in queue`, qui précède la suite initiale ininterrompue d'occurrences `manual` à venir et qui est masquée si cette suite est vide ; `Next from: <titre de la source du contexte>`, qui précède toutes les occurrences suivantes. Une occurrence manuelle déplacée par l'utilisateur dans la suite du contexte s'affiche à sa place réelle, sans nouvel en-tête. Si 99 a livré une autre règle de sections pour le panneau Queue, s'y aligner pour que les deux vues montrent le même ordre, et consigner ce choix.
- Ligne (`fsQueueRowHeight`) : pochette `fsQueueCover` à gauche ; titre en 14 px (couleur `Theme.primary` pour la ligne courante, blanc sinon) ; artiste en 12 px gris. Une ligne indisponible est atténuée.
- Survol d'une ligne : fond `Theme.hover` ; voile noir à 45 % sur la pochette avec l'icône `play` blanche et un fondu d'opacité court. Pour la ligne courante, le voile est visible en permanence, avec l'icône `pause` si la lecture est en cours et `play` sinon ; l'état du lecteur décide, pas le survol, comme la règle P4.2 du plan 98. Réutiliser le composant de voile créé par le plan 98 s'il existe. Un bouton `more` apparaît à droite au survol et ouvre le même menu que le clic droit.
- Clic sur la pochette : `playEntry(entryId)`, ou `togglePlay()` sur la ligne courante. Un double-clic sur la ligne a le même effet, comme le comportement existant. Le clic simple ailleurs sur la ligne ne fait rien.
- Menu (clic droit ou `more`) : `Remove from queue` (occurrences à venir seulement, `removeQueueEntry(entryId)`) ; `Go to folder` ou `Go to playlist` selon la source d'origine de l'occurrence, qui appelle `revealTrack(trackId, source)` ; `Edit info`, qui appelle `revealTrackForEdit(trackId, source)`. Si la source d'origine n'existe plus, la sortie vers le dossier du fichier s'applique.
- Glisser-déposer : identique à 99 (occurrence tenue, trait d'insertion, un seul `moveQueueEntry` au relâchement, Échap annule), réservé aux occurrences à venir. La ligne courante n'est ni déplaçable ni cible.
- La liste est un `ListView` virtualisé. Elle défile seule (P5) et reste en place quand la file change, sauf si l'élément visible en haut a disparu.

## Jalons d'exécution

Chaque jalon se termine par ses tests, la mise à jour de `Progress`, un commit détaillé et un push, conformément à `PLANS.md`. Aucun build EXE.

### 100.0 — Maquette et revue utilisateur

Créer `docs/ux/mockups/Fullscreen100Review.qml` et son lanceur `scripts/review_fullscreen_100.py`, sur le modèle de `scripts/review_queue_99.py` : mêmes imports de polices, `IconProvider`, `Theme`, options `--scene`, `--capture` et `--native`. La maquette est autonome : données fictives, horloge de lecture simulée, aucun service réel.

Contenu de la maquette :

- La page 1 complète selon les contrats, avec trois pochettes générées (couleur vive, couleur pâle, gris) pour montrer l'accent, l'assombrissement et le repli C9 avec son ombre.
- La page 2 complète (Artiste, Track details avec les champs candidats marqués comme tels, Queue avec deux sections et une ligne indisponible), avec le dégradé et la carte qui dépasse.
- La transition réelle par molette, touches, flèches et bouton Queue d'une île fictive.
- La waveform avec survol, tête de lecture, colonne des temps et scrub sur l'horloge simulée, sans son.
- Un panneau de réglage (touche `F2`) avec des curseurs pour la largeur et l'écart des barres, la hauteur, le gamma, l'intensité de l'ombre, la durée de transition et `fsPeek`, et des sélecteurs pour la variante de Play (A/B/C) et la disposition de page 2. Les valeurs courantes s'affichent pour pouvoir être recopiées.

Le lanceur accepte deux options facultatives, pour juger avec la musique de l'utilisateur :

- `--audio <fichier>` décode un fichier local avec le décodeur existant du projet et calcule dans le script un prototype min, max et RMS en 1200 points, pour que les barres montrent de vrais drops ;
- `--covers <dossier>` extrait l'accent de quelques images avec un prototype de l'algorithme de `cover_palette`.

Ces fichiers ne sont jamais copiés dans le dépôt, et les captures commitées n'utilisent que les données générées. Les prototypes du script servent de référence aux jalons suivants, mais ne sont pas importés par l'application.

Scènes et captures à produire dans `docs/ux/fullscreen-100-2026-MM-JJ/` : `page1`, `page1-long-title`, `page1-pale-cover`, `page1-no-cover`, `page1-narrow` (880×600, pochette masquée), `page1-empty`, `page1-generating`, `page1-error`, `waveform-variants` (A/B/C × gamma 1.0/1.6/2.2, sur un signal fictif avec intro, break et deux drops différant de 3 dB), `waveform-hover-ahead`, `waveform-hover-behind`, `play-variants`, `page2`, `page2-narrow`, `queue-hover-menu`. Tailles de référence : 1440×900 et 880×600.

Rédiger `docs/ux/review-100-fullscreen.md` : la correspondance de chaque capture avec les références S, C, W, G, P et D, le parcours interactif, les limites (pas de son, horloge simulée) et la liste des **décisions attendues** :

1. variante de barres ;
2. gamma ;
3. hauteur de waveform ;
4. couleurs grises ;
5. variante de Play ;
6. ombre du repli ;
7. champs de Track details ;
8. disposition de page 2 ;
9. marquee ;
10. placeholder Artiste ;
11. tailles de textes.

Commande, depuis la racine :

    uv run python scripts/review_fullscreen_100.py
    uv run python scripts/review_fullscreen_100.py --audio "<chemin local>" --covers "<dossier local>"
    uv run python scripts/review_fullscreen_100.py --capture

Vérifier les captures hors écran sans avertissement QML. Commiter la maquette, le lanceur, les captures et la revue, puis **s'arrêter et demander la validation**. Consigner les réponses dans le Decision Log, reporter les valeurs retenues dans le tableau des constantes et cocher la validation. Un silence n'est pas une validation. Si l'utilisateur demande des corrections, corriger et soumettre de nouveau.

### 100.1 — Données de waveform RMS

Implémenter le contrat « Données de waveform » et `waveform_levels.py`, avec le gamma retenu. Fichiers : `domain/analysis.py`, `domain/waveform.py`, `domain/waveform_levels.py` (nouveau), `services/analysis/features.py`, `services/analysis/waveform.py`, `services/audio_analyzer.py` si la signature change, `services/analysis_service.py`, `models/waveform_model.py`, `models/demo_workspace.py` (niveaux fictifs).

Tests :

- Étendre `tests/unit/test_waveform_points.py` : aller-retour `<hhH>`, refus des tailles non multiples de 6, RMS agrégé exact sur un signal constant et sur un sinus (RMS = amplitude/√2 à la tolérance de quantification), indépendance du découpage.
- Créer `tests/unit/test_waveform_levels.py` : normalisation par piste (maximum 1), silence, barres plus nombreuses que les points, monotonie selon le gamma, et deux sections à −3 dB d'écart dont les hauteurs diffèrent d'au moins 20 % avec le gamma retenu.
- Étendre `tests/integration/test_analysis_repository.py` : une ligne v1 est ignorée, une ligne v2 est relue.
- Tests d'analyse : `pending(False)` retient une piste dont seule la waveform est périmée ; son traitement n'écrit ni tags ni BPM ni tonalité.

### 100.2 — Rendu de la waveform

Réécrire `WaveformView.qml` selon le contrat « Rendu de la waveform », avec les constantes retenues ajoutées à `Theme.qml`. Brancher `setBarCount`. Adapter `tests/ui/test_fullscreen_waveform.py` et créer `tests/ui/test_waveform_view_100.py`.

Exposer en lecture les propriétés `hoverRatio`, `barCount` et `playheadRatio` pour tester, par la fonction de couleur extraite en JS pur (`barColor(x, p, h)`), les trois lignes du tableau. Vérifier aussi : pas de `timeTag` ni de texte d'aide, la colonne des temps en survol et hors survol, un survol qui n'appelle aucun seek (le faux backend ne reçoit rien), la durée de repeinte mesurée.

### 100.3 — Scrub

Créer `domain/scrub.py` et `tests/unit/test_scrub_session.py`. Couvrir :

- clic simple en pause (Seek puis EnsurePlaying) ;
- maintien immobile (aucun Seek supplémentaire, même après plusieurs `tick`) ;
- déplacements lents limités à un Seek par 100 ms ;
- mouvement rapide (un seul Silence(True), aucun Seek), puis ralentissement (Seek puis Silence(False)) ;
- relâchement après mouvement non encore appliqué ;
- sortie à gauche ;
- sortie à droite puis relâchement dehors (Next) ;
- sortie à droite puis retour avant relâchement (pas de Next) ;
- relâchement sans changement de position.

Ajouter `PlayerService.set_transient_silence()` et les slots de `PlayerModel`. Tester dans `tests/unit/test_player_service.py` que le silence transitoire ne publie ni `muted` ni `volume`, respecte un mute utilisateur et est levé au chargement suivant. Brancher le `MouseArea` de `WaveformView.qml`. Étendre `tests/ui/test_waveform_view_100.py` avec des pressions, déplacements et relâchements Qt simulés sur un backend enregistreur.

Recette audio depuis les sources, avec des fichiers synthétiques générés par `scripts/create_audio_fixtures.py` (WAV, FLAC, MP3 si disponibles) : mesurer la latence de seek, puis faire essayer le scrub par l'utilisateur s'il est disponible, pour ajuster les seuils. Consigner les valeurs retenues et les mesures. Sans essai utilisateur, l'indiquer comme non validé.

### 100.4 — Carte principale, couleur, île en plein écran

Créer `services/cover_palette.py`, `models/cover_accent_model.py`, `MarqueeText.qml` et `PlayingTrackMenu.qml`. Réécrire la page 1 de `FullscreenPlayer.qml`, modifier `Main.qml`, `PlayerIsland.qml`, `Theme.qml`, `WorkspaceModel` et `DemoWorkspace` (nouveaux slots et propriétés). Supprimer du plein écran l'éditeur de tags latéral et ses boutons (S8), la rangée de transport et le volume (C19), ainsi que la ligne d'erreur, déplacée dans la carte.

Tests :

- `tests/unit/test_cover_palette.py` : image vive, image pâle assombrie jusqu'au contraste 4,5:1, image grise renvoyant `None`, `dark` plus sombre que `base`.
- Dans `tests/ui/test_fullscreen_player_100.py` :
  - île visible en plein écran avec l'icône de sortie ;
  - aucun `fullscreenMetadataEditor` ;
  - clic sur l'activité Explorer qui quitte le plein écran ;
  - état `Play a track` sans piste ;
  - genre vide masqué ;
  - pochette masquée à 880 px ;
  - cœur qui bascule le like ;
  - entrées du menu `…` ciblant la piste jouée alors qu'une autre piste est sélectionnée ;
  - `Edit info` qui sélectionne la piste dans sa source et ouvre Info ;
  - `Convert…` qui ajoute la piste jouée et non la sélection ;
  - clic sur le nom de source.
- Adapter `test_player_views.py` et les tests de l'éditeur de métadonnées qui attendaient l'éditeur du plein écran : la suppression est une décision utilisateur (S8), à citer dans le Decision Log.

### 100.5 — Pages et transition

Implémenter les couches, le `fullscreenPage`, la molette, les touches, les flèches, la vignette et le bouton Queue de l'île. Tester dans `test_fullscreen_player_100.py` :

- un événement de molette de 120 donne la page 2, un second événement pendant l'animation est ignoré ;
- un cumul de pixelDelta sous le seuil ne fait rien ;
- PageDown et Up ;
- flèches ;
- bouton Queue de l'île (aller et retour, état `active`) ;
- réouverture en page 1 ;
- changement de piste en page 2 qui reste en page 2 ;
- redimensionnement en page 2 qui garde la vue alignée ;
- clic sur la vignette sans effet ;
- `offset` toujours égal à l'une des deux cibles une fois l'animation terminée.

### 100.6 — Page 2

Prérequis vérifié : les interfaces de 99. Créer `FullscreenArtistCard.qml`, `FullscreenTrackDetailsCard.qml` et `FullscreenQueueCard.qml`, les slots `revealTrack` et `revealTrackForEdit` s'ils n'existent pas encore, et les équivalents de démonstration. Tester :

- sections (manuels présents ou absents, occurrence manuelle déplacée dans le contexte) ;
- clic sur la pochette qui appelle `playEntry` avec le bon `entryId` sur un doublon ;
- ligne courante qui bascule la lecture ;
- menu (Remove absent sur la ligne courante, Go to folder ou Go to playlist, Edit info) ;
- glisser-déposer qui appelle une seule fois `moveQueueEntry` ;
- molette dans la liste en butée qui ne change pas de page ;
- champs de Track details (dossier sans chemin, valeurs absentes `—`) ;
- disposition étroite.

### 100.7 — Recette complète et livraison

Créer `docs/validation/100-plein-ecran-waveform.md` (environnement, commandes, observations, mesures, limites). Parcours Windows depuis les sources avec des fixtures synthétiques :

    uv run python scripts/create_audio_fixtures.py
    uv run python -m mtee --data-dir .local/validation/100

Exécuter la matrice de recette, puis une analyse générale sur la collection de recette pour vérifier le recalcul des waveforms (W10). Aucun build EXE.

## Matrice de recette

| Cas | Action | Résultat obligatoire |
|---|---|---|
| FS-01 | Ouvrir le plein écran pendant une lecture | Page 1, île visible avec l'icône de sortie, barre d'activités visible, sidebar et panneau droit masqués, seulement ⤡ en haut à droite. |
| FS-02 | Cliquer Explorer dans la barre d'activités | Sortie du plein écran, sidebar ouverte. |
| FS-03 | Plein écran sans piste | Texte `Play a track` seul ; molette et touches sans effet. |
| FS-04 | Cliquer le nom de la source | Sortie et ouverture du dossier ou de la playlist ; pas de nouvelle lecture. |
| FS-05 | Pistes à pochette vive, pâle, grise et sans pochette | Dégradé d'accent, accent assombri lisible, repli gris avec ombre. Fondu d'environ 1 s au changement. Play accordé. Fond de page inchangé. |
| FS-06 | Titre très long, genre vide | Marquee aller-retour avec pauses ; ligne genre absente. |
| FS-07 | Réduire à 880×600 | Pochette masquée, icônes au bord droit, rien ne se chevauche. |
| FS-08 | Cœur, +, … | Like rose, menu playlists avec coche, menu … aux six entrées ciblant la piste jouée. |
| FS-09 | Edit info depuis …, avec une autre piste sélectionnée | Sortie, piste jouée sélectionnée dans sa source, Info ouvert, lecture intacte. |
| WF-01 | Observer la waveform d'une piste à drops | Barres symétriques, arrondies, espacées selon la revue ; les variations internes des drops sont visibles. |
| WF-02 | Survoler à droite, puis à gauche de la tête de lecture | Coloration conforme au tableau ; temps du haut = temps survolé ; aucun seek, son inchangé. |
| WF-03 | Clic simple en pause | Saut au point et lecture immédiate. |
| WF-04 | Maintien immobile 3 s, puis relâchement | Le son joue depuis le point, la ligne avance, la coloration reste sous la souris ; le relâchement ne produit aucun saut. |
| WF-05 | Scrub lent, puis rapide, puis lent | Le son suit ; silence pendant le mouvement rapide ; reprise au ralentissement ; icône volume inchangée. |
| WF-06 | Sortie à gauche en maintien | Position au début. |
| WF-07 | Sortie à droite, relâchement dehors ; puis sortie à droite et retour avant relâchement | Morceau suivant dans le premier cas seulement. |
| WF-08 | Piste non seekable, waveform en génération, erreur de lecture | Pas de scrub ; états de la carte conformes. |
| WF-09 | Analyse générale sur une collection avec waveforms v1 | Waveforms recalculées en v2 ; BPM, tonalités, tags et corrections manuelles inchangés. |
| PG-01 | Un cran de molette, pavé tactile, PageDown/Up, flèches, bouton Queue de l'île | Passage animé complet à chaque fois ; jamais d'arrêt entre deux pages. |
| PG-02 | Molette sur la liste Queue, en butée haute et basse | La liste défile, la page ne change pas. |
| PG-03 | Page 2 : carte qui dépasse de 32 px sous la vignette, clic dessus | Aucun effet. |
| PG-04 | Changement de piste en page 2 ; sortie puis retour | Reste en page 2 ; retour en page 1 à la réouverture. |
| Q-01 | Ajouts manuels puis contexte | `Now playing`, `Next in queue`, `Next from: <source>` ; titre courant en lime. |
| Q-02 | Survol d'une ligne, clic sur la pochette, doublon | Voile Play ; lecture de la bonne occurrence. |
| Q-03 | Clic droit : Remove, Go to…, Edit info | Retrait de la seule occurrence ; navigation vers la source d'origine ; Info sur la piste. |
| Q-04 | Glisser une ligne à venir | Même ordre dans la carte, dans le panneau Queue et au Next suivant ; Échap annule. |
| TD-01 | Track details d'une piste complète et d'une piste sans tags | Champs retenus en revue ; dossier sans chemin ; `—` pour les absents. |

## Consigne de reprise

À utiliser pour lancer ou reprendre l'exécution :

    Lis AGENTS.md, PLANS.md et le plan 100 en entier. Exécute uniquement
    le prochain jalon non terminé de 100-plein-ecran-waveform.md.
    Vérifie les prérequis dans le code après consultation du graphe.
    Respecte les décisions S, C, W, G, P et D sans rien ajouter ni retirer.
    Si un point n'est pas couvert, demande à l'utilisateur au lieu d'interpréter.
    Au jalon 100.0, prépare la maquette puis arrête-toi pour obtenir la validation ;
    ne la suppose jamais acquise. Utilise ensuite les valeurs retenues consignées
    dans le Decision Log. Avant 100.6, vérifie que les interfaces du plan 99 existent.
    Maintiens les quatre sections de suivi, exécute les tests du jalon, note les
    limites réelles, commit détaillé et push vers origin. Ne touche pas au travail
    non commité d'autrui, ne lance jamais git stash ni le build Windows.

Si une décision est impossible avec le code actuel, décrire le cas exact et sa preuve avant de proposer une alternative. Ne pas remplacer silencieusement le scrub audio par un simple seek au relâchement, la transition animée par un défilement libre, ni l'énergie RMS par un simple rééchelonnement des pics.

## Commandes et critères de contrôle

Depuis la racine du dépôt. Les tests nouveaux sont créés aux jalons indiqués avant d'être lancés.

Référence avant modification :

    uv run pytest tests/ui/test_fullscreen_waveform.py tests/ui/test_player_views.py tests/unit/test_waveform_points.py tests/integration/test_analysis_repository.py

Après 100.1 à 100.3 :

    uv run pytest tests/unit/test_waveform_points.py tests/unit/test_waveform_levels.py tests/unit/test_scrub_session.py tests/unit/test_player_service.py tests/integration/test_analysis_repository.py tests/ui/test_waveform_view_100.py tests/ui/test_fullscreen_waveform.py

Après 100.4 à 100.6 :

    uv run pytest tests/unit/test_cover_palette.py tests/ui/test_fullscreen_player_100.py tests/ui/test_player_views.py tests/ui/test_demo_navigation.py tests/unit/test_workspace_model.py

Contrôles de code en fin de jalon :

    uv run ruff check src tests scripts
    uv run ruff format --check src tests scripts
    uv run pyright
    git diff --check

Démarrage rapide depuis les sources (il ne remplace pas le parcours interactif) :

    uv run python -m mtee --demo --smoke-test

Noter séparément les diagnostics et échecs préexistants. Ne pas réparer des modules étrangers au plan.

## Reprise, incidents et Git

À chaque interruption, mettre à jour `Progress` avec le prochain sous-jalon exact, les commandes exécutées et les décisions en attente. Aucune musique personnelle, pochette personnelle ni base de recette ne doit entrer dans Git ; les options `--audio` et `--covers` de la maquette lisent des fichiers locaux sans les copier.

Le changement de version de waveform ne modifie pas le schéma SQLite. Un retour arrière du code relirait les lignes v2 comme invalides (taille non multiple de 4) : vérifier que `load_waveform` de la version précédente les ignore sans planter. Si ce n'est pas le cas, le consigner dans Surprises & Discoveries et en informer l'utilisateur, sans modifier une migration publiée.

Avant chaque commit :

1. `git status --short`, puis ajout explicite des seuls fichiers du plan 100 ;
2. `git diff --cached --check` et relecture du diff indexé ;
3. `git fetch origin` et inspection de `HEAD...origin/main` ;
4. intégration des changements compatibles, sans push forcé.

Message multiligne via une here-string PowerShell non interpolée et `git commit --file`. Après le push, comparer `git rev-parse HEAD` et `git rev-parse origin/main`.

## Progress

- [x] 2026-10-01 — Sources du plein écran, de la waveform, de l'analyse, de l'île, des menus et des plans 98/99 inspectées au commit `a22273b`.
- [x] 2026-10-01 — Deux séries de réponses utilisateur consignées (S, C, W, G, P, D).
- [x] 2026-10-01 — Plan rédigé et contrôles documentaires effectués. Aucun code, aucun test applicatif.
- [x] 2026-10-01 — 100.0 : maquette `docs/ux/mockups/Fullscreen100Review.qml` (avec `Fs100Waveform.qml` et `Fs100Marquee.qml`), lanceur `scripts/review_fullscreen_100.py`, quinze captures dans `docs/ux/fullscreen-100-2026-10-01/` et dossier `docs/ux/review-100-fullscreen.md` préparés. Contrôles : captures hors écran sans avertissement QML, `ruff check` et `ruff format --check` sur le lanceur, `pyright` sans erreur, parcours simulé des pages (molette, touches, bouton Queue) et du scrub, essai de `--audio` et `--covers` sur des fichiers synthétiques (WAV, PNG), rendu natif d'une pochette réelle. Non observé : essai à la souris réelle par l'utilisateur.
- [ ] 100.0 — Validation utilisateur obtenue et valeurs retenues consignées. En attente : les onze décisions listées dans `docs/ux/review-100-fullscreen.md` et la ratification de ses points de découverte. Les jalons 100.1 et suivants ne démarrent pas avant.
- [ ] 100.1 — Données RMS, niveaux de barres et recalcul par l'analyse générale testés.
- [ ] 100.2 — Rendu de la waveform testé.
- [ ] 100.3 — Scrub testé, latence mesurée, seuils ajustés à l'écoute.
- [ ] 100.4 — Carte principale, couleur d'accent, île et menu testés.
- [ ] 100.5 — Pages et transition testées.
- [ ] 100.6 — Page 2 testée (prérequis 99 vérifié).
- [ ] 100.7 — Recette complète, rapport, commit et push vérifiés.

## Surprises & Discoveries

2026-10-01 — `TrackContextMenu.qml` agit sur la sélection : `Convert…` appelle `addSelectionToConvert()`. Le réutiliser pour le menu `…` convertirait la sélection au lieu de la piste jouée. D'où `PlayingTrackMenu.qml` et `addTracksToConvert()`.

2026-10-01 — `AnalysisService.pending(force=False)` ne tient pas compte de la version de la waveform. Sans modification, l'analyse générale ignorerait les waveforms v1 et seul « Re-analyze » les recalculerait, en réécrivant aussi BPM et tonalité.

2026-10-01 — `WorkspaceModel.setActivity()` quitte déjà le plein écran : la décision S2 est déjà satisfaite.

2026-10-01 — Un seek à la durée exacte déclencherait la fin du morceau pendant un maintien. La sortie par la droite est donc modélisée par un état « au-delà de la fin » sans seek, avec Next au relâchement.

2026-10-01 — Le plan 99 n'a pas encore de code à la préparation (maquette 99.0 seulement) et le plan 98 a des modifications non commitées dans des fichiers voisins (`workspace_model.py`, `TrackRow.qml`).

2026-10-01 — Jalon 100.0 : avec une colonne unique (carte puis page 2), les cartes de la page 2 sont visibles sous la carte principale dès la page 1 (constaté sur la première capture). La maquette garde les deux positions d'arrivée du contrat « Plein écran, île et pages » mais fait glisser la page 2 depuis le bas de la vue avec la progression de la transition (carte : `-progress × offset`, page 2 : de la hauteur de la vue à `fsPeek + marge_haute`). À ratifier ; sinon la page 2 devrait être masquée en page 1.

2026-10-01 — Jalon 100.0 : `Shortcut` n'accepte pas `PageDown` / `PageUp` comme séquences (les touches ne réagissaient pas) ; `PgDown` et `PgUp` fonctionnent, vérifié par des frappes simulées. À appliquer au jalon 100.5.

2026-10-01 — Jalon 100.0 : `import QtQuick.Effects` fonctionne avec PySide6 6.9.3 et `MultiEffect` masque correctement une image dans la fenêtre native ; il ne s'affiche pas avec le rendu logiciel hors écran. `ClippingRectangle` n'existe pas dans cette installation. Pour l'ombre de repli, le contrat prévoit des rectangles dégradés si l'effet pose problème ; la maquette utilise six rectangles translucides empilés, sans effet.

2026-10-01 — Jalon 100.0 : `Theme.hover` est égal à `Theme.surface`, fond des cartes neutres de la page 2 : le survol des lignes de la file y serait invisible. La maquette utilise `Theme.selection`. Une ombre noire à 5 % sur `Theme.editor` est quasi imperceptible ; `Theme.textMuted` est illisible sur une carte colorée (la maquette utilise du blanc translucide). À trancher en revue.

2026-10-01 — Jalon 100.0 : la maquette a calculé, sur un WAV synthétique (sinus d'amplitude 0,8 / 0,2 / 0,5), des valeurs RMS de 0,567 / 0,142 / 0,355, soit amplitude/√2 comme attendu ; un fichier de moins de 1200 tranches de 20 ms garde un point par tranche. Le prototype d'accent a retenu `#E0245E` sur une image unie vive, `#EADFA0` sur une image pâle, et aucune couleur sur une image grise (repli C9).

## Decision Log

2026-10-01 — Utilisateur, première série : décisions S1–S11, C1–C21, W1–W14, G1–G7, P1–P7 et D1–D9, telles que transcrites. Points notables : barres symétriques ; survol sans effet sur le son ; scrub audio avec silence au-delà d'une vitesse seuil ; suppression de l'éditeur de tags du plein écran ; carte Artiste réduite à un placeholder ; aucune autre carte que celles listées.

2026-10-01 — Utilisateur, seconde série : relâchement sans saut après un maintien immobile ; passage au suivant au relâchement hors de la zone à droite ; Edit info qui sélectionne la piste dans sa source d'origine ; bouton Queue de l'île vers la page 2 ; carte Track details avec BPM, tonalité, format, bitrate, date, genre et dossier d'origine, sans chemin ; deux sections de file comme Spotify.

2026-10-01 — Préparation : l'énergie RMS est stockée avec min/max (format v2, sans migration) et affichée avec normalisation par piste et courbe gamma. Le scrub est un domaine pur à commandes, testable sans Qt. Le silence transitoire passe par le volume du backend sans publier l'état de mute. L'accent de pochette est calculé hors thread UI avec un cache en mémoire. Les pages suivent une propriété `fullscreenPage` partagée avec l'île, sans Flickable libre. Toutes les valeurs numériques sont initiales et doivent être fixées en revue 100.0.

2026-10-01 — Sonnet 5.5 : jalon 100.0 exécuté sur le plan 100 tel quel. Choix de maquette (non produits par l'utilisateur, à valider en revue) : la hauteur de la carte découle de son contenu et la pochette en prend la hauteur intérieure ; la waveform affichée par défaut prend les barres B 3/2 et le gamma 1,6 ; les champs candidats de Track details sont marqués d'un astérisque ; la page 2 étroite place Artiste et Track details sur une rangée de 180 px ; l'île réserve 76 px de chaque côté pour la flèche du bas. Le panneau `F2` et les cartes de comparaison `waveform-variants` et `play-variants` servent à la revue et ne seront pas portés dans l'application.

## Outcomes & Retrospective

Préparation et jalon 100.0 (maquette) : ce document transcrit les décisions de l'utilisateur, décrit les contrats, les fichiers à créer ou modifier, huit jalons, les tests et une matrice de recette. Aucune fonctionnalité de l'application n'est implémentée et aucun build n'est réalisé. Le jalon 100.0 a produit la maquette, quinze captures et le dossier de revue ; la validation de l'utilisateur est en attente et bloque 100.1 à 100.7. Limites observées : maquette sans son, horloge simulée, scrub et seuils non éprouvés à la souris réelle ni à l'écoute, `--audio` et `--covers` essayés seulement sur des fichiers synthétiques, pas sur la collection de l'utilisateur.

Révision du 2026-10-01 : première rédaction après deux séries de questions.

Révision du 2026-10-01 (jalon 100.0) : maquette, lanceur, captures et dossier de revue préparés ; découvertes et choix de maquette ajoutés à Surprises & Discoveries et au Decision Log ; validation utilisateur en attente.
