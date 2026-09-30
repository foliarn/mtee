# Étape 34 — Playlists locales fonctionnelles

ExecPlan vivant préparé le 2026-09-30. Appliquer `PLANS.md`, l'addendum playlists de `PLAN.md` et les décisions de `docs/decisions/34-playlists.md`. Cette demande explicite réactive les playlists locales après le socle existant, sans reprendre toute la trajectoire des anciens plans 10 et 14. Spotify, Shovel, les tags sémantiques et les vues intelligentes ne sont pas des travaux de ce plan. L'idée Spotify reste uniquement dans `docs/ideas/spotify-playlists.md`.

## Objectif et résultat observable

L'utilisateur crée, renomme, décrit, duplique et organise des playlists manuelles persistantes dans des dossiers imbriqués. Il épingle ses playlists et dispose d'une collection `Liked tracks` alimentée exclusivement par les likes MTEE. Les morceaux des dossiers audio peuvent être ajoutés par sélection et menu, bouton `+` ou glisser-déposer, sans doublon musical. Une réorganisation de playlist ne déplace jamais de fichier.

La page de playlist possède une grande pochette carrée, une image locale ou mosaïque par défaut, un grand titre, la description, le nom de créateur commun aux réglages et la durée sans taille en octets. Play/Shuffle se placent sous la pochette ; Search/List/Artwork/Choose columns sont alignés à droite. La recherche se déploie vers la gauche et conserve ses résultats lorsqu'elle est repliée. Le profil Title, Artist, Album, BPM, Key, Duration est commun aux playlists et indépendant des dossiers audio. Les pages de dossiers audio conservent leur en-tête actuel.

Play/Shuffle prennent un instantané des résultats visibles disponibles. Les absences restent grisées à leur position et se résolvent manuellement. L'utilisateur exporte un `.mteeplaylist` léger ou un ZIP avec l'audio, puis peut restaurer/transférer ces playlists, avec rapprochement automatique certain et choix explicite face aux ambiguïtés. L'import ZIP extrait dans une destination choisie, ajoute le dossier à la bibliothèque et recrée la playlist, sans écrasement.

## Progress

- [x] 2026-09-30 — Examiner les contrats existants et recueillir les sept séries de décisions utilisateur.
- [x] 2026-09-30 — Séparer l'idée Spotify des travaux prévus.
- [x] 2026-09-30 — Préparer une maquette QML isolée et ses scènes de revue.
- [x] 2026-09-30 — Captures produites, interactions vérifiées hors écran et en fenêtre Windows native ; preuves de prototype consignées.
- [x] 2026-09-30 — Revue 34.1 validée explicitement par l’utilisateur (« parfait »).
- [x] 2026-09-30 — Réaliser 34.2 : domaine, migration sauvegardée, dépôt, services et tests de persistance.
- [x] 2026-09-30 — Réaliser 34.3 : modèles Qt, sidebar, pages, likes, menus et intégration du lecteur.
- [x] 2026-09-30 — Réaliser 34.4 : échanges légers/ZIP, résolution, annulation et reprise.
- [x] 2026-09-30 — Réaliser 34.5 : recette depuis les sources et contrôles terminés ; commit/push en clôture de livraison, SHA et comparaison distante rapportés dans la conversation.

## Surprises & Discoveries

Le code vivant ne stocke pas de playlists : `WorkspaceModel.playlists` et `playlistsContaining` sont vides ; ouverture/création affichent un message de report et `togglePlaylist` ne fait rien. Seules les playlists de `DemoWorkspace` fonctionnent en mémoire. Il n'existe donc pas de playlist réelle fictivement « migrée » depuis la démo.

Le schéma livré est 15. `Database.migrate` sauvegarde déjà une base existante et applique les migrations transactionnellement. Les fichiers de migration, les tests et le numéro libre devront être revérifiés avant 34.2. `TrackListModel` indexe ses lignes par `id` : plusieurs absences avec `id` vide seraient fusionnées ; le modèle de playlist doit séparer identifiant d'entrée et identifiant de morceau.

La capture hors écran sous Windows ne trouve pas les polices système : le lanceur de revue charge le fallback Segoe UI existant lorsque nécessaire. Ce correctif est limité au lanceur documentaire, sans changement de police ou de runtime de l'application. Aucun fichier utilisateur ni base personnelle ne sont ouverts par la maquette.

## Decision Log

2026-09-30 — Utilisateur — Spotify reporté à une autre fois, idée conservée dans un `.md`, exclue du plan à réaliser. Le Client ID est déclaré configuré mais n'est pas lu ni versionné.

