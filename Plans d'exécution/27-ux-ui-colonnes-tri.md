# 27 — Colonnes personnalisables et tri à trois états

## Résultat attendu et décisions

Le tableau affiche par défaut `Title | Artist | Date created | BPM | Key`. Toutes les colonnes de données, y compris Title, sont déplaçables et masquables. Le menu propose aussi Date modified et l’affichage des pochettes. La colonne ordinale # disparaît.

Décisions utilisateur du 28 septembre 2026 : configuration globale mémorisée ; déplacement par glisser-déposer ; date de création décroissante comme ordre de référence au lancement et au retour au défaut ; retirer la flèche du tri manuel quand on revient au défaut. Le texte de recherche et le tri sont indépendants.

Lire les plans 23, 25 et 26 avant le travail. Ils définissent les identités stables, les comportements de focus et la disposition de l’en-tête.

## Sources et état existant

Lire `src/mtee/qml/components/TrackListView.qml`, `TrackRow.qml`, `src/mtee/models/workspace_model.py`, `track_list_model.py`, `src/mtee/persistence/workspace_repository.py`, `library_repository.py` et `src/mtee/domain/file_dates.py`. Examiner `src/mtee/models/demo_workspace.py` pour garder la maquette représentative. Lire `tests/ui/test_column_selection.py`, `tests/unit/test_workspace_model.py`, `test_track_list_model.py` et `test_file_dates.py`.

Les clés `fileCreatedAt` et `fileModifiedAt` et leurs valeurs numériques existent. Le menu n’en propose pas l’activation. QML force Title visible ; le réordonnancement actuel est un menu Move left/Move right. L’ordre, les masques et les largeurs sont stockés par onglet. `setSort()` alterne deux directions et le défaut `index` restitue l’ordre fourni par le catalogue. Le numéro de ligne contient aussi le bouton de lecture : sa suppression demande un emplacement de remplacement.

## Jalon 27.1 — Maquette et contrat d’état

Préparer un tableau avec les cinq colonnes par défaut, le menu complet et l’option `Show artwork`. Présenter l’état sans cover, sans Title, avec colonnes nombreuses et avec une seule colonne visible. Le menu doit rester accessible même quand la présentation est très réduite. Les boutons de lecture et d’information restent utilisables, séparés des colonnes de données ; aucun numéro ordinal n’est conservé comme substitut.

Proposer une petite zone d’actions de ligne, sans en-tête #, qui reste indépendante de la présence de Title et des pochettes. Distinguer visuellement sélection, lecture, survol et focus. La colonne # supprimée n’est pas le tag Track number du fichier : celui-ci reste dans les métadonnées.

Faire valider ces états dans `docs/ux/review-ux-ui-2026-09.md` avant de brancher les nouveaux gestes. Conserver `Move left` / `Move right` comme alternative au glisser-déposer et moyen utilisable au clavier, avec des libellés cohérents.

## Jalon 27.2 — Préférences globales et compatibilité

Créer une structure de préférence de présentation globale contenant ordre complet des clés, clés masquées, largeurs et `showArtwork`. Réutiliser la session JSON validée par `WorkspaceRepository` ; adapter `_validated()` et les snapshots pour que ces champs ne soient pas silencieusement perdus. Aucun ajout SQL n’est nécessaire pour cette préférence.

Une modification s’applique immédiatement à tous les tableaux ouverts et aux nouveaux onglets, y compris les deux groupes. Recherche, sélection et tri manuel restent propres à chaque onglet. Les tailles d’affichage adaptatives ne réécrivent pas les largeurs mémorisées simplement parce que la fenêtre rétrécit.

Initialisation proposée : en l’absence du nouveau profil global, appliquer les cinq colonnes demandées et des largeurs adaptées. Garder une copie des anciens réglages par onglet dans les données de session ou une sauvegarde de migration, sans les laisser masquer le nouveau profil. Préserver racines, onglets, groupes et recherches. Dès que le profil global existe, les choix explicites de l’utilisateur deviennent prioritaires ; ne pas réinitialiser sa configuration à chaque lancement. Ajouter une commande `Reset columns` qui rétablit les cinq colonnes et les pochettes visibles.

