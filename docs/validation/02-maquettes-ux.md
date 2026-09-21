# Validation 02 — maquettes UX

État au 22 septembre 2026 : prototype terminé, revue utilisateur à obtenir.

## Environnement

- Windows 11 Professionnel 10.0.26200, AMD64.
- Python 3.12.14 dans l'environnement uv.
- PySide6 6.9.3, Qt Quick/QML.
- Échelle observée pendant la recette : 100 %, `devicePixelRatio=1.0`.

## Réalisation

Le prototype ajoute `DemoWorkspace` et huit scénarios déterministes. Ils
injectent uniquement des dictionnaires en mémoire dans les vues ; aucun accès
à la collection, Mutagen, libmpv ou FFmpeg n'est réalisé. Browser, Listening
view et Convert partagent le thème et les composants du socle.

Les captures de référence sont sous [docs/ux/screenshots](../ux/screenshots/).
Elles couvrent les huit scénarios ainsi que les tailles 1024 × 768 et 1280 ×
720. La capture réelle a été faite avec la plateforme Windows de Qt, car la
plateforme `offscreen` ne fournit pas de police exploitable.

## Commandes exécutées

Depuis la racine du dépôt :

    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m ruff format --check .
    .\.venv\Scripts\python.exe -m pyright
    .\.venv\Scripts\python.exe -m pytest tests/unit/test_demo_scenarios.py tests/ui/test_demo_navigation.py

Les huit scénarios ont aussi été ouverts avec `--smoke-test` et ont quitté avec
le code 0. Les tests de l'étape ajoutent les scénarios déterministes, la
séparation de leur état mutable et la navigation Qt entre les trois espaces.

## Résultats observés

- Browser affiche dossiers, onglets, table, sélection, ligne en lecture et
  lecteur inférieur.
- Browser multi affiche trois sélections, `Mixed values` et l'erreur de
  sauvegarde simulée.
- La vue compacte à 1024 × 768 replie l'explorateur et conserve la table.
- Listening view masque le lecteur inférieur, conserve la file et montre la
  progression classique.
- Convert distingue l'entrée en erreur, le message d'action et la conservation
  de la source.
- Aucun recouvrement ou texte coupé n'a été retenu dans les captures finales
  1440 × 900, 1280 × 720 et 1024 × 768 ; l'inspecteur devient défilable lorsque
  la hauteur est faible.

## Limites

La revue clavier et la mise à l'échelle 125 % / 150 % n'ont pas encore été
effectuées par l'utilisateur. La décision produit est donc ouverte. La
conversion, la lecture, l'écriture des métadonnées et le dossier de sortie
restent des simulations de maquette.
