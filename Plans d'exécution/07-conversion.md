# Étape 07 — Conversion audio et fichiers dérivés

Ce document est un ExecPlan vivant rédigé le 2026-09-10. Son exécution suit `PLANS.md` à la racine et réalise `PLAN.md` §4.5, §3 « Onglet Conversion » et le contrôle commun à chaque livraison. Les fichiers et commandes ci-dessous sont à créer ou à exécuter pendant le développement ; aucun résultat de test ni livraison Git n'est déclaré accompli.

## Objectif et résultat observable


L'utilisateur ajoute des fichiers à l'onglet anglais **Convert**, choisit une combinaison de sortie réellement disponible, voit la destination et les avertissements, puis produit des copies sans modifier ses sources. Il suit la progression de chaque entrée, annule les tâches et relance un échec après correction. La conversion reste utilisable pendant la lecture et la navigation.

La livraison couvre les sorties audio accessibles dans la distribution FFmpeg retenue, après vérification de leurs combinaisons conteneur/codec et paramètres. Elle n'applique aucune normalisation de volume implicite. Un profil nommé d'après une platine n'est disponible qu'après un essai consigné sur ce modèle précis ; des réglages génériques restent utilisables sans cette certification.

## Progress


État au 2026-09-10 : plan préparé, aucun jalon de développement exécuté.

- [ ] Vérifier les prérequis, les contrats existants et les binaires distribuables.
- [ ] Implémenter l'inspection et la matrice de capacités vérifiées.
- [ ] Implémenter aperçu, réservation des noms et file limitée à deux conversions.
- [ ] Implémenter vérification de sortie, publication sans écrasement et filiation.
- [ ] Relier la file et les options compatibles à l'onglet Convert.
- [ ] Valider les erreurs, l'annulation, les copies de corpus et le paquet Windows.
- [ ] Renseigner les preuves, créer le commit détaillé et vérifier le push.

## Surprises & Discoveries


Aucune observation d'exécution à ce stade. Noter ici les différences entre capacités annoncées et conversions effectivement réalisables, les effets de délai d'encodage et les limites de transfert des tags. Chaque observation devra inclure une commande ou un fichier de preuve et son effet sur le plan.

## Decision Log


2026-09-10 — Codex — FFmpeg et ffprobe sont exécutés hors du processus UI, avec des arguments structurés et `shell=False`. Les sorties sont audio uniquement. Cette frontière maintient la réactivité et empêche les chemins fournis par l'utilisateur d'être interprétés comme commandes.

2026-09-10 — Codex — `ConversionService` est propriétaire des conversions ; `MediaDecodeService` fournira le décodage PCM commun aux étapes 08, 09 et 11. Ces deux services utilisent `JobService` et les mêmes contrôles de révision de source.

2026-09-10 — Codex — Un dérivé devient un morceau distinct identifié par son propre UUID. La filiation et la correspondance temporelle sont persistées séparément, car une sortie encodée n'a pas nécessairement la même origine temporelle que son entrée.

## Outcomes & Retrospective


Non exécuté. À compléter avec sorties produites, matrice de formats réellement validée, mesures, limites et référence du commit après son obtention. Distinguer la conversion logicielle testée de la compatibilité matérielle éventuellement non testée.

## Contexte et prérequis


Les étapes 00 à 06 ont livré le dépôt sur `https://github.com/foliarn/mtee.git`, un projet Python 3.12 avec `uv.lock`, l'explorateur, `PlayerService`, les écritures Mutagen, la gestion de fichiers et un paquet Windows. Relire leurs preuves et vérifier leurs interfaces avant d'introduire FFmpeg. La conversion ne doit pas être rétroactivement ajoutée au premier lecteur.

Le futur code réside dans `src/mtee/domain`, `services`, `models`, `persistence` et `qml`. Si un contrat existe sous un autre nom, le réutiliser et documenter la correspondance au lieu de construire une seconde pile. `JobService` exécute les travaux en arrière-plan et émet des mises à jour que le modèle Qt applique sur le thread UI. `FileAccessCoordinator` coordonne décodage, lecture native et mutations d'une même source.

`track_id` est un UUID persistant indépendant des chemins, tags et empreintes. `SourceRevision` est une dataclass immuable contenant `size_bytes: int`, `mtime_ns: int`, `file_id: str | None` et `generation: int`. La génération persistée augmente après chaque mutation connue. Ce token détecte les changements ordinaires ; il ne prouve pas à lui seul que le contenu n'a pas changé.

