# Étape 10 — Vocabulaire des tags, recherche et playlists

ExecPlan vivant rédigé le 2026-09-10. Appliquer `PLANS.md` à la racine et `PLAN.md` §4.8 après les résultats réels de l'étape 09. Le vocabulaire n'est pas défini dans ce plan : sa revue utilisateur est un jalon distinct à préparer et à enregistrer avant l'implémentation fonctionnelle de cette étape.

## Raccord aux retours de recette du 2026-09-25

Intégrer C du [complément 06b](06b-correctifs-recette.md) après la revue explicite prévue ci-dessous : champs de recherche `file.created_at` et `file.modified_at`, intervalles de dates avec fuseau et valeurs inconnues, filtres enregistrés et recette de persistance. Leurs colonnes et leur collecte sont livrées en A de 06b ; le défaut de choix des colonnes appartient aussi à A et n'attend pas le moteur de recherche. Réutiliser ce catalogue de champs sans confondre dates physiques, date de tag et dates d'analyse. Les raccourcis de copie/déplacement de fichiers ne doivent pas transformer un réordonnancement de playlist en déplacement sur disque. Si la session nocturne atteint cette étape sans accord de vocabulaire, produire le dossier de revue complet puis laisser une reprise explicite avant l'implémentation fonctionnelle. Cette note ne vaut ni accord de vocabulaire ni validation des correctifs.

## Objectif et résultat observable


L'utilisateur retrouve des morceaux par combinaison de métadonnées, analyses et tags dont le vocabulaire a été validé avec lui. Il enregistre des filtres, ouvre des vues intelligentes recalculées depuis ces critères et construit des playlists manuelles qu'il peut réordonner. Un déplacement de fichier effectué dans MTEE conserve ses références dans toutes ces vues.

Les tags personnalisés organisent la bibliothèque locale. Ils sont distincts des tags écrits dans les fichiers et des résultats calculés. La recherche indique quelle provenance elle interroge ; elle ne traite pas automatiquement une estimation incertaine comme une valeur confirmée.

## Progress


État au 2026-09-25 : préparation de la revue achevée dans `docs/decisions/10-tags-review.md` et `docs/validation/10-tags-review.md`. Aucun accord explicite sur le vocabulaire n'est consigné; le développement fonctionnel et le jalon C n'ont pas commencé.

- [x] Examiner les résultats réels de l'étape 09 et préparer le dossier de revue.
- [ ] Obtenir et consigner la validation utilisateur du vocabulaire proposé.
- [ ] Créer les tags locaux et les critères de recherche typés validés.
- [ ] Ajouter filtres enregistrés et vues intelligentes.
- [ ] Ajouter playlists manuelles et réordonnancement transactionnel.
- [ ] Vérifier références, recherche, interface et paquet Windows.
- [ ] Renseigner les preuves, créer le commit détaillé et confirmer le push.

## Surprises & Discoveries


La validation 09 ne contient que des analyses synthétiques contrôlées : tempo 117,4538 BPM pour des impulsions à 120 BPM, do majeur sur un accord construit, loudness −18 LUFS, deux silences totalisant 2 s. Ces mesures donnent des exemples de champs calculés et d'états de provenance; elles ne témoignent d'aucune utilité sur une collection musicale réelle et ne justifient aucune catégorie sémantique. Le dossier décrit les limites et questions à trancher avant tout vocabulaire.

## Decision Log


2026-09-10 — Codex — La revue prévue par `PLAN.md` §4.8 précède le vocabulaire implémenté. Préparer résultats, exemples de recherches et propositions motivées avant de demander l'avis utilisateur ; une absence de réponse ne vaut pas acceptation.

2026-09-10 — Codex — Une requête enregistrée est un arbre de critères typés et versionné, jamais du SQL fourni par l'interface. Les vues intelligentes réutilisent le moteur de recherche et ne possèdent pas leur propre logique de filtrage.

