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
- SHA-256 initial : `420058FE1AD5FF841105ADE1567B2F0328D0143DBCD6F13AFC65D9B229F87B06`.

## Correctif de démarrage après livraison

Le premier lancement de l’EXE a échoué parce que `TrackRow.qml` importait `QtQuick.Accessibility`, module absent du runtime PySide6 Essentials livré. En Qt 6.9, le type attaché `Accessible` est importé depuis `QtQuick` ; les propriétés `Accessible.name` sont donc conservées et seul l’import erroné a été retiré ([documentation Qt 6.9](https://doc.qt.io/qt-6.9/qml-qtquick-accessible.html)).

`app.py` capture maintenant les avertissements du moteur pendant le chargement initial et affiche les détails QML si aucun objet racine ne se crée.

- Build diagnostique console, avec dossier de données isolé : `--smoke-test` terminé avec code 0.
- EXE principal, avec un autre dossier de données isolé : démarrage `--smoke-test` terminé avec code 0.
- `uv run python -m compileall -q src/mtee`, `uv run ruff check src/mtee/app.py` et lint QML de `TrackRow.qml` : réussis ; lint sans erreur bloquante.
- `scripts/build_windows.ps1` : terminé ; vérificateur intégré QML, notice FFmpeg, libmpv et empreintes FFmpeg réussi.
- EXE principal après correction : 220,85 MiB (231 580 567 octets), SHA-256 `BBAFD8EA24C089BCEB31F3032CBE663A6721BF7FF783E5F02DC1533506817249`.

## Limites de la validation

Conformément à la demande, aucun test automatisé ni lancement de recette manuelle n’a été effectué. Uniquement le démarrage isolé de l’EXE a été vérifié pour diagnostiquer puis confirmer le correctif. Les gestes de menu, redimensionnement, glisser-déposer, tri et persistance restent à essayer par l’utilisateur dans l’EXE.

## Git

Commit : `fbc7d02` (`feat(explorer): customize columns globally and reset sorting to creation date`). Push confirmé sur `origin/main` après fetch ; `HEAD` et `origin/main` correspondent à `fbc7d02d57b687133aed0be754c68ef753db81f6`.

Le push contenait aussi le commit préexistant `bb1d96b` sur les plans SoundCloud, laissé intact. Correctif de démarrage : `40dbe37` (`fix(packaging): use QtQuick accessibility type`), poussé sur `origin/main` après fetch. Les modifications locales de `.gitignore`, `AGENTS.md` et le dossier `.codex/` sont restées hors des commits fonctionnels.

## Correctif visuel après livraison — 2026-09-29

À la demande de l’utilisateur, l’espace laissé par l’ancienne colonne ordinale # est supprimé au début du tableau. La gouttière et son espacement ont été retirés des calculs de largeur ainsi que des rangées d’en-tête et de données; le bouton Lecture rejoint les actions à droite pour rester accessible. L’en-tête de recherche et ses boutons ne sont pas modifiés.

- `uv run pyside6-qmllint -I src/mtee/qml src/mtee/qml/components/TrackListView.qml src/mtee/qml/components/TrackRow.qml` : code de sortie 0 ; avertissements d’accès non qualifié existants, aucune erreur bloquante.
- `git diff --check` : réussi.
- Tests interactifs non exécutés et EXE final non reconstruit.
