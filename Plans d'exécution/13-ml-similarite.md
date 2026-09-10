# Étape 13 — Évaluer le ML et la similarité musicale


Ce document est un ExecPlan vivant régi par `PLANS.md`, à la racine du dépôt. Il met en œuvre le jalon J et la partie ML/similarité du §4.11 de `PLAN.md`. Les fichiers et services annoncés sont des cibles de développement; leur présence ne doit pas être supposée avant la vérification du dépôt.

## Objectif et résultat observable


À partir d'un morceau local, l'utilisateur peut demander une liste de morceaux similaires et juger cette proposition à l'écoute. Chaque résultat indique le système utilisé et permet d'ouvrir ou de lire la version locale exacte. La recherche reste disponible hors connexion après installation des composants facultatifs retenus.

La première livraison est une évaluation documentée sur la musique de l'utilisateur, puis une fonctionnalité locale uniquement si son bénéfice et son coût sont acceptables. Si aucun candidat n'apporte un progrès utile, le résultat attendu est une décision motivée de différer le ML, avec le comparateur non ML conservé et aucun modèle annoncé comme validé.

Les représentations calculées n'écrivent ni les tags du fichier ni les corrections manuelles. Une proximité numérique n'est pas une preuve que deux fichiers contiennent le même enregistrement, la même version ou une édition interchangeable.

## Progress


- [x] 2026-09-10 — Plan préparé; aucun modèle sélectionné, téléchargé ou évalué à ce stade.
- [ ] Définir les cas d'usage, le corpus et les critères d'évaluation avec l'utilisateur.
- [ ] Vérifier les modèles candidats, licences, ressources et installation Windows.
- [ ] Comparer un point de référence non ML à des prototypes locaux.
- [ ] Décider de l'activation, du statut expérimental ou du report selon les résultats.
- [ ] Livrer les interfaces et traitements retenus, vérifier Windows, committer et pousser.

## Surprises & Discoveries


Aucune observation expérimentale n'est disponible. Ajouter ici les surprises d'écoute, incompatibilités de dépendances, écarts CPU/GPU, temps de calcul, téléchargements cachés ou limites de licence constatés, avec leur preuve. Un nom de modèle populaire ne constitue ni un résultat d'écoute ni une validation de distribution.

## Decision Log


2026-09-10, Codex — Évaluer avant d'intégrer. Motif : `PLAN.md` exige de choisir selon la musique réelle, les ressources nécessaires et les licences; ces données ne sont pas encore connues.

2026-09-10, Codex — Définir un point de comparaison avec les mesures non ML déjà livrées. Motif : un modèle doit apporter un bénéfice perceptible face à une méthode simple, pas seulement produire des vecteurs.

2026-09-10, Codex — Démarrer par un index exact local adapté à moins de 10 000 morceaux; n'ajouter un index spécialisé qu'après mesure. Motif : éviter une dépendance opérationnelle supplémentaire sans besoin démontré.

2026-09-10, Codex — Traiter chaque configuration de modèle comme une nouvelle version d'analyse. Motif : des vecteurs produits par des versions ou prétraitements différents ne sont pas comparables implicitement.

## Outcomes & Retrospective


À remplir avec la décision finale, le corpus anonymisé, la préférence d'écoute, les coûts et les limites. Une étude concluant au report est une conclusion valide si ses critères ont été fixés avant les résultats et si les fonctionnalités locales existantes restent utilisables. Ne pas cocher une intégration qui n'a pas eu lieu.

## Contexte et prérequis


MTEE utilise Python 3.12, uv, PySide6/QML et SQLite. La logique pure réside dans `src/mtee/domain`, les traitements dans `services`, les modèles Qt dans `models`, la persistance dans `persistence` et les vues anglaises dans `qml`. Les fonctions principales fonctionnent localement sans compte réseau.

