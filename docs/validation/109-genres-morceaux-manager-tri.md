# Validation 109 — Genres des morceaux, manager et tri

## Préparation documentaire du 7 octobre 2026

Le [plan 109](../../Plans%20d'ex%C3%A9cution/109-genres-morceaux-manager-tri.md) prépare deux lots : association des genres issus des dossiers, puis implémentation complète du manager, du pinceau et des filtres. Le brief 108 est conservé comme historique et renvoie au plan pour les décisions finales.

Les sources consultées comprennent `PLAN.md`, `PLANS.md`, les plans 10, 106/107, le brief 108, la couche SQLite et ses migrations, `TrackListModel`, les points de sélection/lecture de `TrackListView.qml`, les profils artistes, le script de genres d'artistes et les tests de migration/modèle/UI pertinents. Le graphe code-review-graph a servi à cibler la lecture ; les contrats ont été vérifiés dans les sources. La base réelle n'a pas été ouverte pour cette préparation.

Constats : migration 021 libre à la révision de référence `a1da3f6` ; connexion SQLite par thread ; provenance `genre_added` disponible pour le retrait ciblé des ajouts de 107 ; anciennes options de propositions en attente, de passage automatique au suivant et de puces par ligne remplacées par les dernières décisions utilisateur. Les chiffres personnels du brief sont des données historiques, pas un nouvel inventaire.

Contrôles documentaires effectués : décodage UTF-8 des cinq documents modifiés sans caractère de remplacement ; résolution de 71 liens Markdown locaux ; présence de 17 chemins existants cités comme points d'intégration ; présence unique des quatre sections de suivi ; relecture de l'ordre des deux lots et des décisions finales ; somme des effectifs historiques égale à 2 813 et calcul de 242 sans genre, sous réserve de données inchangées. `git diff --check` passe. Les modifications sont exclusivement documentaires. Les chemins de futurs modules/tests sont explicitement présentés comme à créer. La relecture du diff a permis de corriger la position de l'addendum après le titre principal de PLAN.md ; les fins de ligne des fichiers existants ont été conservées.

État Git initial observé : `main` sur `a1da3f6`, synchronisé avec `origin/main` après fetch. `.agents/`, `.codex/` et `skills-lock.json` sont laissés non suivis. Le commit documentaire indexe uniquement le plan, ce rapport et les références documentaires actualisées ; la preuve de push figure dans le compte rendu de tâche.

## Limites de cette préparation

Aucun code applicatif ni test nouveau créé. Aucun test pytest, lancement applicatif, migration, écriture dans la base réelle, classement de morceau, suppression d'ancien tag artiste ou manipulation de fichier audio réalisé. Aucun build Windows ni validation du paquet. Les maquettes et leur revue restent un prérequis d'exécution, sans accord visuel inventé.

## À renseigner pendant l'exécution

Consigner pour chaque sous-jalon les commandes réellement exécutées, les versions et l'environnement, les résultats de tests, les erreurs préexistantes comparées, les mesures sur fixtures et copie, les sauvegardes vérifiées et identifiants d'opérations (détails personnels dans les rapports locaux ignorés par Git). Distinguer aperçu d'amorçage, application sur copie et application réelle. Consigner séparément captures hors écran, recette manuelle depuis les sources et revue interactive de l'utilisateur. Ne jamais remplir cette section à partir de résultats seulement attendus.


## Exécution du prérequis visuel 109.0 — 7 octobre 2026

Création de trois composants QML isolés sous `src/mtee/qml/prototypes/genres/`, du lanceur `scripts/review_genres_109.py`, de 16 captures synthétiques et du [dossier de revue](../ux/review-109-genres.md). Aucun branchement à la base, aux migrations ou au lecteur de production. Le code métier de 109.1 et les lots réels ne sont pas commencés. La revue utilisateur reste en attente conformément au plan.

Environnement observé : Windows, Python 3.12.14, PySide6 6.9.3 ; dimensions 1440 × 900 et 960 × 720 pour narrow. Commande `uv run python scripts/review_genres_109.py --capture-dir docs/ux/genres-109-2026-10-07` : code 0, 16 PNG générés, aucun avertissement QML. Captures examinées visuellement ; correction du rendu des contrôles, du parent de création et de la scène de rétention.

`uv run ruff check scripts/review_genres_109.py` et `uv run ruff format --check scripts/review_genres_109.py` : passent après formatage. Sonde locale ignorée par Git `.local/validation/109/probe.py` : 10 contrôles du prototype réussis (compteur, filtre, coche, critère, annulation, sélection multiple, lot, annulation de lot, retour manager et split), lecteur fictif inchangé après affectations, aucun avertissement QML. La première tentative de sonde utilisait un contexte QML sans les identifiants du composant ; corrigée pour utiliser son contexte propre puis relancée avec succès. Ces sondes ne vérifient pas les futurs services de persistance.

Recette manuelle native de MTEE, accord utilisateur, application sur copie ou base réelle, nettoyage 107 et packaging : non effectués. Aucun fichier audio ni base personnelle ouvert ou modifié. Aucun pytest applicatif requis pour ce prototype isolé ; la capture de toutes les scènes vérifie leur chargement effectif depuis les sources. Git diff/check et publication : preuve dans le compte rendu de livraison.


## Socle et lot réel 109.1–109.2 — 8 octobre 2026

Accord des maquettes reçu : « Je valide ces maquettes, go ». Le tableau réel a été soumis à revue ; l’utilisateur a demandé d’exclure les dossiers « hard house - nu trance - bouncy stuff » et « techno, trance ». Cette correction est intégrée au mapping et vérifiée sur copie avant application réelle. Taxonomie inchangée, aucun fichier audio touché.

Livré : migration 021 et initialisation unique ; 48 UUID stables, alias et méta-familles ; liens locaux sans ancêtre redondant ; transactions, révisions, journal et annulation ciblée ; script seed_track_genres.py avec aperçu sans écriture, --copy-to cohérent, --apply-plan et --undo-operation. Le plan est lié à sa base et son état ; un aperçu périmé, modifié ou provenant d’une autre base est refusé. Une correction manuelle vide reste durable. Les destinations à l’intérieur des collections sont refusées.

Applications sur copies : sauvegardes rouvertes et quick_check vérifié ; redémarrage, provenance, idempotence et annulation vérifiés. Application réelle : après sauvegarde unique et fermeture des outils confirmée par l’utilisateur, 2 456 morceaux affectés, 2 472 liens, 8 hybrides, 358 présents sans genre et 2 absents ignorés. Les deux dossiers exclus n’ont aucun lien. Le contrôle après fermeture relève schema 21, quick_check OK et foreign_key_check vide. Locations, analyses et revues artistes sont identiques à la sauvegarde. Le reçu et le chemin de sauvegarde personnels sont uniquement dans .local/validation/109.

Contrôles : 59 tests ciblés passent (domaines, mapping, service, repository, amorçage, migrations, playback repository, library repository, TrackListModel, affichage local et Info). Ruff passe, Pyright des nouveaux modules : zéro erreur. Windows / Python 3.12.14 / Qt 6.9.3. Lecture groupée des affectations de 2 814 morceaux : 29,63 ms ; dossier de 477 morceaux avec décoration : 38,95 ms, relecture conforme. Mesures exploratoires, pas une recette finale de performance. Smoke depuis les sources sur copie : code 0, sans avertissement QML.

Limite native : certains tests Info existants ont émis des exceptions dans le lecteur mpv tout en passant. Le test nouvellement ajouté utilise le backend indisponible pour isoler l’affichage. Comparaison de deux tests Info sur HEAD 746ab76 dans un worktree avec son propre environnement : 2 passent, exception non reproduite ; l’origine reste indéterminée. Aucun changement audio n’est fait pour contourner ce constat. Recette interactive native complète non effectuée, aucun packaging. Les jalons 109.3–109.7 restent ouverts.

## Manager, pinceau, filtres et retrait 109.3–109.6 — 8 octobre 2026

Les mentions d'attente ci-dessus décrivent les sous-jalons précédents. L'implémentation livre le manager des genres, alias, méta-familles et tags, la création rapide avec parent, les favoris/récents, les affectations par case et lot, les états Saving/erreur/reprise, l'annulation ciblée, les filtres versionnés et leur sauvegarde par vue. Les opérations passent par des tâches de fond et des snapshots Qt. L'affichage Info utilise les affectations groupées déjà chargées. Les playlists décorent leurs morceaux par une lecture groupée. Aucun accès système ni SQLite ajouté aux composants QML.

La suppression ordinaire refuse les définitions utilisées. La suppression forcée est uniquement disponible dans Settings, exige le chemin saisi, crée une sauvegarde cohérente vérifiée et journalise tout le sous-arbre et ses liens. La récupération est ciblée ; les révisions et les opérations inverses empêchent l'écrasement d'une modification ultérieure. Un test déterministe couvre plusieurs transactions partageant exactement le même timestamp. Les tags locaux sont indépendants des genres ; les méta-familles sont héritées.

Les filtres combinent inclusions All/Any et exclusions, avec tags, méta-familles et critères de genre absent/famille seule/sans sous-genre/sans pinceau. Les ancêtres du contexte de dossier restent protégés. Une référence supprimée donne une erreur explicite. Les lignes sortant du filtre après une affectation restent atténuées jusqu'au recalcul ; la file de lecture existante reste conservée. Deux vues partagent les résultats sauvegardés, mais leurs pinceaux et filtres sont distincts.

### Retrait historique : copie puis application réelle

La sauvegarde précédant 107 a été retrouvée. Les marqueurs seuls ne suffisent pas : la preuve compare tous les champs hors tags et dossier d'import au témoin, vérifie exactement les tags manuels et ajoutés, les sources et la fenêtre `saved_at` de l'import. Le champ de validation inchangé est comparé au témoin. Treize profils sans preuve suffisante restent signalés et préservés.

Préparation, application sur copie et annulation ciblée : résultat antérieur retrouvé exactement. Après fermeture confirmée des outils écrivant la base et sauvegarde unique rouverte, l'application réelle retire **2 528 ajouts sur 1 590 artistes** ; **13 cas ambigus restent inchangés**. Les reçus, identifiants d'opération, témoin et chemins de sauvegardes personnels sont uniquement dans `.local/validation/109/cleanup-real/`. Réouverture : quick_check OK, foreign_key_check vide. Comparaison à la sauvegarde : locations, analyses, liens de genres des morceaux et tags locaux identiques ; décisions, rôles, artistes masqués, notes, identités et validation inchangés. Aucun fichier audio écrit.

### Contrôles depuis les sources

Windows, Python 3.12.14, PySide6/Qt 6.9.3. Commandes réellement exécutées, avec `uv run python -m pytest` :

- Lot métier et régressions proches : **118 passent** sur `test_genres`, `test_genre_seed_service`, `test_genre_filters`, `test_folder_genres`, `test_artist_profile`, `test_track_list_model`, `test_genre_repository`, `test_genre_operations`, `test_genre_seed`, `test_artist_genre_cleanup`, `test_database_migrations`, `test_playback_repository`, `test_library_repository`, `test_playlist_identity`, `test_playlist_reorder_98`, `test_playlist_header_data` et `test_playlists_repository`.
- Après la correction d'ordre du journal : **23 passent** sur les repositories/seed/cleanup/filtres ciblés ; le nouveau contrôle des identifiants protégés porte ensuite le fichier de filtres à **3 tests passants**.
- `tests/ui/test_genre_workflow_ui.py` : **7 passent**, puis scénario glisser-déposer également exécuté isolément. Interactions réelles QTest avec les composants de production, base synthétique et lecteur simulé : case indépendante, annulation, rétention/recalcul, référence invalide, création persistante et manager, deux vues, file conservée, échec d'écriture/reprise, accès Advanced dans Settings, déplacement et annulation. `test_track_genres_readonly_ui.py` : **1 passe** isolément.
- Captures synthétiques du manager et de la palette à 960 × 720 examinées visuellement ; contrôles lisibles, liste virtualisée et formulaire de largeur stable. Ces captures locales ne représentent pas la collection personnelle et ne sont pas une recette manuelle native complète.

Une suite élargie Workspace/échanges de playlists relève **4 échecs et 36 succès**. Comparaison sur la révision antérieure `746ab76` dans un worktree et environnement distincts : **les mêmes 4 échecs**, avec 16 succès dans le sous-ensemble correspondant. Un test Workspace suppose un chargement immédiat malgré les tâches asynchrones ; trois tests d'échange utilisent un contexte simulé dépourvu de `report_items`. Ces tests ne sont pas modifiés pour faire disparaître les échecs. Aucun succès de la suite entière annoncé.

### Mesures exploratoires

Fixture de 2 800 morceaux, vue de 830, lecteur simulé en lecture ; chronométrage local avec les tâches de fond et le rendu depuis les sources. Les valeurs incluent l'attente de stabilisation de la sonde et ne définissent pas une garantie de temps maximal.

| Action | Mesure |
|---|---:|
| Affectations groupées de 2 800 morceaux | 28,69 ms |
| Lecture/décoration du dossier de 830 morceaux | 101,07 ms |
| Catalogue et compteurs | 5,43 ms |
| Chargement complet de la vue 830 | 2 011 ms |
| Affectation d'un lot de 830 et actualisation | 2 457 ms |
| Annulation de ce lot et actualisation | 2 272 ms |
| Filtrage de la vue 830 | 2 408 ms |
| Défilement, rendu et attente de 50 ms | 482 ms |
| Quatre touches de recherche et attente de 50 ms | 626 ms |

Quinze cases sont rendues avant et après défilement : aucun composant par morceau hors écran. La file simulée reste identique après affectation, annulation et filtrage. Sur copie cohérente de la base réelle après retrait, lecture de 2 814 affectations : 44,22 ms ; dossier de 477 morceaux : 36,96 ms ; catalogue : 3,60 ms. Rapports personnels et mesures détaillées restent ignorés par Git.

### Limites de livraison

Le [guide d'usage](../usage/genres-locaux.md) décrit les contrôles et scripts d'aperçu, application et récupération. Les composants et ressources sont inclus par les règles récursives existantes de packaging, inspectées sans lancer de build. La recette interactive native complète, l'écoute avec le lecteur réel et la validation d'un paquet Windows ne sont pas annoncées comme faites. Le jalon 109.7 reste explicitement partiel pour cette recette. La publication Git est vérifiée et rapportée dans le compte rendu de tâche.

Contrôles finaux : **119 tests métier et régressions proches passent en 5,02 s**, après correction de l'ordre du journal et ajout du test de contexte protégé. Ruff check et format des 17 fichiers Python modifiés passent ; Pyright ciblé sur les dix modules de domaine, modèle, persistance et services : zéro erreur, avertissement ou information. Le smoke final depuis les sources sur copie post-retrait quitte avec code 1 sans diagnostic avec le backend audio natif, deux fois ; le même lancement passe avec code 0 et sans avertissement QML après substitution du backend simulé. L'origine de cet arrêt natif n'est pas déterminée et aucune validation audio native n'en est déduite. Les interactions QTest sont exécutées avec la plateforme hors écran de la configuration pytest.
