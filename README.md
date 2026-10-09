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

Pour itérer sur l'application réelle sans repackager, lancer `uv run python -m mtee --data-dir .local/dev` depuis la racine. Redémarrer ce processus après une modification Python ou QML. `uv sync --locked` est nécessaire à l'installation initiale et lorsque les dépendances changent ; il n'est pas à relancer à chaque édition.

## Contrôles

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

## Distribution Windows

    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1

La distribution monofichier est produite dans `dist/MTEE.exe`. Les commandes ci-dessus sont réservées aux demandes explicites de packaging ou de distribution Windows ; elles ne font pas partie de la clôture habituelle d'une tâche. Un lancement depuis les sources ne valide pas le paquet sur une machine Windows propre, sans Python ni Qt installés.
