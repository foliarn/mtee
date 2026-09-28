# 25 — Explorer : sélection, activation et stabilité de l’arbre

## Résultat attendu et prérequis

Un double-clic sur un morceau de l’arbre ouvre son dossier dans le groupe actif, sélectionne réellement le morceau, rend sa ligne centrale visible et lance sa lecture. Exception validée : si la recherche masque ce morceau, elle reste intacte et le morceau joue sans être révélé. Ouvrir, replier ou cliquer un dossier ne ramène plus l’arbre en haut. Lire les plans 23, 24 et 19. Le contrat de lancement du plan 24 doit être vérifié avant la recette de bout en bout.

## Sources à lire et état actuel

Lire `src/mtee/qml/components/ExplorerPane.qml`, `TrackListView.qml`, `EditorGroup.qml` et `EditorArea.qml`, puis `src/mtee/models/workspace_model.py`, `folder_tree_model.py` et `track_list_model.py`. Lire `tests/unit/test_workspace_model.py`, `tests/unit/test_track_list_model.py` et `tests/ui/test_incremental_scan_and_scroll.py`.

Dans `ExplorerPane.qml`, le clic simple sur un fichier appelle `openFolder` et `selectTrack`. Le double-clic traite uniquement les dossiers. L’activation explicite d’un fichier manque donc dans ce gestionnaire. La sélection seule ne commande pas à la liste centrale de révéler une ligne hors écran.

`FolderTreeModel` maintient un arbre aplati avec des identités stables. `_replace()` ajoute actuellement les nouvelles lignes à la fin avant de les réordonner via des signaux de layout. Le saut visuel peut venir de cette séquence, du `currentIndex` de la vue ou d’une recréation du composant. Ce sont des hypothèses à isoler avec une reproduction ; ne pas remplacer aveuglément tout le modèle.

## Jalon 25.1 — Conserver le point de navigation

Créer une fixture de trois branches avec assez de sous-dossiers pour dépasser la hauteur de la sidebar. Ouvrir les deux premières, descendre et ouvrir la troisième à une position intermédiaire. Mesurer l’identité de la ligne cliquée et sa coordonnée verticale avant et après l’insertion des enfants, puis au retour du worker. Refaire avec un simple clic sur le libellé et avec un repli.

L’ancre est un identifiant de ligne et son décalage dans la fenêtre visible. Lors d’un clic, privilégier la ligne cliquée ; pour un rafraîchissement extérieur, garder la première ligne visible et son décalage. La restitution utilise les nouvelles coordonnées du modèle après insertion. Une borne en début/fin de contenu peut limiter la restitution ; cela doit être distingué d’un saut intempestif. Si l’ancre disparaît lors d’un repli, garder le parent visible.

Favoriser des insertions/suppressions à leur emplacement réel lorsque la structure le permet. Si une réorganisation complète reste nécessaire, conserver les index persistants et l’ancre de la vue. Ne pas appeler `positionViewAtBeginning()` ou recentrer sur la racine à chaque changement. Vérifier aussi que les signaux généraux du workspace ne recréent pas inutilement la sidebar.

Ajouter les cas de modèle à un nouveau `tests/unit/test_folder_tree_model.py`, créé dans ce jalon, et les interactions à `tests/ui/test_incremental_scan_and_scroll.py`. Les tests doivent observer les identités et les coordonnées de vrais éléments Qt Quick, pas rechercher une chaîne dans le code QML.

## Jalon 25.2 — Révéler puis activer le morceau voulu

Définir une action de modèle unique de type « révéler ce morceau dans son dossier, avec intention de lecture ». Le nom exact est à choisir dans `WorkspaceModel`. Elle s’appuie sur les UUID et les modèles chargés, pas sur un index capturé avant le scan.

Séquence : activer le bon groupe, ouvrir ou réutiliser l’onglet du dossier parent, demander son modèle de lignes, sélectionner uniquement l’UUID cible, révéler sa ligne avec le déplacement minimal nécessaire, puis lancer une fois le morceau depuis l’ordre effectif du listing. Si le modèle est asynchrone, conserver une demande avec groupe, onglet, UUID et génération ; la réaliser seulement lorsque la ligne cible existe. Une navigation ultérieure invalide cette demande. Ne pas ajouter une lecture SQLite synchrone dans QML ou dans un getter pour contourner cette attente.

Le simple clic reste sans lecture. Le double-clic comprend les événements de clic émis par Qt : garantir qu’il ne crée ni deux chargements natifs ni deux onglets. Le nom coloré du morceau en lecture ne suffit pas : `selectedIds` et le panneau Info doivent refléter la cible. Un changement de lecture seul n’impose pas de changer la sélection dans d’autres parcours.

Cas d’une recherche qui masque la cible : décision utilisateur du 28 septembre 2026, conserver le texte et les résultats filtrés et jouer sans révéler. Ne pas vider ni suspendre la recherche, ne pas ajouter une ligne hors filtre et ne pas provoquer de défilement. Garder la sélection visible actuelle pour éviter de cibler silencieusement un morceau caché lors d’une opération de métadonnées ; le morceau joué est annoncé par l’îlot/Fullscreen player et son état dans l’arbre. Ce maintien de sélection est un choix de conception pour cette exception. Le clic simple précédant le double-clic ne doit pas laisser une sélection cachée : traiter la visibilité dès ce chemin.

