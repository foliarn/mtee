# Étape 109 — Genres des morceaux, Genre manager et tri au pinceau

ExecPlan préparé le 7 octobre 2026 selon [PLANS.md](../PLANS.md). Référence produit : [PLAN.md](../PLAN.md). Ce plan reprend le [brief 108](../docs/decisions/108-arbre-des-genres.md) et le remplace pour les points corrigés par la conversation du 7 octobre. Il est autonome pour son exécution : les décisions, correspondances, contrats et critères nécessaires figurent ci-dessous.

La demande actuelle est de **rédiger le plan**, avec deux lots ordonnés : **1. Associer les genres des dossiers aux morceaux ; 2. Implémenter toutes les fonctionnalités du périmètre retenu**. Cette préparation ne lance ni développement, ni migration, ni application sur la collection. Les numéros 109.1 à 109.7 ci-dessous sont des sous-jalons de ces deux lots, pas de nouvelles demandes d'autorisation entre chaque travail technique.

## Objectif et résultat observable

L'utilisateur remet en ordre environ 2 800 morceaux existants pour disposer d'une taxonomie personnelle fiable. Il démarre avec les genres précis de ses dossiers : `d&b/jump up` donne `Drum & Bass › Jump Up`, `house` donne `House`, les dossiers hybrides donnent plusieurs genres. Il ouvre ensuite une liste de dossier ou de playlist, choisit un genre comme pinceau, coche les morceaux qui le possèdent et utilise Play seulement lorsqu'il souhaite écouter. Il peut créer immédiatement un genre oublié, administrer sa taxonomie et combiner des filtres pour travailler sur la bonne sélection.

Un morceau simplement `House` est un classement valide et potentiellement définitif. Il n'existe ni genre principal, ni obligation de préciser, ni état « écouté », « terminé » ou « à revoir ». Une case non cochée signifie seulement que le morceau n'a pas le genre du pinceau. Les hybrides ont plusieurs genres de même poids. Les libellés ambigus sont toujours accompagnés de leur famille : `House › Deep`, `Dubstep › Deep`, `Techno › Minimal`.

La réorganisation future des dossiers physiques en fonction de cette taxonomie est un objectif ultérieur, **hors de cette livraison**. Elle nécessitera notamment de décider comment ranger les hybrides ; ce plan ne choisit pas de genre principal pour anticiper ce rangement.

## Progress

- [x] 2026-10-07 — Lire les règles, le brief 108, le plan 107 et les contrats de 10 ; confronter les points d'intégration aux sources et tests existants.
- [x] 2026-10-07 — Rédiger le plan en deux lots, consigner les décisions finales et actualiser les références documentaires.
- [x] 2026-10-07 — 109.0 : préparer le prototype QML isolé, son lanceur, 16 captures et le dossier de revue.
- [x] 2026-10-08 — 109.0 : accord utilisateur « Je valide ces maquettes, go » ; obtenir et consigner la revue utilisateur des maquettes avant le code fonctionnel.
- [x] 2026-10-08 — 109.1 : créer le socle de taxonomie, le journal d'opérations et l'amorçage reproductible ; vérifier sur base temporaire et copie.
- [x] 2026-10-08 — 109.2 : présenter le tableau d'amorçage, appliquer le lot validé sur la base réelle sauvegardée, vérifier la persistance.
- [ ] 109.3 — Livrer le Genre manager complet et la création rapide.
- [ ] 109.4 — Livrer la palette, le tri sélectif et le mode pinceau sans lecture automatique.
- [ ] 109.5 — Livrer les filtres combinables et la stabilité des listes pendant le tri.
- [ ] 109.6 — Retirer les anciens genres d'artistes du plan 107 de façon ciblée et réversible.
- [ ] 109.7 — Terminer tests, recette depuis les sources, documentation et publication de l'implémentation.

## Surprises & Discoveries

État observé pendant la préparation : `main` pointe sur `a1da3f6`, synchronisé avec `origin/main` après fetch ; `.agents/`, `.codex/` et `skills-lock.json` sont non suivis et restent exclus des commits. Les migrations versionnées vont jusqu'à `020_artist_enrichment.sql` ; 010 est volontairement retirée. La migration 021 est libre à cet instant, à revérifier au démarrage effectif.

`Database.connection()` fournit une connexion **par thread**, contrairement à la formulation du brief 108 ; `Database.transaction()` ouvre une transaction explicite. `TrackListModel` expose actuellement un rôle `modelData`, conserve les lignes par identifiant et applique les changements sans reset systématique. Le test `tests/unit/test_track_list_model.py` protège ce comportement. Ne pas ajouter une seconde liste indépendante de l'ordre réellement affiché.

Les effectifs historiques des correspondances totalisent 2 813 morceaux. Les dossiers sans genre représentent 241 morceaux, auxquels s'ajoute le morceau de `breaks - jungle` sans analyse : **242 sans genre attendus si ces données sont inchangées**. Ce calcul documentaire n'est pas une nouvelle lecture de la base réelle. Les anciennes valeurs 55 Jungle / 19 Breaks utilisaient un seuil strict ; avec les cinq morceaux à 160, le résultat serait 60 / 14 en l'absence d'autres corrections, à recalculer réellement.

Le plan 107 rapporte **1 603 artistes ayant reçu au moins un genre**, et non un total vérifié de 1 603 puces. Il conserve `genre_added` et `genre_sources` dans `artist_enrichment_reviews.record_json`. `save_artist_profile()` ne fournit pas une provenance individuelle permettant de distinguer avec certitude toute réappropriation manuelle ultérieure d'une ancienne puce : le nettoyage devra préserver les cas ambigus.

La base personnelle, son état de migration courant et les anciens échecs de tests décrits par 108 n'ont pas été revérifiés pendant cette préparation. Aucun test applicatif, démarrage de MTEE ou build Windows n'est annoncé comme effectué ici.

## Decision Log

2026-10-07 — Utilisateur — Priorité à la remise en ordre de la collection existante ; association précise depuis les dossiers en premier, puis implémentation complète. Un dossier Jump Up donne Jump Up et sa famille implicite. Les dossiers mixtes mentionnés dans le tableau contiennent réellement des hybrides ; conserver toutes leurs affectations prévues.

2026-10-07 — Utilisateur — Valider le tableau d'amorçage puis appliquer en une fois, sans confirmation morceau par morceau. Les tags et genres locaux ne sont pas écrits dans les métadonnées des fichiers.

2026-10-07 — Utilisateur — Le manager est crucial dès le parcours de tri, avec création immédiate d'un genre oublié. Le pinceau est prioritaire ; les puces par ligne sont jugées trop compliquées à six ou sept sous-genres. Le présent périmètre n'implémente pas cette seconde variante ni un basculement entre deux workflows.

2026-10-07 — Utilisateur — Pas de suivi d'écoute. Cocher ne déclenche ni lecture ni passage au suivant ; l'utilisateur utilise les commandes de lecture classiques au besoin. Retirer le dernier sous-genre Deep ramène le morceau à House. House seul est un résultat valable.

