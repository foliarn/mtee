---
name: Revue artistes — pilote local
description: Système visuel observé de l’outil personnel de revue des artistes.
colors:
  paper: "#f4f6f4"
  ink: "#20352d"
  muted: "#54685d"
  line: "#d5dfd8"
  accent: "#245d43"
  soft: "#e5efe8"
  warn: "#815720"
  warn-bg: "#fff1d9"
  white: "white"
  focus: "#438361"
  accent-hover: "#174b34"
  table-head: "#f0f4f1"
  row-line: "#e5ebe6"
  row-hover: "#f3f7f4"
  badge-neutral: "#edf1ee"
  keep-bg: "#e5f0e8"
  issues-bg: "#fff7e9"
  failure-ink: "#922f24"
  failure-bg: "#fff0e9"
  selection-bg: "#c4decc"
  selection-ink: "#193928"
  scrollbar-thumb: "#a6b9ac"
typography:
  headline:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "clamp(24px, 2.4vw, 34px)"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.7px"
  title:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "26px"
    lineHeight: 1.2
    letterSpacing: "-.4px"
  section:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "15px"
    lineHeight: 1.5
  table:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "13px"
    lineHeight: 1.5
  label:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "12px"
    lineHeight: 1.5
  badge:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
    fontSize: "11px"
    lineHeight: 1.5
rounded:
  badge: "3px"
  control: "5px"
  workspace: "7px"
spacing:
  compact: "6px"
  control-gap: "8px"
  field-gap: "5px"
  small: "12px"
  normal: "16px"
  section: "20px"
  panel: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
    typography: "{typography.body}"
  button-secondary-hover:
    backgroundColor: "{colors.soft}"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
    typography: "{typography.body}"
  badge:
    backgroundColor: "{colors.badge-neutral}"
    textColor: "{colors.muted}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
    typography: "{typography.badge}"
  badge-keep:
    backgroundColor: "{colors.keep-bg}"
    textColor: "{colors.accent}"
  badge-warning:
    backgroundColor: "{colors.warn-bg}"
    textColor: "{colors.warn}"
  decision-selected:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
    typography: "{typography.table}"
  report-card:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "20px"
---

# Design System: Revue artistes — pilote local

## Overview

**Creative North Star: "Le poste de revue"**

Un poste de revue lisible et familier : des surfaces claires, une encre vert sombre et des contrôles reconnaissables laissent la place aux noms, aux sources et aux décisions. La densité sert la comparaison ; les états utilisent simultanément du texte, des attributs accessibles et des changements de fond.

Cette description enregistre le système observé dans le code du pilote. Elle ne constitue pas une identité visuelle approuvée pour MTEE, une maquette validée ou une préférence de framework. Segoe UI correspond ici à un outil personnel dans un environnement Windows.

**Key Characteristics:**

- Palette claire vert-gris et ambre pour les réserves.
- Typographie familière, hiérarchie compacte et nombres tabulaires.
- Surfaces planes, séparateurs fins et coins légèrement arrondis.
- États explicites, focus visible et disposition empilée sur petit écran.

Source de vérité : `style.css`, complété par les composants de `index.html` et `app.js`. Le nom du poste de revue est une description du résultat, pas une nouvelle validation utilisateur. Le périmètre produit et les décisions encore ouvertes restent dans `PRODUCT.md`.

## Colors

Le vert-gris calme soutient la lecture ; l’accent vert indique les actions et les états positifs, tandis que l’ambre signale les réserves.

### Primary

- **Vert de décision** (`accent`) : liens, action principale, choix de tri actif, progression et cases cochées.
- **Vert appuyé** (`accent-hover`) : survol de l’action principale.
- **Vert de focus** (`focus`) : contour clavier visible, indépendant de la sélection.
- **Fond vert discret** (`soft`, `keep-bg`) : contexte, ligne sélectionnée, survol de boutons et badge « Garder ».

### Neutral