2026-09-30 — Utilisateur — Likes locaux, créateur commun dans les réglages, ordre manuel par défaut, tris possibles, lecture limitée aux résultats visibles ; dossiers imbriqués et épingles, ajout par menu/glisser-déposer/`+`, cœur séparé.

2026-09-30 — Utilisateur — Image locale, mosaïque par défaut, exports léger et ZIP avec audio, import ZIP vers un dossier choisi et ajouté à la bibliothèque ; association automatique certaine et choix en cas d'ambiguïté ; lignes grisées pour les absences.

2026-09-30 — Utilisateur — Pas de doublon musical d'après titre/artistes/version normalisés ; distinguer remix/live/original ; demander un choix lorsque les informations sont insuffisantes. Chaque clic du menu ajoute/retire immédiatement et le menu reste ouvert. Duplication autorisée, confirmation avant suppression de playlist et dossiers supprimables seulement lorsqu'entièrement vides.

2026-09-30 — Codex — Réutiliser les modèles/services natifs, isoler le profil de colonnes de playlists, garder l'instantané du lecteur et ne pas anticiper de schéma Spotify. Les détails techniques et propositions de présentation sont identifiés dans la note de décisions et dans la revue, sans les présenter comme réponses utilisateur.

## Outcomes & Retrospective

La maquette a été approuvée (« parfait »). Les playlists locales fonctionnelles, la migration 16 sauvegardée, les likes, les dossiers et les échanges MTEE/ZIP sont implémentés. Les contrôles depuis les sources et les captures natives sont consignés dans `docs/validation/34-playlists-locales.md`. La recette est automatisée sur fixtures isolées ; elle ne constitue pas une écoute humaine ni une validation de distribution Windows. Les erreurs des contrôles globaux antérieures à cette étape sont documentées séparément.

## Contexte et prérequis

MTEE est une application Windows locale Python 3.12/PySide6/QML/SQLite. La demande utilisateur suffit à réactiver ce périmètre local ; elle ne valide pas la taxonomie du plan 10 ni les autres fonctions suspendues. La palette Acid, les surfaces et icônes sont définies dans `src/mtee/qml/Mtee/` et `docs/ux/specification.md`. La revue du nouvel en-tête précède le code fonctionnel conformément à `PLAN.md`.

Réutiliser `LibraryRepository`, les UUID `track_id`, `Database`, `JobService`, `FileAccessCoordinator`, `WorkspaceRepository`, l'éditeur à onglets et `PlayerService`. Les analyses et métadonnées restent indépendantes. QML n'accède ni aux fichiers, ni au réseau, ni aux commandes système ; il appelle des modèles/services Python. Les scans, hachages, copies, images, import/export et chargements importants quittent le thread graphique. Les modèles Qt sont actualisés dans ce thread via messages/signaux, avec génération des requêtes et rejet des résultats périmés.

Relire les implémentations et tests pertinents après les recherches de graphe. Le dossier peut contenir du travail utilisateur non committé : n'indexer que les fichiers de cette livraison. Aucun build Windows n'est prévu ou déclenché automatiquement.

## Plan de travail et jalons

### Jalon 34.1 — Revue concrète de l'interface

La maquette indépendante se trouve dans `docs/ux/mockups/PlaylistReview.qml`, lancée par `review_playlists.py`. Ses données sont inventées et ses actions sont locales à la mémoire. Elle réutilise Theme, CoverArt, KeyBadge et le fournisseur d'icônes de MTEE. Les scènes couvrent playlist, recherche, menu d'ajout, colonnes, vide, fenêtre étroite, Artwork, likes, menu de création, export, import et localisation d'une absence.

Capturer les scènes, inspecter les dimensions et commandes, exercer la recherche, lecture fictive des résultats, coches sans fermeture et likes. Préparer `docs/ux/review-playlists-2026-09-30.md` avec captures et limites. Présenter le résultat et obtenir une réponse explicite avant 34.2/34.3. Mettre à jour le dossier après toute correction exigée. La validation de la maquette ne transforme pas ses actions simulées en fonctionnalités livrées.

### Jalon 34.2 — Domaine et persistance

Créer `src/mtee/domain/playlists.py`, `persistence/playlists_repository.py`, `services/playlist_service.py` et la prochaine migration libre, attendue `016_playlists.sql`. Le schéma porte les playlists, les dossiers virtuels parents, leurs ordres, les épingles, les entrées et les likes. Le nom de créateur est un réglage commun, pas un tag du fichier. Chaque playlist/dossier/entrée possède un UUID stable ; une entrée garde un ordinal, un `track_id` local éventuellement absent et un snapshot utile pour rendre/exporter une absence. Aucune suppression de catalogue ne doit effacer silencieusement les entrées.

