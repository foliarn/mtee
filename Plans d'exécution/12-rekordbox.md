# Étape 12 — Échanger des données avec Rekordbox


Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il développe le jalon I et le §4.10 de `PLAN.md`. Une personne qui découvre MTEE doit pouvoir exécuter ce plan avec le dépôt, les documents nommés et une collection de test. Les chemins décrits comme futurs sont à créer pendant l'exécution, pas à considérer comme déjà livrés.

## Objectif et résultat observable


L'utilisateur peut inspecter un XML Rekordbox, importer explicitement les éléments compatibles dans MTEE, puis exporter une sélection vers un nouveau XML. Un aperçu distingue les éléments transférés, ignorés, ambigus et incompatibles. L'import est en lecture seule vis-à-vis de Rekordbox et des fichiers audio : il peut créer des données internes MTEE après validation de l'aperçu.

Le résultat utilisable est un aller-retour reproductible sur une collection de test : mêmes références musicales, ordre des playlists explicite, absence de doublons inattendus et aucune perte silencieuse. Cues et grilles ne sont activés que pour les cas temporels effectivement validés. Un champ non pris en charge reste visible dans le rapport de limitations et n'est jamais déclaré transféré.

Ce jalon ne manipule pas la base privée de Rekordbox et ne promet pas une synchronisation complète. Il conserve un chemin XML documenté, avec les versions réellement vérifiées de Rekordbox et de son format d'échange.

## Progress


- [x] 2026-09-10 — Plan préparé à partir de `PLAN.md`; aucune intégration réalisée par cette préparation.
- [ ] Vérifier le contrat XML officiel et constituer les fixtures de référence.
- [ ] Développer l'inspection puis l'import sans modification externe.
- [ ] Développer l'aperçu et l'export de sélection avec les limitations visibles.
- [ ] Valider séparément métadonnées, playlists, cues, grilles et fichiers dérivés.
- [ ] Vérifier la distribution Windows, renseigner les preuves, committer et pousser le jalon.

## Surprises & Discoveries


Aucune observation d'exécution n'est encore disponible. Consigner ici, avec un petit XML anonymisé et la version concernée, toute différence entre la documentation officielle, l'export produit par Rekordbox et sa réimportation. Ne pas transformer une hypothèse sur les unités temporelles, les chemins ou les champs en fait établi.

## Decision Log


2026-09-10, Codex — Commencer par le XML et différer l'écriture dans Rekordbox. Motif : `PLAN.md` demande un import en lecture seule, puis un export de sélection; une base propriétaire n'est pas nécessaire à cette trajectoire.

2026-09-10, Codex — Distinguer trois identités : l'UUID `track_id` de MTEE, l'identifiant du document d'échange et le chemin courant du fichier. Motif : un déplacement, un nouveau XML ou un export ne doit pas créer arbitrairement un nouveau morceau.

2026-09-10, Codex — Interdire le transfert automatique des repères d'un dérivé tant que sa correspondance temporelle n'est pas validée. Motif : une conversion et une coupe ne garantissent pas le même domaine temporel.

## Outcomes & Retrospective


À compléter après l'exécution avec les versions testées, la matrice réelle de prise en charge et le résultat de l'aller-retour. Pour l'instant, seul ce plan existe. Indiquer les limitations restantes sans déclarer la compatibilité générale de Rekordbox à partir d'un unique exemple.

## Contexte et prérequis


MTEE est une application locale Python 3.12, PySide6/Qt Quick, SQLite, gérée par uv. `src/mtee/domain` contient les types indépendants de Qt, `services` les traitements, `models` les modèles Qt, `persistence` les migrations et requêtes, et `qml` l'interface en anglais. Aucune lecture XML ni écriture système n'est déclenchée directement depuis QML.

Les étapes 01 à 11 doivent être validées, notamment les métadonnées, déplacements, conversions, playlists et exports de passages. Relire leurs preuves dans `docs/validation`. L'étude Rekordbox amorcée au socle est une source de questions, pas une preuve suffisante de compatibilité.

`track_id` est un UUID interne stable, indépendant du chemin et d'une empreinte de contenu. `SourceRevision` est un type immuable avec `size_bytes: int`, `mtime_ns: int`, `file_id: str | None` et `generation: int` persistée. Un résultat associé à une ancienne révision ne devient pas valable par simple égalité de chemin.