Quand la cible est exclue du listing, fournir au lecteur un snapshot contenant réellement ses données. Choix de conception : lancer une file d’un seul morceau pour cette activation exceptionnelle, plutôt qu’une suite implicite de résultats filtrés qui n’incluent pas la cible. Conserver le parcours asynchrone et les générations. Tester que l’absence dans le modèle visible ne devient ni une erreur « fichier introuvable » ni une boucle d’attente pour sa révélation.

En double groupe, agir seulement dans le groupe actif. En grille Artwork, révéler et sélectionner la tuile correspondante lorsqu’elle passe le filtre. Si le fichier a disparu, afficher l’erreur habituelle et ne pas publier une lecture réussie. Pour une cible visible, une seule file est capturée dans l’ordre courant ; les tris suivants n’en changent pas rétroactivement l’ordre.

## Recette et commandes

Les fichiers mentionnés ci-dessous existent, sauf `test_folder_tree_model.py`, à créer au jalon 25.1. Depuis la racine :

    uv run pytest tests/unit/test_folder_tree_model.py tests/unit/test_track_list_model.py tests/unit/test_workspace_model.py
    uv run pytest tests/ui/test_incremental_scan_and_scroll.py tests/ui/test_player_views.py

Ajouter au second fichier UI un scénario de double-clic arbre → listing → lecteur, ou créer un test UI dédié si cela rend le scénario plus lisible. Tester une cible hors écran, un dossier non encore chargé, un dossier déjà actif, une grille et deux groupes. Vérifier une seule activation, le bon UUID, sa visibilité et la progression du lecteur. Pour une cible masquée, vérifier au contraire le texte et les résultats inchangés, aucune révélation, la sélection visible préservée et la lecture effective de la cible dans une file d’un morceau.

Pour l’arbre, la coordonnée de l’ancre doit rester identique à un pixel logique près en dehors d’une contrainte de bord. Cette tolérance est un critère de recette proposé, pas une mesure déjà obtenue. Répéter à cache froid puis chaud et pendant un rafraîchissement du catalogue. Les opérations de dépliage ne doivent ni couper la lecture ni lancer un autre morceau.

Clore avec le parcours manuel et la distribution du plan 23, puis `docs/validation/ux-ui-25.md`.

## Livraison et reprise

Deux commits intermédiaires possibles : stabilité de l’arbre, puis révélation/activation. Sujet final proposé : `fix(explorer): preserve tree position and reveal activated tracks`. Conserver les changements 24 et les états persistés. En cas d’interruption, noter si la demande différée d’activation existe déjà, ses conditions d’annulation et les tests restant à exercer.

## Progress

- [x] 2026-09-28 — Parcours et modèle d’arbre inspectés pour planification.
- [x] 2026-09-28 — Le modèle insère/déplace les lignes à leur position effective et conserve les index persistants ; l’Explorateur restaure l’ancre par identité et décalage.
- [x] 2026-09-28 — Clic et activation de piste passent par l’état asynchrone du modèle de l’onglet ; génération et navigation invalident les réponses périmées.
- [x] 2026-09-28 — Exception de recherche masquant la cible précisée par l’utilisateur et intégrée.
- [x] 2026-09-28 — Compilation Python/QML et distribution Windows vérifiées ; rapport créé.
- [ ] Tests pytest et recette interactive Explorer laissés à l’utilisateur ; commit et push à clôturer.

## Surprises & Discoveries

2026-09-28 — Le commentaire du composant annonce déjà « double click plays it », mais le gestionnaire ne le fait pas pour les fichiers. L’état de sélection existe déjà ; il faut relier l’intention de navigation à la vue, pas créer une seconde sélection.

2026-09-28 — La séquence d’insertion en fin de modèle suivie de `layoutChanged` était présente dans `_replace()`. Elle a été remplacée par des insertions et déplacements d’index réels. Le saut n’a pas été reproduit manuellement pendant ce jalon.

## Decision Log

2026-09-28 — Codex : séparer l’ancre stable de l’arbre et le défilement intentionnel du listing. Conserver l’identité par UUID à travers les mises à jour asynchrones. Utilisateur : jouer une cible filtrée sans la révéler ni effacer la recherche. Codex : dans cette exception, préserver la sélection visible et capturer une file d’un seul morceau.

2026-09-28 — Codex : la sélection d’un clic simple n’est appliquée qu’après confirmation de la présence dans les lignes filtrées. Une activation masquée récupère le snapshot en worker, vérifie le dossier et le fichier source, puis joue une file d’un morceau.

## Outcomes & Retrospective

Le correctif et le build Windows sont réalisés. Compilation Python, chargement QML en mode démo, lint/formatage et vérification de l’EXE ont réussi. Les tests pytest et la recette Explorer interactive n’ont pas été exécutés à la demande de l’utilisateur ; voir `docs/validation/ux-ui-25.md`. Révision du 28 septembre 2026 : exécution du lot Explorer.
