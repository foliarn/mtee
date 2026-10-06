# Validation 105 — pilote artistes et revue web locale

Le 5 octobre 2026, essai réel exécuté depuis les sources. Le front est un outil autonome de rapports et de revue, conformément à la dernière demande utilisateur. Aucune interface, migration ou fonctionnalité MTEE modifiée par ce lot. Le suivi Spotify reste manuel.

## Résultats observés

La base existante contient 1 976 artistes établis, 382 provisoires et 2 828 morceaux. Le snapshot utilisé contient les 2 812 morceaux à crédits/revue confirmés ; les profils provisoires ne deviennent pas des identités externes à rechercher.

L'échantillon ciblé couvre 50 morceaux distincts et 42 artistes. Tous les sélecteurs ont trouvé le nombre demandé. Couverture structurelle : 36 crédits solo, 14 collaborations, 5 remixes, 2 bootlegs/edits/flips et 7 cas de noms courts ; catégories cumulables, donc compteurs non additionnables. Aucune catégorie structurelle demandée n'est absente. Cette sélection ciblée n'est pas représentative statistiquement de toute la collection.

MusicBrainz : 42 recherches terminées, dont un résultat vide ; 95 appels HTTP, 106,015 secondes, aucun cache préexistant utilisé et aucune interruption. « Recherche réussie » signifie réponse du fournisseur, pas identité correcte. Un score textuel élevé ne vaut pas une confirmation. Le complément web et l'audit des dossiers sont réalisés par l'agent dans la session ; ils ne constituent pas un script LLM autonome sans supervision.

L'audit IA propose 36 profils Spotify et 31 SoundCloud. Les 42 identités sont réparties en 33 rapprochées, 7 à consolider et 2 non résolues. Seize dossiers ont au moins un point à vérifier. Le tri proposé compte 36 garder, 3 bloat possible et 3 à déterminer. Les rôles sont cumulatifs : 28 Producer, 17 DJ, 10 Singer et 5 MC. Les contradictions restent visibles, notamment homonymes, liens communautaires partagés, deux IDs possibles pour un artiste et genres discordants. Les rôles de carrière insuffisamment sourcés sont explicitement à consolider.

Les 42 décisions personnelles du pilote livré restent à faire. Aucun test navigateur n'a validé un artiste à la place de l'utilisateur : les écritures de recette utilisent une copie indépendante. Aucun audio ouvert, modifié ou renommé par l'outil. Les images et une taxonomie des genres ne sont pas validées. Tokens IA et prix total non exposés/non mesurés ; ne pas les annoncer comme zéro.

## Outil livré

`scripts/artist_enrichment_pilot.py` : snapshot SQLite en lecture seule, sélection reproductible, dossiers d'artistes, recherche MusicBrainz avec cache et checkpoint, import d'observations sourcées, rapport Markdown et CSV initial de revue. Bibliothèque standard uniquement. Les erreurs fournisseur restent distinctes des réponses vides ; les erreurs sont retentables, les succès sont conservés à la reprise.

`scripts/artist_pilot_server.py` et `scripts/artist-pilot-web/` : serveur lié à `127.0.0.1`, tableaux artistes/morceaux et bilan. Recherche sur artistes/titres, filtres rôles/tri/revue/anomalies, dossiers sourcés, candidats et genres bruts séparés. Correction de l'identité, des URLs, des rôles et de Bass-related ; tri et notes personnels ; sauvegarde atomique dans `review.json` ; export CSV des décisions à jour. Ce JSON n'écrase ni les observations IA ni le CSV initial, importé tant que le JSON n'existe pas.

Les profils corrigés remplacent les boutons de profil du dossier après sauvegarde. Les champs restent protégés pendant la requête. Host/Origin contrôlés, fichiers statiques limités à une liste autorisée, chemins audio et catalogue complet non servis. Export CSV protégé contre l'interprétation des notes comme formules.

## Contrôles effectués

