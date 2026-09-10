# Étape 14 — Préparer et intégrer Spotify/Shovel selon les accès vérifiés


Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il développe le jalon K et la partie Spotify/Shovel du §4.11 de `PLAN.md`. Il décrit les vérifications qui rendent une intégration possible; aucun contrat Shovel ni droit d'accès Spotify n'est considéré comme acquis.

## Objectif et résultat observable


L'utilisateur peut relier, lorsque les accès et formats le permettent, une découverte ou une playlist externe à des morceaux de sa collection locale. Une proposition de rapprochement présente les versions candidates et ses raisons; l'utilisateur peut accepter un lien, choisir une autre version ou laisser l'élément sans correspondance.

Spotify et Shovel sont deux capacités facultatives avec des statuts distincts. L'absence d'accès à l'une n'empêche pas l'autre, et aucune indisponibilité réseau ne bloque l'explorateur, la lecture, les métadonnées ou les playlists locales.

La livraison peut être une étude suivie d'un adaptateur utilisable, d'un import de fichier documenté, ou d'un report motivé si les conditions ne sont pas réunies. L'interface ne doit pas annoncer une connexion fonctionnelle avant un essai réel avec les accès disponibles. Ce jalon ne télécharge pas d'audio de Spotify et ne promet pas la disponibilité locale d'un morceau à partir d'une référence distante.

## Progress


- [x] 2026-09-10 — Plan préparé; contrats, comptes et accès externes restent à vérifier.
- [ ] Identifier précisément Shovel et documenter son contrat autorisé d'échange.
- [ ] Vérifier les capacités Spotify disponibles pour le compte/application de test.
- [ ] Prototyper la normalisation des références et l'aperçu des correspondances locales.
- [ ] Intégrer uniquement les adaptateurs dont les préconditions sont satisfaites.
- [ ] Valider erreurs, révocation, hors connexion et distribution Windows, puis committer et pousser.

## Surprises & Discoveries


Aucun appel fournisseur n'a été effectué pour préparer ce plan. Noter ici les différences constatées entre documentation, capacités accordées au compte, formats exportés et comportement réel. Une réponse inaccessible ou une restriction fournisseur est un résultat d'étude à préserver, pas une raison d'inventer un endpoint de remplacement.

## Decision Log


2026-09-10, Codex — Définir Shovel avant de développer un adaptateur. Motif : `PLAN.md` nomme ce service sans contrat, URL de produit ni format d'échange; plusieurs produits peuvent porter un même nom.

2026-09-10, Codex — Vérifier Spotify au moment de l'intégration. Motif : l'accès et les fonctionnalités disponibles sont des préconditions externes qui peuvent changer; ce plan n'attribue aucun droit à un compte encore non inspecté.

2026-09-10, Codex — Commencer par un flux explicite entrant vers la collection locale. Motif : la première valeur recherchée est le rapprochement des découvertes et playlists; une publication externe demande des capacités et une interface d'approbation distinctes.

2026-09-10, Codex — Ne pas déduire l'identité d'un enregistrement de sa seule similarité. Motif : les versions radio, extended, live, remix, remaster et extraits peuvent partager des attributs sans être interchangeables.

## Outcomes & Retrospective


À compléter séparément pour Spotify et Shovel : accès vérifié, opérations livrées, formats, compte de test, limitations et cas de correspondance. Si un adaptateur est reporté, identifier la condition concrète qui permettrait de reprendre. Ne pas masquer un report derrière une case de connexion décorative.

## Contexte et prérequis


MTEE est une application locale Python 3.12, PySide6/QML et SQLite, gérée par uv. Les types purs vivent dans `src/mtee/domain`, les adaptateurs dans `services`, la présentation Qt dans `models`, le stockage dans `persistence` et les vues anglaises dans `qml`. QML ne contient ni secret ni requête HTTP métier.

Les étapes 01 à 13 de la séquence doivent être livrées ou avoir une décision de report explicitement acceptée pour leur partie facultative. Les dépendances techniques directes sont les métadonnées, playlists, recherche et tâches de fond. Le ML n'est pas nécessaire pour faire correspondre une référence externe à un morceau local.

`track_id` reste un UUID interne stable indépendant du chemin et d'une empreinte de contenu. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` est immuable, avec une génération persistée. Un identifiant Spotify ou Shovel ne remplace pas ces identités internes.

Une copie convertie ou découpée possède sa propre identité et une `Derivation(source_track_id, source_revision, derived_track_id, transform, time_mapping)`. Les temps internes sont des microsecondes entières avec `TimeRange(start_us, end_us)` à borne finale exclusive. Une correspondance externe n'autorise aucun transfert implicite de repères temporels.

