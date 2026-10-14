# MTEE — Music Tagging and Editing Explorer

Application desktop personnelle pour explorer, écouter, organiser, modifier et préparer une collection de fichiers audio locale. Python 3.12, PySide6 et QML, sans Electron ni WebView, Windows en premier. L'interface est en anglais, la documentation du projet en français.

La fenêtre donne accès à la navigation locale, à la lecture, aux playlists, aux artistes et aux outils de préparation musicale, dont Genre Manager. Les données de démonstration restent séparées d'une collection réelle.

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

## Genre Manager

Dans **Plugins > Genre Manager**, ouvrir **Classify**, puis cliquer sur le nom de la source sous `FOLDER` ou `PLAYLIST`. La fenêtre interne propose les dossiers et playlists avec leur progression. Choisir un dossier n'attribue aucun genre ; **Tag folder songs…** demande un genre et une confirmation pour ses morceaux. La sélection et le pinceau permettent aussi de classer titre par titre. Le premier genre est principal, les suivants sont secondaires ; **Mark N as reviewed** valide uniquement la sélection.

**Genres & tags** donne accès au catalogue défilant, à **New root genre**, au `+` des racines et aux tags libres. **Organize files** montre les pistes vérifiées du lot courant et demande une destination explicite par racine et genre principal. Vérifier les chemins de l'aperçu avant **Move N files** ; les autres pistes restent en place. **Undo organization** prépare un nouvel aperçu de mouvements inverses. **Uncertain** présente les contributions aux artistes qui ne peuvent pas être attribuées avec certitude à partir des crédits confirmés. Les genres calculés restent distincts des tags manuels des artistes.

L'installation neuve utilise les migrations 022 et 023 sans restaurer l'ancienne 021. Une base qui a enregistré 021 est refusée par le contrôle d'historique ; repartir d'une base neuve avant de repeupler la collection, en conservant séparément toute ancienne base nécessaire. Le plugin ne réécrit pas les tags audio.

## Contrôles

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

## Distribution Windows

    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1

La distribution monofichier est produite dans `dist/MTEE.exe`. Les commandes ci-dessus sont réservées aux demandes explicites de packaging ou de distribution Windows ; elles ne font pas partie de la clôture habituelle d'une tâche. Un lancement depuis les sources ne valide pas le paquet sur une machine Windows propre, sans Python ni Qt installés.

## Licence

MTEE est un logiciel libre distribué sous licence GNU GPL version 3 ou ultérieure (`GPL-3.0-or-later`) : voir [LICENSE](LICENSE). Les composants tiers et leurs licences sont listés dans [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