Contraindre l'unicité d'un même `track_id` non nul dans une playlist et contrôler les doublons musicaux dans le service à partir des métadonnées courantes. Normaliser Unicode/casse/accents et artistes, conserver les distinctions de version. Une ressemblance ou une métadonnée manquante n'est pas une preuve audio : produire un aperçu d'ambiguïté et attendre le choix explicite. Ne jamais supprimer rétroactivement des entrées lorsque leurs tags changent ; signaler le conflit pour les futurs ajouts. Les likes sont un choix local persisté, sans lien Spotify.

Créer, renommer, dupliquer, épingler, déplacer, supprimer et réordonner dans des transactions. La duplication crée de nouveaux UUID d'entrées et copie l'ordre, la description et la couverture ; elle ne copie pas l'audio. Prévenir les cycles et refuser la suppression d'un dossier avec enfants ou playlists, y compris sous-dossier vide. La suppression confirmée d'une playlist ne touche que les données de playlist et ses ressources dérivées inutilisées. Vérifier la version de playlist/dossier avant d'appliquer un aperçu devenu périmé. Les réordonnancements évitent les collisions d'ordinals pendant la transaction. Une erreur laisse l'ordre et les coches à l'état réellement persisté.

Créer les tests de domaine et de dépôt dans `tests/unit/test_playlist_identity.py`, `test_playlist_order.py`, `tests/integration/test_playlists_repository.py` et compléter `test_database_migrations.py`. Exercer l'upgrade d'une copie v15 avec données/analyses/tags inconnus conservés, sauvegarde cohérente, réexécution et rollback d'une migration injectée en échec. Ne pas modifier le SQL déjà publié.

### Jalon 34.3 — Modèles Qt et intégration QML

Créer un modèle Qt d'arbre et un modèle d'entrées sous `src/mtee/models/`. Une entrée de playlist est sélectionnée/réordonnée par `entry_id` ; la lecture reçoit seulement les UUID locaux jouables. Plusieurs lignes sans correspondance restent distinctes et visibles. Les onglets sauvegardent filtre, tri temporaire, vue et position ; les requêtes lentes sont annulables et ne réintroduisent pas de données périmées après fermeture d'un onglet.

Brancher `WorkspaceModel`, le runtime dans `app.py`, `PlaylistsPane.qml`, `AddToPlaylistMenu.qml`, `TrackContextMenu.qml`, les commandes de lignes/Artwork et le nouvel en-tête/page de playlist. Ajouter le cœur dans les vues qui montrent des morceaux, avec état partagé, et garder `+` distinct. Les menus de multisélection montrent appartenance complète/partielle : clic sur complet retire la sélection, clic sur partiel ajoute uniquement les absents. La recherche du menu conserve l'accès à New playlist et aux chemins de dossiers pour distinguer les noms identiques. Les coches reflètent le résultat d'écriture, le menu reste ouvert après chaque action. `Close` ne revient pas sur ces changements.

La sidebar propose New playlist, New folder et Import playlist ; aucun bouton Spotify. Glisser-déposer interne déplace les playlists/dossiers ou ajoute les morceaux, jamais les sources audio. Le réordonnancement de morceaux se fait en Custom order sans filtre ; en vue triée/filtrée, proposer le retour à cette vue. Prévoir équivalent clavier pour déplacer et commandes de menus accessibles, restauration du focus, noms longs, arbre replié et menu près des bords.

Le profil de colonnes de playlists est mémorisé séparément du profil de dossiers. Les absences sont rendues grisées avec `Locate file`, conservant titre, artiste et durée connue. L'en-tête montre total des entrées, durées connues et compteur d'indisponibles. `Liked tracks` est une vue système alimentée par les likes, placée avant les épingles ; les épingles et l'arbre ordinaire ont des ordres persistants. Le nom de créateur se règle dans General et met à jour les pages sans écrire de métadonnées audio.

Copier les couvertures choisies dans le répertoire de données applicatives après validation/décodage, stocker une référence relative opaque et fournir l'image via le service/cache d'artwork. Une mosaïque des premières pochettes disponibles est le défaut ; une absence de pochettes conserve un placeholder. Un déplacement ou une suppression de l'image d'origine ne casse pas la couverture copiée.

