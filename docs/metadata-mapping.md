# Correspondance des métadonnées

MTEE lit les tags normalisés par Mutagen et conserve les valeurs répétées dans
des tuples. L'édition passe par un adaptateur choisi d'après l'extension, puis
validé par inspection du conteneur et des tags réels. Chaque écriture prépare
une copie voisine, sauvegarde via l'adaptateur, relit les tags ciblés et
compare le contenu non ciblé avant de publier la copie. Une valeur absente ne
supprime un tag que si la suppression a été explicitement demandée.

## Formats et limites établis au jalon B

| Format inspecté | Tags | Capacités automatiques actuelles | Limites de conservation |
| --- | --- | --- | --- |
| WAV PCM | ID3v2.4 | Champs du tableau ID3 ci-dessous | WAV non PCM et ID3v2.3 refusés |
| MP3 | ID3v2.3 / v2.4 | Champs ID3; Date v2.4 seulement | Date v2.3 en lecture seule, car son aller-retour Mutagen confond TYER/TDRC |
| AIFF PCM | ID3v2.3 / v2.4 | Champs ID3; Date v2.4 seulement | Vérifié sur fixture AIFF PCM synthétique |
| FLAC | Vorbis comments | Champs du tableau Vorbis/MP4 ci-dessous | Alias multiples ou valeurs multiples du champ ciblé refusés; images FLAC comparées |
| Ogg/Vorbis | Vorbis comments | Champs du tableau Vorbis/MP4 ci-dessous | Alias multiples ou valeurs multiples du champ ciblé refusés |
| Ogg/Opus | Vorbis comments | Champs du tableau Vorbis/MP4 ci-dessous | Alias multiples ou valeurs multiples du champ ciblé refusés |
| M4A AAC ou ALAC | Atomes MP4/iTunes | Champs du tableau Vorbis/MP4 ci-dessous | Codec audio inspecté; cover et autres atomes comparés |
| AAC brut/ADTS | — | Écriture désactivée | Aucun aller-retour sûr vérifié |
| Autres formats/extensions | — | Lecture seule | Raison spécifique renvoyée par la capacité |

Les capacités sont observées automatiquement sur copies synthétiques. Elles ne
signifient pas qu'une recette de livraison manuelle a été effectuée.

## Correspondances et restrictions de valeur

| Champ MTEE | ID3 | Vorbis comments / atomes M4A | Règle |
| --- | --- | --- | --- |
| Title | `TIT2` | `TITLE` / `©nam` | Une seule valeur ou alias ciblé |
| Artist | `TPE1` | `ARTIST` / `©ART` | Une seule valeur ou alias ciblé |
| Album | `TALB` | `ALBUM` / `©alb` | Une seule valeur ou alias ciblé |
| Genre | `TCON` | `GENRE` / `©gen` | Une seule valeur ou alias ciblé |
| Date | v2.4 `TDRC` | `DATE` ou `YEAR` / `©day` | ID3v2.3 refusé; alias Vorbis multiples refusés |
| Comment | `COMM` (`eng`/`xxx`, description vide) | `COMMENT` ou `DESCRIPTION` / `©cmt` | Les autres slots/commentaires sont conservés; alias ciblés ambigus refusés |
| Track number | `TRCK` | `TRACKNUMBER` ou `TRACK` / `trkn` | Conserve le total après `/` quand il existe |
| BPM | `TBPM` | `BPM` ou `TEMPO` / `tmpo` | M4A entier de 1 à 1000 |
| Key | `TKEY` | `INITIALKEY`, `KEY` ou `MUSICKEY` / `----:com.apple.iTunes:initialkey` | Le champ M4A utilise un atome libre UTF-8 |

Pour ID3, un champ à plusieurs frames/valeurs est refusé; les slots COMM hors
du commentaire anglais/inconnu sans description restent intacts. Le writer
conserve les frames ID3 non ciblées et vérifie leurs octets sérialisés et les
frames inconnues. WAV garde sa politique historique v2.4 avec ID3v1.

Pour Vorbis, des alias concurrents d'un même champ et des champs avec plusieurs
valeurs rendent uniquement ce champ non modifiable. Les autres commentaires
et, pour FLAC, chaque image (types, dimensions, description et données) sont
comparés après sauvegarde. Pour M4A, les valeurs atomiques non ciblées, les
atomes libres et les pochettes sont comparés. La tonalité initialkey est relue
par MTEE depuis l'atome brut, car Mutagen EasyMP4 ne l'expose pas.

## Lecture normalisée

| Champ MTEE | Clés normalisées essayées |
| --- | --- |
| Title | `title`, `TIT2` |
| Artist | `artist`, `TPE1` |
| Album | `album`, `TALB` |
| Genre | `genre`, `TCON` |
| Date | `date`, `year`, `TDRC`, `TYER` |
| BPM | `bpm`, `tempo`, `TBPM` |
| Key | `initialkey`, `key`, `musickey`, `TKEY` et l'atome M4A `initialkey` |
| Track number | `tracknumber`, `track`, `TRCK` |
| Comment | `comment`, `description`, `COMM` |

Les informations techniques restent distinctes des tags source : durée en
microsecondes, conteneur d'après l'extension, classe Mutagen pour le codec,
débit, fréquence, profondeur et taille. Une erreur de lecture conserve le
fichier dans la bibliothèque avec l'état `unreadable` et son diagnostic.
