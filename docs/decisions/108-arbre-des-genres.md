# 108 — Genres, genre manager et workflow de tri : brief complet pour l'ExecPlan

> **Référence historique remplacée pour l'exécution le 7 octobre 2026 :** suivre le [plan 109](../../Plans%20d'ex%C3%A9cution/109-genres-morceaux-manager-tri.md), qui intègre les réponses finales de l'utilisateur. Le texte ci-dessous conserve l'ancien brief et n'est pas à implémenter littéralement.
>
> Décisions finales : amorçage précis vérifié puis appliqué en un lot ; House seul valide ; libellés avec famille ; hybrides conservés ; manager indispensable et création rapide ; pinceau sans lecture automatique ni suivi d'écoute ; puces par ligne écartées ; retrait du dernier sous-genre ramenant à la famille ; filtres ET/OU/exclusion complets avec contexte de famille protégé ; Ctrl+Z et sauvegardes ; suppression forcée depuis les paramètres. L'étude avancée des impacts de reparentage est reportée. Les chiffres et constats techniques historiques ci-dessous doivent être confrontés aux corrections et prérequis du plan 109.

Document de cadrage du 7 octobre 2026, écrit pour qu'un lecteur sans accès à la conversation puisse rédiger l'ExecPlan (numéro suggéré : 109). Il rassemble le contexte du dépôt, l'état de la base réelle, les décisions de l'utilisateur (explicites, datées du 7 octobre), les points techniques à trancher et les pièges rencontrés. Les décisions de l'utilisateur sont fermes ; ce qui est marqué « à trancher » relève d'un choix technique ordinaire (le décider et le documenter) ou d'une validation à demander.

Rappels de gouvernance (`AGENTS.md`, `PLANS.md`) : interface en anglais, documentation en français ; Python 3.12 / PySide6 / QML ; QML passe par des modèles Qt et des services Python, jamais par le système de fichiers ; les accès longs quittent le thread graphique ; tests adaptés, vérification manuelle depuis les sources, ExecPlan mis à jour, commit détaillé puis push vers `origin/main` à chaque étape ; **pas de `scripts/build_windows.ps1` ni de `smoke_packaged.ps1`** sauf demande explicite de packaging ; opérations d'écriture testées sur des copies, sauvegarde avant toute migration ou écriture sur la base réelle ; ne versionner ni collection personnelle, ni base locale. `PLAN.md` impose des maquettes avant le code fonctionnel et une revue du vocabulaire des tags : **le vocabulaire (arbre ci-dessous) est validé par l'utilisateur** ; pour l'interface de tri, l'utilisateur demande explicitement d'implémenter plusieurs variantes de workflow pour les comparer à l'usage (voir « Workflows »), ce qui tient lieu de maquette pour ces variantes.

## Règles absolues de l'utilisateur

1. **Ne toucher à aucun fichier ni dossier de `foliarn/`** (la collection, `C:\Users\flori\Desktop\foliarn`). Aucun renommage, déplacement, écriture de tag, création ou suppression. Les dossiers ne servent que de point de départ en lecture. Tous les mots « retirer », « renommer », « séparer » de ce document portent sur la **taxonomie** qu'on crée dans MTEE, jamais sur la collection.
2. Les tags personnalisés (Banger, Calm, Euphoric…) **ne vont jamais dans les métadonnées des fichiers** : ils vivent dans la base de MTEE uniquement. Les genres de la taxonomie non plus ne sont pas écrits dans le champ Genre des fichiers sans demande séparée et explicite.
3. L'utilisateur ne connaît pas par cœur tous les artistes et morceaux : le workflow doit lui permettre de **jouer un morceau là où il le trie** (aujourd'hui il doit chercher l'artiste ou le titre pour l'écouter).
4. On travaille **les morceaux d'abord**. Le tri par artiste et la règle d'attribution des remix aux artistes sont **reportés** ; les puces de genre posées sur les artistes par le plan 107 seront retirées une fois les genres de morceaux en place (voir « Reprise du plan 107 »).
5. Les liens Spotify/SoundCloud sont hors sujet ; l'utilisateur s'en occupera plus tard.

## État du dépôt et de la base (au 7 octobre 2026)