2026-10-07 — Utilisateur — Filtres complets combinant inclusion, exclusion, ET et OU : sans le genre du pinceau actif, sans aucun sous-genre, Speed Garage ET Bassline, tout sauf Bassline. Les familles de base ne comptent pas comme sous-genres ; ne pas proposer d'exclure Drum & Bass dans le contexte Jump Up. Pas de XOR strict demandé.

2026-10-07 — Utilisateur — Ctrl+Z et sauvegardes retenus. La suppression forcée enlève tout le sous-arbre et ses liens, depuis une zone sûre de type paramètres. Le point 7 de la critique (étude détaillée des impacts de reparentage et regroupements) est reporté : ne pas ajouter maintenant d'assistant d'impact, de simulation ou de validation spécifique à ce déplacement. Les fonctions initiales de déplacement et de méta-familles du manager restent prévues.

2026-10-07 — Conception du plan — Normaliser les affectations en nœuds les plus précis, déduire les ancêtres, conserver la famille lorsque son dernier sous-genre est retiré par le tri ordinaire. La suppression forcée est une opération distincte sans cette réaffectation automatique. Les noms de tables et API proposés plus bas sont des contrats à créer, pas des fonctionnalités existantes.

2026-10-07 — Conception du plan — Journal persistant d'opérations et sauvegardes cohérentes, avec pile Ctrl+Z de session limitée au périmètre genres/tags. Les filtres sont des arbres de critères versionnés réutilisables par le futur moteur de 10 ; aucune reconstruction des playlists existantes ni implémentation anticipée de toutes les recherches de 10.

## Périmètre et protection des données

Ne créer, renommer, déplacer, modifier ou supprimer **aucun fichier ni dossier de la collection `foliarn`**. Les chemins enregistrés et les analyses existantes servent de sources en lecture. Ne pas écrire de tags audio, même pour confirmer l'amorçage. Les tags personnalisés restent exclusivement dans MTEE. Aucun chemin du `MetadataWriter` ne reçoit les genres/tags locaux.

L'exécution peut écrire la base MTEE, ses sauvegardes et les rapports locaux hors collection, uniquement pour les opérations prévues. Ne versionner ni base, ni rapports nominatifs, ni captures révélant la collection personnelle. Le script refuse une destination de rapport ou de sauvegarde à l'intérieur de la collection protégée. Les tests d'écriture travaillent sur des fixtures ou copies ; une copie de SQLite doit être cohérente en mode WAL, avec l'API de sauvegarde SQLite, jamais une simple copie du seul fichier principal à chaud.

Reste hors périmètre : déplacements physiques futurs, écriture du champ Genre des fichiers, agrégation des genres par artiste, attribution des remix aux artistes, aide basée sur les genres des autres morceaux de l'artiste, Spotify/SoundCloud, nouveau moteur audio, packaging Windows, variantes de tri par puces, fusion de genres et suivi de progression d'écoute. L'affichage du BPM d'analyse existant et des dossiers d'origine reste inclus.

## Prérequis et points d'intégration vérifiés

Lire `PLAN.md`, `PLANS.md`, ce plan entier, le brief 108 et les [plans 10](10-tags-recherche-playlists.md), [106](106-artistes-types-filtres-masques.md), [107](107-genres-depuis-les-dossiers.md) pour les contrats repris. Le vocabulaire et les règles métier sont validés dans la conversation ; la disposition visuelle nouvelle n'a pas encore été revue. La simple rédaction de ce plan n'en tient pas lieu.

Le socle disponible comprend `src/mtee/persistence/database.py`, `library_repository.py`, `artist_repository.py`, `src/mtee/services/jobs.py`, `src/mtee/models/track_list_model.py`, `workspace_model.py` et `src/mtee/app.py`. Les vues passent par `TrackListView.qml`, `TrackContextMenu.qml`, `InfoPanel.qml`, `EditorGroup.qml`, `SideBar.qml` et `views/SettingsView.qml`. Réutiliser les primitives QML `FilterChip.qml` et `Mtee/WheelScrollHandler.qml` lorsque pertinent, sans les coupler aux artistes.

Les entrées de l'amorçage sont `library_roots`, `root_tracks` (racine, chemin relatif, présence), `tracks` et `track_analysis.bpm`. Ne pas lire `metadata_json.genre` ou le BPM du fichier comme substituts. Un morceau sans crédit d'artiste ou un remix non résolu reçoit ses genres normalement : l'identité utilisée est `track_id`.

Le script existant `scripts/genres_from_folders.py` écrit sur les **artistes** ; ne pas le réutiliser tel quel pour appliquer ce plan. `domain/folder_genres.py` et ses tests servent de références de lecture et de normalisation, mais leurs anciennes règles et libellés ne définissent pas la nouvelle taxonomie.

## Taxonomie initiale à créer

Chaque nœud possède un UUID stable, un parent facultatif, un libellé, un ordre et un état d'archivage. Le même libellé est permis sous des parents différents. L'arbre est acyclique ; aucune profondeur fixe de deux niveaux n'est inscrite dans le stockage. L'interface affiche le chemin complet lorsque nécessaire. Les UUID de la taxonomie initiale sont fixés dans la configuration, jamais régénérés à chaque passage.

| Famille | Sous-genres initiaux |
|---|---|
| House | Tech, Bass, Minimal, Deep, Disco, French |
| UK Garage | Speed Garage, 2-Step, Bassline |
| Drum & Bass | Jump Up, Neuro, Liquid, Drumstep, Rollers, Jungle, Minimal, Dancefloor, 4x4 |
| Dubstep | Deep, Tearout, Riddim, Brostep, Trap, UK Dubstep |
| Techno | Minimal, Hardgroove, Hard House, Bouncy Techno, Trance |
| Hard Dance | Hardstyle, Rawstyle, Uptempo, Hard Techno |
| Dance, Breaks, Baile, Rap, Future Bass, Pop, Rock, Jazz, Classical | Aucun pour l'instant ; ajouts libres |

`Nu Trance` est un alias de `Techno › Bouncy Techno`. Les recherches reconnaissent aussi les noms usuels composés comme Deep House, Bass House et les graphies de la configuration (UKG, d&b). Un alias ambigu ne choisit pas silencieusement une famille. Les anciens noms de dossiers servent de correspondances explicites ; ils ne deviennent pas tous des alias globaux de recherche.

Les méta-familles restent distinctes de l'arbre : Bass Music relie UK Garage, Dubstep, Drum & Bass, House › Bass et Baile ; Hard relie Hard Dance, Techno › Hard House et Techno › Hardgroove ; Club relie House, Techno et UK Garage. Ces liens sont modifiables dans le manager. Un morceau en hérite par ses genres et ancêtres ; on n'affecte pas directement une méta-famille au morceau. « Commercial » est abandonné. Les tags personnalisés (par exemple Banger, Calm, Euphoric) sont des définitions libres séparées, avec UUID et couleur facultative ; ces exemples ne constituent pas une liste obligatoire à préremplir.

## 109.0 — Préparation visuelle préalable aux deux lots