2026-09-10 — Codex — Les playlists stockent des UUID de morceaux, un identifiant par occurrence et un ordre explicite. Deux occurrences volontaires d'un morceau peuvent être conservées ; le déplacement d'un fichier ne modifie pas l'identité du morceau.

2026-09-25 — Codex — Aucun accord utilisateur daté sur le vocabulaire de l'étape 10 n'apparaît dans les plans ni dans les décisions versionnées. Le dossier de revue est préparé à partir des seules sorties vérifiées de la fixture 09. Les fonctionnalités de 10 et C restent en attente; le silence de cette session ne vaut pas accord.

## Outcomes & Retrospective


La revue et les fonctionnalités ne sont pas exécutées : aucun accord explicite n'est consigné. La revue est préparée avec quatre exemples de critères, les limites de la fixture synthétique et les questions ouvertes. Reste à recueillir la réponse, définir et versionner le vocabulaire accepté, puis reprendre C et le développement de 10 selon l'ordre du plan.

## Contexte et prérequis


L'étape 09 a produit des analyses versionnées et des corrections manuelles persistantes. Relire `docs/validation/09-analyse-sans-ml.md`, consulter les résultats dans l'application et vérifier que le corpus reflète l'usage réel. Un jeu de valeurs fictives suffit aux tests techniques, mais pas à la revue du vocabulaire.

