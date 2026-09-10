# Dépendances natives : état des vérifications

Document exigé par le plan 01 pour la lecture audio (plan 04) et pour la distribution Windows. Il consigne ce qui est décidé, ce qui reste à vérifier et ce qui n'a pas été observé.

## libmpv — lecture native prévue au plan 04

`PLAN.md` retient libmpv, piloté par une couche Python dédiée. Le socle ne rend pas mpv obligatoire : l'application démarre, affiche sa fenêtre et se ferme sans aucune bibliothèque audio native.

Architecture cible : Windows x86-64 en premier, la même architecture que l'interpréteur Python et que Qt. Une bibliothèque compilée pour une autre architecture ne doit jamais être chargée « au cas où ».

Procédure de chargement retenue pour le plan 04 : rechercher `libmpv-2.dll` d'abord dans un répertoire de l'application connu et vérifié, jamais par une recherche implicite dans `PATH`, afin qu'une DLL étrangère présente sur le poste ne soit pas utilisée. Le chargement échoué doit produire un message clair et laisser l'application utilisable sans lecteur.

Redistribution : la licence effective du binaire retenu (LGPL ou GPL selon les options de compilation) et sa provenance doivent être vérifiées avant toute distribution, car elles conditionnent les obligations de MTEE. **Non vérifié à ce jour** : aucun binaire n'a été téléchargé ni examiné pendant l'étape 01, et aucun choix de fournisseur n'est arrêté.

## FFmpeg et ffprobe — plan 07

Absents des livraisons A et B, conformément à `PLAN.md`. Ni le binaire, ni sa version, ni ses conditions de redistribution n'ont été examinés pendant l'étape 01.

## Bibliothèques d'analyse — plan 09

NumPy, SciPy et librosa ne sont pas installés par le socle. Leur ajout appartient à l'étape d'analyse, avec la mesure de leur effet sur la taille et le temps de démarrage de la distribution.

## Police d'interface

La direction visuelle retient Geist Sans, embarquée localement avec sa licence. Le socle contient le mécanisme d'enregistrement (`src/mtee/fonts.py`) et le répertoire `src/mtee/resources/fonts/`. Les fichiers de police n'y sont pas encore versionnés ; l'application utilise alors la première police de repli disponible du système. Voir `LICENSES/README.md` pour la procédure d'ajout.

## Qt et PySide6

PySide6 fournit Qt et ses greffons ; la distribution est produite par PyInstaller en répertoire, ce qui permet d'inspecter les greffons et les DLL présents. Les modules non utilisés — dont QtMultimedia, QtWebEngine et QtCharts — sont exclus par `packaging/mtee.spec`.
