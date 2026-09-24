# 04 — Lecteur commun et Fullscreen player initial — livraison B, partie 1


Ce plan vivant suit [PLANS.md](../PLANS.md) et couvre `PLAN.md`, §3 « Vue Écoute » et « Sélection, lecture et édition », ainsi que §4.2. Préparé le 2026-09-10 ; le travail, les tests audio et la livraison Git restent à exécuter.

## Objectif et résultat observable


Un double-clic sur un morceau démarre la lecture dans l'îlot de lecture de MTEE. L'utilisateur peut mettre en pause, avancer, reculer, déplacer la position, régler le volume et consulter la file. Passer dans Fullscreen player conserve le même morceau, la position et la file ; revenir restitue l'explorateur tel qu'il était.

Une sélection dans l'explorateur reste indépendante du morceau joué. La lecture continue selon l'ordre visible au moment du lancement, même si l'utilisateur change ensuite le dossier ou son tri. Fullscreen player propose une pochette et les métadonnées, encore en lecture seule, puis une barre de progression classique. La waveform sera ajoutée au plan 08.

La livraison teste les codecs effectivement décodés par la distribution de libmpv retenue. M4A est un conteneur pouvant contenir notamment AAC ou ALAC ; un suffixe ne suffit donc pas à identifier le codec. FFmpeg et ffprobe en exécutables séparés n'entrent pas dans cette étape A/B ; les bibliothèques de décodage internes de libmpv relèvent de son propre runtime.

## Progress


- [x] (2026-09-10) Plan préparé ; aucune lecture audio ni distribution validée à ce stade.
- [ ] Vérifier la disponibilité de l'explorateur et les contrats du socle.
- [ ] Choisir, verrouiller et distribuer un runtime libmpv Windows reproductible.
- [ ] Implémenter l'adaptateur libmpv et les transitions du lecteur commun.
- [ ] Implémenter la file figée au lancement et la séparation lecture/sélection.
- [ ] Relier l'îlot de lecture, Fullscreen player, les raccourcis et les erreurs.
- [ ] Exécuter les tests, la matrice de formats et le parcours de la distribution Windows.
- [ ] Mettre à jour les preuves, committer puis vérifier le push distant.

## Surprises & Discoveries


Aucun résultat connu. Ajouter pendant l'exécution les noms réels des DLL chargées, erreurs de sortie audio, propriétés absentes suivant les formats, précision des seeks et différences entre fichiers AAC et ALAC dans M4A. Fournir le morceau de reproduction autorisé ou son identifiant dans le manifeste et les versions du runtime.

## Decision Log


Les décisions initiales suivantes sont proposées par Codex le 2026-09-10 ; les révisions ultérieures préciseront leur auteur.

- 2026-09-10 — Une seule instance de `PlayerService` et un seul backend libmpv alimentent toutes les vues. Motif : changer de vue ne doit ni redémarrer un fichier ni créer une deuxième sortie audio.
- 2026-09-10 — La file contient une copie ordonnée de UUID, résolus en chemins au moment de l'ouverture. Motif : les tris ne doivent pas altérer la file et les déplacements ultérieurs doivent préserver ses références.
- 2026-09-10 — Évaluer d'abord le binding Python `python-mpv`, isolé derrière un protocole interne. Motif : garder une intégration simple sans lier QML ou les tests au binding retenu.
- 2026-09-10 — Arrêter la progression automatique après une erreur de décodage, en laissant Next et Retry disponibles. Motif : rendre l'erreur visible et éviter de parcourir silencieusement une file de fichiers indisponibles.
- 2026-09-10 — Au lancement de l'application, restaurer éventuellement le volume mais ne pas démarrer de son automatiquement. La reprise persistante d'une session de lecture n'est pas un prérequis de cette livraison.

## Outcomes & Retrospective


