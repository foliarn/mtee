# Dépendances natives : état des vérifications

Document exigé par le plan 01 pour la lecture audio (plan 04) et pour la distribution Windows. Il consigne ce qui est décidé, ce qui reste à vérifier et ce qui n'a pas été observé.

## libmpv — lecteur du plan 04

`PLAN.md` retient libmpv, piloté par une couche Python dédiée. Le socle ne rend pas mpv obligatoire : l'application démarre, affiche sa fenêtre et se ferme sans aucune bibliothèque audio native.

Le plan 04 a retenu le build Windows x86-64 `mpv-dev-lgpl` de zhongfly/mpv-winbuild. Le manifeste épingle l'archive et le DLL par SHA-256 ; voir [docs/native-dependencies.md](../native-dependencies.md) pour la provenance, les tests natifs et les limites de licence. L'acceptation sur une machine Windows propre et l'audit complet des dépendances restent ouverts.

La DLL est chargée depuis un emplacement contrôlé de l'application, jamais par une recherche implicite dans `PATH`, afin qu'une DLL étrangère présente sur le poste ne soit pas utilisée. Si le runtime manque ou ne se charge pas, l'application garde l'explorateur utilisable et affiche l'erreur du lecteur.

Le fournisseur annonce libmpv sous LGPL-2.1-or-later et FFmpeg statiquement lié sous LGPL-3.0-or-later, tout en signalant qu'il ne garantit pas avoir désactivé chaque paquet incompatible. Cette déclaration n'est pas un audit juridique. La redistribution publique attend l'examen complet des dépendances, licences, sources et obligations applicables.

## FFmpeg et ffprobe — plan 07

Absents des livraisons A et B, conformément à `PLAN.md`. Ni le binaire, ni sa version, ni ses conditions de redistribution n'ont été examinés pendant l'étape 01.

## Bibliothèques d'analyse — plan 09

NumPy, SciPy et librosa ne sont pas installés par le socle. Leur ajout appartient à l'étape d'analyse, avec la mesure de leur effet sur la taille et le temps de démarrage de la distribution.

## Police d'interface

La direction visuelle retient Geist Sans, embarquée localement avec sa licence. Le socle contient le mécanisme d'enregistrement (`src/mtee/fonts.py`) et le répertoire `src/mtee/resources/fonts/`. Les fichiers de police n'y sont pas encore versionnés ; l'application utilise alors la première police de repli disponible du système. Voir `LICENSES/README.md` pour la procédure d'ajout.

## Qt et PySide6

PySide6 fournit Qt et ses greffons ; la distribution est produite par PyInstaller en répertoire, ce qui permet d'inspecter les greffons et les DLL présents. Les modules non utilisés — dont QtMultimedia, QtWebEngine et QtCharts — sont exclus par `packaging/mtee.spec`.
