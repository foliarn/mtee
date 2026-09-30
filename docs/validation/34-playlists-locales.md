# Validation 34 — Playlists locales

État du 2026-09-30 : **cadrage et prototype de revue préparés, validation utilisateur de maquette en attente**. Aucun backend de playlists, migration, import/export réel ou packaging n'est livré à cette étape. Les décisions de comportement sont confirmées dans `../decisions/34-playlists.md` ; elles ne constituent pas une validation du rendu.

## Environnement et isolation

Windows, Python 3.12 via uv, PySide6/Qt 6.9.3. Le prototype est `../ux/mockups/PlaylistReview.qml`, chargé par `review_playlists.py`. Les fixtures sont inventées et entièrement en mémoire. Aucun catalogue personnel, fichier audio ou SQLite applicatif n'a été ouvert ou modifié. Les actions Play ne produisent pas de son ; les boutons d'échange ne choisissent ni n'écrivent de fichiers.

Qt hors écran n'énumère pas les polices Windows ; le lanceur charge les polices Segoe UI installées lorsque le fallback est nécessaire. Les captures finales utilisent Segoe UI, le fallback déjà prévu par MTEE. La police de l'application et ses fichiers sources restent inchangés.

## Contrôles terminés

Depuis la racine du dépôt :

    uv run python docs/ux/mockups/review_playlists.py --capture
    uv run python docs/ux/mockups/review_playlists.py --verify-interactions
    uv run python docs/ux/mockups/review_playlists.py --native --verify-interactions
    uv run ruff check docs/ux/mockups/review_playlists.py
    uv run ruff format --check docs/ux/mockups/review_playlists.py
    uv run pyright docs/ux/mockups/review_playlists.py
    git diff --check

Les douze scènes ont été produites à 1440 × 900, 1280 × 720 et 760 × 820 selon leur usage, sans avertissement QML. Les interactions du prototype passent hors écran et sur la plateforme Windows native : révélation de recherche, saisie/filtrage, lecture fictive du disponible visible, repli sans perte du filtre, ouverture du menu `+`, retrait/ajout immédiat sans fermeture, fermeture par Échap et cœur mettant à jour Liked tracks.

L'inspection visuelle des captures page, recherche, menu, colonnes, vide, largeur réduite, export et import a porté sur alignement des commandes, limites du tableau, lisibilité, ligne indisponible et accès aux actions. Corrections : chargement de la police hors écran, taille réelle des icônes, colonnes/actions qui dépassaient, lien Locate file à petite largeur, défilement vertical au-dessus de l'îlot, pied du menu qui dépassait, focus du popup pour Échap et contraste des coches. Les captures finales ont été régénérées après les corrections QML. Il ne s'agit pas d'un parcours manuel sur une bibliothèque réelle.

Ruff et Pyright ciblés ne signalent plus d'erreur. Le détecteur Impeccable a été exécuté sur le QML et a renvoyé une liste vide ; la couverture QML de ce détecteur n'étant pas établie, ce résultat ne constitue pas un audit d'accessibilité. Les contrôles utiles sont le chargement Qt, les interactions et l'inspection des captures.

Les premiers essais ont rencontré des erreurs de syntaxe QML, un appel QTest réservé à QWidget et des types Qt insuffisamment précisés ; ils ont été réparés dans le lanceur/prototype. Le contrôle final natif passe, y compris la saisie numérique des touches et la conservation exacte du texte entré.

## Documents et publication

Le cadrage, le plan 34, l'addendum de `PLAN.md`, l'index et le dossier `../ux/review-playlists-2026-09-30.md` décrivent le même périmètre local. Les liens locaux, l'encodage UTF-8, les SVG et dimensions PNG sont contrôlés avant indexation. Spotify reste dans `../ideas/spotify-playlists.md` et ne reçoit aucun jalon d'implémentation dans le plan 34.

Les modifications utilisateur préexistantes de `.gitignore`, `AGENTS.md`, `.agents/`, `.codex/` et `skills-lock.json` ne sont pas incluses dans le commit. Le commit et son push sont rapportés dans la conversation après vérification du distant ; ce fichier ne s'attribue pas un hash auto-référentiel.

## Travail restant

Obtenir l'accord de revue, puis implémenter et vérifier la migration sauvegardée, les services de persistance, les modèles Qt réels, les menus/actions, les dossiers imbriqués/épingles, les likes, les contrôles de doublons, la résolution, les couvertures, l'import/export et leur reprise. La maquette ne valide pas les écritures, le son, le drag-and-drop réel ni une collection volumineuse.

Les tests du backend et la recette de l'application fonctionnelle depuis les sources restent à créer/exécuter aux jalons 34.2–34.5. Aucun build Windows ni smoke-test d'EXE n'a été lancé ; le packaging n'est pas validé.
