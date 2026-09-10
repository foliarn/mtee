# Étape 11 — Extraction de passages et édition audio légère

ExecPlan vivant rédigé le 2026-09-10. Il applique `PLANS.md` à la racine, réalise `PLAN.md` §4.9 et réutilise les étapes 07 à 10. Les exports, tests et livraisons Git ci-dessous sont futurs ; les originaux ne sont jamais des cibles d'export ou de test d'écriture.

## Objectif et résultat observable


L'utilisateur sélectionne un passage dans la waveform, ajuste début et fin, ajoute un fondu d'entrée ou de sortie, écoute un aperçu puis exporte une copie. Il retrouve cette copie dans MTEE avec sa propre durée, son UUID et la relation vers la source. Les modifications de la recette sont annulables avant export ; aucun geste dans l'éditeur ne réécrit l'original.

Le périmètre se limite à une source et un passage contigu avec fondus. Le multipiste, les collages de passages multiples, les effets arbitraires et le mixage en temps réel restent hors de cette livraison. Les analyses d'une version source ne sont pas présentées comme celles du nouveau fichier.

## Progress


État au 2026-09-10 : plan préparé, aucun jalon de développement exécuté.

- [ ] Vérifier waveform, timeline, conversion, coordination des fichiers et filiation.
- [ ] Définir la recette, ses invariants et l'édition annulable des bornes/fondus.
- [ ] Implémenter aperçu audio et restauration de la session de lecture.
- [ ] Implémenter export vérifié, sans écrasement, avec relation temporelle.
- [ ] Vérifier précision, indépendance des analyses et annulation/reprise.
- [ ] Tester la distribution Windows et renseigner les preuves.
- [ ] Créer un commit détaillé et confirmer le push sur origin/main.

## Surprises & Discoveries


Aucune mesure d'extraction n'a été effectuée. Consigner ici les différences de bornes entre codecs, délais d'encodage, variations d'enveloppe de fondu et contraintes de fichiers verrouillés, avec fixture, recette et mesure décodée.

## Decision Log


2026-09-10 — Codex — Une `EditRecipe` décrit source/révision, plage et fondus. Elle ne contient pas d'instruction de remplacement du fichier source. Les copies finales passent par les garanties de publication de `ConversionService`.

2026-09-10 — Codex — `TimeRange` existe dans `src/mtee/domain/time.py` depuis le socle, en microsecondes et fin exclusive. L'éditeur le réutilise ; il calcule les bornes effectives en échantillons au moment du rendu et expose leur arrondi dans les preuves.

2026-09-10 — Codex — Le premier rendu précis décode puis coupe le PCM, applique des fondus linéaires d'amplitude et encode si demandé. La copie de paquets compressés n'est pas le mode initial, car ses frontières ne garantissent pas les bornes choisies.

## Outcomes & Retrospective


Non exécuté. Après livraison, décrire les formats validés, précision des bornes, comportement de l'aperçu, conservation des sources et limites des correspondances temporelles. Une sortie compressée aux délais non vérifiés reste explicitement marquée comme telle.

## Contexte et prérequis


L'étape 08 fournit waveform, zoom et `TimeRange`. `PlayerService` est l'unique lecteur utilisé par toutes les vues. L'étape 07 fournit `ConversionService`, `MediaDecodeService`, l'inspection FFmpeg/ffprobe et le journal de dérivés. Les étapes 09/10 distinguent résultats calculés, corrections manuelles et organisation locale.

