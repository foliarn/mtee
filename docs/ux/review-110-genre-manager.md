# Revue UX — Genre Manager 110

Date : 9 octobre 2026. Statut : **maquettes révisées après un premier retour ; validation finale 110.2 attendue**. Les deux variantes partagent les mêmes données fictives. La fenêtre reprend le cadre, l'onglet, les listes et le lecteur de MTEE ; ce n'est toujours pas le plugin branché à l'application principale.

## Ouvrir les deux variantes

Depuis la racine du dépôt :

    uv run python scripts/review_genre_manager_110.py --variant selection --scenario house --data-dir .local/validation/110/prototype-selection

    uv run python scripts/review_genre_manager_110.py --variant brush --scenario house --data-dir .local/validation/110/prototype-brush

La sidebar bascule entre **Selection, then assign** et **Brush** sans effacer les décisions en cours. Le titre **House** sous **FOLDER** ouvre une fenêtre interne avec onglets **Folders** et **Playlists**. Chaque source affiche un pourcentage de progression. Changer de source réinitialise les décisions de ce prototype en mémoire ; la future reprise de session est prévue par le plan.

## Captures de revue

- [Classify, sélection, 1440 × 900](review-110-selection.png)
- [Classify, pinceau, 1100 × 760](review-110-brush.png)
- [Fenêtre de choix de source](review-110-source-picker.png)
- [Attribution explicite aux morceaux du dossier](review-110-folder-tag.png)
- [Genres & tags, 29 genres défilants](review-110-catalogue.png)
- [Organize, aperçu de 80 titres vérifiés](review-110-organize.png)

Les captures ont été produites à partir de la maquette QML et examinées visuellement. Elles ne prouvent ni le confort d'usage au pointeur ni une écoute audible.

## Changements appliqués après le premier retour

- Le cadre reprend la barre de menus, la barre d'activité, l'onglet, la palette et le lecteur de MTEE. Les lignes de Classify et Organize sont des tables sans cartes alternées ; les titres et valeurs secondaires reprennent l'alignement des listes ordinaires. Les libellés des boutons et champs sont centrés verticalement.
- La colonne de détails à droite de Classify a été retirée. Les commandes de genre et de tag se trouvent sous le titre de source ; aucun genre n'est répété en palette sur chaque ligne.
- Le dossier **House** démarre avec zéro genre attribué. Son nom n'est qu'une source. **Tag folder songs…** demande un genre choisi puis un clic explicite sur **Tag N songs** ; l'action vise les morceaux, pas le dossier.
- Le catalogue d'exemple contient 29 genres. La liste et la recherche évitent qu'un catalogue de plus de vingt genres déborde. **New root genre** crée à la racine ; le **+** situé à droite de chaque racine crée un sous-genre.
- **Move files** est placé dans le pied de page près de **Undo** et reste désactivé dans la maquette.

## Parcours à essayer

1. Ouvrir **House** puis la fenêtre de source. Comparer les onglets et les pourcentages, essayer la playlist. Revenir à House : aucun morceau n'est classé à cause du nom du dossier.
2. Essayer **Tag folder songs…** et vérifier que le choix de genre et la confirmation sont compréhensibles. **Undo** annule cet essai en mémoire.
3. Classer trois morceaux avec chacune des variantes. En sélection, choisir les lignes puis **Assign genre…**. Au pinceau, choisir le genre dans **Brush: …**, puis utiliser le **+** d'une ligne. Le bouton Play reste séparé.
4. Essayer la recherche, **All tracks**, **To review** et **Mark N as reviewed**. Tester le classement pendant une lecture volontaire.
5. Ouvrir **Genres & tags**, parcourir les 29 noms, chercher un genre, créer une racine puis un sous-genre avec le **+** de son parent. Créer un tag libre.
6. Choisir **Reviewed batch** dans la fenêtre de source, puis **Organize files**. L'aperçu contient 80 titres ; **Move files** est visible dans le pied de page mais indisponible.

Le lanceur écrit dix petits WAV synthétiques dans le dossier isolé indiqué. Il ne lit pas de collection personnelle. Les genres, tags, revues, erreurs, annulations et destinations restent en mémoire ; fermer la fenêtre les efface. Aucun fichier audio n'est déplacé ou retagué.

## Points encore à valider

Le retour reçu valide l'usage des sidebars et donne les corrections détaillées ci-dessus. Il ne choisit pas encore entre sélection et pinceau, ne tranche pas le retrait du dernier genre, la revue d'un morceau sans genre, le reparentage, ni les destinations physiques. Ces choix et l'ergonomie des maquettes révisées attendent un essai et une réponse en texte dans le chat avant le branchement fonctionnel 110.3–110.6.
