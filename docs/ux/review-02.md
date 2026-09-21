# Revue UX — étape 02

État au 22 septembre 2026 : prototype préparé, revue utilisateur en attente.

Cette page sert de support à la revue des trois espaces de MTEE. Les contenus
sont fictifs et le mode démo ne lit ni n'écrit aucun fichier audio. Chaque
scénario est reproductible avec `--demo --scenario <nom>`.

## Parcours à examiner

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

Décision utilisateur : _en attente_.

Points acceptés : _à remplir pendant la revue_.

Points à modifier : _à remplir pendant la revue_.

Date de la décision : _à remplir_.
