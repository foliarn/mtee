# Étape 33 — Analyse audio : BPM précis, tonalité et waveform permanente

ExecPlan vivant rédigé et réalisé le 2026-09-30. Suivre `PLANS.md` à la racine. Cette étape réintroduit une analyse calculée, retirée par le [lot 17](17-stabilisation-lot-01-retraits.md), mais avec un périmètre volontairement réduit : **BPM, tonalité et waveform**, à la demande explicite de l'utilisateur du 2026-09-30. Elle ne rétablit ni silences, ni loudness, ni tags sémantiques, ni analyse par apprentissage automatique.

## Objectif et résultat observable

L'utilisateur choisit un dossier ou des morceaux, fait un clic droit et lance **Analyze**. Le BPM (décimales, tempo stable), la tonalité et la waveform sont calculés en arrière-plan, suivis dans **Tasks**, puis conservés définitivement. Ils apparaissent dans les colonnes BPM/Key, l'inspecteur et le Fullscreen player. Une valeur éditée par l'utilisateur n'est jamais remplacée. La waveform n'est plus recalculée à chaque écoute et n'immobilise plus l'interface.

L'onglet **Analysis** des réglages choisit la notation de la tonalité (Camelot ou classique), la plage de BPM, le nombre d'analyses en parallèle, les décimales affichées du BPM et l'écriture facultative dans les tags.

## Progress

État au 2026-09-30 : implémenté depuis les sources et testé sur signaux synthétiques et sur des copies. Aucune collection réelle n'a été analysée ; la précision musicale sur de la vraie musique reste à constater par l'utilisateur.

- [x] Questions préliminaires posées et réponses de l'utilisateur consignées (voir Decision Log).
- [x] Noyau de calcul : extraction de traits en flux, tempo par peigne d'harmoniques, tonalité par profils de tonalité, waveform à taille fixe.
- [x] Persistance permanente : migration 015 (vérifiée aussi sur une copie de la base réelle), dépôt de résultats et de waveforms.
- [x] Service et job d'analyse : lot récursif, parallélisme réglable, annulation, échecs par piste.
- [x] Waveform : lecture en base, calcul unique, gel du rendu supprimé.
- [x] Interface : onglet Analysis, menus clic droit (liste, arbre, dossier), colonnes, inspecteur, Fullscreen.
- [x] Tests unitaires, d'intégration (FFmpeg réel) et d'interface ; suite complète comparée à HEAD.
- [x] Documentation, licence NumPy dans la spécification de packaging (sans build).
- [x] Correctif du 2026-09-30 : le bouton de colonnes ne faisait rien (préférences ignorées côté QML) ; corrigé et testé (`8756ee7`).
- [x] Correctif du 2026-09-30 : trop de morceaux sans tonalité ; méthode de tonalité revue et mesurée sur les tags de la bibliothèque de l'utilisateur, version d'analyse 2.
- [ ] Recette souris/clavier sur la collection réelle de l'utilisateur : non réalisée.
- [ ] Construction et vérification de l'EXE : non demandées, non réalisées (voir `AGENTS.md`).

## Surprises & Discoveries

Le gel de 2 s à 99 % ne venait pas seulement du calcul. Mesuré le 2026-09-30 avec `QQmlComponent` hors écran, la première peinture de l'ancien `WaveformView.qml` prenait 0,5 s pour 600 points, 4,9 s pour 1 200 et 17 s pour 2 400. Un micro-banc QML a isolé la cause : lire une liste Python (`Property(list)`) depuis QML copie la liste à chaque accès à un élément (`s[i]`), soit un coût quadratique. Le calcul de `displayPoints` parcourait `source[index][0]` sur ~1 200 éléments, ce qui bloquait le thread graphique quand la waveform passait à `ready`, à chaque redimensionnement ensuite. Un tampon binaire lu par `Float32Array` ramène ce coût à 2–17 ms.

