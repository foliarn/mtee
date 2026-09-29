# Dépendances du socle et versions verrouillées

Versions résolues le 10 septembre 2026 par `uv lock`, puis installées par `uv sync --locked` sur Windows 11 Professionnel 10.0.26200, architecture AMD64. Le verrou `uv.lock` fait foi ; ce document explique les choix et donne les documentations officielles consultées pour les utiliser.

## Production

| Composant | Version verrouillée | Rôle | Documentation officielle |
|---|---|---|---|
| Python | 3.12.14 (CPython, installé par `uv python install 3.12`) | Interpréteur imposé par `PLAN.md` | <https://docs.python.org/3.12/> |
| PySide6-Essentials | 6.9.3 | Qt Quick, QML, Core et Gui | <https://doc.qt.io/qtforpython-6/> |
| shiboken6 | 6.9.3 | Liaison C++/Python de PySide6, tirée automatiquement | <https://doc.qt.io/qtforpython-6/shiboken6/> |
| Mutagen | 1.48.1 | Lecture des métadonnées audio, avancée depuis le plan 05 pour la livraison A | <https://mutagen.readthedocs.io/> |
| NumPy | 2.5.3 | Calcul vectorisé du tempo, de la tonalité et de la waveform (plan 33) | <https://numpy.org/doc/> |
| SQLite | 3.53.1 via `sqlite3` de la bibliothèque standard | Persistance locale | <https://docs.python.org/3.12/library/sqlite3.html> |

Le paquet complet `PySide6` a d'abord été verrouillé, puis remplacé par `PySide6-Essentials` : les add-ons embarquaient Qt WebEngine, Quick3D et leurs dépendances, soit 377 Mo de distribution pour un socle qui ne les utilise pas. Avec les essentiels, la même distribution occupe 138 Mo et le contrôle après empaquetage reste vert. Qt Multimedia n'est pas utilisé ; la lecture native viendra de libmpv au plan 04.

## Développement et empaquetage

| Composant | Version verrouillée | Rôle | Documentation officielle |
|---|---|---|---|
| uv | 0.12.12 | Environnement, résolution et verrou | <https://docs.astral.sh/uv/> |
| pytest | 9.1.1 | Tests | <https://docs.pytest.org/> |
| pytest-qt | 4.5.0 | Fixtures Qt (`qapp`, `qtbot`) | <https://pytest-qt.readthedocs.io/> |
| Ruff | 0.16.6 | Lint et format | <https://docs.astral.sh/ruff/> |
| Pyright | 1.1.414 | Vérification de types | <https://microsoft.github.io/pyright/> |
| PyInstaller | 6.22.2 | Distribution Windows en répertoire | <https://pyinstaller.org/en/stable/> |

## Règles retenues

Les bornes de `pyproject.toml` restent souples (`>=6.8,<6.10` pour Qt) et c'est `uv.lock` qui fige les versions exactes. Une mise à jour de dépendance passe par une modification explicite du fichier de projet, un nouveau verrou et une nouvelle exécution complète des contrôles, y compris la construction de la distribution.

Ruff impose les noms Python ordinaires, sauf dans `src/mtee/models/` et pour les signaux de `JobService` : Qt fixe le nom des méthodes redéfinies, des signaux et des propriétés lues par QML, et les renommer casserait la liaison. Ces exceptions sont déclarées dans `pyproject.toml` avec leur motif.

Les tests forcent la plateforme Qt `offscreen`. Ce mode ne fournit aucune police : une capture prise dans ce mode affiche des caractères manquants, ce qui n'indique pas un défaut de l'application. La vérification visuelle passe par la plateforme Windows réelle.

Aucune bibliothèque native supplémentaire n'était installée à l'étape du socle. FFmpeg est venu avec le plan 07 ; NumPy a été ajouté par le [plan 33](../../Plans%20d'ex%C3%A9cution/33-analyse-audio.md) pour l'analyse, sans SciPy, librosa, Numba ni llvmlite. L'état des vérifications natives est tenu dans `native-dependencies.md`.
