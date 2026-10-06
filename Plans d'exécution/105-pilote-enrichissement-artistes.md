# Étape 105 — Pilote de tri et d'enrichissement des artistes

ExecPlan du 5 octobre 2026, selon `PLANS.md`. Suite du catalogue livré par le [plan 104](104-artist-manager-importation.md). La demande autorise un essai sur 50 morceaux réels couvrant les catégories utiles ; elle ne lance pas l'intégration frontend/backend de l'enrichissement à MTEE.

## Objectif et périmètre

Révision du 5 octobre après recette utilisateur : le parcours individuel est rejeté. Cette révision remplace les mentions de confirmations obligatoires ci-dessous. Les valeurs inchangées sont désormais acceptées par défaut dans cet outil local ; seules les exceptions sont corrigées et enregistrées en lot. Tableau pleine largeur, rôles/Bass-related/tri éditables, dossiers facultatifs pour sources et liens, aucun Suivant et aucun compteur « à faire ». Les inconnues restent inconnues. Cette acceptation locale n'écrit rien dans MTEE et n'agit pas sur Spotify.

Préparer un échantillon reproductible de 50 morceaux à partir des crédits confirmés, regrouper leurs artistes, rechercher les candidats MusicBrainz puis compléter les informations manquantes sur le web. Livrer des propositions de rôles, de contexte Bass-related et de tri personnel accompagnées de leurs preuves. La revue humaine reste à faire : aucune proposition ne devient une confirmation ou une exclusion dans MTEE.

L'utilisateur suivra les artistes manuellement sur Spotify, après écoute. Ce pilote n'a besoin ni de jeton Spotify ni d'accès Shovel et n'effectue aucune action de suivi. Les liens Spotify/SoundCloud sont des références documentaires. Les genres récupérés restent des observations brutes, sans taxonomie imposée ni propagation des genres d'artiste aux morceaux.

Les données et rapports personnels restent sous `.local/validation/105/`, ignoré par Git. La base réelle est lue par SQLite en mode lecture seule, dans une transaction cohérente. Aucun audio n'est modifié, copié, tagué ou renommé ; aucune migration ni fenêtre de production n'est nécessaire.

## Progress

- [x] 2026-10-05 — Lire les plans et inspecter Git, le schéma et les tests existants ; vérifier 1 976 artistes établis et 2 828 morceaux dans la base actuelle.
- [x] 2026-10-05 — Consigner l'autorisation du pilote et le suivi Spotify exclusivement manuel.
- [x] 2026-10-05 — Créer la CLI autonome, le serveur web local et les tests synthétiques de sécurité/reprise.
- [x] 2026-10-05 — Sélectionner 50 morceaux distincts, 42 artistes ; aucune catégorie structurelle manquante et tous les sélecteurs satisfaits.
- [x] 2026-10-05 — Collecte MusicBrainz terminée : 95 appels, 106,015 secondes, 42 recherches réussies dont un résultat vide ; complément web et audit dans la session.
- [x] 2026-10-05 — Produire le rapport et le front de revue : 36 profils Spotify, 31 SoundCloud proposés ; 33 identités rapprochées, 7 à consolider et 2 non résolues.
- [x] 2026-10-05 — Vérifier depuis les sources : 22 tests, contrôles Python/JavaScript, recette navigateur sur copie, captures et corrections de revue ; documentation actualisée.
- [x] 2026-10-05 — Commit détaillé `9595607` et push vers `origin/main` réussis ; seuls les outils, tests et documents du lot autonome sont inclus.
- [x] 2026-10-05 — Consigner le rejet utilisateur du parcours individuel et adopter l'acceptation par défaut avec corrections en lot.
- [x] 2026-10-06 — Vérifier la révision par exceptions : 28 tests, Ruff, Python/JavaScript, recette sur copie et recherche/défilement sur 2 000 artistes fictifs ; rouvrir le pilote réel en conservant sa correction existante.
- [x] 2026-10-06 — Révision publiée : commit `d23c4d8`, push et fetch origin/main réussis, écart local/distant nul.

- [x] 2026-10-06 — Préserver la revue utilisateur, retirer le bloat visuel, paginer par 100, valider seulement la page et signaler les genres contradictoires par morceau; 36 tests et recette navigateur sur copie/volume réussis.

- [x] 2026-10-06 — Révision publiée dans 70017b3; push et fetch origin/main réussis, divergence nulle.

