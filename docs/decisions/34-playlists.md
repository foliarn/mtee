# Playlists — décisions du 2026-09-30

Cette note consigne la demande de playlists fonctionnelles et les réponses reçues pendant le cadrage. Elle ne constitue ni une validation de maquette ni une livraison fonctionnelle. Le frontend reste en QML, les services et modèles en Python/PySide6, la persistance en SQLite. La documentation est française et l'interface anglaise.

## Demande et décisions confirmées

Le périmètre demandé est une activité Playlists utilisable avec autant de playlists manuelles que souhaité, alimentées par les morceaux des dossiers audio ajoutés à la bibliothèque. Le backend et sa migration SQLite font partie de la demande. La capture annotée fournie dans la conversation précise la composition de l'en-tête ; ses rectangles colorés sont des repères de placement, pas une nouvelle palette.

Le nouvel en-tête concerne uniquement les playlists. Les pages des dossiers audio conservent leur présentation actuelle. Une grande pochette carrée se place à gauche ; le titre en grand, la description, le créateur et la durée se placent à droite. Le résumé ne présente pas la taille en octets. Play et Shuffle se placent sous la pochette. À droite, la recherche, List, Artwork et les réglages de colonnes sont alignés avec ces commandes de lecture. L'icône Search possède la même taille que Settings et révèle une barre qui se déploie vers la gauche, juste avant List. Une séparation distingue l'en-tête des morceaux.

Le menu `+` de la sidebar propose la création et l'import de playlist au format MTEE encore à définir. Par décision explicite du 2026-09-30, Spotify est reporté à une autre fois et exclu du plan à réaliser. Son idée est conservée séparément dans `docs/ideas/spotify-playlists.md`, sans tâche d'intégration ni commande Spotify dans cette livraison.

La sidebar ne présente pas le créateur des playlists. Elle permet les playlists épinglées et les dossiers imbriqués, avec déplacement par glisser-déposer. Elle comprend une collection `Liked tracks` alimentée uniquement par les likes locaux de MTEE, indépendamment de Spotify. Le créateur des playlists est un nom commun défini dans les réglages.

Les morceaux sont ajoutables par sélection multiple et menu `Add to playlist`, par glisser-déposer vers une playlist et par le bouton `+` à droite des lignes. Les doublons musicaux sont empêchés : comparaison du titre, des artistes et de la version, en ignorant la casse et les accents ; choix utilisateur lorsque les données sont insuffisantes. Un remix ou un live reste distinct.

L'ordre manuel est l'ordre par défaut et peut être réorganisé par glisser-déposer. Des tris restent possibles sans modifier l'ordre manuel enregistré. Play et Shuffle jouent uniquement les résultats visibles après recherche ou filtrage. La file en cours conserve son instantané jusqu'à une nouvelle commande explicite de lecture.

« Filters » désigne le choix des colonnes. Le profil commun aux playlists comprend Title, Artist, Album, BPM, Key et Duration, sans filesize, format, creation date, modified date ni bitrate. Le profil des dossiers audio reste indépendant.

## État observé dans les sources

Le 2026-09-30, avant modification applicative, `WorkspaceModel.playlists` renvoie une liste vide, `playlistsContaining` une liste vide, `openPlaylist` et `addToNewPlaylist` un message de report, et `togglePlaylist` ne fait rien. Les données et interactions de playlists de `DemoWorkspace` sont fictives et conservées seulement en mémoire. Elles ne sont pas une persistance à migrer.

`src/mtee/qml/components/PlaylistsPane.qml` fournit une liste de playlists sans arborescence. `AddToPlaylistMenu.qml` fournit un menu avec marques d'appartenance ; la démo utilise une bascule ajout/retrait, à confirmer pour la version réelle. `TrackListView.qml` partage actuellement l'en-tête des dossiers et des playlists. Il faudra isoler le nouvel en-tête de playlist et garder les composants de morceaux, les onglets et la lecture existants.

La migration la plus récente est `015_track_analysis.sql`. `Database.migrate` possède déjà une sauvegarde cohérente des bases existantes et applique les migrations dans des transactions. Les tests de migration couvrent sauvegarde, préservation des données et rollback. Le numéro libre attendu pour le nouveau schéma est 016 ; il devra être revérifié au moment de l'implémentation.

Le catalogue utilise des UUID `track_id` stables, indépendants des chemins. `PlayerService.play_queue` conserve un instantané de la file de lecture. Les chargements des morceaux de dossiers passent par `JobService` et un modèle Qt virtualisé, avec génération de requête pour rejeter les réponses périmées. Ces contrats doivent être réutilisés.

