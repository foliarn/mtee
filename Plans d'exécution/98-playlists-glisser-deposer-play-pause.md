# Étape 98 — Playlists, glisser-déposer et Play/Pause des listes

ExecPlan préparé le 2026-10-01 pour les features **2, 3 et 4** de la page Notion Segmentation. Appliquer `PLANS.md`. Ce document est le livrable de planification demandé ; sa préparation ne vaut ni implémentation, ni validation d'une maquette. Il doit être exécutable par Luna avec les fichiers versionnés, sans dépendre de la mémoire du chat.

## Objectif et résultat observable

Créer une playlist en un clic, avec un nom automatique calculé sur le nombre de playlists existantes, puis ouvrir sa page. Modifier une playlist en cliquant sur son titre ; rendre explicite le clic déjà disponible sur sa pochette. Pendant le déplacement de morceaux, montrer les morceaux tenus par la souris et leur destination. Dans les listes de morceaux, placer Play/Pause à gauche des pochettes et conserver une icône cohérente avec le lecteur, sans déplacement de contenu au survol.

Le périmètre comprend les vues List et Artwork pour le glisser-déposer. Le déplacement de Play/Pause concerne les lignes des listes de morceaux sur toutes les pages qui les utilisent, sauf la file d'attente. Il ne crée pas un nouveau lecteur sur les cartes Artwork. La file d'attente appartient au [plan 99](99-controles-lecture-file-navigation.md) et conserve ses composants et ses règles propres.

## Sources et décisions utilisateur

