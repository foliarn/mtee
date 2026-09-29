# Jalon 27 — validation de compilation et distribution

Date : 29 septembre 2026.

## Livré

- Préférences de colonnes globales et persistées : ordre, visibilité, largeur et affichage des pochettes.
- Profil par défaut `Title | Artist | Date created | BPM | Key`, avec pochettes visibles.
- Validation locale du profil malformé ; les anciennes colonnes par onglet restent dans la session comme données de compatibilité.
- Menu de colonnes, remise à zéro, déplacement par glisser-déposer et commandes `Move left` / `Move right`.
- Tri de référence par date de création décroissante, puis tri manuel à trois états ; les valeurs absentes restent à la fin.
- Numéro ordinal retiré de la rangée ; les commandes de lecture et d’information restent indépendantes des colonnes. Le style et le placement de la rangée d’en-têtes sont conservés.

## Résultats observés

- `uv run python -m compileall -q src/mtee` : réussi.
- `uv run ruff check src/mtee/models/workspace_model.py src/mtee/persistence/workspace_repository.py` : réussi.
- `uv run pyside6-qmllint -I src/mtee/qml src/mtee/qml/components/TrackListView.qml src/mtee/qml/components/TrackRow.qml` : code de sortie 0 ; avertissements non bloquants d’accès QML non qualifié, dont des avertissements préexistants dans les composants.
- `git diff --check` : réussi.
- `scripts/build_windows.ps1` : terminé ; vérificateur du paquet autonome a confirmé le QML intégré, l’avis FFmpeg et les empreintes du runtime libmpv/FFmpeg.
- EXE construit : `dist/MTEE.exe`, 220,85 MiB.
- SHA-256 : `420058FE1AD5FF841105ADE1567B2F0328D0143DBCD6F13AFC65D9B229F87B06`.

## Limites de la validation

Conformément à la demande, aucun test automatisé ni lancement de recette manuelle n’a été effectué. Les gestes de menu, redimensionnement, glisser-déposer, tri et persistance restent à essayer par l’utilisateur dans l’EXE.

## Git

Commit : `fbc7d02` (`feat(explorer): customize columns globally and reset sorting to creation date`). Push confirmé sur `origin/main` après fetch ; `HEAD` et `origin/main` correspondent à `fbc7d02d57b687133aed0be754c68ef753db81f6`.

Le push contenait aussi le commit préexistant `bb1d96b` sur les plans SoundCloud, laissé intact. Les modifications locales de `.gitignore`, `AGENTS.md` et le dossier `.codex/` sont restées hors du commit fonctionnel.