Exercer les widgets et les contrats du lecteur : Play/Shuffle sautent les absences et ne jouent que les résultats visibles ; changer de filtre, tri ou ordre n'altère pas la file en cours. Les menus, métadonnées, analyses, Info/Queue, dossiers audio et groupes divisés restent utilisables. Ajouter `tests/ui/test_playlists_ui.py` et tests d'intégration de persistance/rechargement ; les données restent des copies/fixtures.

### Jalon 34.4 — Import/export portable et complet

Créer `domain/playlist_exchange.py` et `services/playlist_exchange.py`, un parseur strict et des fixtures versionnées. `.mteeplaylist` est un JSON UTF-8 avec identifiant de format, version, nom, description, ordre, snapshot des morceaux, couverture encodée et références de rapprochement ; il ne contient pas l'audio ni de chemins absolus personnels par défaut. Un UUID exporté n'est pas reconnu aveuglément dans une autre installation. Calculer les empreintes SHA-256 hors du thread UI sous lease de lecture, avec révision de source contrôlée avant/après ; les empreintes identifient un fichier pour le rapprochement, pas un morceau musical ni un `track_id`.

Importer en construisant un aperçu : correspondance locale certaine (identité locale vérifiée ou empreinte exacte), candidats ambigus, absence. Les métadonnées et durées proposent des candidats, sans confondre formats/version ou associer un homonyme. Le choix explicite lie l'entrée ; les absences restent en place. Un réimport crée une playlist locale distincte plutôt que d'écraser une playlist existante. Les noms de playlists identiques sont distingués par leur dossier et peuvent être renommés sans changer d'identité.

Le ZIP contient un manifeste `.mteeplaylist`, sa couverture et les copies des fichiers disponibles, avec chemins internes uniques même pour deux noms de fichier identiques. Afficher les éléments indisponibles et conserver leurs entrées dans le manifeste ; ne pas annoncer un export complet de l'audio absent. Vérifier la révision/source pendant la copie, publier le ZIP final atomiquement sans écraser une destination existante et laisser une progression/annulation/erreur lisibles dans Tasks.

Valider les archives avant extraction : refuser chemins absolus/UNC, remontées `..`, liens, noms Windows réservés/ADS et collisions après normalisation. Borner nombre/taille totale/taille de couverture et décompression, avec messages explicites ; les seuils sont des choix techniques à documenter. Extraire dans un sous-dossier neuf de la destination choisie, sans écrasement. Scanner/ajouter ce dossier via le service de bibliothèque, résoudre les références puis persister la playlist transactionnellement. Conserver la trace des étapes et expliquer un échec partiel ; ne pas annoncer de playlist restaurée avant la validation finale. Une reprise ou un nettoyage ne touche que les fichiers appartenant à l'opération et inchangés depuis celle-ci, jamais un fichier utilisateur modifié extérieurement.

Créer `tests/integration/test_playlist_exchange.py`, des fixtures synthétiques et des tests de services sur copies : échange entre deux bases dont les chemins racines et UUID diffèrent, mêmes fichiers identifiés, ambiguité, hash périmé, format inconnu, ZIP malformé, traversal, collisions de noms, annulation, interruption, disque indisponible et sources inchangées. Les tests démontrent réellement le no-clobber et la conservation des tags/pochettes, sans réencoder l'audio.

### Jalon 34.5 — Recette et livraison

Avec un répertoire isolé et des copies audio, créer plusieurs playlists et niveaux de dossiers, dupliquer, épingler, ajouter/retirer par toutes les commandes, liker, réordonner et redémarrer. Vérifier la durée, les profils de colonnes, le créateur commun et la couverture locale/mosaïque. Tester un original, le même morceau dans un autre format, un remix et des informations insuffisantes. Filtrer puis lancer Play/Shuffle, changer le tri pendant la lecture et vérifier l'instantané.

Déconnecter/déplacer une copie, vérifier sa ligne grisée et la résolution. Exporter/importer les deux formats, restaurer dans une seconde base et contrôler les mêmes fichiers, les absences, les ambiguïtés et les collisions sans écrasement. Refuser la suppression d'un dossier non vide et confirmer celle d'une playlist en constatant la conservation des fichiers audio. Tester fenêtres large/étroite, arbre long, menu près des bords et groupes divisés, avec listes virtualisées. La cible de 10 000 entrées est un contrôle de charge à mesurer, pas une performance déjà démontrée.

Actualiser décisions, spécification, ExecPlan et `docs/validation/34-playlists-locales.md`. Exécuter les contrôles concernés ; examiner le diff et indexer explicitement les seuls fichiers de l'étape. Commit détaillé puis push séquentiel vers origin sans réécriture ; confirmer HEAD == origin/main après fetch. Ne pas lancer le packaging Windows.