Métadonnées de fichier, analyses calculées et corrections manuelles restent distinctes. Une durée ou un titre venant d'un service est une observation externe avec sa provenance, pas une instruction d'écrire le fichier local. La similarité ML peut fournir un indice exploratoire, jamais une preuve suffisante de version.

Préparer dans `.local/validation/14` une base de test et des copies de fichiers comprenant plusieurs versions proches d'un titre, un remix, un live, des accents, un titre absent et des fichiers déplacés. Les exports personnels, jetons et identifiants de compte ne sont pas committés.

## Plan de travail et jalons


### Jalon 14.1 — Établir les deux contrats avant tout branchement


Pour Shovel, retrouver d'abord la référence exacte du produit dans le dépôt ou les décisions disponibles. Si elle reste inconnue au moment d'exécuter ce jalon, obtenir de l'utilisateur son URL et le flux voulu. Continuer en parallèle le modèle d'échange local et l'étude Spotify, qui ne dépendent pas de cette réponse.

Consulter la documentation officielle du Shovel identifié. Déterminer s'il existe un export de fichier, une API, une extension ou une autre interface autorisée. Relever format, version, identifiants, champs, pagination éventuelle, limites, authentification, erreurs et conditions d'usage. Ajouter un exemple minimal fourni par cet outil et autorisé à servir de fixture, sinon créer un exemple synthétique conforme au schéma documenté.

Pour Spotify, consulter la documentation officielle de la plateforme développeur et les capacités actuelles de l'application/compte de test. Documenter les opérations concrètement disponibles, restrictions, scopes, redirect URI, mode d'authentification desktop autorisé, limites d'appels, pagination, gestion de marché ou de disponibilité lorsque ces notions s'appliquent.

Enregistrer les URLs exactes et dates de consultation dans `docs/integrations/spotify-shovel-contract.md`. Séparer « documenté », « accordé à ce compte » et « testé ». Ne pas annoncer la lecture ou l'écriture d'une playlist à partir du seul fait qu'un compte Spotify existe.

Le jalon est acquis pour chaque fournisseur lorsqu'un flux précis et licite peut être reproduit avec une entrée de test. Si aucun accès exploitable n'est disponible, consigner le report et les préconditions de reprise; aucun contournement ou format supposé n'est développé.

### Jalon 14.2 — Normaliser les références et évaluer les rapprochements


Créer un modèle interne neutre pour une référence distante : fournisseur, identifiant opaque, lien d'origine, titre, artistes, durée éventuelle, version et identifiants d'enregistrement lorsqu'ils sont disponibles dans le contrat vérifié. Conserver les champs absents comme absents, sans fabriquer une durée ou une édition.

Construire d'abord un rapprochement hors réseau avec des fixtures : liens déjà confirmés, indices exacts documentés, puis candidats d'après métadonnées et durée. Les règles produisent des raisons lisibles et un statut `Confirmed`, `Needs review` ou `Unmatched`. Une égalité d'identifiant d'enregistrement ne dispense pas de vérifier la version lorsqu'un fournisseur expose des éditions ambiguës.

La validation crée une association externe vers le `track_id` choisi. Une proposition ne modifie pas les tags, ne fusionne pas deux morceaux et ne remplace pas automatiquement un fichier source par un dérivé. Les versions concurrentes restent affichées avec les éléments qui les distinguent.

Pour une playlist, préserver l'ordre et les occurrences répétées selon le contrat reçu. Afficher les éléments indisponibles ou non rapprochés dans l'aperçu. L'utilisateur peut créer une playlist locale partielle en connaissance de cause; l'application n'annonce pas un import complet lorsque des titres manquent.

### Jalon 14.3 — Connecter chaque adaptateur validé


Pour un export de fichier Shovel, implémenter le parseur du format réellement observé et sa validation. Pour une API, implémenter seulement les opérations documentées et autorisées. Les deux options restent alternatives tant que le jalon de contrat n'a pas tranché.

Pour Spotify, appliquer le flux desktop officiel actuellement prescrit. Si un flux avec PKCE est autorisé et retenu, tester code verifier/challenge, validation de l'état et fermeture du rappel local; ne pas intégrer un secret client dans une application distribuée. Si une configuration serveur est indispensable, réévaluer le périmètre et documenter le report plutôt que d'inventer un serveur implicite.

Stocker les secrets dans le mécanisme sécurisé du système via une interface dédiée et une implémentation Windows vérifiée. SQLite conserve seulement les références non secrètes nécessaires. Retirer jetons, codes d'autorisation et URLs de rappel sensibles des logs. Le chemin de base locale configurable ne doit pas rediriger les secrets vers un fichier de test en clair.

