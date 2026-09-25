# Étape 09 — Analyse audio sans apprentissage automatique

ExecPlan vivant rédigé le 2026-09-10 et réalisé le 2026-09-25. Suivre `PLANS.md` à la racine et `PLAN.md` §4.7, en respectant l'ordre silences/technique, loudness/crêtes/dynamique, tempo, tonalité. Les preuves reposent sur des fixtures synthétiques et des copies; aucune analyse du corpus de l'utilisateur n'est prétendue réalisée.

## Raccord aux retours de recette du 2026-09-25

Maintenir les contrats du [complément 06b](06b-correctifs-recette.md) : réconciliation de bibliothèque discrète et incrémentale, navigation stable, dates de fichiers séparées de la date musicale et des dates d'analyse, édition vérifiée sans mélange avec les résultats calculés. Exécuter sa recette transversale avec analyse active et préparer les résultats réels pour la revue de 10. Ne pas reconstruire silencieusement le catalogue ou la file de lecture pour rafraîchir une analyse. Aucun correctif ni test n'est déclaré réalisé par cette note.

## Objectif et résultat observable


L'utilisateur lance une analyse sur une sélection, suit son avancement, voit les résultats avec leur provenance et corrige tempo ou tonalité sans perdre sa correction lors d'une réanalyse. Les analyses alimenteront la recherche de l'étape 10 ; elles ne réécrivent jamais automatiquement les tags des fichiers.

La première livraison présente des mesures techniques, silences, loudness intégrée, crêtes, indications de dynamique, tempo estimé et tonalité estimée. Chaque résultat affiche méthode/version et état disponible, incertain, non applicable, périmé ou en erreur. Une piste non tonale ou trop courte ne reçoit pas une valeur musicale arbitraire.

## Progress


État au 2026-09-25 : l'étape est implémentée et validée sur fixtures synthétiques et copies. Aucun corpus personnel n'a été analysé; les mesures musicales ne déterminent pas une taxonomie produit.

- [x] Vérifier le pipeline, les révisions, l'annulation et les sources modifiées sur copies/fixtures.
- [x] Livrer mesures techniques et détection des silences.
- [x] Livrer loudness, crêtes et dynamique avec unités distinctes.
- [x] Livrer estimation de tempo et alternatives moitié/double.
- [x] Livrer estimation de tonalité et confirmation manuelle séparée.
- [x] Vérifier persistance, annulation, obsolescence, réanalyse et migration.
- [x] Produire les preuves et tester le paquet Windows copié.
- [ ] Committer le jalon et confirmer son push sur `origin/main`.

## Surprises & Discoveries


Le 2026-09-25, une fixture WAV mono synthétique de 14 s (PCM 16 bits, 22,05 kHz, accord de do majeur et impulsions à 120 BPM) a produit 117,4538 BPM, do majeur, deux silences totalisant 2 s, −18 LUFS intégrés et des crêtes sample/true de −4 dBFS/dBTP. Cela prouve le calcul sur la fixture, pas l'exactitude générale ni la qualité musicale sur une collection réelle. L'écart de tempo observé est −2,5462 BPM; les alternatives 58,7269/234,9077 BPM sont conservées. Le test QML couvre l'inspecteur; aucun parcours manuel de la fenêtre n'a été fait.

Le paquet embarque librosa, NumPy, SciPy, Numba et llvmlite. PyInstaller signale `tbb12.dll` absent pour le backend TBB facultatif de Numba; le paquet copié a néanmoins exécuté les cinq analyseurs en état `available`. L'exception SEH `0xe24c4a02` a été observée dans le test natif libmpv; un lancement complet ultérieur a terminé par access violation `-1073741819`. Le mécanisme causal n'est pas établi et aucun correctif de crash n'est revendiqué.

## Decision Log


2026-09-10 — Codex — Chaque résultat est indexé par UUID du morceau, révision source, analyseur, version et configuration. Une nouvelle exécution peut remplacer le résultat actif de cette méthode sans modifier l'historique des corrections manuelles.

2026-09-10 — Codex — Les confirmations manuelles ont leur propre provenance et révision de référence. La réanalyse les conserve ; si la source a changé, elles restent visibles avec un avertissement de pertinence à revoir. La valeur calculée et la valeur confirmée ne sont jamais confondues dans la persistance.

