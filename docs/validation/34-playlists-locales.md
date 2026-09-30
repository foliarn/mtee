# Validation 34 — Playlists locales

État du 2026-09-30 : **maquette approuvée, playlists locales fonctionnelles implémentées et vérifiées depuis les sources**. La section prototype ci-dessous conserve ses preuves historiques ; les résultats fonctionnels sont détaillés plus bas. Aucun packaging n’est livré. Les décisions de comportement sont confirmées dans `../decisions/34-playlists.md` ; elles ne constituent pas une validation du rendu.

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

## Recette fonctionnelle terminée

Les tests utilisent des WAV synthétiques et des bases sous les répertoires temporaires pytest. Aucun fichier audio personnel n’est modifié. Le schéma passe de 15 à 16 avec sauvegarde ; les anciennes métadonnées inconnues et réglages sont conservés. Les tests de transaction couvrent les ordres périmés, duplications avec nouveaux UUID d’entrées, cycles de dossiers, suppression d’un dossier non vide, likes, doublons musicaux et entrées devenues absentes.

Commande backend/non-régression :

    uv run pytest tests/unit/test_playlist_identity.py tests/integration/test_playlists_repository.py tests/integration/test_playlist_exchange.py tests/integration/test_database_migrations.py tests/integration/test_library_repository.py tests/integration/test_runtime_shutdown.py tests/unit/test_artwork_provider.py

Résultat final : **34 passed**. Échange entre bases avec chemins et UUID différents, correspondance SHA-256 exacte, ambiguity de copies identiques, fichiers sources inchangés, traversals et noms Windows refusés, absence de remplacement, annulation/reprise et refus d’un fichier extrait modifié vérifiés.

    uv run pytest tests/ui/test_playlists_ui.py

Le parcours UI passe hors écran et avec `QT_QPA_PLATFORM=windows` : **1 passed** sur chaque plateforme. Il exerce le formulaire de création réel, les colonnes indépendantes, le créateur commun, la copie d’image malgré suppression de l’original, recherche/repli, Play des résultats visibles, ajout/retrait immédiat dans le popup ouvert, drag vers la sidebar et réordonnancement par drag, likes, sélection convertie en UUID local, maintien de la file de lecture, déplacement d’une source et ligne grisée, export léger, aperçu d’import/création et restauration après fermeture/réouverture du runtime. La recette appelle `forceLayout` après un filtre pour attendre la matérialisation des délégués avant le geste suivant. Aucun avertissement QML n’est admis. Les fenêtres sont réelles ; les entrées QTest sont automatisées, pas des gestes d’un opérateur humain.

Le backend audio est contrôlé dans `tests/integration/test_mpv_playback.py` : les deux tests libmpv passent avec sortie audio `null` (décodage, seek, pause, piste suivante). La console signale toutefois des exceptions Windows `0xe24c4a02` dans le thread mpv tout en retournant un succès ; une écoute humaine et une stabilité audio de longue durée ne sont pas validées. Le test de playlists utilise un backend audio contrôlé pour vérifier exactement les files, indépendamment du périphérique sonore.

Smoke-test :

    uv run python -m mtee --data-dir .local/validation/34-playlists-functional --smoke-test

Sortie 0, base isolée fraîche. Aucun EXE construit, aucun `smoke_packaged` exécuté.

Captures de l’application fonctionnelle inspectées en deux passages bornés : [page](playlists-2026-09-30/playlist.png), [menu](playlists-2026-09-30/add-menu.png), [absence](playlists-2026-09-30/missing.png), [largeur réduite](playlists-2026-09-30/narrow.png). Grande pochette, commandes alignées, popup contenu dans la fenêtre et ligne indisponible visibles. L’inspection a corrigé le chargement des images locales dans CoverArt, le profil de largeur de colonnes et les compteurs de durée. Les images ne contiennent que des fixtures synthétiques.

Charge de 10 000 entrées absentes, sur base synthétique : création 0,162 s, lecture 0,051 s, remplacement du modèle Qt 0,026 s. Mesure limitée au backend/modèle, pas un benchmark de 10 000 fichiers audio ni du rendu natif complet.

## Contrôles statiques et limites du socle

Ruff check/format et Pyright ciblés sur les 14 modules nouveaux et WorkspaceModel/app/tests sont verts. Les anciennes erreurs Pyright de WorkspaceRepository et LibraryRepository restent exclues du résultat ciblé ; le diff de ces fichiers est vérifié séparément. LibraryRepository ne reçoit qu’un flag `identityUncertain` ; ses trois anciennes lignes trop longues ne sont pas reformattées. Le contrôle global Ruff présente des erreurs et plusieurs fichiers anciens à reformater. Ces contrôles échouaient aussi sur HEAD initial archivé dans un répertoire temporaire (27 erreurs Ruff, 12 fichiers à reformater avant les corrections ciblées). Les résultats globaux ne sont pas présentés comme verts.

Pyright global : **34 erreurs**, contre **38 sur HEAD initial `71369de`**. Comparaison par fichier/message : aucun nouveau diagnostic. Deux anciens tests, `test_navigation_keeps_each_panel_selection_and_restores_it` et `test_space_goes_to_search_while_a_track_is_playing`, échouent identiquement sur HEAD initial à cause d’attentes synchrones sur des modèles maintenant asynchrones. Ils ne sont pas modifiés dans cette livraison. Le lancement élargi des tests library/runtime/artwork/application a obtenu 41 succès avec les exceptions mpv signalées ci-dessus.

La recette ne couvre pas exhaustivement chaque combinaison de panneaux divisés, une arborescence arbitrairement profonde ni l’accès à des supports amovibles physiques. Les tests repository couvrent les invariants d’intégrité ; la simulation Qt couvre les parcours principaux. Les couvertures inutilisées restent dans le dossier applicatif ; elles ne touchent jamais les originaux.

## Livraison

ExecPlan, décisions et spécification mis à jour. Seuls les fichiers de cette livraison sont indexés ; les modifications utilisateur initiales restent hors commit. Commit détaillé puis push vers origin/main, avec fetch et comparaison des SHA. Les hashes sont rapportés dans la conversation pour éviter l’auto-référence du document.
