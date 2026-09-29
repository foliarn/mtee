# 32 — Tri des captures vers les dossiers : manuel puis règles

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il range les morceaux de l'Inbox livrée au [plan 31](31-soundcloud-inbox-mtee.md) dans les dossiers de la collection. Il comprend deux livraisons distinctes : le tri manuel, puis les règles de tri automatique. Chacune a ses prérequis.

**État au 2026-09-29 : abandonné par l'utilisateur.** Ni tri manuel, ni règles de tri ne seront développés dans cette série. Le document est conservé comme trace ; aucune de ses étapes ne doit être exécutée sans une nouvelle demande explicite.

## Objectif et résultat observable

**Tri manuel.** Depuis l'Inbox, l'utilisateur sélectionne un ou plusieurs morceaux, choisit `Move to folder…`, voit un aperçu (fichier, destination, collision éventuelle) et confirme. Les fichiers quittent l'Inbox pour le dossier choisi, conservent leur `track_id`, leur provenance et leur place dans la file de lecture ; la capture passe à `triaged`. `Undo` remet le dernier lot à sa place tant que les fichiers n'ont pas changé.

**Règles.** L'utilisateur crée des règles `Filter` ordonnées : « si la condition est vraie, proposer ce dossier ». Chaque morceau de l'Inbox affiche la destination proposée et la règle qui l'a produite. `Apply suggestions` déplace, après le même aperçu, les morceaux sélectionnés dont la suggestion est acceptée. Une règle peut, sur option explicite, s'appliquer automatiquement à l'arrivée ; elle reste alors journalisée et annulable.

## Contexte et prérequis