À compléter avec formats réellement validés, runtime et provenance, comportement des changements de vue, limites de positionnement et résultat du test sur Windows sans environnement Python. Distinguer test avec faux backend, décodage libmpv automatisé et écoute réelle : ces preuves ne sont pas interchangeables.

## Contexte et prérequis


Le dépôt est documentaire au moment où ce plan est rédigé. Le [plan 01](01-socle-technique.md) doit fournir Python 3.12, PySide6/QML, uv, SQLite, `JobService`, les outils de qualité et `scripts/build_windows.ps1`. Le [plan 02](02-maquettes-ux.md) doit fournir les maquettes validées. Le [plan 03](03-explorateur.md) doit fournir les fichiers indexés, `MetadataReader`, les vignettes, `WorkspaceModel` et `activationRequested(track_id, ordered_track_ids)`.

`track_id` est un UUID indépendant du chemin, dont `TrackRepository` connaît l'emplacement et la disponibilité. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` détecte les changements ordinaires du fichier ; elle ne remplace pas une empreinte de contenu. La sélection est un ensemble de UUID dans le panneau actif ; le lecteur expose séparément `playing_track_id`. Conserver cette distinction jusque dans les composants QML et les tests.

Les données utilisateur restent dans `QStandardPaths`, surchargeables par `--data-dir`. Utiliser `.local/validation/04` pour l'essai. `--demo` n'ouvre que des données fictives sans accès aux fichiers utilisateur et ne peut donc pas prouver une lecture sonore. `--smoke-test` vérifie seulement que la fenêtre est prête. La distribution est attendue dans `dist/MTEE/MTEE.exe`.

Vérifier au début de l'implémentation les versions effectivement retenues dans le [manuel officiel mpv](https://mpv.io/manual/master/) et la [documentation du binding python-mpv](https://github.com/jaseg/python-mpv). Les callbacks du binding peuvent arriver depuis son thread d'événements : ils devront rejoindre le thread Qt avant de modifier les modèles. Consigner les versions, URLs précises, empreintes des binaires et licences dans `docs/native-dependencies.md`.

## Plan de travail et jalons


### Jalon 1 — Runtime distribué et backend isolé


Ajouter `src/mtee/services/mpv_backend.py` et `src/mtee/services/player_backend.py`. Le premier adapte le binding retenu ; le second définit un protocole que les tests peuvent remplacer par un faux backend. Résoudre la DLL depuis un emplacement contrôlé de la distribution et compléter le mécanisme de chargement natif du socle. Ne pas dépendre d'une installation mpv personnelle ou d'un PATH particulier.

Ajouter la dépendance Python validée à `pyproject.toml` puis régénérer `uv.lock`. Compléter `packaging/mtee.spec`, `scripts/build_windows.ps1` et les notices de distribution pour le runtime mpv choisi. Un manifeste versionné `resources/native/mpv/manifest.json` fixe architecture, version, URL précise, empreinte SHA-256, licences et emplacement attendu. Créer `scripts/fetch_mpv.ps1` pour télécharger uniquement cette ressource, vérifier l'empreinte avant extraction sous `vendor/mpv` ignoré par Git, et retourner un code non nul à toute erreur ; le packaging reprend ensuite le runtime vérifié.

Initialiser mpv en audio seulement, sans fenêtre vidéo ni chargement implicite de configuration personnelle. En cas de DLL absente, architecture incorrecte ou sortie audio indisponible, garder l'explorateur utilisable et afficher un état explicite du lecteur. Tester le démarrage et la terminaison du backend sans bloquer la boucle Qt.

### Jalon 2 — État du lecteur et file


Créer `src/mtee/domain/playback.py`, `src/mtee/services/player_service.py` et `src/mtee/models/player_model.py`. Définir les états Idle, Loading, Playing, Paused, Ended et Error, avec UUID courant, durée connue ou absente, position et durée en microsecondes entières, volume borné entre 0 et 100, message d'erreur et numéro de session. Les secondes de libmpv sont converties à la frontière du backend avec arrondi explicite à la microseconde la plus proche. Les événements retardés d'un fichier précédent sont ignorés grâce à ce numéro.