`Derivation(source_track_id, source_revision, derived_track_id, transform, time_mapping)` relie un fichier dérivé à sa source. Les temps sont des microsecondes entières, avec `TimeRange(start_us, end_us)` à borne finale exclusive; `time_mapping` indique une correspondance vérifiée ou inconnue. Le dérivé possède sa propre identité, sa durée et ses analyses. Métadonnées, analyses calculées et confirmations manuelles restent distinctes; un import ne remplace pas silencieusement une correction.

Préparer dans `.local/validation/12` une collection jetable contenant des fichiers originaux, des copies converties, un extrait, deux fichiers homonymes dans des dossiers différents, un fichier déplacé et un fichier manquant. Les données et exports personnels restent locaux et ignorés par Git. Les fixtures committées sont synthétiques ou redistribuables et ne contiennent pas de chemins personnels.

Disposer d'une installation de Rekordbox utilisable pour l'aller-retour manuel. Si elle n'est pas disponible, l'implémentation et les tests internes peuvent progresser, mais la validation croisée reste explicitement ouverte et la fonctionnalité porte un statut expérimental.

## Plan de travail et jalons


### Jalon 12.1 — Fixer le contrat d'échange vérifiable


Consulter au moment de l'exécution la documentation XML officielle de Rekordbox/AlphaTheta et la documentation d'import/export correspondant à la version testée. Archiver dans `docs/validation/12-rekordbox.md` les URLs exactes, dates de consultation, versions, champs retenus, types, unités, règles d'encodage des emplacements et limites constatées. Ne pas déduire le contrat d'un exemple trouvé sur un forum.

Comparer cette documentation à un export minimal réellement généré : deux titres, une playlist ordonnée, un cue et une grille. Ajouter ensuite accents, caractères réservés dans un chemin, emplacement absent, plusieurs playlists et au moins un champ volontairement non pris en charge.

Définir une matrice par catégorie, avec import, export, préservation et limitations. Un champ opaque peut être conservé avec sa provenance pour diagnostic sans être annoncé comme réexportable. Tout XML exporté doit rester dans le sous-ensemble réellement compris.

Le jalon est acquis lorsque chaque mapping activé dispose d'une règle écrite et d'un exemple attendu. Si la documentation manque sur les grilles ou les cues, laisser ces catégories désactivées et documenter l'essai précis nécessaire pour décider.

### Jalon 12.2 — Inspecter et importer sans écrire à l'extérieur


Construire un parseur borné en taille et en nombre d'éléments, sans récupération de ressources externes. Il retourne un document normalisé et un rapport d'anomalies; il ne modifie ni SQLite ni les fichiers. Les erreurs donnent l'élément et la cause lorsque c'est possible.

Résoudre les fichiers par un processus explicite : liens externes déjà connus, emplacements normalisés existants, puis propositions à confirmer. Ne jamais fusionner sur le seul titre ou artiste. Les doublons de contenu et les fichiers homonymes doivent pouvoir rester distincts.

L'aperçu annonce les nouvelles références, rapprochements sûrs, ambiguïtés et données ignorées. La validation utilisateur ouvre une transaction SQLite qui applique uniquement le sous-ensemble accepté. Un import annulé ou interrompu avant la transaction laisse les données inchangées.

Identifier les imports avec un `ImportFingerprint` du document et un journal d'association des identifiants externes. Réimporter le même document avec la même sélection ne duplique pas les pistes ni les playlists. Documenter la politique d'import d'une version modifiée du document, y compris son aperçu de différences.

### Jalon 12.3 — Exporter une sélection contrôlée


Créer `ExportPlan` avant toute écriture : pistes choisies, versions de fichiers utilisées, playlists, éléments temporels compatibles, avertissements et conflits. Montrer cet objet dans la vue `Rekordbox exchange`, avec les textes anglais `Preview import`, `Preview export`, `Unsupported` et `Needs review`.

Attribuer des identifiants d'export déterministes dans un document donné et faire référencer les playlists aux mêmes identifiants. La sélection explicite des sources ou des sorties converties détermine les chemins; aucun basculement silencieux vers une autre version du titre n'est permis.

Écrire un nouveau XML temporaire dans le dossier destination, le reparcourir avec le validateur, puis le finaliser sans écraser une destination existante. Le rapport de transfert doit pouvoir être sauvegardé à côté du XML. L'application ne commande pas automatiquement l'import dans Rekordbox.

