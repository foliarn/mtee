# Validation 06 — Renommage, déplacement et corbeille

## Résultat

La tranche vérifiée permet de prévisualiser puis de renommer ou déplacer des
fichiers audio à l'intérieur d'une bibliothèque enregistrée, sur le même
volume. Le déplacement natif refuse une destination existante ; l'UUID reste
stable, les références SQLite suivent le nouveau chemin et Undo vérifie la
révision, l'empreinte et l'absence de collision avant le retour.

La livraison ne valide pas tout le plan 06. Le poste n'expose qu'un seul volume
pour les essais ; le type du volume C: n'a pas pu être lu dans cet environnement
restreint. Il n'y a donc pas de preuve d'un déplacement intervolume. Aucun
recyclage/restauration natif ni test interactif de la corbeille n'a été réalisé.
Move to trash reste indisponible dans l'interface ; aucune suppression
définitive n'est appelée comme solution de repli.

## Environnement observé

- Windows 11, version de build 26200, Python 3.12.14, PySide6 6.9.3,
  Mutagen 1.48.1, PyInstaller 6.22.2.
- Volume de recette accessible : C:. Le système de fichiers et les propriétés
  de montage n'ont pas pu être lus ; aucun second volume d'essai n'était
  accessible.
- Fichiers audio générés dans des répertoires temporaires isolés par les tests.
  Aucune collection personnelle n'a été utilisée.
- Aucune dépendance d'exécution ou binding COM ajouté ; `uv.lock` est inchangé.

## Changements vérifiés

- Aperçu avec chemin source et destination, nom Windows invalide/réservé,
  conservation du suffixe audio, racine enregistrée, volume identique et
  collision revalidés au moment de l'exécution.
- Adaptateur Windows fondé sur `MoveFileW`, qui exige un nom de destination
  libre ; l'essai de collision créée après l'aperçu laisse intact le fichier
  préexistant.
- Migration SQLite 005 et journal par opération : UUID, chemins, révision,
  SHA-256 et état. Un renommage où seule la casse change passe par un nom
  temporaire unique ; son chemin est journalisé si le retour échoue.
- Après déplacement réussi, la bibliothèque met à jour le chemin et les
  appartenances aux racines dans une transaction sans changer l'UUID. Un lot
  de scan ancien qui présente ensuite l'ancien chemin ne crée pas un deuxième
  morceau.
- Undo est une opération inverse journalisée. Il refuse le fichier déplacé
  modifié ou un ancien chemin désormais occupé. Le dernier Undo disponible est
  retrouvé depuis le journal au démarrage.
- Les opérations s'exécutent comme tâches d'arrière-plan avec résultat par
  fichier, annulation entre fichiers, état Busy, action explicite d'arrêt du
  lecteur et nouvelle prévisualisation après libération de l'accès.
- Le menu de contexte propose Rename, Move et Move to trash. F2 ouvre Rename ;
  Delete ouvre l'explication de la corbeille indisponible sans muter le fichier.

## Contrôles exécutés

| Contrôle | Résultat |
| --- | --- |
| `uv sync --locked` | Réussi après redirection du cache dans `.local/uv-cache` et accès au backend Hatchling verrouillé. Aucun changement de `uv.lock`. |
| `uv run ruff check .` | Réussi. |
| `uv run ruff format --check .` | Réussi ; 132 fichiers formatés. |
| `uv run pyright` | 0 erreur, 0 avertissement. |
| `pytest tests/unit tests/integration -m "not native_audio"` | 128 réussis, 2 ignorés (liens symboliques non disponibles), 1 désélectionné (audio natif). |
| `tests/ui/test_file_actions.py` | 2 réussis : déplacement/Undo depuis le modèle relié à QML et annulation avant mutation. |
| Autres tests UI, exécutés par fichier | 27 réussis : smoke (6), démonstration (16), navigation (1), éditeur de métadonnées (2), vues du lecteur (2). |
| `pwsh -NoProfile -File scripts/build_windows.ps1` | Réussi sur Windows 11 avec PyInstaller 6.22.2 ; `dist/MTEE/MTEE.exe` fait 2,25 MB. |
| Smoke de `dist/MTEE/MTEE.exe` avec `--data-dir .local/validation/06-package --smoke-test` | Code de sortie 0 ; la base isolée est au schéma 5 et contient `file_operations`. Le paquet contient `FileOperationDialog.qml`. |
| Tous les fichiers `tests/ui` dans un seul processus Pytest | Bloqués après le premier test pendant plus de 60 secondes ; processus interrompu. Les fichiers UI passent séparément. |

Les vérifications UI sont automatisées/offscreen. L'application Windows n'a pas
été pilotée manuellement sur ce poste. Les opérations sur fichiers sont
exercées par des tests sur copies audio temporaires.

## Limites et suites requises

- Déplacement sur deux volumes : non implémenté et non validé. Il faut un
  second volume de recette pour définir et tester la copie, la publication,
  l'annulation et la reprise avant d'activer cette capacité.
- Corbeille : pas d'appel `IFileOperation`, pas de binding COM ajouté, aucune
  restauration réelle observée. L'interface la garde indisponible jusqu'à un
  essai Windows de recyclage et de restauration par fichier.
- Pas de vérification manuelle des permissions insuffisantes, manque d'espace,
  déconnexion du support, lecture réelle pendant mutation ni changement entre
  deux panneaux. Le verrou Busy est vérifié avec `FileAccessCoordinator`, pas
  avec une lecture mpv active.
- La suite UI combinée doit être diagnostiquée ; ses tests isolés, dont le
  nouveau parcours fichier, passent.

## Références natives

Microsoft précise que le nouveau nom transmis à
[`MoveFileW`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew)
ne doit pas déjà exister. La corbeille reste reportée :
[`IFileOperation`](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileoperation)
doit être utilisée dans un appartement STA, et la capacité de restauration
n'a pas été exercée ici.