Ce numéro désigne un prérequis, sans changer l'ordre des deux lots métier. Produire des maquettes QML à données fictives sous `src/mtee/qml/prototypes/genres/`, avec un lanceur à créer `scripts/review_genres_109.py` et un dossier de revue `docs/ux/review-109-genres.md`. Ne pas brancher la base réelle dans ce prototype. Il doit permettre de voir le résultat minimal du lot 1, le manager en tables, le pinceau, les filtres et les cas de retrait/erreur avant le code fonctionnel, conformément à `PLAN.md`.

Montrer une liste House avec House seul, Deep, Deep + Minimal, un hybride inter-familles, une liste Jump Up avec son contexte Drum & Bass, et une playlist mélangée. Examiner la création rapide, une sélection multiple, une fenêtre étroite, deux panneaux, les lignes grisées retenues, l'état Saving/erreur et la suppression dans les paramètres. La maquette ne comporte aucune rangée de six à neuf puces interactives par morceau. Les affectations déjà présentes peuvent être montrées comme texte ou badges récapitulatifs non interactifs, avec le chemin non ambigu.

Consigner la revue des maquettes et les ajustements avant d'implémenter les surfaces correspondantes ; ne pas reprendre l'affirmation de 108 selon laquelle la demande de variantes équivaudrait automatiquement à cette revue. La présente demande porte sur le plan : préparer et obtenir cette revue sera une action de l'exécution, pas une raison de laisser le plan incomplet aujourd'hui.

## Lot 1 — Associer les genres des dossiers aux morceaux

### Correspondances à vérifier puis appliquer en un lot

Les chiffres ci-dessous proviennent du brief, pas d'un inventaire exécuté par ce plan. La configuration versionnée future contiendra les chemins complets réellement observés, sans les abréviations `…` du tableau. Les noms de la racine personnelle ne sont pas codés dans le moteur générique. Une racine inconnue ou plusieurs racines portant le même nom exigent un `root_id` explicite, sans sélectionner arbitrairement la première.

| Dossier ou groupe de dossiers | Effectif historique | Affectations directes |
|---|---:|---|
| d&b / jump up | 478 | Drum & Bass › Jump Up |
| d&b / minimal - dark | 92 | Drum & Bass › Minimal |
| d&b / washed up | 72 | Drum & Bass |
| d&b / liquid (chill) | 48 | Drum & Bass › Liquid |
| d&b / le reste (…) | 47 | Drum & Bass |
| d&b / neurofunk (je crois) | 42 | Drum & Bass › Neuro |
| d&b / dancefloor | 30 | Drum & Bass › Dancefloor |
| d&b / 4x4 | 12 | Drum & Bass › 4x4 |
| d&b / drumstep | 6 | Drum & Bass › Drumstep |
| ukg - speed garage & bangers | 262 | UK Garage › Speed Garage |
| ukg - chill | 195 | UK Garage |
| ukg - slow bangers | 103 | UK Garage |
| ukg - 2step | 85 | UK Garage › 2-Step |
| ukg - bassline | 37 | UK Garage › Bassline |
| dubstep 140 | 206 | Dubstep › UK Dubstep |
| dubstep (le reste), dubstep cool | 49 + 31 | Dubstep |
| nu trap | 24 | Dubstep › Trap |
| house | 202 | House |
| tech house, bass house | 25 + 14 | Respectivement House › Tech, House › Bass |
| hard house - nu trance - bouncy stuff | 77 | Techno › Hard House ET Techno › Bouncy Techno |
| hardgroove | 84 | Techno › Hardgroove |
| techno min cool | 36 | Techno › Minimal |
| techno, trance | 39 | Techno › Trance ; Techno implicite |
| hard techno | 88 | Hard Dance › Hard Techno |
| hard,rawstyle | 8 | Hard Dance › Hardstyle ET Rawstyle ET Uptempo |
| breaks - jungle | 75 | Règle BPM ci-dessous |
| baile, rap, dance, pop | 25 + 16 + 54 + 5 | Respectivement Baile, Rap, Dance, Pop |
| future | 5 | Future Bass |
| chill&atmospheric, old school | 23 + 16 | Aucun genre |
| zzZ, Artists, dj blc | 97 + 75 + 30 | Aucun genre |

Pour `breaks - jungle`, lire le BPM d'analyse MTEE (correction manuelle déjà intégrée à cette valeur comprise). Si le BPM est positif, fini et inférieur à 90, le doubler **pour le calcul de la règle seulement**. Valeur effective supérieure ou égale à 160 : Drum & Bass › Jungle ; sinon : Breaks. BPM absent ou invalide : aucun genre et motif dans le rapport. Ne modifier ni l'analyse, ni son indicateur de correction, ni un tag audio. Une réanalyse ultérieure ne reclassera pas automatiquement le morceau.

Le rapport distingue morceaux, affectations multiples, familles implicites, morceaux sans genre, exclus, absents et conflits de correspondance. Ne pas compter les affectations hybrides comme plusieurs morceaux. Les morceaux présents de `foliarn` sont concernés ; `mixs` est exclu de cet amorçage. Un chemin non couvert reste sans nouvelle affectation avec un signalement, sans déduction approximative depuis ses mots.

### 109.1 — Socle et amorçage sur copie

Créer `src/mtee/domain/genres.py`, `src/mtee/persistence/genre_repository.py`, `src/mtee/services/genre_service.py`, `src/mtee/services/genre_seed_service.py` et `src/mtee/resources/genres/initial_taxonomy.json`, `folder_mapping.json`. La migration proposée `021_track_genres.sql` ajoute les définitions et affectations décrites dans les contrats plus bas. Le bootstrap crée l'arbre initial sur base vide, mais ne réinitialise jamais les noms ou positions modifiés dans le manager. Une nouvelle version de configuration ne vaut pas autorisation de réécrire les affectations existantes.

Pour rendre le lot 1 observable avant le manager, brancher dès ce jalon une lecture groupée des affectations dans `TrackListModel`/`WorkspaceModel` et un affichage en lecture seule `MTEE genres` dans la liste et le panneau Info, conformément à la maquette. Distinguer ce champ local du champ Genre des métadonnées audio. Le lot 2 enrichira ce même flux avec l'édition, sans remplacer le lecteur de données. Étendre le test du modèle pour vérifier les chemins de genres, les familles seules et les hybrides après rechargement.

Créer `scripts/seed_track_genres.py`, avec `--database`, `--root-id`, `--report-dir` et les modes exclusifs `--preview`, `--apply-plan <fichier>` et `--undo-operation <id>`. Le mode par défaut est preview, en lecture SQLite seule et sans migration implicite ; il doit pouvoir examiner une base au schéma 020 et produire un plan avant la migration 021. Il écrit uniquement ses rapports dans le répertoire demandé. L'application exige une sauvegarde réussie, migre si nécessaire, puis inscrit dans une transaction toutes les affectations du plan approuvé.