Les étapes 01 à 12 de la séquence initiale doivent avoir leurs preuves de livraison. Ce jalon dépend directement du décodage, de la gestion des tâches, de l'analyse non ML, des corrections manuelles et des playlists. L'échange Rekordbox fournit un scénario de collection, sans être une dépendance technique de l'inférence.

`track_id` est un UUID stable indépendant du chemin et d'une empreinte de contenu. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` est immuable; la génération entière est persistée. Une réanalyse doit invalider les résultats devenus obsolètes sans écraser une valeur confirmée par l'utilisateur.

`Derivation(source_track_id, source_revision, derived_track_id, transform, time_mapping)` conserve l'origine d'une copie produite. Chaque dérivé a sa propre durée et ses propres analyses. Les temps partagés sont des microsecondes entières, avec `TimeRange(start_us, end_us)` à fin exclusive. Une similarité n'autorise pas à transférer des cues ou des analyses entre source et dérivé.

Le vocabulaire des tags défini à l'étape 10 reste celui qui a été validé. Ce plan ne crée pas automatiquement une taxonomie de genres ou d'émotions. D'éventuelles nouvelles étiquettes perceptuelles nécessitent une revue séparée et une provenance visible.

Préparer un corpus local copié dans `.local/validation/13`, avec diversité de genres réellement écoutés, tempos, enregistrements et éditions. Conserver les fichiers audio privés hors Git. Les tests committés utilisent de courts signaux synthétiques et de petites représentations artificielles, jamais des poids de modèle ou de la musique sans autorisation de redistribution.

## Plan de travail et jalons


### Jalon 13.1 — Définir ce que « similaire » signifie ici


Mener une courte revue d'écoute pour choisir les usages : continuité de texture, énergie comparable, proximité rythmique ou autre préférence concrète. Distinguer une recherche de ressemblance d'une recherche d'identité de version. Enregistrer les critères retenus dans `docs/validation/13-ml-similarite.md` sans les déduire arbitrairement du nom des fichiers.

Préparer au moins vingt morceaux requêtes diversifiés et des exemples positifs/négatifs jugés à l'écoute. Prévoir des familles de versions proches pour vérifier qu'une liste n'est pas remplie de copies du même titre. Ces familles servent à organiser l'évaluation, sans fusionner les identités du catalogue.

Séparer les requêtes servant à choisir les paramètres de celles réservées au bilan final. Fixer avant l'évaluation le nombre de résultats écoutés par requête, la grille de jugement, le temps maximum acceptable et les seuils de mémoire/disque sur le matériel Windows disponible.

Convenir d'une règle de décision : amélioration perceptuelle attendue face au point de référence, proportion minimale de listes utiles et coût maximum. Inscrire les valeurs acceptées avant de lancer le bilan final. Si l'utilisateur n'est pas disponible pour écouter, produire les mesures techniques et garder la pertinence perceptuelle non validée.

### Jalon 13.2 — Vérifier un petit nombre de candidats


À l'exécution, consulter uniquement les publications, dépôts officiels, cartes de modèle et licences primaires des candidats. Enregistrer URLs, date de consultation, version exacte du code et des poids, provenance, empreinte attendue si publiée, licence des poids et du runtime, taille et besoins matériels. Distinguer autorisation d'usage local et redistribution dans une application open source.

Limiter le prototype à deux candidats pertinents au plus, en plus du point de référence non ML. Ne pas choisir un nom de modèle dans ce plan sans avoir vérifié sa disponibilité, ses entrées attendues et son installation sur Python 3.12 Windows au moment de l'exécution.

Valider explicitement le prétraitement : fréquence, canaux, niveau, fenêtres, durée acceptée et agrégation des segments. Réutiliser `MediaDecodeService.stream_pcm` pour fournir les échantillons et conserver une configuration d'analyse versionnée. Le rééchantillonnage pour l'inférence ne modifie jamais le fichier audio.

Installer les dépendances et poids dans un environnement/profil facultatif isolable. Un téléchargement de modèle doit être une action explicite de l'interface, indiquant taille, licence et destination locale; aucun premier lancement ne lance un transfert caché. Si les droits de redistribution restent incertains, exclure les poids du paquet.

