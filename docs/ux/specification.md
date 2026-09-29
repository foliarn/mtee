# Spécification visuelle MTEE — prototype 02, révision 2

Révision du 24 septembre 2026. Elle remplace la première version (Browser /
Listening view / Convert en onglets supérieurs, palette bleue, panneaux
arrondis) à partir de l'esquisse de l'utilisateur :
[sketches/esquisse-2026-09-24.png](sketches/esquisse-2026-09-24.png).

## Direction

MTEE emprunte la navigation de VS Code et la lecture de Spotify : une fenêtre
sans cadre, à angles droits, en gris sombres neutres, avec une couleur primaire
vive réservée à l'action, au focus et au morceau en lecture. L'interface reste
épurée : pas de cartes décoratives, pas de dégradés, séparations par valeurs de
gris plutôt que par bordures épaisses. Elle doit rester utile avec une
collection longue, un chemin accentué ou une métadonnée absente.

## Palette

Palette **A — Acid**, choisie par l'utilisateur le 24 septembre 2026 parmi
quatre propositions (B Toxic, C Volt et D Cyber écartées). Chrome plus sombre
que la zone d'éditeur, gris neutres, texte blanc, primaire lime, secondaire
magenta.

| Rôle | Valeur |
|---|---|
| Titre / activités | `#0B0B0C` |
| Barre latérale | `#111113` |
| Éditeur (fond général) | `#18181B` |
| Surface (îlot, survol) | `#212125` |
| Sélection | `#2A2A30` |
| Séparateur | `#2E2E33` |
| Texte principal | `#FFFFFF` |
| Texte secondaire | `#A1A1AA` |
| Texte sur couleur | `#0A0A0A` |
| Primaire | `#C6FF1A` (lime) |
| Secondaire | `#FF2E88` (magenta) |
| Erreur | `#FF4D4D` |

Règles d'emploi :

- Un bouton primaire est rempli de la couleur primaire avec un texte presque
  noir (`#0A0A0A`) ; un bouton secondaire est rempli de la secondaire ; un
  bouton neutre est une surface grise avec texte blanc.
- Primaire : action principale, focus clavier, progression, volume, morceau en
  lecture (indicateur ▷ et titre), activité active de la barre d'activités.
- Secondaire : `Add to playlist`, états actifs de Shuffle/Repeat, accents
  ponctuels. Elle ne sert jamais au focus ni à l'erreur.
- L'erreur utilise sa propre couleur, jamais la secondaire.
- Les pastilles Camelot (Key) suivent la roue harmonique à 12 teintes, avec
  texte noir, indépendamment de la palette.

## Dimensions et typographie

| Élément | Valeur |
|---|---|
| Fenêtre de référence | 1440 × 900 |
| Barre de titre | 32 px |
| Barre d'activités | 48 px de large, icônes 24 px |
| Barre latérale | 240 px, redimensionnable |
| Panneau droit | 320 px, redimensionnable |
| Onglets d'éditeur | 36 px |
| Ligne de liste | 56 px, pochette 40 px |
| Îlot de lecture | 72 px de haut, 16 px de marge au bas de l'éditeur |
| Rayon des angles | 0 px (fenêtre, panneaux, îlot) ; 2 px tolérés pour les pastilles |
| Texte courant | 14 px |
| Texte secondaire | 12 px |
| Nom du dossier en en-tête | 28 px, gras |

La police préférée reste Geist Sans lorsqu'elle sera embarquée avec sa licence.
Le prototype utilise la police système enregistrée par le socle lorsqu'aucun
fichier de police n'est présent.

## Fenêtre et barre de titre

Fenêtre sans cadre système. La barre de titre porte le logo « M », les menus
`File`, `Edit`, `View`, une zone de déplacement et les commandes Minimize,
Maximize/Restore et Close (fond rouge au survol de Close). Un double-clic sur
la zone de déplacement maximise ou restaure.

Sous Windows 11, les angles arrondis automatiques sont désactivés
(`DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_DONOTROUND`). La fenêtre conserve le
redimensionnement par ses bords, l'ancrage Aero Snap (Win+flèches, glisser vers
les bords) et le menu Snap Layouts au survol de Maximize.

## Barre d'activités et barre latérale

De haut en bas : Explorer, Playlists, Convert, Tasks, Plugins ; en bas :
Profile et Settings. L'activité active porte un trait primaire à gauche et une
icône blanche ; les autres sont en texte secondaire. Cliquer l'activité active
replie ou déplie la barre latérale.

- **Explorer** : en-tête `EXPLORER` et bouton `+` (Add folder), arborescence
  des dossiers. Le dossier ouvert dans l'onglet actif est mis en évidence.
- **Playlists** : liste fictive de playlists ; fonctionnement au plan 10.
- **Convert** : lots en cours et récents ; ouvre ou active l'onglet Convert.
- **Tasks** : tâches de fond (lecture de dossiers, conversions, analyses) avec
  progression et erreurs. Remplace le bandeau `Session tasks`.
