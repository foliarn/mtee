# Validation de la distribution Windows — `main` (`4655a5a`)

## Révision intégrée

Le 25 septembre 2026, `fix` a été intégré à `main` par fast-forward de `478af5c` à `4655a5a`, puis poussé sur `origin/main`. L'état local contenait des modifications dans `.gitignore`, `AGENTS.md` et `.codex/`; elles n'ont pas été ajoutées au merge ni au commit de validation.

## Construction

La distribution GUI a été construite depuis `main` à `4655a5a` avec `pwsh -NoProfile -File scripts/build_windows.ps1 -DistDirectory dist/main-prod-4655a5a -WorkDirectory build/main-prod-4655a5a`. L'environnement observé était Windows 11 `10.0.26200`, Python `3.12.14` et PyInstaller `6.22.2`. Le script a validé les runtimes FFmpeg/libmpv et la licence FFmpeg avant la fin réussie de PyInstaller.

Le format est une distribution en dossier : `MTEE.exe` fait `2 966 134` octets (2,83 Mio), et ses DLL, ressources QML et runtimes se trouvent à côté. SHA-256 de `MTEE.exe` : `BD42F885FFB25EE2816D7116E327769ED0433E3BA1A46EA5AEFF11120133F2E8`. Le dossier contient 1 982 fichiers pour `413 961 095` octets. L'archive fournie est `dist/MTEE-main-4655a5a-test.zip` (`171 613 213` octets).

## Démarrage et limites

Le smoke-test du paquet GUI avec `--data-dir <profil-isolé> --smoke-test` a quitté avec le code `0`. L'application a aussi été ouverte en mode normal avec ce profil isolé. Le lanceur `Lancer MTEE - profil test.bat` utilise `%LOCALAPPDATA%\MTEE\profiles\main-test-4655a5a`; aucune collection audio n'a été lue pendant ces vérifications.

Le test de démarrage avec le profil local historique a quitté avec le code `3` et signalé la migration retirée `010_audio_analysis`. Le garde-fou a refusé de rétrograder ou d'effacer ce schéma; la base n'a pas été modifiée. La suite automatisée, le scan/écoute d'une collection audio réelle et les opérations d'écriture sur copies n'ont pas été exécutés ici.
