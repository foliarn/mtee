# Revue UX — étape 02

État au 24 septembre 2026 : première revue obtenue, prototype à refaire selon
l'esquisse de l'utilisateur ; seconde revue en attente.

Cette page sert de support à la revue des maquettes de MTEE. Les contenus
sont fictifs et le mode démo ne lit ni n'écrit aucun fichier audio. Chaque
scénario est reproductible avec `--demo --scenario <nom>`.

## Parcours examinés en revue 1 (prototype du 22 septembre)

Ces scénarios et captures documentent le premier prototype, refusé le
24 septembre. Ils seront remplacés par les scénarios du prototype révisé
listés dans l'ExecPlan 02.

| Scénario | Ce qu'il permet de vérifier | Capture |
|---|---|---|
| `browser` | Browser de référence, dossiers, onglets, table et lecteur inférieur | [Browser](screenshots/browser.png) |
| `browser-inspector` | Inspecteur visible, champs éditables et état initial de sauvegarde | [Inspector](screenshots/browser-inspector.png) |
| `browser-split` | Deux groupes de morceaux côte à côte, sélection et lecture distinctes | [Split view](screenshots/browser-split.png) |
| `browser-multi` | Multisélection, valeurs `Mixed values`, erreur de sauvegarde et Retry | [Multi-selection](screenshots/browser-multi.png) |
| `browser-no-artwork` | Vue Artwork et remplacement neutre d'une pochette absente | [No artwork](screenshots/browser-no-artwork.png) |
| `listening` | Grande pochette, progression, file stable, métadonnées et retour Browser | [Listening view](screenshots/listening.png) |
| `convert` | Réglages courants, Advanced, liste de sources et dossier de sortie | [Convert](screenshots/convert.png) |
| `convert-error` | Erreur par entrée, conservation de la source et Retry | [Convert error](screenshots/convert-error.png) |

Deux tailles proposées complètent la référence 1440 × 900 : [Browser à
1024 × 768](screenshots/browser-1024x768.png) et [Inspector à 1280 ×
720](screenshots/browser-inspector-1280x720.png). Ces essais ont été réalisés
à 100 % de mise à l'échelle logique sur la machine de développement ; les
échelles 125 % et 150 % restent à examiner sur un écran Windows configuré ainsi.

## Questions de décision

1. La densité du Browser est-elle confortable à 1440 × 900 et à 1024 × 768 ?
2. La hiérarchie entre dossiers, onglets, table, inspecteur et lecteur est-elle
   claire sans explication ?
3. Dans Listening view, l'équilibre entre pochette, progression, métadonnées et
   file correspond-il à l'usage attendu ?
4. La distinction entre morceau sélectionné et morceau en lecture est-elle
   visible dans `browser-split` et `browser-multi` ?
5. Les états `Saving`, `Saved`, `Could not save`, `Mixed values`, `Retry` et
   l'erreur de conversion expliquent-ils assez bien la suite à donner ?
6. À 1024 × 768, le basculement vers `Library` / `Inspector` conserve-t-il
   assez de contexte ?
7. Quels libellés, tailles ou espacements doivent changer avant l'explorateur
   fonctionnel ?

## Parcours clavier à effectuer

- Passer entre les contrôles avec Tab et vérifier que le contour bleu de focus
  reste visible.
- Dans Listening view, appuyer sur Espace avec le focus sur la vue et vérifier
  Play/Pause.
- Placer le focus dans un champ de métadonnée, saisir du texte puis appuyer sur
  Espace : la lecture ne doit pas changer.
- Sortir du champ pour afficher `Saving`, puis `Saved` ou `Could not save`.
- Dans `browser-multi`, modifier un seul champ et vérifier que les autres
  restent `Mixed values`.

## Réponse à consigner

### Revue 1 — 24 septembre 2026

Décision utilisateur : **prototype du 22 septembre refusé dans sa structure**.
L'utilisateur fournit une esquisse
([sketches/esquisse-2026-09-24.png](sketches/esquisse-2026-09-24.png)) et
demande une maquette précise avant tout développement fonctionnel.

Points retenus (détaillés dans [specification.md](specification.md)) :

- Fenêtre sans cadre à angles droits, barre de titre avec logo « M » et menus
  `File`, `Edit`, `View`.
- Barre d'activités verticale comme VS Code : Explorer, Playlists, Convert,
  Tasks, Plugins ; Profile et Settings en bas. Plugins et Profile sont des
  boutons réservés sans fonction pour l'instant.
- Zone d'éditeur à onglets comme VS Code, division en deux groupes conservée.
- Lignes de liste de style Spotify : numéro, pochette, titre et artiste sur
  deux lignes, album discret, BPM, pastille Camelot, durée ; `+` signifie Add
  to playlist. En-tête de dossier : nom et `n titles · durée · taille`.
- Double-clic ou Entrée : lecture. Édition : `Ctrl+I`, `Edit info` du menu
  contextuel ou icône ⓘ au survol. Le panneau droit a deux onglets, Info (suit
  la sélection) et Queue (ouvert par le bouton Queue de l'îlot).
- Îlot de lecture flottant de style Spotify (pochette, titre, `+`, Shuffle,
  Previous, Play/Pause, Next, Repeat, progression, Queue, volume, Fullscreen),
  masquable depuis `View` et Settings. Les trois carrés blancs de l'esquisse
  masquaient seulement des fonctions de Spotify et ne sont pas repris.
- Fullscreen player : barre d'activités conservée, barre latérale masquée,
  source, grande pochette, titre, artiste, waveform réservée, transport.
- Convert et Tasks passent dans la barre d'activités ; le bandeau
  `Session tasks` et les onglets supérieurs Browser / Listening / Convert
  disparaissent.
- Couleurs : gris sombres neutres, barre latérale plus sombre que le fond
  général, texte blanc, primaire vert néon / lime, secondaire contrastée.
  Les couleurs et formes de l'esquisse servaient seulement à distinguer les
  zones.

Palette : **A — Acid** choisie le 24 septembre 2026 (gris neutres, primaire
lime `#C6FF1A`, secondaire magenta `#FF2E88`).

Point ouvert : contenu futur de Profile et Plugins.

Prochaine revue : captures du prototype révisé, après application de ces
décisions.