Gérer expiration, révocation, annulation de connexion, restrictions d'accès et temporisation conformément aux réponses documentées. Les tâches réseau ont un délai maximal et restent annulables. Un échec laisse visibles les données déjà importées avec leur provenance et leur date, sans les présenter comme fraîchement synchronisées.

### Jalon 14.4 — Livrer un flux compréhensible et réversible


Créer `Connections` avec un état indépendant par fournisseur : `Not configured`, `Connected`, `Access unavailable` et `Offline`. Les commandes utiles sont `Connect`, `Import playlist`, `Review matches` et `Disconnect`, selon les capacités réellement livrées.

L'import présente fournisseur, playlist choisie, compte concerné, ordre, nombre de titres liés et cas à examiner avant l'application locale. La confirmation porte sur un aperçu stable; si la source distante change, recalculer cet aperçu plutôt que d'appliquer des données différentes.

Une éventuelle écriture externe demeure une extension de périmètre à décider après le flux entrant. Si elle est retenue et autorisée, construire un aperçu listant destination et changements exacts, puis demander une validation explicite avant toute mutation distante. Ne pas envoyer de messages à d'autres personnes dans ce jalon.

Déconnecter supprime les secrets locaux de l'intégration et arrête ses tâches. Les fichiers et playlists locales restent utilisables; leur provenance conserve le lien d'origine lorsqu'il peut être conservé selon le contrat vérifié. Documenter les contraintes de cache et de suppression imposées par le fournisseur.

## Étapes concrètes


Depuis la racine Windows du dépôt, vérifier l'état puis installer l'environnement verrouillé.

    git status --short
    git branch --show-current
    uv sync --locked

Créer d'abord `docs/integrations/spotify-shovel-contract.md`, `src/mtee/domain/external_discovery.py`, `src/mtee/services/external_matching.py` et les fixtures synthétiques dans `tests/fixtures/external_discovery`. Ces composants peuvent être développés sans accès à un compte réel.

Après validation d'un contrat, créer l'adaptateur concerné sous `src/mtee/services/integrations/spotify.py` ou `shovel.py`, avec `src/mtee/services/integrations/credentials.py`, `src/mtee/persistence/external_links_repository.py`, `src/mtee/models/connections_model.py` et `src/mtee/qml/Connections.qml`. Ne créer une dépendance fournisseur facultative que si elle remplit un besoin documenté.

Déclarer et verrouiller les éventuels extras retenus avant de documenter leur installation. L'environnement de base doit continuer à fonctionner par `uv sync --locked`; une bibliothèque HTTP ou un coffre de secrets ne doit pas être ajouté sous un nom supposé sans vérification d'installation et de distribution.

Créer les tests suivants en adaptant leurs scénarios aux adaptateurs effectivement retenus; les tests automatiques utilisent un faux fournisseur local et ne nécessitent pas de secrets.

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_external_matching.py tests/integration/test_external_discovery.py tests/ui/test_connections.py
    uv run python -m mtee --data-dir .local/validation/14
    pwsh -File scripts/build_windows.ps1

Exécuter les essais réels avec le compte de test autorisé uniquement après les essais synthétiques. Vérifier `dist/MTEE/MTEE.exe`, connecté puis hors connexion; fermer et relancer l'application pour confirmer persistance des liens et lecture locale. Ne pas enregistrer les secrets ni le contenu personnel brut dans les preuves Git.

## Validation et acceptation


Les tests unitaires couvrent les champs manquants, durées divergentes, versions concurrentes, accents, casse, homonymes et déplacements locaux. La même référence importée deux fois retrouve l'association confirmée sans doublon; une association invalidée demande une nouvelle revue.

Les tests d'intégration couvrent pagination si présente, données répétées, ordre de playlist, appel interrompu, format modifié, expiration d'autorisation, accès refusé, limitation d'appels et absence de réseau. Utiliser les codes et sémantiques réellement documentés pour chaque fournisseur au lieu d'imposer un contrat HTTP identique à tous.

Tester l'aperçu annulé, la source distante modifiée après aperçu, le fichier local manquant et l'application locale partielle. Les occurrences et absences sont explicites, et une transaction interrompue ne laisse pas une playlist prétendument complète.

Le parcours réel doit permettre de vérifier au moins une correspondance correcte, une ambiguïté de version et un élément non disponible localement. Le fait de jouer le fichier choisi confirme la version de la collection; un score de similarité seul ne satisfait pas cette vérification.

L'acceptation d'un adaptateur nécessite contrat sourcé, accès réellement testé, limites affichées, gestion des secrets vérifiée et fonctionnement local hors connexion. Un fournisseur reporté doit présenter un état exact et une condition de reprise, sans bloquer l'acceptation d'un autre flux indépendant validé.

