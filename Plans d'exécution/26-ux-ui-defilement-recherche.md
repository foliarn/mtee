# 26 — Défilement, scrollbars et recherche de dossier

## Résultat attendu et prérequis

Accélérer légèrement la navigation à la molette, conserver les scrollbars visibles suffisamment longtemps et rendre prévisible le focus de recherche. Garder l’en-tête fourni par l’utilisateur : champ de recherche à sa place en haut à droite, commandes List, Artwork et Choose columns groupées en bas à droite. Ne pas refaire le champ ni déplacer les commandes sur sa rangée. Lire les plans 23 et 25 ; la stabilité des ancres doit être disponible pour distinguer un déplacement demandé d’un saut de modèle.

Décision utilisateur du 28 septembre 2026 : Échap et clic ailleurs retirent le focus de recherche mais conservent son texte et les résultats filtrés. Le clic sur un morceau du même listing conserve le focus si le champ l’avait déjà. Le tri de colonnes est une commande indépendante ; sortir du champ ne réinitialise pas le tri. Le 29 septembre, l’utilisateur confirme l’apparence actuelle du champ et les commandes groupées ; la capture jointe fait référence pour leur disposition.

## Sources et état actuel

Lire `src/mtee/qml/components/TrackListView.qml`, `ExplorerPane.qml`, `TrackRow.qml`, `src/mtee/qml/Mtee/ThinScrollBar.qml`, `Main.qml` et `src/mtee/models/workspace_model.py`. Lire les tests `tests/ui/test_player_views.py`, `test_incremental_scan_and_scroll.py` et `tests/unit/test_workspace_model.py`.

La recherche est déjà ancrée en haut à droite de l’en-tête et les boutons sont ancrés en bas à droite, comme sur la capture utilisateur ; cette disposition et le style du champ sont conservés. Le champ n’a pas de traitement explicite d’Échap. `press()` de la liste force le focus de la vue. `ThinScrollBar` fait dépendre son opacité de `active` et `hovered`, avec un fondu de 160 ms mais sans délai de maintien dédié.

## Jalon 26.1 — Maquette locale de l’en-tête

Conserver la composition et le style existants tels qu’ils apparaissent sur la capture utilisateur : champ en haut à droite, titre et résumé à gauche, commandes en bas à droite. La maquette précédente qui rapprochait recherche et boutons reste une proposition non retenue ; elle ne doit pas être branchée dans l’application.

`docs/ux/review-ux-ui-2026-09.md` conserve les propositions historiques et consigne la décision. L’utilisateur a validé la direction visuelle ; ne pas changer la palette, la police, la taille, les boutons ni le texte du champ.

## Jalon 26.2 — Focus et raccourcis

Faire gérer Échap par le champ lui-même : quitter sa saisie sans effacer le texte, sans modifier le filtre et sans basculer lecture/pause. Restaurer le focus vers le conteneur de liste du même groupe. Le liseré actif et le caret doivent disparaître.

Un clic sur le fond, la sidebar, une autre activité, un onglet, une commande ou un autre éditeur retire le focus et laisse le contrôle cliqué agir dès ce premier clic. Utiliser la propagation et les gestionnaires de focus Qt existants ; éviter un grand `MouseArea` qui intercepterait tous les boutons ou imposerait un second clic.

Un clic gauche simple dans une ligne du même listing sélectionne cette ligne mais préserve la saisie si le champ était actif. La ligne n’acquiert pas simultanément un faux focus clavier. Si le champ n’avait pas le focus, la navigation clavier de la liste conserve son comportement habituel. Le double-clic active la lecture ; les boutons et menus contenus dans la ligne suivent leurs propres contrats de focus. Ctrl/Shift sélectionnent correctement sans transformer les caractères saisis en commandes de lecteur.

Pendant la saisie, Espace reste un espace ; Enter ne lance pas involontairement un morceau, les flèches naviguent dans le texte et Ctrl+A sélectionne le texte. Après Échap, les raccourcis du listing reprennent. Le test existant `test_space_goes_to_search_while_a_track_is_playing` est une protection à conserver. Un focus retiré ne doit pas être repris à chaque rafraîchissement du workspace ou changement de position du lecteur.

La recherche est propre à l’onglet et ne filtre pas l’arbre. Le cas d’un double-clic dans l’arbre sur une cible masquée est traité explicitement au plan 25 ; ne pas le confondre avec un simple clic ailleurs.

## Jalon 26.3 — Molette et visibilité des barres

Appliquer le facteur 1,25 aux crans de molette dans l’arbre et les vues List/Artwork du dossier, en respectant le nombre de lignes défini par Windows. Centraliser le traitement dans un composant réutilisable ; ne pas disperser des constantes dans les vues.

