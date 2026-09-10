
# MTEE — Plan de conception et de développement

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
| **E** | Waveform et vue Écoute complète | Écouter et repérer les passages confortablement |
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

La navigation principale est un **explorateur de dossiers à gauche, inspiré de VS Code**. Le contenu sélectionné s’ouvre dans la zone centrale.

Cette zone comprend :

- Des onglets pour garder plusieurs dossiers ou espaces ouverts.
- Une division verticale en deux groupes d’onglets.
- Une vue **Table** et une vue **Artwork**.
- Un inspecteur de métadonnées à droite, replié par défaut.
- Un lecteur commun fixé en bas.
- Un onglet **Convert** dédié.

Limiter la première implémentation à deux vues côte à côte. Les dispositions arbitraires et fenêtres détachables pourront attendre.

**Maquette structurelle — navigation :**

```text
┌──────────────────────────────────────────────────────────────────┐
│ MTEE                                             Window controls │
├──────────────┬───────────────────────────────────────────────────┤
│ Explorer     │ Downloads ×   Collection ×   Convert ×            │
│              ├───────────────────────────────────────────────────┤
│ Music        │ Path / Breadcrumbs       Search…   View   Details │
│ ├ Downloads  ├──────────────────────────┬────────────────────────┤
│ └ Collection │ Title Artist Genre      │ Second folder / view   │
│              │ BPM   Key               │                        │
│ Add folder   │                         │                        │
├──────────────┴──────────────────────────┴────────────────────────┤
│ Artwork  Track / Artist   Previous Play Next   Seek   Volume     │
└──────────────────────────────────────────────────────────────────┘
```

La table présente par défaut **Title, Artist, Genre, BPM, Key**. Les colonnes peuvent être triées, redimensionnées et réordonnées. Duration, Format et Filename sont disponibles comme colonnes supplémentaires.

La grille affiche une pochette par fichier, avec titre et artiste. Une illustration neutre remplace les pochettes absentes ; les fichiers ne sont pas regroupés automatiquement par album.

### Vue Écoute

Le bouton **Listening view** agrandit le lecteur dans l’espace central. Le morceau, la position et la file restent identiques.

```text
┌ Explorer ────┬ Listening view ───────────────────────────────────┐
│              │                                                  │
│              │ Large artwork       Title / Artist               │
│              │                     Editable metadata            │
│              │                                                  │
│              │ Large waveform with playhead                     │
│              │ Time       Previous Play Next          Volume    │
│              │                                  Back to browser │
└──────────────┴───────────────────────────────────────────────────┘
```

- Pochette et métadonnées occupent la partie supérieure.
- La waveform utilise la largeur disponible dans la partie inférieure.
- Les futurs tags d’analyse trouvent leur place près des métadonnées.
- Le lecteur inférieur disparaît dans ce mode pour éviter des commandes dupliquées.
- Le retour restaure les onglets, la division et la sélection précédentes.

Avant l’implémentation de la waveform, cette zone affiche une barre de progression classique.

### Sélection, lecture et édition

- Un clic sélectionne ; un double-clic lance la lecture.
- La sélection et le morceau en lecture peuvent être différents.
- L’inspecteur de navigation suit la sélection ; la vue Écoute suit le morceau joué.
- La lecture continue selon l’ordre de la liste au moment du lancement. Changer de dossier ou de tri ne reconstruit pas silencieusement cette file.
- Espace contrôle la lecture sauf lorsqu’un champ de saisie possède le focus.
- Une file d’attente consultable permet de voir les prochains morceaux.

Les métadonnées s’enregistrent automatiquement **à la validation du champ ou à sa perte de focus**, pas après chaque frappe.

Afficher les états **Saving**, **Saved** et **Could not save**. Une erreur conserve la saisie pour permettre une nouvelle tentative. Une action d’annulation restaure la valeur précédente.

En sélection multiple, afficher les valeurs différentes comme **Mixed values**. Modifier explicitement un champ applique uniquement ce champ à la sélection.

### Onglet Conversion

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

La conversion accepte les formats audio réellement pris en charge par la version de FFmpeg distribuée avec MTEE. Elle propose les sorties audio disponibles et uniquement les combinaisons conteneur/codec valides.

Les réglages fréquents restent accessibles immédiatement ; les options techniques complémentaires sont regroupées dans **Advanced**.

Les sources sont conservées. Les sorties vont dans un dossier choisi, sans écraser de fichier existant. Une correspondance source/sortie est enregistrée pour les futures opérations Rekordbox.

### Direction visuelle

Base de maquette validée : **1440 × 900**, densité intermédiaire, interface sombre et panneaux arrondis.

Palette initiale :

| Rôle | Valeur |
|---|---|
| Fond | `#080E18` |
| Panneaux | `#111B2B` |
| Surfaces actives | `#1B2A40` |
| Texte principal | `#EDF2FA` |
| Texte secondaire | `#A5B3C7` |
| Accent et focus | `#80B5FF` |

- Police : **Geist Sans**, embarquée localement avec sa licence.
- Texte courant autour de 14 px ; lignes de table de 36 px.
- Arrondis de 12 px pour les panneaux et 6–8 px pour les contrôles.
- Pas de grands dégradés décoratifs ni de cartes pour chaque information.
- Distinguer survol, sélection, lecture en cours et focus clavier.
- À petite largeur, replier les panneaux et afficher un seul groupe d’onglets sans perdre son contenu.

### Validation avant le code fonctionnel

Produire trois maquettes détaillées : **Browser**, **Listening view**, **Convert**, puis leurs états importants : inspecteur ouvert, double panneau, sélection multiple, pochette absente et erreur de conversion.

Utiliser un prototype QML à données fictives pour vérifier les dimensions et interactions, sans accès aux fichiers utilisateur.

La revue utilisateur doit notamment examiner :

- La densité et la lisibilité sur l’écran réel.
- L’équilibre pochette/waveform/métadonnées.
- L’accès aux commandes en panneau divisé.
- La compréhension de l’enregistrement automatique.
- La lisibilité des options et erreurs de conversion.

**La validation de ces maquettes constitue un jalon distinct.** Les ajustements visuels sont reportés dans la spécification avant l’implémentation fonctionnelle.

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

Ajouter les dossiers racines choisis par l’utilisateur, l’arborescence, les onglets, les deux panneaux et les vues Table/Artwork.

Lire les fichiers en arrière-plan, charger les pochettes à la demande et afficher les grandes listes sans créer un composant permanent par fichier.

Persister les racines, onglets, largeurs de colonnes et dispositions. Ne pas réorganiser les fichiers lors de leur ajout.

**Validation :** dossiers imbriqués, caractères accentués, pochettes absentes, disque déconnecté et collection de 10 000 fichiers sans blocage durable de l’interface.

### 4.2 — Ajouter le lecteur

Intégrer mpv derrière un service commun à toutes les vues.

Ajouter lecture/pause, précédent/suivant, position, volume, file d’attente et bascule vers la vue Écoute.

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

Ajouter FFmpeg/ffprobe et l’onglet Convert.

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