2026-09-10 — Codex — Les bibliothèques d'analyse sont ajoutées au moment où une fonction les nécessite. Les sorties sans ML servent de base mesurable et ne créent pas encore une taxonomie de styles, humeur ou énergie.

## Outcomes & Retrospective


Implémentation et fixtures contrôlées livrées; la précision musicale sur corpus réel demeure inconnue. Les tests d'intégration couvrent réanalyse avec conservation des corrections, changement de révision et annulation sans perdre les résultats valides. La suite `tests/unit` + `tests/integration` sans le test natif libmpv a terminé avec succès (deux tests sautés). La suite complète a interrompu le processus lors du test natif de lecture. La recette souris/clavier réelle reste non réalisée.

## Contexte et prérequis


Les étapes 07/08 apportent FFmpeg/ffprobe, `MediaDecodeService`, `JobService`, caches et timeline décodée. Les étapes 03/05 apportent bibliothèque et métadonnées. Vérifier que lecture, navigation et conversion continuent à fonctionner avant de lancer des calculs intensifs. Les états de jobs restent `queued`, `running`, `succeeded`, `failed`, `cancelled` ; une interruption est un échec codé `interrupted`, présenté **Interrupted**. Les lectures sont coordonnées par `FileAccessCoordinator`.

`track_id` est un UUID stable ; il ne se déduit ni du chemin ni d'un hash. `SourceRevision` contient `size_bytes: int`, `mtime_ns: int`, `file_id: str | None` et `generation: int`. La génération persistée augmente sur mutation connue ; le token détecte les changements usuels, mais un contrôle d'intégrité sensible exige aussi une empreinte en flux.

Les repères sont des microsecondes entières et les plages ont une fin exclusive. Réutiliser `domain/time.py` pour les silences et les durées. Les caractéristiques techniques du fichier viennent de l'inspection ; les valeurs calculées sont stockées séparément, avec leurs unités et leur méthode.

Constituer un manifeste de copies représentatives de la musique réelle, complété de signaux synthétiques contrôlés. Le manifeste privé consigne UUID de fixture, hash, durée, codec, référence d'écoute et droit d'utilisation ; ne pas committer les chemins personnels ou fichiers audio privés. Les références tempo/tonalité doivent indiquer qui les a établies et avec quel degré de certitude.

Créer un corpus restreint de validation automatique librement redistribuable et un corpus local d'écoute plus large. Enregistrer des morceaux à tempo stable, changements de tempo, demi-temps ambigu, introductions silencieuses, sons non tonaux, silence total et extraits trop courts. Les premiers résultats réels serviront à la revue de l'étape 10.

## Plan de travail et jalons


Le premier jalon crée `domain/analysis.py`, `services/analysis_service.py` et `persistence/analysis_repository.py`, puis une migration versionnée. Définir un résultat indépendant par analyseur : état, métriques/unités, segments, méthode/configuration, source/révision, date et erreurs. Le scheduler exécute un job CPU lourd à la fois par défaut ; les travaux légers restent soumis au budget global pour préserver lecture et UI.

Le deuxième jalon implémente `services/analyzers/silence.py` et `technical.py`. Utiliser le filtre FFmpeg `silencedetect` avec seuil initial de −60 dB et durée minimale de 0,5 s, valeurs proposées à calibrer sur le corpus ; rapporter les plages détectées et le mode combiné des canaux. L'inspection présente fréquence, canaux, codec et profondeur PCM pertinente, sans profondeur fixe inventée pour un codec avec pertes. Le contrat du filtre est vérifié dans la [documentation FFmpeg](https://ffmpeg.org/ffmpeg-filters.html#silencedetect).

