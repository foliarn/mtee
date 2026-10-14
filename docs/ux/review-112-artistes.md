# Revue UX — Vue Artistes du cœur (112)

Date : 14 octobre 2026. Statut : maquette à valider. La vue réelle n'est pas branchée : `Main.qml`, la barre d'activités et les liens d'artistes restent inchangés. Aucun lien d'artiste n'est réactivé avant votre réponse.

## Ce qui est montré

- **Barre d'activités** : une entrée « Artists » (icône micro, mise en évidence).
- **Volet latéral** : titre ARTISTS, recherche « Search artists », compteur « N artists », liste alphabétique avec le nombre de pistes à droite. Un clic ouvre la page.
- **Page d'artiste** : onglet à son nom, libellé « Artist », nom en grand, « N tracks · from “…” », boutons **Play** et **Shuffle**, puis la liste des pistes (#, Title, Album, Time) aux couleurs et typographies de la table des morceaux.
- **Deux actions de correction** : **This is one artist** et **Split into separate artists**. Elles se trouvent dans le menu « … » de la page (variante affichée par défaut), ou sous forme de deux boutons (variante « inline »). Une phrase sous les boutons dit exactement quel crédit l'action touche.
- **Pied de page** : le résultat de la dernière action, le nombre de choix gardés dans la maquette, et « Reset choices ».

## Captures

| Scénario | Taille | Capture |
|---|---|---|
| Liste, aucun artiste ouvert | 1440 × 900 | [liste](review-112-artistes-liste-1440x900.png) |
| Page « Status », menu « … » ouvert | 1440 × 900 | [menu](review-112-artistes-page-menu-1440x900.png) |
| Page « Status », variante boutons | 1440 × 900 | [inline](review-112-artistes-page-inline-1440x900.png) |
| Recherche « sub » | 1100 × 760 | [recherche](review-112-artistes-recherche-1100x760.png) |
| Après « This is one artist » sur « Chase & Status » | 1100 × 760 | [après](review-112-artistes-apres-1100x760.png) |

Les captures ont été produites hors écran et relues. Elles ne remplacent pas un essai au pointeur, que vous pouvez faire avec la commande ci-dessous.

## Ouvrir la maquette

Depuis la racine du dépôt :

    uv run python scripts/review_artists_112.py --scenario default --size 1440x900

Options utiles : `--scenario default|selected|search|after`, `--variant menu|inline`, `--open-menu`, `--size 1440x900|1100x760`.

## Ce qui est réel et ce qui est fictif

- **Réel** : les règles de découpage et les deux actions sont les fonctions du cœur (`mtee.domain.artist_index`). Le compteur de pistes, la liste et l'ordre de la page sont calculés par ces règles sur les étiquettes fictives.
- **Fictif** : 19 pistes inventées (`src/mtee/prototypes/artists_112.py`). Aucune base, aucun fichier audio, aucune étiquette ne sont lus ou écrits.
- **Non connectés** : Play et Shuffle affichent seulement un message. Les pochettes ne sont pas dessinées (voir les points à trancher).

## Parcours à essayer

1. Ouvrir **Status** : le texte « from “Chase & Status” » explique d'où vient ce nom. Ouvrir le menu « … » : **This is one artist** est actif, **Split into separate artists** non, car « Status » ne contient aucun séparateur.
2. Choisir **This is one artist**. « Status » disparaît de la liste, « Chase & Status » apparaît, « Chase » passe de 4 à 1 piste. La page se ferme et le message le dit.
3. Ouvrir **Chase & Status** : **Split into separate artists** devient actif. Le choisir pour revenir au découpage.
4. Ouvrir **Camo & Krooked** (aucun côté seul) : **Split into separate artists** est actif et coupe le nom en « Camo » et « Krooked ».
5. Chercher « sub », puis effacer la recherche. Vérifier que le compteur indique « 1 of 17 artists » puis « 17 artists ».
6. Revenir à la variante inline avec `--variant inline` et refaire les points 1 à 4 avec les boutons.
7. Cliquer **Reset choices** : toutes les corrections disparaissent.

## Points à trancher

1. **Règle « au moins un côté seul » pour `&` et `x`.** C'est la lecture la plus littérale de votre règle : « Chase & Status » est coupé dès qu'une piste porte l'artiste seul « Chase ». Résultat visible dans la maquette : « Chase » (4 pistes) et « Status » (3 pistes). Variante possible : couper seulement si **les deux** côtés sont seuls ; « Chase & Status » resterait alors entier. Quelle règle retenez-vous ?
2. **Virgule.** « Nikita, the Wicked » donne deux artistes, « Nikita » et « the Wicked ». Une virgule coupe toujours. Pour garder le nom entier, il faut répondre « This is one artist » (la question est déjà posée dans l'éditeur de tags depuis l'étape 111). Acceptez-vous cette règle, ou voulez-vous une liste de noms protégés ?
3. **Emplacement des actions.** Menu « … » (par défaut, une seule place pour les actions rares) ou deux boutons visibles en permanence ? Comparer les captures « menu » et « inline ».
4. **Portée d'une action.** Une action s'applique à tous les morceaux où le crédit apparaît, et la phrase sous les boutons nomme ce crédit. Confirmez-vous ce comportement, ou voulez-vous confirmer chaque action ?
5. **Page après une action.** Quand l'artiste disparaît (par exemple « Status » après « This is one artist »), la page se ferme (choix actuel). Préférez-vous ouvrir directement le ou les artistes résultants ?
6. **Ordre des pistes** sur la page : titre (choix actuel). Album puis numéro de piste serait aussi possible.
7. **Tri de la liste** : alphabétique seulement (choix actuel), sans tri par nombre de pistes.
8. **Recherche** : sous-chaîne sur le nom seulement, sans recherche dans les titres ni dans les albums.
9. **Pochettes** : la maquette ne les dessine pas. La vraie ligne de morceau affiche une pochette de 40 px devant le titre, lorsque la colonne est active (`TrackRow.qml`). Les ajouter demande de brancher la pochette réelle ; à décider.
10. **Play et Shuffle** : sans effet dans la maquette. Leur branchement est prévu après validation, sur la file de lecture existante.

## Ce qui reste hors de cette maquette

- L'entrée réelle dans `Main.qml` et la barre d'activités.
- Le rétablissement des liens d'artistes depuis le lecteur, la file et l'historique.
- La page Settings › Library pour gérer les choix (le service expose déjà la liste et la suppression).
- Les tests au pointeur sur la vraie collection, qui n'ont pas été faits.