- **Plugins** et **Profile** : emplacements réservés. Le bouton existe ; son
  panneau indique `Coming later` et ne propose aucune action.
- **Settings** : ouvre un onglet d'éditeur `Settings`.

## Zone d'éditeur et listes

Onglets fermables comme dans VS Code, deux groupes au maximum côte à côte.

Un onglet de dossier commence par le nom du dossier en grand puis
`n titles · durée totale · taille`. Colonnes par défaut : `#`, pochette,
Title avec l'artiste en seconde ligne, Album (texte secondaire), Genre, BPM,
Key (pastille Camelot), Duration, puis `+` (Add to playlist) visible au survol
et sur la ligne sélectionnée. Colonnes supplémentaires : Date added, Format,
Filename, Bitrate, Size. En-têtes triables ; la colonne triée affiche sa
flèche.

États de ligne : survol en surface ; sélection en gris de sélection ; lecture
avec ▷ primaire à la place du numéro et titre en primaire ; focus clavier par
un contour primaire de 1 px. Au survol, une icône ⓘ ouvre l'édition.

La vue Artwork reste accessible depuis `View` et l'en-tête de liste : une
entrée par fichier, sans regroupement par album ; une pochette absente affiche
une illustration neutre.

## Panneau droit Info / Queue

Replié par défaut. `Ctrl+I`, `Edit info` dans le menu contextuel ou l'icône ⓘ
l'ouvrent sur Info ; le bouton Queue de l'îlot l'ouvre sur Queue.

- **Info** suit la sélection : titre et artiste en tête, puis les champs
  modifiables (Title, Artist, Album, Genre, Date, Track number, BPM, Key,
  Comment), puis les caractéristiques en lecture seule (Duration, Format,
  Bitrate, Sample rate, Size, Filename, Path).
- **Queue** montre `Now playing`, `Next up` et `History`.

Une perte de focus ou Entrée enregistre le champ : Saving puis Saved, ou
Could not save avec Retry en conservant la saisie. Undo restaure la valeur
précédente. En multisélection, Mixed values est un état d'affichage ; il ne
peut pas être écrit comme une valeur.

## Îlot de lecture

Flottant, centré en bas de la zone d'éditeur (largeur maximale 960 px), fond
de surface, séparateur fin, angles droits. De gauche à droite : pochette 48 px,
titre et artiste(s), `+` ; au centre Shuffle, Previous, Play/Pause (bouton
primaire), Next, Repeat, puis la progression avec temps écoulé et total ; à
droite Queue, volume et Fullscreen player. La liste réserve en bas une marge
égale à la hauteur de l'îlot pour que la dernière ligne reste accessible.

Visible dès qu'un morceau est chargé ; masquable par `View › Player island` et
dans Settings. Masqué dans Fullscreen player.

## Fullscreen player

La barre d'activités reste visible ; barre latérale, éditeur et panneau droit
sont masqués. En haut : `Playing from: <source>` et Exit fullscreen. Au
centre : grande pochette, titre, artiste. En dessous : waveform monochrome à
extrema min/max, adaptée à la largeur visible, puis les commandes de transport
et le volume. La partie lue est assombrie ; une tête de lecture et son temps
suivent la position et la durée du lecteur. Le clic sur les deux parties reste
un seek. L’utilisateur retient uniquement cette variante monochrome ; aucune
bande de fréquence ni coloration RGB. Fullscreen player suit le morceau joué,
pas la sélection. `Esc` restaure l'état précédent.

## Convert

Onglet d'éditeur. Il sépare les fichiers d'entrée et les réglages de sortie.
Les commandes immédiates sont Add files, Add selected tracks et Start
conversion. Les choix fréquents sont visibles ; Sample rate, Channels et
Metadata sont regroupés dans Advanced. Les combinaisons affichées sont
explicitement fictives au stade du prototype. Une erreur est attachée à
l'entrée concernée, garde le fichier source intact et propose Retry. Open output
folder est visible mais simulé.

## Largeurs réduites

Le panneau droit reste ancré à toutes les largeurs ; une superposition masquait
l'îlot de lecture et les colonnes. Sous 1160 px, la barre latérale se replie
(la barre d'activités reste) ; rouverte, elle se superpose à l'éditeur jusqu'à
un clic en dehors. Sous 930 px, un seul groupe d'onglets est affiché avec un
contrôle pour retrouver l'autre ; onglets et sélections restent en mémoire.
Les colonnes Album puis Genre se masquent avant Title, BPM et Key, et un groupe
de moins de 600 px resserre marges et espacements.

## Vocabulaire

Les mêmes actions gardent le même libellé partout : Explorer, Playlists,
Convert, Tasks, Plugins, Profile, Settings, Info, Queue, Edit info, Add to
playlist, Player island, Fullscreen player, Exit fullscreen, Save, Saved,
Retry, Undo. Les messages décrivent l'état et l'action possible ; ils
n'exposent pas de journal technique dans le parcours courant.