Les deltas en pixels du pavé tactile sont transmis sans gain. Pour les crans, le nouveau gestionnaire applique une seule variation à 1,25 et borne aux extrémités ; les gestes horizontaux ne sont pas interceptés. Ne pas détourner une molette destinée à un contrôle tel que le volume.

Le périmètre d’accélération est la sidebar Explorer et les vues List/Artwork du dossier. Les autres vues conservent leur vitesse, sauf nécessité démontrée et documentée. La scrollbar partagée peut recevoir le maintien commun si ses usages restent cohérents.

Après la fin du défilement, le curseur de scrollbar reste visible au moins 1 000 ms. Valeur d’implémentation proposée : temporisation de 1 200 ms, puis fondu de 160 ms existant. Relancer le délai à chaque nouvelle interaction. Survol, appui et glissement maintiennent sa visibilité ; son utilisation reste possible jusqu’à la fin du geste. Quand aucun défilement n’est possible, ne pas afficher une barre inutile. Les timers sont locaux aux composants et disparaissent avec eux.

## Vérifications et commandes

L’utilisateur demande de ne pas exécuter la suite de tests ; il effectuera sa recette. Compiler et reconstruire l’EXE à la fin du jalon. Les tests UI prévus ci-dessous sont reportés à sa recette.

Commande de tests documentée, non exécutée à la demande de l’utilisateur :

    uv run pytest tests/ui/test_search_focus.py tests/ui/test_scroll_interactions.py tests/ui/test_player_views.py tests/ui/test_incremental_scan_and_scroll.py

Les tests de GUI ne remplacent pas la recette avec une molette physique et, si disponible, un pavé tactile. Noter les périphériques réellement utilisés. Vérifier 100 % et 150 % d’échelle Windows pour l’en-tête ; aucun chevauchement, aucune zone de clic inaccessible. La recherche reste filtrée après Échap, mais son état de focus est visuellement retiré.

Clore avec une compilation de l’EXE et `docs/validation/ux-ui-26.md`. Ne pas lancer l’EXE ni faire la recette manuelle ; l’utilisateur le fera.

## Livraison et reprise

Livrer en trois jalons cohérents : disposition approuvée, focus, défilement. Sujet proposé : `fix(ui): align folder search and improve scrolling and focus`. En cas de régression de raccourci, conserver les règles explicites du champ et retirer uniquement le gestionnaire fautif. Ne pas régler une erreur de focus en supprimant la recherche ou la navigation clavier.

## Progress

- [x] 2026-09-28 — Sources et décision de conservation du filtre documentées.
- [x] 2026-09-28 — Maquettes d’en-tête rendues à 1440 × 900, 1280 × 720 et en groupes partagés de 415 px.
- [x] 2026-09-29 — Disposition actuelle confirmée par l’utilisateur ; la recherche reste inchangée et ses commandes gardent leur position.
- [x] 2026-09-29 — Échap, focus de navigation, raccourcis et défilement ciblé implémentés ; les tests ne sont pas exécutés à la demande de l’utilisateur.
- [x] 2026-09-29 — QML lint sans erreur, EXE Windows vérifié et rapport consigné dans `docs/validation/ux-ui-26.md`.
- [ ] Commit et push terminés.

## Surprises & Discoveries

2026-09-28 — Le champ conserve son filtre indépendamment du focus ; le correctif doit respecter cette séparation. Le clic de ligne force aujourd’hui le focus de la liste, ce qui doit changer seulement dans le cas demandé.

## Decision Log

2026-09-28 — Utilisateur : garder le texte et les résultats lorsqu’on quitte la recherche. Codex : proposer 1,25 pour la molette à crans et 1 200 ms pour le maintien, à vérifier sur périphériques réels.

2026-09-28 — Codex : maquettes statiques rendues dans le thème natif, voir `docs/ux/review-ux-ui-2026-09.md`.

2026-09-29 — Utilisateur : ne pas changer le champ de recherche, uniquement conserver son emplacement de la capture ; garder les boutons dans leur disposition précédente. L’utilisateur confirme que le filtre doit survivre à Échap et aux clics ailleurs.

## Outcomes & Retrospective

La composition d’en-tête existante correspond à la référence utilisateur et est conservée. Le code traite le focus de recherche, les raccourcis, le gain des crans de molette et le maintien des scrollbars. La compilation Windows sera consignée dans `docs/validation/ux-ui-26.md` ; tests automatisés et recette manuelle sont reportés selon la demande de l’utilisateur.