- 22 cas Pytest passent pour la lecture sans modification, les crédits confirmés, la sélection/couverture, les liens canoniques, le cache/les reprises, les réponses invalides, les preuves obligatoires, la préservation de revue et les accès HTTP/sauvegardes séparées.
- Ruff check/format sur les deux scripts et leurs deux fichiers de tests ; compilation Python ; `node --check scripts/artist-pilot-web/app.js` ; `git diff --check`.
- Recette navigateur : recherche, dossier et sources, reprise de notes/identité après rechargement, filtre MC (5 dossiers), onglet des 50 morceaux, bilan des profils/coûts. Sur copie : sauvegarde, rejet d'une URL d'album Spotify, correction d'un profil, actualisation du bouton et téléchargement CSV contrôlé (42 lignes, correction incluse).
- Captures privées desktop 1360 × 950, mobile 390 × 844 et panneau Codex réel. Vérification de la composition et de l'absence de débordement global au format mobile. Le dossier desktop dispose d'un défilement interne ; la capture pleine page ne déroule pas ce panneau.
- Revue visuelle par un sous-agent frais : deux corrections matérielles demandées, puis verdict `ship` portant sur ces deux corrections résolues. Documentation visuelle propre à l'outil ; aucun thème MTEE modifié. Détecteur exécuté une fois : avertissement d'onglet souligné classé faux positif (boutons sans arrondi).
- Le graphe ne référence pas encore les nouveaux scripts ; son rayon nul ne prouve pas une absence d'impact. Le périmètre autonome est vérifié dans les imports et les sources.

Aucun build Windows, test du paquet ni modification de dépendance requis pour ce front autonome. Les fichiers production déjà modifiés dans le workspace appartiennent à un autre travail et ne sont pas inclus dans ce lot.

Publication du lot : commit `9595607`, push vers `origin/main` réussi le 5 octobre 2026. Aucun fichier de collection, rapport personnel, cache fournisseur ou décision utilisateur inclus.

## Relancer et poursuivre

### Révision après retour utilisateur — revue par exceptions

Le parcours initial est remplacé : les valeurs inchangées sont acceptées par défaut et exportables immédiatement. L'acceptation par défaut n'est pas une consultation individuelle des preuves ; la provenance est conservée dans la colonne `acceptance` de l'export (`default` ou `correction`). Les identités non résolues restent non résolues et les profils absents restent vides. Les observations IA restent inchangées.

Tableau pleine largeur avec rôles cumulables, Bass-related et tri éditables. Dossier facultatif pour les sources, URLs et notes ; fermeture/changement de dossier conserve les brouillons. Un bouton global enregistre uniquement les artistes modifiés. Aucun Suivant ni compteur à faire. Chargement de 100 lignes à la fois, ajout automatique au défilement et recherche sur le jeu entier.

Recette sur copie : deux artistes corrigés ensemble, notes conservées en changeant de dossier, sauvegarde puis rechargement. Fixture fictive de 2 000 artistes : 100 lignes initiales, 200 après défilement, recherche directe du dernier artiste sans pagination. Captures desktop et mobile sans débordement global ; sur petit écran le tableau défile horizontalement. La base réelle et les décisions utilisateur ne sont pas utilisées comme support d'écriture de recette.

Tests supplémentaires : propositions effectives/export sans 2 000 écritures, lot invalide entièrement refusé, corrections précédentes préservées, retrait explicite d'un profil et retour de Bass-related à inconnu, compatibilité des anciens tris pending. Les contrôles de la version initiale ci-dessus restent historiques ; cette révision a son propre contrôle final et sa publication.

Clôture technique le 6 octobre 2026 : 28 tests passent, Ruff check/format, compilation Python, syntaxe JavaScript et diff sans erreur. La fixture de volume inclut aussi un CSV initial de 2 000 lignes pending : seules les deux corrections sont écrites. Les notes des anciens CSV restent conservées même sans décision de tri. Le pilote réel est rouvert avec ses 50 morceaux et 42 artistes ; sa correction utilisateur préexistante reste prioritaire sur les propositions. Aucun test de sauvegarde sur le dossier réel.

Révision publiée dans `d23c4d8` le 6 octobre : push vers origin/main et fetch de confirmation réussis, sans divergence. Données/captures restent privées et les changements production préexistants ne sont pas inclus.

6 octobre — Producer/DJ regroupés en une case et un filtre communs, dans les lignes et le dossier. Recette sur copie : décocher puis recocher le groupe et sauvegarder ; le filtre retrouve 28 artistes du pilote. Contrôle JavaScript et actualisation du front réel sans écriture de recette sur ce dernier. Les observations IA originales ne sont pas réécrites.

Depuis la racine, après création du pilote :

```powershell
.\.venv\Scripts\python.exe scripts/artist_pilot_server.py --output <dossier-prive-du-pilote> --port 8765
```

Ouvrir `http://127.0.0.1:8765`. Les données réelles restent dans le dossier privé `.local/validation/105/`, ignoré par Git. Ctrl+C arrête le serveur ; le JSON de revue permet la reprise. Une copie `ui-check` contient exclusivement les décisions fictives de recette et ne doit pas être importée comme revue utilisateur.