- **Papier vert-gris** (`paper`) et **surface blanche** (`white`) : fond de page et panneaux.
- **Encre vert sombre** (`ink`) et **encre secondaire** (`muted`) : information principale, métadonnées, labels et compteurs.
- **Séparateurs clairs** (`line`, `row-line`) : contours des contrôles, divisions des panneaux et lignes du tableau.
- **Fonds de lecture** (`table-head`, `row-hover`, `badge-neutral`) : en-tête de tableau, survol de ligne et badges neutres.
- **Sélection de texte** (`selection-bg`, `selection-ink`) et **curseur de défilement** (`scrollbar-thumb`) : traitements utilitaires définis dans la feuille.

L’ambre (`warn`, `warn-bg`, `issues-bg`) distingue les incertitudes et les points à vérifier. Les couleurs `failure-ink` et `failure-bg` sont réservées au message d’échec de chargement. Ce sont des états fonctionnels, pas une palette décorative secondaire.

**The Explicit State Rule.** Associer les couleurs d’état à un libellé ; les propositions IA et la revue humaine gardent des intitulés distincts.

## Typography

**Body Font:** Segoe UI, puis system-ui et sans-serif.

**Character:** La famille système sert les tableaux, les labels et les dossiers de travail. La feuille ne définit ni police décorative, ni rôle display distinct, ni police monospace.

### Hierarchy

- **Headline** : titre de page fluide, graisse semi-forte et interlettrage resserré ; token `headline`.
- **Title** : nom de l’artiste et titre du bilan ; token `title`. La graisse n’est pas déclarée par la feuille pour ce rôle : elle reste celle de l’élément h2 du navigateur.
- **Section** : titres courts de preuves et de formulaire ; token `section`.
- **Body** : corps et contrôles standards ; token `body`.
- **Table** : lignes, preuves, contrôles de décision et métadonnées ; token `table`.
- **Label** : labels de champs, notes et en-têtes ; token `label`.
- **Badge** : petits états de tri et rôles ; token `badge`.

Les paragraphes de contexte et les liens d’export utilisent aussi une taille intermédiaire (14px). Le compteur de corrections reste discret (12px). Les nombres des tableaux et du bilan emploient `font-variant-numeric: tabular-nums`.

## Layout

La page possède un conteneur centré (max-width: 1600px) avec un retrait horizontal de page. Les barres d’outils sont flexibles et leurs contrôles peuvent passer à la ligne. Les espacements sont une échelle pragmatique, pas une grille mathématique uniforme.

Depuis la révision par exceptions, le tableau occupe toute la largeur. La barre compacte de validation de la page reste sticky ; aucun grand titre ni bandeau de contexte. Le dossier facultatif est un panneau fixe à droite (16px), de largeur `min(580px, calc(100vw - 32px))` et hauteur `calc(100vh - 32px)`, avec défilement interne. Fermer le panneau conserve les corrections.

À 1100px et moins, les retraits et cellules se resserrent. À 800px et moins, les sections du récap s'empilent ; la recherche occupe sa ligne. Le tableau reste un tableau à défilement horizontal dans son conteneur, sans débordement de page. Le panneau conserve une largeur bornée au viewport. La pagination borne chaque page à 100 artistes, avec sélection directe du numéro et boutons Précédente/Suivante.

## Elevation & Depth

Le tableau et les cartes restent plans. Le panneau facultatif utilise une ombre décalée `-8px 8px 28px #20352d26` pour rendre sa superposition visible. Le focus clavier reste un contour (3px, décalage 3px).

**The Flat Surface Rule.** Garder les surfaces ordinaires planes ; réserver l'ombre à la superposition du dossier.

## Shapes

Les coins sont légèrement arrondis : badge, contrôle et poste de revue correspondent aux trois tokens de rayon. Les onglets restent rectangulaires et sont repérés par leur bordure basse. Les traits ordinaires sont fins (1px), la séparation du formulaire est renforcée (2px) et l’onglet actif utilise un trait plus marqué (3px).

## Components

### Buttons