Le plan d'amorçage enregistre version et empreinte de configuration, racine, UUID ciblés, chemins observés, BPM utilisés, états initiaux des affectations et empreinte de cet ensemble. Avant application, recalculer les préconditions : si les données pertinentes diffèrent, ne rien écrire et régénérer l'aperçu. L'approbation porte sur ce résultat concret. Après application, provenance `folder` confirmée pour tout le lot ; aucun état de proposition en attente par morceau à traiter dans la liste.

Les exécutions répétées sont idempotentes. Un morceau déjà amorcé ou corrigé manuellement n'est pas réinitialisé ; conserver une marque durable de traitement et les suppressions manuelles, même si le morceau n'a plus de genre. Les nouveaux morceaux peuvent faire l'objet d'un nouveau plan explicite. Aucun nouvel amorçage automatique au démarrage, au scan ou à l'analyse.

Créer `tests/unit/test_genres.py`, `test_genre_seed_service.py` et `tests/integration/test_genre_repository.py`, `test_genre_seed.py`. Étendre `test_database_migrations.py` et `test_playback_repository.py` pour la nouvelle version. Vérifier migrations neuve/existante, sauvegarde, rollback, stabilité des UUID, exclusions, hybrides, demi-BPM, borne 160, absence d'analyse, configuration ambiguë, préconditions périmées et répétition après correction manuelle. Vérifier sur copies que les octets des fichiers audio restent identiques et que le service ne dépend pas des voies d'écriture audio.

### 109.2 — Application contrôlée et livraison du lot 1

Préparer une copie cohérente de la base, produire le tableau et les rapports détaillés locaux, appliquer sur cette copie et relire les affectations après fermeture/réouverture. Présenter le tableau réel à l'utilisateur pour la vérification par lot déjà demandée ; il n'y a pas de confirmation par morceau. Si cette vérification a déjà été donnée pour le même plan inchangé dans la session d'exécution, ne pas la redemander.

Avant l'application réelle, fermer proprement les instances MTEE et les outils qui écrivent sa base, ou utiliser la même coordination de service si l'application pilote l'opération ; ne pas tuer un processus de force. Sauvegarder avec SQLite, conserver le chemin et l'identifiant d'opération dans le rapport local, appliquer exactement le plan vérifié, contrôler `quick_check`, les clés étrangères, les effectifs et un échantillon de familles simples/hybrides. Relancer depuis les sources pour vérifier les données affichées par la vue minimale revue en 109.0. Aucun genre n'est écrit dans `foliarn`.

Ce lot est achevé quand l'association est effectivement présente et vérifiée dans MTEE, avec rapport, sauvegarde et reprise disponibles. Un aperçu seul ou une application sur copie ne vaut pas application réelle. En cas d'attente de revue utilisateur, consigner l'état exact et continuer uniquement les travaux indépendants autorisés.

## Lot 2 — Implémenter tout le périmètre retenu

### 109.3 — Genre manager et création immédiate

Créer `src/mtee/models/genre_manager_model.py`, `src/mtee/qml/views/GenreManagerView.qml` et des composants dédiés `GenreFamilyTable.qml`, `GenreEditDialog.qml`, `GenreDeleteDialog.qml`. Brancher l'accès à `Genre manager` depuis la navigation et la barre de tri, dans `workspace_model.py`, `EditorGroup.qml`, `SideBar.qml` et `app.py`. Ouvrir le manager ne coupe pas la lecture et conserve le dossier, le pinceau et la sélection de retour.

Présenter les familles en tables avec leurs enfants, leurs compteurs et un défilement adapté. Le manager permet création, renommage, réordonnancement, déplacement d'un sous-genre par glisser-déposer, alias, archivage/restauration et suppression ordinaire. Prévoir l'équivalent clavier/menu `Move to…`. Les opérations utilisent les UUID ; aucun changement de libellé ne perd les affectations. Interdire cycles, autoparentage et doublons de nom normalisé au même niveau ; résoudre explicitement les collisions de destination, sans fusion implicite. Le déplacement conserve l'UUID et applique les règles élémentaires de l'arbre, sans développer l'assistant d'impact reporté.

Des sections dédiées administrent les méta-familles (liens multiples aux genres) et les tags personnalisés (définitions, couleur facultative, renommage, archivage et suppression). Les compteurs reflètent des morceaux distincts selon un périmètre annoncé ; ne pas additionner aveuglément les sous-genres hybrides. Une définition archivée reste lisible sur les morceaux et dans les filtres existants, mais n'est plus proposée par défaut pour de nouvelles affectations. Restaurer la définition la rend à nouveau disponible ; archiver une famille archive son sous-arbre et conserve tous les liens.

La suppression ordinaire refuse un genre qui a des descendants ou des morceaux affectés. Les autres dépendances (alias, liens méta-familles, filtres) sont inventoriées ; supprimer un nœud vide retire ses liens techniques et rend explicitement invalides les filtres qui le référencent. Ne pas effacer silencieusement un critère pour élargir une vue.

La **suppression forcée** est accessible uniquement depuis `Settings > Library > Genres > Advanced`, avec une cible nommée, le nombre de descendants et de morceaux, une confirmation explicite et une sauvegarde préalable obligatoire. Elle supprime la définition ciblée, ses descendants, alias, affectations et liens actifs de méta-familles. Elle ne réaffecte pas de famille de remplacement, préserve les autres genres du morceau et tous les fichiers. Le journal conserve les instantanés nécessaires à la récupération ; « tout supprimer » concerne les données actives, pas la destruction des sauvegardes et de la preuve d'opération. Une sauvegarde échouée interdit l'opération. Appliquer le même principe aux tags et méta-familles : supprimer un regroupement n'efface pas les genres qu'il regroupait.

Depuis la palette de tri, une recherche sans résultat propose `Create genre…` avec famille/parent explicite, ou `Create tag…` dans le mode tags. Le contexte peut préremplir le parent, mais sa confirmation ne doit jamais créer Deep dans la mauvaise famille. Après création, le genre devient sélectionnable comme pinceau immédiatement, sans attribuer arbitrairement ce genre à tous les morceaux visibles. Les derniers genres utilisés sont accessibles sans déplacer automatiquement le choix actuellement actif. Les touches 1 à 9 choisissent les favoris/récents visibles lorsque la barre de pinceau a le focus ; elles ne changent jamais les genres d'une sélection à elles seules et restent de la saisie normale dans un champ texte.

Créer `tests/unit/test_genre_manager_model.py` et `tests/ui/test_genre_manager_ui.py`. Vérifier UUID après renommage/déplacement, cycles, collisions, même libellé sous deux familles, archivage, création depuis une liste, suppression ordinaire refusée, suppression forcée complète et restauration sans perte de données étrangères à l'opération.

### 109.4 — Palette, tri sélectif, pinceau et Ctrl+Z

Créer `src/mtee/models/genre_tagging_model.py` et les composants QML `GenreTaggingBar.qml`, `GenrePicker.qml`, `TrackGenreEditor.qml`. Étendre le flux de lignes existant de `TrackListModel` et `WorkspaceModel`, plutôt que d'ajouter un service ou une requête SQL par delegate QML. Exposer sur chaque ligne les affectations explicites, libellés complets, familles déduites, état du pinceau, état d'enregistrement et éventuelle rétention par filtre.