Le calcul Python de l'ancienne pyramide (niveaux successifs, cache compressé) coûtait en plus 0,07 s après le décodage pour 5 minutes et 0,42 s pour 30 minutes sur la machine de mesure ; il tenait l'interpréteur pendant tout le décodage. Le cache disque existait (108 fichiers observés) mais sa clé dépendait de la révision de la source (taille, date, génération) : la moindre écriture de tag ou nouvelle génération le rendait inutilisable. La cause exacte des recalculs à chaque écoute n'a pas été reproduite ; la nouvelle clé (identité du morceau + durée audio) supprime cette classe de causes.

La première analyse de tempo (librosa, plan 09) donnait 117,45 BPM pour une fixture à 120 BPM. Le nouveau calcul retrouve les tempos synthétiques à quelques millièmes de BPM près sur 60 s et plus.

Les préférences de colonnes arrivent en QML comme des séquences Qt pour lesquelles `Array.isArray` est faux : `TrackListView.qml` les ignorait et retombait sur les colonnes par défaut, si bien que le bouton de choix des colonnes ne changeait rien. Le test `test_column_selection` échouait déjà avant l'étape 33 et signalait ce défaut. Par ailleurs, un `QByteArray` vide arrive en QML comme un `ArrayBuffer` de longueur nulle que `Float32Array` refuse : c'était une régression de la première livraison, corrigée avec un test.

Le premier réglage de la tonalité (seuil de corrélation 0,45, pondération en racine carrée) avait été validé sur des signaux synthétiques seulement. Sur 92 morceaux réels dont un autre outil avait écrit la tonalité, il ne renvoyait rien pour 43 d'entre eux et trouvait la tonalité exacte 24 fois. Voir `docs/validation/33-analyse-audio.md`.

Deux tests d'interface utilisaient `QTest.qWait`, qui garde le verrou de l'interpréteur : les threads de travail étaient affamés et un test de 0,4 s prenait 20 s. Les attentes des nouveaux tests alternent `processEvents` et `time.sleep`.

`git stash` lancé par erreur pendant le développement a remisé puis restauré immédiatement l'ensemble des fichiers suivis, y compris les modifications préexistantes de `.gitignore` et `AGENTS.md` de l'utilisateur ; l'état a été vérifié identique après `git stash pop`.

## Decision Log

2026-09-30 — Claude, sur réponses de l'utilisateur : BPM avec décimales pour une musique à tempo fixe, tonalité corrigée en Camelot ou notation classique compacte (`Am`, `F#m`), l'analyse prime sur le tag existant, mais la valeur éditée par l'utilisateur prime sur l'analyse.

2026-09-30 — Claude, sur réponses de l'utilisateur : une waveform absente est calculée à la lecture puis conservée ; elle est aussi produite par le job d'analyse. Les résultats sont permanents et ne sont invalidés que si la durée audio change (de plus d'une seconde) ; une écriture de tags ne les invalide pas.

2026-09-30 — Claude, sur réponses de l'utilisateur : deux entrées de menu, **Analyze** (ignore les morceaux déjà analysés) et **Re-analyze** (refait tout, sans jamais écraser une valeur éditée). Réglages : notation, plage de BPM, analyses en parallèle, décimales affichées, écriture dans les tags (désactivée par défaut ; si activée, remplace les tags BPM/Key existants par le résultat).

2026-09-30 — Claude, choix technique : NumPy seul, sans SciPy, librosa, Numba ni llvmlite. Les anciennes dépendances alourdissaient la distribution et le tempo librosa était imprécis. Décodage unique par le `MediaDecodeService` existant (22 050 Hz stéréo), traits accumulés en flux pour une mémoire bornée.

2026-09-30 — Claude, correctif après essai de l'utilisateur : la tonalité est estimée à partir de pics pondérés à la puissance 1,5 avec prise en compte des harmoniques (bande 80–2 500 Hz) et d'un profil des basses (40–250 Hz, poids 0,4), avec un seuil de corrélation de 0,35 et un contraste minimal entre classes de hauteur. Les réglages ont été choisis sur un plateau mesuré sur les tags de 92 morceaux de la bibliothèque, sans gabarits appris. La version d'analyse passe à 2 ; la waveform garde sa propre version. Une estimation faible est renvoyée plutôt que rien : l'utilisateur préfère une valeur à corriger à l'absence de valeur.

2026-09-30 — Claude, choix technique : la plage de BPM doit couvrir au moins une octave (`max ≥ 2 × min`) ; modifier l'une des bornes déplace l'autre. Sans cela, certains tempos n'auraient aucun représentant dans la plage. Quand deux représentants existent (plage plus large qu'une octave), le meilleur score l'emporte avec un léger a priori centré sur 120 BPM ; resserrer la plage lève l'ambiguïté demi/double tempo. Plage par défaut 70–180, 1 analyse en parallèle, 2 décimales, notation Camelot.

