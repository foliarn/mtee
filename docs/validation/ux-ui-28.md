# Jalon 28 — validation de compilation et distribution

Date : 29 septembre 2026.

## Livré

- Waveform complète conservée en monochrome ; le choix utilisateur écarte la variante trois bandes et le RGB.
- Agrégation d’affichage adaptée à la largeur visible, conservant le minimum et le maximum de chaque groupe de points existants.
- Dessin des données séparé du Canvas de progression ; assombrissement transparent de la portion lue et curseur à contraste constant.
- Étiquette de temps `m:ss` ou `h:mm:ss`, attachée au curseur et décalée près des bords ; clic de seek maintenu.
- La waveform utilise `playbackDuration`, durée positive rapportée par le moteur. La propriété `duration` historique conserve son repli sur les métadonnées pour les autres vues.
- Aucun nouveau calcul audio, cache, RMS, bande de fréquence ou mode de couleur.

## Résultats observés

- `uv run python -m compileall -q src/mtee` : réussi.
- `uv run ruff check src/mtee/models/player_model.py` : réussi.
- `uv run pyside6-qmllint -I src/mtee/qml src/mtee/qml/components/WaveformView.qml src/mtee/qml/views/FullscreenPlayer.qml` : code de sortie 0, aucune erreur. Les avertissements d’accès non qualifié signalés dans `FullscreenPlayer.qml` sont dans le delegate de tags existant, hors des lignes modifiées par ce jalon.
- `git diff --check` : réussi.
- `scripts/build_windows.ps1` : terminé ; le vérificateur confirme le QML intégré, l’avis FFmpeg, libmpv et les empreintes du runtime FFmpeg.
- EXE construit : `dist/MTEE.exe`, 220,85 MiB (231 582 509 octets).
- SHA-256 : `AF7B3EFB6F3E55667B61D1A4CB7D70D79F4536E88D158C78618E4442E801C572`.

## Correction visuelle après retour utilisateur

La capture a montré que l’assombrissement rectangulaire colorait le fond sans suivre la forme d’onde. Le remplissage est supprimé. Une seconde couche de traits monochromes grisés est découpée à la position de lecture ; le fond reste transparent. Les deux Canvas de données ne sont repeints qu’aux changements de données ou de largeur, pas à chaque tick du lecteur.

- `uv run pyside6-qmllint -I src/mtee/qml src/mtee/qml/components/WaveformView.qml` : code de sortie 0.
- `git diff --check` : réussi.
- `scripts/build_windows.ps1` : terminé ; vérification du contenu embarqué réussie.
- EXE principal après correction : `dist/MTEE.exe`, 220,85 MiB (231 582 846 octets).
- SHA-256 : `EE2B2EB710561C8810FBC0C0421B3835A79BECE6E60C4ED58B699527F6F7D7F7`.

## Limites de la validation

Conformément à la demande, aucun test automatisé ni contrôle visuel interactif de cette correction n’a été effectué ; l’utilisateur essaiera le rendu dans l’EXE. Les interactions de lecture, pause, seek, changement de morceau, dimensions de fenêtre et affichage du temps restent à vérifier. Aucun corpus audio ni mesure de performance n’a été utilisé ; aucun gain de performance mesuré n’est revendiqué.

## Git

Commit fonctionnel : `e907053` (`feat(waveform): improve monochrome density and playback cues`). Correction du rendu : `44095cd` (`fix(waveform): shade played bars without background overlay`), poussée sur `origin/main` après fetch.

Le push contient aussi le commit local antérieur `b39dbe3` (`docs(capture): apply user decisions to SoundCloud extension plans`), conservé intact comme parent. Les modifications locales de `.gitignore`, `AGENTS.md` et `.codex/` sont restées hors des commits du jalon.