Le bouton `Tagging` est disponible dans les listes de dossiers et playlists, pas dans les pages d'artiste ni les résultats de recherche globaux. Il ajoute la barre de pinceau et une case par morceau. La case représente **uniquement l'appartenance au genre actif** : elle n'est pas une seconde sélection multiple. La sélection habituelle par clic/Ctrl/Maj garde son rôle pour les opérations par lot. Les cases et les commandes de filtre consomment leur événement pour ne déclencher ni sélection indésirable, ni Play, ni glisser-déposer de fichier.

Dans ce mode, cliquer une ligne sélectionne le morceau ; cocher ajoute le genre immédiatement, décocher le retire. Ni ces actions, ni le changement de pinceau, ni la création d'un genre ne lancent la lecture. Les boutons Play/Pause et raccourcis explicites du lecteur restent utilisables. Ne pas ajouter « cocher et suivant », lecture automatique, saut vers un non-classé ou parcours imposé. Le comportement des listes hors mode tagging n'est pas refondu.

Le parcours permet d'afficher et trier sur le BPM d'analyse existant, distinct d'un BPM provenant uniquement des métadonnées, et de consulter le dossier d'origine de l'amorçage. Une valeur d'analyse absente reste vide ; ne pas lancer une analyse ni substituer silencieusement le BPM du fichier. Ces aides ne réintroduisent pas l'agrégation des genres par artiste.

Ajouter Deep à House remplace l'affectation directe House par House › Deep ; la famille reste déduite et affichable. Ajouter House › Minimal conserve Deep. Retirer Deep conserve Minimal s'il est présent ; retirer le dernier sous-genre de cette famille restaure House. Pour un arbre plus profond, le retrait du dernier descendant rend la famille racine, choix cohérent avec la demande actuelle ; un ancêtre intermédiaire reste attribuable explicitement. Ajouter une famille déjà impliquée par un descendant est sans effet. Retirer explicitement toute une famille est une commande distincte qui retire tous ses descendants du morceau. Les autres familles des hybrides restent intactes.

Si le pinceau est une famille, la case reflète aussi l'appartenance héritée : un Deep apparaît House. La famille de contexte du dossier est montrée comme acquise, sans case de retrait active ; les autres familles héritées portent un état explicite et renvoient à `Remove family and subgenres…` pour le retrait de toute la branche. Ne pas donner à une simple décoche l'effet caché de supprimer plusieurs sous-genres. Une famille directement attribuée, sans descendants ni protection de contexte, reste retirable normalement.

La palette depuis le clic droit et le panneau Info permet `Add genre`, `Remove genre` et les équivalents pour tags, avec nombre de morceaux ciblés. La cible est la sélection explicite, jamais l'ensemble des cases déjà cochées du pinceau. Entrée ajoute ; un remplacement éventuel exige une commande nommée, jamais le raccourci par défaut. Les valeurs mixtes sont montrées comme telles ; ajouter un genre n'uniformise pas les autres affectations du lot. Les actions capturent leurs `track_id` au déclenchement, même si la sélection évolue ensuite.

Ctrl+Z annule la dernière opération locale de genre/tag, un lot entier en une fois. Le focus dans une saisie texte garde l'annulation de texte ; l'annulation des métadonnées et des fichiers existante ne doit pas être interceptée. Une annulation est une opération inverse avec vérification des révisions, pas une restauration complète de la base. Les mutations en attente sont sérialisées ; une erreur ramène l'interface à l'état confirmé sans écraser un changement postérieur. La pile se vide au redémarrage ; le journal durable et les sauvegardes permettent la reprise administrative décrite plus bas.

Créer `tests/unit/test_genre_tagging_model.py`, `tests/integration/test_genre_operations.py` et `tests/ui/test_genre_tagging_ui.py`. Couvrir recyclage des delegates, scroll, sélection différente des cases, changement de pinceau, créations, état mixte, retour à House, Ctrl+Z de lot, focus texte, clics rapides, erreur d'écriture, absence de lecture automatique et mise à jour du même morceau dans deux onglets.

### 109.5 — Filtres complets et listes stables

Créer `src/mtee/domain/genre_filters.py`, `src/mtee/models/genre_filter_model.py` et `GenreFilterEditor.qml`. Une expression versionnée est composée de groupes `all` (ET), `any` (OU), négation `not` et prédicats typés. Le modèle valide cette expression et la compile vers des requêtes paramétrées, sans SQL libre en provenance de QML. Le moteur doit permettre les combinaisons ci-dessous et leur imbrication ; ne pas réduire la demande à une simple paire de puces « avec/sans ».

| Contrôle de l'interface | Sens exact |
|---|---|
| `Has all genres` | Tous les genres choisis, avec descendants lorsque l'on choisit une famille |
| `Has any genre` | Au moins un des genres choisis |
| `Exclude genres` | Aucun des genres choisis ni de leurs descendants |
| `Without brush genre` | Absence du genre actuellement choisi comme pinceau, résolu au moment de l'évaluation |
| `No subgenre` | Aucun genre explicite de profondeur supérieure à zéro, quelle que soit sa famille |
| `Family only` | Famille choisie présente, aucun descendant affecté dans cette famille ; autres familles permises |
| `No genre` | Aucun genre attribué ; les tags personnalisés ne changent pas ce résultat |
| `Has / excludes tags` | Inclusion/exclusion des tags locaux, combinable avec les genres |
| `Has / excludes meta-family` | Appartenance déduite d'un genre ou de son ascendance |

`No subgenre` inclut les morceaux sans genre et les morceaux House/UK Garage seuls. Un morceau House + Drum & Bass › Jump Up ne satisfait pas ce filtre global, mais satisfait `Family only: House`. Un Jump Up issu de l'amorçage est bien un sous-genre ; les familles Drum & Bass/House implicites ne comptent pas comme un sous-genre supplémentaire.

La liste courante (dossier ou playlist), sa recherche textuelle et l'expression de filtres se combinent par intersection. Dans les filtres, « tout » signifie tous les morceaux de ce périmètre, pas toute la bibliothèque. Dans un dossier dont le contexte de taxonomie est connu, montrer la famille de base séparément : `Context: Drum & Bass` pour Jump Up. Ne pas proposer `Exclude Drum & Bass` à l'intérieur de ce contexte ; une exclusion de tout ancêtre qui annulerait ce contexte est pareillement invalide. Cette protection ne rend pas Jump Up intouchable et n'empêche pas l'édition des affectations. Dans une playlist mélangée sans famille imposée, les exclusions de familles restent possibles.

Le contexte vient des correspondances validées, pas d'un nom de dossier interprété approximativement. Un dossier hybride entre familles peut avoir plusieurs contextes ; un dossier non reconnu n'en a aucun. Au changement de dossier, revalider les filtres : une combinaison incompatible reste signalée et modifiable, jamais supprimée silencieusement. Une condition liée au pinceau n'est pas évaluée sans pinceau sélectionné ; demander de choisir le pinceau ou de retirer cette condition.