### Jalon 13.3 — Comparer les résultats et décider


Construire le point de référence à partir des caractéristiques non ML réellement disponibles, normalisées de façon documentée. Les valeurs absentes doivent donner un comportement explicite. Préserver les valeurs manuelles et préciser si le comparateur prend une mesure brute ou une valeur confirmée.

Comme point de départ concret, utiliser tempo confirmé s'il existe, sinon calculé, loudness intégrée et loudness range lorsqu'elle est applicable. Standardiser chaque mesure avec moyenne et écart-type du seul sous-ensemble de réglage ; une mesure constante est retirée. Classer par distance euclidienne moyenne sur les mesures communes, avec au moins deux mesures présentes et un départage stable par UUID. Les paires insuffisamment décrites restent sans score, pas artificiellement proches. Cette méthode est une référence simple à battre, et ne prétend pas résumer la perception musicale ; consigner toute modification avant le bilan final.

Pour les représentations ML, tester d'abord la similarité cosinus de vecteurs normalisés, en excluant les vecteurs nuls et non finis. Si le modèle prescrit une autre métrique, appliquer celle de sa documentation et la conserver dans `EmbeddingSpec`. Calculer les scores exactement par blocs bornés sur le catalogue, sans matrice de toutes les paires ; l'index est ici l'ensemble des vecteurs et de leurs clés de version.

Exécuter les prototypes sur le même corpus et produire pour chaque requête des listes anonymisées pour l'écoute. Mesurer les jugements utiles dans les dix premiers résultats, la préférence par rapport au point de référence et les erreurs typiques. Rapporter les effectifs et désaccords; un petit corpus personnel ne prouve pas une qualité universelle.

Mesurer téléchargement, installation, temps de première analyse, réanalyse à cache chaud, mémoire maximale, taille de cache et temps de requête. Séparer décodage et inférence. Tester la lecture simultanée pour vérifier que l'analyse ne provoque pas de blocage durable ou de coupure audible.

Appliquer les critères préétablis. Si le bénéfice manque, conserver l'étude et le point de référence utile, puis différer l'intégration ML. Si seuls certains usages passent, exposer un statut `Experimental` et ce périmètre précis. Un échec du prototype ne déclenche pas automatiquement un entraînement de modèle.

### Jalon 13.4 — Intégrer seulement le candidat retenu


Créer une commande `Find similar` depuis un morceau sélectionné, avec une liste qui affiche titre, artiste, version locale et méthode. La sélection de résultats reste indépendante du morceau joué. Les résultats sont lisibles dans le lecteur commun et peuvent être ajoutés explicitement à une playlist.

Ajouter une vue de disponibilité : `Model not installed`, `Analyzing`, `Ready`, `Outdated`, `Unavailable` et `Could not analyze`. Les détails techniques se trouvent dans le diagnostic; le parcours principal explique ce que l'utilisateur peut faire.

Indexer uniquement les vecteurs dont la révision et la configuration correspondent à l'index actif. Les annulations et changements de fichier retirent les entrées obsolètes. Un modèle indisponible conserve l'explorateur, la lecture, les tags et les playlists en état de fonctionnement.

Si aucune intégration ML n'est retenue, limiter ce jalon à l'évaluation reproductible, au point de référence s'il est validé et à une décision de report clairement visible dans les documents. Ne pas créer une interface factice prétendant offrir une analyse absente.

## Étapes concrètes


Depuis la racine du dépôt, vérifier le périmètre des changements et utiliser le verrou de dépendances existant.

    git status --short
    git branch --show-current
    uv sync --locked

Créer `src/mtee/domain/similarity.py`, `src/mtee/services/similarity_service.py`, `src/mtee/services/ml_runtime.py` et `src/mtee/persistence/similarity_repository.py`. Ajouter `src/mtee/models/similarity_model.py` et `src/mtee/qml/SimilarityView.qml` uniquement pour la fonctionnalité retenue. Un runtime optionnel doit pouvoir être importé paresseusement, sans faire échouer le démarrage de base.

