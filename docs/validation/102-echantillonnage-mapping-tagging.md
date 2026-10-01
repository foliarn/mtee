# Validation de l’étude d’échantillonnage mapping/tagging

## Périmètre réalisé

L’outil `scripts/audit_mapping_sample.py` inventorie les conteneurs MP3, FLAC, WAV, AIFF/AIF et M4A en lecture seule. Il conserve les tags bruts, les valeurs normalisées exposées par `MetadataReader`, les valeurs répétées, les noms de champs et les références musicales locales reconnues. Il note la taille et la date de modification avant et après lecture, exclut les liens symboliques et jonctions rencontrés sous les racines, et refuse une sortie située dans une racine scannée.

Le tirage est reproductible depuis l’inventaire figé. Il distingue le groupe aléatoire du groupe ciblé et inscrit les motifs et la priorité de sélection. Les résultats contenant des données de collection restent sous `.local/validation/102/`, exclu de Git.

## Contrôles effectués

Environnement de cette exécution : Python 3.12.14, Mutagen 1.48.1. Le script a été exercé depuis les sources sur la racine explicitement fournie par l’utilisateur. La dernière exécution a terminé l’inventaire et produit les fichiers privés prévus. L’examen local porte sur les tags, le nom du fichier et son contexte de dossier; aucun audio n’a été écouté.

Les contrôles synthétiques effectués depuis la racine du dépôt sont :

    rtk proxy uv run python -m pytest tests/unit/test_mapping_sample_audit.py -q
    uv run ruff check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py
    uv run ruff format --check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py
    git diff --check

Les onze tests couvrent le tirage stable, la séparation des groupes et des priorités, les populations et formats rares, les valeurs Unicode multiples, l’absence de métadonnées, les tags illisibles, l’absence d’écriture audio, le traitement des alias Mutagen absents, l’assainissement des URL musicales et l’exclusion des jonctions.

Une première exécution a classé des fichiers FLAC lisibles comme illisibles : l’accès à un alias Vorbis absent peut lever `ValueError` avec Mutagen. Le lecteur a été corrigé pour considérer cette exception comme une clé absente. Une nouvelle exécution a ensuite confirmé la lecture des fichiers observés sans modification de taille ni de date pendant la lecture. La première sortie privée est conservée comme trace non concluante; elle n’est pas utilisée dans le rapport transmis.

## Livrables et limites

Le rapport détaillé, le résumé, l’inventaire et les lignes de revue demeurent privés dans le dossier d’exécution local. Aucun titre, artiste, chemin de collection, URL brute, audio ou export de base n’est inclus ici.

Aucune écriture de tag ou de nom n’a été faite. Aucune recherche Web, API Spotify/SoundCloud, connexion Shovel, export Rekordbox ou écoute n’a été réalisée. Les identités proposées sont des indices locaux non confirmés. La version de Rekordbox n’a pas été relevée et sa compatibilité n’a pas été testée. Les collisions et renommages restent des simulations sans suffixe de collision validé.

Un examen humain des cas prioritaires et une décision sur les groupes d’artistes restent nécessaires avant de cadrer l’automatisation, le catalogue Artists ou l’application de corrections.