Le troisième jalon implémente `services/analyzers/loudness.py` avec le scanner FFmpeg `ebur128`, sur l'intégralité du morceau à canaux natifs, sortie jetée et aucun filtre de normalisation. Activer explicitement les mesures sample/true peak disponibles dans le binaire distribué et vérifier le parsing de ses métadonnées et résumé. Rapporter LUFS intégrés, sample peak en dBFS, true peak en dBTP si calculée et loudness range en LU ; cette dernière est l'indication de dynamique retenue. Contrôler le contrat dans la [documentation du scanner ebur128](https://ffmpeg.org/ffmpeg-filters.html#ebur128).

Le quatrième jalon implémente `services/analyzers/tempo.py` avec NumPy/SciPy/librosa, versions verrouillées après essai Windows. Décoder en mono float32 à 22 050 Hz ; calculer `onset_strength` puis `beat_track` avec `hop_length=512`. Conserver tempo principal, alternatives moitié/double et dispersion des estimations par segment. Un score interne n'est pas une probabilité calibrée. L'utilisateur choisit une alternative ou une valeur positive ; normaliser le type de retour tempo selon la [documentation librosa 0.11 consultée](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html), à revalider contre la version effectivement verrouillée.

Le cinquième jalon implémente `services/analyzers/key.py` avec `chroma_stft`, `n_fft=4096`, `hop_length=512` et douze classes chromatiques, puis agrégation sur les fenêtres non silencieuses. Comparer les rotations de deux profils majeurs/mineurs versionnés par corrélation normalisée ; consigner les poids et leur provenance dans `docs/validation/09-analyse-sans-ml.md` avant d'accepter le prototype. Conserver meilleur résultat, second résultat et désaccords par segment pour permettre l'abstention. L'extraction suit la [documentation librosa chroma_stft](https://librosa.org/doc/0.11.0/generated/librosa.feature.chroma_stft.html) ; le choix des profils et leur utilité doivent être validés sur le corpus, sans prétendre que librosa estime directement une tonalité.

Le prototype tempo/tonalité utilise des segments de 60 s traités successivement ; viser un budget supplémentaire de 512 Mo par job sur la machine de référence. Les métriques globales incluent toutes les fenêtres retenues et affichent leur couverture. Une absence d'onsets, un chroma quasi uniforme, une durée utile insuffisante ou de forts désaccords entre segments donnent une estimation incertaine ou une abstention. Calibrer les seuils sur un sous-ensemble annoté et évaluer ensuite sur un autre sous-ensemble ; consigner séparation et choix, sans pourcentage de confiance inventé.

Le dernier jalon expose les résultats à l'inspecteur et à **Fullscreen player** via `AnalysisModel`. Montrer valeur calculée, confirmation, provenance et état périmé. Tester chaque méthode indépendamment, puis un lot complet, puis le paquet Windows avec ses bibliothèques numériques et binaires natifs.

## Étapes concrètes


Inspecter le dépôt puis installer les dépendances verrouillées :

    git status --short
    uv sync --locked

Créer les types `AnalysisSpec`, `AnalysisResult`, `AnalysisMetric`, `AnalysisOverride` et `AnalysisRunSummary` dans `src/mtee/domain/analysis.py`. Les unités et valeurs absentes sont explicites ; ne pas utiliser zéro comme sentinelle d'échec ou de tempo inconnu.

Créer le dépôt des résultats et celui des overrides dans `src/mtee/persistence/analysis_repository.py`. La migration prévoit l'unicité des résultats par exécution et analyseur, l'historique des confirmations, leur révision de référence et les index sur UUID/méthode. Garder les métadonnées Mutagen dans leurs structures existantes.

Implémenter le contrat d'analyseur commun dans `src/mtee/services/analyzers/base.py`. Chaque analyseur reçoit une source immuable et l'annulation, et produit un résultat validé ; aucun ne possède un handle d'écriture vers le fichier audio. Enregistrer les versions de décodage et de dépendances qui influencent les valeurs.

Vérifier révision source au début et à la fin de chaque travail. Invalider un résultat lorsque la source change pendant son calcul, et laisser les anciens résultats consultables comme périmés si cela est utile. L'écriture atomique en base évite de publier un demi-résultat comme une analyse terminée.

Pour loudness et silences, traiter le flux entier en mémoire bornée. Pour tempo et tonalité, appliquer le découpage de 60 s, éviter le double comptage des frontières et enregistrer segments, couverture, paramètres et agrégation. La première expérience compare segments et traitement intégral sur dix extraits courts annotés ; retenir les paramètres seulement si les écarts et besoins mémoire sont documentés. Si les profils de tonalité ne discriminent pas le corpus, adapter leurs poids avec provenance et retester le sous-ensemble d'évaluation, sans ajouter prématurément ML.

Dans `src/mtee/models/analysis_model.py` et `qml/components/AnalysisPanel.qml`, ajouter lancement, annulation, progression par méthode, erreurs et commandes **Confirm**, **Half tempo**, **Double tempo**, **Use calculated value**. La dernière commande retire explicitement la confirmation active après prévisualisation de la valeur à reprendre. Une éventuelle écriture vers les tags utilise l'éditeur existant et une action volontaire distincte.

Créer `tests/unit/test_silence_analysis.py`, `test_loudness_analysis.py`, `test_tempo_key_analysis.py` et `test_analysis_overrides.py` sous `tests/unit/`. Créer `tests/integration/test_analysis_pipeline.py` et `tests/ui/test_analysis_panel.py`. Les fixtures synthétiques permettent d'affirmer des résultats précis ; l'évaluation musicale consigne des écarts et une appréciation d'écoute.

Exécuter les vérifications une fois les analyseurs et fixtures disponibles :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_silence_analysis.py tests/unit/test_loudness_analysis.py tests/unit/test_tempo_key_analysis.py tests/unit/test_analysis_overrides.py tests/integration/test_analysis_pipeline.py tests/ui/test_analysis_panel.py
    uv run python -m mtee --data-dir .local/validation/09
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/09-packaged --smoke-test

Exécuter ensuite dans le paquet un lot couvrant les quatre familles d'analyse ; un simple démarrage ne prouve pas que SciPy/librosa ni les mesures FFmpeg fonctionnent une fois distribués.

## Validation et acceptation


Sur une fixture synthétique, les plages de silence retrouvent les bornes connues selon la précision temporelle du filtre et des frames décodées, mesurée avant acceptation. Le seuil, la durée minimale, la version FFmpeg et la règle de fusion sont enregistrés avec le résultat. Silence total, fichier vide, signal corrompu et extrait trop court produisent chacun un état documenté sans BPM ou tonalité inventés.

Comparer les mesures loudness à des fichiers de référence publiés avec leur valeur attendue, compatibles avec les droits de redistribution, ou à une implémentation indépendante validée. Fixer les tolérances avant le test, viser 0,1 LU pour la loudness intégrée et documenter toute divergence. Un test qui appelle deux fois le même analyseur ne prouve pas son exactitude.

Vérifier qu'un sample peak et une true peak portent des noms et unités différents. Pour un signal à amplitude connue, contrôler l'échelle dBFS. Les pistes ne satisfaisant pas les conditions d'une mesure de loudness range affichent **Not applicable**, sans zéro trompeur.

Tester les tempos synthétiques connus et les cas moitié/double. Pour le corpus musical, publier nombre de titres, erreurs absolues, nombre de cas dans une tolérance fixée à l'avance et cas équivalents moitié/double séparément. Les désaccords d'écoute deviennent des limites de méthode et peuvent motiver une abstention.

Pour la tonalité, combiner accords synthétiques contrôlés et références d'écoute documentées. Distinguer erreur de classe, mode incorrect et cas indéterminés ; ne pas attribuer une vérité certaine à toutes les annotations manuelles. Les critères d'acceptation portent sur la traçabilité et l'utilité constatée, sans imposer une précision arbitraire non vérifiée.

Confirmer manuellement BPM et tonalité, réanalyser, redémarrer et réanalyser avec une version/configuration différente : les confirmations restent intactes. Modifier une copie source : le résultat calculé devient périmé et la confirmation garde sa provenance avec un état à revoir. Vérifier les hashes des fichiers avant/après ; aucun tag ne change.

Annuler un lot, injecter un échec d'analyseur et déconnecter une source. Les autres résultats valides restent lisibles ; la reprise cible uniquement les travaux souhaités et ne marque pas tout le lot comme réussi. Lancer lecture/navigation pendant calcul et consigner temps, mémoire et réactivité sur la machine de référence.

Écrire `docs/validation/09-analyse-sans-ml.md` avec versions, configurations, corpus, mesures, exemples d'incertitude et captures UI. Préparer une synthèse de résultats utiles pour l'étape 10, sans proposer d'office une liste de tags sémantiques.

## Reprise et réexécution


Un résultat complet de même source/révision/méthode/configuration est réutilisable. **Reanalyze** crée une exécution traçable et ne supprime pas les confirmations. Une nouvelle version d'algorithme invalide la compatibilité de cache, sans effacer le résultat précédent avant succès du nouveau calcul.

Les jobs interrompus deviennent `failed` avec le code `interrupted`, affiché **Interrupted** au redémarrage. La relance présente les méthodes concernées et vérifie les sources ; elle ne recommence pas silencieusement toute la collection. Les erreurs d'un fichier n'annulent pas les résultats indépendants d'autres fichiers.

La migration est transactionnelle et testée sur copie de base. Sauvegarder cette copie avant les essais de migration ; restaurer la sauvegarde de test si nécessaire. Les caches décodés sont jetables et ne doivent jamais être confondus avec les overrides persistants.

## Interfaces et dépendances


`AnalysisService.preview(track_ids, specs) -> AnalysisBatchPreview` décrit sélection, méthodes, révisions et ressources estimées ; `submit(preview) -> JobId` revalide les sources ; `results(track_id) -> AnalysisView` rassemble résultats et confirmations sans écraser leurs provenances. `JobService.cancel(job_id)` contrôle l'annulation.

`Analyzer.analyze(source, config, cancellation) -> AnalysisResult` produit des valeurs typées, unités, méthode/version et diagnostics. `AnalysisRepository.save_result(result)` et `save_override(override)` sont distincts. Une requête de valeur effective indique explicitement la priorité confirmation/calcul/tag et conserve la possibilité de lire chaque source séparément.

`AnalysisOverride` contient UUID du morceau, champ, valeur, date, référence de révision, provenance manuelle et historique ; il n'est pas une écriture Mutagen. L'étape 10 pourra choisir les champs calculés ou effectifs dans ses critères de recherche sans ambiguïté.

Réutiliser `MediaDecodeService`, FFmpeg/ffprobe et `JobService`. Documenter les versions/licences NumPy, SciPy et librosa réellement retenues et les verrouiller après essai Windows. Aucun modèle ML, service distant ni accès réseau n'est requis pour analyser.

## Preuves et livraison Git


Mettre à jour le plan et le rapport avec les résultats constatés, puis inspecter toutes les modifications. Ajouter les fichiers d'analyse explicitement ; inclure individuellement migration, dépendances et adaptations partagées après revue.

    git status --short
    git diff --check
    git add -- src/mtee/domain/analysis.py src/mtee/services/analysis_service.py src/mtee/services/analyzers/base.py src/mtee/services/analyzers/silence.py src/mtee/services/analyzers/technical.py src/mtee/services/analyzers/loudness.py src/mtee/services/analyzers/tempo.py src/mtee/services/analyzers/key.py src/mtee/persistence/analysis_repository.py src/mtee/models/analysis_model.py src/mtee/qml/components/AnalysisPanel.qml tests/unit/test_silence_analysis.py tests/unit/test_loudness_analysis.py tests/unit/test_tempo_key_analysis.py tests/unit/test_analysis_overrides.py tests/integration/test_analysis_pipeline.py tests/ui/test_analysis_panel.py docs/validation/09-analyse-sans-ml.md "Plans d'exécution/09-analyse-sans-ml.md"
    git diff --cached --check
    git diff --cached

Compléter ce message avec les validations et limites réelles avant de l'utiliser :

    git fetch origin
    git log --oneline --left-right HEAD...origin/main
    $mteeCommitMessage = @'
    feat(analysis): add versioned audio metrics and manual confirmations

    Changes: add silence, loudness, tempo and key analysis with provenance,
    cancellable jobs and manual values preserved across reanalysis.
    Validation: replace with exact reference, corpus and Windows package results.
    Limits: replace with uncertain material, tolerances and resource constraints.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-09-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Confirmer l'égalité des deux révisions après fetch et rapporter le résultat réel dans la livraison. Si le distant refuse le push, conserver le commit et résoudre la divergence sans force. Ne pas committer une affirmation anticipée de push ni le hash du commit dans son propre contenu.

Note de révision — 2026-09-10, Codex : création et harmonisation avec PLANS.md, identités stables, services communs et preuves futures explicités ; aucun développement ou test prétendu réalisé.