Écrire `scripts/evaluate_similarity.py` avec une entrée de manifeste local, un dossier de sortie et une graine lorsque pertinente. Il doit produire configuration, métriques techniques et listes à juger. Il ne doit pas embarquer la liste de morceaux privés dans le dépôt. Conserver le schéma et un exemple synthétique dans `tests/fixtures/similarity`.

Si le profil facultatif `ml` est retenu, le déclarer dans `pyproject.toml`, mettre à jour `uv.lock` et documenter l'installation `uv sync --locked --extra ml`. Cette commande n'est applicable qu'après définition de cet extra; le profil de base reste installé par `uv sync --locked`.

Ajouter les tests prévus ci-dessous et lancer les contrôles sur le profil de base, puis sur le profil ML retenu. Le téléchargement d'un gros modèle ne doit pas être une dépendance cachée des tests unitaires.

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_similarity_service.py tests/integration/test_similarity_pipeline.py tests/ui/test_similarity_view.py
    uv run python scripts/evaluate_similarity.py --manifest .local/validation/13/corpus.json --output-dir .local/validation/13/results
    uv run python -m mtee --data-dir .local/validation/13
    pwsh -File scripts/build_windows.ps1

Les tests UI et fichiers de vue ne sont créés que si la décision est d'intégrer une fonctionnalité; en cas de report, adapter explicitement les commandes et le bilan au prototype réellement livré. Tester `dist/MTEE/MTEE.exe` sans réseau et sans runtime ML installé, puis avec la configuration facultative si elle est prise en charge par ce paquet.

## Validation et acceptation


Les tests unitaires vérifient les dimensions, valeurs non finies, vecteurs nuls, distance choisie, ordre stable à égalité, exclusion du morceau requête et comportement sur un index vide. Une recherche ne mélange jamais deux signatures de modèle incompatibles.

Les tests d'intégration utilisent un runtime factice déterministe pour vérifier orchestration, transactions, progression, annulation et invalidation après changement de `SourceRevision`. Ajouter un test de fumée avec les vrais poids seulement lorsque ceux-ci sont installés explicitement; son absence est signalée, jamais comptée comme succès d'inférence.

Tester le fichier trop court, illisible, silencieux, très long et celui qui change pendant le calcul. L'échec d'un morceau ne bloque pas tout le lot. Vérifier qu'aucune écriture de métadonnées, correction manuelle ou substitution de version n'est effectuée par l'analyse.

L'évaluation finale réutilise les requêtes mises de côté et la grille fixée au début. Documenter les listes utiles, échecs, coût matériel et comparaison au point de référence; l'utilisateur doit pouvoir vérifier à l'écoute la conclusion de pertinence.

L'acceptation d'une intégration nécessite les critères d'écoute et de ressources convenus, un profil de base indépendant, la recherche locale hors connexion après installation et un paquet Windows vérifié. L'acceptation d'un report nécessite une étude reproductible, une justification claire et aucun résidu qui dégrade l'application.

## Reprise et réexécution


Chaque tâche porte `track_id`, `SourceRevision` et la signature d'analyse. Réexécuter une tâche déjà finalisée avec la même clé utilise son résultat valide; changer un paramètre ou le modèle crée une nouvelle clé. Ne pas écraser les résultats encore utilisés par un index actif.

Écrire les fichiers de représentation vers des temporaires appartenant à l'opération, puis finaliser après vérification. Au redémarrage, les tâches interrompues restent relançables et les temporaires identifiés peuvent être nettoyés. La reconstruction de l'index ne modifie jamais le catalogue audio.

Un téléchargement partiel ne devient pas un modèle `Ready`. Reprendre seulement si le mécanisme du fournisseur est vérifié, sinon recommencer dans un nouveau temporaire. Vérifier l'intégrité avec les informations officielles disponibles et enregistrer la provenance locale.