`play_queue(track_ids, start_index)` copie les UUID dans une file appartenant au service, résout le morceau initial et lance son ouverture asynchrone. Le signal de fin normale avance au suivant ; la fin de la file donne Ended. La commande Previous joue le morceau précédent sans règle cachée de retour au début ; au premier élément elle revient au début du morceau. Next au dernier élément termine la lecture proprement.

Observer la durée et la position via le backend, puis publier un rythme d'actualisation modéré, par exemple dix fois par seconde. Un seek est borné à la durée disponible et reste désactivé si la source n'est pas seekable. L'interface affiche l'état Seeking si nécessaire ; elle n'affirme pas une position validée avant le retour du backend. Ne pas bloquer l'UI en attendant un seek ou la fin d'un fichier.

Créer `src/mtee/models/playback_queue_model.py` pour une file consultable contenant titre, artiste, UUID, état courant et disponibilité. Pour cette livraison, choisir un élément existant permet de le jouer ; la réorganisation de playlists reste une autre fonctionnalité. Un tri, une nouvelle sélection ou la fermeture de l'onglet source ne modifie pas la file créée.

### Jalon 3 — Commandes et bascule de vue


Relier `src/mtee/qml/components/PlayerIsland.qml` et `src/mtee/qml/views/FullscreenPlayer.qml`, créés au plan 02, au même `PlayerModel` ; ajouter `src/mtee/qml/components/PlaybackQueueView.qml`. Fullscreen player suit `playing_track_id` ; l'inspecteur du navigateur suit la sélection. Ne pas réutiliser la sélection comme source des champs de Fullscreen player.

À l'entrée dans Fullscreen player, conserver l'état de `WorkspaceModel` comprenant onglets, division, groupe actif, sélection et positions de défilement. Masquer l'îlot de lecture pour ne pas dupliquer les commandes. Le retour restaure cet état sans recréer le backend. Les états Playback, Loading et Error restent visibles dans les deux présentations.

Le double-clic de l'explorateur utilise l'ordre instantané transmis par le plan 03. Un clic simple conserve son rôle de sélection. La touche Espace appelle pause/reprise uniquement si aucun champ de saisie, menu ou dialogue n'en a besoin ; tester notamment Search et les futurs champs de métadonnées. Les commandes conservent des noms anglais et un focus clavier visible.

Enrichir le `FileAccessCoordinator` du socle dans `src/mtee/services/file_access.py` comme point commun d'arbitrage par UUID. Le lecteur publie une utilisation en lecture et sait libérer son handle par une action explicite stop-and-release. L'édition et le déplacement des plans 05 et 06 demanderont un accès exclusif ; ces opérations ne devront pas interrompre le son de leur propre initiative.

### Jalon 4 — Formats et incidents


Compléter `tests/fixtures/audio/manifest.json` avec de petits échantillons autorisés MP3, FLAC, AAC brut, WAV PCM, AIFF PCM, Ogg/Vorbis, Opus et deux M4A distincts contenant AAC et ALAC. Chaque entrée indique conteneur, codec attendu, durée, provenance et droit d'utilisation. Un corpus non présent doit être obtenu avant de cocher la matrice ; ne pas produire ces fixtures avec FFmpeg comme dépendance implicite de cette étape.

À l'ouverture, relever le codec réel et les paramètres audio exposés par libmpv, en complétant les informations déjà connues de Mutagen. Associer les observations au UUID et à sa révision pour ne pas réécrire les caractéristiques d'une source remplacée. Un codec inconnu reste Unknown ; ne pas le déduire du seul nom de fichier.

Un fichier supprimé, illisible, déplacé extérieurement ou un périphérique audio perdu conduit à une erreur utilisable avec Retry et Next. Ne pas modifier les fichiers source pour réparer une lecture. L'arrêt de MTEE demande la fin du backend et ignore les callbacks devenus obsolètes pour éviter les crashs à la fermeture.

