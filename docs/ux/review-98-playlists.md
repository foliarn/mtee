# Revue de maquette — plan 98

Préparée le 2026-10-01. Cette maquette QML ne lit aucune collection et ne modifie aucune playlist. Elle montre les interactions proposées avant leur branchement aux modèles Qt et services Python. La validation utilisateur de cette maquette reste attendue.

## Parcours de revue

Depuis la racine du dépôt, ouvrir une scène dans une fenêtre Windows native :

    uv run python scripts/review_playlists_98.py --scene playback-states

Le lanceur accepte `--scene`, `--width`, `--height` et `--output`. Les dimensions minimales sont 880 × 600. Sans sortie, la fenêtre reste ouverte pour inspection. Les scènes disponibles sont `creation-menu`, `creation-resume`, `creation-opened`, `title-edit`, `cover-hover`, `drag-single`, `drag-multiple`, `drop-playlist`, `insert-list`, `insert-artwork`, `playback-states` et `playback-paused`.

## Correspondance avec les exigences

| Exigence | Captures et choix visible |
|---|---|
| P2.1–P2.5 | [Menu compact](playlists-98-2026-10-01/creation-menu-1440x900.png), [avec Resume](playlists-98-2026-10-01/creation-resume-1440x900.png), [playlist créée et ouverte](playlists-98-2026-10-01/creation-opened-1440x900.png). Les actions du menu occupent des lignes contiguës ; le nouveau nom est un exemple fictif de décompte. |
| P2.6–P2.7 | [Édition par le titre](playlists-98-2026-10-01/title-edit-1440x900.png), [survol de la mosaïque](playlists-98-2026-10-01/cover-hover-1440x900.png). Le grand voile et `Change cover` couvrent la mosaïque ; le bouton d'en-tête `Edit playlist` est absent. |
| P3.1–P3.3 | [Un morceau](playlists-98-2026-10-01/drag-single-1440x900.png), [trois morceaux](playlists-98-2026-10-01/drag-multiple-1440x900.png), [cible de sidebar](playlists-98-2026-10-01/drop-playlist-1440x900.png), [insertion List](playlists-98-2026-10-01/insert-list-1440x900.png), [insertion Artwork](playlists-98-2026-10-01/insert-artwork-1440x900.png). L'étiquette sombre reprend titre/artiste, puis `and 2 other tracks…` ; le contour et le trait emploient `Theme.primary`. |
| P4.1–P4.3 | [Lecture active et panneau divisé](playlists-98-2026-10-01/playback-states-native-1440x900.png), [pause active](playlists-98-2026-10-01/playback-paused-1440x900.png), [taille minimale](playlists-98-2026-10-01/playback-states-880x600.png). Un emplacement de 32 px reste réservé avant chaque pochette, y compris quand l'icône est masquée. |

La [grille Artwork à 880 × 600](playlists-98-2026-10-01/insert-artwork-880x600.png) illustre le retour à la ligne et le trait d'insertion vertical. La carte sous l'étiquette reste lisible après disparition du proxy ; pendant le geste, l'étiquette montre le lot sans déplacer les cartes.

## Vérifications et limites

Les douze scènes ont chargé sans avertissement QML et leurs captures hors écran ont été produites le 2026-10-01. La capture native `playback-states-native-1440x900.png` a aussi été produite sous Windows. Les premières captures ont révélé des glyphes manquants et un lecteur bas de page de largeur nulle ; la maquette a été corrigée avec les icônes MTEE et une largeur explicite, puis les scènes concernées ont été recapturées. Les captures ont été inspectées pour la lisibilité, les bordures, le placement et la taille minimale.

La maquette est une proposition visuelle statique : elle ne vérifie ni la persistance, ni le vrai glisser-déposer QML, ni la lecture libmpv. Les scènes de déplacement montrent des positions représentatives ; l'étiquette n'est pas encore asservie à la souris. Le parcours fonctionnel et les cas A01–A24 appartiennent aux jalons 98.2–98.5, après validation explicite de cette revue.
