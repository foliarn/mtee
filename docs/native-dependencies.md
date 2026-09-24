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

Aucun exécutable `ffmpeg` ou `ffprobe` n'est ajouté à MTEE ou au paquet
Windows. Le décodeur statiquement lié à libmpv fait partie du runtime du
lecteur décrit ci-dessus et ne constitue pas un processus externe.

## Renommage et déplacement Windows

Le renommage et les déplacements sur un même volume passent par
`MoveFileW`, appelé directement via `ctypes` dans
`src/mtee/services/platform/windows_file_ops.py`. La documentation Microsoft
précise que le nom de destination ne doit pas déjà exister ; MTEE revalide
l'absence de collision avant l'appel et l'API native refuse elle-même une
destination occupée. Les déplacements entre volumes restent bloqués jusqu'à
la validation séparée de leur copie, de leur empreinte et de leur reprise.

Cette livraison n'ajoute aucun binding COM. `IFileOperation` n'est pas
instanciée : Microsoft indique que cette interface doit s'exécuter dans un
appartement monothread (STA), et aucun test de corbeille/restauration réelle
n'a pu être fait sur ce poste. Le raccourci Delete ne déclenche donc pas une
suppression ; il ouvre une explication et la commande reste indisponible. Il
n'existe aucun repli vers une suppression définitive. Voir la [documentation
de MoveFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew),
la [documentation de IFileOperation](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileoperation)
et le rapport de [validation du plan 06](validation/06-fichiers.md).

## Autres dépendances natives

PySide6 fournit Qt et ses greffons ; le build PyInstaller reste en mode
répertoire afin de rendre ses fichiers inspectables. `packaging/mtee.spec`
exclut QtMultimedia, QtWebEngine, QtCharts et les autres modules non utilisés.
Les bibliothèques d'analyse audio et leurs dépendances natives appartiennent
aux plans ultérieurs.