2026-09-30 — Claude, choix technique : les résultats sont stockés dans des tables séparées des tags (`track_analysis`, `track_waveforms`, migration 015 ; 010 reste réservé à l'historique retiré). Une valeur éditée est marquée par un drapeau (`bpm_user_edited`, `key_user_edited`) posé par l'éditeur de métadonnées après une sauvegarde vérifiée ; l'affichage suit l'ordre édité (tag) > calculé > tag.

2026-09-30 — Claude, choix technique : la waveform stockée est une suite de 1 200 paires (min, max) sur 16 bits au plus, soit quelques kilo-octets, au lieu de la pyramide multi-niveaux. Elle est transmise à QML sous forme de tampon binaire float32.

## Outcomes & Retrospective

Livraison fonctionnelle depuis les sources. Le calcul est validé sur des signaux synthétiques uniquement : tempo à moins de 0,03 BPM sur des boucles de 40 s et plus, 24 tonalités reconnues, absence de valeur pour le silence, le bruit, les nappes sans rythme et les extraits trop courts. La précision sur de la vraie musique n'est pas mesurée. Correctif du 2026-09-30 : sur 92 morceaux réels avec une tonalité écrite par un autre outil, la méthode révisée ne renvoie rien pour 3 morceaux (43 avant), trouve la tonalité exacte pour 49 (24 avant) et une tonalité exacte, à une quinte ou relative pour 73 % des résultats. Limites connues : tempo instable non traité (le résultat est la valeur moyenne dominante, avec un écart mesuré de 0,04 BPM pour une dérive de 1,5 %), ambiguïté demi/double tempo tranchée par le score et la plage, accords ambigus majeur/mineur relatifs, **Undo** de l'éditeur de métadonnées qui ne retire pas le drapeau « édité », résultats non recalculés quand la plage change (il faut **Re-analyze**), aucun import de l'ancienne analyse conservée dans les tables 010.

## Contexte et prérequis

Prérequis observés dans le code : `MediaDecodeService`, `JobService`, `FileAccessCoordinator`, `MetadataEditService`, dépôt de bibliothèque, migrations jusqu'à 014, tables 010 conservées comme historique. Le calcul s'appuie sur FFmpeg (LGPL, embarqué) uniquement pour décoder.

## Plan de travail et jalons

Jalon 1, calcul. `src/mtee/services/analysis/features.py` accumule en une passe des bins min/max de 20 ms, une enveloppe d'attaques (flux spectral logarithmique, fenêtre 1024, saut 256) et un profil de classes de hauteur sur 36 tiers de demi-ton. `tempo.py` évalue un peigne d'harmoniques sur le spectre de l'enveloppe, normalisé par le bruit local et par la racine du nombre de dents, puis affine par interpolation parabolique sur une grille de 0,01 BPM. `key.py` regroupe le profil autour de l'accord le plus énergétique et corrèle 24 rotations de deux profils publiés (Krumhansl-Kessler, Temperley). `waveform.py` réduit à 1 200 points par un `reduceat`. Une absence de pulsation ou de tonalité donne `None`, jamais une valeur inventée.

Jalon 2, persistance. Migration `015_track_analysis.sql`, `persistence/analysis_repository.py`, `domain/analysis.py`, `domain/musical_key.py`, `domain/waveform.py`. `LibraryRepository` fusionne les valeurs calculées dans les lignes de liste et sait lister récursivement les morceaux d'un dossier.

Jalon 3, services et jobs. `services/audio_analyzer.py` (décodage unique, contrôle de révision, bail de lecture), `services/analysis_service.py` (lot parallèle, échecs par piste, écriture facultative des tags par le service d'édition vérifié), `services/waveform_service.py` (lecture en base ou calcul unique), modèles Qt `AnalysisModel` et `AnalysisSettingsModel`.

Jalon 4, interface. `SettingsView.qml` (onglets General et Analysis), `ExplorerContextMenu.qml`, entrées dans `TrackContextMenu.qml`, `KeyBadge.qml` (couleur Camelot indépendante de la notation), tampon binaire dans `WaveformView.qml`.

## Étapes concrètes

Depuis la racine du dépôt :

    uv sync --locked
    uv run ruff check src tests
    uv run pytest tests/unit tests/integration tests/ui
    uv run python -m mtee --data-dir .local/validation/33

Le lancement manuel exerce : clic droit sur un dossier de l'explorateur, clic droit sur un morceau de la liste, onglet Analysis des réglages, colonnes BPM/Key, lecture d'un morceau puis retour sur ce morceau.

## Validation et acceptation

Critères vérifiés par les tests : tempo de boucles synthétiques à 0,03 BPM ; repli dans la plage demandée ; 24 tonalités, avec et sans batterie, avec désaccord de diapason ; absence de valeur sans preuve ; résultats identiques quelle que soit la découpe du flux ; valeur éditée jamais remplacée, y compris quand l'édition précède l'analyse ; waveform relue de la base sans décodage et conservée après une écriture de tags mais pas après un remplacement d'audio ; lot récursif, ignorant les morceaux déjà analysés sauf **Re-analyze** ; annulation ; échec d'une piste sans perte des autres ; tags écrits selon le réglage sur une copie de fichier ; première peinture de la waveform sous 1 s (une seconde de budget, ~14 ms mesurées contre ~4,9 s avant).

Non vérifiés : précision musicale sur la collection réelle, comportement sur de très gros dossiers, temps de calcul sur la machine de l'utilisateur, recette souris/clavier avec la vraie police, distribution Windows.

## Reprise et réexécution

Un morceau analysé n'est pas retraité par **Analyze**. Un changement de `ANALYSIS_ALGORITHM_VERSION` rend tous les résultats et waveforms obsolètes : ils sont alors recalculés à la demande. La migration 015 est transactionnelle et précédée de la sauvegarde SQLite habituelle. L'ancien cache `waveforms` du répertoire de cache n'est plus lu ; il peut être supprimé par l'utilisateur, aucune donnée n'a été nettoyée.

## Interfaces et dépendances

`AudioAnalyzer.analyze(source, revision, tempo_range, tonality, expected_duration_us, is_cancelled, report_progress) -> AnalysisOutcome`. `AnalysisService.run_batch(track_ids, settings, ...)`. `AnalysisRepository.save_result`, `mark_user_edited`, `save_waveform`, `load_waveform`. `WorkspaceModel.analyzeTracks(ids, force)` et `analyzeFolder(folder_id, force)`. Dépendance ajoutée : NumPy (BSD-3-Clause), verrouillée dans `uv.lock`, licence embarquée par `packaging/mtee.spec`.

## Preuves et livraison Git

Les commandes exécutées, versions, mesures et limites sont consignées dans [`docs/validation/33-analyse-audio.md`](../docs/validation/33-analyse-audio.md). Le commit ajoute explicitement le code, les tests et la documentation, sans les modifications préexistantes de `.gitignore`, `AGENTS.md` ni `.codex/`.

Note de révision — 2026-09-30, Claude : création et clôture du développement ; recette réelle et build non réalisés.
