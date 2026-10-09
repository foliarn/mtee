# Revue UX — Genre Manager 110

Date : 9 octobre 2026. Statut : **maquettes manipulables prêtes pour l'essai utilisateur ; choix non validés**. Les variantes utilisent les mêmes données fictives et le thème QML de MTEE. Elles ne sont pas raccordées à la bibliothèque personnelle.

## Ouvrir les deux variantes

Depuis la racine du dépôt, dans deux lancements successifs :

    uv run python scripts/review_genre_manager_110.py --variant selection --scenario house --data-dir .local/validation/110/prototype-selection

    uv run python scripts/review_genre_manager_110.py --variant brush --scenario house --data-dir .local/validation/110/prototype-brush

La sidebar permet aussi de passer de **Selection, then assign** à **Brush** sans effacer les choix de la session ouverte. Les boutons de source `House folder`, `Playlist`, `80 of 100` et `New tracks` chargent d'autres jeux fictifs et réinitialisent les décisions du prototype ; ce comportement de démonstration n'est pas le contrat de reprise de la future application. Le prototype écrit dix petits WAV synthétiques dans le dossier isolé indiqué ; il ne lit aucun morceau personnel.

## Captures de repérage

- [Sélection puis attribution, 1440 × 900](review-110-selection.png)
- [Pinceau, 1100 × 760](review-110-brush.png)
- [Catalogue sur page](review-110-catalogue.png)
- [Aperçu des 80 vérifiés](review-110-organize.png)

Ces captures vérifient la présence et la disposition des surfaces. Elles ne constituent ni une validation du confort d'utilisation, ni une preuve d'écoute audible.

## Parcours à essayer dans chaque variante

1. Dans `House folder`, classer trois titres. En sélection, cliquer une ligne puis utiliser Ctrl ou Maj pour étendre les cibles ; choisir ensuite `Deep House` dans la palette. Au pinceau, choisir `Deep House`, puis cliquer `Mark` sur les lignes voulues ; recliquer `Mark` retire ce genre. Observer que le clic de pinceau ne sélectionne pas la piste.
2. Cliquer `Play` sur une ligne. La commande passe par le `PlayerService` et le backend libmpv existants ; aucun classement ou état Reviewed n'est changé par le lancement de la lecture. Le bas de la fenêtre affiche le morceau courant et une commande Play / pause.
3. Ajouter `Minimal House` comme secondaire à une piste Deep House, puis utiliser `Promote 2nd` sur sa ligne. Observer l'ordre des genres et la perte de Reviewed si la piste avait été vérifiée. Le passage de `House` seul à `Deep House` en fait le principal dans la maquette.
4. Créer volontairement `banger` dans la palette ou la page `Genres & tags`, puis l'attribuer et le retirer. Une installation fictive commence avec zéro tag libre. Un changement de tag conserve Reviewed.
5. Sélectionner des pistes et cliquer `Mark N as reviewed`. Passer entre `All tracks` et `To review`. La seconde vue retire les pistes vérifiées après l'action ; la première les conserve avec `Yes` dans la colonne Review.
6. Cliquer `Simulate save error`, puis effectuer une attribution. Lire l'erreur, faire `Retry`, puis `Undo`. Le prototype simule ces états en mémoire seulement.
7. Ouvrir `Genres & tags` : sélectionner une définition, en créer une sous House ou à la racine, la renommer et l'archiver. Examiner la place des commandes dans la page. `Uncertain` montre des exemples de crédits volontairement non attribués.
8. Ouvrir `80 of 100`, puis `Organize files`. L'aperçu montre exactement 80 morceaux vérifiés, leurs sources et destinations illustratives. `Move files` est désactivé ; aucun dossier musical n'est créé.

Le champ `Search this source` et le choix `Include subfolders` montrent le périmètre de travail. La fixture House n'a pas de sous-dossier : ce dernier choix affiche son intention sans modifier les lignes. La playlist fictive contient plusieurs sources (`House` et `Inbox`).

## Ce qui est réel et ce qui est simulé

La fenêtre est une vraie UI PySide6/QML lancée depuis les sources. `Play` invoque le lecteur natif sur un WAV synthétique. Le classement, les tags, la revue, le catalogue, la recherche, l'erreur, Undo et l'aperçu sont des états de démonstration en mémoire. Fermer la fenêtre les efface. Les mouvements sont entièrement simulés. Les deux fichiers de base SQLite 020/021 du banc de mesure sont séparés de cette fenêtre et ne sont pas ouverts par elle.

## Retours attendus en texte dans le chat

Après les deux essais, indiquer quelle interaction garder (sélection, pinceau ou les deux), les gestes pénibles et ce qui manque pour marquer un lot comme vérifié. Préciser aussi la disposition souhaitée de la sidebar et de la palette, ce que devrait faire le retrait du dernier genre, si une piste sans genre peut être Reviewed, comment déplacer un sous-genre dans l'arbre, et si les exemples `House/Deep House` et `House` conviennent comme destinations physiques. Ces points restent ouverts jusqu'à un retour explicite ; la maquette ne fixe pas à elle seule ces règles.

La revue est demandée en texte libre, conformément au plan : le questionnaire structuré de l'application a déjà posé problème. Les corrections demandées seront reportées ici avant le branchement fonctionnel 110.3–110.6.
