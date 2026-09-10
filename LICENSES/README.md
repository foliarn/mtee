# Licences des composants distribués

Ce répertoire contient le texte des licences des composants réellement embarqués dans la distribution de MTEE. `THIRD_PARTY_NOTICES.md`, à la racine, en donne la liste et l'état de vérification.

## Police d'interface

`src/mtee/resources/fonts/` est destiné aux fichiers de Geist Sans. Les fichiers de police ne sont pas encore versionnés : leur téléchargement n'a pas été effectué pendant l'étape 01. Tant qu'ils sont absents, MTEE utilise la première police de repli disponible du système et la fenêtre reste utilisable.

Pour les ajouter :

1. Récupérer la version distribuée officiellement, ainsi que son texte de licence.
2. Placer les fichiers `.ttf` ou `.otf` dans `src/mtee/resources/fonts/`.
3. Copier le texte de la licence ici sous le nom `Geist-OFL.txt` ou l'intitulé exact du fichier fourni.
4. Compléter `THIRD_PARTY_NOTICES.md` avec la version, la source et la licence constatées.

`src/mtee/fonts.py` enregistre automatiquement tout fichier de police présent dans ce répertoire au démarrage ; aucun code supplémentaire n'est nécessaire.

## Licence de MTEE

Le projet pourra être publié en open source. Aucune licence n'est attribuée à ce stade : la décision revient à l'auteur avant une publication sous une licence nommée.