La barre permet de créer des groupes `All`/`Any`, d'ajouter des exclusions, de retirer une condition et de réinitialiser les filtres. Afficher un résumé intelligible et le nombre de résultats. Persister l'expression, le pinceau et le mode par onglet avec les préférences existantes ; permettre d'enregistrer et rappeler des filtres nommés dans les réglages locaux. Le critère dynamique `Without brush genre` reste dynamique lors du rappel, tandis qu'un critère de genre explicite conserve son UUID. Aucun état « écouté » n'est stocké. Un filtre référençant un genre supprimé est marqué invalide, sans transformer cette référence en critère vrai.

Quand une coche fait sortir un morceau du résultat, conserver sa ligne à la même place, atténuée et identifiée comme ne correspondant plus au filtre, jusqu'à l'action `Refresh results`, qui recalcule explicitement la liste. Cette rétention s'applique aussi au filtre `No subgenre`. Les lignes retenues restent corrigeables et jouables ; elles ne sont pas comptées comme résultats correspondants. Annuler une action qui rétablit la correspondance retire leur atténuation.

Un changement explicite de filtre, de pinceau, de dossier ou de tri reconstruit les résultats et termine cette rétention ; une écriture de genre seule ne déplace pas les lignes. Conserver l'ancre de scroll si elle existe encore. Play utilise un instantané explicite de l'ordre affiché, lignes retenues comprises ; les filtres et modifications ultérieures ne reconstruisent pas la file en cours. Préserver les comportements existants de playlist, d'îlot et d'ordre manuel.

Créer `tests/unit/test_genre_filters.py`, `tests/integration/test_genre_filter_queries.py` et `tests/ui/test_genre_filters_ui.py`. Tester notamment `(sans pinceau OU sans sous-genre) ET sans Bassline`, Speed Garage ET Bassline, la variante OU, les familles implicites, les genres de même nom, la famille contextuelle protégée, playlists mixtes, valeurs manquantes, tags, filtres sauvegardés, références supprimées et stabilité des lignes après coche/annulation. Comparer l'évaluation métier et les résultats du dépôt sur la même fixture.

### 109.6 — Retrait ciblé des genres d'artistes du plan 107

Ce travail vient après les genres de morceaux effectivement en place. Créer un mode de préparation/application/récupération dans `scripts/retire_artist_folder_genres.py`, en s'appuyant sur `artist_repository.py`. Produire un rapport des modifications proposées depuis `record_json.genre_added`, sauvegarder, puis retirer uniquement les ajouts traçables de 107 et leurs champs de provenance actifs. Conserver rôles, `idgaf`, décision, masquage, liens, notes, crédits et tags manuels étrangers au lot.

Ne pas traiter la liste de noms de genres comme une autorisation de supprimer toute puce homonyme. Une puce modifiée ou réintroduite manuellement après 107 peut être ambiguë avec la provenance disponible : comparer aux instantanés et sauvegardes utilisables, isoler les cas non prouvables dans le rapport au lieu de les effacer. Le script doit pouvoir annuler son opération sans restaurer les autres données d'artistes. Ne pas recréer les agrégats artistes ni traiter les 52 remix non résolus à cette occasion.

Ajouter les cas de conservation, répétition et restauration à `tests/unit/test_folder_genres.py` ou créer `tests/integration/test_retire_artist_folder_genres.py` si la transaction dédiée justifie un module séparé. Faire la recette sur copie avant base réelle, puis vérifier les profils existants depuis les sources.

### 109.7 — Recette finale et livraison

Mesurer le comportement sur une fixture de l'ordre de 830 morceaux dans une vue et 2 800 dans la collection, puis sur une copie cohérente de la bibliothèque. Vérifier le chargement, le filtrage, la frappe dans la palette, le scroll, les lots et l'annulation pendant la lecture ; consigner machine, tailles et temps réellement observés sans inventer un seuil contractuel. Les requêtes et mutations quittent le thread graphique ; aucun accès par ligne depuis QML, aucune reconstruction permanente de milliers de composants.

Terminer les parcours manuels ci-dessous, corriger les régressions du périmètre, actualiser ce plan et `docs/validation/109-genres-morceaux-manager-tri.md`. Consigner séparément recette automatisée, vérification manuelle par l'agent et recette interactive de l'utilisateur. Le packaging reste non exécuté, sauf demande explicite ultérieure portant sur la distribution Windows.

## Contrats à créer pour le domaine, la persistance et les modèles

### Données et invariants

La migration 021 proposée crée `genres` (UUID, parent, nom, clé normalisée, ordre, archivage, révision), `genre_aliases`, `genre_meta_families`, `genre_meta_members`, `track_genres`, `local_tags`, `track_local_tags`, `genre_seed_runs`, `genre_seed_tracks`, `genre_operations` et `genre_operation_items`. Les filtres nommés et préférences d'onglet utilisent les réglages existants avec un format JSON versionné ; ne créer une autre table que si la lecture du dépôt justifie ce changement, à documenter.

Les liens `track_genres` sont uniques par couple morceau/genre, sans ordre ni poids musical ; leur provenance indique `folder` ou `manual`, l'opération et la date. Les ensembles sont normalisés sans ancêtre redondant. Les assignations de genres et de tags sont séparées. Les liaisons aux genres supprimés sont retirées transactionnellement lors d'une suppression forcée. L'historique contient UUID et instantanés nécessaires sans clé étrangère avec suppression en cascade : disparition d'un fichier ou retrait d'une définition ne détruit pas cette histoire.

Le journal conserve type d'action, cibles, états avant/après, révisions attendues, statut et éventuelle opération inverse. Les définitions et relations supprimées sont dans ces instantanés, pas seulement leurs noms. Un changement manuel, y compris le retrait du dernier genre, est enregistré durablement pour qu'un futur amorçage ne le reconstitue pas. Un déplacement connu dans MTEE conserve `track_id` et donc les liens ; ne promettre ni dédoublonnage ni identité retrouvée après un déplacement externe non résolu.

Les index couvrent affectations par morceau et par genre, parent de genre, appartenance aux méta-familles et clés de recherche normalisées. Tester l'unicité des familles racines malgré le parent NULL, ainsi que l'unicité parmi les enfants d'un même parent. Les alias n'introduisent aucun lien de parentage et ne provoquent pas de fusion. Les longueurs maximales éventuelles protègent seulement l'entrée technique ; ne reprendre ni la limite de 20 tags par artiste ni la taxonomie plate de 106.

### Opérations de service

Le contrat proposé de `GenreService` distingue lecture et commandes : `taxonomy_snapshot`, `track_assignments`, `create_genre`, `rename_genre`, `move_genre`, `archive_genre`, `delete_genre`, `set_brush_membership(track_ids, genre_id, enabled)`, `add_genres`, `remove_genres`, opérations équivalentes pour tags, `undo(operation_id, expected_revision)`. Le service d'amorçage propose `preview`, `apply` et `undo` sur un plan révisé. Les noms peuvent être adaptés aux conventions réelles, en conservant les sémantiques.

