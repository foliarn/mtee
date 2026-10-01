# Rapport de validation — plan 101

Exécuté le 1er octobre 2026 sur Windows 11, Python 3.12.14, PySide6 6.9.3, depuis les sources (`uv run`). Aucun build Windows ni paquet n'a été produit ni vérifié. Conformément à la demande de l'utilisateur, **aucun test UI** n'a été créé, modifié ni lancé, et l'agent n'a inspecté aucun rendu visuel.

## Livraisons

| Jalon | Commit |
|---|---|
| 101.0 base de travail | `ee7124c`, plan `7f40606` |
| 101.1 maquettes (validées par l'utilisateur, variante `history-times` incluse) | `459af90` |
| 101.2 désélection | `aa8a4c3` |
| 101.3 Explorer | `2950c08` |
| 101.4 rafraîchissement des dossiers | `2ee9a99` |
| 101.5 historique d'écoute persistant | `59e4827` |
| 101.6 tâches et page Tasks | `f732720` |
| 101.7 couleur d'accent | `814138f` |
| 101.8 en-tête de playlist | `098fe8c` |
| 101.9 panneau Queue et History | `69baca8` |
| 101.10 menu « Add to playlist » compact | `19d2ce3` |

## Contrôles effectués

- Tests unitaires ciblés à chaque jalon (scanner, rafraîchissement, watcher, workspace, historique, file, service, session v1/v2, jobs, lot d'analyse, palette OKLab, format de méta de playlist, onglet History du panneau droit).
- Suite `uv run pytest tests/unit` (sans `test_conversion_queue.py` ni `test_icon_provider.py`, échecs préexistants) : un seul échec, `test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it`, qui échoue à l'identique sur un worktree du commit de base `2950c08`.
- Ruff et Pyright sur les fichiers Python modifiés ; les avertissements E501 restants sont antérieurs à ce plan.
- `uv run python -m mtee --data-dir .local/validation/101 --smoke-test` et `--demo --smoke-test` : code 0, sans avertissement QML après chaque jalon QML ; `--demo --scenario playing-queue --smoke-test` après 101.9.
- Chargements hors écran non interactifs, sans avertissement QML : `TasksView` et `TasksPane` avec de vrais jobs, `PlaylistHeader` (hauteur implicite 320), `QueuePanel` et `HistoryPanel`, `AddToPlaylistMenu` ouvert.
- `tests/integration/test_playback_repository.py` (session v2) passe. `tests/integration/test_conversion_ffmpeg.py` échoue sans FFmpeg local et les tests d'analyse de bout en bout sont ignorés (`vendor/` absent) ; ce n'est pas lié au plan. Un plantage natif (code `0xe24c4a02`) apparaît pendant l'exécution des tests d'intégration, sans lien établi avec ce plan.

## Tests UI touchés (non modifiés)

- `tests/ui/test_playback_queue_ui.py` vise `playbackQueueView`, `queueEntry_<id>` et `removeQueueAction`, supprimés avec `PlaybackQueueView.qml` ; à adapter vers `queuePanel`, `queueRow_<entryId>`, `queueRemove`.
- Les `objectName` du plein écran (`queueRow_<id>`, `queueCurrentRow`, `queueSection_<section>`, `queueEmpty`, `queueRemove`, `queueGoTo`, `queueEditInfo`, `queueCoverButton`, `queueRowMore`, `queueCoverIcon`, `queueRowTitle`, `queueNowPlaying`, `fullscreenQueueList`) sont conservés ; `queueWheelGuard` n'est actif que dans le plein écran.
- `tests/ui/test_playlist_creation_98.py` : `playlistCoverHover` et `playlistTitleText` conservés ; le texte « PLAYLIST » en capitales devient « Playlist » (`playlistKind`).
- Les tests UI du menu « Add to playlist » ne devraient pas être touchés (`playlistMenuSearch`, `playlistMenuEntry_<id>` conservés), mais le bouton `Close` n'existe plus.

## Limites et décisions

- L'onglet `tasks:` est rejoué par Back/Forward mais non restauré au démarrage, comme Settings et Convert.
- La prime de chroma de l'accent (0,35) et le seuil de regroupement (0,09) sont des réglages proposés.
- Le rafraîchissement ignore volontairement un dossier dont la racine est en cours de scan complet ; `QFileSystemWatcher` peut manquer des événements sur des lecteurs réseau ou amovibles (couverts par l'ouverture et le retour au premier plan).

## Recette utilisateur — à vérifier par l'utilisateur

| Cas | Action | Résultat attendu | Statut |
|---|---|---|---|
| U1 | Sélectionner une ligne, cliquer sous la dernière ligne puis dans la sidebar vide | Plus de fond ni de cadre vert ; la touche Bas sélectionne la première ligne | à vérifier |
| U2 | Clic simple sur un dossier replié | La page s'ouvre, le dossier reste replié | à vérifier |
| U3 | Double-clic sur ce dossier, puis à nouveau | Il se déplie puis se replie ; la page reste ouverte | à vérifier |
| U4 | Copier un gros fichier audio dans un dossier ouvert | La ligne apparaît après la fin de la copie | à vérifier |
| U5 | Supprimer puis renommer un fichier d'un dossier ouvert | La ligne disparaît puis réapparaît renommée | à vérifier |
| U6 | Ajouter un fichier dans un dossier fermé puis l'ouvrir | La ligne est présente dès l'ouverture | à vérifier |
| U7 | Analyser 100+ morceaux | Compteur X/N, fichier en cours, temps, estimation ; Cancel arrête | à vérifier |
| U8 | Page Tasks, « Clear finished », échecs dépliés | Terminées retirées ; échecs lisibles | à vérifier |
| U9 | Pochettes blanche, noire, grise, colorée avec petit détail vif | Carte à la couleur dominante ; texte sombre sur carte claire | à vérifier |
| U10 | Playlist avec et sans description | Disposition Spotify, méta `• 8 tracks, 34 min 26 sec`, Play/Shuffle inchangés | à vérifier |
| U11 | Panneau droit Queue puis History | Mêmes lignes que le plein écran, heure relative au repos ; clic pochette lit ; menus corrects | à vérifier |
| U12 | Fermer et rouvrir MTEE après plusieurs écoutes | L'historique est conservé | à vérifier |
| U13 | Bouton + d'une piste | Menu compact conforme à la maquette, bascule immédiate, Échap ferme | à vérifier |
