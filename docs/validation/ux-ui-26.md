# Validation du jalon 26 — Recherche et défilement

Date : 29 septembre 2026

## Décisions appliquées

- L’en-tête suit la capture de l’utilisateur : champ de recherche inchangé en haut à droite, commandes conservées en bas à droite.
- Échap rend le focus à la navigation sans effacer le filtre. Les raccourcis d’application qui pourraient consommer la saisie sont désactivés pendant le focus du champ.
- Le gain 1,25 s’applique aux crans verticaux de molette dans l’arbre Explorer et les vues List/Artwork. Les événements avec deltas en pixels, les gestes horizontaux et Shift+molette restent transmis au défilement Qt.
- Les scrollbars partagées restent visibles 1 200 ms après la fin de l’activité, puis suivent le fondu existant de 160 ms. Survol et glissement maintiennent leur visibilité.

## Vérifications réellement effectuées

- `pyside6-qmllint` sur les fichiers QML modifiés : code de sortie 0. Il affiche aussi des avertissements préexistants de propriétés et d’accès non qualifié dans `ExplorerPane.qml` et `Main.qml`.
- `git diff --check` : code de sortie 0.
- `scripts/build_windows.ps1` avec les sources du jalon 26 : réussite. Le script a confirmé la présence du QML et vérifié l’EXE autonome, le texte de licence FFmpeg, libmpv et les empreintes des exécutables FFmpeg/ffprobe.
- EXE reconstruit : `dist/MTEE.exe`, 220,85 Mio, SHA-256 `A8301BE4AB51251539E2272775B39542EB27AF01F851B55773349B840195AD22`.

## À faire par l’utilisateur

Les tests automatisés et la recette manuelle ne sont pas exécutés à la demande de l’utilisateur. Il pourra vérifier le focus au clavier, la recherche persistante, la molette et le délai de scrollbar dans l’EXE reconstruit.
