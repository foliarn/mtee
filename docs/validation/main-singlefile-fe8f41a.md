# Validation de la distribution Windows monofichier — `main` (`fe8f41a`)

## Révision et sortie

Le build a été produit depuis `main` au commit source `fe8f41aab7ed1279eab4dd29630f46a40726c66f`. Après vérification, l'unique fichier conservé dans `dist/` est `MTEE.exe` : 231 568 186 octets (220,84 Mio), SHA-256 `B8D82B2AD64D7DC694E7A206F86A572C5A8D16F2FD73A8DEC059AEF60E4B1B30`.

Le format monofichier intègre Qt/QML, FFmpeg et libmpv, d'où une taille supérieure au lanceur du paquet en dossier. La vérification du contenu PyInstaller confirme les ressources QML/licences et les runtimes intégrés.

## Construction et vérifications observées

Commande : `pwsh -NoProfile -File scripts/build_windows.ps1 -DistDirectory dist/main-singlefile-final-fe8f41a -WorkDirectory build/main-singlefile-final-fe8f41a`. Environnement Windows 11 `10.0.26200`, Python `3.12.14`, PyInstaller `6.22.2`, comme pour le build précédent documenté.

Le build PyInstaller a réussi; les empreintes de contenu embarqué ont été vérifiées par `scripts/verify_singlefile.py`. `scripts/smoke_packaged.ps1` exécuté contre `dist/MTEE.exe` avec un répertoire de données isolé a quitté avec le code `0`. L'exécutable a ensuite été ouvert avec un nouveau profil isolé `main-singlefile-fe8f41a`.

Les anciens artefacts de test et de build présents dans `dist/` et `build/` ont été supprimés. Les profils de test/démo créés durant la recette ont été supprimés; le profil `main-singlefile-fe8f41a` est gardé pour le lancement. Le profil utilisateur par défaut et ses données n'ont pas été supprimés.

## Limites

Le profil historique par défaut échoue encore sur la migration retirée `010_audio_analysis`; son état n'a pas été modifié. Pour démarrer le build de recette sans réutiliser ce profil, fournir un chemin isolé avec `--data-dir <dossier>`. Le scan et l'écoute d'une collection audio réelle, les opérations d'écriture sur copie, la suite automatisée et la validation native complète restent non exécutés.