Contrôles familiers et libellés explicites. Le bouton principal utilise l’accent ; le bouton standard reste blanc avec un contour clair. Le survol standard devient teinté, le survol principal plus sombre. Les actions textuelles sont soulignées et transparentes. Les liens de profil réutilisent le contour des boutons avec un retrait plus compact (6px 11px).

Le bouton principal valide uniquement la page affichée, y compris les valeurs inchangées. Il est désactivé pour une page vide. Pendant la requête, les contrôles du main sont désactivés et l'état « Enregistrement… » est écrit. Aucune confirmation individuelle ; les brouillons hors page sont conservés.

### Chips

Catégories du récap affichées en lignes cliquables, libellé à gauche et nombre à droite. Dans le tableau artistes, les rôles sont des cases à cocher et le tri une liste ; la provenance « Accepté par défaut », « Corrigé » ou « Correction à enregistrer » est textuelle.

### Cards / Containers

Les cartes du bilan sont blanches et bordées, sans ombre. Le tableau reste un conteneur unique. Le dossier est fermé à l'arrivée et ne partage pas la largeur du tableau.

### Inputs / Fields

Champs et listes blancs avec contour clair, coins de contrôle et hauteur minimale (39px). Les labels discrets sont au-dessus ; les cases à cocher restent des contrôles natifs teintés avec l’accent. Le champ de notes est redimensionnable verticalement et possède une hauteur minimale (75px). Les erreurs de sauvegarde sont textuelles ; la feuille ne définit pas de contour d’erreur individuel.

### Navigation

Les trois vues sont des boutons dans une navigation de rapports. L’état actif combine `aria-pressed`, texte renforcé et bordure basse verte. Les compteurs sont plus petits et secondaires. La navigation conserve sa disposition horizontale sur petit écran avec des espaces et caractères réduits.

### Tableau et dossier de revue

Producer et DJ ont des cases et filtres séparés. Les quatre rôles occupent une grille de deux colonnes dans les lignes. Cocher Producer coche aussi DJ ; DJ reste modifiable séparément. Le dossier suit la même règle.

Les lignes sont séparées par un trait clair ; une correction non enregistrée teinte la ligne en ambre (`#fff7e9`). Le nom ouvre les sources et champs secondaires. Rôles, Bass-related et tri restent éditables dans la ligne ; les profils sont des liens textuels compacts. Les anomalies se lisent sous le nom.

Le dossier juxtapose nom, profils, proposition IA, alertes, sources dépliables et formulaire humain. Les intitulés et les sources rendent la provenance visible. Après sauvegarde, les boutons de profil reflètent les URL retenues par l’utilisateur. Le suivi Spotify reste manuel et n’a aucun état d’action automatisée.

## Do's and Don'ts

### Do:

- **Do** reprendre les primitives observées pour étendre cet outil et garder les libellés d’état visibles.
- **Do** conserver le focus visible sur les contrôles et liens.
- **Do** laisser les textes, les tableaux et les sources porter l’information.
- **Do** garder les propositions IA et les décisions humaines identifiables par leurs intitulés.

### Don't:

- **Don't** ajouter des illustrations décoratives dans cet outil de revue.
- **Don't** présenter une couleur seule comme une décision ou une certitude.
- **Don't** déduire de ce pilote une identité approuvée pour MTEE ou une préférence de framework.

Les composants, breakpoints et états viennent du code ; la documentation n’ajoute aucune permission ni validation. Les rampes tonales de la sidecar sont des aperçus synthétiques pour le panneau de documentation et ne sont pas des tokens de l’application.


Révision du 6 octobre : suppression des grands titres, bandeaux, notes de bas de page et footer explicatif. Récap sans carte de mode de revue ; entrées filtrantes et alertes de genre par morceau. Onglet Morceaux : tags observés, genres retenus et tags ignorés/contradictoires séparés.


Collection complète : navigation Artistes / Validés / Morceaux / Récap, compteurs propres à chaque population. Même tableau et mêmes filtres pour les deux états de revue ; Valider cette page devient Enregistrer cette page dans Validés. Les morceaux ont leur recherche et leur pagination indépendante. Le mot Pilote disparaît de l’en-tête.
