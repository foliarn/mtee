# Revue de maquette — panneau Queue/History et menu « Add to playlist » (plan 101)

Préparée le 1er octobre 2026. Deux maquettes interactives, sans données réelles : le panneau droit à trois onglets (Info, Queue, History) et le menu « Add to playlist » compact. Les autres retours du plan 101 (désélection, Explorer, dossiers, tâches, couleur, en-tête de playlist) ne sont pas concernés par cette revue. Les jalons 101.9 et 101.10 du plan attendent la décision ci-dessous.

## À examiner

1. **Onglet Queue** : la file reprend la présentation de la page 2 du plein écran, à une colonne étroite (marges de 12 px, pas de fond de carte). Bloc fixe « Now playing », puis « Next in queue » et « Next from: Deep Focus », lignes de 56 px (pochette 44 px avec voile et icône au survol, titre, artiste, bouton « … » au survol). Deux occurrences du même titre et une ligne indisponible sont présentes. La poignée `||` actuelle disparaît ; on tient la ligne n'importe où pour la déplacer.
2. **Onglet History** : mêmes lignes, intertitre « Recently played », du plus récent au plus ancien, sans glisser-déposer. Clic sur la pochette ou double-clic : lecture immédiate (la file et les ajouts manuels sont conservés). Menu « … » ou clic droit : `Add to queue`, `Go to folder`, `Edit info`. L'historique est conservé entre les sessions, sur 100 écoutes.
3. **Variante proposée, non demandée : `history-times`.** Elle affiche à droite de chaque ligne au repos l'heure relative d'écoute (« 3 min ago », « Yesterday »), remplacée par « … » au survol. **À accepter ou refuser** ; sans accord explicite, elle ne sera pas implémentée.
4. **Menu « Add to playlist »** : 300 px de large (au plus 420 px de haut) au lieu de 350 × 520, lignes de 44 px avec pochette 32 px, nom en 13 px, sous-ligne « N tracks » en 11 px, rangée « New playlist » avec carré `+`, champ de recherche de 30 px avec loupe. La bascule reste immédiate (un clic ajoute ou retire ; coche = enregistré, tiret = partiel). **Changement à valider : le bouton `Close` disparaît** ; Échap ou un clic à l'extérieur ferment le menu. La scène `menu-compare` superpose le menu actuel et la proposition aux tailles réelles.

## Parcours interactif

Depuis la racine du dépôt :

    uv run python scripts/review_101.py --scene queue

Scènes du panneau : `queue`, `queue-hover`, `queue-drag`, `queue-menu`, `queue-empty`, `history`, `history-menu`, `history-empty`, `history-times`. Scènes du menu : `menu`, `menu-search` (filtre « deep »), `menu-partial` (état partiel), `menu-empty`, `menu-compare`. Les onglets du panneau sont cliquables. Dans la file, tenir une ligne et la déplacer (Échap annule) ; clic droit ou « … » pour le menu ; clic sur une pochette pour lire/mettre en pause l'élément courant. Dans le menu, cliquer une playlist bascule la coche et réordonne « Saved in » ; taper dans le champ filtre la liste.

`--capture` écrit des PNG dans `docs/ux/review-101-2026-10-01/` (rendu hors écran, facultatif). `--close-after 1` ouvre puis ferme la fenêtre pour vérifier le chargement.

## Limites et décision attendue

Les actions modifient uniquement des tableaux QML en mémoire : aucun service audio, fichier, playlist ni base de données. Le chargement des quatorze scènes a été vérifié sans avertissement QML ; le rendu et la qualité des gestes à la souris n'ont pas été inspectés par l'agent, qui n'a pas fait de test visuel.

**Décision attendue :** validation ou corrections précises de (a) l'onglet Queue, (b) l'onglet History, (c) la variante `history-times` (oui/non), (d) le menu compact, y compris la suppression du bouton `Close`. Un silence n'est pas un accord.
