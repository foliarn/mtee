# 26 — Défilement, scrollbars et recherche de dossier

## Résultat attendu et prérequis

Accélérer légèrement la navigation à la molette, conserver les scrollbars visibles suffisamment longtemps et rendre prévisible le focus de recherche. Aligner `Search this folder` avec les boutons List, Artwork et Choose columns. Lire les plans 23 et 25 ; la stabilité des ancres doit être disponible pour distinguer un déplacement demandé d’un saut de modèle.

Décision utilisateur du 28 septembre 2026 : Échap et clic ailleurs retirent le focus de recherche mais conservent son texte et les résultats filtrés. Le clic sur un morceau du même listing conserve le focus si le champ l’avait déjà. Le tri de colonnes est une commande indépendante ; sortir du champ ne réinitialise pas le tri.

## Sources et état actuel

Lire `src/mtee/qml/components/TrackListView.qml`, `ExplorerPane.qml`, `TrackRow.qml`, `src/mtee/qml/Mtee/ThinScrollBar.qml`, `Main.qml` et `src/mtee/models/workspace_model.py`. Lire les tests `tests/ui/test_player_views.py`, `test_incremental_scan_and_scroll.py` et `tests/unit/test_workspace_model.py`.

La recherche est actuellement ancrée en haut de l’en-tête, tandis que les boutons sont ancrés en bas. Elle n’a pas de traitement explicite d’Échap. `press()` de la liste force le focus de la vue, ce qui entre en conflit avec l’exception demandée pour le clic sur une ligne. `ThinScrollBar` fait dépendre son opacité de `active` et `hovered`, avec un fondu de 160 ms mais sans délai de maintien dédié.

## Jalon 26.1 — Maquette locale de l’en-tête

Créer dans le mode démo un état d’en-tête avec un titre long, son résumé, un champ vide puis rempli, et les trois boutons. Utiliser une même rangée avec centres verticaux alignés. Préserver l’espace du nom de dossier ; réduire ou élider proprement les éléments secondaires à petite largeur. Prévoir 1440 × 900, 1280 × 720 et la largeur effective d’un groupe divisé.

Ajouter les captures et le contrat de focus à `docs/ux/review-ux-ui-2026-09.md` (à créer si absent). Faire valider cet ajustement avant son branchement fonctionnel conformément à `PLAN.md`. Il s’agit d’un ajustement de disposition dans l’identité existante ; ne pas changer la palette, la police ou la densité générale.

## Jalon 26.2 — Focus et raccourcis

Faire gérer Échap par le champ lui-même : quitter sa saisie sans effacer le texte, sans modifier le filtre et sans basculer lecture/pause. Restaurer le focus vers un destinataire de navigation explicite, par exemple le conteneur de liste du même groupe. Le liseré actif et le caret doivent disparaître.

Un clic sur le fond, la sidebar, une autre activité, un onglet, une commande ou un autre éditeur retire le focus et laisse le contrôle cliqué agir dès ce premier clic. Utiliser la propagation et les gestionnaires de focus Qt existants ; éviter un grand `MouseArea` qui intercepterait tous les boutons ou imposerait un second clic.

Un clic gauche simple dans une ligne du même listing sélectionne cette ligne mais préserve la saisie si le champ était actif. La ligne n’acquiert pas simultanément un faux focus clavier. Si le champ n’avait pas le focus, la navigation clavier de la liste conserve son comportement habituel. Le double-clic active la lecture ; les boutons et menus contenus dans la ligne suivent leurs propres contrats de focus. Ctrl/Shift sélectionnent correctement sans transformer les caractères saisis en commandes de lecteur.

Pendant la saisie, Espace reste un espace ; Enter ne lance pas involontairement un morceau, les flèches naviguent dans le texte et Ctrl+A sélectionne le texte. Après Échap, les raccourcis du listing reprennent. Le test existant `test_space_goes_to_search_while_a_track_is_playing` est une protection à conserver. Un focus retiré ne doit pas être repris à chaque rafraîchissement du workspace ou changement de position du lecteur.

La recherche est propre à l’onglet et ne filtre pas l’arbre. Le cas d’un double-clic dans l’arbre sur une cible masquée est traité explicitement au plan 25 ; ne pas le confondre avec un simple clic ailleurs.

## Jalon 26.3 — Molette et visibilité des barres

Mesurer d’abord le déplacement obtenu avec dix crans identiques sur la même fixture, dans l’arbre et dans une liste de plus de 100 morceaux. Appliquer un facteur initial de 1,25 au delta de molette à crans. Centraliser cette valeur dans le composant ou les paramètres de présentation adaptés ; ne pas disperser des constantes dans les vues.