Métadonnées lues du fichier, résultats calculés et corrections manuelles vivent dans des espaces distincts. Une conversion ne confirme aucune estimation et n'écrase aucun override. Les jobs vérifient la révision avant et après traitement ; les contrôles d'intégrité sensibles utilisent également un SHA-256 calculé en flux.

Préparer un dossier de copies de test hors de la collection originale : MP3, FLAC, WAV, AIFF, Vorbis, Opus, AAC et ALAC en M4A, tags connus/inconnus, pochette et noms accentués. Les médias doivent être autorisés à être utilisés ; seuls de petits fixtures synthétiques ou librement redistribuables vont dans Git.

## Plan de travail et jalons


Le premier jalon ajoute `services/ffmpeg_runtime.py`, `services/media_probe.py` et `domain/conversion.py`. Localiser les binaires inclus dans le paquet, lire leurs versions, inspecter les codecs, encodeurs et muxers, puis effectuer de courtes conversions synthétiques pour confirmer les combinaisons exposées. `ffprobe` produit un JSON interprété avec validation, délais et messages d'erreur traduits en états UI. Reconnaître AAC et ALAC par leur codec réel, même si les deux fichiers portent `.m4a`.

Le deuxième jalon construit `ConversionService` et `persistence/derivations_repository.py`. Un aperçu immuable contient entrées/révisions, paramètres validés, chemins de sortie prévus, estimation d'espace si disponible et politique de tags. L'utilisateur voit cet aperçu avant de démarrer. Revalider espace, collision et révision à l'exécution ; un aperçu n'est pas un verrou sur le système de fichiers.

Le troisième jalon termine le cycle d'un job. Limiter à deux processus de conversion simultanés dans toute l'application. Écrire un fichier temporaire dans le dossier de destination, garder l'extension ou préciser le muxer, vérifier son contenu puis le publier par une opération sans remplacement. Une collision apparue entre aperçu et publication doit échouer proprement. Enregistrer sortie et filiation seulement après publication réussie ; un journal permet de réparer une interruption entre publication et transaction SQLite.

Le quatrième jalon crée `models/conversion_queue_model.py` et `models/conversion_options_model.py`, puis relie `ConversionQueueModel`, `ConversionOptionsModel` et `qml/views/ConvertView.qml`. Afficher format, codec, qualité, fréquence, canaux et profondeur seulement lorsqu'ils s'appliquent ; regrouper les réglages complémentaires sous **Advanced**. Les états persistants communs sont `queued`, `running`, `succeeded`, `failed`, `cancelled` ; **Completed** affiche `succeeded`, **Cancelling** est une indication transitoire du job actif. Un arrêt inattendu devient `failed` avec code `interrupted`, affiché **Interrupted**, sans ajouter un autre enum de jobs.

Le cinquième jalon valide conversion réelle, erreurs et distribution. Les rapports distinguent transfert exact, conversion de représentation et perte de métadonnées. Consigner séparément les profils matériels éventuels : modèle, firmware, support, paramètres et essai de lecture. L'absence de matériel ne bloque pas la conversion générique.

## Étapes concrètes


Depuis la racine du dépôt, inspecter l'état avant toute modification et installer l'environnement verrouillé :

    git status --short
    uv sync --locked

Créer les types `MediaProbe`, `CodecCapabilities`, `ConversionRequest`, `ConversionPreview`, `ConversionResult` et `Derivation` dans `src/mtee/domain/conversion.py`. Les chemins sont des valeurs de domaine Python, jamais des fragments de commande QML. Représenter les erreurs structurées avec un code, un message utilisateur, une cause technique et une possibilité de relance.

Ajouter un adaptateur FFmpeg qui capture le journal avec une taille bornée, interprète la progression et arrête les processus enfants à l'annulation. Utiliser un protocole de progression documenté par la version distribuée. Traiter durée inconnue par une progression indéterminée ; ne jamais déduire un succès uniquement du pourcentage affiché.

Créer `src/mtee/services/media_decode_service.py` avec le contrat PCM décrit plus bas et un test `tests/unit/test_media_decode_contract.py` pour le format, la taille bornée des blocs et l'annulation. Le service coordonne ses lectures avec `FileAccessCoordinator` ; les tests d'intégration de conversion vérifient aussi le décodage réel qui servira aux étapes suivantes.