## Reprise et réexécution


Les inspections et aperçus restent sans mutation. L'application d'un import local est transactionnelle et identifiée par sa provenance et son contenu normalisé; une relance ne duplique pas les éléments déjà acceptés. Le journal distingue la dernière tentative de la dernière importation réussie.

Un jeton expiré ou révoqué mène à une reconnexion explicite, jamais à une boucle de tentatives illimitée. Respecter les temporisations reçues; une annulation ferme les tâches en cours et ignore toute réponse tardive devenue périmée.

Conserver seulement les données de cache permises par le contrat, avec date et expiration si nécessaire. Lorsqu'un format change, refuser les champs critiques inconnus et conserver un diagnostic anonymisé; l'utilisateur peut continuer à utiliser les liens locaux déjà confirmés.

En cas d'écriture externe ultérieure, ne rejouer une requête interrompue qu'après vérification de son résultat distant ou d'un mécanisme d'idempotence officiellement supporté. Sans ce mécanisme, demander une nouvelle revue de l'état au lieu de risquer des doublons.

## Interfaces et dépendances


`ExternalReference` et `ExternalPlaylist` sont les types normalisés avec provenance et version de contrat. `ProviderCapabilities` décrit les opérations réellement disponibles; ce type ne transforme pas une opération non autorisée en fonctionnalité affichée.

`DiscoveryAdapter.capabilities() -> ProviderCapabilities` et `read_playlist(reference) -> ExternalPlaylist` isolent un fournisseur. Pour un fichier, la lecture utilise une entrée locale; pour une API, elle suit le contrat documenté. Ne pas ajouter de méthode d'écriture à une interface tant que ce flux n'est pas validé.

`ExternalMatchingService.preview(references) -> MatchPreview` retourne candidats et raisons. `apply(preview_id, choices) -> MatchResult` revalide les révisions et persiste les liens choisis. `ExternalTrackLink` associe fournisseur, identifiant opaque et `track_id`, sans supposer une unicité mondiale d'enregistrement.

`CredentialStore` permet stocker, obtenir et retirer les secrets dans le coffre système. `JobService` exécute les travaux réseau bornés et annulables. Le stockage local, les playlists, le lecteur et les modèles QML ne dépendent pas de la disponibilité d'un fournisseur.

## Preuves et livraison Git


Renseigner `docs/validation/14-spotify-shovel.md` avec les contrats sourcés, capacités de test, fixtures anonymisées, résultats hors connexion, cas de version et limitations par fournisseur. Mettre à jour les sections vivantes du plan. Un accès non disponible est mentionné comme tel, jamais comme test réussi.

Indexer les chemins effectivement créés; omettre l'adaptateur reporté et ajouter précisément les migrations ou dépendances modifiées. La commande illustrative ci-dessous cible les deux adaptateurs lorsqu'ils existent. Les exports privés, secrets, réglages de compte et données `.local` restent exclus.

    git status --short
    git diff --check
    git add -- docs/integrations/spotify-shovel-contract.md src/mtee/domain/external_discovery.py src/mtee/services/external_matching.py src/mtee/services/integrations/spotify.py src/mtee/services/integrations/shovel.py src/mtee/services/integrations/credentials.py src/mtee/persistence/external_links_repository.py src/mtee/models/connections_model.py src/mtee/qml/Connections.qml tests/fixtures/external_discovery tests/unit/test_external_matching.py tests/integration/test_external_discovery.py tests/ui/test_connections.py docs/validation/14-spotify-shovel.md "Plans d'exécution/14-spotify-shovel.md"
    git diff --cached --check
    git diff --cached

Remplacer les indications entre chevrons par le périmètre et les résultats réellement obtenus. Si seuls l'étude et le rapprochement local sont livrés, le titre doit les nommer sans promettre une connexion absente.

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step14-commit.txt'
    @'
    feat(integrations): connect verified discovery sources to local tracks

    Changes: <verified Spotify/Shovel flows, reviewed version matching and optional connection UI>
    Validation: <actual provider tests, synthetic cases, offline run and Windows package>
    Limits: <unavailable capabilities, deferred adapters, version ambiguity and cache constraints>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Exécuter les commandes successivement après réussite, sur `main` avec `origin` défini à l'étape 00 comme `https://github.com/foliarn/mtee.git`. Comparer les deux identifiants finaux. Un refus de push demande un diagnostic sans force ni réécriture; le hash réel est communiqué après le commit, sans l'inscrire dans son propre contenu.

Note de révision — 2026-09-10, Codex : création et revue du plan ; préciser les contrats à vérifier, les rapprochements de versions et l'indépendance des fonctions locales avant toute activation externe.
