# 99 — File d'attente, commandes de lecture, navigation et désélection

## Statut et résultat attendu

Ce plan prépare uniquement les features **9 à 13** de la sous-page Notion Segmentation. Il est destiné à une exécution ultérieure par Luna. Sa préparation n'autorise pas son implémentation. Les décisions produit validées ci-dessous priment sur les interprétations de la segmentation. Les deux séries de réponses utilisateur ont été intégrées ; la revue de maquette est un jalon de l'exécution future.

Le résultat attendu est une file modifiable et persistante, l'ajout FIFO par clic droit, une commande Espace fiable hors saisie, une navigation arrière/avant par les boutons latéraux de souris, un Précédent cohérent autour de trois secondes et la désélection par clic dans le vide du panneau actif.

Sources lues le 1er octobre 2026 : [MTEE — fixes & idées](https://www.notion.so/3e5d502f2cc0804da316d980908fd518), [Segmentation](https://www.notion.so/3ebd502f2cc0819bb756ce582ee4fc4c), `PLAN.md`, `PLANS.md` et les sources du dépôt au commit `eabb253ba9391982df58357aa364422ccd196866`. Les réponses utilisateur sont transcrites dans ce document pour permettre l'exécution sans historique du chat ni accès à Notion.

## Périmètre confirmé par l'utilisateur

| Feature | Contrat confirmé le 2026-10-01 |
|---|---|
| 9 — File d'attente | Ajouter via clic droit, libellé anglais `Add to queue`. Plusieurs morceaux et une playlist entière peuvent être ajoutés. Ajouts FIFO, doublons autorisés, reprise de la suite après les insertions. Les ajouts manuels en attente survivent au lancement d'un autre morceau, dossier ou playlist. Restaurer file, morceau courant et position en pause. Réordonner les morceaux à venir par glisser-déposer ; retirer par clic droit `Remove from queue`. Aucune commande pour vider la file. |
| 10 — Espace | Pause/reprise partout dans MTEE sauf pendant l'écriture, avec la fenêtre active. |
| 11 — Souris | Les boutons latéraux servent à la navigation arrière/avant entre toutes les pages existantes, avec un historique propre à chaque panneau et restitution de la recherche, du défilement et de la sélection. Ils ne sont pas des commandes de changement de morceau. |
| 12 — Précédent | Position strictement inférieure à 3 secondes : morceau précédent. À partir de 3 secondes : début du morceau courant. Même décision en pause, avec démarrage immédiat de la lecture. Sans précédent : début du morceau courant en Repeat off/one ; dernière piste de la liste en Repeat all. Toutes les commandes Précédent partagent cette règle. |
| 13 — Désélection | Clic dans le fond et les zones vides, y compris la sidebar. Désélection limitée au panneau actif en vue divisée. Info n'affiche rien après désélection. |

L'utilisateur demande un seul plan portant le numéro 99 dans `Plans d'exécution/`. Ne pas confondre ces numéros de features avec les anciens ExecPlans 09 à 13 : analyse, tags, édition audio, Rekordbox et ML ne sont pas activés ici. Les features Notion 1 à 8 et 14 à 20 restent hors de ce travail. En particulier, ce plan ne crée pas de contrôles multimédias Windows, de raccourci système global, d'intégration musicale ou de nouvelle page Tasks.

## Précisions confirmées et exemples normatifs

Les quatre réponses complémentaires ont été reçues le 2026-10-01. Les numéros ci-dessous servent de références dans les jalons ; ils ne sont plus des questions ouvertes.

| Référence | Décision utilisateur |
|---|---|
| Q1 | Si 1 joue dans `[1, 2, 3, 4, 5]`, ajouter 9 puis 8 produit `[1, 9, 8, 2, 3, 4, 5]`. Les ajouts manuels encore en attente sont conservés même si l'utilisateur clique un autre morceau, dans le même contexte ou ailleurs. |
| Q2 | Shuffle conserve l'ordre des ajouts manuels. Repeat one boucle sur le morceau actif et ne consomme pas automatiquement les ajouts en attente. Sans précédent : Repeat all revient à la dernière piste ; Repeat one revient au début de la piste courante. |
| Q3 | Restaurer aussi le morceau courant et sa position, en pause. Le réordonnancement concerne les sons de la file, par drag-and-drop entre eux ; le retrait se fait par clic droit sur le son. Les contrôles couvrent donc la liste à venir, ajouts et suite du contexte. |
| Q4 | Historique propre à chaque panneau ; toutes les pages ; restitution de la recherche, du défilement et de la sélection. |

Exemple de changement de contexte : 1 joue, 9 et 8 attendent ; lancer explicitement B dans `[A, B, C]` donne B courant, puis `[9, 8, C]`. Cliquer une piste dont le `track_id` existe aussi parmi les ajouts ne supprime pas ces occurrences : les doublons sont autorisés. Les simples changements de page, filtre ou tri ne changent jamais la file déjà capturée.

Exemple de répétition : en Repeat one, 1 finit puis recommence, tandis que 9 et 8 restent en attente. Désactiver Repeat one permet ensuite la consommation de 9 puis 8. La commande explicite Next garde son rôle existant de passage au suivant ; la règle Repeat one concerne la fin naturelle d'un morceau. Précédent applique le seuil avant d'examiner le cas de bord de boucle.

Le drag-and-drop est une intention explicite qui remplace l'ordre des occurrences déplacées. FIFO définit l'ordre des ajouts tant qu'ils n'ont pas été réordonnés volontairement ; il ne doit pas annuler un déplacement réalisé par l'utilisateur.

## Préparation et état du dépôt

Lire ce plan entièrement, puis `AGENTS.md`, `PLANS.md` et les addenda applicables de `PLAN.md`. Pour les contrats existants, lire les plans `18-stabilisation-lot-02-jobs-lecteur.md`, `24-ux-ui-lecteur.md`, `25-ux-ui-explorer.md` et `34-playlists-locales.md` dans le présent dossier. Leurs anciennes commandes de build ne sont pas des étapes de ce plan : `PLANS.md` interdit le build automatique sans demande explicite de packaging.

Lors de la préparation, la branche est `main`, synchronisée avec la référence locale `origin/main`. `.gitignore`, `AGENTS.md`, `.agents/`, `.codex/` et `skills-lock.json` portent déjà du travail extérieur à cette demande. Ne pas les indexer ou les réécrire pour livrer 99. Réinspecter Git à l'exécution, car le dépôt peut avoir évolué.

Commencer l'exploration par le graphe code-review-graph, mettre son index à jour si son SHA diffère de HEAD, puis lire les sources et tests exacts. Le graphe a été actualisé pendant la préparation et graphify a servi à repérer les modèles de lecture et de sélection. Ni les relations du graphe ni les commentaires des fichiers ne prouvent à eux seuls un comportement.

### Sources existantes vérifiées

| Fichier | Fait observé et rôle dans ce plan |
|---|---|
| `src/mtee/services/player_service.py` | `play_queue()` capture l'ordre, `_base_ids` sert à désactiver Shuffle, `_open_index()` charge les pistes, `previous()` recule sans seuil, `_on_eof()` applique Repeat. Aucun contrat d'ajout/retrait/réordonnancement persistant n'est exposé. |
| `src/mtee/domain/playback.py` | `PlaybackState.track_ids` contient des identifiants de morceaux, avec index courant, position en microsecondes, repeat, shuffle et historique. |
| `src/mtee/models/player_model.py` | Façade Qt commune au lecteur, à la file et au plein écran. Les slots de transport délèguent au service. |
| `src/mtee/models/playback_queue_model.py` | Modèle Qt des lignes de file ; `refresh()` utilise `queue_rows()`. Les lignes n'ont pas d'identifiant propre d'occurrence. |
| `src/mtee/models/workspace_model.py` | Onglets/groupes, sélection par `(groupe, onglet)`, ouverture des pages et adaptation des lignes de playlist pour la lecture. `playTrack()` et `playPlaylistRows()` remplacent la file de contexte. |
| `src/mtee/persistence/workspace_repository.py` | Document JSON de disposition dans SQLite, validation explicite des champs. La restauration des onglets ne garde actuellement que folder/playlist. Ce stockage n'est pas une persistance de file audio. |
| `src/mtee/qml/Main.qml` | Le raccourci Espace est désactivé par `textInputFocused()`. Cette fonction considère aussi `AbstractButton` comme une saisie : piste concrète à tester pour le défaut intermittent. |
| `src/mtee/qml/components/TrackContextMenu.qml` | Menu partagé, `targetIds()` préserve la sélection si la ligne cliquée en fait partie. Pas de `Add to queue` dans l'état lu. |
| `src/mtee/qml/components/PlaylistsPane.qml` | Menu contextuel de playlist à compléter pour l'ajout de son contenu entier. |
| `src/mtee/qml/components/PlaybackQueueView.qml` | Liste actuellement construite avec un Repeater. `nextOnly` masque seulement le morceau courant et peut donc présenter des lignes déjà passées comme à venir. |
| `src/mtee/qml/components/QueuePanel.qml` | Présente Now playing, la file de contexte et History. Réutiliser cet emplacement. |
| `src/mtee/qml/components/TrackListView.qml` | Sélection List/Artwork, menus et focus clavier. Le fond d'en-tête donne actuellement le focus, sans commande explicite de désélection. |
| `src/mtee/qml/components/EditorGroup.qml` | Onglets et Loader du groupe. Les changements de page peuvent recréer une vue : prendre en compte sa capture/restitution d'état. |
| `src/mtee/qml/components/InfoPanel.qml` | Sans sélection, le panneau montre actuellement `Select a track to see its info.` ; adapter à la demande d'un panneau vide. |
| `src/mtee/app.py` | Assemblage des services et arrêt : sauvegarde workspace, arrêt des jobs/services, puis fermeture SQLite. La sauvegarde finale de file doit précéder la remise à zéro du lecteur. |
| `src/mtee/persistence/database.py` | Migrations transactionnelles avec sauvegarde cohérente ; migration maximale observée : 017. |

Tests existants à lire : `tests/unit/test_player_service.py`, `tests/unit/test_playback_queue.py`, `tests/unit/test_workspace_model.py`, `tests/ui/test_player_views.py`, `tests/ui/test_playlists_ui.py`, `tests/ui/test_browser_navigation.py`, `tests/ui/test_column_selection.py`, `tests/ui/test_metadata_editor.py`, `tests/integration/test_database_migrations.py`, `tests/integration/test_mpv_playback.py` et `tests/integration/test_runtime_shutdown.py`.

La préparation n'a pas exécuté ces tests et n'a pas reproduit le bug intermittent. Le test Espace déjà présent couvre la recherche pendant la lecture, pas tous les types de focus. Les faux fichiers du test de service ne sont pas de l'audio décodable : les parcours natifs doivent utiliser de vrais WAV synthétiques.

## Contrats techniques à respecter

Les paragraphes de cette section sont des décisions techniques de planification, pas des demandes supplémentaires de l'utilisateur. Ils décrivent comment rendre les comportements confirmés testables.

### Identité et indépendance de la file

Séparer l'identité d'un morceau (`track_id`) de celle d'une occurrence de lecture (`entry_id`). Deux ajouts du même morceau produisent deux occurrences distinctes. Retirer, réordonner, jouer et rendre une ligne utilisent `entry_id`, jamais seulement `track_id` ou un index mémorisé avant une mutation. Les métadonnées peuvent rester en cache par morceau ; les positions, origines et identités des occurrences sont distinctes.

Créer le domaine pur dans `src/mtee/domain/playback_queue.py` : occurrences, ordre, occurrence courante, distinction des ajouts manuels et du contexte. Le service possède un seul état autoritaire. Les vues et `upNext` sont des projections de cet état. Ne pas ajouter une seconde liste QML comme autorité et ne pas utiliser les vingt lignes de History comme stockage complet de la file.

La sélection d'une playlist utilise parfois une identité d'entrée de playlist ; sa conversion vers `trackId` local est nécessaire avant la lecture. `WorkspaceModel.localTrackIds()` utilise effectivement `dict.fromkeys()` et déduplique : ne pas l'utiliser comme convertisseur générique de lots d'occurrences. Ajouter une conversion dédiée qui garde leur multiplicité et leur ordre. Ne pas modifier les règles de déduplication des playlists du plan 34.

Les ajouts groupés conservent l'ordre visible de la sélection, indépendamment de l'ordre des Ctrl-clics. L'ajout d'une playlist entière lit son ordre propre sans la limiter à un filtre de l'onglet. Préparer les gros snapshots hors du thread graphique, puis appliquer atomiquement le lot sur le thread Qt. Donner à chaque demande un ordre d'arrivée : un second lot prêt plus vite ne doit pas passer devant le premier. Les sources indisponibles doivent produire un résultat explicite cohérent avec le traitement existant des absences, sans charger un autre morceau à la place ni annoncer un lot entièrement ajouté si des éléments ont été refusés.

Ajouter ou éditer une file ne doit pas couper le morceau courant, remettre sa position à zéro, modifier une playlist, écrire des tags, déplacer ou supprimer un fichier. Une occurrence courante n'est pas un morceau « à venir ».

### État de domaine et opérations de file

Définir `QueueEntry(entry_id, track_id, origin, source, source_title, snapshot)` ; `origin` vaut `manual` ou `context`. Le snapshot contient uniquement les champs nécessaires au rendu et à la résolution, pas des objets Qt ou des fichiers ouverts. `entry_id` est un UUID nouveau à chaque ajout. Le même `track_id` peut apparaître sans limite fonctionnelle de déduplication.

Définir `QueueState` avec une révision entière croissante, le contexte de lecture et son ordre de référence, les occurrences avant le curseur, l'occurrence courante optionnelle et la liste ordonnée `upcoming`. Garder assez de parcours pour Précédent ; le limiter aux vingt éléments du widget History serait une régression de navigation dans le contexte. Garder séparément la projection visuelle History, toujours bornée comme aujourd'hui. La position et l'état natif restent dans `PlaybackState` ; relier explicitement les deux états par `current_entry_id`. Une seule fonction de publication dans le service met à jour ces projections et les signaux Qt.

Invariants à vérifier après chaque mutation : IDs d'occurrence uniques, courant absent de `upcoming`, occurrences retirées absentes des ordres de reprise, références cohérentes, pas de position native modifiée par une simple édition. Une projection de compatibilité `track_ids` peut rester disponible, mais aucune opération sur un doublon ne choisit sa cible avec `track_ids.index(track_id)`.

| Opération | Transformation à implémenter |
|---|---|
| Ajouter un lot | Fabriquer les occurrences manuelles, puis les insérer après la dernière occurrence manuelle encore en attente ; s'il n'y en a aucune, les insérer en tête de `upcoming`. Le lot est appliqué en une mutation. Les demandes concurrentes passent dans l'ordre de clic. |
| Lancer une piste depuis une liste | Capturer le nouveau contexte et l'index demandé. Extraire les occurrences `manual` encore en attente dans leur ordre actuel, remplacer le contexte, faire de la piste choisie le courant, puis placer les occurrences manuelles avant la nouvelle suite du contexte. Une piste de contexte ayant le même `track_id` qu'un ajout ne le consomme pas. |
| Next explicite | Prendre la première occurrence à venir et l'ouvrir avec le service ; elle quitte `upcoming` une seule fois. Sans suivant, conserver le comportement de fin existant. Next ne recapture jamais le listing actuellement visible. |
| Fin naturelle | En Repeat one, relancer l'occurrence courante sans consommer `upcoming`. Sinon prendre le suivant. En fin de liste, Repeat all reprend le contexte de référence ; Repeat off termine. Les ajouts manuels déjà consommés sont ponctuels et ne sont pas recréés au prochain cycle. |
| Retirer | Chercher `entry_id` uniquement dans `upcoming`, retirer cette occurrence et sa référence éventuelle dans l'ordre de reprise de la session. Ses doublons restent. Aucun accès d'écriture au fichier, aucune suppression de playlist. |
| Réordonner | Retirer l'occurrence à venir et la réinsérer avant l'occurrence cible à venir, ou en fin avec une cible nulle. Autoriser le passage entre lignes d'origine manuelle et de contexte. Actualiser l'ordre de référence des occurrences de contexte pour qu'un changement Shuffle ne ressuscite pas un ancien ordre imposé par le code. |
| Shuffle | Mélanger les occurrences de contexte à venir ; les occurrences manuelles gardent leur ordre et leurs emplacements relatifs à la suite explicitement éditée. Désactiver Shuffle restaure l'ordre de référence des seules occurrences encore en attente ; ne pas recréer les occurrences consommées ou retirées. |
| Jouer une ligne de Queue | Cibler son occurrence, la retirer de `upcoming` et la rendre courante. Garder les autres ajouts manuels en attente. Ne pas appeler `workspace.playTrack()` avec un dossier deviné : ce chemin reconstruirait le contexte et perdrait les éditions. |
| Ajouter sans piste courante | Conserver le lot sans démarrer la lecture, comme toute action `Add to queue`. La file peut être ouverte par son emplacement existant ; jouer une occurrence ou Play/Espace charge la première disponible à la demande explicite. |

Ces détails d'ordonnancement sont des conventions opérationnelles pour l'implémentation des exigences, consignées comme choix de conception. La distinction entre ajouts ponctuels et contexte évite de recréer indéfiniment des demandes consommées. Pour un retour Précédent, conserver les occurrences réellement traversées, y compris les ajouts, et les réinsérer correctement dans le chemin futur : ne pas fabriquer un nouvel `entry_id` pour un simple retour de lecture.

Préserver le traitement d'erreur existant : une occurrence qui devient indisponible au chargement affiche une erreur et peut être passée avec Next. Ne pas introduire un nouveau skip silencieux illimité. L'ajout d'une entrée de playlist sans fichier local est refusé avec indication du nombre d'éléments non ajoutés ; les autres éléments disponibles du lot sont ajoutés dans leur ordre. Une source devenue indisponible après ajout ou après fermeture reste représentée dans la file sauvegardée.

Interfaces de façade à créer et tester : `WorkspaceModel.enqueueTracks(ids, source, rows)` pour la sélection capturée ; `enqueuePlaylist(playlist_id)` pour le contenu complet ; `PlayerModel.playEntry(entry_id)`, `removeQueueEntry(entry_id)` et `moveQueueEntry(entry_id, before_entry_id)` pour les opérations sur la file. Ajouter `revision`, `entryId`, `trackId`, `origin`, `available` et `current` aux projections appropriées. Le domaine utilise des noms Python en snake_case. Les noms Qt ci-dessus sont les contrats de ce plan ; une adaptation justifiée doit être consignée et appliquée à tous les appelants/tests.

Une opération reçue avec une révision périmée doit revalider l'identité des occurrences. Si une source ou cible de drop est déjà consommée/retirée, ne pas réordonner un autre morceau : abandonner ce drop et rafraîchir la vue. Un ajout préparé en worker ne doit pas être annulé par une simple navigation de page ; il garde les cibles capturées et sa place FIFO.

### Persistance

Créer `src/mtee/persistence/playback_repository.py` et une migration dédiée, attendue `018_playback_session.sql` si ce numéro est encore libre à l'exécution. Ne jamais modifier une migration publiée ; choisir le prochain numéro libre et le noter ici si nécessaire. Créer `playback_session(session_id TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at_utc TEXT NOT NULL)` avec une ligne logique `main`. Le JSON contient `version: 1`, révision de file, contexte/ordre de référence, occurrences avant/courante/à venir, position en microsecondes, modes repeat/shuffle et projection d'historique nécessaire. `session_id` désigne ici la session persistée, pas le numéro de chargement natif. Valider explicitement les champs et invariants à la lecture. Aucune contrainte d'unicité sur `track_id`.

Persister l'identité et le snapshot utile d'un morceau indisponible plutôt que dépendre d'une suppression en cascade du catalogue. À la lecture, résoudre le chemin actuel via le catalogue et préserver `FileAccessCoordinator`, les générations de session et la libération après confirmation native. Les chemins historiques ne remplacent pas cette résolution.

Utiliser un writer séquentiel pour les snapshots persistants ; une écriture ancienne ne doit jamais remplacer une révision plus récente. La file affichée doit rester cohérente avec les erreurs de sauvegarde. Ne pas écrire la base à chaque tick de position de 100 ms. Choix technique : enregistrer les mutations de file, les changements de piste et les pauses, avec checkpoint de position toutes les cinq secondes au plus en lecture ; la fermeture normale enregistre la dernière position effective. Cette cadence est un compromis d'écriture pour la reprise après arrêt brutal, pas une promesse de récupération du dernier échantillon après crash. Capturer et vider les écritures en attente avant que `PlayerService.close()` efface le morceau courant et avant la fermeture SQLite.

Pour restaurer : lire et valider la session hors du rendu QML, résoudre le morceau courant, le charger avec une intention initiale de pause, attendre `loaded`/durée/seekable de cette session, appliquer la position sauvegardée bornée à la durée, puis publier Paused. Le chargement actuel dépause systématiquement avant `load` : ajouter un paramètre explicite d'intention initiale, par défaut Play pour les activations existantes et Pause pour la restauration. Ne pas lancer Play puis corriger après coup par Pause, ce qui pourrait émettre du son au démarrage. Si l'utilisateur lance un autre morceau pendant la restauration, invalider le seek différé par la génération de session. Espace reprend à la position restaurée. Une piste introuvable garde ses informations et une erreur visible ; elle ne déclenche pas la lecture spontanée de la suivante.

Une session malformée doit être diagnostiquée, sans réinitialiser la bibliothèque ou les playlists. Tester format/version inconnus, identifiants absents et base temporairement indisponible. Ne pas annoncer que la restauration est livrée avec un test de sérialisation seul : construire un second runtime et vérifier ses modèles ainsi que le backend.

### Navigation entre pages

Créer `NavigationLocation` et `NavigationHistory` dans `domain/navigation_history.py`. Chaque groupe possède sa propre liste de destinations et un curseur, en mémoire pour la session applicative : la persistance de cet historique entre fermetures n'est pas demandée. La persistance audio de Q3 est indépendante. La limite de deux groupes existante reste inchangée.

Une destination décrit le type de page, l'ID d'onglet ou la référence stable, l'activité latérale, le mode plein écran, les sous-pages existantes et un état de vue. L'état de vue comprend recherche, mode List/Artwork, tri utile à la restitution, sélection/ancre et position de défilement. Pour une liste, garder une ancre d'occurrence/ligne stable et son décalage visible, avec `contentY` borné comme repli. Les valeurs de réglages et les contenus de playlists ne sont pas copiés/restaurés par l'historique : Back doit retrouver une page, pas annuler ses modifications métier.

Inventorier et brancher **toutes les destinations existantes** : dossiers, playlists et Liked tracks, onglets Convert et Settings avec ses sous-pages, activités Explorer/Playlists/Convert/Tasks, emplacements Plugins/Profile déjà affichables, plein écran et vues Info/Queue. Les placeholders restent des placeholders. Aucun écran supplémentaire n'est créé. Pour des sous-vues actuellement locales au QML, exposer un état capturable/restaurable plutôt que supposer que le Loader les conserve. Les menus et dialogues transitoires ne deviennent pas des pages d'historique.

Capturer l'état avant de quitter une page ; enregistrer la nouvelle destination une fois qu'elle est acceptée. Le changement de groupe seul ne pousse aucune destination. Les clics répétés sur la page actuelle et les mises à jour de modèle ne créent pas de doublons. `navigateBack()` et `navigateForward()` travaillent sur le groupe actif et rejouent une destination avec un garde empêchant son réenregistrement. Utiliser `canNavigateBack`/`canNavigateForward` pour les tests, sans ajouter de boutons non demandés.

Le shell a une sidebar et un plein écran partagés : leur restauration peut changer cette surface commune, mais ne remplace ni les onglets, ni l'historique, ni la sélection de l'autre groupe. Attacher la destination à l'ID du groupe qui l'a créée. Les tables internes de vue doivent être indexées par `(groupe, onglet)` pour ne pas écraser les snapshots de deux panneaux montrant la même page. Les données métier de la page peuvent rester partagées.

Lors d'un retour, appliquer recherche/tri avant la requête de lignes, attendre le résultat du bon groupe/onglet/génération, rétablir les seuls IDs encore présents puis l'ancre de scroll. Un retour devenu périmé ne doit ni sélectionner ni défiler une nouvelle page. Un onglet fermé peut être rouvert par sa destination si elle existe encore. Une playlist supprimée ou une référence devenue invalide est passée avec un diagnostic bref ; ne pas rester dans une boucle. Sur borne d'historique, ne rien faire. Une nouvelle navigation depuis une ancienne entrée coupe Forward. À la fusion des groupes, supprimer l'historique du groupe retiré ; à une nouvelle division, initialiser le nouveau groupe sur sa page initiale, sans partager la même liste mutable.

Recevoir les boutons Qt BackButton/ForwardButton au niveau de la fenêtre ou d'un filtre Qt dédié ; un clic produit une seule navigation dans le groupe actif. Ne pas activer le groupe survolé silencieusement ni détourner les événements en touches Previous/Next. Aucun besoin de hook système ou de support de souris hors fenêtre active.

### Commandes et focus

`PlayerService` reste l'unique autorité pour Précédent et la pause. `PlayerModel`, `WorkspaceModel`, l'îlot, le plein écran et Ctrl+Left délèguent. Le seuil vaut exactement `3_000_000` microsecondes de position dans le morceau, pas trois secondes depuis la dernière action ou depuis le début de la session.

Espace doit être traité une fois par appui, sans répétition automatique lors d'un maintien. Distinguer une véritable saisie de texte d'un bouton ou d'un contrôle sans texte. Conserver la saisie normale des champs de recherche, tags, noms et descriptions de playlists et réglages. Tester les contrôles focalisés plutôt que simplement retirer `AbstractButton` du prédicat : le même événement ne doit pas à la fois activer le bouton et basculer le lecteur. Garder l'effet limité à la fenêtre MTEE active ; aucun hook clavier système. Si aucune piste ni occurrence en attente n'existe, Espace ne déclenche aucune erreur ou lecture inventée.

Une commande Précédent reçue en pause doit lancer le résultat, y compris lorsque le résultat est un seek à zéro du même morceau. Conserver la priorité d'une nouvelle pause explicitement demandée pendant un chargement et le rejet des événements tardifs d'une ancienne session. Les réponses du backend, et pas seulement les icônes, doivent confirmer l'état.

### Sélection

Ajouter une commande explicite `WorkspaceModel.clearSelection()` qui vide les IDs et l'ancre du groupe/onglet actif, émet les signaux nécessaires et persiste la sélection vide. Ne pas détourner `selectTrack("")`, qui créerait une sélection contenant une chaîne vide. Annuler les demandes différées de révélation/sélection qui pourraient rétablir une ancienne sélection après le clic.

En zone vide d'un groupe, activer ce groupe puis vider sa sélection. En zone vide commune de sidebar ou du panneau droit, agir sur le groupe déjà actif. Préserver l'autre groupe et les sélections des onglets non concernés. Cette activation ne commande pas la lecture.

Les surfaces vides doivent être de vrais fonds : ligne, tuile, bouton, champ texte, menu, en-tête de tri, poignée, scrollbar et action de transport ne sont pas des zones vides. Éviter un MouseArea opaque placé au-dessus de toute la fenêtre. Les gestionnaires de fond ne doivent pas avaler le drag, le scroll ou le clic destiné à un enfant.

Info reste ouvert si c'était son état, mais son contenu devient vide : ni fiche ancienne, ni repli sur le morceau joué, ni texte d'invitation. Préserver la sauvegarde par champ des métadonnées ; un changement de focus ne doit pas appliquer une édition à une nouvelle sélection. Une sauvegarde déjà engagée garde ses destinataires capturés.

## Jalons d'exécution

### 99.0 — Vérifier le socle et préparer la revue de la file

Avant toute modification fonctionnelle, relire les décisions finales Q1–Q4, inspecter Git et vérifier les chemins de la table de sources. Exécuter les tests existants pertinents pour distinguer les échecs du socle de ceux introduits ensuite. Relever toute différence dans Surprises & Discoveries.

Préparer une maquette QML de la file dans `docs/ux/mockups/Queue99Review.qml`, accompagnée d'un lanceur `scripts/review_queue_99.py` réutilisant les imports/thèmes/providers du projet. Ces deux fichiers sont à créer pendant ce jalon, pas des outils déjà disponibles. La maquette doit montrer un morceau courant, plusieurs ajouts dont deux occurrences identiques, la suite du contexte, retrait et réordonnancement, une file vide et une source indisponible. Utiliser les emplacements existants du panneau Queue et du plein écran ; aucune refonte du lecteur des features 5–8.

La revue porte sur les seules commandes visuelles nouvelles : `Add to queue`, `Remove from queue` et le drag-and-drop de réordonnancement. Montrer la ligne prise par la souris, la cible d'insertion et l'absence de modification avant le drop. Préserver le clic/double-clic existant et le scroll pendant le drag. Ne proposer aucun bouton `Clear queue`. Préparer captures, parcours et limites dans `docs/ux/review-99-queue.md`, puis obtenir la validation de la maquette conformément à `PLAN.md`. Les choix fonctionnels déjà validés ne sont pas remis en question par cette revue. Ne pas implémenter le backend de file avant cette validation.

Commande à utiliser après création du lanceur, depuis la racine :

    uv run python scripts/review_queue_99.py

### 99.1 — Domaine de file et transitions

Créer `src/mtee/domain/playback_queue.py` et `tests/unit/test_playback_queue_state.py`. Implémenter les structures, invariants et transitions définis plus haut avant de connecter QML. Couvrir occurrence unique, ajout FIFO et lot, doublons, retrait d'une occurrence, déplacement, transitions Next/EOF/Previous, changement de contexte, Shuffle et Repeat. Chaque cas doit vérifier les IDs d'occurrences et le prochain morceau réel.

Adapter `domain/playback.py` et `services/player_service.py` sans déplacer les ressources natives dans le domaine pur. Modifier tous les chemins qui utilisent `_base_ids`, `track_ids.index()` ou un index numérique comme identité lorsque des doublons rendent leur comportement ambigu. Conserver les façades existantes encore appelées, ou adapter tous leurs appelants dans le même jalon. L'absence d'une occurrence demandée après une mutation ne doit pas jouer arbitrairement la ligne ayant récupéré son ancien index.

Procéder dans cet ordre : identité et projection, ajout et changement de contexte, consommation et retour, retrait/déplacement, puis modes Shuffle/Repeat. À chaque sous-étape, rejouer les cas déjà acquis. Terminer par le modèle Qt : signaux `queueChanged` après une mutation réelle et `positionChanged` pour la seule position ; les ticks ne reconstruisent pas les milliers de lignes d'une file.

### 99.2 — Sauvegarde et restauration de la session audio

Créer le repository et la migration définis plus haut, avec `tests/integration/test_playback_repository.py`. Brancher chargement, writer séquentiel et flush dans `app.py` et le service adapté. Tester sur copie de base v17 avec playlists et analyses : migration, backup lisible, répétition sans second changement, rollback provoqué et conservation des données existantes.

Créer `tests/integration/test_playback_session.py` pour fermer puis reconstruire réellement le runtime. Vérifier ordre, doublons, origine des entrées et état courant selon Q3. Vérifier aussi fermeture pendant une écriture, sauvegarde en erreur, fichier déplacé entre deux sessions, source indisponible, backend absent et réponse asynchrone devenue périmée.

### 99.3 — Relier les menus et la file visible

Adapter `TrackContextMenu.qml` et la façade de `WorkspaceModel` pour l'ajout depuis les listes de dossiers et playlists, y compris leurs résultats filtrés et leur vue Artwork. Capturer les cibles avant fermeture du menu. Clic droit sur une ligne de la sélection : ajouter la sélection dans l'ordre visible. Clic droit hors sélection : ajouter la ligne visée selon le comportement existant du menu. `Ctrl+A`, puis `Add to queue`, permet le lot visible complet.

Ajouter `Add to queue` au menu contextuel d'une playlist dans `PlaylistsPane.qml` ; préparer son contenu complet hors du thread UI. Ne pas confondre la playlist entière et ses seuls résultats visibles. Ne pas créer de boutons supplémentaires dans l'îlot ou le lecteur pour cette action.

Adapter `PlaybackQueueModel`, `PlaybackQueueView.qml`, `QueuePanel.qml` et leurs usages dans `FullscreenPlayer.qml`. Les deux présentations doivent montrer les mêmes occurrences et le même ordre. La partie à venir ne contient pas l'historique. Clic droit `Remove from queue` et drag-and-drop utilisent `entry_id` ; toutes les occurrences à venir, manuelles ou de contexte, sont modifiables. Garder le morceau courant et l'historique hors des cibles de retrait/drop.

Le drag capture ID et révision, affiche une prévisualisation et appelle `moveQueueEntry()` une seule fois au relâchement sur une cible valide. Escape, sortie sans drop ou disparition de la cible annulent le déplacement. Le clic droit capture l'occurrence visée ; le traitement ne doit pas supprimer toutes les lignes du même morceau. Ne pas proposer de vidage global, même dans le menu du fond.

Remplacer le Repeater non virtualisé de la file si son usage charge toutes les lignes d'une playlist importante. Une seule vue doit gérer le défilement d'une même liste ; ne pas empiler deux Flickable concurrents. Ajouter `tests/ui/test_playback_queue_ui.py`, en exerçant réellement les menus et le changement de modèle.

### 99.4 — Précédent à trois secondes

Faire échouer des tests ciblés dans `test_player_service.py` aux positions `0`, `2_900_000`, `2_999_999`, `3_000_000` et `3_100_000` microsecondes. Paramétrer Playing/Paused, première occurrence, présence d'une précédente, modes de boucle, file avec doublons et courant issu d'un ajout manuel.

Dans `PlayerService.previous()`, choisir la destination avec une position effective cohérente : le dernier tick peut dater de 100 ms. Consulter le backend si cela est fiable à cette frontière et tenir compte d'un seek encore en attente, sans laisser un ancien relevé inverser la décision après un premier clic. Tester deux clics rapprochés : le premier revient à zéro, le second doit pouvoir atteindre le précédent si disponible.

Revenir au début utilise seek puis reprise explicite lorsque nécessaire. Changer d'occurrence utilise le chargement central existant. Vérifier les règles Q2 à la première occurrence, et ne pas recréer une file à partir de la sélection courante. Étendre `test_player_views.py` pour l'îlot, le plein écran et Ctrl+Left. Les boutons latéraux de souris restent des commandes de navigation de pages.

### 99.5 — Espace et focus

Étendre `tests/ui/test_player_views.py` avec une fixture de lecture et des appuis Qt sur le fond, les listes, un bouton focalisé, la file, Settings, Convert et le plein écran. Tester ensuite les champs de recherche, de métadonnées et de playlist. En saisie, l'espace apparaît dans le texte et le backend ne reçoit aucune bascule. Hors saisie, un appui produit exactement une pause ou reprise et ne déclenche pas le contrôle focalisé en plus.

Corriger le routage dans `Main.qml` et, seulement si nécessaire, dans un filtre d'événements Qt dédié créé sous `src/mtee/platform/`. Centraliser la décision, ne pas multiplier des raccourcis indépendants dans les composants. Tester maintien, relâchement, modificateurs, absence de piste et focus sur une autre fenêtre. Documenter si le bug d'origine a été reproduit ou si seule la cause concrète identifiée dans le prédicat a été corrigée.

### 99.6 — Historique de pages et boutons latéraux

Créer le domaine `src/mtee/domain/navigation_history.py` et `tests/unit/test_navigation_history.py` selon le contrat de navigation ci-dessus. Ce domaine gère destinations et curseur arrière/avant. Les commandes de replay ne doivent pas recréer une entrée d'historique. Une nouvelle navigation après Back retire la branche Forward. Répéter la destination courante n'ajoute pas une entrée identique.

Brancher les ouvertures de toutes les pages inventoriées dans `WorkspaceModel` : `openFolder`, activation de morceau depuis l'arbre ouvrant un dossier, `openPlaylist`, `openConvert`, `openSettings`, `activateTab`, `setActivity`, `setFullscreen` et l'ouverture/changement Info/Queue. Les gestes dépliage d'un dossier, scroll ou sélection mettent à jour le snapshot courant mais ne créent pas une nouvelle page. Ajouter les sous-pages Settings au contrat plutôt que les perdre avec sa propriété QML locale `page`. Ne pas utiliser l'historique de lecture pour cet usage. Adapter `Main.qml` ou un filtre Qt attaché à la fenêtre pour recevoir BackButton/ForwardButton, une fois par clic. Le bouton arrière ne doit ni jouer le morceau précédent ni désélectionner accidentellement une ligne sous la souris.

Créer `tests/ui/test_navigation_history_ui.py` : événements natifs Qt, navigation de pages, limite d'historique, nouvelle branche après retour et séparation des groupes. Tester la restitution de recherche/défilement/sélection après chargement asynchrone, ancre disparue et abandon d'un retour devenu périmé. Vérifier deux groupes montrant le même onglet avec des snapshots différents. La fermeture/suppression d'une destination doit donner un résultat sûr sans déclencher de lecture. Adapter `DemoWorkspace` pour que les vues partagées restent chargeables en mode démo.

### 99.7 — Désélection des surfaces vides

Implémenter `clearSelection()` et sa version dans `DemoWorkspace` si les vues partagées l'appellent. Relier les fonds de `TrackListView.qml` en List/Artwork, `EditorGroup.qml`, `SideBar.qml`, `ExplorerPane.qml`, `PlaylistsPane.qml` et les espaces communs concernés. Vérifier les fonds du panneau droit sans recouvrir les contrôles de métadonnées ou de file. Conserver les indices du groupe concerné dans tous les callbacks.

Adapter `InfoPanel.qml` pour n'afficher aucun contenu sans sélection, y compris les footers qui pourraient garder des données anciennes. Les erreurs liées à une opération déjà engagée restent disponibles via leur mécanisme existant ; ne pas étendre ici l'interface de notifications.

Créer `tests/ui/test_empty_selection.py` et compléter `test_workspace_model.py`. Vérifier clic sous la dernière ligne, liste vide, espaces entre tuiles, sidebar vide, autre panneau en split, sélection multiple et Ctrl/Shift après désélection. Vérifier qu'un clic sur un contrôle ne désélectionne pas par propagation et que ni `playingId`, ni la position, ni le nombre de chargements backend ne changent. Après redémarrage, la sélection explicitement vidée ne réapparaît pas.

### 99.8 — Recette complète et livraison

Créer `docs/validation/99-controles-lecture-file-navigation.md` avec environnement, commandes, observations et limites réelles. Exécuter les tests de chaque jalon après sa modification puis une passe intégrée. Faire le parcours Windows depuis les sources avec WAV synthétiques ou copies autorisées, entendre les changements de lecture et exercer les vrais boutons latéraux de souris. Les événements Qt simulés ne prouvent pas à eux seuls le routage d'une souris physique.

Exécuter la matrice de recette ci-dessous. Vérifier dans une seconde session que la file restaurée correspond à la dernière sauvegarde. Aucun build EXE ou smoke-test de paquet n'est requis par cette demande.

## Matrice de recette et preuves attendues

Utiliser une collection synthétique avec au moins cinq pistes de plus de dix secondes, des métadonnées distinctes, deux playlists, un doublon de référence au même morceau et deux groupes. Les tests unitaires imposent des positions entières ; l'écoute humaine contrôle le son et les UI tests vérifient les objets réellement affichés. Les chiffres de séquence ci-dessous sont des noms de fixtures, pas des IDs de production.

| Cas | Action | Résultat obligatoire et niveau de preuve |
|---|---|---|
| F9-01 | Lire 1 dans `[1,2,3,4,5]`, ajouter 9 puis 8 | Courant 1 intact ; à venir `[9,8,2,3,4,5]`. Aucun rechargement ni seek de 1. Domaine + service + clic droit UI. |
| F9-02 | Sélectionner 4 puis Ctrl-clic 2, ajouter | Le lot suit l'ordre visible `[2,4]`. Clic droit hors sélection ajoute seulement la ligne visée. Dossier, playlist, recherche et Artwork. |
| F9-03 | Ajouter une playlist entière depuis la sidebar alors que son onglet est filtré | Tout son contenu local jouable est ajouté dans l'ordre de playlist, avec bilan des absences. Filtre et lecture inchangés. |
| F9-04 | Ajouter deux fois 9, retirer la seconde occurrence au clic droit | Deux `entry_id` distincts avant retrait ; seule la cible disparaît, premier 9 conservé. Fichier et playlist inchangés. |
| F9-05 | Drag d'un ajout manuel après une piste de contexte, puis drag d'une piste de contexte avant un ajout | Ordre conforme au point de drop dans les deux sens, même ordre dans les deux vues Queue et au prochain Next. Escape annule sans mutation. |
| F9-06 | Conserver 9/8 en attente, lancer B dans `[A,B,C]`, puis cliquer une autre piste du même contexte | Les occurrences manuelles gardent leurs IDs et leur ordre, suivent le nouveau courant avant sa nouvelle suite. Pas de perte ou de fusion par `track_id`. |
| F9-07 | Activer puis désactiver Shuffle après ajouts, déplacement et retrait | Ordre des manuels conservé ; seul le contexte autorisé est mélangé/restauré. Aucun élément retiré ou consommé ne réapparaît. |
| F9-08 | Activer Repeat one et laisser finir 1 avec 9/8 en attente | 1 recommence, 9/8 restent en attente. Désactiver Repeat one puis atteindre EOF consomme 9. Vérifier backend, pas seulement affichage. |
| F9-09 | Fin naturelle et Next, retours Previous et nouvelle avance autour de deux occurrences de 9 | Chaque occurrence conserve sa propre identité ; pas de double consommation, boucle d'événements ou inversion de FIFO. |
| F9-10 | Réordonner/retirer, lire jusqu'à une position connue, fermer et rouvrir | Même courant, ordre, doublons, modes et position sauvegardée ; état Paused avant toute émission audio. Espace reprend. Intégration avec deux runtimes et recette Windows. |
| F9-11 | Arrêter pendant la sauvegarde ou lancer B pendant une restauration de A | Transaction cohérente ; aucun vieux snapshot ne remplace le nouveau, aucun seek de A ne touche B. Erreur visible si sauvegarde impossible. |
| F9-12 | Rendre une source absente après ajout ou avant restauration | Ligne conservée et diagnostic ; aucun faux succès ou démarrage d'une autre piste. Retrait ou Next permet de poursuivre. |
| F9-13 | Ajouter deux gros lots dont le second est préparé plus vite | Ordre des demandes conservé, application réactive, Qt modifié seulement sur le thread UI. Mesurer une playlist de 10 000 occurrences et rapporter l'environnement, sans inventer un seuil déjà validé. |
| F9-14 | File vide et aucun courant ; ajouter un lot | Pas de lecture automatique. Une demande Play/Espace explicite joue la première occurrence. Aucun contrôle de vidage global n'est présent. |
| F10-01 | Espace avec focus sur fond, bouton, liste, queue, page spéciale et plein écran | Une seule bascule réelle, même identité de piste, aucun déclenchement parasite du contrôle focalisé. |
| F10-02 | Espace dans recherche, tags, nom/description de playlist et champ de réglage | Espace saisi ; aucune pause/reprise. Répéter après ouverture/fermeture d'un menu et retour au fond. |
| F10-03 | Maintenir Espace, relâcher ; faire de même hors de MTEE | Une bascule par appui dans MTEE, aucune quand une autre fenêtre est active. Sans file ni courant : aucune action. |
| F11-01 | Dossier → playlist → Settings/Analysis → Convert → Tasks puis Back/Forward | Chaque destination existante est retrouvée dans le bon ordre, une étape par clic. Tester aussi autres activités, plein écran et Info/Queue selon l'inventaire. |
| F11-02 | Recherche active, scroll au milieu et multisélection, quitter puis revenir | Texte, résultats, ancre de scroll et sélection restaurés après chargement ; aucune lecture démarrée. Les modifications métier faites ailleurs restent. |
| F11-03 | Deux groupes, chacun avec son parcours ; naviguer dans l'actif | Historique et sélection de l'autre groupe intacts. Tester même onglet visible dans les deux groupes et groupe compact masqué. |
| F11-04 | Back puis nouvelle page, borne d'historique, onglet fermé, playlist supprimée | Forward coupé seulement par la nouvelle navigation ; borne sans effet ; onglet valide rouvert ; destination supprimée traitée sans boucle ni lecture. |
| F11-05 | Back puis nouvelle navigation avant le retour d'un worker lent | Pas de sélection, focus ou scroll appliqué à la page devenue courante par erreur. Vérifier génération et groupe. |
| F12-01 | Précédent à 2,9 s et 2,999999 s avec une occurrence précédente | Occurrence précédente chargée et lue. Tester Playing et Paused, îlot/plein écran/Ctrl+Left. |
| F12-02 | Précédent à 3,000000 s et 3,1 s | Même occurrence, seek à zéro, lecture active, pas de navigation de page ni de reconstruction de file. |
| F12-03 | Première occurrence avant 3 s, Repeat off/one/all | Off/one : début du courant. All : dernière occurrence du cycle de liste. Une seule piste : début de cette piste. Toujours lecture active. |
| F12-04 | Deux clics Précédent rapides depuis plus de 3 s | Premier : début du courant. Second : précédent si disponible. L'ancien tick de position ne bloque pas le second. |
| F12-05 | Précédent provoque un chargement lent, puis l'utilisateur appuie Pause | La pause la plus récente reste respectée à `loaded` ; les événements d'anciennes sessions ne changent pas l'état. |
| F13-01 | Multisélection puis clic sur fond sous les lignes, entre tuiles ou dans sidebar vide | Sélection/ancre vides dans le groupe actif, Info vide, lecture et file inchangées. |
| F13-02 | Deux panneaux sélectionnés, clic dans le vide d'un groupe | Ce groupe devient actif et lui seul est vidé ; l'autre sélection reste. Clic dans une surface commune vide cible le groupe déjà actif. |
| F13-03 | Clic sur bouton, ligne, scrollbar, menu, tri ou contrôle de transport | Action normale ; le gestionnaire de fond ne déclenche pas une désélection parasite. |
| F13-04 | Éditer un champ puis cliquer dans le vide, avec inspection asynchrone encore en cours | Sauvegarde éventuelle garde ses cibles capturées ; aucune donnée appliquée à la nouvelle sélection, aucune fiche obsolète ne réapparaît. |
| F13-05 | Désélectionner puis redémarrer, puis revenir par l'historique pendant une session | Une sélection explicitement vidée est sauvegardée comme vide ; le snapshot courant de navigation est actualisé et ne ressuscite pas l'ancien état. |

Les cas d'erreur et les conventions opérationnelles sont des critères techniques de ce plan ; les comportements produit normatifs sont ceux confirmés dans les deux tableaux de décisions. La réussite d'une feature exige son comportement visible et les preuves correspondantes, pas simplement l'existence de ses méthodes ou de ses tests.

## Consigne de reprise pour Luna

Utiliser ce texte lors d'une demande ultérieure d'exécution :

    Lis AGENTS.md, PLANS.md et le plan 99 en entier. Exécute uniquement
    le prochain jalon non terminé de 99-controles-lecture-file-navigation.md.
    Vérifie les prérequis dans les sources et tests après consultation du graphe.
    Respecte les décisions utilisateur Q1–Q4 et les cas F9 à F13. Ne remplace
    pas les comportements par des TODO, des mocks permanents ou une démo.
    Prépare la revue de maquette 99.0 avant de demander sa validation ;
    ne suppose pas cette validation acquise. Lorsqu'elle est déjà consignée,
    avance dans les sous-étapes autorisées sans nouvelle permission de routine.
    Maintiens les quatre sections de suivi, exécute les contrôles adaptés,
    note les limites réelles, crée le commit détaillé et pousse vers origin.
    Ne touche pas aux autres features, au travail utilisateur ou au packaging.

Si un contrat confirmé est impossible avec le code actuel, décrire le cas exact et la preuve avant de proposer une alternative. Ne pas remplacer silencieusement la persistance par de la mémoire, le drag-and-drop par des boutons, l'historique de pages par des pistes précédentes ou la restauration en pause par une reprise sonore automatique.

## Commandes et critères de contrôle

Toutes les commandes sont exécutées depuis la racine du dépôt. Les tests nouveaux cités ci-dessous doivent être créés aux jalons indiqués avant leur lancement. Ne pas les annoncer comme passés pendant la préparation du plan.

Socle existant et transport :

    uv run pytest tests/unit/test_player_service.py tests/unit/test_playback_queue.py tests/unit/test_workspace_model.py tests/ui/test_player_views.py

Après 99.1 à 99.3 :

    uv run pytest tests/unit/test_playback_queue_state.py tests/unit/test_playback_queue.py tests/integration/test_playback_repository.py tests/integration/test_playback_session.py tests/integration/test_database_migrations.py tests/ui/test_playback_queue_ui.py tests/ui/test_playlists_ui.py

Après 99.6 et 99.7 :

    uv run pytest tests/unit/test_navigation_history.py tests/unit/test_workspace_model.py tests/ui/test_navigation_history_ui.py tests/ui/test_empty_selection.py tests/ui/test_browser_navigation.py tests/ui/test_column_selection.py tests/ui/test_metadata_editor.py

Recette de lecture et fermeture :

    uv run pytest tests/integration/test_mpv_playback.py tests/integration/test_runtime_shutdown.py tests/ui/test_player_views.py
    uv run python -m mtee --data-dir .local/validation/99

Le runtime libmpv est requis par les tests natifs ; une absence est un contrôle non réussi à déclarer. Les tests de service utilisent un backend déterministe ; ils ne remplacent pas l'écoute réelle. Ne pas modifier le runtime téléchargé ou les dépendances sans besoin démontré du périmètre.

Contrôles de code à la fin des changements :

    uv run ruff check src tests
    uv run ruff format --check src tests
    uv run pyright
    git diff --check

Noter séparément les éventuels diagnostics préexistants et vérifier qu'aucun diagnostic nouveau de 99 ne subsiste. Ne pas réparer des modules étrangers pour nettoyer toute la base. Un smoke-test depuis les sources peut compléter ces contrôles, mais ne remplace aucun parcours interactif.

## Reprise, incidents et Git

À chaque interruption, mettre à jour Progress et consigner le prochain sous-jalon exact, les commandes exécutées et les décisions restant ouvertes. Ne pas cocher une validation utilisateur, un test natif ou un push sans preuve. Aucun fichier audio personnel ni base de recette ne doit entrer dans Git.

Pour la migration, conserver la sauvegarde cohérente créée par `Database`. Ne jamais effacer ou recréer la base utilisateur pour faire passer un test. Un rollback de code après migration doit respecter le refus existant des schémas trop récents ; une restauration éventuelle se fait sur une copie et ne doit pas écraser des modifications ultérieures.

Avant un commit : `git status --short`, revue du diff, ajout explicite des fichiers 99, puis `git diff --cached --check` et revue du diff indexé. Faire `git fetch origin` et inspecter les écarts de `HEAD...origin/main`. Intégrer les changements compatibles sans push forcé ni écrasement du travail extérieur. Le commit documentaire initial ne contient pas de code fonctionnel. Les commits ultérieurs peuvent suivre les jalons du plan.

Sujet proposé pour la préparation : `docs(plan): define feature 9-13 execution plan 99`. Le corps doit indiquer les décisions utilisateur, les chemins inspectés, les contrôles documentaires réellement passés et l'absence d'implémentation. Écrire le message multiligne dans un fichier temporaire avec une here-string PowerShell non interpolée, puis utiliser `git commit --file`.

Après le push, faire `git fetch origin` et comparer `git rev-parse HEAD` à `git rev-parse origin/main`. Mettre dans le compte rendu le hash et la destination réellement vérifiés. Une erreur réseau ne requiert pas un nouveau commit ; contrôler puis réessayer le même push. Les contrôles de cette préparation portent sur les chemins/liens, l'encodage, la couverture des demandes et `git diff --check`.

## Progress

- [x] 2026-10-01 — Deux pages Notion lues, périmètre 9–13 identifié.
- [x] 2026-10-01 — Première série de réponses utilisateur consignée, destination et numéro 99 confirmés.
- [x] 2026-10-01 — Graphe consulté et actualisé, sources et tests pertinents inspectés.
- [x] 2026-10-01 — Réponses complémentaires Q1–Q4 consignées ; plan, contrats de file et matrice de recette finalisés.
- [x] 2026-10-01 — Contrôles documentaires : UTF-8, structure PLANS.md, couverture F9–F13, 28 chemins existants, 14 chemins futurs explicitement décrits, lien d'index et `git diff --check` vérifiés. Aucun test applicatif exécuté.
- [x] 2026-10-01 — 99.0 : socle inspecté, maquette préparée et revue utilisateur obtenue dans le chat (« Oui go »).
- [x] 2026-10-01 — Sous-étape 99.0 : maquette QML, lanceur, six captures et dossier de revue préparés ; rendu hors écran sans avertissement QML.
- [x] 2026-10-01 — Sous-étape 99.0 : validation utilisateur de la maquette reçue avant le backend.
- [x] 2026-10-01 — 99.1 : domaine d'occurrences, service et façade Qt reliés ; 22 tests ciblés passés, Ruff et Pyright ciblés verts.
- [x] 99.1 — Domaine et transitions de file implémentés et testés.
- [x] 2026-10-01 — 99.2 : migration 018, sauvegarde séquentielle et restauration en pause sur deux instances testées sur copies ; 18 tests ciblés de migration/session passés.
- [x] 99.2 — Persistance et restauration validées sur copies.
- [x] 2026-10-01 — 99.3 : ajout par menus de morceaux et playlists, file virtualisée, retrait et drag par occurrence ; 24 tests ciblés passés, Ruff et Pyright ciblés verts.
- [x] 99.3 — Menus et vues de file reliés et testés.
- [x] 2026-10-01 — 99.4 : 36 tests domaine/service et deux tests UI passés ; seuil 3 s, pause, double clic rapide, doublon manuel et Repeat all couverts.
- [x] 99.4 — Précédent validé aux bornes et en pause.
- [ ] 99.5 — Espace validé selon le focus et sur backend.
- [ ] 99.6 — Navigation arrière/avant validée par panneau et à la souris.
- [ ] 99.7 — Désélection et Info vide validés.
- [ ] 99.8 — Recette intégrée depuis les sources, rapport, commit et push vérifiés.

La preuve du commit et du push de préparation est fournie dans le compte rendu de livraison, après comparaison de HEAD et origin/main ; elle n'est pas précochée avant publication ni inscrite sous forme de hash autoréférentiel.

## Surprises & Discoveries

2026-10-01 — La Segmentation transforme « naviguer » en navigation entre morceaux. L'utilisateur précise une navigation entre pages. La réponse humaine remplace cette interprétation.

2026-10-01 — `Main.qml::textInputFocused()` inclut `AbstractButton`, ce qui désactive Espace après certains changements de focus. C'est une cause plausible à reproduire, pas la preuve que tous les cas intermittents proviennent de là.

2026-10-01 — `PlayerService.previous()` n'observe pas la position ; le seuil demandé est donc absent du chemin lu. `PlaybackQueueView.nextOnly` masque uniquement la ligne courante. La recette de file doit vérifier le contenu exact des lignes à venir.

2026-10-01 — Les occurrences de playlist et les morceaux locaux n'ont pas systématiquement la même identité. La file avec doublons exige encore une identité d'occurrence indépendante. Une conversion ou une déduplication involontaire ferait perdre le comportement demandé.

2026-10-01 — Le socle de tests est déjà imparfait avant les changements fonctionnels de 99 : `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it` échoue (`trackIds` vide au lieu de deux IDs) dans la passe de 15 tests unitaires. La passe initiale qui incluait `tests/ui/test_player_views.py` s'est interrompue sur une violation d'accès Windows pendant une écriture asynchrone de disposition. Ces résultats ne sont pas attribués à la maquette isolée.

2026-10-01 — Avant l'intégration 99.1, la branche `main` contient de nouveaux commits indépendants pour les plans 98 et 100. Le travail 99 se base sur ce HEAD et ne modifie pas leurs fichiers. Le graphe étant construit sur un SHA précédent, ses résultats ont été vérifiés dans les sources.

2026-10-01 — Le contrôle natif `test_mpv_playback.py` a produit un diagnostic fatal Windows `0xe24c4a02` au `MpvBackend.close()` tout en terminant avec un code de sortie zéro. Ce signal ne permet pas de déclarer la recette audio native validée ; il sera repris à la recette intégrée. Le smoke-test applicatif depuis les sources avec `.local/validation/99` a quitté avec code zéro.

2026-10-01 — Le test d'ordre de sélection 99.3 a d'abord supposé l'ordre d'insertion des fichiers ; la liste visible était triée autrement. Il compare désormais à l'ordre effectivement affiché et sélectionne les lignes dans l'ordre inverse pour contrôler le réordonnancement du lot.

## Decision Log

2026-10-01 — Utilisateur : `Add to queue` au clic droit, FIFO et lots, doublons, conservation, retrait et réordonnancement sans commande de vidage ; Espace hors écriture ; souris pour les pages ; Précédent à trois secondes avec lecture en sortie de pause ; vide désélectionnant le panneau actif et Info vide ; plan unique 99 dans le dépôt.

2026-10-01 — Utilisateur, seconde série : conserver les ajouts même après un clic sur un autre morceau ; préserver leur ordre en Shuffle ; laisser Repeat one boucler ; confirmer le retour au dernier morceau en Repeat all au début de liste ; restaurer courant/position en pause ; drag-and-drop entre les sons de la file et retrait au clic droit ; toutes les pages, historique par panneau et restauration recherche/défilement/sélection.

2026-10-01 — Codex : identité propre d'occurrence, persistance dédiée, writer séquentiel, checkpoint audio de cinq secondes et tests séparant domaine, service, Qt et backend natif. Les détails de représentation et les conventions d'ordonnancement sont explicités pour éviter à Luna de redéfinir la file. L'historique de pages reste en mémoire de session, sans nouvelle exigence de persistance après fermeture. La file audio, elle, est persistée comme demandé.

2026-10-01 — Codex : le prototype 99.0 utilise les jetons `Theme` et les composants `AppMenu` existants, mais garde ses données dans QML. Cette séparation permet la revue sans anticiper le domaine de file ni toucher aux données utilisateur.

2026-10-01 — Utilisateur : « Oui go » après présentation de la maquette 99.0 ; la revue visuelle est validée et le développement peut avancer.

2026-10-01 — Codex : `QueueState` garde une identité d'occurrence pour les transitions et projette `PlaybackState.track_ids` pour les anciens appelants. La source et les lignes de rendu restent résolues par le service au chargement ; le domaine n'ouvre aucun fichier. Les opérations QML ciblent `entry_id` via la façade Qt.

2026-10-01 — Codex : migration 018 dédiée, JSON versionné avec validation stricte et séquence d'écriture ; un seul worker persiste les snapshots. La fermeture vide les écritures avant l'arrêt du backend, y compris lorsque la sauvegarde échoue. La restauration envoie Pause au backend avant Load, puis borne la position une fois la durée et Seekable connus ; une nouvelle session invalide le seek différé.

2026-10-01 — Codex : 99.3 prépare les lots dans `JobService` et applique les réponses dans l'ordre des requêtes, même si les workers finissent dans un autre ordre. La vue de file utilise un `ListView` unique pour les occurrences à venir ; courant et historique sont ses en-tête et pied. Les mutations ciblent `entry_id`.

2026-10-01 — Codex : 99.4 privilégie le seek demandé encore en attente, sinon lit la position native puis celle publiée, pour trancher à 3 secondes. Un redémarrage publie immédiatement zéro afin qu'un second clic rapide atteigne l'occurrence précédente. En Repeat all, un retour au début réactive la dernière occurrence du contexte et conserve les ajouts manuels en attente.

## Outcomes & Retrospective

Les deux séries de décisions utilisateur sont intégrées. Le plan décrit les structures et interfaces à créer, les changements dans les sources existantes, neuf jalons, les tests à créer/étendre et une matrice de recette couvrant les cinq features. La maquette 99.0 a été approuvée ; le domaine 99.1, la persistance 99.2 et les commandes UI de file 99.3 sont implémentés et testés. Les commandes de lecture et de navigation, la désélection et la recette intégrée restent à réaliser. Aucune distribution Windows n'est demandée.

Révision du 2026-10-01 : rédaction après lecture des sources et deux séries de réponses utilisateur ; Q1–Q4 résolues, algorithmes de file et restauration définis, navigation de toutes les pages et matrice de recette ajoutées.

Révision du 2026-10-01 : exécution du jalon 99.0 jusqu'à la revue. `docs/ux/mockups/Queue99Review.qml`, `scripts/review_queue_99.py`, six captures et `docs/ux/review-99-queue.md` créés. La validation utilisateur reste ouverte ; les jalons fonctionnels ne sont pas commencés. Prochaine action : recueillir la décision de revue, puis exécuter 99.1.

Révision du 2026-10-01 : approbation de la maquette reçue ; 99.1 implémenté dans le domaine, le service et la façade Qt, avec transitions et tests ciblés. Prochaine étape : 99.2, persistance et restauration en pause.

Révision du 2026-10-01 : 99.2 implémenté avec migration, dépôt, writer et chargement en pause. Prochaine étape : 99.3, menus et file visible ; la validation native complète reste réservée à 99.8.

Révision du 2026-10-01 : 99.3 implémenté et testé depuis les sources, avec clic droit, lot ordonné, playlist entière, retrait, drag et annulation Escape. Prochaine étape : 99.4, seuil Précédent et tests des bornes.

Révision du 2026-10-01 : 99.4 implémenté et testé aux cinq positions demandées, en lecture et pause ; les commandes de l'îlot, du plein écran et Ctrl+Left passent par la même méthode. Prochaine étape : 99.5, Espace et focus.
