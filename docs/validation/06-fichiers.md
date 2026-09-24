# Validation 06 — Renommage, déplacement et corbeille

## Résultat

La tranche permet de prévisualiser puis de renommer ou déplacer des fichiers
audio à l'intérieur d'une bibliothèque enregistrée. Le même volume utilise un
déplacement natif sans remplacement. Entre volumes, le service copie sur le
volume cible, vérifie taille et SHA-256, publie sans remplacement, puis retire
la source par handle après vérification ; l'UUID reste stable et SQLite suit
le nouvel emplacement. L'Undo revalide révision, empreinte et collision.

La livraison ne valide pas tout le plan 06. Le poste expose C: en NTFS, plus un
volume NTFS sans lettre qui n'est pas accessible comme disque de recette ;
`Win32_LogicalDisk` ne liste que C:. Les tests forcent le parcours de copie
intervolume sur C: pour exercer le protocole, mais ils ne prouvent pas son
fonctionnement sur deux volumes distincts. Une sonde native de corbeille a
échoué à démontrer le
recyclage : `IFileOperation` a renvoyé succès et `GetAnyOperationsAborted`
faux, mais la source a disparu et l'espace de noms Shell de la Corbeille était
vide. Une sauvegarde séparée du fichier d'essai a permis de restaurer et
vérifier son hash ; aucun recyclage ni retour depuis la Corbeille n'a été
prouvé. Move to trash reste indisponible dans l'interface, sans suppression
définitive comme solution de repli.

## Environnement observé

- Windows 11, version de build 26200, Python 3.12.14, PySide6 6.9.3,
  Mutagen 1.48.1, PyInstaller 6.22.2.
- Volumes observés avec la lecture système autorisée : C: NTFS, fixe, et un
  volume NTFS sans lettre. Seul C: apparaît dans `Win32_LogicalDisk` ; aucun
  deuxième volume de recette monté n'est accessible.
- Le compte de cette session n'est pas administrateur ; un disque virtuel de
  recette distinct n'a pas pu être provisionné.
- Fichiers audio générés dans des répertoires temporaires isolés par les tests.
  Aucune collection personnelle n'a été utilisée.
- Aucune dépendance d'exécution ou binding COM ajouté ; `uv.lock` est inchangé.

## Changements vérifiés

- Aperçu avec chemin source et destination, nom Windows invalide/réservé,
  conservation du suffixe audio, racine enregistrée et collision revalidée au
  moment de l'exécution.
- Adaptateur Windows fondé sur `MoveFileW`, qui exige un nom de destination
  libre ; l'essai de collision créée après l'aperçu laisse intact le fichier
  préexistant.
- Migrations SQLite 005–006 et journal par opération : UUID, chemins, révision,
  SHA-256, phase et état. Un renommage où seule la casse change passe par un
  nom temporaire unique ; son chemin est journalisé si le retour échoue.
- Parcours intervolume testé en le forçant sur C: NTFS : copie vérifiée,
  conservation de l'UUID et des horodatages/attributs de base, annulation en
  cours qui laisse la source, et échec injecté du retrait qui conserve les
  deux copies pour inspection. Le test n'a pas traversé deux volumes réels.
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
- Le glisser-déposer d'une sélection d'un groupe éditeur vers un autre onglet
  dossier appelle le même aperçu Move et attend la confirmation ; le parcours
  QML testé vérifie les UUID capturés et la destination. Le geste de souris
  réel n'a pas été vérifié manuellement.

## Contrôles exécutés

| Contrôle | Résultat |
| --- | --- |
| `uv sync --locked` | Réussi avec le cache redirigé vers `.local/validation/uv-cache` et accès au backend Hatchling verrouillé. Aucun changement de `uv.lock`. |
| `uv run ruff check .` | Réussi. |
| `uv run ruff format --check .` | Réussi ; 132 fichiers formatés. |
| `uv run pyright` | 0 erreur, 0 avertissement. |
| `pytest tests/unit tests/integration -m "not native_audio"` | 131 réussis, 2 ignorés (liens symboliques non disponibles), 1 désélectionné (audio natif). Inclut le parcours de copie intervolume forcé sur C:. |
| UI, chaque fichier exécuté séparément | 29 réussis : file actions (2), smoke (6), démonstration (16), navigation navigateur (1), éditeur de métadonnées (2), vues du lecteur (2). |
| `pwsh -NoProfile -File scripts/build_windows.ps1` | Réussi sur Windows 11 avec PyInstaller 6.22.2 ; `dist/MTEE/MTEE.exe` fait 2,25 MB. |
| Smoke de `dist/MTEE/MTEE.exe` avec `--data-dir .local/validation/06-package-final --smoke-test` | Code de sortie 0 ; la base isolée est au schéma 6 et `file_operations` contient la colonne `phase`. Le paquet contient `FileOperationDialog.qml`. |
| Tous les fichiers `tests/ui` dans un seul processus Pytest | Bloqués après le premier test pendant plus de 60 secondes ; processus interrompu. Les fichiers UI passent séparément. |

Les vérifications UI sont automatisées/offscreen. Une tentative de recette
manuelle a lancé le paquet avec une bibliothèque isolée et un fichier WAV
généré, mais l'outil d'automatisation n'a pas retourné la fenêtre MTEE dans son
inventaire des fenêtres sélectionnables, malgré le processus visible dans
Windows. Selon la consigne du skill `computer-use`, seules les fenêtres
retournées par cet inventaire peuvent être ciblées ; aucun clic, glisser-déposer
ou déplacement de fichier n'a donc été tenté, puis le processus a été fermé.
L'application Windows n'a pas été pilotée manuellement sur ce poste. Les opérations sur fichiers sont
exercées par des tests sur copies audio temporaires. La sonde IFileOperation
STA a utilisé le seul nom `mtee-trash-probe-20260924.wav` dans un dossier
temporaire dédié, avec une copie de sauvegarde distincte ; le fichier original
a été rétabli par copie et son SHA-256 correspondait à la sauvegarde.

## Limites et suites requises

- Déplacement sur deux volumes : le protocole copy-first, le journal de phase,
  l'annulation et le retrait par handle sont implémentés et testés en forçant
  cette route sur C: NTFS. Aucun déplacement n'a été exécuté sur deux volumes
  distincts ; il reste à vérifier cette capacité sur un volume de recette,
  notamment déconnexion, manque d'espace, permissions, reprise après
  redémarrage et attributs non pris en charge.
- Corbeille : un appel `IFileOperation` a été essayé en STA avec
  `FOFX_RECYCLEONDELETE`, sans binding ajouté au produit. Malgré le succès
  HRESULT et l'absence d'abandon, la copie a quitté son chemin et aucune entrée
  n'est apparue dans l'espace de noms Shell de la Corbeille. Faute de
  `PostDeleteItem` positif et de restauration native vérifiée, ce résultat est
  un échec de recette ; la commande reste désactivée.
- Pas de vérification manuelle des permissions insuffisantes, manque d'espace,
  déconnexion du support, geste drag-and-drop, lecture réelle pendant mutation
  ni sélection/file après redémarrage. Le verrou Busy est vérifié avec
  `FileAccessCoordinator`, pas avec une lecture mpv active.
- La suite UI combinée s'est bloquée lors d'une tentative précédente ; les six
  fichiers UI, dont le parcours fichier, passent chacun séparément.

## Références natives

Microsoft précise que le nouveau nom transmis à
[`MoveFileW`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew)
ne doit pas déjà exister. La corbeille reste reportée :
[`IFileOperation`](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileoperation)
doit être utilisée dans un appartement STA, et la capacité de restauration
n'a pas été exercée ici.