Sources consultées, captures comprises : [MTEE — fixes & idées](https://app.notion.com/p/3e5d502f2cc0804da316d980908fd518) et sa sous-page [Segmentation](https://app.notion.com/p/3ebd502f2cc0819bb756ce582ee4fc4c). Les réponses directes de l'utilisateur du 2026-10-01 ci-dessous précisent ces notes. Ne pas appliquer les autres features de ces pages. Le [plan 34](34-playlists-locales.md) reste la référence pour les playlists existantes, sauf les interactions explicitement remplacées ici.

| ID | Exigence confirmée |
|---|---|
| P2.1 | Retirer le blanc entre les actions du menu « + » de Playlists. Conserver les actions existantes et leur ordre. |
| P2.2 | « New playlist » crée immédiatement la playlist puis l'ouvre. Aucune fenêtre de saisie du nom, aucun passage automatique en édition. |
| P2.3 | Nom : `Untitled playlist NN`, où NN est le **nombre de playlists présentes + 1**, tous noms et dossiers confondus. Au moins deux chiffres : 01, 02, …, 99, 100. |
| P2.4 | Les suppressions diminuent ce total. Avec 34 playlists, en supprimer une puis en créer une donne `Untitled playlist 34`. `Liked tracks` est exclu ; les noms identiques sont acceptés. Il ne s'agit ni d'un compteur historique, ni du premier suffixe libre. |
| P2.5 | Même comportement depuis tous les points d'entrée de création, notamment le menu d'ajout : créer, ajouter la sélection concernée, puis ouvrir la nouvelle playlist. |
| P2.6 | Retirer le bouton d'en-tête « Edit playlist ». Cliquer sur le titre de la playlist ouvre le formulaire d'édition existant. |
| P2.7 | Survoler la grande pochette l'assombrit et affiche une invitation à la modifier. Cliquer conserve le sélecteur d'image actuel. Interface anglaise : `Change cover`. |
| P3.1 | Pendant le glisser-déposer, une étiquette suit la souris et indique titre et artiste. Avec N morceaux : premier titre/artiste et N−1 autres morceaux. |
| P3.2 | Entourer la playlist cible avec la couleur d'accent de MTEE ; montrer une ligne d'insertion pour le changement d'ordre. Les trois éléments s'inspirent des captures Spotify fournies. |
| P3.3 | Couvrir l'ajout à une playlist et le réordonnancement dans une playlist, depuis List et Artwork, pour un ou plusieurs morceaux. |
| P4.1 | Dans les listes, placer Play/Pause à gauche de la pochette. Conserver son emplacement vide sur les autres lignes afin que rien ne se décale. |
| P4.2 | Montrer le bouton au survol et le garder visible sur le morceau actif, même en pause. Icône Pause si le morceau joue, Play s'il est en pause ; le survol ne change jamais cette décision. |
| P4.3 | Appliquer cette règle aux listes des dossiers, playlists et Liked tracks, y compris les résultats filtrés et les panneaux divisés. Exclure la file d'attente. |

Le bouton d'en-tête et l'entrée contextuelle « Edit playlist » sont distincts. P2.6 remplace le bouton visible dans l'en-tête ; le menu contextuel existant reste accessible. Le titre et la pochette de la vue système `Liked tracks` restent non modifiables, conformément à son fonctionnement actuel.

Les captures sources montrent : trois actions de création/import séparées par un blanc inutile ; une fenêtre « New playlist » à supprimer de ce parcours ; une étiquette de déplacement titre/artiste, un contour de playlist et un trait d'insertion ; enfin un Play situé à droite qui devient Pause uniquement au survol. Cette description et la table sont le contrat durable si les URL temporaires des images Notion expirent.

## Progress

- [x] 2026-10-01 — Lire les deux pages Notion, inspecter les six captures pertinentes et recueillir les réponses utilisateur.
- [x] 2026-10-01 — Vérifier les sources, les tests pertinents, les contrats de persistance et les limites du glisser-déposer actuel.
- [x] 2026-10-01 — Rédiger le plan 98 et ses critères de recette pour Luna.
- [x] 2026-10-01 — 98.0 : état du dépôt, schéma 017, plans 34/99 et tests relevés ; fixture synthétique définie pour 98.2.
- [x] 2026-10-01 — 98.1 : maquette QML, lanceur et captures hors écran/native préparés et inspectés.
- [ ] 98.1 — Validation explicite de la maquette par l'utilisateur avant le code fonctionnel.
- [ ] 98.2 — Livrer la création immédiate, le menu compact et l'édition par titre/pochette.
- [ ] 98.3 — Livrer le placement et les états de Play/Pause dans les listes.
- [ ] 98.4 — Livrer le glisser-déposer avec retour visuel, lots et vue Artwork.
- [ ] 98.5 — Effectuer la recette intégrée depuis les sources, documenter les preuves, committer et pousser.

## Surprises & Discoveries

Le dépôt contient déjà l'implémentation des playlists du plan 34. Son index conserve une description de préparation plus ancienne : pour l'état réel, lire les sources et le suivi du plan 34. Le HEAD observé pendant l'étude est `bf37679` ; revérifier au début de l'exécution.

`PlaylistsPane.qml` place une entrée `Resume interrupted import…` entre New folder et Import playlist. Elle utilise `visible: false` lorsqu'aucun import n'est à reprendre, tandis que `AppMenuItem.qml` impose une hauteur implicite de 28. C'est une cause possible du blanc observé ; elle reste à reproduire dans une fenêtre Qt. La correction ne doit pas supprimer l'accès aux imports interrompus.

`PlaylistDialogs.qml` reçoit actuellement `playlistCreationRequested`, ouvre le formulaire `create`, puis appelle `PlaylistsModel.create(name, folder, tracks)`. `WorkspaceModel.attach_playlists` relie déjà `playlistCreated` à `openPlaylist` : réutiliser cette ouverture après succès, sans ouvrir une seconde fois.

Le nom de playlist n'est pas unique en base : la migration 016 utilise `playlist_id` comme clé primaire. `Liked tracks` provient d'une table séparée. Le décompte demandé peut être obtenu par `COUNT(*) FROM playlists`, sans migration et sans compteur persistant.

`TrackRow.qml` crée un proxy de déplacement de taille 1 × 1 : il transporte des identifiants mais n'affiche aucune étiquette. Le delegate Artwork dans `TrackListView.qml` n'a pas de DragHandler. Le réordonnancement actuel de liste déplace une seule entrée avant une autre, sans position après la dernière ligne ni identité de playlist source dans la charge transportée.

`TrackRow.qml` choisit explicitement l'icône du morceau joué avec `(row.hovered ? "pause" : "play")`. Le défaut est donc présent dans la source. `playing` signifie ici « cette ligne correspond au morceau actif », tandis que `paused` vaut `!workspace.isPlaying` : ne pas confondre morceau actif et lecture en cours.

Le graphe code-review-graph a été actualisé puis interrogé. La recherche graphify a retrouvé les modèles mais contient aussi des informations historiques ; elle ne prouve pas les comportements QML. Les constats ci-dessus viennent des fichiers lus. Aucun parcours interactif ni test applicatif n'a été exécuté pendant cette préparation documentaire.

2026-10-01 — Exécution 98.0 : HEAD `189dd1f` sur `main`, aligné sur `origin/main` au début ; `.gitignore`, `AGENTS.md`, `.agents/`, `.codex/` et `skills-lock.json` portent toujours des travaux extérieurs. Le schéma le plus récent est `017_playlist_imports_compatibility.sql`. Les tests nommés par 98 existent, sauf les nouveaux tests `*_98.py` à créer aux jalons prévus. Le plan 34 est achevé ; la maquette du plan 99 attend aussi une validation. Le graphe a été remis à jour puis la source ciblée a été relue : le menu Resume reste une entrée masquée de hauteur implicite, la création passe par le formulaire et `TrackRow` choisit encore l'icône selon le survol.

2026-10-01 — Exécution 98.1 : douze scènes documentaires ont chargé et produit des captures sans avertissement QML. La revue visuelle initiale a montré des glyphes manquants dans les icônes Unicode et une barre de lecture de largeur nulle ; ces défauts ont été corrigés dans la maquette puis les captures concernées ont été refaites. Une capture native Windows a été produite. La maquette ne représente pas encore une interaction de drag réelle ; cette vérification appartient à 98.4.

## Decision Log

2026-10-01 — Utilisateur — Limiter les travaux aux features Notion 2, 3 et 4, avec le bonus d'édition par titre et de survol de pochette. Livrer le document dans `Plans d'exécution/`, numéro 98.

2026-10-01 — Utilisateur — Décompter toutes les playlists actuelles, nommées ou non, exclure Liked tracks, accepter les noms identiques et décrémenter implicitement le total lors des suppressions. Ouvrir la nouvelle playlist sans dialogue de nommage et ajouter la sélection lorsqu'elle existe.

2026-10-01 — Utilisateur — Retenir les trois indicateurs de déplacement, les sélections multiples, les vues liste et pochettes et le réordonnancement. Play/Pause apparaît au survol ou sur le morceau actif, dans un emplacement réservé ; la file est exclue.

2026-10-01 — Codex, décisions techniques de planification — Calculer le nom dans la transaction d'insertion ; conserver les noms explicites d'import/duplication ; utiliser les identifiants d'entrée pour l'ordre et les identifiants de morceau pour l'ajout. Un état de déplacement temporaire commun à la fenêtre porte les indicateurs, sans écriture de fichier ni nouvelle dépendance. Les choix de géométrie indiqués plus bas sont des propositions techniques à vérifier dans la maquette, pas des exigences supplémentaires de l'utilisateur.

2026-10-01 — Codex, exécution 98.1 — Réutiliser `Theme`, `Icon`, `CoverArt` et `PlaylistCover` pour la maquette isolée ; montrer la mosaïque avec quatre motifs fictifs et réserver 32 px avant les pochettes. Le lanceur fournit les scènes demandées plus les variantes Resume et pause. La fixture de 98.2 comportera six WAV synthétiques de plusieurs secondes, tags distincts, couvertures variées, un titre long, des dossiers virtuels et une référence absente ; son script refusera un dossier de données non vide.

## Outcomes & Retrospective

Le périmètre et les cas de numérotation sont clarifiés. Le présent document prépare l'exécution ; les fonctionnalités, la maquette et la recette restent à réaliser. La validation des anciennes maquettes du plan 34 ne valide pas automatiquement la nouvelle disposition de 98. Les contrôles documentaires et la publication de cette préparation seront rapportés dans le compte rendu ; les preuves applicatives futures iront dans `docs/validation/98-playlists-glisser-deposer-play-pause.md`.

2026-10-01 — La maquette 98.1 et son [dossier de revue](../docs/ux/review-98-playlists.md) sont prêts. Les comportements applicatifs 98.2–98.5 et A01–A24 restent non exécutés tant que la revue produit n'est pas explicitement validée. Aucun build d'EXE ni test libmpv n'a été effectué.

## Prérequis, limites et ordre de travail

Lire `AGENTS.md`, `PLANS.md`, les addenda applicables de `PLAN.md`, ce plan entier et le plan 34. Le plan 98 corrige le socle actuel ; sa numérotation ne signifie pas qu'il faut implémenter les plans historiques 35 à 97 ou les fonctions suspendues. Les features 1, 5 à 20 ne sont pas incluses. Le plan 99 peut évoluer séparément : ne pas changer les fonctions de file, d'Espace, de navigation ou de désélection dans 98.

Le travail demandé maintenant est documentaire. Lorsqu'une demande d'exécution arrivera, commencer par 98.0 puis 98.1. `PLAN.md` et `PLANS.md` exigent la revue des maquettes avant le code fonctionnel correspondant : préparer les éléments examinables, obtenir la validation, puis poursuivre 98.2 à 98.5. Les réponses de cadrage présentes dans ce document ne sont pas une validation de maquette.

Lors de la préparation, `.gitignore`, `AGENTS.md`, `.agents/`, `.codex/` et `skills-lock.json` portent du travail extérieur à cette demande. Réinspecter Git avant chaque modification ou commit. Ne pas indexer ces fichiers pour livrer 98. Des travaux concomitants, notamment le plan 99, peuvent toucher `Main.qml`, `TrackListView.qml`, `PlaylistsPane.qml` et `WorkspaceModel` : relire leur version courante, intégrer les changements compatibles et éviter les remplacements de fichiers entiers.

Garder Python 3.12, PySide6/QML, SQLite et les composants MTEE existants. QML ne lit ni n'écrit les fichiers et n'exécute aucune commande système. Les opérations de playlists suivent la file de jobs existante, hors du thread graphique. Ce plan n'ajoute ni migration, ni dépendance, ni conversion audio, ni téléchargement, ni intégration externe, ni build d'EXE.

## Carte des fichiers à lire et modifier

Les chemins de cette table existent à la préparation. Les nouveaux fichiers proposés sont nommés dans leur jalon de création.

| Fichier | Intervention attendue |
|---|---|
| `src/mtee/qml/components/PlaylistsPane.qml` | Compacter le menu, router la création dans un dossier, montrer le contour d'une cible de morceaux admissible. |
| `src/mtee/qml/Mtee/AppMenu.qml`, `AppMenuItem.qml` | Lire la géométrie des entrées masquées. Privilégier une correction locale au menu Playlists ; vérifier les autres menus si le composant commun change. |
| `src/mtee/qml/components/PlaylistDialogs.qml` | Retirer le parcours de nommage de création ; conserver édition, dossiers, import/export, ambiguïtés et choix d'image. |
| `src/mtee/qml/components/PlaylistHeader.qml` | Retirer le bouton d'édition, rendre le titre activable et ajouter le voile de survol de la grande pochette. |
| `src/mtee/qml/components/PlaylistCover.qml` | Composant partagé à préserver ; le voile spécifique à l'en-tête doit rester dans PlaylistHeader. |
| `src/mtee/qml/components/AddToPlaylistMenu.qml`, `TrackContextMenu.qml` | Vérifier tous les points d'entrée New playlist et leur sélection. |
| `src/mtee/models/workspace_model.py` | `addToNewPlaylist`, `localTrackIds`, `openPlaylist`, `reorderPlaylistBefore` ; nouveau contrat de réordonnancement de lot. |
| `src/mtee/models/playlists_model.py` | `create`, `confirmAmbiguity`, `requestUI`, `_receive`, `run`, `reorder` ; conserver la sérialisation et les signaux de succès. |
| `src/mtee/persistence/playlists_repository.py` | Décompte et insertion atomiques du nom automatique ; réutiliser le réordonnancement versionné. |
| `src/mtee/services/playlist_service.py` | Réutiliser les contrôles d'ajout et de doublons musicaux. |
| `src/mtee/domain/playlists.py` | Héberger une fonction pure de réordonnancement de lot si nécessaire. |
| `src/mtee/qml/components/TrackRow.qml` | Emplacement Play/Pause, états, source de déplacement et arrêt propre du geste. |
| `src/mtee/qml/components/TrackListView.qml` | Géométrie tableau/en-tête, payload commun, cibles d'insertion List/Artwork, sélection et réordonnancement. |
| `src/mtee/qml/Main.qml`, `components/EditorArea.qml`, `EditorGroup.qml`, `Sidebar.qml` | Propager une instance commune d'état visuel de déplacement jusqu'aux sources et cibles, si ce choix est retenu. |
| `src/mtee/models/demo_workspace.py` | Aligner seulement le nom et l'ouverture de la création de démonstration ; ne pas reconstruire la démo comme backend de playlists. |

Tests existants à lire : `tests/ui/test_playlists_ui.py`, `test_track_hover.py`, `test_column_selection.py`, `test_player_views.py`, `tests/unit/test_workspace_model.py`, `test_demo_scenarios.py`, `test_playlist_identity.py`, `tests/integration/test_playlists_repository.py` et `test_playlist_exchange.py`. Le premier attend actuellement une fenêtre de nommage : il faudra changer le parcours testé tout en conservant ses vérifications de persistance, ajout, recherche, lecture, pochette, déplacement et rechargement.

## Contrats détaillés

### Création et nom automatique

Une playlist est un enregistrement de la table `playlists`. Compter aussi celles des dossiers repliés, épinglées, importées et dupliquées. Compter chaque UUID une seule fois : les épingles et l'arbre sont deux présentations possibles du même objet. Les dossiers virtuels, les likes et les opérations d'import non finalisées ne sont pas des playlists supplémentaires.

La formule est `f"Untitled playlist {count + 1:02d}"`. Ne pas extraire les suffixes des noms existants, mémoriser un compteur de création ou chercher un nom libre. Exemples : zéro playlist donne 01 ; onze playlists aux noms libres donnent 12 ; trente-trois playlists, dont une nommée Untitled playlist 34, donnent une nouvelle Untitled playlist 34 avec un UUID distinct. Renommer ou déplacer une playlist ne modifie pas le compte. Après redémarrage, calculer de nouveau depuis la base.

Proposition d'interface précise : autoriser `name: str | None` dans `PlaylistsRepository.create`. `None` signifie nom automatique ; une chaîne conserve le contrat actuel de validation de `playlist_name`. Effectuer le COUNT et l'INSERT dans le même `Database.transaction()` existant, qui utilise `BEGIN IMMEDIATE`. Ne pas imbriquer deux appels à `Database.transaction`, qui ne gère pas de savepoints. Les imports et duplications continuent de fournir leur nom explicite.

Exposer `PlaylistsModel.createUntitled(folder: str, track_ids: list)` comme slot QML ; factoriser le travail commun avec `create(name, folder, track_ids)` dans une méthode privée. Calculer le nom dans le job, au moment de l'insertion, jamais depuis le snapshot QML `_playlists`. Ainsi deux clics en attente ne calculent pas le même total obsolète. Garder le verrou et la file `run()` existants.

Préserver l'ajout via `PlaylistService.add`, la suppression compensatrice de la nouvelle playlist en cas d'échec et la confirmation existante des doublons musicaux incertains. « Sans fenêtre » concerne la saisie du nom ; cela n'autorise pas à supprimer les contrôles d'ambiguïté déjà validés au plan 34. Si une confirmation est requise, mémoriser le mode automatique, le dossier et le lot propres à la demande. Une reprise recalcule le total réel et ne conserve pas un numéro réservé. Une annulation n'ouvre pas de playlist et ne laisse pas d'objet partiellement créé.

Capturer les arguments de chaque demande pour que deux jobs successifs ne partagent pas accidentellement le même dictionnaire `_ambiguity`. Publier `playlistCreated(id)` seulement après le succès complet et le rafraîchissement du modèle. L'ouverture existante dans WorkspaceModel reste l'unique ouverture de page. Fermer le menu de création/ajout qui masquerait la page après création réussie ; les coches d'ajout à une playlist existante gardent leur fonctionnement actuel sans fermeture automatique.

Router : le « + » de la sidebar, « New playlist here » d'un dossier, « New playlist » du menu d'ajout et tout appel existant de `WorkspaceModel.addToNewPlaylist`. Pour le dossier, conserver son identité cible. Pour une sélection, convertir ses identifiants d'entrée vers les UUID locaux avant d'ouvrir un autre onglet. Ne pas renommer rétroactivement les playlists existantes.

### Édition, pochette et menu compact

Cliquer ou activer au clavier le titre de la grande page ouvre `requestUI("edit", playlist_id, [])`, avec les mêmes champs et la même version que le bouton actuel. Garder les textes, dimensions et ellipses du titre. Enregistrer ou annuler conserve les règles existantes. Le menu contextuel continue de fonctionner.

Le voile de pochette couvre l'image entière, y compris une mosaïque ou un placeholder, uniquement lorsqu'elle est modifiable. Proposition de maquette : noir à 45 % et libellé blanc centré `Change cover`, transition courte d'opacité. Le voile ne doit pas bloquer le MouseArea ni rester présent après sortie de la souris. Il ne modifie pas les miniatures de sidebar ni les pochettes de morceaux. Conserver le sélecteur natif, les formats acceptés et le service de copie actuel.

Pour P2.1, reproduire d'abord le menu avec et sans import interrompu. Une entrée masquée doit occuper zéro hauteur effective dans la liste du Menu. Corriger localement ses contraintes de hauteur ou son insertion conditionnelle ; vérifier le résultat réel, car `visible: false` seul n'a pas suffi dans la capture. Lorsque l'entrée Resume est présente, elle occupe une ligne normale et reste activable. Ne pas retirer New folder, Import playlist ou Resume pour masquer le défaut.

### Play/Pause et géométrie des listes

Réutiliser le bouton existant et son `objectName: "trackPlayButton"`. Une seule commande Play/Pause par ligne. Créer un emplacement fixe avant les cellules du tableau ; proposition : largeur 32, égale au bouton existant, puis l'espacement de colonnes déjà calculé. Appliquer exactement la même réservation dans l'en-tête, `rowCells.x`, le calcul de largeur disponible pour Title et `totalWidth`. Ne pas enregistrer cette commande comme une colonne métier déplaçable/masquable.

Le bouton reste à gauche de la pochette quand les colonnes sont déplacées ; il reste disponible si les pochettes sont cachées. Le placement ne dépend pas de `visible`. Conserver l'espace sur toutes les lignes, y compris une ligne indisponible. Réduire la réservation des actions de droite seulement d'une largeur explicitement redistribuée, en gardant les actions cœur, info, ajout et Locate accessibles. Vérifier en-têtes, scroll horizontal, largeur minimale et panneaux divisés.

| Ligne | Hors survol | Au survol | Action |
|---|---|---|---|
| Morceau disponible non actif | Emplacement vide | Play | Lancer ce morceau par le parcours existant de la vue. |
| Morceau actif en lecture | Pause | Pause | Mettre en pause, sans reconstruire la file. |
| Morceau actif en pause | Play | Play | Reprendre au point courant, sans repartir de zéro. |
| Morceau indisponible | Emplacement vide | Emplacement vide | Aucune action Play ; Locate conserve sa place existante. |

En termes de propriétés actuelles : visibilité `available && (hovered || playing)` ; icône `playing && !paused ? "pause" : "play"`. L'état du lecteur décide de l'icône, pas le survol. Garder `toggleRequested` pour la ligne active et `activated` pour une autre ligne. Le bouton doit rester dans le calcul de survol de la ligne et ne pas initier un glisser-déposer lors d'un clic.

### Identités et état temporaire du glisser-déposer

Un `track_id` identifie le fichier local à ajouter ; un `entry_id` identifie la position d'un morceau dans une playlist. Les deux ne sont pas interchangeables. Le payload d'un geste doit être figé au démarrage après établissement de la sélection, dans l'ordre visible de la source. Déplacer un membre d'une multisélection transporte cette sélection ; déplacer une ligne non sélectionnée transporte ce morceau après la sélection normale existante.

Définir le payload avec `sourceTabId`, `sourcePlaylistId` (vide pour un dossier), `sourceGroupIndex`, `sourceVersion`, `entryIds`, `trackIds`, `title`, `artist`, `count`. Les IDs d'entrée servent au réordonnancement ; les IDs locaux disponibles servent à l'ajout. Ne jamais transporter des index de delegate comme identité durable. Les listes ne sont plus recalculées depuis `selectedIds` pendant le déplacement. Rejeter une source devenue périmée plutôt que déplacer un autre morceau.

Une entrée absente peut être réordonnée dans sa propre playlist avec son entry_id, comme le permet la source actuelle ; elle ne devient pas un fichier ajoutable à une autre playlist. Une sélection contenant des absences reste entièrement réordonnable ; son dépôt d'ajout sur une autre playlist est refusé explicitement si tout le lot ne peut être ajouté. Ne pas annoncer N morceaux dans l'étiquette puis en ajouter silencieusement moins.

Créer au jalon 98.4 `src/mtee/qml/components/TrackDragSession.qml` comme état temporaire QML de fenêtre, et `src/mtee/qml/components/TrackDragPreview.qml` comme étiquette purement visuelle. Une instance est détenue dans Main ; la passer par EditorArea → EditorGroup → TrackListView → TrackRow, et Sidebar → PlaylistsPane. Les noms sont proposés ; adapter si un composant équivalent existe à l'exécution, en documentant la correspondance. Ces objets ne font aucune persistance.

La session porte le proxy `Drag`, le payload immuable et les coordonnées de fenêtre. Elle distingue `begin`, `updatePosition`, `finishDrop` et `cancel`. Le proxy reste un enfant non rogné de la fenêtre pendant tout le geste, même lorsque le curseur quitte la liste pour la sidebar. Le delegate source n'est pas déplacé. Transformer les coordonnées avec `mapToItem` ; ne pas additionner les offsets de sidebar, scrolling ou écran à la main. L'étiquette ne capture pas la souris et ne masque pas la détection des cibles.

`finishDrop` demande un seul dépôt puis réinitialise la session. `cancel` utilise l'annulation du Drag sans appeler le code de dépôt. Échap, perte de capture, fermeture/changement de source et destruction du delegate annulent le geste. Si la fenêtre perd l'activation, annuler proprement. Sortir d'une cible enlève immédiatement son contour/trait. Le nettoyage doit être idempotent et un relâchement ultérieur après Échap ne doit rien écrire.

### Indicateurs et cibles

L'étiquette est une petite surface sombre, lisible, décalée du pointeur, avec titre et artiste. Texte anglais pour un lot : `Title — Artist · and 2 other tracks…` pour trois morceaux ; `and 1 other track…` pour deux ; pas de suffixe pour un seul. Le premier élément est le premier morceau du lot dans l'ordre visible. Utiliser le fallback d'artiste existant `Unknown artist`, ellipser les textes longs et borner l'étiquette dans la fenêtre. Conserver la couleur d'accent `Theme.primary` pour le contour de destination et le trait d'insertion ; ne pas introduire le vert de Spotify.

Sur la sidebar, une playlist manuelle admissible reçoit un contour lorsqu'elle peut accepter le lot. Le dépôt appelle le chemin existant `PlaylistsModel.add` une seule fois et conserve les règles de doublons musicaux. Un dossier, Liked tracks, une zone vide ou un payload non compatible ne reçoit pas de contour d'ajout et ne produit pas d'écriture. La navigation et le déplacement des playlists/dossiers via `mtee-playlist-node` restent indépendants.

Dans une playlist en ordre Custom sans filtre, montrer l'insertion avant/après une ligne selon la moitié verticale survolée. Dans Artwork, utiliser la moitié gauche/droite de la carte pour avant/après ; le trait vertical se place dans l'espace entre les cartes, y compris aux limites des rangées. Cette adaptation géométrique est une décision technique à montrer dans la maquette. Fournir aussi une cible de fin réelle, après le dernier élément, en List et Artwork. Une cible indique la position à laquelle le lot sera effectivement enregistré.

Le réordonnancement n'est admis que si la source et la destination sont la même playlist manuelle. Le simple ajout à une autre playlist se fait sur sa cible de sidebar et ajoute à la fin comme aujourd'hui ; ce plan ne crée pas un nouveau transfert entre listes ni un déplacement de fichiers. Pour une vue triée/filtrée, conserver le refus existant et le message `Switch to Custom order and clear search before reordering.` Ne pas effacer automatiquement le filtre ni changer le tri pour faire réussir un geste. N'afficher aucun trait qui promettrait une insertion interdite.

Réutiliser le défilement normal. Pour atteindre une destination hors champ pendant un geste, prévoir un défilement de bord borné dans la liste/grille/arborecence concernée, actif seulement au maintien près d'un bord. Son arrêt doit suivre sortie, dépôt ou annulation. Ne jamais reconstruire tout le modèle à chaque mouvement de souris ; seuls la position du proxy et l'indicateur changent.

### Réordonnancement de plusieurs entrées

Ajouter un contrat `WorkspaceModel.reorderPlaylistEntries(source, entry_ids, before_entry_id, expected_version)` ; une cible `before_entry_id` vide signifie la fin. Conserver `reorderPlaylistBefore` comme adaptateur si des appels existants en dépendent. Vérifier à nouveau le contexte, le mode Custom, l'absence de filtre et la version au dépôt, même si QML a déjà validé la cible.

Algorithme pur, proposé dans `domain/playlists.py` : prendre l'ordre complet actuel ; vérifier que les IDs déplacés sont uniques et appartiennent à cette playlist ; ordonner le bloc selon l'ordre source ; retirer ce bloc ; insérer le bloc avant l'ID cible restant, ou à la fin. Si la frontière de dépôt tombe dans le bloc lui-même, ne rien changer. Si l'ordre final égale l'ordre initial, ne pas écrire. Envoyer ensuite toute la permutation à `PlaylistsModel.reorder`, qui délègue au dépôt versionné existant. Il n'est pas nécessaire de changer le schéma ou la stratégie SQL d'ordinals.

Exemples normatifs pour l'ordre initial `[A, B, C, D, E]` : déplacer `[B, D]` avant E donne `[A, C, B, D, E]` ; déplacer `[B, D]` en fin donne `[A, C, E, B, D]` ; déplacer E avant A donne `[E, A, B, C, D]`. Déposer B dans son emplacement actuel ne modifie ni ordre ni version. Une version périmée ou un ID retiré pendant le geste est refusé, la vue se recharge et un message explique que la playlist a changé.

Une réorganisation de playlist n'altère pas la file déjà capturée ni la position de lecture. Garder la sélection sur les mêmes entry_ids après succès, même si leurs index ont changé. Les mutations de modèle et les signaux restent sur le thread Qt ; l'écriture passe par le job existant.

## Jalons d'exécution

### 98.0 — Relever l'état réel et préparer la recette

Depuis la racine du dépôt, relever branche, HEAD, status, schéma courant et état des plans 34/99. Interroger le graphe puis relire les fonctions nommées ci-dessus. Vérifier que les fichiers de test existent ; un ancien plan n'est pas une preuve de leur présence. Ne pas créer une migration simplement parce qu'un ancien texte en évoque une.

Définir les fixtures synthétiques à créer en 98.2 sous `.local/validation/98/`, ou dans `tmp_path` pour pytest : six vrais WAV de plusieurs secondes, titres/artistes explicites et distincts, pochettes variées, un nom très long, plusieurs dossiers virtuels, une playlist avec une référence absente. L'outil existant `scripts/create_browser_fixture.py` produit des WAV très courts et sans tags : il ne suffit pas à vérifier une pause/reprise observable. La maquette 98.1 utilise seulement ses données fictives en mémoire.

Résultat attendu : inventaire daté des écarts de code et des tests existants, aucune donnée personnelle modifiée, aucun changement fonctionnel à ce stade.

### 98.1 — Maquette ciblée et revue avant le code fonctionnel

Créer `docs/ux/mockups/Playlists98Review.qml` et `scripts/review_playlists_98.py`, sur le modèle des lanceurs de revue existants. Réutiliser Theme, IconButton, CoverArt et PlaylistCover. Les données sont inventées. Le lanceur à créer accepte `--scene <nom>`, `--width`, `--height` et `--output <png>` ; il produit une capture et un code non nul si QML ne charge pas. Sans `--output`, il ouvre la maquette native pour la revue interactive.

Créer les scènes `creation-menu`, `creation-opened`, `title-edit`, `cover-hover`, `drag-single`, `drag-multiple`, `drop-playlist`, `insert-list`, `insert-artwork`, `playback-states`. Elles doivent rendre visibles les trois changements sans construire les autres fonctions Notion. Montrer les variantes sur un écran usuel et à la taille minimale de l'application, avec un panneau divisé pour vérifier la géométrie des lignes.

Documenter les captures dans `docs/ux/review-98-playlists.md`, avec les correspondances P2/P3/P4 et les choix visuels techniques. Produire un état au repos, les survols et une comparaison Play/Pause actif. Vérifier une fois l'ensemble, corriger les défauts constatés puis confirmer la correction. Obtenir la validation explicite de cette maquette avant 98.2. Ne pas substituer un test hors écran à la revue demandée.

### 98.2 — Création, menu, titre et pochette

Modifier d'abord le dépôt et le modèle pour le nom automatique et son contrat d'erreur ; ajouter les tests de décompte. Brancher ensuite tous les points d'entrée, conserver l'ouverture sur signal de succès, et retirer le formulaire create du parcours normal. Adapter la démo sans utiliser son `_next_playlist` comme compteur de noms : l'identité reste unique, le nom dépend du nombre présent.

Créer `scripts/create_playlists_98_fixture.py` avec le contrat décrit en 98.5 pour permettre la vérification manuelle de chaque sous-jalon. Les tests automatisés utilisent leurs propres répertoires temporaires indépendants.

Corriger la géométrie du menu et modifier PlaylistHeader selon la maquette validée. Tester le menu en l'absence et en présence d'un import à reprendre. Le titre doit fonctionner avec un nom long, après renommage et après changement de pochette qui incrémente la version. Une annulation du choix d'image ne modifie rien.

Adapter `tests/ui/test_playlists_ui.py` : appeler New playlist, attendre la création automatique et l'ouverture, puis ouvrir l'édition par le titre pour renommer en Night drive si le test a besoin de ce nom. Supprimer uniquement les attentes de dialogue de création obsolètes. Ajouter des cas ciblés dans `tests/ui/test_playlist_creation_98.py` (à créer ici), et compléter `tests/integration/test_playlists_repository.py`.

Résultat attendu : toutes les voies de création suivent P2 ; changement de nom/pochette et persistance restent opérationnels. Tester avant commit du sous-jalon.

### 98.3 — Play/Pause sans déplacement des cellules

Appliquer le contrat de géométrie dans TrackRow et TrackListView, puis la table d'états. Mettre à jour les tests de survol qui recherchent le bouton à son ancienne position. Compléter `tests/ui/test_track_hover.py` et `test_column_selection.py` ; réutiliser le backend factice de `test_player_views.py` pour piloter play/pause de manière déterministe.

Mesurer la position de la pochette, du titre et des colonnes avant/après survol, pause et reprise : les coordonnées doivent rester identiques à largeur de fenêtre constante. Vérifier le cas pochettes cachées, titre déplacé ou masqué dans une playlist, noms longs et scroll horizontal. Vérifier le même track_id dans deux onglets : les icônes reflètent le même lecteur.

Résultat attendu : P4 vérifié sans toucher PlaybackQueueView, QueuePanel ou les comportements du plan 99. Un clic pause/reprise ne remet pas la position à zéro et un clic sur une autre ligne conserve le parcours de lecture existant.

### 98.4 — Glisser-déposer complet pour List et Artwork

Commencer par la fonction pure de réordonnancement de lot et ses tests dans `tests/unit/test_playlist_reorder_98.py` (à créer). Ajouter le contrat de WorkspaceModel et les vérifications d'appartenance/version. Conserver la permutation transactionnelle du dépôt.

Créer ensuite TrackDragSession/TrackDragPreview et leur propagation. Brancher la source List, puis celle d'Artwork, sur le même payload. Tester qu'une sélection multiple n'est pas réduite au morceau saisi et qu'un clic sur Play, cœur ou ajout n'initie pas un geste. Ajouter les cibles de sidebar, puis les insertions List/Artwork, les positions de fin, les annulations et le défilement de bord. Ne pas faire dépendre la visibilité du proxy de l'existence du delegate source.

Créer `tests/ui/test_track_drag_98.py` : envoyer de vrais événements de pression, déplacement au-delà du seuil et relâchement avec QTest, en réutilisant les techniques de `test_playlists_ui.py`. Vérifier à la fois l'indicateur pendant le geste et l'ordre persistant après dépôt. Les tests doivent exercer les deux vues, les lots et Échap ; appeler seulement le slot Python ne valide pas le geste QML.

Résultat attendu : étiquette visible du départ à la fin, contour uniquement sur une cible compatible, insertion identique à ce qui est montré, ordre restauré après relance, aucune mutation après annulation ou dépôt invalide.

### 98.5 — Recette intégrée et livraison

Réutiliser `scripts/create_playlists_98_fixture.py`, créé en 98.2, pour rendre le parcours manuel reproductible. Son contrat : `--data-dir <dossier neuf>` prépare la bibliothèque synthétique, les métadonnées et playlists décrites en 98.0 avec les dépôts/services existants, refuse d'écraser un dossier non vide, puis quitte. Les fichiers créés sont uniquement des données de validation. Prévoir des morceaux assez longs pour constater une pause sans atteindre immédiatement la fin.

Effectuer le parcours de recette ci-dessous depuis les sources, avec le vrai backend de lecture pour les pauses/reprises. Consigner les versions, commandes, résultats observés, captures et limites dans `docs/validation/98-playlists-glisser-deposer-play-pause.md`. Distinguer tests à backend factice, contrôles Qt hors écran et vérification en fenêtre native. Un test non effectué reste non effectué ; aucun build Windows n'est requis.

Mettre à jour Progress, Discoveries, Decision Log et Outcomes, puis publier conformément à la section Git. Les autres chantiers en cours ne doivent pas être déclarés achevés par cette recette.

## Cas d'acceptation obligatoires

| ID | Mise en situation | Résultat attendu |
|---|---|---|
| A01 | Menu +, aucun import interrompu. | New playlist, New folder et Import playlist se suivent sans ligne vide. |
| A02 | Menu + avec un import interrompu. | Resume est visible et utilisable, avec une hauteur normale. |
| A03 | Bibliothèque sans playlist ; créer depuis la sidebar. | Untitled playlist 01 est créée et ouverte sans fenêtre de nommage. |
| A04 | Onze playlists nommées, réparties en dossiers, certaines épinglées ; créer. | Untitled playlist 12. Ni les dossiers ni les apparitions épinglées ne gonflent le compte. |
| A05 | Trente-quatre playlists ; en supprimer une puis créer. | Untitled playlist 34, y compris si ce nom existe déjà. UUID distincts, aucune modification de l'homonyme. |
| A06 | Liker des morceaux, renommer/déplacer une playlist, redémarrer puis créer. | Seul le nombre de playlists persistantes intervient ; Liked tracks est exclu. |
| A07 | Deux créations rapidement demandées. | Deux objets créés dans l'ordre des jobs, noms calculés sur les comptes réellement insérés. |
| A08 | New playlist depuis le + d'un morceau, le menu d'une sélection et New playlist here. | Lot concerné ajouté une fois, dossier cible conservé, bonne page ouverte. |
| A09 | Ajouter un lot ambigu ou injecter une erreur lors de l'ajout initial. | Confirmation existante conservée ; annulation/échec sans playlist résiduelle ni ouverture fictive ; reprise cohérente. |
| A10 | Cliquer le titre, modifier nom/description, annuler puis enregistrer. | Formulaire existant ; annulation intacte, succès persisté ; bouton d'en-tête Edit playlist absent. |
| A11 | Survoler la grande pochette puis sortir/clique-annuler le sélecteur. | Voile et Change cover au survol seulement ; image inchangée après annulation ; mosaïque couverte de la même façon. |
| A12 | Morceau inactif, actif en lecture puis actif en pause, avec/sans survol. | Matrice P4 exacte ; mêmes positions de pochettes, titres et cellules dans tous les états. |
| A13 | Dossiers, playlists, Liked tracks, filtre, deux panneaux et pochettes masquées. | Même comportement de ligne ; file d'attente inchangée. |
| A14 | Clic Pause puis Play sur le morceau actif. | Pause/reprise au point courant ; la file en cours et son ordre restent identiques. |
| A15 | Saisir un morceau List puis Artwork et traverser vers la sidebar. | Étiquette titre/artiste visible, non rognée ; contour accent sur la bonne playlist ; un seul ajout. |
| A16 | Sélectionner trois morceaux dans un ordre de clic différent de l'ordre visible. | Étiquette du premier morceau visible + « and 2 other tracks… » ; lot ajouté/réordonné dans l'ordre visible. |
| A17 | Déposer avant le premier, entre deux éléments et après le dernier, List et Artwork. | Indicateur à la bonne frontière ; ordre sauvegardé identique à la proposition, y compris aux changements de rangée Artwork. |
| A18 | Déplacer un lot non contigu, puis déposer à sa place initiale. | Algorithme décrit respecté ; aucun doublon, aucune perte ; pas d'écriture si l'ordre ne change pas. |
| A19 | Geste sur une vue triée/filtrée, une autre playlist, un dossier ou Liked tracks. | Aucune insertion annoncée à tort ni mutation illégale ; message de retour à Custom order si nécessaire. |
| A20 | Échap, sortie de fenêtre, perte d'activation ou fermeture de l'onglet pendant le geste. | Tous les indicateurs disparaissent ; aucun dépôt tardif, aucune écriture. |
| A21 | Source modifiée/supprimée pendant un geste ; version de playlist périmée. | Rejet explicite et rafraîchissement ; aucune mauvaise entrée déplacée. |
| A22 | Liste/grille longue, défilement et source hors champ. | Étiquette stable ; indicateur suit la destination ; défilement de bord s'arrête au dépôt/annulation. |
| A23 | Réordonner une entrée absente puis tenter son ajout à une autre playlist. | Réordonnancement local conservé ; ajout incompatible refusé sans succès partiel silencieux. |
| A24 | Fermer puis relancer avec le même data-dir. | Noms, dossiers, éditions, couvertures et ordres persistés ; aucun état de drag restauré. |

Mesurer les états Qt et le contenu de la base, pas seulement la présence de chaînes dans le QML. Les captures servent à constater placement, lisibilité, clipping et indicateurs. Les tests de réordonnancement doivent comparer les UUID et les ordres attendus, pas seulement le nombre d'entrées. Vérifier l'intégrité des fichiers audio de fixture avant/après : aucune opération de ce plan ne doit changer leurs octets.

## Commandes et preuves

Exécuter depuis `C:\Users\flori\Desktop\dev\MTEE` en PowerShell. Adapter la racine si le dépôt est dans un autre checkout. Les scripts et tests portant 98 ci-dessous sont **à créer dans les jalons indiqués** ; leur commande n'est pas une preuve qu'ils existent déjà.

Avant modification :

    git status --short
    git branch --show-current
    git log -1 --oneline

Après synchronisation de l'environnement si elle est nécessaire :

    uv sync --locked

Après 98.1, exemple de capture avec le lanceur à créer :

    uv run python scripts/review_playlists_98.py --scene playback-states --width 1440 --height 900 --output docs/ux/playlists-98-2026-10-01/playback-states.png

Contrôles ciblés après les jalons correspondants :

    uv run pytest tests/integration/test_playlists_repository.py tests/integration/test_playlist_exchange.py tests/ui/test_playlist_creation_98.py tests/ui/test_playlists_ui.py
    uv run pytest tests/ui/test_track_hover.py tests/ui/test_column_selection.py tests/ui/test_player_views.py
    uv run pytest tests/unit/test_playlist_reorder_98.py tests/ui/test_track_drag_98.py tests/unit/test_workspace_model.py tests/unit/test_demo_scenarios.py
    uv run ruff check src tests scripts/review_playlists_98.py scripts/create_playlists_98_fixture.py
    uv run pyright
    git diff --check

Les tests UI peuvent utiliser le backend factice existant. N'annoncer aucun test libmpv natif à partir de leurs résultats. Un échec préexistant de Ruff/Pyright doit être distingué d'un échec introduit ; consigner la preuve et ne pas corriger du code sans rapport pour rendre artificiellement le contrôle global vert.

Recette applicative, avec le préparateur créé en 98.2 et un dossier neuf :

    uv run python scripts/create_playlists_98_fixture.py --data-dir .local/validation/98/manual-01
    uv run python -m mtee --data-dir .local/validation/98/manual-01

Après fermeture, relancer la seconde commande pour A24. Si le dossier existe déjà, le réutiliser pour le redémarrage ou choisir manual-02 pour une nouvelle fixture ; ne pas le supprimer automatiquement. Exercer A01–A24 et consigner les résultats réellement observés. Un smoke-test de chargement facultatif ne remplace pas ce parcours :

    uv run python -m mtee --data-dir .local/validation/98/smoke --smoke-test

Pour la préparation documentaire seule : vérifier titres, encodage UTF-8, liens locaux, existence des chemins indiqués comme existants, couverture des décisions et `git diff --check`. Les tests d'application et scripts futurs ne sont pas exécutés pour publier le plan.

## Reprise, erreurs et publication Git

Chaque création possède un UUID ; un homonyme n'est jamais une cible de remplacement. Une erreur de base ne doit pas ouvrir une page absente ni consommer un numéro historique. Une demande d'édition devenue périmée reprend le message de conflit existant. Une erreur de dépôt de drag nettoie l'affichage temporaire et recharge l'état persistant, sans modifier le fichier source ou la file de lecture. Ne pas rejouer automatiquement un lot après une erreur dont le résultat n'est pas connu.

Au redémarrage de Luna, lire Progress et les dernières découvertes, vérifier le dépôt et reprendre le premier sous-jalon incomplet. Ne pas refaire une maquette déjà explicitement validée et inchangée ; retrouver sa preuve dans le dossier de revue. Ne pas supposer qu'un commit suffit à prouver une recette.

Avant chaque commit, lire status et diff, indexer uniquement les fichiers du sous-jalon, puis inspecter `git diff --cached --check` et `git diff --cached`. La préparation documentaire peut être publiée séparément de l'implémentation. Exemples de sujets à adapter : `docs(plan): preparer le plan 98 playlists et interactions`, `fix(playlists): creer et ouvrir les playlists sans dialogue`, `fix(ui): stabiliser Play Pause a gauche des pochettes`, `feat(playlists): rendre visibles les depots et reordonner les selections`.

Écrire le corps du commit dans un fichier temporaire avec une here-string PowerShell non interpolée ; préciser problème, modifications, contrôles effectivement exécutés et limites. Utiliser `git commit --file <fichier>`. Ne pas ajouter globalement les données de recette ou les changements d'autrui.

Faire `git fetch origin`, inspecter `git log --oneline --left-right HEAD...origin/main`, puis publier sans push forcé. Sur main et sans divergence, utiliser `git push origin main`, puis `git fetch origin` et comparer `git rev-parse HEAD` à `git rev-parse origin/main`. Sinon documenter la branche réellement utilisée et intégrer prudemment les travaux compatibles avant de republier. Un échec réseau nécessite la vérification du distant, pas un nouveau commit du même contenu.

La livraison fonctionnelle se termine lorsque P2/P3/P4 et A01–A24 sont démontrés, la revue requise est consignée, les contrôles pertinents sont passés et le push est confirmé. Ne pas lancer `scripts/build_windows.ps1` ou `scripts/smoke_packaged.ps1` : aucun packaging n'est demandé.

## Consigne de reprise prête pour Luna

    Lis AGENTS.md, PLANS.md et Plans d'exécution/98-playlists-glisser-deposer-play-pause.md entièrement. Travaille seulement sur les features Notion 2, 3 et 4 et le bonus décrit dans ce plan. Vérifie les sources et les tests avant de modifier ; préserve les travaux extérieurs et le plan 99. Commence par le premier jalon incomplet. Prépare la maquette 98.1 et sa preuve avant sa revue, puis attends sa validation explicite avant le code fonctionnel correspondant. Après validation, exécute les sous-jalons dans l'ordre, maintiens le plan, teste chaque comportement et effectue la recette depuis les sources sur fixtures isolées. Termine les étapes réalisées par un commit détaillé et un push vérifié. Ne crée pas de migration, dépendance ou fonction supplémentaire sans nécessité démontrée dans le périmètre. Aucun build d'EXE. Si une décision produit nouvelle est nécessaire, explique le cas précis et pose une question plutôt que l'inventer ; consigne les adaptations techniques ordinaires et continue.

Note de révision — 2026-10-01 : création du plan après clarification du décompte, des noms identiques, des vues couvertes et des interactions d'édition ; périmètre documentaire, aucun comportement applicatif modifié.