### Jalon 12.4 — Préserver les repères seulement lorsque leur temps est valide


Pour un original non modifié, vérifier unités et convention temporelle par des repères audibles. Pour une conversion, tester durée, décalage initial, délai de codec éventuel et repères près du début, du milieu et de la fin. Une durée proche ne suffit pas à prouver l'alignement.

Pour un extrait, traduire seulement les repères appartenant à l'intervalle conservé lorsque la transformation validée le permet; les repères exclus sont listés. Les boucles chevauchant une coupe et les grilles demandent une règle dédiée, prouvée ou désactivée. Un fondu ne crée pas à lui seul un nouveau temps, mais cette propriété doit être portée par la transformation effectivement produite.

Ne pas reconstruire une grille depuis le seul BPM. Le BPM moyen et une grille de battements constituent des données différentes; une grille importée peut comporter des informations que l'analyse MTEE ne produit pas encore.

## Étapes concrètes


Depuis la racine Windows du dépôt, vérifier la branche et installer l'environnement verrouillé. Si une dépendance XML supplémentaire est nécessaire, documenter sa justification, verrouiller sa version et répéter la validation de distribution.

    git status --short
    git branch --show-current
    uv sync --locked

Créer `src/mtee/domain/rekordbox.py` pour les types d'échange, `src/mtee/services/rekordbox_exchange.py` pour le parseur et l'orchestration, `src/mtee/persistence/rekordbox_repository.py` pour les associations, `src/mtee/models/rekordbox_model.py` et `src/mtee/qml/RekordboxExchange.qml` pour l'aperçu. Ajouter une migration numérotée après celles existantes, sans réécrire une migration déjà appliquée.

Ajouter les fixtures dans `tests/fixtures/rekordbox`, les tests purs dans `tests/unit/test_rekordbox_exchange.py`, les transactions et sorties dans `tests/integration/test_rekordbox_exchange.py`, puis le parcours Qt dans `tests/ui/test_rekordbox_exchange.py`. Étendre les tests de transformation temporelle existants au lieu de créer une seconde convention de temps.

Exécuter les contrôles suivants après l'implémentation; corriger les erreurs avant l'essai dans Rekordbox.

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_rekordbox_exchange.py tests/integration/test_rekordbox_exchange.py tests/ui/test_rekordbox_exchange.py
    uv run python -m mtee --data-dir .local/validation/12
    pwsh -File scripts/build_windows.ps1

Exécuter ensuite la même importation et le même export avec la distribution Windows autonome. Charger le XML exporté dans une collection Rekordbox de test isolée, vérifier les catégories une à une et exporter à nouveau pour comparaison sémantique. La différence de mise en forme XML n'est pas une perte de données.

## Validation et acceptation


Les tests unitaires doivent vérifier les chemins avec accents, espaces et caractères réservés, XML malformé, document trop grand, identifiants incohérents, champs inconnus, nombre de pistes divergent et absence de récupération réseau. Une entrée partiellement valide donne un rapport; une incohérence dangereuse bloque l'application concernée.

Les tests d'intégration vérifient l'idempotence, l'ordre des playlists, la transaction annulée, le fichier absent, deux homonymes, le déplacement conservant `track_id`, les conflits d'import et l'absence de modification des sources. Comparer les empreintes des fichiers audio avant et après.

Le parcours manuel vérifie qu'un import vide ou invalide explique son état, que les ambiguïtés sont visibles avant application, que les données manuelles ne disparaissent pas et que l'export indique exactement les versions de fichiers retenues.

Pour chaque catégorie annoncée comme compatible, constater l'aller-retour dans la version de Rekordbox inscrite au rapport. Mesurer les écarts temporels en millisecondes sur les repères du corpus et fixer la tolérance avant de décider de l'activation. Ne pas choisir la tolérance après coup pour faire passer le test.

L'acceptation nécessite un import répété sans doublon inattendu, un export lisible, les catégories compatibles vérifiées séparément, les limitations affichées et un démarrage autonome Windows sans Python de développement. Des cues ou grilles non validés peuvent rester exclus de cette première livraison, avec un périmètre annoncé correspondant.

## Reprise et réexécution


Une nouvelle tentative d'inspection est sans effet externe. Un import validé est une transaction identifiée; au redémarrage, un import non committé est abandonné, un import committé retrouve son rapport. Une reprise ne rejoue pas aveuglément les insertions.