`track_id` est un UUID interne stable indépendant du chemin ou du hash. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` est immuable ; `file_id` est facultatif et la génération persistée augmente après les mutations connues. Le token détecte les modifications usuelles ; les contrôles d'intégrité de l'export utilisent également un SHA-256 en flux lorsque nécessaire.

`FileAccessCoordinator` coordonne les accès entre décodeur, lecteur et mutations. `JobService` travaille hors UI avec états `queued`, `running`, `succeeded`, `failed`, `cancelled` ; un arrêt de l'application est enregistré comme `failed` avec le code `interrupted`, présenté **Interrupted** à l'utilisateur. Une relance crée une tentative traçable.

`Derivation` conserve source UUID/révision, UUID dérivé, transformation et correspondance temporelle vérifiée ou inconnue. Ce lien n'autorise pas à réutiliser automatiquement une grille ou des cues Rekordbox. L'étape 12 pourra exploiter une relation de découpe suffisamment vérifiée et ses limites explicites.

Utiliser des copies de corpus : PCM avec impulsions proches des bornes, tonalité constante pour les fondus, silence, morceau réel, MP3 VBR, AAC/ALAC en M4A et fichier long. Les originaux de collection, les bases locales et les exports privés restent hors Git.

## Plan de travail et jalons


Le premier jalon crée `domain/audio_edit.py` et les invariants d'`EditRecipe`. La plage respecte `0 <= start_us < end_us <= duration_us`. Les fondus sont positifs ou nuls, exprimés sur la timeline de sortie, et leur somme ne dépasse pas sa durée dans cette première version. Toute correction automatique de borne doit être montrée ; préférer une erreur claire à une modification silencieuse de la sélection.

Le deuxième jalon ajoute `models/audio_edit_model.py`, `qml/components/AudioEditPanel.qml` et l'intégration dans `ListeningView.qml`. Afficher début, fin, durée, fondus et destination avec saisie numérique et marqueurs accessibles au clavier. L'historique undo/redo porte sur la recette ; changer la sélection du navigateur ne change pas la source d'une recette déjà ouverte sans action explicite.

Le troisième jalon crée `services/audio_edit_service.py`. Compiler la recette en traitement audio validé avec décodage, coupe par indices d'échantillons, remise à zéro des timestamps et fondus. À fréquence native, convertir le début avec plancher et la fin avec plafond, puis borner au nombre d'échantillons réellement décodés ; enregistrer ces bornes effectives dans le résultat.

Le quatrième jalon produit un aperçu temporaire dans le répertoire de données applicatif. Un clic **Preview** sauvegarde l'état de `PlayerService`, lit cet aperçu avec le même moteur et affiche clairement la session d'aperçu. **Back to track** restaure morceau, position, volume et file si l'utilisateur n'a pas entre-temps lancé explicitement une autre lecture ; ce nouveau choix prévaut.

Le cinquième jalon étend `ConversionService` pour recevoir un rendu audio structuré, sans accepter de chaîne de filtre libre depuis QML. L'aperçu d'export décrit source/révision, bornes, fondus, format, nom, dossier, transfert de tags et précision attendue. L'export final revalide tout, écrit un temporaire, inspecte et publie sans remplacement.

Le dernier jalon ajoute la copie au catalogue après succès, enregistre la recette et la relation de temps dans `persistence/audio_edits_repository.py`, puis propose waveform et analyse propres au dérivé. Aucun BPM, résultat de tonalité ou override confirmé n'est copié comme calcul du dérivé. Le transfert éventuel des valeurs écrites dans les tags suit un choix affiché séparément.

## Étapes concrètes


Depuis la racine, inspecter l'état et préparer l'environnement :

    git status --short
    uv sync --locked

Créer `EditRecipe`, `FadeSpec`, `EditPreview` et `EditResult` dans `src/mtee/domain/audio_edit.py`. Réutiliser `TimeRange` du socle ; ajouter ses conversions d'échantillons au fichier existant `src/mtee/domain/time.py` seulement si elles manquent. L'aperçu conserve un hash de recette et une révision source pour détecter une modification avant export.

Créer `src/mtee/services/audio_edit_service.py`. Définir une compilation déterministe vers le traitement de `ConversionService`, sans shell. Les paramètres de coupe/fondu sont des nombres validés, les chemins sont passés comme arguments séparés. Rendre le PCM à fréquence/canaux source avant conversion de sortie, pour maintenir une correspondance de bornes explicite.

Étendre la frontière de conversion dans `src/mtee/domain/conversion.py` et `services/conversion_service.py` avec un `AudioRenderSpec` typé contenant une recette de coupe/fondus autorisée. Réutiliser collision, métadonnées, dither si réduction PCM, progression, limite globale de deux conversions et journal de publication. Ne pas créer une seconde implémentation d'export plus permissive.

Ajouter la prochaine migration disponible pour les recettes persistées et la relation d'édition dans `src/mtee/persistence/migrations/`, après sauvegarde SQLite cohérente. Un brouillon de recette peut être restauré après redémarrage, avec une validation de sa révision source ; il n'est pas une preuve qu'un fichier a été exporté.

Pour l'aperçu, mettre en cache les rendus par UUID/révision/recette et invalider le résultat si l'une de ces valeurs change. Limiter l'espace de cache et les rendus en attente. Avant un export long, permettre l'écoute des bornes et fondus concernés ; ne pas bloquer le thread UI pendant leur génération.

Créer `src/mtee/models/audio_edit_model.py` et `qml/components/AudioEditPanel.qml`. Afficher **Preview**, **Export copy**, **Rendering**, **Cancelled** et **Could not export**. Une erreur conserve la recette et les paramètres ; **Retry** refait l'aperçu des effets et des chemins au lieu de réutiliser un nom devenu occupé.

Créer `tests/unit/test_audio_edit_recipe.py`, `tests/unit/test_audio_edit_timing.py`, `tests/integration/test_audio_edit_export.py`, `tests/integration/test_audio_edit_recovery.py` et `tests/ui/test_audio_edit_panel.py`. Les tests de PCM comparent des échantillons/positions attendus ; les tests de filiation vérifient UUID, durée et absence d'analyses héritées.

Exécuter les contrôles après implémentation :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_audio_edit_recipe.py tests/unit/test_audio_edit_timing.py tests/integration/test_audio_edit_export.py tests/integration/test_audio_edit_recovery.py tests/ui/test_audio_edit_panel.py
    uv run python -m mtee --data-dir .local/validation/11
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/11-packaged --smoke-test

Ouvrir le paquet sans `--smoke-test`, rendre un aperçu, exporter WAV/FLAC et une sortie compressée, puis relire les copies dans MTEE. Effectuer cet essai sur Windows propre sans Python ni binaires natifs récupérés par hasard depuis le `PATH` de développement.

## Validation et acceptation


Sur PCM à fréquence inchangée, une extraction retrouve exactement la tranche d'échantillons définie par la règle d'arrondi annoncée. Sa durée décodée égale le nombre d'échantillons retenus divisé par la fréquence ; l'écart aux bornes demandées reste inférieur à un échantillon par borne, sauf borne limitée à la durée réelle et explicitement signalée.

Placer des impulsions avant, sur et après les bornes. Le segment ne contient pas les échantillons exclus ; une sélection vide, inversée ou hors durée empêche l'export avec une erreur compréhensible. Tester les limites d'un échantillon, les extraits très courts et les très longs fichiers.

Sur signal constant, vérifier l'enveloppe linéaire des fondus, leur début/fin et l'absence de gain dépassant celui demandé. Vérifier durée nulle, fondu plus long que l'extrait et chevauchement interdit : l'interface conserve la saisie et explique la contrainte. Les mêmes paramètres donnent le même rendu PCM à versions constantes.

Décoder les exports compressés pour mesurer durée, délai et éventuel padding. Consigner par codec la précision obtenue et la tolérance avant d'accepter la sortie ; si la correspondance temporelle ne peut pas être vérifiée, la marquer inconnue. Ne pas déduire une précision à l'échantillon du seul champ duration fourni par le conteneur.

Comparer les SHA-256 des sources avant/après aperçu et export. Tester nom déjà présent, collision concurrente, dossier inaccessible, manque d'espace et modification extérieure pendant le rendu. Aucun original ni fichier préexistant ne change, et aucun temporaire incomplet n'apparaît comme une sortie réussie.

Annuler l'aperçu et l'export, puis simuler une fermeture après publication mais avant transaction de filiation. La reprise identifie uniquement ses propres fichiers et réconcilie le journal sans doublon. Un job interrompu a l'état persistant `failed` et le code `interrupted`, avec une relance explicite disponible.

Après export, le dérivé possède un UUID distinct, sa durée propre et aucune analyse de source active par héritage. Lancer sa propre analyse et une réanalyse de l'original : résultats et corrections manuelles restent indépendants. La playlist source garde ses références et l'ajout du dérivé est explicite.

L'aperçu utilise le lecteur commun. Vérifier restauration de session, choix volontaire d'un autre morceau pendant l'aperçu, raccourcis avec champs saisis, changement de vue et disposition restaurée. Aucun résultat de rendu tardif ne remplace la recette ou la source courante.

Écrire `docs/validation/11-edition-audio.md` avec recettes, bornes demandées/effectives, mesures, hashes, captures et parcours dans le paquet. Distinguer réussite d'export, précision temporelle vérifiée et capacité future à transporter des cues.

## Reprise et réexécution


L'historique de recette et son brouillon sont relisibles après redémarrage, sous réserve de revalider la source. Si celle-ci a changé, montrer les différences et demander une relecture avant de recalculer les bornes. Une ancienne recette ne s'applique pas silencieusement à une autre version audio.

Un aperçu complet est réutilisable uniquement à UUID/révision/recette/versions constants. Une annulation tue les processus appartenant au job et retire seulement ses temporaires connus. Vérifier les chemins absolus de cache ; ne jamais nettoyer récursivement un dossier de sorties utilisateur.

L'export suit le journal déjà introduit par la conversion. Si le fichier final existe et que sa provenance est prouvée, finaliser son enregistrement sans réexporter ; sinon conserver le conflit visible. La relance crée un nouveau nom sûr ou échoue sur collision, et n'utilise jamais une option de remplacement automatique.

## Interfaces et dépendances


`AudioEditService.preview_recipe(recipe, output_options) -> EditPreview` calcule effets, bornes effectives et erreurs sans produire de sortie finale. `render_preview(preview) -> JobId` crée un audio temporaire ; `export_copy(preview) -> JobId` revalide et délègue à la conversion. `JobService.cancel(job_id)` est commun aux trois traitements.

`EditRecipe` contient UUID/révision source, `TimeRange`, deux `FadeSpec` et version de recette. `EditResult` contient UUID dérivé, chemin, durée décodée, bornes effectives, paramètres appliqués, contrôle de sortie et relation temporelle. La relation de découpe vérifiée indique `source_time = derived_time + effective_start` sur le segment retenu, avec ajustement documenté des délais de codec si nécessaire.

`PlayerService` reçoit une session d'aperçu avec sauvegarde de son état et une restauration conditionnelle à l'absence de choix de lecture plus récent. `AudioEditModel` expose la recette et ses erreurs via signaux Qt ; il n'exécute ni FFmpeg ni opération de fichiers.

Réutiliser les binaires distribués, `MediaDecodeService`, `ConversionService`, `FileAccessCoordinator` et les services d'analyse. Aucune bibliothèque de station audionumérique ni moteur multipiste n'est ajoutée. La licence et les ressources natives continuent à être contrôlées par `scripts/build_windows.ps1`.

## Preuves et livraison Git


Mettre à jour le plan et le rapport avec les preuves réelles. Inspecter les fichiers partagés avant leur ajout et indexer seulement les modifications de cette étape ; ajouter individuellement la migration choisie et les fixtures redistribuables créées.

    git status --short
    git diff --check
    git add -- src/mtee/domain/audio_edit.py src/mtee/domain/time.py src/mtee/domain/conversion.py src/mtee/services/audio_edit_service.py src/mtee/services/conversion_service.py src/mtee/persistence/audio_edits_repository.py src/mtee/models/audio_edit_model.py src/mtee/qml/components/AudioEditPanel.qml src/mtee/qml/views/ListeningView.qml tests/unit/test_audio_edit_recipe.py tests/unit/test_audio_edit_timing.py tests/integration/test_audio_edit_export.py tests/integration/test_audio_edit_recovery.py tests/ui/test_audio_edit_panel.py docs/validation/11-edition-audio.md "Plans d'exécution/11-edition-audio.md"
    git diff --cached --check
    git diff --cached

Compléter le message avec les mesures et limites constatées ; examiner le distant avant de publier :

    git fetch origin
    git log --oneline --left-right HEAD...origin/main
    $mteeCommitMessage = @'
    feat(audio-edit): export timed selections and fades as verified copies

    Changes: add reversible edit recipes, shared-player previews, precise PCM
    trimming and safe derived-file exports with independent analyses.
    Validation: replace with exact boundary, recovery and Windows package results.
    Limits: replace with measured codec delay and unsupported editing operations.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-11-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Si le distant a avancé, résoudre la divergence sans force et revalider les parties touchées. Comparer les révisions après fetch pour confirmer le push, puis rapporter sa preuve dans la livraison. Ne pas écrire le hash du commit dans son propre contenu ni cocher la publication avant sa vérification.

Note de révision — 2026-09-10, Codex : création du plan, arrondi temporel et limites d'encodage explicités, réutilisation des contrats de conversion/lecture ; aucune implémentation ou validation prétendue réalisée.
