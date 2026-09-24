# Validation du plan 04 — Lecteur commun

Date de la recette : 2026-09-24. Environnement : Windows x86-64, Python 3.12.14, Qt via l'environnement verrouillé du dépôt. La validation a été faite sur les fichiers temporaires du dépôt et sur un runtime natif acquis par empreinte.

## Résultats automatisés

| Contrôle | Résultat observé |
| --- | --- |
| Ruff (`ruff check .`) | Réussi : `All checks passed!` |
| Format Ruff (`ruff format --check .`) | Réussi : 108 fichiers déjà formatés |
| Pyright | Réussi : 0 erreur, 0 avertissement, 0 information |
| Pytest complet | Réussi : 137 réussis, 2 ignorés en 18,36 s |
| Tests ignorés | Deux tests de liens symboliques ; cette fonctionnalité n'est pas disponible dans l'environnement Windows de recette |
| Décodage natif libmpv | WAV PCM synthétique : décodage, durée, codec, seek et pause/reprise réussis sur sortie `null`, y compris avec la DLL extraite du paquet |
| QML partagé | Réussi : tests UI de bascule/conservation d'état et saisie d'un espace dans Search pendant la lecture |

Un premier test de fixture avait utilisé un guillemet dans son nom, caractère interdit par Windows ; la fixture a été corrigée pour conserver les espaces et l'accent sans caractère illégal. La suite finale complète passe avec le handler `faulthandler` désactivé : `uv run --no-sync --cache-dir .local/uv-cache python -X faulthandler=0 -m pytest -p no:faulthandler -p no:cacheprovider -rs --basetemp .local/pytest-basetemp`. Avec le handler Pytest actif, le thread natif produit de grands rapports pour l'exception SEH `0xe24c4a02` de LuaJIT, bien que la suite parvienne aussi à terminer. Le test sélectionné par `native_audio` passe proprement avec le handler désactivé. Le signal et sa portée sont détaillés dans [docs/native-dependencies.md](../native-dependencies.md) et restent à contrôler manuellement.

## Formats et comportement manuel

La matrice à jour se trouve dans [tests/fixtures/audio/manifest.json](../../tests/fixtures/audio/manifest.json). Seul WAV PCM généré est décodé avec le vrai runtime ; le son audible sur WASAPI, MP3, FLAC, AAC ADTS, AIFF, Ogg/Vorbis, Opus, M4A/AAC et M4A/ALAC restent non validés, faute de fixtures autorisées et de recette audio réelle.

Le test UI automatisé confirme que Search reçoit une espace pendant la lecture sans mettre le lecteur en pause. Le parcours interactif d'une fenêtre MTEE, des dix bascules Fullscreen, des commandes de transport audibles, du seek aux trois positions, de la perte de sortie audio et du paquet hors ligne sur Windows propre reste à effectuer. Les surfaces de contrôle ordinateur disponibles pendant cette recette ne donnaient accès à aucune application native ; aucun geste clavier/souris ni écoute réelle n'est donc revendiqué. Les tests UI automatisés ne sont pas une écoute.

## Distribution

Runtime et hashes : [resources/native/mpv/manifest.json](../../resources/native/mpv/manifest.json). Acquisition : `scripts/fetch_mpv.ps1`. Contrôle Windows : `scripts/build_windows.ps1`, qui compte une unique DLL empaquetée et vérifie son empreinte. Un build diagnostique avec console et un build de production sans console ont réussi sous Windows 11 x86-64 avec PyInstaller 6.22.2. Le rebuild final après changements a réussi ; `MTEE.exe --data-dir .local/validation/04-package-final --smoke-test` exécuté par `Start-Process -Wait` a retourné 0 et créé le SQLite isolé. Une DLL unique est présente à `dist/MTEE/_internal/mtee/native/mpv/libmpv-2.dll`, SHA-256 `85071ee7c8bfc9f3690a0eb140f15bbb697cdf81bc96e9c905dc8a54cfff8c10d` ; la notice tierce est incluse. Le test natif a ensuite chargé explicitement cette DLL du paquet et décodé/seeké le WAV généré (sortie `null`). Cela valide le DLL sur ce poste, pas le fonctionnement hors ligne sur un Windows propre ni la sortie WASAPI.

Le test de build vérifie l'intégrité et le chargement sur ce poste seulement. `vulkan-1.dll` est une dépendance importée par libmpv, fournie ici par l'environnement graphique Windows ; elle n'est pas intégrée dans le paquet. La disponibilité sur une installation Windows minimale reste donc une limite à lever ou à accepter explicitement.

## Limites d'acceptation

La livraison du code, les faux backends, le test de décodage WAV et l'UI partagée sont des preuves distinctes de la matrice complète et du parcours sur machine propre. Les formats et contrôles marqués non validés ne sont pas implicitement approuvés. L'audit des dépendances/licences du build LGPL tiers est également ouvert ; voir [docs/native-dependencies.md](../native-dependencies.md).
