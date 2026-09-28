# Revue des plans UX/UI 26 à 28

**Statut : choix utilisateur attendu.** Les images sont une planche QML statique, fondée sur `docs/ux/specification.md`. Elles ne modifient ni l’interface livrée ni ses données. Régénérer avec `uv run python docs/ux/mockups/render_review.py` depuis la racine ; le rendu utilise Qt Quick en mode logiciel et n’ouvre aucune collection.

## Plan 26 — En-tête de dossier

La recherche et les commandes List, Artwork et Choose columns partagent une même ligne et leurs centres verticaux sont alignés. Le nom et le résumé gardent chacun leur propre ligne. Les boutons restent groupés quand la largeur diminue ; le nom long est élidé.

À 1440 × 900, l’éditeur fait 852 px entre la barre latérale et le panneau Info : [recherche vide](review-ux-ui-2026-09/header-wide-1440x900.png). À 1280 × 720, il fait 712 px avec le champ rempli : [recherche filtrée](review-ux-ui-2026-09/header-medium-1280x720.png). Le cas partagé montre deux groupes de 415 px dans une fenêtre de 1100 px : [groupes divisés](review-ux-ui-2026-09/header-split-1100x760.png).

**À confirmer :** approuves-tu cet alignement et cette réduction, ou veux-tu un ajustement avant le code de recherche et de défilement du plan 26 ? Le texte et les résultats filtrés restent conservés selon ta décision déjà consignée.

## Plan 27 — Colonnes, pochettes et commandes de ligne

Le tableau par défaut présente `Title | Artist | Date created | BPM | Key`, sans numéro ordinal, avec les pochettes visibles. Le menu liste les douze colonnes ainsi que Show artwork et Reset columns. Sa position flotte au-dessus de la liste pour rester atteignable avec peu de colonnes. Les commandes de lecture et d’information occupent une bande fixe de 36 px avant les colonnes et les pochettes ; elles gardent donc leur place même si Title ou les pochettes sont masqués. Une piste sélectionnée et en lecture reste indiquée par fond de sélection, chevron lime et titre lime quand celui-ci est visible.

- [Menu complet et colonnes par défaut](review-ux-ui-2026-09/columns-menu-1440x900.png)
- [Beaucoup de colonnes](review-ux-ui-2026-09/columns-many-1600x900.png)
- [Title et pochettes masqués](review-ux-ui-2026-09/columns-reduced-1440x900.png)
- [Une seule colonne, avec le menu encore accessible](review-ux-ui-2026-09/columns-single-1280x720.png)
- [Menu dans un groupe partagé de 415 px](review-ux-ui-2026-09/columns-split-1100x760.png)

Les choix déjà documentés — colonnes par défaut, personnalisation globale, pochettes configurables et aucune colonne `#` — restent ceux du plan. **À confirmer :** la bande d’actions fixe à gauche te convient-elle ? Elle est distincte des colonnes configurables ; le numéro de piste enregistré dans les tags reste inchangé.

## Plan 28 — Comparaison de waveforms

### Diagnostic du rendu existant

Le calcul actuel produit du PCM stéréo 22 050 Hz, agrégé par fenêtres de 20 ms en extrema min/max. Il conserve une pyramide de réduction et la vue choisit un niveau d’au plus 1 200 points. Le modèle fusionne les extrema des canaux pour son aperçu. `WaveformView.qml` dessine un trait vertical par point, avec une largeur minimale de 1 px ; chaque changement de données ou de position demande actuellement un repaint du Canvas. Les données et le cache ne comportent ni énergie RMS, ni valeur grave/médium/aigu. Les extrema seuls ne permettent donc pas de fabriquer des bandes de fréquences réelles.

Cette inspection du code ne remplace pas le diagnostic sur un corpus audio : aucun morceau utilisateur, signal synthétique décodé par le service, mesure de performance ou gain de lisibilité n’a été observé. Le signal des maquettes est généré directement dans QML et représente une intro calme, des passages plus denses et un creux. Les niveaux de bandes sont eux aussi synthétiques. Les captures ne prétendent pas représenter l’analyse d’un fichier.

### Les variantes proposées

La comparaison conserve le même morceau synthétique, la même taille de vue (1440 × 900), la même durée (4:36) et la même position courante (1:18, environ 28,3 %). La portion lue est assombrie dans les trois propositions et le repère temporel garde une couleur indépendante.

![Comparaison monochrome, 3 bandes et mélange RGB](review-ux-ui-2026-09/wave-compare-1440x900.png)

La grille montre chaque variante au début, à 1:18 et à la fin ; la capture d’états illustre le curseur à 0 et à la fin, la pause à mi-parcours ainsi que les états Preparing et Unavailable. La vue étroite mesure 508 px de large.

- [Chaque variante au début, au milieu et à la fin](review-ux-ui-2026-09/wave-positions-1440x900.png)
- [Pause, extrémités et états indisponibles](review-ux-ui-2026-09/wave-edges-1280x900.png)
- [Vue étroite de 508 px](review-ux-ui-2026-09/wave-narrow-620x900.png)

| Choix | Avantage proposé | Coût et limite |
|---|---|---|
| Monochrome | Réutilise le cache min/max existant et reste dans la palette actuelle. | La géométrie doit suffire à distinguer les passages ; la capture seule ne prouve pas une amélioration. |
| 3 bandes | Sépare visuellement trois zones de fréquences. | Exige un vrai calcul audio hors thread UI et une version de cache dédiée ; le cyan montré est un accent supplémentaire proposé. |
| RGB | Résume les trois niveaux par une couleur composite. | Exige les mêmes calculs et une règle de mélange stable ; les teintes colorées s’éloignent de la palette Acid et peuvent être moins lisibles. |

**Recommandation de mise en œuvre :** choisir le monochrome si les données disponibles doivent rester suffisantes. Choisir 3 bandes ou RGB seulement si la séparation fréquentielle apporte une lecture visuelle que tu préfères aux coûts de calcul et de cache. Aucun sélecteur permanent entre variantes n’est proposé.

**À confirmer :** quelle variante unique veux-tu faire implémenter ? La demande de comparaison n’engage pas encore le développement d’une variante ni le retour du zoom, de la boucle A/B ou des cues.

## Réponse attendue

Tu peux répondre en une ligne, par exemple : **« 26 : validé ; 27 : bande d’actions validée ; 28 : monochrome. »** Si tu souhaites des changements, indique seulement les éléments concernés. Après validation, les plans 26, 27 et 28 pourront s’enchaîner dans cet ordre, avec une compilation de l’EXE à chaque jalon applicatif.