La palette Acid, les surfaces sombres neutres, la police de l'application, les icônes SVG, les onglets et les angles droits sont l'autorité visuelle existante. La refonte des playlists ne remplace pas cette identité.

## Réponses à la troisième série de questions

Le 2026-09-30, l'utilisateur indique que sa configuration Spotify est déjà prête, mais reporte explicitement l'intégration. Il confirme les likes uniquement MTEE, un nom de créateur commun dans les réglages, l'ordre manuel par défaut avec tri possible, et la lecture limitée aux résultats visibles. Ces décisions remplacent les propositions laissées ouvertes dans la première version de cette note.

## Réponses à la quatrième série de questions

La pochette est une image locale choisie par l'utilisateur, avec une mosaïque des pochettes des morceaux par défaut.

L'utilisateur accepte le format proposé `.mteeplaylist` conservant nom, description, pochette, ordre et références, sans audio pour l'export léger. Ce fichier sert à sauvegarder/restaurer et à transférer une playlist vers un autre PC possédant les mêmes fichiers. Un export complet ZIP incluant les fichiers audio est également demandé ; son import est confirmé dans la septième série. Les sources audio sont conservées et aucune destination existante n'est écrasée.

Les playlists peuvent être dupliquées. Une playlist est supprimée après confirmation ; un dossier ne peut être supprimé que s'il est entièrement vide, sous-dossiers compris. Une suppression de playlist ou de dossier virtuel ne supprime jamais les fichiers audio.

## Réponses à la cinquième série de questions

L'export complet est une archive ZIP contenant la playlist et les fichiers audio. Le parcours d'extraction est confirmé dans la septième série.

L'interdiction de doublons concerne le même morceau musical, y compris lorsque plusieurs fichiers physiques ou formats le représentent. La règle de comparaison est confirmée dans la sixième série ; ne pas assimiler silencieusement un remix ou une version live à l'original.

Un fichier local introuvable conserve une ligne grisée et peut être retrouvé manuellement. Lors d'un transfert/import, l'association automatique est acceptée pour une correspondance certaine ; les ambiguïtés donnent lieu à un choix utilisateur. La lecture saute les entrées indisponibles.

## Réponses à la sixième série de questions

La comparaison de doublons musicaux proposée est acceptée : titre, artistes et version (Original, Remix, Live…), en ignorant la casse et les accents. Deux formats du même morceau sont refusés ; un remix ou une autre version restent distincts. Si les informations sont insuffisantes, demander le choix utilisateur. La règle doit être formalisée et testée avec les métadonnées réellement disponibles, sans promettre une reconnaissance audio.

Le bouton `+` ouvre un menu inspiré de la capture Spotify fournie dans la conversation : recherche de playlists, création, pochettes, nombre de morceaux et indicateurs d'appartenance. Les groupes « enregistrés dans » et « récemment mis à jour » constituent la référence de présentation à adapter en anglais à l'identité visuelle MTEE. Un petit cœur séparé du `+` permet les likes. La septième série confirme l'application immédiate de chaque clic et le maintien du menu ouvert.

« Filters » désigne le sélecteur de colonnes. Le profil est commun à toutes les playlists et indépendant de celui des dossiers audio. Les colonnes retenues sont Title, Artist, Album, BPM, Key et Duration. Filesize, format, creation date, modified date et bitrate sont exclus de ce profil.

## Réponses à la septième série de questions

Chaque clic sur une destination ajoute ou retire immédiatement les morceaux concernés. Le menu reste ouvert pour modifier d'autres destinations. Le bouton final est `Close`, pas `Cancel` : il n'annule pas les opérations déjà effectuées.

L'import d'un ZIP demande un dossier d'extraction. MTEE y copie les fichiers, ajoute le dossier à la bibliothèque puis recrée la playlist, sans écraser de fichiers existants. Les correspondances certaines sont automatiques et les ambiguïtés sont soumises au choix utilisateur.

L'utilisateur confirme une demande de confirmation avant la suppression d'une playlist et interdit la suppression d'un dossier non vide, sous-dossiers compris. Retirer un morceau d'une playlist ne supprime jamais son fichier audio.

## Choix techniques et propositions de présentation

Les choix ci-dessous sont des propositions de conception rendues examinables dans la maquette et le plan, pas de nouvelles réponses attribuées à l'utilisateur. La structure JSON versionnée de `.mteeplaylist`, la copie de couverture et les détails de migration sont des choix techniques ordinaires.

