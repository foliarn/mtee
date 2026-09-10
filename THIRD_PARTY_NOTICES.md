# Composants tiers distribués avec MTEE

Ce document liste les composants réellement embarqués dans la distribution Windows produite par `scripts/build_windows.ps1`, avec l'état de vérification de leur licence. Un composant absent de la distribution n'y figure pas.

| Composant | Rôle | Licence annoncée | État de vérification |
|---|---|---|---|
| Python 3.12 | Interpréteur embarqué par PyInstaller | PSF License | Licence connue, texte non encore copié dans `LICENSES/` |
| PySide6 et Qt 6 | Interface QML, greffons et DLL Qt | LGPL v3 pour Qt, LGPL v3 pour PySide6 | À confirmer sur la version verrouillée dans `uv.lock` |
| Mutagen | Lecture des métadonnées audio | GPL v2 ou ultérieure | À confirmer ; conditionne la licence de MTEE |
| PyInstaller | Outil de construction, non redistribué | GPL v2 avec exception pour les exécutables produits | À confirmer sur la version verrouillée |
| Geist Sans | Police de l'interface | Attendue sous SIL Open Font License | Non vérifiée : fichiers non versionnés à ce jour |

Points à trancher avant une publication : Mutagen étant sous licence GPL, la licence retenue pour le code de MTEE doit être compatible avec la distribution combinée. Aucune licence n'est attribuée à MTEE à ce stade ; la décision revient à l'auteur.

Les textes de licence des composants effectivement embarqués sont rassemblés dans `LICENSES/`. Ce fichier est mis à jour à chaque changement de dépendance distribuée, en indiquant la version constatée et non une version supposée.