- [x] 2026-10-06 — Charger la collection complète et importer les 42 validations dans une extension SQLite indépendante, avec sauvegarde préalable ; 40 tests et recette de transition sur copie réussis.

## Contexte et décisions

Le schéma 019 distingue `artists`, crédits proposés/confirmés et revue par morceau. Les 382 profils provisoires observés ne font pas partie des 1 976 artistes établis. Lire `artists`, `track_artist_credits`, `track_artist_review` et `track_locations` sans initialiser les services applicatifs ni leur base. Utiliser le titre confirmé et conserver les tags observés séparément.

Créer `scripts/artist_enrichment_pilot.py` et `tests/unit/test_artist_enrichment_pilot.py`. Le script fonctionne avec la bibliothèque standard ; aucun fournisseur LLM payant ni clé supplémentaire n'est nécessaire pour cette expérimentation. L'agent réalise et documente les recherches web et l'audit IA ; le script importe ces observations structurées sans les inventer.

La dernière instruction utilisateur remplace toute idée d'intégration : créer `scripts/artist_pilot_server.py` et `scripts/artist-pilot-web/`, avec tests dans `tests/unit/test_artist_pilot_server.py`. HTML/CSS/JavaScript simple et serveur Python standard constituent un choix technique ordinaire pour cet outil de tableaux. La préférence de framework reste ouverte ; aucune préférence durable de workflow graphique n'est déduite d'une absence de réponse.

## Jalons et commandes

### 105.1 — Photographie et sélection

La commande `prepare --database <base> --output <nouveau-dossier> --selectors <json-privé> --size 50 --seed 105` sera créée dans ce jalon. Le fichier de sélecteurs fournit les artistes/titres à couvrir et la catégorie hypothétique (producteur, MC, chanteur, rôle combiné, original remixé, confidentiel/homonyme). Les catégories sont des motifs de sélection, pas des classifications confirmées. Ajouter la couverture structurelle remix, bootleg/flip/edit, collaboration, artiste solo et noms courts, puis compléter de manière déterministe. Un morceau peut couvrir plusieurs catégories ; ne le compter qu'une fois. Signaler les catégories absentes et les populations trop petites, sans inventer de cas.

Conserver un catalogue privé figé, l'échantillon, les dossiers d'artistes (nombre de crédits dans la collection, titres représentatifs, rôles de crédit) et les empreintes du jeu d'entrée. Une sélection ciblée ne permet pas d'extrapoler un taux de succès à tous les artistes.

### 105.2 — Recherche MusicBrainz

La commande `musicbrainz --output <dossier>` sera créée pendant ce jalon. Rechercher par nom avec échappement Lucene, conserver jusqu'à cinq candidats et détailler jusqu'à deux candidats de nom exact. Le score MusicBrainz reste une pertinence textuelle, jamais une probabilité d'identité. Les MBID et liens récupérés sont candidats jusqu'à l'audit.

Un client HTTPS identifié par `MTEEArtistPilot/105 (https://github.com/foliarn/mtee)` espace les appels d'au moins 1,1 seconde. Il gère timeout, HTTP 429/5xx, Retry-After et reprises bornées. Cache uniquement les réponses réussies ; distinguer résultat vide, erreur réseau et réponse invalide. La reprise conserve les résultats réussis et retente les erreurs. Écrire les checkpoints atomiquement, conserver les requêtes et durées observées, permettre Ctrl+C. Ne pas rechercher toute la collection.

