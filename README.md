# MTEE — Music Tagging and Editing Explorer

Application desktop personnelle pour explorer, écouter, organiser, modifier et préparer une collection de fichiers audio locale. Python 3.12, PySide6 et QML, sans Electron ni WebView, Windows en premier. L'interface est en anglais, la documentation du projet en français.

L'état actuel est le **socle technique** : la fenêtre affiche ses zones nommées avec des données fictives. La navigation dans les dossiers, la lecture, l'édition des métadonnées, la conversion et l'analyse arrivent aux étapes suivantes.

## Documents

- `PLAN.md` — vision produit et exigences validées.
- `PLANS.md` — méthode des plans d'exécution et règles de livraison.
- `Plans d'exécution/README.md` — index des étapes, de l'initialisation au portage.
- `docs/architecture/overview.md` — couches du socle et sens des appels.
- `docs/validation/` — comptes rendus de recette par étape.

## Développer

Le projet utilise [uv](https://docs.astral.sh/uv/) pour l'environnement et le verrouillage des dépendances.

    uv sync --locked
    uv run python -m mtee --demo

Options reconnues : `--data-dir PATH` isole les données d'une recette, `--demo` affiche des données fictives dans un stockage séparé, `--smoke-test` charge la fenêtre puis quitte avec un code de succès ou d'échec.

## Contrôles

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

## Distribution Windows

    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1

La distribution est produite en répertoire dans `dist/MTEE/`. Un lancement rapide ne remplace pas l'essai sur une machine Windows propre, sans Python ni Qt installés.