## Étapes concrètes


Depuis la racine du dépôt, installer d'abord l'environnement verrouillé existant. Mettre à jour le verrou uniquement lorsqu'une nouvelle dépendance a été choisie, puis retester avec le verrou :

    uv sync --locked

Créer `tests/unit/test_player_service.py`, `test_playback_queue.py`, `tests/integration/test_mpv_playback.py` et `tests/ui/test_player_views.py` ; compléter `tests/unit/test_file_access.py` du socle. Déclarer le marqueur `native_audio` dans `pyproject.toml`. Le faux backend permet des tests déterministes d'événements et d'erreurs ; les tests natifs exigent le runtime distribué et le corpus du manifeste. Après création du script d'acquisition et revue de son manifeste, exécuter :

    pwsh -File scripts/fetch_mpv.ps1

    uv sync --locked
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_player_service.py tests/unit/test_playback_queue.py tests/unit/test_file_access.py tests/ui/test_player_views.py
    uv run pytest -m native_audio tests/integration/test_mpv_playback.py
    uv run python -m mtee --data-dir .local/validation/04

Effectuer la matrice d'écoute puis vérifier la distribution :

    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/04-package

Enregistrer les commandes, résultats et essais manuels dans `docs/validation/04-lecteur.md`. Un test natif ignoré faute de DLL ou de périphérique doit y apparaître comme non exécuté et ne satisfait pas l'acceptation Windows.

## Validation et acceptation


Les tests unitaires couvrent toutes les transitions, la fin de file, les erreurs, les positions hors limites, l'absence de durée, les callbacks tardifs et la résolution d'un UUID dont le chemin a changé. Ils prouvent qu'un nouvel ordre d'explorateur ne modifie pas la file déjà créée et qu'un double lancement ne crée pas deux backends.

Les tests UI et le parcours manuel vérifient : sélectionner un autre morceau pendant la lecture ; changer de dossier et de tri ; ouvrir puis fermer Fullscreen player dix fois ; ouvrir la file ; mettre en pause depuis chaque vue ; déplacer la tête de lecture ; taper des espaces dans Search sans déclencher le lecteur. Le morceau et la file restent stables lors des changements de présentation, et le son n'est pas interrompu.

Pour chaque fixture de format, vérifier ouverture, son audible, pause/reprise, durée plausible, Next et seek à 25 %, 50 % et 75 %. Relever l'écart entre position demandée et position retournée : proposer une tolérance de 250 ms pour ce lecteur généraliste, puis documenter les limites des codecs. Cette cible n'est pas une promesse d'édition à l'échantillon près.

Tester suppression et verrouillage sur des copies. Simuler une erreur de décodage et une perte de sortie audio. Le lecteur montre une erreur et permet une nouvelle action ; l'explorateur reste navigable. Vérifier qu'une demande d'accès exclusif au fichier joué retourne Busy tant qu'un arrêt explicite n'a pas libéré le handle.

Lancer enfin le paquet autonome sur Windows sans Python ni mpv préinstallés et hors réseau. Consigner les versions et le périphérique audio utilisé. La présence d'une DLL dans `dist` n'est pas une preuve qu'elle a été chargée : relever le chemin de runtime réellement utilisé dans les diagnostics.

## Reprise et réexécution


Un backend indisponible ne doit pas empêcher de rouvrir la bibliothèque. Retry reconstruit uniquement la session de lecture nécessaire et conserve la file. Après erreur ou arrêt, libérer les ressources natives avant d'ouvrir une nouvelle session. À la fermeture, retirer les observers et attendre la terminaison hors thread UI avec une limite documentée.

Réexécuter les tests sur les mêmes fixtures ne modifie pas leurs octets. Les essais natifs s'effectuent dans un `--data-dir` isolé. Si le runtime doit être changé, mettre à jour manifeste, verrou éventuel, notices et preuve de packaging ensemble ; ne pas compter sur une DLL temporairement présente dans le répertoire courant.