## Commandes et résultats attendus

Depuis la racine, les commandes de maquette existent dès 34.1 :

    uv run python docs/ux/mockups/review_playlists.py
    uv run python docs/ux/mockups/review_playlists.py --capture
    uv run python docs/ux/mockups/review_playlists.py --verify-interactions
    uv run python docs/ux/mockups/review_playlists.py --native --verify-interactions

La première ouvre une fenêtre interactive sans base ni fichier audio. Les captures sont écrites sous `docs/ux/playlists-2026-09-30/`. Les vérifications simulent seulement les contrats UI et échouent sur avertissement QML. Le mode natif utilise la plateforme Windows réelle, sans valider le backend ou une distribution.

Après création des modules/tests aux jalons indiqués, exécuter :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_playlist_identity.py tests/integration/test_playlists_repository.py tests/integration/test_database_migrations.py tests/integration/test_playlist_exchange.py tests/ui/test_playlists_ui.py
    uv run python -m mtee --data-dir .local/validation/34-playlists-functional --smoke-test
    uv run python -m mtee --data-dir .local/validation/34-playlists

Les futurs tests ne sont pas présentés comme existants avant leur création. Ajuster les chemins de modules/tests au code réel et consigner les adaptations. La dernière commande sert au parcours manuel avec données de test ; le smoke-test n'en tient pas lieu. Ajouter les tests de non-régression des modules touchés selon les changements, sans répétition systématique après des résultats inchangés.

## Validation, reprise et limites

L'acceptation exige maquette approuvée, persistance au redémarrage, identité/order sans perte, fonctions visibles réellement branchées, écriture sur copies, import/export reproductibles et erreurs lisibles. Une absence de réponse à la revue suspend le backend au jalon 34.1 et laisse le dossier prêt. Une migration/applicative/échange en échec conserve l'état précédent ou expose précisément la partie achevée ; ne jamais substituer une suppression permanente de source à une opération indisponible.

Le prototype ne teste ni le son, ni les migrations, ni les exports, ni le drag-and-drop réel. La recette native de l'application fonctionnelle reste à effectuer après implémentation. Aucun EXE n'est construit/validé sans demande explicite de distribution. Note de révision du 2026-09-30 : plan initial établi à partir des décisions de cadrage, périmètre local et dossier de revue distincts de l'intégration différée.

## Résultats de réalisation du 2026-09-30

Migration `016_playlists.sql` : ajout de tables sans transformation des tags/analyses existants, backup exact du schéma 15 et application idempotente vérifiés. Les UUID d’entrées restent distincts des morceaux locaux. Toutes les opérations du gateway Qt passent par une file FIFO de jobs ; la fermeture vide les petites écritures et annule les transferts avec journal de reprise.

La vue réutilise les composants/jetons MTEE et possède un profil de colonnes séparé. Le pooling des délégués est désactivé pour les playlists après observation d’un délégué conservant un ancien modèle ; la virtualisation reste active. La recette native force le layout Qt après le changement de filtre avant de simuler un drag. Les autres vues conservent leur comportement de réutilisation.

Le format léger version 1 est un manifeste UTF-8 avec couverture et SHA-256, sans chemins absolus. Le ZIP contient `playlist.mteeplaylist` et les sources exactes sous `audio/`. Seuils : manifeste 20 Mo, couverture importée 5 Mo, 100 000 entrées, archive 20 Go décompressés. Publication par création atomique sans remplacement ; reprise vérifiant les empreintes de fichiers déjà extraits avant toute continuation. Les candidats sur métadonnées seuls demandent un choix.

35 tests ciblés (34 backend/persistance/non-régression et 1 parcours UI), recette Windows native et smoke-test depuis les sources terminés. Pyright ciblé est vert ; le contrôle global présente 34 erreurs contre 38 sur HEAD initial, sans nouveau diagnostic. Ruff ciblé est vert hors anciennes lignes de LibraryRepository ; Ruff global et format global ne sont pas verts avant cette étape. Deux anciens tests workspace/player échouent également sur un checkout isolé de HEAD initial ; aucun résultat global propre n’est revendiqué.

Charge synthétique de 10 000 entrées absentes : création 0,162 s, lecture 0,051 s, remplacement du modèle Qt 0,026 s. Ce test ne mesure ni les accès à 10 000 fichiers réels ni le rendu complet sur toutes les machines. Packaging non lancé. Spotify reste exclu.
