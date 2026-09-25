# Dépendances natives distribuées

Ce document décrit les dépendances natives de MTEE et sépare leur provenance,
les vérifications exécutées et les obligations qui restent à examiner. Une
empreinte vérifiée identifie un binaire ; elle ne vaut ni audit de licence ni
validation sur toutes les versions de Windows.

## Lecteur : libmpv Windows x86-64

Le lecteur utilise l'API C de `libmpv-2.dll` directement depuis `ctypes`. Le
binding Python `python-mpv` a été évalué puis écarté : il n'est pas ajouté à
`pyproject.toml` et le service dépend seulement du protocole interne
`PlayerBackend`. Les appels sont isolés dans `MpvBackend`; les événements sont
copiés depuis le thread mpv puis transmis aux modèles par une connexion Qt en
file d'attente. MTEE initialise mpv sans configuration utilisateur, sans
scripts, sans vidéo et sans fenêtre de rendu. La sortie normale est WASAPI.
Le test natif force une sortie `null` et ne prouve donc pas qu'un son a été
entendu.

| Élément | Valeur vérifiée |
| --- | --- |
| Fournisseur / build | [zhongfly/mpv-winbuild](https://github.com/zhongfly/mpv-winbuild), archive `mpv-dev-lgpl` |
| Release | `2026-09-23-6fd80b2003` |
| Commit mpv | `6fd80b2003873ef2bed09e78374549687a143236` |
| Commit FFmpeg rapporté | `a6e5d5ff9` |
| Archive | `mpv-dev-lgpl-x86_64-20260923-git-6fd80b2003.7z` |
| SHA-256 archive | `8d65bab888f5dfff059c50431d2c72c4c6ab78706c363056697176694563321d` |
| SHA-256 DLL | `85071ee7c8bfc9f3690a0eb140f15bbb697cdf81bc96e9c905dc8a54cfff8c10d` |
| Architecture / taille | Windows x86-64 / 100 392 960 octets |
| Développement | `vendor/mpv/libmpv-2.dll`, ignoré par Git |
| Distribution | `mtee/native/mpv/libmpv-2.dll` |
| Chargement PyInstaller | emplacement contrôlé sous `_MEIPASS`, jamais recherche implicite dans `PATH` |

Le DLL importé demande aussi `vulkan-1.dll`. Cette dépendance n'est pas dans
l'archive `mpv-dev-lgpl` et n'est pas livrée par le dépôt à ce stade ; sur la
machine de développement, elle est fournie par les composants graphiques de
Windows. Il faut encore vérifier le démarrage sur une machine Windows propre,
hors réseau, et la réaction si le chargeur Vulkan n'est pas installé.

### Formats et signal natif observé

La seule fixture décodée par le vrai runtime est un signal PCM 16 bits mono,
WAV, généré par le test dans un dossier temporaire avec espaces et caractères
accentués. `libmpv` rapporte un codec et une durée, accepte pause/reprise et un
seek proche de la cible. L'audio est dirigé vers `null`. Les autres formats
attendus (MP3, FLAC, AAC ADTS, AIFF, Vorbis, Opus, M4A/AAC et M4A/ALAC) n'ont
pas de fixtures autorisées et n'ont donc pas été validés.

Avec le gestionnaire `faulthandler` de Pytest actif, le test affiche une
exception Windows de premier passage `0xe24c4a02` depuis `mpv_wait_event` ;
l'amont l'identifie comme l'exception SEH de LuaJIT et décrit un risque
d'intégration particulier avec l'API de rendu vidéo
([signalement amont](https://github.com/shinchiro/mpv-winbuild-cmake/issues/811)).
MTEE utilise l'API client audio seulement, sans créer de contexte de rendu.
Le même test termine proprement avec `faulthandler` désactivé (code de sortie
0), et le smoke test de la build GUI sans console termine également avec 0.
Le signal demeure à contrôler lors de la recette manuelle ; le désactiver dans
le test n'est pas une preuve d'écoute ni une validation sur Windows propre.

### Provenance, licences et redistribution

Le fournisseur décrit cette variante comme libmpv LGPL-2.1-or-later, avec
FFmpeg lié statiquement sous LGPL-3.0-or-later. Il précise qu'il ne peut pas
garantir que tous les composants incompatibles avec LGPL soient désactivés.
Le dépôt du script de build est annoncé sous MIT. Ces déclarations sont celles
du fournisseur, pas un audit de la DLL ; le binaire contient un ensemble de
dépendances compilées qui n'a pas été entièrement inventorié ici.

Les liens de référence sont [la licence de mpv](https://github.com/mpv-player/mpv),
[FFmpeg](https://github.com/FFmpeg/FFmpeg) et [le dépôt de build](https://github.com/zhongfly/mpv-winbuild).
La notice incluse à `mtee/resources/THIRD_PARTY_NOTICES.txt` conserve la
provenance et les principales mentions. Avant toute redistribution publique,
il reste à auditer les dépendances transitives et leur configuration, fournir
les textes de licence et les sources/scripts correspondants lorsque requis,
et confirmer que les conditions de redistribution de ce binaire précis sont
satisfaites. Aucune validation juridique n'est revendiquée.

L'acquisition reproductible passe par
`scripts/fetch_mpv.ps1` : le script télécharge uniquement l'URL épinglée,
vérifie le SHA-256 de l'archive, extrait le seul DLL attendu dans un répertoire
de staging sous `vendor`, en vérifie l'empreinte, puis refuse tout
remplacement d'un runtime existant.

## FFmpeg et ffprobe exécutables

Le runtime de conversion est séparé de `libmpv` : MTEE lance les outils
épinglés par `FfmpegRuntime` depuis un chemin explicite, sans shell ni recherche
dans `PATH`. En développement, les binaires se trouvent dans
`vendor/ffmpeg/bin`; le paquet Windows les place sous
`mtee/native/ffmpeg/bin`. Seuls `ffmpeg.exe`, `ffprobe.exe` et les DLL FFmpeg
partagées sont installés. L'archive, le manifeste, les tailles et empreintes
SHA-256 sont contrôlés par `scripts/fetch_ffmpeg.ps1` et le build Windows.

| Élément | Valeur vérifiée |
| --- | --- |
| Fournisseur / variante | [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), `win64-lgpl-shared` |
| Release | `autobuild-2026-09-24-14-14` |
| FFmpeg | `n9.0.2-3-ga5923073bf-20260924` |
| Commit FFmpeg rapporté | `a5923073bf` |
| Archive | `ffmpeg-n9.0.2-3-ga5923073bf-win64-lgpl-shared-9.0.zip` |
| SHA-256 archive | `735bae484ba2c3342bfb34df477b9c6b0f43f9819f4d2fde011be293ee1b6517` |
| Taille archive | 76 974 101 octets |
| Licence indiquée par l'archive | LGPL-3.0, texte inclus dans la distribution |
| Cible | Windows x86-64 |

Le manifeste local comprend les empreintes des deux exécutables et des sept
DLL livrées. Le binaire annonce les encodeurs natifs AAC, ALAC, FLAC et les
encodeurs MP3, Vorbis et Opus ; cette annonce ne constitue pas encore la
matrice complète des conversions livrées. La configuration inspectée active
`--enable-libmp3lame`, `--enable-libvorbis`, `--enable-libopus` et
`--enable-version3`, sans `--enable-gpl`, et désactive `libx264`/`libx265`.
Cette lecture du binaire ne remplace pas l'audit des dépendances transitives,
des sources correspondantes et des conditions de redistribution du build.

`scripts/create_audio_fixtures.py` génère des signaux locaux de trois secondes
pour MP3, FLAC, WAV PCM, AIFF PCM, Ogg/Vorbis, Opus, AAC/ADTS, M4A/AAC et
M4A/ALAC, avec une petite PNG de test générée localement pour les vérifications
de pochettes. Le manifeste de sortie est local, inclut les codecs réellement
retournés par ffprobe et une empreinte par fichier; aucun binaire de fixture
n'est versionné. L'AAC brut demeure non éditable si Mutagen ne peut garantir un
aller-retour sûr.

Pour ce sous-jalon, versions et probes du runtime ont été obtenus depuis les
binaires épinglés. La recette d'édition/conversion, le démarrage d'un paquet
Windows depuis une machine propre et l'audit complet des licences restent
distincts et non réalisés tant qu'ils ne sont pas consignés ci-dessous.

## Renommage et déplacement Windows

Le renommage et les déplacements sur un même volume passent par
`MoveFileW`, appelé directement via `ctypes` dans
`src/mtee/services/platform/windows_file_ops.py`. La documentation Microsoft
précise que le nom de destination ne doit pas déjà exister ; MTEE revalide
l'absence de collision avant l'appel et l'API native refuse une destination
occupée. Entre volumes, le service copie vers un temporaire exclusif du volume
cible, vérifie taille, SHA-256 et attributs de base, publie sans remplacement,
puis retire la source via son handle Windows verrouillé et vérifié. Les phases
sont journalisées. Cette routine a été testée en forçant ce parcours sur C:
NTFS ; aucun second volume de recette n'est accessible ici, donc le déplacement
sur deux volumes distincts reste à valider. Les fichiers chiffrés sont refusés.

Le retrait vérifié de la source utilise
[`SetFileInformationByHandle`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
avec `FILE_DISPOSITION_INFO` sur un handle ouvert pour lecture et suppression,
sans partage d'écriture ou de suppression. Les horodatages et attributs de
base pris en charge sont obtenus et posés par handle via
[`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
et `SetFileInformationByHandle`.

Cette livraison n'ajoute aucun binding COM. Une sonde temporaire exécutée en
STA a appelé `IFileOperation` avec `FOFX_RECYCLEONDELETE` sur un fichier
jetable : Windows a renvoyé un succès et aucun abandon, mais la source avait
disparu et l'espace de noms Shell de la Corbeille ne contenait aucun élément.
Une copie de sauvegarde distincte a permis de remettre les mêmes octets au
chemin source ; le recyclage et la restauration natives n'ont donc pas été
démontrés. Ce résultat ne satisfait pas le contrat strict : Delete ouvre une
explication et reste indisponible, sans repli vers une suppression définitive.
L'interface doit rester dans un appartement STA, et son résultat par fichier
doit être observé via `IFileOperationProgressSink::PostDeleteItem`, qui
distingue un élément présent dans la Corbeille d'une suppression complète.
Voir la [documentation de MoveFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew),
la [documentation de IFileOperation](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileoperation),
[`PostDeleteItem`](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperationprogresssink-postdeleteitem)
et le rapport de [validation du plan 06](validation/06-fichiers.md).

## Autres dépendances natives

PySide6 fournit Qt et ses greffons ; le build PyInstaller reste en mode
répertoire afin de rendre ses fichiers inspectables. `packaging/mtee.spec`
exclut QtMultimedia, QtWebEngine, QtCharts et les autres modules non utilisés.
Les bibliothèques d'analyse audio et leurs dépendances natives appartiennent
aux plans ultérieurs.