## Interfaces et dépendances


`PlayerBackend` définit `load(path, session_id)`, `set_paused(bool)`, `seek(position_us)`, `set_volume(value)` et `close()`, avec événements de chargement, position, durée, codec, fin et erreur. Il ne connaît ni QML ni SQLite. `MpvBackend` traduit les temps internes entiers en secondes pour libmpv, et ses retours en microsecondes ; il utilise les appels supportés de la version verrouillée.

`PlayerService.play_queue(track_ids, start_index)`, `pause()`, `resume()`, `previous()`, `next()`, `seek(position_us)` et `stop_and_release(track_id)` alimentent un `PlaybackState` immuable. `PlayerModel` transforme cet état en propriétés Qt. `TrackRepository` résout chaque UUID au moment nécessaire, et les signaux de changement d'emplacement restent compatibles avec le plan 06.

`FileAccessCoordinator` arbitre utilisation en lecture et mutation exclusive par UUID, et rend un résultat Busy explicite. Les jobs futurs réutiliseront ce contrat. Ajouter uniquement le binding mpv et les ressources natives validées à cette étape ; aucune installation d'exécutable FFmpeg ou ffprobe, aucune analyse et aucun service réseau.

## Preuves et livraison Git


Mettre à jour ce plan et `docs/validation/04-lecteur.md` avant le commit avec matrice des formats, traces du runtime, captures de Fullscreen player et résultats réels. Reporter les limitations sans transformer un test simulé en écoute validée. Ne pas inclure les binaires de distribution ni un corpus personnel dans Git.

Sur `main`, avec `origin` vérifié vers `https://github.com/foliarn/mtee.git`, sélectionner les changements propres à cette étape. Les chemins de ressources ou de packaging peuvent être adaptés aux choix du socle après inspection.

    git status --short
    git diff --check
    git add -- pyproject.toml uv.lock src/mtee/domain/playback.py src/mtee/services/player_backend.py src/mtee/services/mpv_backend.py src/mtee/services/player_service.py src/mtee/services/file_access.py src/mtee/models/player_model.py src/mtee/models/playback_queue_model.py src/mtee/qml/components/PlayerIsland.qml src/mtee/qml/components/PlaybackQueueView.qml src/mtee/qml/views/FullscreenPlayer.qml tests/unit/test_player_service.py tests/unit/test_playback_queue.py tests/unit/test_file_access.py tests/integration/test_mpv_playback.py tests/ui/test_player_views.py tests/fixtures/audio/manifest.json resources/native/mpv/manifest.json scripts/fetch_mpv.ps1 scripts/build_windows.ps1 packaging/mtee.spec docs/native-dependencies.md docs/validation/04-lecteur.md "Plans d'exécution/04-lecteur.md"
    git diff --cached --check
    git diff --cached

Ajouter séparément les raccordements réellement nécessaires dans le bootstrap et le navigateur, en excluant tout travail étranger. Adapter le corps du commit aux vérifications effectuées, puis utiliser une here-string non interpolée :

    $mteeCommitMessage = @'
    feat(player): integrate shared libmpv playback and listening view

    Changes: one playback service, stable queue snapshots, transport controls,
    independent browser selection and a listening view that preserves playback.
    Validation: record unit, UI, native-format and standalone Windows results
    in docs/validation/04-lecteur.md, including runtime provenance.
    Limits: classic seek bar; waveform and metadata writing arrive later.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-04-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Les deux hashes doivent être identiques après fetch. Ne pas forcer le push si la branche distante a avancé ; inspecter et intégrer la divergence suivant le plan 00. Rapporter le hash distant vérifié après l'opération, sans l'inventer dans les preuves préalables.

Note de révision — 2026-09-10, Codex : création du plan ; réutilisation du coordinateur et des composants QML existants, acquisition libmpv vérifiée et microsecondes internes alignées sur `PLANS.md`.