Pour un autre échantillon, `prepare` exige un nouveau dossier. Les sélecteurs sont une liste JSON d'objets contenant `category`, `artists` (noms), `count` et, facultativement, `title_pattern`. `musicbrainz` reprend le même dossier. `report` importe une liste d'observations portant les IDs locaux, les rôles/tri proposés, sources, liens prouvés et problèmes ; les décisions humaines restent indépendantes.

La prochaine étape utile est la revue des dossiers ambigus et du bloat possible, puis la comparaison des choix personnels avec les propositions. Les corrections d'identité doivent précéder toute utilisation en découverte. Ne pas dériver les genres d'un morceau uniquement des genres de ses artistes. Un rôle Producer n'indique pas automatiquement que l'utilisateur aime toute sa discographie.

Clarification du 6 octobre : le regroupement initial est remplacé par deux cases séparées ; Producer active DJ par défaut et à la coche, avec exception DJ possible. 29 tests passent, dont défaut Producer/DJ, conservation d’une exception enregistrée et des preuves originales ; Ruff et syntaxe JavaScript passent. Recette des cases et sauvegarde sur copie, actualisation du pilote réel sans écriture de recette.


## Révision du 6 octobre — pages et genres par morceau

Autorisation utilisateur : préserver sa revue terminée des 42 artistes, retirer les textes redondants, rendre les catégories du Récap cliquables, valider des pages de 100 maximum, conserver les artistes écartés avec idgaf. Les valeurs sans information affichent Non/Garder ; aucune preuve de carrière n'est inventée. Cette demande remplace le défilement continu et la sauvegarde limitée aux seules corrections.

Sauvegarde privée du review.json existant et des 42 valeurs effectives avant édition. Il contient dix corrections explicites ; les autres valeurs étaient acceptées par défaut. Son empreinte SHA-256 reste identique après la recette. Aucune sauvegarde de test sur ce dossier réel. Les valeurs explicites, liens, notes et exceptions Producer/DJ restent prioritaires.

Nouveau endpoint same-origin PUT /api/page : 1 à 100 artistes, validation intégrale puis écriture atomique. Les autres pages restent intactes. idgaf est dérivé du tri dans les lectures/export et enregistré lors d'une validation ; aucun artiste, crédit ni morceau n'est supprimé. La base MTEE n'est pas modifiée.

Politique de genres dans scripts/track_genre_audit.py : découper les tags composés, ignorer Alternative/Dance/Pop/Electronic/Electronica et valeurs génériques, conserver les genres précis. Un contexte de carrière explicite et sourcé peut rejeter House mais ne fournit jamais le genre de remplacement. L'absence de House dans une liste de genres d'artiste ne suffit pas à le rejeter. Le fichier privé genre-rules.json contient les corrections par track_id et contextes facultatifs par artist_id. La correction d'un morceau ne s'étend pas aux autres productions. Phoneline reçoit la correction DnB demandée par l'utilisateur ; son tag House rejeté est signalé au Récap et son tag original reste visible. Aucun classement audio automatique ni taxonomie complète n'est annoncé.

Contrôles : 36 tests passent (limite 100/101, atomicité, autre page préservée, idgaf/export, tags composés, contexte sourcé et correction isolée par morceau), Ruff et syntaxe JavaScript. Recette navigateur sur copie : catégorie Producer puis validation de 27 lignes, catégorie bootleg ouvrant le bon filtre, alerte Phoneline ouvrant sa ligne. Sur 2 000 artistes fictifs : 100 lignes et 20 pages ; validation de la page 2 laissant le brouillon MC de la page 1 en attente, puis validation de celle-ci. Captures desktop dans le panneau et mobile 390 × 844 ; aucun débordement global, tableau horizontal sur mobile. Aucun build Windows.

Test supplémentaire : audit des tags et catégories structurelles servis sans réécriture du snapshot. Recette du filtre Remix : huit artistes du pilote, retour à la liste complète. Bouton de page sticky, accessible en haut sans grand titre.

Publication : commit 70017b3, push origin/main et fetch confirmés; aucun écart local/distant. Seuls les onze fichiers de l’outil, tests et documents sont inclus; décisions, données et captures restent privées.


## Collection complète et Validés — 6 octobre