Chaque commande de lot est atomique et sérialisée par base dans ce domaine. QML envoie des UUID, une intention et les révisions attendues ; Python valide, ouvre la connexion du thread de travail, écrit, puis renvoie un résultat avec identifiant d'opération et morceaux modifiés. Les modèles Qt ne sont modifiés que sur le thread graphique. Les résultats d'un ancien onglet, ancien pinceau ou filtre périmé sont rejetés par révision. Les tâches longues passent par `JobService`, avec progression et annulation avant commit ; un lot annulé ne laisse pas d'affectations partielles.

Une correction optimiste reste identifiée comme `Saving` jusqu'à confirmation. Les erreurs affichent `Could not save`, préservent les choix utiles et rendent possible la relance. L'échec d'une action ancienne ne remet pas un morceau dans un état antérieur à une action plus récente. Ctrl+Z attend ou annule proprement une commande en cours au lieu de courir contre son commit. Les mises à jour sont diffusées à toutes les vues du morceau, au manager et aux filtres concernés.

### Sauvegarde et reprise

Créer des sauvegardes SQLite cohérentes avant migration, amorçage réel, suppression forcée et nettoyage 107. Les déposer hors de `foliarn` avec un nom unique et la version de schéma. Vérifier qu'elles se rouvrent et passent `quick_check` avant de qualifier une sauvegarde d'utilisable. Aucune rotation destructive automatique n'est ajoutée à cette étape.

L'annulation ordinaire restaure seulement les données touchées si leurs révisions correspondent encore à l'opération. En cas de conflit, refuser l'annulation avec les cibles concernées, sans écraser une correction indépendante. La reprise administrative via les scripts utilise le même mécanisme d'inversion. Restaurer une base entière est un dernier recours, application fermée, après sauvegarde de l'état courant et décision explicite ; ne pas remplacer la base courante pour annuler un seul genre.

Prévoir un contrôle d'interruption : fermeture entre aperçu et application, exception pendant un lot, arrêt avant commit, lancement avec une migration incomplète. SQLite restaure la transaction non validée ; le journal confirme les opérations réellement commises. L'application ne doit jamais afficher un succès déduit seulement d'une mise à jour optimiste.

## Commandes et contrôles à exécuter aux jalons concernés

Toutes les commandes partent de la racine du dépôt. Les modules de tests, scripts et rapports portant 109 ci-dessous sont des **livrables futurs**, créés dans leurs sous-jalons respectifs. La préparation documentaire actuelle ne les exécute pas. Ne synchroniser les dépendances que si le verrouillage ou l'environnement change.

Contrôles de code et tests de base, après création des modules de 109.1 :

    uv run ruff check src/mtee/domain/genres.py src/mtee/persistence/genre_repository.py src/mtee/services/genre_service.py src/mtee/services/genre_seed_service.py scripts/seed_track_genres.py
    uv run ruff format --check src/mtee/domain/genres.py src/mtee/persistence/genre_repository.py src/mtee/services/genre_service.py src/mtee/services/genre_seed_service.py scripts/seed_track_genres.py
    uv run python -m pytest tests/unit/test_genres.py tests/unit/test_genre_seed_service.py tests/integration/test_genre_repository.py tests/integration/test_genre_seed.py tests/integration/test_database_migrations.py tests/integration/test_playback_repository.py

Pour l'aperçu sur une copie préparée en 109.1, remplacer le paramètre racine par l'UUID réellement lu et non par le nom du dossier. Le fichier `plan.json` est un livrable du mode preview :

    uv run python scripts/seed_track_genres.py --database .local/validation/109/data/mtee.sqlite3 --root-id <UUID_RACINE_VERIFIE> --preview --report-dir .local/validation/109/seed
    uv run python scripts/seed_track_genres.py --database .local/validation/109/data/mtee.sqlite3 --apply-plan .local/validation/109/seed/plan.json

L'application réelle utilise un **aperçu produit pour cette base réelle**, son chemin vérifié, son propre rapport et sa sauvegarde ; ne pas appliquer aveuglément un plan d'une autre base. L'outil de copie cohérente et le mode de restauration seront documentés avec leurs commandes réelles dans le rapport de 109.1. Les chemins personnels détaillés n'ont pas à être publiés dans Git.

Après 109.3 à 109.6, contrôles métier et UI :

    uv run python -m pytest tests/unit/test_genre_manager_model.py tests/unit/test_genre_tagging_model.py tests/unit/test_genre_filters.py tests/integration/test_genre_operations.py tests/integration/test_genre_filter_queries.py tests/unit/test_track_list_model.py tests/unit/test_folder_genres.py
    $env:QT_QPA_PLATFORM = 'offscreen'
    uv run python -m pytest tests/ui/test_genre_manager_ui.py tests/ui/test_genre_tagging_ui.py tests/ui/test_genre_filters_ui.py tests/ui/test_artist_profile_ui.py

Préserver puis restaurer la valeur précédente de `QT_QPA_PLATFORM` avant la recette interactive. Les tests UI construisent un runtime temporaire via `_build_runtime` et exécutent `_shutdown(runtime)` dans `finally`. Les essais utilisent de courts fichiers synthétiques ou des copies de fichiers autorisées, jamais des écritures sur la collection réelle. Compléter Ruff/format sur tous les nouveaux modules et les fichiers effectivement modifiés, puis Pyright selon la configuration du dépôt en distinguant les défauts préexistants.

Lancement et vérification manuelle depuis les sources, après préparation de la copie :

    uv run python -m mtee --data-dir .local/validation/109/data --smoke-test
    uv run python -m mtee --data-dir .local/validation/109/data

Un smoke-test et des captures hors écran ne remplacent pas les parcours interactifs. Si le contrôle manuel ne peut pas être exercé dans la session d'exécution, le noter comme non fait et fournir les étapes de reprise, sans annoncer la recette terminée. Ne pas lancer `scripts/build_windows.ps1` ni `scripts/smoke_packaged.ps1`.

Les suites existantes mentionnées comme défaillantes dans 108 ne sont pas une dispense de vérifier les régressions de ce changement. Comparer les seuls échecs pertinents à la même révision de référence dans un checkout isolé avec son propre environnement ; ne pas utiliser le `.venv` éditable du checkout principal ni `git stash`. Élargir les tests en fonction des composants effectivement touchés, sans relancer indéfiniment toute la suite si les contrôles pertinents passent.

## Recette observable obligatoire

