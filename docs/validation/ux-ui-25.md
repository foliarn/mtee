# Explorateur — validation du plan 25

## Portée

Source de départ : `da69218` (`main`). Le modèle d’arbre applique maintenant les insertions et déplacements à leurs vrais index au lieu d’ajouter les enfants à la fin puis de réordonner les lignes. Il conserve les index persistants. La vue enregistre l’identité de l’ancre et son décalage vertical ; au repli, elle retombe sur le dossier parent quand la ligne ancrée disparaît.

Livraison : commit `e46a258` sur `main`, push vers `origin/main` vérifié.

Un clic simple sur une piste ouvre son dossier et ne la sélectionne qu’après confirmation de sa présence dans les résultats affichés. Le double-clic demande l’activation au `WorkspaceModel` : il ouvre/réutilise l’onglet, attend les lignes chargées en arrière-plan, sélectionne la piste, la révèle dans la liste ou la grille et la lance une fois. Une génération et le groupe/onglet actif protègent contre les réponses périmées. Quand la recherche masque la piste, le texte, les résultats et la sélection visibles sont préservés ; le worker récupère et vérifie le snapshot source, puis joue une file d’un morceau sans révélation.

## Contrôles exécutés

Environnement : Windows 11, Python 3.12.14.

- `uv run ruff check src/mtee/models/workspace_model.py src/mtee/models/folder_tree_model.py` — réussi.
- `uv run ruff format --check src/mtee/models/workspace_model.py src/mtee/models/folder_tree_model.py` — réussi.
- `uv run python -m compileall -q src/mtee` — réussi.
- `uv run python -m mtee --demo --smoke-test --data-dir .local/validation/ux-ui-25-qml` — réussi ; fenêtre de démo chargée puis fermée.
- `uv run python -m mtee --data-dir .local/validation/ux-ui-25-live --smoke-test` — réussi ; modèle live et fenêtre principale chargés avec un profil de données isolé.
- `git diff --check` — réussi.
- `pwsh -NoProfile -File scripts/build_windows.ps1 -DistDirectory dist -WorkDirectory build/ux-ui-25-final` — réussi ; `dist/MTEE.exe` reconstruit à 220,85 MiB. Le script a validé les ressources QML, les empreintes libmpv/FFmpeg et les versions FFmpeg/ffprobe embarquées.

## Contrôles restant à faire

Les tests pytest et la recette interactive de l’arbre/listing/lecteur n’ont pas été lancés, conformément à la demande de l’utilisateur. Le saut de défilement a été localisé dans la séquence du modèle, mais n’a pas été reproduit manuellement. Aucune mesure de coordonnée au pixel, vérification tactile, écoute ou recette sur plusieurs groupes n’est revendiquée.

## Reprise

Essayer dans `dist/MTEE.exe` : ouvrir une branche à mi-parcours, replier et développer des sous-dossiers, puis effectuer un double-clic sur une piste hors écran en mode liste et Artwork. Refaire avec une recherche qui masque la piste et vérifier que seuls le morceau joué et son îlot changent, sans déplacer la liste ni modifier sélection, texte ou résultats. Vérifier enfin le cas où le fichier source a disparu avant l’activation.