La sidebar place `Liked tracks` en tête, puis les épingles et l'arbre de dossiers/playlists ; les éléments ordinaires et les épingles gardent un ordre manuel mémorisé. `Liked tracks` est une vue système des likes locaux, sans création, duplication ou suppression comme une playlist ordinaire ; son ordre initial suit la date de like, les tris restent temporaires. La page présente le total des entrées, la somme des durées connues et le nombre d'indisponibles, sans annoncer une durée complète si des durées sont inconnues. Les résultats filtrés pilotent la lecture, pas ces totaux de playlist.

Pour une sélection multiple, une destination est cochée si elle contient tous les morceaux sélectionnés ; si elle ne les contient pas tous, cliquer ajoute les absents. Cliquer une destination complètement cochée retire uniquement la sélection. Les doublons musicaux refusés et les ambiguïtés sont signalés avec un résultat par morceau. Échec de persistance : la coche revient à l'état réellement enregistré.

Replier la recherche conserve texte et résultats, avec icône active tant qu'un filtre subsiste. Les glisser-déposer de réordonnancement s'effectuent en ordre manuel sans recherche active ; en vue triée/filtrée, proposer de revenir à `Custom order` plutôt que d'appliquer une position ambiguë.

Le fichier léger contient un manifeste JSON versionné et la couverture encodée, avec références portables et empreintes de fichiers calculées hors du thread graphique pour reconnaître les mêmes fichiers sur un autre PC. Les empreintes sont des preuves de rapprochement, pas des `track_id`. Le ZIP contient le manifeste et les copies audio avec noms sans collision. Les chemins absolus personnels ne sont pas nécessaires à l'export par défaut. À l'import, une empreinte exacte peut justifier un rapprochement ; des métadonnées seules donnent des candidats lorsque la certitude manque.

## Revue et réalisation

Après clarification des décisions structurantes, préparer une maquette QML à données fictives, intégrée visuellement à MTEE, avec état normal, recherche ouverte, ligne manquante, playlist vide et largeur réduite. Présenter un résultat concret avant la validation produit exigée par `PLAN.md`. Le silence ne constitue pas une validation.

Le [plan 34](../../Plans%20d'ex%C3%A9cution/34-playlists-locales.md) décrit cette demande de playlists locales, sans réactiver les tags sémantiques, les vues intelligentes, Spotify ni Shovel. Le plan 10 fournit des contrats à adapter, pas une obligation d'implémenter ses autres fonctions. Spotify n'est pas ajouté aux jalons, aux prérequis, aux tests d'intégration ou au menu de cette livraison.

L'implémentation devra séparer playlists, dossiers virtuels, likes et liens aux fichiers locaux. Prévoir intégrité référentielle, unicité des membres selon la décision finale, ordre transactionnel, suppression limitée aux données de playlist, erreurs de persistance visibles, accès longs hors du thread graphique et validation sur copies de données. Ne pas créer de schéma ou service propre à Spotify en anticipation.

La recette inclura création, ajout/retrait, réordonnancement, redémarrage, dossiers imbriqués et prévention des cycles, épingles, likes, titres manquants selon la décision à venir, lecture et shuffle limités aux résultats visibles, import MTEE invalide/partiel, sauvegarde et rollback de migration, fenêtres étroites et conservation du comportement des dossiers audio.

Aucun build Windows n'est demandé. À chaque étape implémentée : contrôles adaptés, parcours depuis les sources, suivi de l'ExecPlan, commit détaillé et push vérifié. L'état Git initial comporte déjà des modifications utilisateur de `.gitignore` et `AGENTS.md`, et des répertoires de skills non suivis ; ils ne doivent pas être inclus dans les commits du travail playlists.

## Réalisation du 2026-09-30

Revue approuvée explicitement par l’utilisateur (« parfait »). Le schéma 16 et le gateway Qt implémentent le périmètre local. `.mteeplaylist` est le JSON version 1 ; ZIP stocke le manifeste et l’audio sous `audio/`, sans réencodage. Les candidats provenant uniquement des tags restent ambigus ; seule une empreinte exacte unique associe automatiquement une source. Les morceaux aux tags insuffisants demandent la confirmation d’identité distincte avant un ajout susceptible de créer un doublon.

Les entrées et pistes ont des UUID séparés. Les écritures UI sont ordonnées dans JobService, les transferts sont annulables et les imports ZIP inachevés repris par le menu + avec empreintes contrôlées. Le profil de colonnes/largeurs est propre aux playlists, le cache d’artwork distingue les URLs locales des URLs image provider. La recette et ses limites sont consignées dans [validation 34](../validation/34-playlists-locales.md).