| Cas | Résultat attendu |
|---|---|
| Amorcer le dossier Jump Up | Jump Up attribué, Drum & Bass déduit et affichable, aucun tag de fichier modifié |
| Amorcer House et les dossiers exclus | House seul pour House ; aucun genre pour chill&atmospheric/old school/zzZ/Artists/dj blc |
| Amorcer un dossier hybride | Tous les sous-genres prévus présents, un seul morceau dans les compteurs de famille |
| BPM 87, 159, 160, absent | Jungle, Breaks, Jungle, aucun genre ; aucune réécriture du BPM |
| Corriger puis relancer l'amorçage | La correction et les retraits manuels restent en place |
| Choisir un pinceau Deep | House › Deep distinct de Dubstep › Deep ; cases conformes aux données |
| Cocher/décocher puis scroll | Données persistantes, aucune lecture ni navigation automatique |
| Deep + Minimal puis retraits successifs | Minimal reste après retrait de Deep ; House seul après le dernier retrait |
| Créer un genre oublié | Parent visible, création immédiate, retour au pinceau sans perte de contexte |
| Appliquer à une sélection puis Ctrl+Z | Seules les cibles annoncées changent ; le lot entier est annulé |
| Speed Garage ET Bassline / OU | Respectivement intersection / union dans la liste courante |
| Sans pinceau OU sans sous-genre | Familles de base seules incluses ; aucun faux sous-genre implicite |
| Contexte Jump Up | Exclusion de Drum & Bass indisponible ; Jump Up compte comme sous-genre |
| Cocher avec filtre excluant le pinceau | Ligne retenue atténuée ; recalcul seulement sur action explicite ; file courante conservée |
| Deux onglets sur le même morceau | Genre actualisé dans les deux ; filtres et pinceaux propres à chacun |
| Erreur d'écriture / annulation concurrente | Pas de faux succès ni d'écrasement d'une action plus récente |
| Renommer/déplacer/archiver un genre | UUID et affectations conservés ; chemins affichés cohérents |
| Suppression forcée d'une famille | Sous-arbre et liens actifs supprimés ; autres genres et audio intacts ; récupération vérifiée |
| Filtre référençant un genre supprimé | Erreur explicite et possibilité de corriger le filtre ; aucun élargissement silencieux |
| Retrait du plan 107 | Genres traçables retirés ; tags manuels et masquage préservés ; ambiguïtés rapportées |
| Fermer et rouvrir MTEE | Taxonomie, affectations et filtres sauvegardés retrouvés |

## Documentation, commits et publication

À chaque sous-jalon exécuté, mettre à jour `Progress`, `Surprises & Discoveries`, `Decision Log` et `Outcomes & Retrospective`, puis le rapport de validation avec les commandes, résultats, écarts et limites réellement observés. Le rapport détaille séparément les sauvegardes locales, le lot appliqué sur copie, le lot appliqué sur base réelle et les contrôles interactifs. Les titres et captures d'exemple publiés utilisent des données fictives.

Inspecter l'état Git avant chaque commit, indexer explicitement seulement les fichiers du sous-jalon, exécuter `git diff --check`, relire `git diff --cached --check` et `git diff --cached`. Ne pas inclure `.agents/`, `.codex/`, `skills-lock.json`, `.local/` ni une base personnelle. Créer un commit détaillé qui explique le comportement livré, les contrôles et leurs limites, puis pousser vers `origin/main` si la branche et les règles distantes le permettent. Ne pas forcer de push.

Avant publication, `git fetch origin` puis comparer `HEAD...origin/main` ; traiter toute divergence sans écraser le travail d'autrui. Après push, fetch et comparaison de `HEAD` avec `origin/main`. Une publication non vérifiée reste non faite dans le compte rendu. La préparation documentaire reçoit son propre commit, sans prétendre avoir livré les fonctionnalités.

## Outcomes & Retrospective

2026-10-07 — Préparation documentaire : les deux lots et leurs critères sont définis ; les corrections finales remplacent les options contradictoires du brief 108. Le manager reste central, le pinceau est l'unique mode de tri spécifique retenu, les filtres supportent ET/OU/exclusion, et l'amorçage précis est une opération confirmée par lot. Les commandes futures et points d'intégration sont identifiés.

Développement, maquettes exécutables, revue visuelle, migrations, sauvegardes personnelles, association effective des genres, nettoyage artistes, recette applicative et packaging : **non réalisés par cette préparation**. Le [rapport documentaire](../docs/validation/109-genres-morceaux-manager-tri.md) consigne les contrôles du plan ; la preuve de publication du commit de préparation est fournie dans le compte rendu de la tâche, sans hash auto-référentiel dans ce fichier.


## Révision d’exécution du 7 octobre 2026 — 109.0

Demande utilisateur : « Exécute le plan 109 ». La mention de préparation seule en introduction décrit la demande historique ; cette révision commence son exécution.

Surprises & Discoveries : le répertoire proposé `src/mtee/qml/prototypes/` n’existait pas ; créé pour ce prototype. Les composants existants sont sous `qml/components/`, le thème sous `qml/Mtee/`. Le graphe consulté décrit une révision antérieure ; les chemins ont été vérifiés dans les sources. HEAD initial `2f46b789`, synchronisé avec origin/main après fetch.

Decision Log : Codex, 2026-10-07 — préparer uniquement les surfaces à données fictives avant la revue imposée. Réutiliser Theme, FilterChip et WheelScrollHandler ; lanceur autonome sans runtime applicatif, base ni lecteur audio. Les presets fixes de filtres illustrent les combinaisons avant leur éditeur générique. Ne pas interpréter la demande d’exécution comme un accord visuel absent.

Outcomes & Retrospective : prototype, captures et [dossier de revue](../docs/ux/review-109-genres.md) prêts ; 16 scènes chargées sans avertissement QML, contrôles Ruff propres et sondes d’interactions en mémoire réussies. Inspection visuelle des captures réalisée ; recette interactive native et accord utilisateur non réalisés. Les jalons 109.1–109.7 attendent cette revue. Aucun schéma, donnée personnelle ni audio modifié ; aucun packaging. La publication du sous-jalon est vérifiée et rapportée dans le compte rendu après push.


## Révision d’exécution du 8 octobre 2026 — 109.1 et 109.2

Surprises & Discoveries : les effectifs ont changé depuis le brief. Le lot réel corrigé porte sur 2 456 morceaux, 2 472 liens directs, 8 hybrides ; 358 présents restent sans genre, 2 absents sont ignorés. La règle donne 56 Jungle, 18 Breaks et un BPM manquant. Les rapports personnels sont conservés localement hors Git.

Decision Log : utilisateur — après examen du tableau réel, exclure « hard house - nu trance - bouncy stuff » et « techno, trance ». Ces deux dossiers (116 présents) sont exclus du mapping, sans retirer les définitions de taxonomie. Codex — appliquer ce tableau avec ces corrections après fermeture confirmée des deux outils utilisant la base ; copie cohérente vérifiée avant migration et amorçage réel.

Outcomes & Retrospective : migration 021, arbre initial, liens locaux distincts des métadonnées, aperçu reproductible, application atomique, marqueurs durables de corrections manuelles et annulation ciblée livrés. Base réelle rouverte : quick_check OK, aucune erreur de clés étrangères, liens et exclusions conformes. Comparaison avec sauvegarde : locations, analyses et revues artistes identiques. Les genres locaux apparaissent en lecture seule dans la liste et Info. Manager, pinceau, filtres et nettoyage 107 restent à réaliser. Contrôles et limites dans le rapport de validation.
