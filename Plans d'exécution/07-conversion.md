# Étape 07 — Conversion audio et fichiers dérivés

Ce document est un ExecPlan vivant rédigé le 2026-09-10. Son exécution suit `PLANS.md` à la racine et réalise `PLAN.md` §4.5, §3 « Onglet Conversion » et le contrôle commun à chaque livraison. Les chemins et commandes ci-dessous décrivent le résultat attendu ; l'avancement et les observations effectivement obtenues sont consignés dans les sections vivantes et `docs/validation/07-conversion.md`.

## Raccord aux retours de recette du 2026-09-25

Exécuter d'abord A du [complément 06b](06b-correctifs-recette.md). Le runtime FFmpeg/ffprobe et les fixtures synthétiques nécessaires ont été réalisés, puis B de 06b a été exécuté sur copies : adaptateurs ID3, Vorbis comments et M4A AAC/ALAC ont désormais leurs essais automatiques de transfert et Undo. La recette UI/manuelle par version reste à faire. Réutiliser ces adaptateurs vérifiés pour les sorties compatibles, en distinguant édition d'une source et transfert vers un dérivé. Le dérivé conserve son UUID propre et ses dates de fichiers réellement observées. Consigner la progression dans les deux plans.

## Objectif et résultat observable


L'utilisateur ajoute des fichiers à l'onglet anglais **Convert**, choisit une combinaison de sortie réellement disponible, voit la destination et les avertissements, puis produit des copies sans modifier ses sources. Il suit la progression de chaque entrée, annule les tâches et relance un échec après correction. La conversion reste utilisable pendant la lecture et la navigation.

La livraison couvre les sorties audio accessibles dans la distribution FFmpeg retenue, après vérification de leurs combinaisons conteneur/codec et paramètres. Elle n'applique aucune normalisation de volume implicite. Un profil nommé d'après une platine n'est disponible qu'après un essai consigné sur ce modèle précis ; des réglages génériques restent utilisables sans cette certification.

## Progress


État au 2026-09-25 : runtime et fixtures réalisés, B vérifié sur copies, puis service de conversion et interface implémentés. Les preuves automatisées sont consignées dans `docs/validation/07-conversion.md`. La recette manuelle sur corpus, l'installation Windows propre et l'audit des dépendances transitives restent ouverts.

- [x] 2026-09-25 — Vérifier les prérequis, les contrats existants et les binaires distribuables; le runtime, le paquet et les fixtures initiales sont consignés dans `docs/validation/07-conversion.md`.
- [x] 2026-09-25 — Raccord B 06b : round-trip des neuf champs et Undo sur les huit combinaisons éditables, audio décodé, tags inconnus et pochettes vérifiés sur copies synthétiques; date ID3v2.3 et AAC/ADTS refusés avec raison.
- [x] Implémenter l'inspection et la matrice de capacités vérifiées par codecs réellement présents.
- [x] Implémenter aperçu, refus des collisions et file limitée à deux conversions.
- [x] Implémenter vérification de sortie, publication sans écrasement, annulation et filiation persistée.
- [x] Relier la file, les options et les rapports de transfert à l'onglet Convert.
- [x] Valider erreurs, annulation, copies synthétiques et paquet Windows; recette interactive encore à réaliser.
- [ ] Renseigner les preuves, créer le commit détaillé et vérifier le push.

2026-09-25 — Tranche FFmpeg et fixtures du raccord 06b effectuée : runtime Windows x64 épinglé, manifesté et ajouté au paquet; neuf fixtures synthétiques locales produites et identifiées par ffprobe. Voir `docs/validation/07-conversion.md`.

2026-09-25 — Service et vue Convert exécutés : sondage des encodeurs/muxeurs présents, aperçu, file à deux workers, options de sortie, transfert contrôlé des champs pris en charge, validation audio, annulation, publication sans remplacement et filiation. Les conversions automatisées couvrent les formats et copies synthétiques indiqués dans le rapport; la recette interactive et sur corpus privé reste non réalisée.

2026-09-25 — B 06b exécuté avant la suite de 07 : les neuf champs MTEE ont été écrits puis annulés dans WAV, MP3, AIFF, FLAC, Vorbis, Opus, M4A/AAC et M4A/ALAC sur copies générées. Les empreintes PCM décodées restent identiques, les valeurs non ciblées et pochettes testées sont vérifiées; 21 tests ciblés passent. AAC/ADTS et Date ID3v2.3 restent explicitement non éditables. La recette UI et les copies manuelles ne sont pas faites.

## Surprises & Discoveries


2026-09-25 — L'archive `lgpl-shared` de BtbN identifie les mêmes AAC/ALAC `.m4a` par leurs codecs réels (`aac` et `alac`); les neuf fixtures audio et l'artwork PNG synthétique sont consignés dans `.local/fixtures/07-metadata/audio/manifest.json`. Cette génération et l'inspection ffprobe ne certifient pas encore les conversions de sortie.

2026-09-25 — PyInstaller copiait aussi les dépendances FFmpeg à la racine lorsqu'on déclarait les PE comme binaires ou données. Le build copie désormais les neuf fichiers runtime hashés après PyInstaller, dans un unique dossier adjacent sous `_internal/mtee/native/ffmpeg/bin`. Le paquet de base runtime fait 412 961 278 octets; après B, le rebuild comprend 1 970 fichiers pour 412 978 343 octets. Une copie externe smoke-test code 0 et a regénéré les neuf fixtures à partir du runtime copié. Cela reste un test sur le même Windows, pas une installation propre.

## Decision Log


2026-09-10 — Codex — FFmpeg et ffprobe sont exécutés hors du processus UI, avec des arguments structurés et `shell=False`. Les sorties sont audio uniquement. Cette frontière maintient la réactivité et empêche les chemins fournis par l'utilisateur d'être interprétés comme commandes.

2026-09-10 — Codex — `ConversionService` est propriétaire des conversions ; `MediaDecodeService` fournira le décodage PCM commun aux étapes 08, 09 et 11. Ces deux services utilisent `JobService` et les mêmes contrôles de révision de source.

2026-09-10 — Codex — Un dérivé devient un morceau distinct identifié par son propre UUID. La filiation et la correspondance temporelle sont persistées séparément, car une sortie encodée n'a pas nécessairement la même origine temporelle que son entrée.

2026-09-25 — Codex — Épingler le build BtbN Windows x64 `lgpl-shared` du 2026-09-24, FFmpeg `n9.0.2-3-ga5923073bf-20260924`. Motif : artefact daté/hashé, version de FFmpeg issue d'une branche stable, codecs audio des formats attendus, et variante annoncée sans dépendances GPL-only. La provenance et les empreintes sont dans `resources/native/ffmpeg/manifest.json`; l'audit de redistribution transitive reste ouvert.

## Outcomes & Retrospective


Les conversions utilisent huit profils audio rapportés par le runtime et ont été exercées sur les fixtures synthétiques; l'aperçu bloque une destination existante, une annulation active nettoie le temporaire, et la sortie est sondée avant publication sans remplacement. Le journal persiste les tentatives et les dérivations. Les rapports vérifient les champs écrits par les adaptateurs; pochettes et champs sans adaptateur sont déclarés non transférés/non vérifiés. Les tests ciblés passent; run complet et rebuild final du paquet nécessaires avant clôture. Le crash natif intermittent SEH de libmpv demeure une hypothèse non attribuée. Aucun geste manuel de recette Convert ni essai sur corpus utilisateur n'est revendiqué. Le paquet est lancé depuis une copie hors checkout sur le même Windows; installation propre et audit transitif restent ouverts.

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
