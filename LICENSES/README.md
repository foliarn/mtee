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

MTEE est distribué sous licence GNU General Public License version 3 ou ultérieure (`GPL-3.0-or-later`), décision de l'auteur du 2026-10-14. Le texte officiel est dans `LICENSE` à la racine du dépôt (identique à <https://www.gnu.org/licenses/gpl-3.0.txt>, SHA-256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`). Ce répertoire ne contient que les licences des composants tiers.