Valider les clés, supprimer doublons et clés inconnues, borner les largeurs et compléter les clés disponibles manquantes dans l’ordre global. Au moins une colonne de données reste visible ; empêcher seulement le masquage de la dernière, quelle qu’elle soit. Title est masquable dès qu’une autre reste affichée. Une préférence malformée doit produire une présentation utilisable sans réinitialiser tout le workspace.

## Jalon 27.3 — Colonnes, pochettes et gestes

Construire le menu depuis une liste commune de clés/libellés afin d’éviter un décalage entre données, ordre et options. Exposer Title, Artist, Album, Genre, BPM, Key, Duration, Format, Filename, Bitrate, Date created et Date modified. Les deux dates affichent leur valeur du système de fichiers et non la date musicale du tag. La date absente reste `—` ; ne pas substituer la date d’import ni un ctime POSIX à une création.

Le glisser-déposer d’un en-tête montre l’emplacement d’insertion. Il ne déclenche pas de tri au relâchement et ne démarre pas depuis la poignée de redimensionnement. Échap annule le geste ; un dépôt hors zone laisse l’ordre intact. Réordonner une colonne visible tient compte des colonnes masquées dans l’ordre complet, de façon déterministe. Une colonne réaffichée retrouve une position cohérente.

Masquer les pochettes supprime image et espace réservé dans le tableau. La grille Artwork conserve ses images. Le mode sans Title ni cover garde les actions de ligne, la sélection et un nom accessible pour le morceau. Mettre à jour les calculs de largeur pour retirer le numéro, son espacement et les contraintes implicites de Title. Préserver le défilement horizontal, l’alignement en-têtes/cellules et le redimensionnement.

## Jalon 27.4 — Tri explicite à trois états

Représenter séparément le mode de tri (`default` ou `manual`), la clé et la direction manuelles. Le défaut a pour ordre effectif `fileCreatedAt` décroissant et n’affiche aucune flèche. Ne pas déduire le mode de la seule clé : le tri manuel descendant sur Date created a le même résultat que le défaut mais constitue un état distinct du cycle.

| État avant clic | Clic | État après clic | Flèche |
|---|---|---|---|
| Défaut | Colonne C | Manuel C croissant | Haut sur C |
| Manuel C croissant | C | Manuel C décroissant | Bas sur C |
| Manuel C décroissant | C | Défaut : création décroissante | Aucune |
| Manuel C, toute direction | Colonne D différente | Manuel D croissant | Haut sur D |

Nouvel onglet et nouveau lancement de l’application : défaut création décroissante. Revenir à un onglet pendant la même session garde son tri manuel. Cette distinction est la règle de conception retenue pour appliquer « au lancement » sans réinitialiser le tableau à chaque changement d’onglet. Les anciennes valeurs persistées `index` et les anciens tris de session ne doivent pas empêcher le nouveau défaut au lancement.

Trier les dates et BPM/durées sur leurs valeurs numériques, jamais sur les libellés formatés. Les valeurs absentes restent en bas dans les deux directions. Départager les égalités avec le titre, puis l’UUID de façon stable ; documenter cette règle pour éviter des déplacements aléatoires à chaque refresh. Un troisième clic ne vide pas la recherche. Si la colonne triée est masquée, revenir au défaut pour éviter un tri manuel invisible. Conserver la sélection par UUID et révéler la sélection lorsque nécessaire sans ramener arbitrairement la liste en haut. Ne pas réordonner rétroactivement la file déjà capturée par le lecteur.

## Vérifications et critères de recette

Étendre les tests existants et créer `tests/unit/test_table_preferences.py` au jalon 27.2 pour la compatibilité de session et le profil global. Ce fichier n’existe pas à la préparation.

    uv run pytest tests/unit/test_table_preferences.py tests/unit/test_workspace_model.py tests/unit/test_track_list_model.py tests/unit/test_file_dates.py
    uv run pytest tests/ui/test_column_selection.py tests/ui/test_incremental_scan_and_scroll.py tests/ui/test_search_focus.py

