# Validation 03 — Explorateur et métadonnées en lecture seule

Exécutée le 24 septembre 2026 sur Windows 11, version 10.0.26200. Python 3.12.14, PySide6 6.9.3 et Mutagen 1.48.1. Le processeur est rapporté par Python comme `AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD`; le modèle CPU, la RAM physique et le disque n'ont pas été relevés (l'interrogation WMI a été refusée). Les mesures de mémoire ci-dessous concernent le working set du processus de validation uniquement.

## Contrôles exécutés

| Commande / parcours | Résultat |
| --- | --- |
| `uv sync --locked` | Réussi ; 22 dépendances résolues, 21 vérifiées. |
| `uv run python -m mtee --demo --data-dir .local/validation/03-demo --smoke-test` | Code 0. |
| `uv run ruff check .` | Réussi, aucun problème. |
| `uv run ruff format --check .` | 96 fichiers déjà formatés. |
| `uv run pyright` | 0 erreur, avertissement ou information. |
| `uv run pytest -rs` | 124 réussis, 2 ignorés, en 17,24 s. |
| `git diff --cached --check` | Réussi sur le diff indexé final. |
| `pwsh -File scripts/build_windows.ps1` | L'exécutable autonome `dist/MTEE/MTEE.exe` a été produit (2 239 236 octets à l'inspection). |
| `pwsh -NoProfile -File scripts/smoke_packaged.ps1 -DataDir .local/validation/03-package-final` | La fenêtre de l'application empaquetée s'est chargée puis fermée avec le code 0. |

Les deux tests ignorés vérifient le non-suivi des liens de répertoire. Windows n'a pas permis de créer les liens symboliques requis dans cet environnement. Les parcours de tests couvrent aussi les chemins accentués, les racines imbriquées et dupliquées, les dossiers vides, l'annulation et la récupération de scan, la persistance des identifiants et de la session, ainsi que les interactions entre sélection, panneaux et vues.

Le corpus de performance a été généré avec `uv run python scripts/create_browser_fixture.py --output .local/fixtures/03 --count 10000`. Il comprend exactement 10 000 WAV PCM synthétiques, des sous-dossiers accentués et un dossier vide. Mesure effectuée avec `uv run python scripts/measure_browser_fixture.py --root .local/fixtures/03 --data-dir .local/validation/03-measure-final` :

| Mesure | Résultat |
| --- | ---: |
| Morceaux indexés | 10 000 |
| Premier lot | 261,9 ms |
| Scan total | 22 172,9 ms |
| Retard de boucle Qt au p95 | 108,66 ms |
| Retard de boucle Qt maximum | 295,45 ms |
| Working set initial / pic | 87,4 / 142,8 MiB |
| Croissance du working set | 55,5 MiB |

Le script échantillonne un `QTimer` de 10 ms pendant l'indexation : le p95 de ce proxy respecte le budget proposé de 250 ms, avec un maximum isolé au-dessus. Cette valeur ne mesure pas le délai d'un clic utilisateur injecté. Le corpus de 10 000 fichiers ne contient pas de vraie musique ni de pochettes ; il valide l'énumération et l'échelle, pas la diversité d'une collection réelle. Le premier lot est arrivé après 261,9 ms.

## Lecture seule et formats

Les tests utilisent des WAV synthétiques et des WAV auxquels sont ajoutés des tags ID3/APIC et une petite image générée. Ils valident les champs correspondants et que la lecture ne modifie pas les octets du fichier. Le mapping des champs normalisés est décrit dans [metadata-mapping.md](../metadata-mapping.md). Aucun corpus réel n'a été utilisé ; les lecteurs Easy Mutagen pour MP3, FLAC, Ogg/Opus et MP4 n'ont donc pas tous été contrôlés sur des fichiers réels. Les erreurs de lecture et images mal formées ou hors limites ont des tests de repli. Les limites d'image sont 20 MiB de données et 100 millions de pixels ; le cache LRU de vignettes est borné à 128 MiB.

## Validation Windows restant à faire

Le binaire a réussi le smoke test empaqueté et son processus a été observé avec une fenêtre « MTEE » répondante. La revue visuelle/interactives de la table, des pochettes, des deux panneaux, de la fenêtre étroite et de la restauration après fermeture n'a pas été effectuée. L'inventaire `cua.getState()` n'a exposé aucune application native dans cette session, et `cua.listWindows` n'était pas disponible ; je n'ai donc pas pu obtenir de capture ni piloter cette fenêtre avec l'outil de Computer Use. Le smoke test confirme le démarrage et le chargement de fenêtre, mais ne remplace pas ce parcours.

Le lancement a eu lieu sur cette machine de développement, pas sur une installation Windows propre sans Python ni réseau. Aucun média d'utilisateur n'a été utilisé ; aucun essai de déconnexion physique de volume n'a été effectué. Ces vérifications et la comparaison visuelle aux maquettes validées restent ouvertes.
