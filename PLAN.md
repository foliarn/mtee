
# MTEE — Plan de conception et de développement

## Addendum UX/UI — 2026-09-28

La demande du 28 septembre prépare cinq catégories de correctifs pour la version existante, détaillées dans les plans 23–28 de [l’index d’exécution](Plans%20d'ex%C3%A9cution/README.md). Cette préparation ne constitue pas leur implémentation ni la clôture de la recette de stabilisation.

Les décisions utilisateur précisent : ordre de référence par date de création décroissante et sans flèche de tri manuel ; colonnes déplaçables/masquables avec configuration globale mémorisée ; conservation du texte et des résultats de recherche lorsqu’elle perd le focus ; double-clic dans l’arbre sélectionnant, révélant et jouant le morceau, sauf cible masquée par la recherche qui joue sans être révélée. Les cinq colonnes de base sont Title, Artist, Date created, BPM et Key. L’affichage des pochettes est configurable et le numéro ordinal # est retiré du tableau.

La lisibilité des waveforms, leur repère temporel et l’assombrissement de la portion lue sont à améliorer. Trois variantes monochrome, 3 bandes et RGB seront comparées dans des maquettes avant le choix utilisateur. Jusqu’à ce choix et à son implémentation validée, la version fonctionnelle reste celle de la stabilisation. Cette étude ne réactive ni zoom temporel, ni boucle A/B, ni analyse musicale. Les autres fonctionnalités différées restent hors périmètre.

## Addendum de trajectoire — 2026-09-25

La trajectoire fonctionnelle décrite ci-dessous est suspendue pendant la remise en état de la version Windows. La série [16–22 — Stabilisation](Plans%20d'ex%C3%A9cution/README.md) devient prioritaire et ses critères remplacent temporairement les livraisons C–K ci-dessous.

Le périmètre actuellement retenu conserve l’exploration, la lecture, les métadonnées écrites (y compris BPM et Key déjà présents), la conversion, l’affichage monochrome de la waveform avec recherche par clic et la corbeille Windows. L’analyse calculée est retirée. Zoom, déplacement horizontal, boucle A/B, indexation globale des waveforms, nouvelles mesures audio, renommage, déplacement, copie, presse-papiers de fichiers et déplacement par glisser-déposer sont suspendus ou retirés selon les lots de stabilisation. Les autres fonctionnalités restent différées jusqu’à la clôture de cette stabilisation et aux validations produit prévues.

Cet addendum ne supprime pas l’historique de conception ci-dessous. Les exigences qu’il remplace y restent comme trace de la trajectoire initialement envisagée. Les validations utilisateur antérieures, notamment les maquettes, ne sont pas annulées.

## 1. Contexte, vision et stack retenue

**MTEE — Music Tagging and Editing Explorer — est une application desktop personnelle pour explorer, écouter, organiser, modifier et préparer une collection de fichiers audio.** Le projet pourra être publié en open source ; sa priorité est de répondre à ton usage.

L’idée combine la navigation d’un IDE, la gestion musicale d’un logiciel DJ et, progressivement, quelques fonctions d’édition audio.

Les besoins à couvrir sont :

- Explorer les dossiers et leurs morceaux avec plusieurs vues.
- Écouter les formats audio courants dans l’application.
- Consulter et modifier les métadonnées existantes, dont genre, BPM et tonalité.
- Renommer, déplacer et supprimer manuellement des fichiers.
- Convertir les morceaux, notamment pour les anciennes CDJ et autres platines.
- Analyser le signal, puis utiliser les résultats pour rechercher et classer.
- Créer des playlists et retrouver des morceaux similaires.
- Extraire des passages et effectuer des éditions simples.
- Échanger des données avec Rekordbox en préservant les informations compatibles.
- Ajouter ultérieurement une connexion Spotify/Shovel.
- Réévaluer un système de plugins lorsque des besoins concrets apparaîtront.

**Contraintes validées :**

- Python pour la logique applicative.
- Interface desktop sans Electron ni WebView.
- Windows en premier ; architecture compatible avec un portage Linux/macOS.
- Interface en anglais.
- Collection initiale inférieure à 10 000 morceaux.
- Fonctionnement local autonome pour les fonctions principales.
- Tags personnalisés et playlists reportés après l’analyse.

| Composant | Choix |
|---|---|
| Interface | PySide6 + Qt Quick / QML |
| Logique | Python avec annotations de types |
| Lecture | libmpv, piloté par une couche Python dédiée |
| Métadonnées | Mutagen |
| Persistance | SQLite |
| Inspection/conversion, après le premier lecteur fonctionnel | ffprobe et FFmpeg en processus séparés |
| Analyse | NumPy, SciPy et librosa, ajoutés selon les fonctions effectivement développées |
| Outils du projet | uv, pytest, Ruff et Pyright |

Démarrer avec Python 3.12 et verrouiller les versions des dépendances après validation de leur installation et de leur distribution sous Windows.

L’application distingue dès le départ **fichier source, métadonnées du fichier, résultats d’analyse et fichiers dérivés**. Les données issues de ces catégories ne doivent pas s’écraser implicitement.

---

## 2. Ordre de livraison des fonctionnalités

Chaque étape doit produire une version utilisable et vérifiable avant d’élargir le périmètre.

| Ordre | Fonctionnalités | Résultat attendu |
|---|---|---|
| **A** | Interface, explorateur et affichage des métadonnées | Parcourir ses dossiers dans MTEE |
| **B** | Lecteur intégré et modification manuelle des métadonnées | Écouter et corriger sa collection |
| **C** | Gestion physique des fichiers | Renommer, déplacer et mettre à la corbeille |
| **D** | Conversion FFmpeg généraliste | Produire des copies adaptées à ses besoins |
| **E** | Waveform et Fullscreen player complet | Écouter et repérer les passages confortablement |
| **F** | Analyse audio sans ML | Obtenir des mesures et estimations musicales exploitables |
| **G** | Tags avancés, recherche enrichie et playlists | Organiser et retrouver ses morceaux à partir des résultats |
| **H** | Extraction de samples et édition légère | Exporter des passages et créer des variantes |
| **I** | Liaison Rekordbox | Importer/exporter progressivement les données compatibles |
| **J** | Analyse ML et similarité musicale avancée | Explorer la collection selon des caractéristiques plus perceptuelles |
| **K** | Spotify/Shovel | Relier les découvertes et playlists à la collection locale |

**FFmpeg ne fait pas partie des toutes premières étapes A/B.** Sa fonction de conversion arrive toutefois avant l’analyse, conformément à son importance dans ton usage.

Une courte étude du format d’échange Rekordbox est réalisée pendant la préparation technique. Elle sert à anticiper les identifiants, emplacements et repères temporels ; elle ne déclenche pas la construction anticipée de l’intégration.

Les plugins publics, le multipiste et le mixage en temps réel restent hors de cette première trajectoire.

---

## 3. Conception UX/UI et maquettes

### Organisation générale validée

Révision du 24 septembre 2026 : l’utilisateur a fourni une esquisse ([docs/ux/sketches/esquisse-2026-09-24.png](docs/ux/sketches/esquisse-2026-09-24.png)) qui remplace la première organisation Browser / Listening view / Convert en onglets supérieurs. La structure suit désormais **VS Code** pour la navigation et **Spotify** pour les listes et le lecteur.

La fenêtre comprend, de gauche à droite et de haut en bas :

- Une **barre de titre personnalisée**, sans cadre système et à angles droits : logo « M », menus `File`, `Edit`, `View`, commandes de fenêtre.
- Une **barre d’activités** verticale à gauche. Chaque icône remplace le contenu de la barre latérale : **Explorer**, **Playlists**, **Convert**, **Tasks** et **Plugins**. En bas : **Profile** et **Settings**.
- Une **barre latérale** qui affiche le contenu de l’activité choisie ; pour Explorer, l’arborescence des dossiers et un bouton `+` d’ajout de dossier.
- Une **zone d’éditeur** à onglets, comme VS Code, avec division verticale en deux groupes au maximum. Un onglet contient une liste de morceaux, Convert ou Settings.
- Un **panneau droit** facultatif à deux onglets, **Info** et **Queue**.
- Un **îlot de lecture** (« music player island ») flottant en bas de la zone d’éditeur.

Plugins et Profile sont des emplacements réservés : leurs boutons existent, sont visibles et restent sans fonction jusqu’à une décision ultérieure. Le système de plugins reste hors de la première trajectoire (§2).

Limiter la première implémentation à deux groupes côte à côte. Les dispositions arbitraires et fenêtres détachables pourront attendre.

**Maquette structurelle — navigation :**

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ M  File  Edit  View                                          ─   ▢   ✕     │
├──┬─────────────┬───────────────────────────────────────────┬───────────────┤
│Ex│ EXPLORER  + │ dnb ×   ukg ×                             │ Info │ Queue  │
│Pl│ ▾ Music     ├───────────────────────────────────────────┤               │
│Cv│   › dubstep │ dnb                                        │ title1        │
│Tk│   › dnb     │ 42 titles · 2 h 31 min · 1.8 GB            │ artist        │
│Pg│   ▾ ukg     │ #  Title / Artist      Album  BPM Key  ⏱ + │               │
│  │     song 1  │ 1  ▣ Title             Album  174 8A 3:16 +│ Editable      │
│  │   › techno  │      Artist                                │ fields        │
│  │             │ 2  ▣ Title ...                             │               │
│Pr│             │   ┌─────────────────────────────────────┐  │ Read-only     │
│St│             │   │▣ Title +  ⤮ ⏮ ⏯ ⏭ ⟲  ━━━━  ≡ 🔊━ ⛶ │  │ fields        │
│  │             │   └─────────────────────────────────────┘  │               │
└──┴─────────────┴───────────────────────────────────────────┴───────────────┘
 Ex Explorer · Pl Playlists · Cv Convert · Tk Tasks · Pg Plugins · Pr Profile · St Settings
```

### Listes de morceaux

Un onglet de dossier ou de playlist commence par un en-tête : nom en grand, puis `n titles · durée totale · taille`. La liste suit le style Spotify :

- Colonnes par défaut : **#**, pochette miniature, **Title** avec l’artiste sur une seconde ligne, **Album** (discret), **Genre**, **BPM**, **Key** en pastille Camelot colorée, **Duration**, puis un bouton `+` **Add to playlist**.
- Colonnes supplémentaires : Date added, Format, Filename, Bitrate, Size. Les colonnes peuvent être triées, redimensionnées et réordonnées.
- Une icône ⓘ apparaît au survol d’une ligne et ouvre l’édition.
- La vue **Artwork** reste disponible depuis le menu `View` et l’en-tête de liste : une pochette par fichier, avec titre et artiste, une illustration neutre pour les pochettes absentes et aucun regroupement par album.

### Îlot de lecture

L’îlot flotte au-dessus du bas de la zone d’éditeur, centré, sans masquer la dernière ligne de la liste (marge de défilement réservée). Il contient :

- Pochette, titre, artiste(s) et `+` **Add to playlist**.
- **Shuffle**, **Previous**, **Play/Pause**, **Next**, **Repeat**, avec la barre de progression et les temps écoulé/total.
- **Queue** (ouvre l’onglet Queue du panneau droit), volume et **Fullscreen player**.

Il est visible dès qu’un morceau est chargé ; `View › Player island` et Settings permettent de le masquer. Il disparaît dans Fullscreen player pour éviter des commandes dupliquées.

### Fullscreen player

Remplace l’ancienne vue Écoute. La barre d’activités reste visible, la barre latérale et la zone d’éditeur sont masquées.

```text
┌──┬──────────────────────────────────────────────────────────────────────┐
│Ex│ Playing from: dnb (folder)                            Exit fullscreen│
│Pl│                                                                      │
│Cv│                         ┌──────────────┐                             │
│Tk│                         │  Large cover │                             │
│  │                         └──────────────┘                             │
│  │                              Title                                   │
│  │                              Artist                                  │
│  │          ▌▌▌▐▐▌▌▌▐▌▌▐▐▐▌▌▌▐▌▌▌▐▐▌▌▌  waveform (placeholder)          │
│Pr│          0:49                                        3:25            │
│St│                     ⤮    ⏮    ⏯    ⏭    ⟲          🔊━━━            │
└──┴──────────────────────────────────────────────────────────────────────┘
```

- La source de lecture (dossier, playlist, album, artiste) figure en haut.
- Avant le plan 08, la waveform est un emplacement réservé doté d’une barre de progression classique.
- `Esc` ou **Exit fullscreen** restaure onglets, division, panneau droit et sélection précédents.
- Les futurs tags d’analyse trouveront leur place sous l’identité du morceau.

### Sélection, lecture et édition

- Un clic sélectionne ; Ctrl et Shift étendent la sélection.
- **Un double-clic ou Entrée lance la lecture.**
- **L’édition s’ouvre avec `Ctrl+I`, l’entrée `Edit info` du menu contextuel ou l’icône ⓘ de survol.** Elle affiche le panneau droit sur l’onglet Info.
- Une fois ouvert, l’onglet Info suit la sélection ; Fullscreen player suit le morceau joué. La sélection et le morceau en lecture peuvent être différents.
- L’onglet Queue montre la file à venir et l’historique.
- La lecture continue selon l’ordre de la liste au moment du lancement. Changer de dossier ou de tri ne reconstruit pas silencieusement cette file.
- Espace contrôle la lecture sauf lorsqu’un champ de saisie possède le focus.
- Le morceau en lecture est marqué dans la liste par un indicateur ▷ et la couleur primaire.

Le panneau Info sépare les champs modifiables (Title, Artist, Album, Genre, Date, BPM, Key, Comment…) des caractéristiques en lecture seule (Duration, Format, Bitrate, Size, Filename, Path).

Les métadonnées s’enregistrent automatiquement **à la validation du champ ou à sa perte de focus**, pas après chaque frappe. Afficher les états **Saving**, **Saved** et **Could not save**. Une erreur conserve la saisie pour permettre une nouvelle tentative. Une action d’annulation restaure la valeur précédente. En sélection multiple, afficher les valeurs différentes comme **Mixed values**. Modifier explicitement un champ applique uniquement ce champ à la sélection.

### Convert, Tasks, Playlists et Settings

L’activité **Convert** affiche dans la barre latérale les lots en cours et récents, et ouvre ou active l’onglet d’éditeur **Convert** :

```text
┌ Convert ────────────────────────────────────────────────────────┐
│ Add files    Add selected tracks                                │
├──────────────────────────────┬──────────────────────────────────┤
│ Input files                  │ Output format                    │
│ Name / Codec / Duration      │ Codec / Quality / Sample rate    │
│ Status / Progress            │ Channels / Bit depth if relevant │
│                              │ Output folder                    │
│                              │ Start conversion                 │
├──────────────────────────────┴──────────────────────────────────┤
│ Progress summary       Cancel pending       Open output folder  │
└─────────────────────────────────────────────────────────────────┘
```

La conversion accepte les formats audio réellement pris en charge par la version de FFmpeg distribuée avec MTEE. Elle propose les sorties audio disponibles et uniquement les combinaisons conteneur/codec valides. Les réglages fréquents restent accessibles immédiatement ; les options techniques complémentaires sont regroupées dans **Advanced**. Les sources sont conservées. Les sorties vont dans un dossier choisi, sans écraser de fichier existant. Une correspondance source/sortie est enregistrée pour les futures opérations Rekordbox.

L’activité **Tasks** remplace l’ancien bandeau des tâches de session : elle liste les analyses, lectures de dossiers et conversions en cours ou terminées, avec progression et erreurs.

L’activité **Playlists** est maquettée avec des données fictives ; son fonctionnement arrive avec les playlists (§4.8).

**Settings** s’ouvre comme un onglet d’éditeur, à la manière de VS Code, et contient notamment l’affichage de l’îlot de lecture.

### Direction visuelle

Base de maquette : **1440 × 900**, densité intermédiaire, interface sombre en gris neutres.

- Fenêtre sans cadre, **angles droits** (y compris sous Windows 11), surfaces sobres et épurées ; pas d’arrondis décoratifs.
- Barre de titre, barre d’activités et barre latérale plus sombres que la zone d’éditeur.
- Texte principal blanc.
- Une **couleur primaire vive** (famille vert néon / lime) pour les actions principales, le focus, la progression et le morceau en lecture ; une **couleur secondaire contrastée** pour les actions secondaires et accents. Palette retenue le 24 septembre 2026 : **Acid**, gris neutres `#0B0B0C` à `#18181B`, primaire lime `#C6FF1A`, secondaire magenta `#FF2E88` ; valeurs complètes dans [docs/ux/specification.md](docs/ux/specification.md).
- Les couleurs des pastilles Camelot suivent la roue harmonique et sont indépendantes de la palette.
- Police : **Geist Sans**, embarquée localement avec sa licence. Texte courant autour de 14 px.
- Pas de grands dégradés décoratifs ni de cartes pour chaque information.
- Distinguer survol, sélection, lecture en cours et focus clavier.
- À petite largeur, replier la barre latérale puis le panneau droit, et afficher un seul groupe d’onglets sans perdre son contenu.

### Validation avant le code fonctionnel

Produire les maquettes QML détaillées de l’**explorateur à onglets**, du **panneau Info/Queue**, de l’**îlot de lecture**, du **Fullscreen player**, de **Convert**, de **Tasks**, de **Playlists** et de **Settings**, puis leurs états importants : édition ouverte, double groupe, sélection multiple, pochette absente, erreur de conversion et fenêtre étroite.

Utiliser un prototype QML à données fictives pour vérifier les dimensions et interactions, sans accès aux fichiers utilisateur.

La revue utilisateur doit notamment examiner :

- La densité et la lisibilité des lignes de style Spotify sur l’écran réel.
- La barre de titre sans cadre, le déplacement, l’ancrage et le redimensionnement de la fenêtre.
- L’îlot de lecture et l’équilibre du Fullscreen player.
- L’accès aux commandes en groupes divisés.
- La compréhension de l’enregistrement automatique.
- La lisibilité des options et erreurs de conversion.

**La validation de ces maquettes constitue un jalon distinct.** Les ajustements visuels sont reportés dans la spécification avant l’implémentation fonctionnelle.

Jalon validé le 24 septembre 2026 : l’utilisateur approuve sans modification le prototype révisé (revue 2, `docs/ux/review-02.md`). Il sert de référence visuelle aux étapes suivantes.

---

## 4. Développement, étape par étape

### 4.0 — Préparer le projet

Ajouter l’environnement Python, le verrouillage des dépendances, la fenêtre PySide6 et le système de thème QML.

Séparer les responsabilités :

- Présentation QML.
- Modèles Qt exposés à l’interface.
- Services Python : fichiers, métadonnées, lecture, conversion, analyse.
- Persistance et gestion des tâches.

Les composants échangent des informations de morceau, de sélection, d’état du lecteur et de progression. QML ne manipule pas directement les fichiers ni les commandes système.

**Validation :** démarrage depuis une installation propre et création précoce d’une distribution Windows autonome.

### 4.1 — Implémenter l’explorateur

Ajouter la barre de titre sans cadre, la barre d’activités, les dossiers racines choisis par l’utilisateur, l’arborescence, les onglets, les deux groupes, les listes de style Spotify et la vue Artwork.

Lire les fichiers en arrière-plan, charger les pochettes à la demande et afficher les grandes listes sans créer un composant permanent par fichier.

Persister les racines, onglets, largeurs de colonnes et dispositions. Ne pas réorganiser les fichiers lors de leur ajout.

**Validation :** dossiers imbriqués, caractères accentués, pochettes absentes, disque déconnecté et collection de 10 000 fichiers sans blocage durable de l’interface.

### 4.2 — Ajouter le lecteur

Intégrer mpv derrière un service commun à toutes les vues.

Ajouter lecture/pause, précédent/suivant, aléatoire, répétition, position, volume, file d’attente, îlot de lecture et bascule vers Fullscreen player.

Tester MP3, FLAC, AAC, WAV, ALAC, AIFF, Ogg/Vorbis, M4A et Opus à partir de fichiers représentatifs. Identifier le codec réel plutôt que de se fier uniquement à l’extension.

**Validation :** changer de vue sans couper le son ; sélectionner un autre fichier sans interrompre la lecture ; gérer proprement un fichier illisible ou supprimé.

### 4.3 — Modifier les métadonnées

Ajouter Mutagen et une correspondance explicite entre les champs de MTEE et les tags de chaque format.

Commencer par titre, artiste, album, genre, date, commentaire, numéro de piste, BPM et tonalité. Afficher les caractéristiques techniques en lecture seule.

Préserver les tags inconnus et les pochettes lors de l’édition d’un autre champ. Désactiver l’édition des champs que le format ou la bibliothèque ne permet pas d’écrire correctement.

Sérialiser les écritures par fichier et conserver un historique des valeurs modifiées. Si le fichier a changé extérieurement, suspendre l’écriture concernée et proposer sa relecture.

**Validation :** relecture des valeurs après redémarrage, modifications multiples, annulation, fichier verrouillé, lecture seule et sauvegarde échouée sans faux état « Saved ».

### 4.4 — Gérer les fichiers

Ajouter renommage, déplacement et mise à la corbeille depuis les menus et raccourcis.

Le déplacement entre panneaux doit montrer sa destination et demander confirmation. Un simple changement de dossier dans l’arborescence reste une navigation.

Mettre à jour les références internes après une opération réussie. Ne pas écraser les collisions de noms. Si la corbeille est indisponible, signaler l’échec sans basculer vers une suppression définitive.

**Validation :** annulation d’un déplacement lorsque possible, collision, disque déconnecté, permissions insuffisantes et morceau en cours de lecture.

### 4.5 — Construire la conversion

Ajouter FFmpeg/ffprobe, l’activité et l’onglet Convert.

Implémenter l’inspection des entrées, la sélection du format et du codec, les paramètres compatibles, la destination, la progression, l’annulation et la relance des échecs.

Lancer FFmpeg avec une liste d’arguments, sans interpréteur de commandes. Limiter initialement à deux conversions simultanées.

Écrire vers un fichier temporaire, vérifier la sortie, puis lui attribuer son nom définitif. Recopier les métadonnées compatibles et signaler celles qui ne sont pas transférées.

Ne pas normaliser implicitement le volume. En réduction de profondeur PCM, appliquer un dithering adapté.

**Validation :** lots mixtes, AAC et ALAC en M4A, annulation, manque d’espace, collision et contrôle du codec/fréquence/canaux des sorties.

La compatibilité avec une platine est validée séparément, sur les modèles réellement ciblés, avant d’afficher un profil portant leur nom.

### 4.6 — Ajouter la waveform

Décoder l’audio en arrière-plan, calculer une représentation réduite et la mettre en cache.

Ajouter déplacement de la tête de lecture, zoom et boucle A/B. Invalider le cache lorsque la source change.

**Validation :** alignement avec la lecture, recherche temporelle, fichiers longs et absence de ralentissement pendant le calcul.

### 4.7 — Analyser sans ML

Introduire successivement :

1. Silences et caractéristiques techniques.
2. Loudness, crêtes et dynamique.
3. Estimation de tempo, avec correction moitié/double.
4. Estimation de tonalité, corrigeable.

Conserver la version de l’analyse et distinguer résultat calculé et valeur confirmée manuellement. L’analyse ne réécrit pas automatiquement les tags des fichiers.

**Validation :** corpus représentatif de ta musique, résultats reproductibles, erreurs explicites et correction manuelle préservée après réanalyse.

### 4.8 — Définir les tags avancés et ajouter les playlists

À partir des résultats réellement utiles, mener une courte revue utilisateur pour fixer le vocabulaire des tags. Ne pas inventer une taxonomie avant cette revue.

Ajouter ensuite recherche combinée, filtres enregistrés et playlists manuelles avec ordre modifiable. Les vues intelligentes réutilisent les critères de recherche.

**Validation :** retrouver une sélection par critères, réordonner une playlist et conserver ses références après un déplacement effectué dans MTEE.

### 4.9 — Extraire et éditer légèrement

Ajouter export de sélection temporelle, coupe début/fin, fondus et export d’une copie.

Conserver la relation avec la source. Les nouvelles versions possèdent leur propre durée et leurs propres analyses.

**Validation :** précision des bornes exportées, absence de modification de l’original et cohérence entre sélection et fichier produit.

### 4.10 — Relier Rekordbox

Commencer par l’import XML en lecture seule, puis l’export d’une sélection.

Tester séparément playlists, métadonnées, cues et grilles. Afficher ce qui sera transféré et les limitations constatées.

Pour les fichiers convertis, vérifier la correspondance temporelle avant de réutiliser les cues. Une piste découpée nécessite un traitement spécifique.

**Validation :** aller-retour sur une collection de test sans doublons inattendus ni modification silencieuse des données non prises en charge.

### 4.11 — Ajouter ML, similarité et Spotify/Shovel

Évaluer d’abord la similarité sur tes propres morceaux et tes jugements d’écoute. Choisir les modèles selon leur pertinence, leurs ressources nécessaires et leurs licences.

Définir ensuite le contrat d’échange avec Shovel et vérifier les accès Spotify disponibles au moment de l’intégration. La connexion reste facultative ; son indisponibilité ne bloque pas les fichiers locaux.

**Validation :** pertinence des suggestions évaluée à l’écoute, correspondances de versions vérifiables et fonctionnement local maintenu hors connexion.

### Contrôle commun à chaque livraison

À chaque jalon : tests ciblés, parcours manuel dans l’interface et vérification de la distribution Windows. Les opérations susceptibles de modifier des fichiers sont testées sur des copies.

Le portage Linux/macOS fera l’objet d’un jalon dédié avec validation des dépendances natives, chemins, raccourcis et sorties audio. La compatibilité architecturale ne sera pas présentée comme un portage testé.
