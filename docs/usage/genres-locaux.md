# Genres locaux : classement et tri

Les genres et tags décrits ici sont enregistrés dans la base MTEE. Ils ne modifient ni les métadonnées ni les fichiers audio. Le champ Genre du fichier reste une information distincte. Les genres des morceaux ne sont pas agrégés sur les artistes.

## Classer les morceaux

Ouvrir un dossier ou une playlist, puis choisir un **Genre brush**. La recherche reconnaît les noms, chemins et alias ; les libellés complets distinguent par exemple House › Deep de Dubstep › Deep. Cocher la case d'une ligne ajoute le genre choisi ; la décocher le retire. Cette action ne sélectionne pas le morceau et ne lance pas la lecture. Les commandes Play restent indépendantes.

Un morceau peut avoir plusieurs genres. Les parents sont implicites : House › Deep appartient également à House. House seul est un classement valable. Retirer le dernier sous-genre d'une famille laisse cette famille ; retirer directement la famille enlève ses genres. Le bouton **Undo**, ou Ctrl+Z hors d'un champ de texte, annule l'opération locale la plus récente de la session, y compris un lot.

Pour un lot, sélectionner les morceaux puis utiliser **Add to selection** ou **Remove from selection**. Les cases de pinceau restent indépendantes de cette sélection. Pendant **Saving**, attendre la fin de l'opération. Une erreur ne montre pas un faux résultat sauvegardé : **Retry** relance l'action, **Reload** relit les données. Une tâche annulée avant sa validation est entièrement abandonnée.

**+ Genre** crée immédiatement une définition avec un parent explicite, puis la choisit comme pinceau. Les favoris et les neuf derniers pinceaux sont accessibles dans la palette ; les touches 1 à 9 fonctionnent lorsque celle-ci a le focus. Chaque onglet et panneau conserve son propre pinceau et ses filtres.

Les **Local tags** sont des définitions libres séparées des genres. Choisir un tag puis utiliser **+ Tag** ou **− Tag** pour la sélection. Les méta-familles regroupent des genres et sont héritées par les morceaux ; elles ne sont pas affectées directement comme un genre.

## Filtrer sans perdre sa place

**Without brush** montre les morceaux sans le genre du pinceau ; **No subgenre** inclut les familles seules et les morceaux sans genre. **Filters** permet de combiner des inclusions en **All** (ET) ou **Any** (OU), avec des exclusions de genres toujours respectées, des méta-familles, des tags, des familles seules ou l'absence de genre. Les filtres peuvent être nommés, enregistrés et rechargés.

Les ancêtres du contexte d'un dossier sont protégés : dans Jump Up, l'exclusion de Drum & Bass n'est pas proposée. Une définition supprimée référencée par un filtre produit une erreur explicite ; corriger ou réinitialiser le filtre pour reprendre la liste.

Lorsqu'une affectation fait sortir une ligne du filtre courant, MTEE la conserve atténuée pour garder sa position. **Refresh results** recalcule la liste. Changer de filtre, pinceau, dossier ou tri réinitialise également cette rétention. La file de lecture déjà constituée est conservée.

## Administrer la taxonomie

**Manager** ouvre les genres, méta-familles et tags locaux : création, nom, alias, parent **Move to**, ordre, archivage/restauration et suppression ordinaire. Dans la liste des genres, déposer sur une ligne en fait un enfant ; déposer dans le tiers supérieur le place avant cette ligne, sous son parent. **Move to** et **Display order** permettent aussi ces opérations au clavier. Les UUID restent stables lors d'un renommage ou déplacement. Un genre archivé ne reçoit plus de nouvelles affectations ; ses anciennes affectations restent conservées.

La suppression ordinaire refuse une définition encore utilisée ou un genre ayant des enfants. La suppression forcée se trouve uniquement dans **Settings → Genres · Manager and Advanced**. Sélectionner le genre et saisir son chemin complet pour activer **Delete subtree**. Une sauvegarde cohérente et vérifiée précède l'opération. Tout le sous-arbre et ses liens sont retirés, sans réaffectation automatique à la famille ; les autres genres restent conservés. Undo restaure les seules cibles concernées et refuse un conflit avec une modification ultérieure.

## Amorçage et retrait historique

Ces commandes sont destinées à une intervention sur une base fermée. Tester sur copie, examiner l'aperçu et conserver le reçu d'application et la sauvegarde. Les destinations de rapport et de sauvegarde doivent rester hors des collections audio. Remplacer les valeurs d'exemple par celles de la base concernée.

```powershell
uv run python scripts/seed_track_genres.py --database BASE --copy-to COPIE
uv run python scripts/seed_track_genres.py --database COPIE --root-id UUID_RACINE --report-dir RAPPORT
uv run python scripts/seed_track_genres.py --database COPIE --apply-plan RAPPORT/plan.json
uv run python scripts/seed_track_genres.py --database COPIE --undo-operation UUID_OPERATION
```

L'aperçu ne migre ni n'écrit la base. L'application refuse un tableau modifié, périmé ou provenant d'une autre base. Un réamorçage préserve les corrections manuelles, y compris un retrait complet. Les dossiers **hard house - nu trance - bouncy stuff** et **techno, trance** sont exclus du mapping validé.

Le retrait des genres artistes de 107 exige une sauvegarde témoin antérieure à cet import et sa fenêtre de temps. Seuls les ajouts prouvés, avec les autres champs inchangés depuis le témoin, sont retirés ; les cas ambigus restent conservés et signalés. Sans preuve suffisante, aucun retrait n'est proposé.

```powershell
uv run python scripts/retire_artist_genres.py --database COPIE --witness TEMOIN --seed-start DEBUT_ISO --seed-end FIN_ISO --report-dir RAPPORT
uv run python scripts/retire_artist_genres.py --database COPIE --apply-plan RAPPORT/plan.json
uv run python scripts/retire_artist_genres.py --database COPIE --undo-operation UUID_OPERATION
```

L'ancien `genres_from_folders.py --apply` est refusé sur une base de version 21 ou supérieure. Les reçus personnels et sauvegardes restent locaux, hors Git. Voir le [rapport de validation](../validation/109-genres-morceaux-manager-tri.md) pour les contrôles effectués et les limites de recette.
