# Validation de stabilisation — branche `fix`

Date : 2026-09-25
Commit source du build : `6098748`
Branche : `fix`

## Environnement

- Windows 11, build `10.0.26200`
- Python `3.12.14`
- uv `0.12.17`
- PyInstaller `6.22.2`
- FFmpeg `n9.0.2-3-ga5923073bf-20260924`

## Vérifications effectuées

| Vérification | Résultat |
| --- | --- |
| `uv run --no-sync python -m compileall -q src` | Réussi |
| Imports critiques (`mtee.app`, modèle/service/repository Trash) | Réussis |
| `qmllint` sur les fichiers QML avec `src/mtee/qml` en chemin d'import | Code de sortie 0; avertissements QML présents (bindings non qualifiés et vérifications statiques de propriétés) |
| `uv run --no-sync ruff check src --select F821,B012` | Réussi |
| `pwsh -NoProfile -File scripts/build_windows.ps1 -DistDirectory dist/fix-6098748 -WorkDirectory build/fix-6098748` | Réussi |

Le premier build avec les répertoires par défaut a compilé l'exécutable, puis PyInstaller a échoué pendant le nettoyage de `dist/MTEE`, car Windows refusait l'accès à `libmpv-2.dll`. Le script accepte maintenant des répertoires isolés. Le second build a utilisé `dist/fix-6098748` et `build/fix-6098748`; la distribution existante n'a pas été remplacée.

## Paquet produit

- Exécutable : `dist/fix-6098748/MTEE/MTEE.exe`
- Taille : 2 966 134 octets (2.83 MiB)
- SHA-256 : `c2e45993462eb66a697c8adb78b47e7b3c7636811a8980c300263d41d59488d6`
- Fichiers du paquet : 1 980
- FFmpeg et ffprobe, versions et hashes des DLL, `libmpv-2.dll` et licence FFmpeg vérifiés par `build_windows.ps1` contre leurs manifestes verrouillés.
- Le script a lancé `ffmpeg.exe -version` et `ffprobe.exe -version` du paquet et confirmé la version attendue.

## Non exécuté

Les tests automatisés, le smoke-test paqueté, le parcours UI, les conversions FFmpeg et le recyclage/restauration via la Corbeille Windows n'ont pas été exécutés. La syntaxe du code et le build ne valident pas ces comportements natifs.
