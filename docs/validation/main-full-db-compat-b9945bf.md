# Validation du lancement avec la base utilisateur complète — `main` (`b9945bf`)

## Cause et compatibilité

La base locale existante avait `PRAGMA user_version = 10` et les migrations 1 à 10, avec la migration `audio_analysis`. Le build précédent avait retiré le script 010 avec la fonctionnalité d'analyse et refusait cet historique. L'application GUI étant construite sans console, elle quittait sans rendre cette erreur visible.

La migration 010 ajoutait seulement des tables d'analyse. Le correctif garde la ligne `audio_analysis` et toutes ses tables/données, puis applique les migrations 011 à 014. Les historiques inconnus restent refusés. La migration existante crée une sauvegarde SQLite cohérente avant d'appliquer la première migration suivante.

## Vérifications observées

Le test d'intégration synthétique vérifie la conservation des données applicatives et d'analyse, la sauvegarde v10, l'application de 011–014 et la réouverture sans nouvelle migration. Les commandes suivantes passent :

- `uv run --offline --no-sync pytest tests/integration/test_database_migrations.py -q` — 10 tests réussis.
- `uv run --offline --no-sync ruff check src/mtee/persistence/database.py tests/integration/test_database_migrations.py`.
- `uv run --offline --no-sync ruff format --check src/mtee/persistence/database.py tests/integration/test_database_migrations.py`.

La construction Windows a été exécutée avec `pwsh -NoProfile -File scripts/build_windows.ps1 -DistDirectory dist/main-full-db-b9945bf -WorkDirectory build/main-full-db-b9945bf`, depuis le commit source `b9945bf`. Windows 11 `10.0.26200`, Python `3.12.14`, PyInstaller `6.22.2`. Le script a validé les ressources QML, FFmpeg et libmpv intégrées.

Une copie SQLite cohérente de la base v10 a été utilisée avec `scripts/smoke_packaged.ps1`; la fenêtre QML s'est chargée et le code de sortie était `0`. Le test a atteint le schéma 14, conservé la ligne de migration 10 et les lignes d'analyse, et créé une sauvegarde v10. Aucun écart de nombre de lignes n'a été observé dans les tables présentes avant la migration. La copie de test a été supprimée ensuite.

L'EXE final a ensuite été lancé sans argument, donc avec le profil par défaut. Une fenêtre `MTEE` s'est ouverte. La base locale est maintenant au schéma 14. Sa sauvegarde avant migration s'appelle `mtee.sqlite3.v10.20260926T110154Z.backup`.

## Livrable et limites

`dist/MTEE.exe` fait 231 570 914 octets (220,84 Mio). SHA-256 : `AE963B28A554C0E0E7D55AC3578626452193790D19AD195C1B7E8B0B83EF420F`. C'est le seul fichier présent dans `dist/`.

Le démarrage de l'interface est vérifié avec le profil complet. La lecture/écoute effective d'un fichier audio et les opérations d'écriture dans des fichiers de la bibliothèque ne sont pas validées ici.