En cas de manque de mémoire ou de runtime incompatible, réduire la concurrence et proposer le point de référence disponible. Le mode CPU ne doit pas être annoncé comme utilisable tant qu'il n'a pas été mesuré. La suppression explicite d'un cache ne supprime pas les corrections manuelles ni les playlists.

## Interfaces et dépendances


`EmbeddingSpec` contient l'identifiant et la version du modèle, l'empreinte des poids, la configuration de prétraitement, l'agrégation et la dimension. Sa signature normalisée participe à la clé de cache. `EmbeddingRecord` relie cette signature à `track_id`, `SourceRevision`, l'état et l'emplacement local du vecteur.

`SimilarityService.capabilities() -> SimilarityCapabilities` expose les méthodes utilisables. `submit_analysis(track_ids, method) -> JobId` crée des tâches via `JobService`. `query(track_id, method, limit) -> list[SimilarityHit]` retourne des références stables et un score identifié comme relatif à la méthode, sans le présenter comme probabilité universelle.

`ModelRuntime.describe() -> EmbeddingSpec` et `infer(pcm, config) -> Embedding` isolent la dépendance choisie. `MediaDecodeService.stream_pcm` fournit les données; les objets Qt et QML ne reçoivent pas de tenseurs volumineux. Les calculs bloquants restent hors du thread UI et leur annulation est observée entre unités de travail bornées.

`EvaluationManifest` décrit requêtes, corpus, groupes de versions et répartition réglage/bilan. `EvaluationReport` référence les configurations et jugements réellement collectés. Les rapports versionnés du dépôt n'incluent que des agrégats et exemples redistribuables.

## Preuves et livraison Git


Créer `docs/validation/13-ml-similarite.md` avec les sources primaires, licences séparées, versions, matériel, protocole préétabli, résultats d'écoute, mesures et décision. Mettre à jour les sections vivantes de ce plan. Aucune mesure ne doit être inventée ni extrapolée d'un autre ordinateur.

Indexer les seuls fichiers effectivement livrés. La liste ci-dessous vise le chemin avec intégration; retirer explicitement les fichiers non créés en cas de report, et ajouter les migrations ou dépendances individuellement après inspection. Ne pas indexer corpus, poids, caches et configurations personnelles.

    git status --short
    git diff --check
    git add -- src/mtee/domain/similarity.py src/mtee/services/similarity_service.py src/mtee/services/ml_runtime.py src/mtee/persistence/similarity_repository.py src/mtee/models/similarity_model.py src/mtee/qml/SimilarityView.qml scripts/evaluate_similarity.py tests/fixtures/similarity tests/unit/test_similarity_service.py tests/integration/test_similarity_pipeline.py tests/ui/test_similarity_view.py docs/validation/13-ml-similarite.md "Plans d'exécution/13-ml-similarite.md"
    git diff --cached --check
    git diff --cached

Remplacer les indications entre chevrons par les résultats réels avant d'exécuter le commit. En cas de report, adapter le titre à `feat(similarity): add evaluation baseline and record ML decision`.

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step13-commit.txt'
    @'
    feat(similarity): add evaluated local similarity workflow

    Changes: <baseline, chosen optional model or documented deferral, versioned cache and UI>
    Validation: <actual tests, listening corpus results, resource measurements and Windows package>
    Limits: <validated uses, missing runtime cases, licenses and remaining uncertainty>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Exécuter chaque commande après succès de la précédente, avec `origin` configuré sur `https://github.com/foliarn/mtee.git` à l'étape 00. Les deux identifiants doivent être identiques. Diagnostiquer un push refusé sans force ni réécriture d'historique; communiquer le hash après création du commit, sans le rendre autoréférentiel dans son contenu.

Note de révision — 2026-09-10, Codex : création et revue du plan ; préciser la référence non ML, la métrique initiale, les conditions d'évaluation et la distinction entre étude conclue et intégration livrée.