Commits récents sur `main` (tous poussés) : `e1f5344` (travaux en cours : tag editor, déplacement par glisser-déposer, tâches), `bfc50a7` (plan 106 : types, dossiers, filtres, masqués, profil d'artiste), `dc75df7` (plan 107 : genres depuis les dossiers sur les artistes), `473bacd` et `22a0b07` (premières versions de ce dossier). Arbre Git : `.agents/`, `.codex/` et `skills-lock.json` sont de la configuration d'outils non versionnée, à laisser de côté.

Base réelle : `%APPDATA%\MTEE\MTEE\mtee.sqlite3` (SQLite, WAL). Schéma applicatif : migrations `src/mtee/persistence/migrations/001…020` (la 010 n'existe pas, c'est voulu) ; **la migration 020 (`020_artist_enrichment.sql`) n'est appliquée à la base réelle qu'au prochain démarrage de MTEE** (la table existait déjà, créée par un outil externe) ; la prochaine migration libre est **021**. Une sauvegarde automatique par version est faite par `Database.migrate()`. Tests de migration : `tests/integration/test_database_migrations.py` et `test_playback_repository.py` listent les versions et sont à mettre à jour à chaque migration ajoutée.

Tables utiles : `library_roots` (racines : `foliarn` avec 2 813 morceaux, `mixs` avec 12), `root_tracks` (`track_id`, `relative_path`, `present`, `parent_relative_path`), `track_locations` (chemin, `metadata_json` avec bpm, title, artist, genre, key…), `track_analysis` (`bpm`, `bpm_user_edited`, `key_*`, 2 812 lignes ; le BPM d'analyse de MTEE), `track_artist_credits` (role `artist` ou `remixer`, `confirmed`), `track_artist_review`, `artists`, `artist_enrichment_reviews` (rôles, tags, décision, liens ; contient les tags `idgaf` et, depuis le plan 107, des puces de genre).

Code à connaître : `src/mtee/qml/components/TrackListView.qml` (liste de morceaux réutilisée par dossiers, playlists, pages d'artiste ; lecture au clic, sélection, colonnes, tri ; très gros fichier), `src/mtee/models/workspace_model.py` (onglets, navigation), modèles de liste de morceaux (`trackModelForTab`), `src/mtee/qml/Mtee/WheelScrollHandler.qml` (molette avec `speed`), `FilterChip.qml` et `ArtistProfileDialog.qml` (plan 106), `ArtistManagerPane.qml` / `ArtistsView.qml` (sidebar et liste des artistes), `src/mtee/domain/artist_profile.py`, `src/mtee/domain/folder_genres.py` et `src/mtee/services/folder_genre_service.py` (plan 107 : lecture des dossiers, formatage des noms, marqueurs de remix), `src/mtee/persistence/artist_repository.py` (`set_folder_genres`, `save_artist_profile`), `src/mtee/services/jobs.py` (`JobService`, tâches annulables), `scripts/genres_from_folders.py`, `scripts/clean_orphan_artists.py`. Une recherche globale existe déjà ; le moteur de critères du plan 10 (AND/OR/NOT sur tags, champs typés) n'est **pas** implémenté : le filtre « avec/sans genre » des listes en sera la première brique, à concevoir pour s'y intégrer. Le plan 10 (`Plans d'exécution/10-tags-recherche-playlists.md`) prévoit déjà des tags locaux à identifiant stable, distincts des tags de fichier et des analyses : s'y aligner.

Environnement de test : `uv run python -m pytest …` avec `QT_QPA_PLATFORM=offscreen` ; les tests UI démarrent l'application réelle sur une base temporaire (`_build_runtime`, voir `tests/ui/test_artist_profile_ui.py` pour un modèle). Échecs **existants avant ces travaux, non liés** : nombreux tests de `tests/ui` (browser_navigation, convert_view, playlists_ui, metadata_editor, player_views, playback_queue_ui, track_drag_98, incremental_scan_and_scroll, analysis_ui, plantage dans fullscreen_player_100) et côté unitaire `test_conversion_queue` (2), `test_icon_provider`, `test_workspace_model` (navigation). Pour comparer avec HEAD, utiliser un `git worktree` et `uv run` dedans (le `.venv` principal est en mode éditable et chargerait le code du dépôt principal). Pas de `git stash`. Fichiers souvent en CRLF dans la copie de travail : préserver les fins de ligne en éditant. Les scripts d'édition en lot passent par un fichier (les heredocs imbriqués de l'outil shell sont fragiles).

## Arbre de genres validé

Sous-genres rattachés à **une seule famille** ; le même libellé peut exister sous plusieurs familles (Minimal sous House, Techno et Drum & Bass) comme **nœuds distincts**, affichés avec leur famille. Libellés d'interface en anglais.

- **House** : Tech, Bass, Minimal, Deep, Disco, French
- **UK Garage** : Speed Garage, 2-Step, Bassline
- **Drum & Bass** : Jump Up, Neuro, Liquid, Drumstep, Rollers, Jungle, Minimal, Dancefloor, 4x4
- **Dubstep** : Deep, Tearout, Riddim, Brostep, Trap, UK Dubstep
- **Techno** : Minimal, Hardgroove, Hard House, Bouncy Techno (alias : Nu Trance), Trance
- **Hard Dance** : Hardstyle, Rawstyle, Uptempo, Hard Techno
- Familles sans sous-genre pour l'instant : **Dance, Breaks, Baile, Rap, Future Bass, Pop, Rock, Jazz, Classical**. L'utilisateur veut « tous les genres possibles » : le manager doit permettre d'en ajouter librement.
- Règle de nommage : « si le son est Speed Garage, il est UKG, évidemment » : un sous-genre implique sa famille.

**Méta-familles** (regroupements transversaux, à part de l'arbre ; « Commercial » est abandonné) : **Bass Music** (UK Garage, Dubstep, Drum & Bass, Bass House, Baile), **Hard** (Hard Dance, Hard House, Hardgroove), **Club** (House, Techno, UK Garage). Une famille ou un sous-genre peut appartenir à plusieurs méta-familles ; un morceau en hérite par ses genres ; une méta-famille ne s'affecte jamais directement à un morceau. Liste modifiable dans le manager.

## Modèle de données voulu

- **Genres** : arbre (famille → sous-genre, structure assez générale pour plus de deux niveaux), identifiants stables (UUID) distincts des libellés pour que le renommage garde les affectations, ordre d'affichage, archivage, **alias** (anciens noms de dossiers, « Nu Trance »).
- **Méta-familles** : table et liaison plusieurs-à-plusieurs avec les genres.
- **Genres d'un morceau : un ensemble sans ordre ni genre principal.** L'utilisateur a **supprimé la notion de genre principal** : tous les genres d'un morceau ont le même poids, y compris les hybrides (Jump Up + Minimal, Speed Garage + Hard House). Un morceau est « classé » dès qu'il a au moins un genre ; sinon il est « À classer ». Affecter un sous-genre rend sa famille implicite : ne stocker que le nœud le plus précis, la famille seule signifiant « pas encore précisé » (et servant à un filtre, voir plus bas). Les familles d'un morceau se déduisent des ancêtres.
- **Tags personnalisés** : table de définitions (libellé, couleur éventuelle) et affectations par morceau, créés à la volée, **dans la base uniquement**, jamais écrits dans un fichier (aucune voie du `MetadataWriter` ne doit les lire).
- Provenance et historique : chaque affectation garde sa provenance (`folder` proposé, `manual`) ; un amorçage depuis les dossiers est une **proposition non confirmée** tant que l'utilisateur ne l'a pas validée par lot ; une réanalyse ou un nouvel amorçage n'écrase jamais une décision manuelle. Annulation (undo) de la dernière action de tri.
- Genre d'un artiste : **agrégat calculé** plus tard (genres et nombre de morceaux), pas stocké à la main. Hors périmètre pour l'instant.
- Les morceaux sont identifiés par `track_id` (UUID) ; les affectations survivent à un déplacement de fichier ; une suppression de fichier n'efface pas en cascade l'historique (règle du plan 10).

## Amorçage depuis les dossiers de `foliarn` (lecture seule)

Source : `root_tracks.relative_path` de la racine `foliarn`, 2 813 morceaux. Effectifs de morceaux entre parenthèses. Un morceau n'est que dans un dossier ; un second genre se choisit à la main. Les dossiers retirés par l'utilisateur ne sont **pas des genres** ; leurs morceaux gardent seulement la famille du dossier parent ou du préfixe.

| Dossier (réel) | Genre(s) proposés |
|---|---|
| d&b / jump up (478) | Drum & Bass › Jump Up |
| d&b / minimal - dark (92) | Drum & Bass › Minimal (« dark » abandonné) |
| d&b / washed up (72) | Drum & Bass (famille seule) |
| d&b / liquid (chill) (48) | Drum & Bass › Liquid |
| d&b / le reste (…) (47) | Drum & Bass (famille seule) |
| d&b / neurofunk (je crois) (42) | Drum & Bass › Neuro |
| d&b / dancefloor (30) | Drum & Bass › Dancefloor |
| d&b / 4x4 (12) | Drum & Bass › 4x4 |
| d&b / drumstep (6) | Drum & Bass › Drumstep |
| ukg - speed garage & bangers (262) | UK Garage › Speed Garage |
| ukg - chill (195) | UK Garage (« pas un genre », retiré) |
| ukg - slow bangers (103) | UK Garage (« pas un genre », retiré) |
| ukg - 2step (85) | UK Garage › 2-Step |
| ukg - bassline (37) | UK Garage › Bassline |
| dubstep 140 (206) | Dubstep › UK Dubstep |
| dubstep (le reste) (49), dubstep cool (31) | Dubstep (famille seule) |
| nu trap (24) | Dubstep › Trap |
| house (202) | House (famille seule) |
| tech house (25) / bass house (14) | House › Tech / House › Bass |
| hard house - nu trance - bouncy stuff (77) | Techno › Hard House **et** Techno › Bouncy Techno |
| hardgroove (84) | Techno › Hardgroove |
| techno min cool (36) | Techno › Minimal |
| techno, trance (39) | Techno **et** Techno › Trance |
| hard techno (88) | Hard Dance › Hard Techno |
| hard,rawstyle (8) | Hard Dance › Hardstyle, Rawstyle **et** Uptempo |
| breaks - jungle (75) | règle BPM ci-dessous |
| baile (25), rap (16), dance (54), pop (5) | familles Baile, Rap, Dance, Pop |
| future (5) | famille Future Bass |
| chill&atmospheric (23), old school (16) | À classer (retirés) |
| zzZ (97), Artists (75), dj blc (30) | À classer (dossiers qui ne sont pas des genres) |

Au départ **241 morceaux sont À classer** (39 par les retraits, 202 dans les dossiers qui ne sont pas des genres). Les parenthèses des noms de dossiers sont retirées (« Dance (Electronica - Kaytra - French Touch) » devient Dance). Les sous-genres sans dossier source (Deep, Disco, French, Tearout, Riddim, Brostep, Rollers…) n'ont pas d'amorçage : ils se posent à la main. Ces correspondances sont à tenir dans une table de configuration versionnée, pas dans le code.

**Règle `breaks - jungle`** : le BPM de l'**analyse de MTEE** (`track_analysis.bpm`, pas le tag) décide. BPM inférieur à 90 : le BPM est noté à moitié, on le **double** avant d'appliquer la règle (87 → 174). Ensuite **160 BPM inclus ou plus = Jungle** (Drum & Bass › Jungle), moins de 160 = **Breaks** (famille Breaks). Pas d'analyse disponible : À classer. Contrôle sur la collection actuelle (avant ces deux ajustements) : 74 des 75 morceaux ont une analyse ; avec le seuil « strictement au-dessus de 160 » on obtenait 55 Jungle et 19 Breaks, dont 5 morceaux à exactement 160 qui passent à Jungle avec la règle « 160 inclus » ; le seul morceau sous 90 dans le tag (« Inside The Rider », tag 87) est déjà à 174 dans l'analyse ; un morceau (« The Caracal Project… ») n'a pas d'analyse. Ces chiffres sont à recalculer à l'implémentation et à consigner.

## Genre manager

Une page (ou vue) dédiée, conçue en **tables** : une table (colonne ou carte) par famille, listant ses sous-genres ; chaque sous-genre se **glisse-dépose** d'une table à l'autre pour le re-parenter (par exemple déplacer Hard House de Techno vers House). Mêmes principes pour les méta-familles (table des méta-familles, chaque genre pouvant être déposé dans une ou plusieurs) et pour les tags. Actions : créer une famille, un sous-genre, une méta-famille, un tag ; renommer ; déplacer par glisser-déposer ; archiver/supprimer ; gérer les alias. Chaque table affiche le nombre de morceaux. Le glisser-déposer de QML passe par un modèle Qt et un service Python (aucun accès direct à la base depuis QML) ; un déplacement garde l'identifiant, donc les affectations.

**Suppression** : refusée tant que le genre a des sous-genres ou des morceaux affectés, avec le nombre de morceaux touchés et la liste bloquante ; une **suppression forcée** est possible (l'utilisateur la demande explicitement) ; les morceaux concernés repassent « À classer » (sinon ils gardent leurs autres genres) ; **pas de fusion**. Prévoir l'annulation (ou l'archivage) pour qu'une suppression forcée reste récupérable.

Création **à la volée** : depuis n'importe quel écran de tri, taper un nom absent propose « Créer … » (famille ou sous-genre sous la famille courante) sans quitter le workflow.

## Workflows de tri (plusieurs variantes à implémenter pour comparer)

L'utilisateur demande un workflow **hyper simple, intuitif et rapide**, pour le **tri par lot** (page ou mode dédié) et le **tri sélectif** (par page, par sélection). Il veut implémenter **plusieurs modes pour tester le meilleur à l'usage** ; les écrire de façon que les modes partagent le même modèle de genres et se basculent dans l'interface.

**Mode « tagging » des listes** : disponible sur les **playlists et les dossiers uniquement** (pas les pages d'artiste ni les résultats de recherche). Un bouton de bascule transforme la page classique en mode tagging ; chaque morceau reçoit une **case à cocher** (état distinct de la sélection actuelle, qui change quand on clique une ligne pour jouer ; la case survit à la lecture et au défilement). Un clic sur la ligne continue de jouer le morceau.

**Variante 1 — Pinceau (idée de l'utilisateur)** : on choisit un genre « pinceau » (ex. Deep House) ; la case de chaque ligne signifie « ce morceau a ce genre ». **Cocher applique tout de suite (écriture en direct) ; décocher retire** ; annulation disponible. Filtre de la liste par genre, puces « avec » / « sans » combinables (l'utilisateur a parlé de ET/XOR ; interprétation retenue : ET plus « sauf », c'est-à-dire avec / sans ; un XOR strict entre deux genres n'est pas prévu sauf demande). Cas d'usage : dans la liste `house`, choisir Deep, cocher les sons Deep, afficher seulement les Deep (révision) ou tout sauf les Deep (avancer sur le reste).

**Variante 2 — Puces par ligne** : chaque ligne affiche les **sous-genres de la famille du dossier** sous forme de puces à activer (dossier House : Tech, Bass, Minimal, Deep, Disco, French). En une écoute on fixe tous les genres d'un son, hybrides compris, sans le réécouter à une autre passe. Un bouton bascule entre pinceau et puces par ligne. Le temps d'écoute coûte plus cher que les clics, d'où l'intérêt des deux.

**Éléments communs** :
- **Palette de saisie rapide** : un champ qui filtre l'arbre en tapant (`spe` → Speed Garage), Entrée applique le genre aux morceaux ciblés (cochés ou sélectionnés), Maj+Entrée ajoute sans remplacer, un nom absent propose « Créer … » ; derniers genres utilisés en tête, raccourcis 1 à 9 ; raccourci clavier pour cocher le morceau en cours de lecture et passer au suivant non classé.
- **Filtre « famille seule »** (pas encore de sous-genre) : c'est l'outil qui fait rétrécir la liste à mesure qu'on précise. Un filtre « À classer » (aucun genre) et un filtre « proposition non confirmée » complètent. Les filtres tiennent compte de la hiérarchie : filtrer House inclut ses sous-genres.
- **Éviter que les lignes disparaissent sous la souris** : en vue « sans ce genre », une ligne qu'on vient de cocher reste visible (grisée) jusqu'à une action « Masquer les faits » ; sinon la liste se décale pendant le tri.
- **Confirmation de l'amorçage par lot** (par dossier ou par proposition) en une action.
- **Tri sélectif** : le même panneau/palette depuis le clic droit d'une sélection de morceaux et le panneau Info d'un morceau ; la sélection multiple habituelle (clic, Maj, Ctrl) puis un genre classe tout le lot. Afficher le nombre de morceaux touchés et offrir l'annulation.
- Informations pour aider à classer sans connaître le morceau : colonne BPM (analyse), proposition du dossier d'origine, et les genres déjà posés sur d'autres morceaux de l'artiste ; le tri par BPM aide à séparer, par exemple, les styles de Dubstep ou de Drum & Bass.
- Lecture : le tri passe par le lecteur existant ; ne pas casser le comportement de lecture, de file et d'îlot.

Contraintes de performance : listes jusqu'à environ 830 morceaux dans un dossier (Drum & Bass), collection de 2 800 morceaux ; l'état des genres de chaque ligne vient du modèle Qt (rôles), jamais d'une recherche côté QML ; les écritures partent en arrière-plan avec mise à jour optimiste de l'interface, annulation et gestion d'erreur.

## Reprise du plan 107 (puces de genre sur les artistes)

Le plan 107 a posé 1 603 puces de genre sur des artistes d'après les dossiers (`record_json.genre_added` et `genre_sources` dans `artist_enrichment_reviews`, sauvegarde `mtee.sqlite3.before-folder-genres-20261007T125907Z.bak`). Décision : **les retirer une fois les genres de morceaux en place** (sauvegarde préalable, réversible). Le script et la règle des remixeurs du plan 107 (`domain/folder_genres.py`) resteront utiles plus tard pour agréger des genres de morceaux vers les artistes (remix : seul le remixeur ; remixeur introuvable : personne ; 52 remix non résolus listés dans `.local/validation/107/unresolved-remixes.csv`, ignoré par Git). À ce stade les genres vivent sur les morceaux et ce travail est hors périmètre.

Constat lié : le marqueur « (X Remix) » a disparu du titre de quelques morceaux (6 repérés sur la collection actuelle) ; il se retrouve parfois dans le titre d'origine ou le nom de fichier. Au niveau des morceaux le problème disparaît, un remix étant un morceau dont le genre est celui de son dossier.

## Jalons suggérés (à ajuster par l'auteur du plan)

1. Migration 021 (genres, alias, méta-familles, affectations de morceaux, tags), domaine, dépôt, service, jeu de tests ; table de configuration de l'arbre validé et script d'amorçage en lecture seule des dossiers avec rapport (modèle : `scripts/genres_from_folders.py`), application sur une copie puis sur la base réelle après sauvegarde et accord.
2. Genre manager (modèle Qt, vue en tables, glisser-déposer, création, renommage, suppression refusée/forcée, méta-familles, tags).
3. Palette de saisie et tri sélectif (clic droit, panneau Info) avec annulation.
4. Mode tagging des dossiers et playlists : pinceau, puis puces par ligne, filtres avec/sans, famille seule, À classer.
5. Retrait des puces d'artiste du plan 107, documentation, rapport de validation.

À chaque jalon : tests unitaires et UI sur base temporaire, recette depuis les sources avec captures hors écran sur une **copie** de la base réelle, mise à jour de l'ExecPlan, commit détaillé, push. Recette interactive de l'utilisateur à signaler comme non faite tant qu'elle ne l'est pas.

## Pièges et leçons déjà rencontrés

- Écrire dans la base réelle pendant que MTEE ou le serveur de revue tournent est possible (WAL) mais l'application garde un état périmé : demander de la relancer.
- `Database.connection()` partage une connexion ; les écritures passent par `Database.transaction()`.
- Le catalogue des artistes ne compte que les crédits confirmés sur des fichiers présents ; les anciens orphelins (artistes sans morceau) ont été supprimés le 7 octobre (`scripts/clean_orphan_artists.py`, sauvegarde `…before-orphan-cleanup-20261007T122958Z.bak`).
- Les tests de migration comptent les versions : les mettre à jour avec la migration 021.
- Une puce de tag est limitée à 64 caractères et 20 par artiste (`normalize_tags`) ; les genres de morceaux n'ont pas cette limite et utilisent leur propre table.
- Un test UI qui démarre l'application réelle doit appeler `_shutdown(runtime)` en `finally`.

## Décisions encore ouvertes (techniques, à trancher et consigner dans l'ExecPlan)

- Noms de tables, forme exacte de l'arbre (profondeur autorisée), stockage de l'alias et de la provenance.
- Où vit le mode tagging dans `TrackListView.qml` (composant, colonne, barre) et comment l'état de chaque ligne arrive du modèle.
- Disposition exacte du genre manager (colonnes ou cartes, défilement des familles nombreuses, retour visuel du glisser-déposer, accessibilité clavier).
- Format d'annulation (pile par session ou journal persistant).
- Raccourcis clavier précis de la palette.