Les étapes 03 et 06 fournissent un catalogue, les vues Table/Artwork et les notifications de déplacement. `track_id` est un UUID stable indépendant des chemins ; chaque copie dérivée peut avoir son propre UUID. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` suit les modifications usuelles, avec `file_id` facultatif et génération persistée ; elle n'est ni un identifiant musical ni une garantie cryptographique.

`PlayerService` reste l'unique lecteur. Au lancement d'une lecture depuis une recherche ou playlist, sa file reçoit un instantané explicite de l'ordre affiché ; une recherche réévaluée ou une playlist réordonnée ne remplace pas silencieusement cette file.

Les espaces de données restent distincts : métadonnées du fichier, résultats d'analyse, confirmations manuelles, tags locaux et playlists. `AnalysisService` permet de lire chaque provenance séparément. `JobService` exécute les requêtes longues hors du thread graphique, avec annulation et rejet des réponses périmées.

Les chemins proposés ci-dessous sont relatifs à la racine. Réutiliser les contrats existants si leurs fichiers ont changé et noter la correspondance. Les schémas propres à cette étape sont créés seulement après la revue requise, avec sauvegarde SQLite cohérente et migration transactionnelle.

## Plan de travail et jalons


Le premier jalon est une revue documentée. Créer `docs/decisions/10-tags-review.md` contenant les résultats utiles observés, quelques besoins de sélection décrits en anglais pour l'interface, des exemples concrets de morceaux et les propositions de termes directement motivées par ces besoins. Distinguer une propriété mesurée, une estimation, une correction et un jugement utilisateur ; ne pas inventer par défaut des catégories humeur, énergie ou style.

Préparer une maquette de saisie et de filtre avec ces propositions, leurs définitions, cardinalité simple/multiple, éventuels synonymes et exemples de limites. Demander ensuite une revue courte en présentant ce dossier. Consigner date, décisions explicites, termes acceptés/rejetés et questions restantes. Le vocabulaire final et sa version sont copiés dans `docs/specs/tag-vocabulary.md` après l'accord. Si l'accord manque, s'arrêter à ce jalon avec le dossier prêt ; ne pas présenter la fonctionnalité comme livrée.

Le deuxième jalon implémente `domain/tags.py`, `services/tag_service.py`, `persistence/tags_repository.py` et le modèle Qt. Les définitions de tags ont un identifiant stable distinct du libellé, de sorte qu'une correction de nom conserve les affectations. Gérer explicitement type, valeurs multiples, archivage et conflits de libellés. Les éventuelles suppressions montrent leurs conséquences avant confirmation.

Le troisième jalon crée `domain/search.py`, `services/search_service.py` et `persistence/search_repository.py`. L'arbre de critères prend en charge groupes AND/OR/NOT, champs de texte, comparaisons numériques, intervalles, présence/absence et appartenance aux tags. Les opérateurs autorisés dépendent du type de champ ; les paramètres SQL sont liés, jamais concaténés depuis des valeurs de saisie.

Le quatrième jalon persiste les recherches nommées et les vues intelligentes avec version de schéma. Une vue intelligente réexécute exactement les mêmes critères, tri et politique de valeurs manquantes. Afficher un diagnostic si un champ ou tag a disparu ; ne pas supprimer ce critère silencieusement pour élargir les résultats.

Le cinquième jalon ajoute `domain/playlists.py`, `services/playlist_service.py`, `persistence/playlists_repository.py`, `models/playlist_model.py` et `qml/views/PlaylistView.qml`. Créer, renommer et réordonner des playlists manuelles avec clavier et glisser-déposer. Le déplacement d'une occurrence change l'ordre, pas les fichiers ; une source inaccessible reste visible avec un état explicite.

Le dernier jalon relie tags, barre de recherche, inspecteur et navigation aux modèles Qt. Vérifier sélection, double panneau, conservation des références et performances sur 10 000 entrées. Les copies utilisées pour valider déplacements et disparition de fichiers restent séparées de la collection originale.

## Étapes concrètes


Depuis la racine, vérifier les prérequis et le dépôt :

    git status --short
    uv sync --locked
    uv run python -m mtee --data-dir .local/validation/10-review

Préparer le dossier de revue à partir des résultats réels accessibles dans un répertoire de données de test. Présenter quelques recherches concrètes et leurs morceaux résultats, les champs pertinents et les inconnues. Obtenir la décision explicite avant de poursuivre les paragraphes d'implémentation suivants.

Ajouter les tables de définitions/affectations de tags, filtres enregistrés, playlists et occurrences dans la prochaine migration libre sous `src/mtee/persistence/migrations/`. Les contraintes référentielles conservent l'UUID d'un morceau devenu indisponible ; une suppression de fichier ne doit pas effacer en cascade son historique ou ses occurrences sans décision explicite.

Définir dans `domain/search.py` un registre de champs : exemple `file.bpm`, `analysis.tempo`, `confirmed.tempo` et `effective.tempo`. La règle proposée de valeur effective est confirmation manuelle, puis analyse courante exploitable, puis métadonnée fichier ; faire afficher cette règle et conserver l'accès aux trois sources. Une analyse périmée n'est pas utilisée par défaut et une confirmation à revoir est identifiée comme telle.

Définir la normalisation texte, le traitement des accents et de la casse, les valeurs absentes et le tri stable avec départage par UUID. Échapper les métacaractères des recherches LIKE lorsqu'ils sont littéraux. Étudier FTS5 dans SQLite distribué si utile ; si indisponible, utiliser une requête indexée ou une recherche adaptée au volume validée par mesure, sans dépendance système implicite.

Ajouter `models/search_model.py`, `models/tag_model.py`, `qml/components/SearchBar.qml` et `qml/components/TagEditor.qml`. Les requêtes reçoivent un identifiant monotone, un délai de regroupement des frappes et un token d'annulation ; seule la réponse correspondant à la demande courante met à jour la vue. Les résultats restent virtualisés par les vues existantes.

Pour une playlist, attribuer un UUID par occurrence et un ordinal réordonné dans une transaction. Tester les duplications volontaires et le déplacement d'un groupe d'occurrences sans perte. En cas d'erreur de persistance, conserver l'ordre précédent et afficher un échec ; ne pas prétendre que le réordonnancement est enregistré.

Créer `tests/unit/test_search_criteria.py`, `tests/unit/test_tags.py`, `tests/unit/test_playlist_order.py`, `tests/integration/test_search_persistence.py`, `tests/integration/test_playlist_file_moves.py` et `tests/ui/test_search_playlists.py`. Les tests de types emploient des libellés de fixture neutres ; ils ne deviennent pas un vocabulaire produit proposé à l'utilisateur.

Exécuter les contrôles après implémentation :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_search_criteria.py tests/unit/test_tags.py tests/unit/test_playlist_order.py tests/integration/test_search_persistence.py tests/integration/test_playlist_file_moves.py tests/ui/test_search_playlists.py
    uv run python -m mtee --data-dir .local/validation/10
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/10-packaged --smoke-test

Ouvrir ensuite le paquet sans `--smoke-test` pour charger une recherche enregistrée, réordonner une playlist, lire puis déplacer une copie de fichier dans MTEE. Répéter après redémarrage pour vérifier la persistance réelle.

## Validation et acceptation


La revue comporte un accord daté explicite et un vocabulaire versionné. Chaque terme final possède une définition et un cas utile issus de la revue ; aucun résultat automatique n'affecte de lui-même un jugement utilisateur tel qu'un style ou une humeur.

Sur un petit jeu de référence dont les résultats attendus sont écrits avant l'exécution, combiner texte, plage de tempo, présence d'un tag et origine de valeur. Vérifier AND/OR/NOT, parenthèses, champs absents et analyses périmées. Une confirmation manuelle différente du BPM fichier produit des résultats différents selon le champ choisi, conformément à la règle affichée.

Enregistrer les critères et rouvrir l'application : la même source de données produit la même sélection et le même ordre. Ajouter ensuite un morceau correspondant : une vue intelligente le retrouve lors de sa réévaluation ; une playlist manuelle ne change pas spontanément.

Réordonner cinq occurrences, dont deux du même morceau, annuler une action si l'interface le permet, puis redémarrer. L'ordre persisté est exact. Déplacer et renommer une copie via MTEE : toutes ses occurrences restent liées au même UUID. Déconnecter le disque conserve une ligne **Unavailable**, sans rattachement automatique à un fichier homonyme.

Lancer une lecture, puis changer de filtre, trier ou réordonner la playlist : la file du `PlayerService` garde son instantané d'origine. L'utilisateur peut explicitement relancer une lecture depuis le nouvel ordre. Aucun déplacement de playlist n'entraîne un déplacement physique de fichier.

Sur 10 000 entrées, viser un délai inférieur à 300 ms après saisie stabilisée pour les filtres usuels sur la machine de référence, sans blocage durable du thread UI. Ce seuil est une cible de conception à mesurer, pas une exigence chiffrée déjà validée dans `PLAN.md`. Tester la succession rapide de critères pour exclure les réponses périmées.

Renommer/archiver un tag utilisé par un filtre : soit son identifiant continue à résoudre le terme, soit la vue affiche un diagnostic d'incompatibilité, jamais une sélection élargie sans avertissement. Injecter un échec de transaction et vérifier que filtres, affectations et ordre précédent restent cohérents.

Consigner accord de revue, exemples, requêtes sérialisées, résultats, captures et essai du paquet dans `docs/validation/10-tags-recherche-playlists.md`. Les captures et fixtures versionnées ne révèlent pas la collection privée ni ses chemins.

## Reprise et réexécution


La préparation de revue peut être reprise avec les documents existants ; conserver décisions déjà obtenues et ne redemander que les points nouveaux ou explicitement ouverts. Une taxonomie validée n'autorise pas l'ajout silencieux de nouveaux jugements sémantiques lors d'une évolution technique.

Les migrations sont transactionnelles et testées sur une copie de sauvegarde SQLite cohérente. Les changements de vocabulaire ont une version et une table de correspondance explicite si des identifiants doivent être fusionnés. Prévisualiser les affectations et filtres affectés avant une telle migration.

Une annulation de recherche n'a aucun effet sur les données. Une écriture de playlist ou d'affectation est atomique ; après interruption, relire la base pour afficher l'état réellement enregistré. Une source introuvable conserve son UUID et attend une reconnexion ou une résolution explicite, sans recherche de substitut fondée uniquement sur son nom.

## Interfaces et dépendances


`TagService.definitions()`, `preview_assignments(track_ids, changes)` et `apply_assignments(preview)` exposent des affectations locales traçables. Les définitions possèdent identifiant stable, nom, type, cardinalité et version de vocabulaire ; elles ne sont pas des clés Mutagen.

`SearchService.execute(criteria, sort, cancellation) -> SearchResult` utilise un arbre `SearchCriteria` versionné. `SearchResult` contient UUID ordonnés, total et diagnostics de valeurs ou critères indisponibles. `save_filter(name, criteria, sort)` conserve exactement le contrat de recherche et sa politique de provenance.

`PlaylistService.create(name)`, `add_entries(playlist_id, track_ids)`, `preview_reorder(playlist_id, entry_ids)` et `apply_reorder(preview)` travaillent sur des occurrences identifiées. Une version de playlist permet de détecter un aperçu devenu périmé avant écriture. La résolution du chemin passe toujours par le catalogue.

Réutiliser SQLite, les vues virtualisées, `JobService`, `PlayerService` et `AnalysisService`. Aucun moteur de recherche distant ni nouveau service réseau n'est requis. Tout ajout technique doit être justifié par mesure et embarqué dans le paquet Windows.

## Preuves et livraison Git


Avant livraison, mettre à jour le plan, les décisions de revue et le rapport. Indexer uniquement les chemins de l'étape inspectés, en ajoutant individuellement la migration et les adaptations partagées réelles.

    git status --short
    git diff --check
    git add -- src/mtee/domain/tags.py src/mtee/domain/search.py src/mtee/domain/playlists.py src/mtee/services/tag_service.py src/mtee/services/search_service.py src/mtee/services/playlist_service.py src/mtee/persistence/tags_repository.py src/mtee/persistence/search_repository.py src/mtee/persistence/playlists_repository.py src/mtee/models/tag_model.py src/mtee/models/search_model.py src/mtee/models/playlist_model.py src/mtee/qml/components/SearchBar.qml src/mtee/qml/components/TagEditor.qml src/mtee/qml/views/PlaylistView.qml tests/unit/test_search_criteria.py tests/unit/test_tags.py tests/unit/test_playlist_order.py tests/integration/test_search_persistence.py tests/integration/test_playlist_file_moves.py tests/ui/test_search_playlists.py docs/decisions/10-tags-review.md docs/specs/tag-vocabulary.md docs/validation/10-tags-recherche-playlists.md "Plans d'exécution/10-tags-recherche-playlists.md"
    git diff --cached --check
    git diff --cached

Renseigner le message suivant avec les vrais résultats, puis vérifier le distant avant de publier :

    git fetch origin
    git log --oneline --left-right HEAD...origin/main
    $mteeCommitMessage = @'
    feat(library): add reviewed tags, saved searches and ordered playlists

    Changes: implement approved vocabulary, typed provenance-aware filters,
    smart views and stable playlist entries across file moves.
    Validation: replace with review date, exact tests and Windows package result.
    Limits: replace with missing-data behavior and measured search constraints.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-10-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Résoudre toute divergence distante avant publication, sans force ni écrasement du travail d'autrui. L'égalité des révisions après fetch confirme le push ; rapporter cette preuve dans la livraison sans hash auto-référentiel dans le commit. La préparation du dossier de revue seule peut recevoir un commit documentaire intermédiaire, sans prétendre clôturer cette étape fonctionnelle.

Note de révision — 2026-09-10, Codex : création du plan, revue de vocabulaire matérialisée, contrats de recherche et d'occurrences définis ; implémentation et validation encore à réaliser.