La nouvelle demande autorise toute la collection et la persistance des validations dans la base MTEE, sans interface QML ni actions Spotify. Elle remplace les limitations en lecture seule de cet outil. Le premier import charge 2 828 morceaux et 1 976 artistes établis ; 16 morceaux sans crédits confirmés restent visibles, sans inventer de crédits ni transformer les profils provisoires en artistes établis. Les 42 validations du pilote, dont six idgaf, sont importées une fois ; les enregistrements déjà présents en base restent prioritaires.

Stockage indépendant : scripts/artist-review-migrations/001_artist_enrichment.sql crée artist_enrichment_schema (version 1) et artist_enrichment_reviews dans la base existante. Une sauvegarde SQLite cohérente précède cette migration. Cette extension autonome ne modifie ni PRAGMA user_version (19), ni l'historique des migrations principales, ni les crédits, titres, fichiers ou playlists. Cela préserve l'ouverture par l'application existante sans build Windows. Les rôles, profils, tri, tags, notes, validation et observations sourcées sont conservés séparément et liés à artists par clé étrangère.

ReviewDatabase utilise des connexions par opération, foreign_keys activé et un timeout borné. Une validation de page écrit tous ses artistes dans une transaction ; aucune transition visuelle avant sa réussite. SQLite devient la source de vérité du serveur avec --database ; le JSON historique n'est pas réécrit en miroir. Sans --database, la validation reste disponible en JSON atomique. Les Validés sont éditables et restent validés après correction. La page à revoir est recalculée après chaque validation : le lot suivant remplace les lignes retirées. Les brouillons hors page restent conservés. L'export distingue validation_state et validated_at.

scripts/artist_full_collection.py --database <base> --pilot <pilote> --output <nouveau-dossier> --import-validated-pilot prépare le snapshot intégral dans une transaction en lecture seule, copie les preuves/choix/règles de genres, puis importe les choix validés du pilote. Un dossier existant est refusé. Relancer le serveur : scripts/artist_pilot_server.py --output <collection-privée> --database <base> --port 8765. Les autres artistes sont chargés avec les défauts Non/Garder et un état À enrichir : aucune recherche web ou identité n'est inventée. Cette livraison charge la collection ; elle ne prétend pas avoir réalisé l'audit des 1 934 autres artistes.

Contrôles : 40 tests passent, dont chargement des morceaux sans revue et artistes sans crédits, import idempotent des 42 choix, conservation des corrections et observations, sauvegarde préalable, transaction entièrement annulée sur clé étrangère invalide, reprise et autres pages non validées. Recette sur copie cohérente de la base : 42 Validés, validation de 100 supplémentaires donnant 142 Validés et 1 834 à revoir, changement effectif du premier artiste visible, onglet Validés éditable. La base réelle reçoit seulement les 42 choix déjà validés par l'utilisateur : 42 lignes d'enrichissement, six idgaf, 2 828 morceaux, 2 358 profils (dont 1 976 établis), version principale 19, quick_check ok et zéro violation de clé étrangère. Le fichier original de revue reste intact. Captures desktop/mobile ; aucun débordement global. Recherche et pages de 100 pour les morceaux également.

Compatibilité vérifiée sur la copie : Database.migrate() ne demande aucune migration principale avec les nouvelles tables ; ouverture du schéma 19 acceptée. Recherche Phoneline dans les 2 828 morceaux et filtre Producer ouvrant les Validés vérifiés. Correction d’un artiste validé en mode JSON conservant son état couverte par test. La copie de review.json importée est identique au pilote original.

### Worker préparé — 2026-10-06

GPT-6 Luna / low choisi par l'utilisateur ; utilisation Codex CLI avec connexion ChatGPT obligatoire, aucune API payante configurée. File persistante et verrou de collection, MusicBrainz avant audit web sourcé, publication des propositions séparée des validations SQLite. Commandes et limites dans scripts/artist-pilot-web/AUTOMATION.md. Nouvel onglet Job : démarrage/reprise, pause après lot, arrêt, retry, compteurs/journal/tokens et rechargement volontaire des propositions.

55 tests ciblés passent (40 précédents + 15 nouveaux). Protocole de sortie Codex testé avec un faux processus Python ; fournisseurs simulés uniquement. Recette navigateur sur le serveur réel inactif : 1 934 en attente, 42 Validés, zéro en cours, bouton Démarrer disponible. Vue mobile 390 × 844 sans débordement global, capture desktop privée job-idle.jpg. Aucun lancement d'enrichissement, aucune nouvelle validation humaine ou écriture dans la base réelle. La disponibilité de GPT-6 Luna et la qualité de l'audit réel restent à mesurer au premier lot lancé par l'utilisateur.