Références vérifiées le 5 octobre : [API](https://musicbrainz.org/doc/MusicBrainz_API), [recherche](https://musicbrainz.org/doc/MusicBrainz_API/Search), [limitation](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting). Le type MusicBrainz Person/Group ne signifie pas Producer/MC/Singer.

### 105.3 — Complément web, audit et revue

Importer avec `report --output <dossier> --observations <json-privé>` les dossiers établis par l'agent : artiste local, liens, sources, propositions de rôles cumulables, Bass-related, garder/écarter/incertain, raisons et anomalies. Chaque lien retenu doit avoir une preuve ; l'identité peut rester ambiguë. Les décisions humaines sont initialisées à `pending` dans un CSV distinct, préservé à la régénération. Un champ absent reste absent. Une absence MusicBrainz ou Spotify n'est pas un motif de bloat.

Le rapport Markdown fournit les 50 morceaux, la couverture, chaque artiste et ses preuves, les anomalies de crédit local, les erreurs fournisseurs et le coût réellement observable. Distinguer propositions IA, preuves documentaires et décisions utilisateur. Les tokens/prix non exposés par les outils sont indiqués non mesurés, pas zéro.

La commande `python scripts/artist_pilot_server.py --output <dossier> --port 8765` sert le front uniquement sur `127.0.0.1`. Recherche par artiste/titre, filtres de rôles, propositions, revue et anomalies ; onglets artistes, 50 morceaux et bilan. Chaque dossier présente liens, preuves, candidats non retenus et genres bruts. L'utilisateur peut corriger les URLs, l'identité, les rôles et Bass-related, puis enregistrer son tri et ses notes. `review.json` est la source de la revue web, indépendante des observations IA ; le CSV initial est importé tant que ce JSON n'existe pas. L'export web restitue les décisions à jour sans écraser ce CSV historique. Sauvegarde atomique, URL de profils validées, export protégé contre les formules, chemins privés non servis, contrôle Host/Origin et fichiers statiques autorisés explicitement.

## Validation et reprise

Tests synthétiques : lecture sans changement de la base, exclusion des crédits provisoires, tirage reproductible indépendamment de l'ordre, absence de doublons et couverture/absences, noms Lucene spéciaux, cache/reprise après erreur et temporisation des reprises, distinction HTTP/JSON/vide, import des observations et préservation des décisions humaines. Les appels réseau des tests sont simulés ; les données musicales sont fictives.

Exécuter depuis la racine `uv run python -m pytest tests/unit/test_artist_enrichment_pilot.py tests/unit/test_artist_pilot_server.py`, Ruff sur les fichiers Python du lot, compilation Python et `git diff --check`. Recette navigateur depuis les sources : recherche, filtres, dossiers, rapports, sauvegarde et reprise sur une copie privée, liens corrigés et export CSV ; captures desktop/mobile et panneau Codex. Aucun build Windows. Créer `docs/validation/105-pilote-enrichissement-artistes.md` pour les contrôles et limites sans collection personnelle.

Les commandes prepare/refaire un échantillon utilisent un nouveau dossier. Les commandes de réseau/rapport reprennent le dossier existant sans remplacer les décisions humaines. Avant Git, examiner les changements préexistants ; indexer explicitement seulement les nouveaux outils, tests et documents. Commit détaillé et push selon `PLANS.md`, sans push forcé.

## Surprises & Discoveries

2026-10-05 — La base contient 2 828 morceaux, 1 976 artistes établis et 382 provisoires : les nombres annoncés sont cohérents pour les profils établis. Les compteurs doivent distinguer ces états.

2026-10-05 — Les deux adresses SSH tofik essayées lors du cadrage expirent. Le pilote n'en dépend pas ; aucun contrat Shovel/WKDIG n'est présenté comme vérifié.

2026-10-05 — Des homonymes et liens communautaires contradictoires rendent la sélection par score dangereuse. Un titre original remixé n'est pas une preuve de mauvais crédit. Les contradictions et identités non résolues restent visibles. Plusieurs rôles de carrière manquent encore de preuve : signalés à consolider, jamais confirmés automatiquement.

## Decision Log

2026-10-06, clarification utilisateur — Conserver Producer et DJ séparés, mais cocher DJ par défaut si Producer est coché. Cette clarification remplace le regroupement initial, qui était une mauvaise interprétation. Cocher Producer coche aussi DJ, sans empêcher une correction indépendante de DJ ; les exceptions enregistrées restent prioritaires sur le défaut. Les observations sourcées restent intactes.

2026-10-05, utilisateur — « Je change ce que j'ai besoin de changer et si j'ai rien à dire c'est validé » ; refuser 2 000 clics Suivant. Les propositions inchangées sont donc retenues sans écriture par artiste, avec provenance « default » dans l'export. Les corrections sont validées intégralement avant une écriture atomique unique ; une entrée invalide ne sauvegarde pas la moitié du lot. Les corrections antérieures restent prioritaires et les états pending de tri hérités reprennent la proposition sans perdre leurs autres corrections.

2026-10-05, utilisateur — Tester sur un batch de 50 sons regroupant les catégories et choisir manuellement qui suivre sur Spotify.

2026-10-05, Codex — Produire un outil d'étude et une revue privée avant toute intégration MTEE. Les catégories aident à couvrir l'essai et ne fixent pas la future taxonomie. Écarter du catalogue n'efface pas les crédits.

2026-10-05, utilisateur — Les rapports/tableaux passent par un front web local ; l'enrichissement ne fait pas partie de l'app MTEE. Cette décision remplace l'intégration précédemment envisagée.

## Outcomes & Retrospective

Pilote exécuté, audit IA sourcé et outil de revue autonome disponibles localement. Propositions : 36 garder, 3 bloat possible, 3 à déterminer. MusicBrainz est automatisé ; le complément web et l'audit ont été réalisés par l'agent, pas par un pipeline LLM sans supervision. Images, taxonomie des genres, contrôle du suivi Spotify et recette utilisateur restent hors validation. Les 42 revues réelles sont initialement pending ; les écritures de recette utilisent une copie séparée. Contrôles et publication consignés dans le rapport de validation.


## Révision du 6 octobre — pages et genres par morceau

Autorisation utilisateur : préserver sa revue terminée des 42 artistes, retirer les textes redondants, rendre les catégories du Récap cliquables, valider des pages de 100 maximum, conserver les artistes écartés avec idgaf. Les valeurs sans information affichent Non/Garder ; aucune preuve de carrière n'est inventée. Cette demande remplace le défilement continu et la sauvegarde limitée aux seules corrections.

Sauvegarde privée du review.json existant et des 42 valeurs effectives avant édition. Il contient dix corrections explicites ; les autres valeurs étaient acceptées par défaut. Son empreinte SHA-256 reste identique après la recette. Aucune sauvegarde de test sur ce dossier réel. Les valeurs explicites, liens, notes et exceptions Producer/DJ restent prioritaires.

Nouveau endpoint same-origin PUT /api/page : 1 à 100 artistes, validation intégrale puis écriture atomique. Les autres pages restent intactes. idgaf est dérivé du tri dans les lectures/export et enregistré lors d'une validation ; aucun artiste, crédit ni morceau n'est supprimé. La base MTEE n'est pas modifiée.

Politique de genres dans scripts/track_genre_audit.py : découper les tags composés, ignorer Alternative/Dance/Pop/Electronic/Electronica et valeurs génériques, conserver les genres précis. Un contexte de carrière explicite et sourcé peut rejeter House mais ne fournit jamais le genre de remplacement. L'absence de House dans une liste de genres d'artiste ne suffit pas à le rejeter. Le fichier privé genre-rules.json contient les corrections par track_id et contextes facultatifs par artist_id. La correction d'un morceau ne s'étend pas aux autres productions. Phoneline reçoit la correction DnB demandée par l'utilisateur ; son tag House rejeté est signalé au Récap et son tag original reste visible. Aucun classement audio automatique ni taxonomie complète n'est annoncé.

Contrôles : 36 tests passent (limite 100/101, atomicité, autre page préservée, idgaf/export, tags composés, contexte sourcé et correction isolée par morceau), Ruff et syntaxe JavaScript. Recette navigateur sur copie : catégorie Producer puis validation de 27 lignes, catégorie bootleg ouvrant le bon filtre, alerte Phoneline ouvrant sa ligne. Sur 2 000 artistes fictifs : 100 lignes et 20 pages ; validation de la page 2 laissant le brouillon MC de la page 1 en attente, puis validation de celle-ci. Captures desktop dans le panneau et mobile 390 × 844 ; aucun débordement global, tableau horizontal sur mobile. Aucun build Windows.


## Révision du 6 octobre — collection complète et validations en base

La nouvelle demande autorise toute la collection et la persistance des validations dans la base MTEE, sans interface QML ni actions Spotify. Elle remplace les limitations en lecture seule de cet outil. Le premier import charge 2 828 morceaux et 1 976 artistes établis ; 16 morceaux sans crédits confirmés restent visibles, sans inventer de crédits ni transformer les profils provisoires en artistes établis. Les 42 validations du pilote, dont six idgaf, sont importées une fois ; les enregistrements déjà présents en base restent prioritaires.

Stockage indépendant : scripts/artist-review-migrations/001_artist_enrichment.sql crée artist_enrichment_schema (version 1) et artist_enrichment_reviews dans la base existante. Une sauvegarde SQLite cohérente précède cette migration. Cette extension autonome ne modifie ni PRAGMA user_version (19), ni l'historique des migrations principales, ni les crédits, titres, fichiers ou playlists. Cela préserve l'ouverture par l'application existante sans build Windows. Les rôles, profils, tri, tags, notes, validation et observations sourcées sont conservés séparément et liés à artists par clé étrangère.

ReviewDatabase utilise des connexions par opération, foreign_keys activé et un timeout borné. Une validation de page écrit tous ses artistes dans une transaction ; aucune transition visuelle avant sa réussite. SQLite devient la source de vérité du serveur avec --database ; le JSON historique n'est pas réécrit en miroir. Sans --database, la validation reste disponible en JSON atomique. Les Validés sont éditables et restent validés après correction. La page à revoir est recalculée après chaque validation : le lot suivant remplace les lignes retirées. Les brouillons hors page restent conservés. L'export distingue validation_state et validated_at.

scripts/artist_full_collection.py --database <base> --pilot <pilote> --output <nouveau-dossier> --import-validated-pilot prépare le snapshot intégral dans une transaction en lecture seule, copie les preuves/choix/règles de genres, puis importe les choix validés du pilote. Un dossier existant est refusé. Relancer le serveur : scripts/artist_pilot_server.py --output <collection-privée> --database <base> --port 8765. Les autres artistes sont chargés avec les défauts Non/Garder et un état À enrichir : aucune recherche web ou identité n'est inventée. Cette livraison charge la collection ; elle ne prétend pas avoir réalisé l'audit des 1 934 autres artistes.

Contrôles : 40 tests passent, dont chargement des morceaux sans revue et artistes sans crédits, import idempotent des 42 choix, conservation des corrections et observations, sauvegarde préalable, transaction entièrement annulée sur clé étrangère invalide, reprise et autres pages non validées. Recette sur copie cohérente de la base : 42 Validés, validation de 100 supplémentaires donnant 142 Validés et 1 834 à revoir, changement effectif du premier artiste visible, onglet Validés éditable. La base réelle reçoit seulement les 42 choix déjà validés par l'utilisateur : 42 lignes d'enrichissement, six idgaf, 2 828 morceaux, 2 358 profils (dont 1 976 établis), version principale 19, quick_check ok et zéro violation de clé étrangère. Le fichier original de revue reste intact. Captures desktop/mobile ; aucun débordement global. Recherche et pages de 100 pour les morceaux également.

Compatibilité vérifiée sur la copie : Database.migrate() ne demande aucune migration principale avec les nouvelles tables ; ouverture du schéma 19 acceptée. Recherche Phoneline dans les 2 828 morceaux et filtre Producer ouvrant les Validés vérifiés. Correction d’un artiste validé en mode JSON conservant son état couverte par test. La copie de review.json importée est identique au pilote original.

## 2026-10-06 — Worker préparé, démarrage explicite

Demande : automatiser l'enrichissement via l'abonnement OpenAI et le monitorer dans le front autonome, sans lancer le job pendant la préparation. L'utilisateur a choisi low pour GPT-6 Luna, minimal n'étant pas pris en charge. Implémentation : scripts/artist_enrichment_worker.py, phases MusicBrainz puis recherche web/audit par codex exec, réponse structurée, file JSON atomique privée, verrou interprocessus, contrôles same-origin et onglet Job. Lots de cinq, configurables 1–10 ; un audit à la fois, limite dix minutes, pause après le lot, arrêt/cancel, reprise du cache et relance explicite des erreurs. Les échecs mettent en pause sans fallback API/modèle ni boucle de relance.

Authentification vérifiée à chaque démarrage par login status ; seules les connexions ChatGPT sont acceptées. Variables API retirées, fournisseur et méthode ChatGPT imposés, configuration utilisateur ignorée. Session éphémère et sandbox read-only dans un dossier temporaire extérieur au dépôt. Les 42 Validés ne sont pas traités ; les propositions n'écrivent jamais les décisions humaines en SQLite. Nouvelle validation pendant un audit prioritaire sur sa publication. Aucun suivi Spotify ni genre de morceau automatique.

Validation : 55 tests ciblés passent, dont worker inactif, publication sans validation, audit incomplet/profil sans source refusés, priorité d'une validation concurrente, pause, arrêt, redémarrage inactif, reprise MusicBrainz, refus de l'auth API, suppression des variables API, verrou interprocessus et protocole subprocess avec un faux Codex local. Aucun appel IA ni recherche MusicBrainz réels pendant ces tests. Front vérifié depuis les sources : Job Non démarré, 1 934 en attente, 42 Validés ; desktop/mobile sans débordement global. Aucun build Windows. Lancement réel et qualité/disponibilité du modèle non vérifiés conformément à la demande. Contrat opérationnel : scripts/artist-pilot-web/AUTOMATION.md.