Tri manuel : plan 31 livré ; réponse positive à la question 29.3-5 (réintroduire un déplacement limité à l'Inbox), consignée dans `docs/decisions/29-soundcloud-capture.md`. Sans cet accord, ce plan s'arrête à la maquette.

Règles : tri manuel livré ; critères retenus à la question 29.3-6. Les critères de provenance (artiste SoundCloud, voie, passerelle, genre affiché sur la page) et de tags de fichier existants (Genre, BPM, Key, Artist) sont possibles dès le tri manuel livré. Les critères fondés sur des tags personnalisés ou des filtres enregistrés attendent l'accord de vocabulaire et le moteur de critères de l'étape 10 ; ce plan réutilisera alors ce moteur au lieu d'en créer un second.

Lire `Plans d'exécution/17-stabilisation-lot-01-retraits.md` (retrait de Move), `06-fichiers.md` (contrat historique des déplacements), `21-stabilisation-lot-05-corbeille.md`, puis `src/mtee/persistence/library_repository.py` (`move_location_in_transaction`, `registered_roots_for`, `path_owner`), `005_file_operations.sql`, `006_file_operation_phases.sql`, `src/mtee/services/file_access.py` et leurs tests. Vérifier si ces primitives sont encore couvertes et correctes avant de les réutiliser ; les adapter plutôt que réintroduire l'ancien code d'interface retiré.

## Plan de travail et jalons

### Jalon 32.1 — Maquettes

États : sélection dans l'Inbox et commande `Move to folder…`, sélecteur de dossier limité aux racines de collection, aperçu avec collision, résultat partiel, `Undo`, éditeur de règle, liste ordonnée des règles, colonne `Suggested folder` avec la règle source. Revue utilisateur consignée avant le code QML.

### Jalon 32.2 — Déplacement sûr depuis l'Inbox

Créer `src/mtee/services/inbox_triage.py`. Pour chaque fichier : acquérir le bail `FileAccessCoordinator` (le morceau en lecture est libéré ou signalé selon la règle du lecteur), vérifier `SourceRevision`, refuser toute collision (jamais d'écrasement ; proposer `Keep both` avec suffixe ou `Skip`), déplacer sur le même volume par renommage atomique, ou entre volumes par copie vérifiée (taille puis SHA-256 en flux) suivie de la suppression de l'original seulement après succès, puis mettre à jour le catalogue dans la même transaction via `move_location_in_transaction`. Le journal d'opérations existant (migrations 005/006) enregistre chaque phase pour la reprise et `Undo`.

Le lot s'exécute comme travail `JobService` annulable, avec résultat par fichier. Seuls les morceaux de l'Inbox sont déplaçables par cette commande ; elle ne réactive pas Move dans l'Explorer.

Tests : `tests/integration/test_inbox_triage.py` sur copies (même volume, collision, fichier modifié entre aperçu et application, fichier verrouillé, annulation au milieu d'un lot, `Undo`, destination disparue) ; test marqué `windows_file_ops` pour la sémantique Windows.

### Jalon 32.3 — Règles de tri

Créer `src/mtee/domain/triage_rules.py` : une règle est un arbre typé et versionné de conditions (`field`, `operator`, `value`) combinées par `all`/`any`, avec une destination (racine + chemin relatif) et un ordre. Champs initiaux selon la décision 29.3-6, par exemple `capture.artist_display`, `capture.route_kind`, `capture.tags_displayed`, `file.genre`, `file.bpm`, `file.key`. Opérateurs : égalité insensible à la casse et aux accents, contient, intervalle numérique, appartenance. Jamais de SQL ni d'expression libre venant de l'interface (même principe que l'étape 10).

Évaluation : la première règle vraie donne la suggestion ; les autres correspondances sont montrées en info. Une destination disparue rend la règle `Invalid` sans la supprimer. Migration suivante pour `triage_rules` ; application automatique désactivée par défaut, activable par règle.

Tests : `tests/unit/test_triage_rules.py` (accents, casse, champs absents, BPM décimal, Key en notation Camelot et classique si les deux existent dans les tags, ordre, règle invalide), `tests/ui/test_triage_rules_editor.py`.

### Jalon 32.4 — Recette et distribution

    uv sync --locked
    uv run python -m compileall -q src/mtee
    uv run pytest tests/integration/test_inbox_triage.py tests/unit/test_triage_rules.py tests/ui/test_triage_rules_editor.py
    uv run python -m mtee --data-dir .local/validation/32-live
    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1 -DataDir .local/validation/32-packaged

Parcours manuel sur une collection de recette copiée : tri manuel de captures réelles, collision, morceau en cours de lecture, `Undo`, trois règles concurrentes, application des suggestions, règle automatique activée puis nouvelle capture. Consigner dans `docs/validation/32-soundcloud-tri.md`.

## Validation et acceptation

Tri manuel accepté lorsqu'aucun écrasement n'est possible, que chaque échec est visible et reprenable, que l'identité et la provenance survivent au déplacement et au redémarrage, que `Undo` fonctionne sur fichiers inchangés et que le paquet Windows passe. Règles acceptées lorsqu'elles donnent des suggestions explicables, sans déplacement non confirmé hors des règles explicitement automatiques.

## Reprise et réexécution

Un lot interrompu reprend à partir du journal : chaque fichier est soit à l'origine, soit à destination avec catalogue à jour, soit marqué `needs review` si une copie inter-volumes est incomplète (la source est alors conservée). Une règle modifiée ne réapplique rien aux morceaux déjà triés.

## Interfaces et dépendances

`InboxTriageService.preview(track_ids, destination) -> TriagePreview`, `.apply(preview_id, choices, context) -> TriageResult`, `.undo(operation_id)`. `TriageRuleEngine.suggest(track) -> Suggestion | None`. Le futur moteur de critères de l'étape 10 remplacera l'évaluateur de conditions si ses types couvrent ces champs ; documenter alors la migration des règles.

## Preuves et livraison Git

Deux commits au moins, un par livraison (tri manuel, règles), chacun poussé selon `PLANS.md`.

    git status --short
    git diff --check
    git add -- src/mtee/services/inbox_triage.py src/mtee/domain/triage_rules.py src/mtee/persistence src/mtee/models src/mtee/qml tests/integration/test_inbox_triage.py tests/unit/test_triage_rules.py tests/ui/test_triage_rules_editor.py docs/validation/32-soundcloud-tri.md "Plans d'exécution/32-soundcloud-tri-dossiers.md"
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step32-commit.txt'
    @'
    feat(inbox): move captured tracks to collection folders

    Changes: <preview, collision policy, journaled move, undo | rules and suggestions>
    Validation: <tests on copies, Windows file ops, manual run, packaged smoke test>
    Limits: <cross-volume behaviour, rule fields pending step 10>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Restreindre `git add` aux fichiers réellement modifiés dans `persistence`, `models` et `qml`.

## Progress

- [x] 2026-09-29 — Plan préparé ; attend 31 et les décisions 29.3-5 et 29.3-6.
- [x] 2026-09-29 — Abandonné par l'utilisateur (réponses 29.3-5 et 29.3-6).
- [ ] Maquettes validées (32.1).
- [ ] Déplacement sûr depuis l'Inbox livré (32.2).
- [ ] Règles et suggestions livrées (32.3).
- [ ] Recette, distribution, rapports, commits et push (32.4).

## Surprises & Discoveries

Non observé à ce stade.

## Decision Log

2026-09-29 — Claude — Déplacement réintroduit uniquement depuis l'Inbox, sous réserve d'accord. Motif : répondre au besoin de tri sans rouvrir les opérations fichiers générales retirées au lot 17.

2026-09-29 — Claude — Règles proposant une destination, application automatique désactivée par défaut. Motif : une règle erronée ne doit pas disperser la collection ; l'aperçu reste la voie ordinaire.

2026-09-29 — Utilisateur — Abandonner le tri vers les dossiers ; pas de réintroduction du déplacement.

## Outcomes & Retrospective

Non exécuté : plan abandonné le 2026-09-29.

Note de révision — 2026-09-29, Claude : création du plan.
