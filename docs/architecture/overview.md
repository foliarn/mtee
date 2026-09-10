# Architecture du socle MTEE

Ce document décrit les couches créées à l'étape 01 et le sens de leurs appels. Il complète `Plans d'exécution/01-socle-technique.md`, qui reste le document opérationnel de l'étape.

## Couches et dépendances autorisées

Les appels vont toujours de la présentation vers le domaine, jamais l'inverse.

| Couche | Répertoire | Rôle | Peut appeler |
|---|---|---|---|
| Présentation | `src/mtee/qml/` | Fenêtre, zones nommées, états visuels | Rien directement : lit des propriétés et modèles exposés |
| Modèles et pont | `src/mtee/models/` | Rôles visibles, transmission des actions | domaine, services, persistance en lecture |
| Services | `src/mtee/services/` | Travail effectif : chemins, tâches, accès fichiers | domaine, persistance |
| Persistance | `src/mtee/persistence/` | SQLite, migrations, réglages | domaine |
| Domaine | `src/mtee/domain/` | Types purs : identité, temps, tâches | rien |

QML n'accède ni au système de fichiers ni aux commandes système : la fenêtre reçoit `shell`, `jobsModel` et `tracksModel` par le contexte racine du moteur QML. Un service n'importe aucun élément visuel ; il ne connaît ni `QQuickItem`, ni la fenêtre.

## Assemblage au démarrage

`src/mtee/app.py` est le seul endroit qui assemble les couches. Son ordre est : lecture des arguments (`cli.py`), création de l'application Qt et de son identité, résolution des répertoires (`services/app_paths.py`), ouverture et migration de la base (`persistence/database.py`), enregistrement de la police (`fonts.py`), création du service de tâches, des modèles et du pont, puis chargement de `qml/Main.qml` retrouvé par `assets.py`.

Une erreur de stockage renvoie le code 3, une ressource d'interface manquante le code 4, un argument inconnu le code 2 par `argparse`. Chaque échec écrit une explication en anglais sur la sortie d'erreur ; l'interface est en anglais, la documentation en français.

À la fermeture, `_shutdown` annule les tâches, attend leur arrêt, signale celles restées incomplètes puis ferme les connexions SQLite.

## Threads

Le thread graphique traite les interactions et le dessin. `JobService` exécute les tâches dans un `QThreadPool` ; il publie ses états par signaux Qt, que Qt délivre au thread des modèles. Le registre des états est protégé par un verrou, ce qui permet de lire un instantané depuis n'importe quel thread sans dépendre d'une boucle d'événements.

`FileAccessCoordinator` sérialise les accès au fichier d'un morceau par `track_id`, avec un délai d'acquisition borné et une libération garantie même en cas d'exception. SQLite utilise une connexion par thread, créée à la demande, en mode WAL.

## Contrats exportés

`TrackId` est un UUID interne stable ; deux copies physiques ont deux identifiants. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` détecte les modifications ordinaires et ne prouve pas le contenu : `sha256_of_file` complète le contrôle pour une opération critique. `TimeRange(start_us, end_us)` est en microsecondes, fin exclue, avec une conversion en indices d'échantillons arrondie vers le bas au début et vers le haut à la fin.

`JobService` expose `submit`, `cancel`, `status` et `shutdown`, avec les états `queued`, `running`, `succeeded`, `failed` et `cancelled`. Une tâche interrompue par un arrêt devient `failed` avec le code `interrupted`, affichée `Interrupted` sans créer un second modèle d'état.

La base initiale contient `schema_migrations` et `settings`. Le catalogue des morceaux appartient au plan 03 ; chaque fonctionnalité ultérieure apporte sa propre migration numérotée.

## Ce que le socle ne fait pas

Aucune lecture audio, aucune écriture de métadonnées, aucun accès FFmpeg, aucune analyse. Les données affichées dans la fenêtre sont fictives et ne proviennent d'aucun fichier de l'utilisateur.