Après un échec d'export, ne supprimer que les temporaires reconnus par l'opération et situés dans son dossier destination. Une sortie déjà finalisée n'est jamais écrasée; proposer un nouveau nom. Conserver le diagnostic de l'échec pour une relance explicite.

Si un fichier change entre aperçu et application, invalider le plan concerné avec `SourceRevision` et recalculer son aperçu. Si la correspondance temporelle devient inconnue, exporter le fichier sans ses repères seulement après une sélection explicite de ce périmètre.

Tester les migrations sur une copie de la base. En cas d'échec, conserver l'ancienne base exploitable selon la stratégie du socle et donner le chemin de sauvegarde. La désinstallation de l'intégration ne doit pas retirer les fichiers audio ni les données de playlists locales.

## Interfaces et dépendances


`RekordboxDocument` représente la version/variante déclarée, les pistes externes, playlists et données temporelles prises en charge. `ExchangeIssue` contient une catégorie, une gravité, une référence externe et un message affichable; les erreurs ne sont pas de simples chaînes impossibles à filtrer.

`RekordboxExchangeService.inspect(path) -> ImportPreview` analyse sans mutation. `apply_import(preview_id, choices) -> ImportResult` revalide les révisions puis écrit seulement dans SQLite. `preview_export(selection, options) -> ExportPlan` est sans écriture; `export(plan_id, destination) -> ExportResult` crée le XML vérifié et son rapport.

`ExternalTrackLink` associe une source d'échange, un identifiant externe et un `track_id`; il n'est pas une preuve d'identité audio universelle. `ImportFingerprint` stabilise le réimport d'un document. L'unicité et les règles de remplacement des associations sont testées en base.

Le service réutilise le dépôt de morceaux, les playlists et les relations `Derivation` du socle. `JobService` pilote les longues inspections et exports annulables; les modèles Qt exposent progression et résultats sur le thread UI. Les sources restent accessibles quand l'intégration échoue. La distribution de contrôle est `dist/MTEE/MTEE.exe`.

## Preuves et livraison Git


Renseigner `docs/validation/12-rekordbox.md` : environnement, documentation officielle consultée, version de Rekordbox, corpus anonymisé, commandes réellement exécutées, résultats, captures d'aperçu, différences d'aller-retour et matrice temporelle. Mettre à jour `Progress`, les décisions et les limites dans ce plan avant le commit. Ne pas inscrire un succès non observé.

Inspecter l'état, puis indexer uniquement les fichiers de cette étape. Adapter les chemins de migration à ceux réellement créés et ajouter individuellement une éventuelle modification de dépendances après lecture du diff. Ne pas inclure `.local`, XML personnels, logs privés ou binaires.

    git status --short
    git diff --check
    git add -- src/mtee/domain/rekordbox.py src/mtee/services/rekordbox_exchange.py src/mtee/persistence/rekordbox_repository.py src/mtee/models/rekordbox_model.py src/mtee/qml/RekordboxExchange.qml tests/fixtures/rekordbox tests/unit/test_rekordbox_exchange.py tests/integration/test_rekordbox_exchange.py tests/ui/test_rekordbox_exchange.py docs/validation/12-rekordbox.md "Plans d'exécution/12-rekordbox.md"
    git diff --cached --check
    git diff --cached

Préparer le message détaillé dans un fichier temporaire, en remplaçant les indications entre chevrons par les observations réelles. Ajouter les autres fichiers d'intégration effectivement modifiés par des `git add --` ciblés avant le commit.

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step12-commit.txt'
    @'
    feat(rekordbox): add reviewed XML import and selection export

    Changes: <categories supported, import identity rules, previews and temporal mapping>
    Validation: <commands, Windows package, Rekordbox version and round-trip results>
    Limits: <unsupported fields, cues/grids or derived files excluded and why>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Le dépôt `origin` doit désigner `https://github.com/foliarn/mtee.git`, configuré à l'étape 00. Exécuter chaque commande après succès de la précédente. Les deux identifiants finaux doivent être identiques; un refus de push exige un diagnostic sans force ni réécriture d'historique. Le hash final est communiqué après le commit, sans tentative de l'inscrire dans son propre contenu.

Note de révision — 2026-09-10, Codex : création et revue du plan ; séparer import local, export XML et qualification temporelle des dérivés, puis vérifier chaque catégorie dans Rekordbox.