Le pavé tactile, les deltas en pixels, le sens naturel de défilement, l’inertie native, Shift+molette et le défilement horizontal doivent être traités séparément du gain de molette. Éviter le double traitement du même événement par le nouveau gestionnaire et le `Flickable` existant. Borner aux extrémités. Ne pas détourner une molette destinée à un contrôle tel que le volume.

Le périmètre d’accélération est la sidebar Explorer et les vues List/Artwork du dossier. Les autres vues conservent leur vitesse, sauf nécessité démontrée et documentée. La scrollbar partagée peut recevoir le maintien commun si ses usages restent cohérents.

Après la fin du défilement, le curseur de scrollbar reste visible au moins 1 000 ms. Valeur d’implémentation proposée : temporisation de 1 200 ms, puis fondu de 160 ms existant. Relancer le délai à chaque nouvelle interaction. Survol, appui et glissement maintiennent sa visibilité ; son utilisation reste possible jusqu’à la fin du geste. Quand aucun défilement n’est possible, ne pas afficher une barre inutile. Les timers sont locaux aux composants et disparaissent avec eux.

## Vérifications et commandes

Créer `tests/ui/test_search_focus.py` au jalon 26.2. Il exercera un vrai champ QML, des clics sur une ligne, une commande, le fond et un autre groupe ; observer `activeFocus`, le texte, les IDs filtrés et l’état du lecteur. Créer `tests/ui/test_scroll_interactions.py` au jalon 26.3 : une série contrôlée d’événements de molette donne environ 1,25 fois le déplacement initial loin des bords ; la scrollbar reste visible avant le seuil puis s’efface après le délai et le fondu. Tolérer l’ordonnancement Qt dans les assertions temporelles sans élargir silencieusement le minimum demandé.

Depuis la racine, après création des tests :

    uv run pytest tests/ui/test_search_focus.py tests/ui/test_scroll_interactions.py tests/ui/test_player_views.py tests/ui/test_incremental_scan_and_scroll.py

Les tests de GUI ne remplacent pas la recette avec une molette physique et, si disponible, un pavé tactile. Noter les périphériques réellement utilisés. Vérifier 100 % et 150 % d’échelle Windows pour l’en-tête ; aucun chevauchement, aucune zone de clic inaccessible. La recherche reste filtrée après Échap, mais son état de focus est visuellement retiré.

Clore selon le plan 23 : smoke-tests, build, scénario dans l’EXE et `docs/validation/ux-ui-26.md`.

## Livraison et reprise

Livrer en trois jalons cohérents : disposition approuvée, focus, défilement. Sujet proposé : `fix(ui): align folder search and improve scrolling and focus`. En cas de régression de raccourci, conserver les règles explicites du champ et retirer uniquement le gestionnaire fautif. Ne pas régler une erreur de focus en supprimant la recherche ou la navigation clavier.

## Progress

- [x] 2026-09-28 — Sources et décision de conservation du filtre documentées.
- [x] 2026-09-28 — Maquettes d’en-tête rendues à 1440 × 900, 1280 × 720 et en groupes partagés de 415 px.
- [ ] En-tête maquetté et validé.
- [ ] Focus et raccourcis corrigés et testés.
- [ ] Vitesse et maintien des scrollbars mesurés et vérifiés.
- [ ] Distribution, recette Windows, rapport, commit et push terminés.

## Surprises & Discoveries

2026-09-28 — Le champ conserve son filtre indépendamment du focus ; le correctif doit respecter cette séparation. Le clic de ligne force aujourd’hui le focus de la liste, ce qui doit changer seulement dans le cas demandé.

## Decision Log

2026-09-28 — Utilisateur : garder le texte et les résultats lorsqu’on quitte la recherche. Codex : proposer 1,25 pour la molette à crans et 1 200 ms pour le maintien, à vérifier sur périphériques réels.

2026-09-28 — Codex : maquettes statiques rendues dans le thème natif, voir `docs/ux/review-ux-ui-2026-09.md`. La validation de disposition attend l’examen utilisateur ; aucun code du focus ou du défilement n’a été branché.

## Outcomes & Retrospective

Plan d’en-tête préparé et rendu pour revue. La disposition n’est pas encore validée ; focus, raccourcis, mesures de molette, maintien de scrollbar, comportement applicatif et recette restent à réaliser. Révision du 28 septembre 2026 : ajout des trois tailles de maquette et lien vers le dossier de revue commun.