Le test UI de colonnes doit manipuler le menu réel, masquer Title, changer l’ordre par drag, afficher les deux dates, couper les covers et vérifier en-têtes et cellules. Ajouter le cycle de trois clics avec une fixture dont titres, noms de fichiers et dates donnent trois ordres différents. À l’état défaut, vérifier à la fois la création décroissante et l’absence de flèche. Tester dates égales/absentes, un seul morceau, zéro résultat et refresh pendant un tri.

Pour les préférences : profil neuf, ancienne session avec deux groupes et réglages différents, profil global déjà personnalisé, données invalides, fermeture/réouverture et redémarrage. Aucun réglage global n’est perdu et les anciens onglets restent accessibles. Après redémarrage, les colonnes restent personnalisées tandis que le tri revient à la création décroissante.

Recette visuelle aux tailles du plan 26 : aucune colonne superposée, gestes non ambigus, titre long élidé, toutes les commandes accessibles même lorsque Title est caché. Clore avec `docs/validation/ux-ui-27.md`, distribution et push du plan 23.

## Livraison et reprise

Commits intermédiaires possibles : profil global, colonnes et gestes, puis cycle de tri. Sujet proposé : `feat(explorer): customize columns globally and reset sorting to creation date`. Une reprise ne doit pas recalculer un nouveau profil global depuis les anciens onglets après que l’utilisateur l’a personnalisé. Préserver la copie de session utilisée pour vérifier la compatibilité sans la versionner.

## Progress

- [x] 2026-09-28 — Décisions utilisateur, modèle existant et tests inspectés.
- [x] 2026-09-28 — États de colonnes, menu complet et accès dans un groupe partagé de 415 px rendus.
- [x] 2026-09-29 — L’utilisateur confirme le menu et demande de conserver la rangée d’en-têtes existante ; la maquette et l’emplacement du champ de recherche et des boutons restent inchangés.
- [x] 2026-09-29 — Profil global persistant, valeurs par défaut, validation isolée et reprise des champs d’onglets historiques implémentés.
- [x] 2026-09-29 — Colonnes masquables, dates système, affichage des pochettes, remise à zéro, déplacement par menu et glisser-déposer implémentés.
- [x] 2026-09-29 — Tri par défaut sur la date de création décroissante et cycle manuel à trois états implémentés.
- [x] 2026-09-29 — Compilation Python/QML et distribution Windows principale vérifiées ; rapport de validation ajouté.
- [ ] Recette comportementale manuelle laissée à l’utilisateur ; tests non lancés à sa demande.
- [x] 2026-09-29 — Commit `fbc7d02` poussé sur `origin/main`, puis confirmé après fetch.

## Surprises & Discoveries

2026-09-28 — Les données de dates et leur tri existent déjà ; le travail porte surtout sur leur exposition, le défaut et les états de présentation. La validation de session doit évoluer avec les nouveaux champs, sinon leur écriture apparente pourrait être perdue au rechargement.

## Decision Log

2026-09-28 — Utilisateur : création décroissante pour le défaut, aucune flèche au retour au défaut, personnalisation globale mémorisée. Codex : autoriser le masquage de Title mais garder une colonne minimale, préserver les commandes de ligne et distinguer mode de tri et ordre effectif. Les règles de compatibilité et de conservation pendant une session sont des choix de conception documentés.

2026-09-28 — Codex : proposer une bande d’actions de 36 px à gauche des pochettes/colonnes pour que lecture et information restent accessibles dans les configurations réduites. Choix en attente ; captures dans `docs/ux/review-ux-ui-2026-09.md`.

2026-09-29 — Utilisateur : conserve l’apparence actuelle de la rangée d’en-têtes (capture 2), accepte le menu flottant montré, et demande de ne pas retoucher l’en-tête de recherche ni ses boutons. Implémentation : conserver les cellules d’en-tête et leur placement ; le petit espace des commandes de ligne reste sans numéro ordinal.

## Outcomes & Retrospective

Les préférences globales, le menu, la visibilité des colonnes et pochettes, les gestes, les dates et le tri à trois états sont implémentés. La rangée d’en-têtes conserve son style existant. Compilation et distribution Windows vérifiées ; aucune recette comportementale ni test automatisé n’a été exécuté, conformément à la demande de l’utilisateur. Révision du 29 septembre 2026.