Créer `src/mtee/services/conversion_service.py`. Imposer une validation conteneur/codec, des limites de paramètres et la destination choisie. Pour une réduction de profondeur PCM, appliquer explicitement un dithering adapté et conserver sa configuration dans la recette. Préserver les niveaux en l'absence d'une transformation explicitement demandée ; ne pas ajouter un filtre de normalisation.

Étendre l'adaptateur de métadonnées de l'étape 05 pour transférer les champs compatibles et les pochettes lorsque la sortie les supporte. Établir un rapport par champ et préserver les valeurs inconnues côté source. Réinspecter la sortie après écriture des tags, en vérifiant codec, conteneur, fréquence, canaux, profondeur pertinente et durée tolérable selon le codec.

Ajouter la migration suivante disponible sous `src/mtee/persistence/migrations/` pour `derivations` et le journal de conversions, après sauvegarde SQLite cohérente et sous transaction. Les UUID et révisions source doivent être stockés, avec paramètres, version FFmpeg, résultat de validation et `time_mapping_status`. Ne pas réutiliser les analyses de la source pour le dérivé.

Créer `tests/unit/test_conversion_contracts.py`, `tests/unit/test_conversion_queue.py` et `tests/integration/test_conversion_ffmpeg.py`. Ajouter `tests/ui/test_convert_view.py` avec moteur de jobs simulé pour les états UI et un scénario avec les binaires réels pour la livraison. Ne pas faire dépendre les tests unitaires de l'installation globale de FFmpeg.

Exécuter les vérifications suivantes lorsque les fichiers existent :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_conversion_contracts.py tests/unit/test_conversion_queue.py tests/unit/test_media_decode_contract.py tests/integration/test_conversion_ffmpeg.py tests/ui/test_convert_view.py
    uv run python -m mtee --data-dir .local/validation/07
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/07-packaged --smoke-test

Lancer aussi le paquet sans `--smoke-test` pour convertir un petit lot sur copies. La présence des binaires FFmpeg, leurs licences et leur résolution hors du checkout doivent être vérifiées dans la distribution autonome.

## Validation et acceptation


Un lot mixte de dix fichiers peut être inspecté et converti avec au plus deux conversions actives. L'utilisateur continue à changer d'onglet et à écouter. Les formats indisponibles et combinaisons incompatibles ne sont pas proposés comme réalisables.

Pour AAC et ALAC en M4A, prouver le codec réel en inspectant les sorties. Tester un chemin contenant espaces, accents, apostrophes et caractères qui auraient une signification dans un shell. Vérifier qu'ils restent de simples chemins et qu'aucune commande parasite n'est exécutée.

Comparer les SHA-256 de toutes les sources avant/après. Tester une sortie déjà présente et une collision concurrente au moment de publier : aucun octet du fichier existant ne change. Injecter manque d'espace, permissions insuffisantes et source modifiée ; aucune sortie partielle n'apparaît comme terminée.

Annuler un job en attente puis un job actif. Aucun processus orphelin ne subsiste et aucun état **Completed** n'est affiché sans fichier vérifié. Redémarrer après interruption simulée ; les travaux incomplets apparaissent comme interrompus, et la relance reconstruit un aperçu avec les chemins réellement disponibles.

Pour WAV PCM, vérifier réduction de profondeur avec dithering explicite et absence de gain non demandé ; pour des codecs avec délai, fixer une tolérance mesurée et documentée avant d'approuver le test. Signaler les métadonnées non transférables dans le rapport UI. Aucun tag source ne doit être réécrit.

Écrire les versions, commandes, résultats réels, captures et limitations dans `docs/validation/07-conversion.md`. Fournir un tableau entrée/paramètres/sortie/contrôle et la preuve d'un essai dans le paquet Windows. Une validation matérielle manquante y est marquée « non réalisée ».

## Reprise et réexécution


Les migrations et la découverte des capacités sont relançables ; le cache de capacités est indexé par la version et l'empreinte du binaire. Une relance ne reprend jamais automatiquement un fichier temporaire non validé comme une sortie correcte.

