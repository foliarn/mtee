# Correspondance des métadonnées

MTEE lit les tags avec Mutagen (`File(..., easy=True)`). Ce tableau décrit les
clés normalisées demandées à ses lecteurs de format et les champs affichés par
l’explorateur. La lecture n’appelle jamais `save()` ; une clé absente reste
absente dans `MetadataSnapshot`.

| Champ MTEE | Clés normalisées essayées | Affichage |
| --- | --- | --- |
| Title | `title` | Première valeur ; le nom du fichier sert seulement de libellé de secours. |
| Artist | `artist` | Toutes les valeurs jointes par une virgule. `albumartist` reste distinct et n’est pas présenté comme artiste de piste. |
| Album | `album` | Première valeur. |
| Genre | `genre` | Toutes les valeurs jointes par une virgule. |
| Date | `date`, puis `year` | Première valeur. |
| BPM | `bpm`, puis `tempo` | Première valeur ; la conversion numérique de tri conserve le texte d’origine. |
| Key | `initialkey`, `key`, puis `musickey` | Première valeur. |
| Track number | `tracknumber`, puis `track` | Première valeur. |
| Comment | `comment`, puis `description` | Toutes les valeurs jointes par une virgule. |

Les lecteurs Easy de Mutagen normalisent les familles source avant que ces
alias soient consultés. Les tags ID3 utilisent notamment TIT2, TPE1, TALB,
TCON, TDRC, TBPM, TKEY, TRCK et COMM ; les commentaires Vorbis/FLAC/Opus et
les tags MP4 sont lus selon les clés exposées par leur lecteur Easy. Les tests
de cette livraison vérifient effectivement les tags ID3 contenus dans WAV.
Les autres conteneurs suivent les lecteurs Easy de Mutagen mais n’ont pas tous
été validés par un corpus de fichiers réels dans cette exécution.

Les informations techniques sont séparées des tags source : durée en
microsecondes, conteneur d’après l’extension, nom de classe Mutagen pour le
codec lorsqu’il est reconnu, débit, fréquence, profondeur et taille du fichier.
Une erreur de lecture conserve le fichier dans la bibliothèque avec l’état
`unreadable` et le diagnostic associé.
