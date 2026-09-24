# Correspondance des métadonnées

MTEE lit les tags avec Mutagen (`File(..., easy=True)`). Les valeurs source
restent des tuples afin de ne pas perdre les répétitions. Une édition ne
modifie que les champs explicitement changés ; une valeur vide ne supprime un
tag que lorsqu'elle a été saisie puis validée comme suppression.

| Champ MTEE | ID3 natif | État d’écriture vérifié |
| --- | --- | --- |
| Title | `TIT2` | Une seule valeur sur WAV PCM avec ID3v2.4. |
| Artist | `TPE1` | Une seule valeur sur WAV PCM avec ID3v2.4. |
| Album | `TALB` | Une seule valeur sur WAV PCM avec ID3v2.4. |
| Genre | `TCON` | Une seule valeur sur WAV PCM avec ID3v2.4. |
| Date | `TDRC`, ou `TYER` si seul présent | WAV PCM avec ID3v2.4 ; refus si les deux slots coexistent. |
| Comment | `COMM` (langue `eng`/`xxx`, description vide) | Refus si un autre slot de commentaire existe. |
| Track number | `TRCK` | Une seule valeur ; conserve le total après `/`. |
| BPM | `TBPM` | Une seule valeur. |
| Key | `TKEY` | Une seule valeur ; le texte d'origine reste libre. |

## Capacités activées dans le plan 05

Seuls les fichiers WAV PCM avec tags ID3v2.4 sont modifiables. Le numéro de
format WAVE doit être PCM (`1`). Les tags absents peuvent être créés en
ID3v2.4. Les tags ID3v2.3, les autres codages WAV et tous les autres conteneurs
restent en lecture seule, même si Mutagen sait les ouvrir. La matrice sera
élargie seulement après des essais de copie et de relecture pour le format,
la version et les slots concernés.

Un champ à valeurs multiples, des commentaires non ciblés ou un couple Date
ambigu rendent le champ concerné non éditable. La pochette, les frames ID3
inconnues et les frames qui ne sont pas visées par le patch sont conservées.
Un remplacement écrit une copie temporaire voisine, la relit, vérifie les
frames et l'empreinte, puis utilise `ReplaceFileW` avec une sauvegarde de
récupération sur Windows.

## Lecture normalisée

| Champ MTEE | Clés normalisées essayées | Affichage |
| --- | --- | --- |
| Title | `title` | Première valeur ; le nom de fichier reste un libellé de secours. |
| Artist | `artist` | Toutes les valeurs jointes par une virgule. `albumartist` reste distinct. |
| Album | `album` | Première valeur. |
| Genre | `genre` | Toutes les valeurs jointes par une virgule. |
| Date | `date`, puis `year` | Première valeur. |
| BPM | `bpm`, puis `tempo` | Première valeur ; le texte source n'est pas arrondi. |
| Key | `initialkey`, `key`, puis `musickey` | Première valeur. |
| Track number | `tracknumber`, puis `track` | Première valeur. |
| Comment | `comment`, puis `description` | Toutes les valeurs jointes par une virgule. |

Les lecteurs Easy de Mutagen normalisent les autres familles à la lecture.
Pour FLAC, Ogg/Vorbis, Opus et MP4, l'écriture demeure désactivée à cette
étape. AAC brut reste également en lecture seule. Cette prudence préserve les
alias, atomes, commentaires, dates et valeurs décimales dont l'aller-retour
n'a pas été validé.

Les informations techniques restent distinctes des tags source : durée en
microsecondes, conteneur d'après l'extension, nom de classe Mutagen pour le
codec lorsqu'il est reconnu, débit, fréquence, profondeur et taille. Une
erreur de lecture conserve le fichier dans la bibliothèque avec l'état
`unreadable` et son diagnostic.
