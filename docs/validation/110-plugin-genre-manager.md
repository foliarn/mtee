# Plan 110 — Rapport de préparation et de validation

Date : 9 octobre 2026. Référence : [ExecPlan 110](../../Plans%20d'ex%C3%A9cution/110-plugin-genre-manager.md). Ce rapport distingue le travail documentaire actuel de l'implémentation future.

## Préparation documentaire

Le plan reprend les réponses utilisateur concernant le plugin, les sources dossiers/playlists, l'écoute volontaire, les deux variantes à essayer, les genres ordonnés, les noms complets sous House, les tags libres sans préremplissage, Reviewed et les changements qui l'invalident. Il ajoute le rangement du lot vérifié, les genres déduits des artistes avec abstention et la vue Uncertain proposée. Info et les listes ordinaires restent à maquetter ultérieurement.

La demande antérieure d'attendre avant de rédiger a été respectée pendant les questions. La demande suivante de passage au plan autorise cette préparation ; elle n'autorise pas à considérer une maquette examinée ou un rangement réel effectué.

La référence produit et l'index désignent 110 comme plan actif. Un avis de remplacement est ajouté à 109 en préservant son historique. Les choix de disposition, le coût de validation après pinceau, le retrait du dernier genre et les destinations précises sont explicitement à éprouver pendant la revue.

## Constat du dépôt

Au début de cette préparation, branche `main`, révision `1eab96e30d71c5318baaf4426fecb0d5a65ba6b7`. `git fetch origin` puis comparaison `HEAD...origin/main` ne montrent aucune divergence. Ce commit retire les fichiers de l'exécution de 109. Les corrections locales du lecteur, de la file et des listes ainsi que leurs nouveaux tests sont laissées hors de ce travail.

Le graphe code-review-graph a été actualisé, puis les sources et tests ont été lus. Les points vérifiés comprennent le placeholder Plugins de `Sidebar.qml`, la sélection de vues dans `EditorGroup.qml`, `FileMoveService`, son modèle et ses tests, `LibraryRepository.move_location_in_transaction`, `Database` et les tests de migration, `PlaylistService.rows`, ainsi que le schéma des crédits d'artistes. Le SQL historique 021 a été lu dans le commit `4de9320` pour cadrer une adaptation future compatible ; il n'a pas été restauré par cette tâche.

La migration maximale du checkout est 020. La base personnelle n'a pas été ouverte et sa version n'est pas présumée. Les garanties de reprise durable des mouvements par lot sont des exigences futures : elles ne sont pas déduites du seul retour arrière immédiat de `FileMoveService`.

## Contrôles documentaires

Les contrôles de cette préparation portent sur les liens relatifs des documents modifiés, les chemins existants cités comme points d'intégration, l'encodage UTF-8, les sections obligatoires de l'ExecPlan, la cohérence avec les décisions de la conversation et les diffs Git. Les chemins futurs sont expressément présentés comme des livrables à créer, avec jalon et contrat de commande.

Contrôles exécutés le 9 octobre : lecture UTF-8 des cinq documents de cette préparation sans caractère de remplacement ; résolution de tous leurs liens Markdown locaux sans cible manquante ; présence des quatre sections obligatoires ; cases à cocher limitées à Progress ; existence des points d'intégration cités comme actuels. Le package `src/mtee/plugins/` est confirmé absent et décrit comme futur. `git diff --check` passe ; les avertissements de normalisation CRLF/LF ne sont pas des erreurs de contenu. La relecture du plan couvre les décisions recueillies et distingue les comportements encore proposés pour les maquettes.

Le message final de la tâche donnera la preuve de publication sans ajouter un commit uniquement pour y inscrire son propre hash. Les changements applicatifs préexistants continuent d'évoluer pendant cette préparation ; seuls les cinq fichiers documentaires sont destinés à son commit.

## Ce qui restait non réalisé après la préparation documentaire

Aucun prototype créé ou lancé, aucune maquette approuvée, aucun changement Python/QML, aucune migration exécutée, aucun test applicatif, aucun benchmark et aucune recette du lecteur ne sont réalisés par cette préparation. Aucun fichier musical n'a été déplacé, renommé ou réécrit. Aucun build ni smoke-test du paquet Windows.

Le soupçon de lag reste à mesurer. Le protocole de 110.0/110.7 doit séparer le socle, le plugin inutilisé, le plugin actif et la reprise après fermeture. Les anciens résultats de 109 ne valent pas mesures de 110.

## Point de départ indiqué avant l'exécution

Lors d'une demande d'exécution, commencer par 110.0 puis préparer 110.1 sur données fictives et fichiers synthétiques. Faire essayer les deux variantes avec les mêmes tâches, recueillir les réponses textuellement et consigner la revue 110.2 avant le branchement fonctionnel. Le présent rapport sera ensuite enrichi avec les résultats réels de chaque jalon, en séparant tests automatisés, observations de l'agent, retours utilisateur et opérations sur données personnelles.

## Exécution du 9 octobre 2026 — 110.0 et 110.1 prêts pour la revue

Le dépôt a été réexaminé avant modification. Les travaux locaux du lecteur et des listes présents au démarrage ont ensuite été publiés séparément sous `fb71560` et `ec31b84`; ils n'entrent pas dans le diff du prototype. Le graphe code-review-graph a été mis à jour, puis le code effectif de `PlayerService`, du backend libmpv, du thème QML, de `LibraryRepository`, de `PlaylistService` et de `Database` a été lu. La migration 021 a été prélevée dans le commit historique `4de9320` uniquement pour créer une copie synthétique de compatibilité hors Git.

Le lanceur [review_genre_manager_110.py](../../scripts/review_genre_manager_110.py) charge deux variantes d'une même maquette QML dans une fenêtre séparée. Son contrôleur produit dix WAV fictifs sous `.local/validation/110/` et maintient les classements en mémoire. La page Classify montre dossiers, playlist, nouveaux morceaux, recherche, sous-dossiers optionnels, sélection multiple, pinceau, principal/secondaires, tags initialement absents, revue All tracks/To review, erreur/retry/Undo et aperçu. La page Genres est manipulable pour créer, renommer et archiver des définitions fictives ; Uncertain est une proposition visuelle ; Organize montre 80 destinations simulées pour 80 pistes vérifiées sur 100. Aucun fichier n'est déplacé. [Le dossier de revue](../ux/review-110-genre-manager.md) sépare les gestes à essayer des choix encore ouverts.

Captures générées et examinées à 1440 × 900 et 1100 × 760 : [sélection](../ux/review-110-selection.png), [pinceau](../ux/review-110-brush.png), [catalogue](../ux/review-110-catalogue.png), [aperçu](../ux/review-110-organize.png). Elles montrent le chargement des quatre surfaces sans erreur QML bloquante. Le `PlayerService` partagé a atteint `Playing` sur le WAV synthétique avec sortie libmpv silencieuse et le lanceur s'est fermé avec code 0. Une exécution avec sortie WASAPI a aussi affiché `Playing`, mais le processus autonome a retourné 1 après fermeture ; aucune conclusion sur l'écoute audible n'est tirée de cet essai. Le prototype interactif est prêt pour une écoute et une critique utilisateur depuis les sources.

Le banc [measure_genre_manager_110.py](../../scripts/measure_genre_manager_110.py) a créé et contrôlé deux bases fictives isolées : schémas 020 et 021 historique, `PRAGMA integrity_check = ok`. Aucune base personnelle n'a été ouverte. Dernière mesure sur la révision `ec31b848661f7dc6b1589ab7c09d3cd6b6c04f5e`, checkout encore modifié par ce jalon, Windows 11 `10.0.26200`, Python 3.12.14, AMD Ryzen 7 7735HS. Les opérations de service et les gestes QML sont répétés cinq fois ; l'ouverture de chaque vue QML est un essai distinct :

| Opération | Médiane | Minimum–maximum | Portée |
|---|---:|---:|---|
| Démarrage de l'application en démo hors écran | 1 994 ms | 1 881–2 943 ms | fenêtre chargée puis quittée, sans lecture |
| Lecture du dossier House, 340 pistes fictives | 21 ms | 18,6–24,5 ms | repository et projection Python, sans rendu |
| Lecture d'une playlist de 2 800 références fictives | 965 ms | 943–1 016 ms | service actuel, chemins non présents |
| Relecture du dossier puis extraction de 340 identifiants | 22 ms | 18,6–23,3 ms | préparation des identifiants, **pas** un clic de sélection |
| Ouverture et rendu du dossier House dans MTEE | 350 ms | un essai | application depuis les sources, hors écran |
| Ouverture et rendu de la playlist dans MTEE | 2 144 ms | un essai | application depuis les sources, hors écran |
| Scroll programmatique et capture d'une image | 35 ms | 26–121 ms | cinq positions, `grabWindow`, **pas** une mesure du geste au pointeur |
| Sélection programmatique et capture d'une image | 4 ms | 3–13 ms | cinq pistes, `grabWindow`, **pas** le délai du clic |
| Play explicite jusqu'à `Playing` | 30 ms | 25–33 ms | cinq WAV fictifs, libmpv avec sortie silencieuse |

La playlist fictive volontairement grande expose le coût de son accès piste par piste ; cette mesure ne prouve pas une régression du plugin, qui n'est pas branché. Le script conserve les résultats détaillés dans `.local/validation/110/perf-baseline/baseline-results.json`, ignoré par Git. Le passage du pointeur au feedback et l'écoute audible restent à observer pendant l'essai utilisateur ; la mesure comparative avec plugin actif est prévue en 110.7. Le maximum de scroll ci-dessus inclut le coût de `grabWindow` hors écran et ne se compare pas directement au seuil de pause du thread graphique proposé pour 110.7.

Contrôles réellement effectués : quatre tests du prototype Qt/QML passés, tests de fumée de l'application et tests des migrations terminés avec code 0, Ruff et Pyright sans erreur sur les fichiers nouveaux, chargement des deux variantes et des pages depuis les sources, inspection des captures, lecture native silencieuse atteignant `Playing`, contrôle d'intégrité des copies 020/021. La suite de fumée de l'application a émis un diagnostic Windows non fatal lié au backend natif pendant le chargement ; il n'est pas présenté comme une validation de l'écoute. Le build Windows et le smoke-test du paquet n'ont pas été lancés. La revue utilisateur 110.2 n'a pas eu lieu ; aucun choix de variante ni de destination n'est présenté comme validé. Les migrations et services fonctionnels 110.3–110.6 restent à créer après cette revue.

## Révision des maquettes après le premier retour 110.2

L'utilisateur a constaté que les premières maquettes s'écartaient trop de l'application MTEE et que certains textes étaient mal centrés. Il approuve l'usage des sidebars, puis demande un catalogue viable à plus de vingt genres, une création de racine et de sous-genre contextualisée, les listes classiques de MTEE, le bouton Move files dans le pied de page, et un sélecteur de sources intégré avec onglets et progression. Il exclut toute attribution automatique de House parce qu'un dossier se nomme House. Ce retour est consigné dans l'ExecPlan ; il ne constitue pas la validation finale de 110.2.

La fenêtre QML a été révisée en reprenant la barre de menus, la barre d'activité avec les icônes natives, un onglet de l'éditeur, le titre `FOLDER` avec nom de source cliquable, des listes à colonnes et le lecteur de MTEE. La palette droite de Classify a été retirée ; ses commandes sont sous le titre. Les boutons et champs ont reçu un centrage vertical explicite. Le sélecteur de source est une fenêtre modale interne avec onglets Folders/Playlists et pourcentage. La fixture House a zéro genre au chargement ; le lot ne reçoit un principal qu'après choix et confirmation explicites. Le catalogue propose 29 genres fictifs dans une liste défilante avec recherche et `+` sur les racines. Organize affiche une table et Move files, désactivé, à côté de Undo.

Six captures synthétiques actualisées ont été ouvertes et examinées : Classify sélection 1440 × 900, pinceau 1100 × 760, fenêtre de source, confirmation d'attribution au dossier, catalogue et Organize. Six tests UI/prototype passent. Ils couvrent notamment l'absence de classement inféré depuis les sources, l'attribution explicite et Undo, la hiérarchie à plus de vingt genres, le défilement QML et l'ouverture de la fenêtre de source. Ruff, son contrôle de formatage, Pyright et `git diff --check` passent sur les fichiers du jalon. Un nouveau lancement du sélecteur depuis le script a confirmé l'ouverture après correction d'un appel Qt erroné détecté au contrôle manuel. L'essai utilisateur au pointeur, l'écoute audible, le choix entre variantes et les destinations physiques restent à valider. Aucun paquet Windows n'a été construit.

## Revue utilisateur et socle fonctionnel 110.3

Après les maquettes corrigées, l'utilisateur demande d'appliquer le plan en soignant l'espacement et l'alignement pour rejoindre exactement le front MTEE actuel. Les deux gestes, sélection et pinceau, restent disponibles faute de choix exclusif. Il demande ensuite de ne pas rétablir l'ancienne 021 et annonce un repeuplement de la base avec cette version. La nouvelle migration porte le numéro 022 ; aucun fichier 021 historique n'a été remis dans le dépôt. Une base enregistrant l'ancienne 021 est refusée sans écriture par le contrôle d'historique. Aucune base personnelle n'a été ouverte, supprimée ou convertie.

Le socle 110.3 ajoute le registre statique des plugins, le domaine des genres ordonnés, 31 genres initiaux semés à la première ouverture, zéro tag libre initial, les décisions de genre/tag/revue avec révisions attendues et Undo ciblé, les sessions de sources persistées, la progression des dossiers/playlists et des lectures groupées. Le choix d'un dossier n'affecte aucun genre ; une commande explicite applique un genre choisi à ses pistes. Les données du plugin restent dans SQLite, séparées des métadonnées audio. La sauvegarde préalable à une migration refuse tout écrasement et son intégrité est contrôlée avant la migration.

Contrôles 110.3 réellement effectués : 31 tests ciblés migrations, domaine, repository, sessions et lecture passent ; Ruff et Pyright sont sans erreur sur le code du socle ; `git diff --check` passe. Une exécution manuelle depuis les sources sur une base temporaire neuve a constaté schéma 022, 31 genres, zéro tag, puis l'attribution explicite d'un genre à une piste fictive sans la marquer Reviewed. Les tests de migration montrent la sauvegarde vérifiée de 020, la conservation d'une correction d'artiste, le refus non destructif d'une 021 synthétique et le refus d'écraser une sauvegarde existante. L'interface réelle, le rangement physique et les contributions artistes restent à livrer dans les jalons suivants. Aucun EXE n'a été construit.

Le banc de référence modifié a aussi été relancé avec 340 pistes fictives et une copie isolée du schéma 020 : version 020 confirmée, démarrage démo hors écran médian 2 181 ms, lecture du dossier 22,3 ms, playlist 73,4 ms et extraction des identifiants 22,9 ms sur cinq passes. Ce contrôle vérifie surtout que le script historique continue de fonctionner sans recréer 021 ; il ne mesure pas encore l'interface du plugin.