Chaque tentative possède son identifiant, ses chemins temporaires exacts et un journal persistant. Au redémarrage, réconcilier uniquement les fichiers répertoriés par ce journal. Proposer suppression ciblée ou nouvelle tentative ; ne pas parcourir ni effacer récursivement un dossier utilisateur pour nettoyer les temporaires.

Si la sortie est publiée avant la transaction SQLite, la reprise inspecte ce fichier et reconstitue sa filiation sans reconversion ni doublon. Si le journal n'en prouve pas l'origine, demander une décision dans l'interface après avoir présenté les faits. Réviser les aperçus lorsque source, réglages ou destination changent.

## Interfaces et dépendances


`ConversionService.inspect(source: SourceRef) -> MediaProbe` lit le fichier ; `capabilities() -> CodecCapabilities` décrit la matrice testée ; `preview(request: ConversionRequest) -> ConversionPreview` ne crée aucun fichier ; `submit(preview: ConversionPreview) -> JobId` revalide puis programme ; `retry(job_id, fresh_preview) -> JobId` crée une nouvelle tentative traçable. `JobService.cancel(job_id)` pilote l'annulation commune.

`MediaDecodeService.stream_pcm(source, sample_rate, channels, cancellation)` fournit des blocs bornés pour les étapes suivantes, sans charger tout un morceau en mémoire. Il expose format, fréquence, timeline et erreurs. Le décodage utilise FFmpeg séparé et n'emprunte pas l'état de lecture de mpv.

`Derivation` associe `source_track_id`, `source_revision`, `derived_track_id`, transformation et correspondance temporelle vérifiée ou inconnue. Les repères temporels internes seront des microsecondes entières ; les durées décodées et délais de codec doivent rester explicites. La relation n'autorise aucun transfert automatique de cues.

Les dépendances FFmpeg/ffprobe sont versionnées et distribuées selon leurs licences, avec documentation de provenance. Toute nouvelle dépendance Python justifiée entraîne une mise à jour de `pyproject.toml` et `uv.lock` vérifiée sous Windows. Les opérations de fichiers réutilisent les verrous et notifications de l'étape 06.

## Preuves et livraison Git


Compléter les sections vivantes et `docs/validation/07-conversion.md` avec des observations réelles avant de livrer. Vérifier les modifications étrangères et choisir uniquement les chemins de cette étape ; ne jamais utiliser `git add .`. Adapter la liste ci-dessous aux fichiers réellement créés et à la migration numérotée existante.

    git status --short
    git diff --check
    git add -- src/mtee/domain/conversion.py src/mtee/services/ffmpeg_runtime.py src/mtee/services/media_probe.py src/mtee/services/media_decode_service.py src/mtee/services/conversion_service.py src/mtee/models/conversion_queue_model.py src/mtee/models/conversion_options_model.py src/mtee/qml/views/ConvertView.qml src/mtee/persistence/derivations_repository.py tests/unit/test_conversion_contracts.py tests/unit/test_conversion_queue.py tests/unit/test_media_decode_contract.py tests/integration/test_conversion_ffmpeg.py tests/ui/test_convert_view.py docs/validation/07-conversion.md "Plans d'exécution/07-conversion.md"
    git diff --cached --check
    git diff --cached

Ajouter explicitement les fichiers de migration, d'adaptateur, d'empaquetage et de verrouillage modifiés après examen. Le corps ci-dessous est un modèle à compléter avec les résultats exacts et les limites constatées ; une validation non faite ne doit pas devenir une affirmation positive.

    git fetch origin
    git log --oneline --left-right HEAD...origin/main
    $mteeCommitMessage = @'
    feat(conversion): add verified audio conversion and source lineage

    Changes: add inspected codec options, two-worker conversion queue,
    cancellation, validated outputs without replacement and source lineage.
    Validation: replace with exact tests, corpus cases and Windows package result.
    Limits: replace with metadata losses and hardware profiles not validated.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-07-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Les deux révisions doivent être identiques après le fetch. Si le push échoue, conserver le commit, corriger la cause et relancer sans force ; si le distant a avancé, examiner et intégrer les changements avant de retester ce qui est concerné. Le succès du push est inscrit dans le rapport de livraison externe au commit qu'il décrit, sans hash auto-référentiel dans le fichier committé.

Note de révision — 2026-09-10, Codex : création et harmonisation avec PLANS.md, identités stables, services communs et preuves futures explicités ; aucun développement ou test prétendu réalisé.
