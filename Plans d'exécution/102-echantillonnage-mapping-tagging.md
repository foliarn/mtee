# Étape 102 — Échantillon de la collection pour préparer le mapping et le tagging

Ce document est un ExecPlan à exécuter avec Luna selon `PLANS.md`. Sa préparation est documentaire. L'utilisateur lancera l'étude dans une autre session et rapportera les résultats pour décider de l'implémentation. Le lancement de cette étude autorise uniquement son outillage et son diagnostic ; les fonctions de catalogue Artists, extension Brave, écriture des tags et renommage restent à concevoir ensuite.

## Objectif et résultat observable

Inventorier en lecture seule la collection indiquée par l'utilisateur, puis examiner au plus 150 fichiers distincts. Produire un rapport exploitable pour choisir les règles d'identification des artistes, les sources de correspondances et le traitement des fichiers sans tags. Le résultat attendu comprend les proportions réellement observées, les ambiguïtés concrètes, les propositions de titres/artistes/noms de fichiers et ce qui nécessite encore une vérification humaine ou externe.

L'étude ne promet pas d'identifier tous les fichiers. Une absence de preuve doit rester visible. Elle doit se terminer avec ses résultats locaux même si aucune API ni donnée Shovel n'est disponible.

## Progress

- [x] 2026-10-01 — Préparer le protocole, les décisions utilisateur, les livrables et la consigne de lancement Luna.
- [x] 2026-10-01 — 102.0 : l'utilisateur a indiqué la racine; vérification directe du dossier et sortie privée ignorée par Git.
- [x] 2026-10-01 — 102.1 : créer l'outil de diagnostic en lecture seule et onze tests synthétiques ciblés.
- [x] 2026-10-01 — 102.2 : inventaire stable et tirage reproductible des groupes random et targeted.
- [x] 2026-10-01 — 102.3 : examiner les 150 lignes au moyen des tags bruts, de la vue MTEE, des noms et du contexte de dossier; garder toutes les confirmations à not_checked.
- [x] 2026-10-01 — 102.4 : produire le rapport privé, vérifier sa structure et consigner les limites dans `docs/validation/102-echantillonnage-mapping-tagging.md`.
- [x] Publier l'outillage, les tests synthétiques et la documentation sans données de collection.

## Surprises & Discoveries

À la préparation, aucun fichier de la collection n'a été lu et aucun appel authentifié Spotify ou SoundCloud n'a été effectué. Le chemin de la collection reste à fournir lors du lancement.

Le 2026-10-01, l'outil a d'abord classé à tort des FLAC comme illisibles. La cause était l'exception `ValueError` que la vue Vorbis de Mutagen lève lorsqu'un alias demandé est absent. `MetadataReader` lisait pourtant ces mêmes fichiers. Le diagnostic attrape désormais `ValueError` au niveau de la lecture d'un alias et la traite comme une absence de clé; un test synthétique couvre ce comportement.

La première exécution contient donc des erreurs de classement et n'est pas utilisée. Une exécution séparée après le correctif a relu l'inventaire; la dernière exécution inclut ensuite les identifiants musicaux déjà présents, le filtrage des URL et les dernières priorités du tirage. Les rapports finaux référencent explicitement ce dernier dossier. `.local/validation/102/` est ignoré par la règle `.gitignore:19`.

Le dépôt possède `MetadataReader` dans `src/mtee/services/metadata_reader.py`, fondé sur Mutagen et sans appel à une méthode de sauvegarde. Ses valeurs normalisées utilisent des tuples. Sa vue simplifiée ne suffit pas à observer tous les tags bruts : les champs personnalisés, URL et divergences d'alias nécessitent une lecture complémentaire ciblée avec Mutagen en mode brut. Ne pas confondre une valeur absente du modèle MTEE avec une valeur absente du fichier.

La migration `src/mtee/persistence/migrations/002_library.sql` distingue les identifiants locaux et leurs emplacements. Ne pas ouvrir une base personnelle en écriture ni lancer un scan applicatif pour cette étude. Les essais `tests/integration/test_metadata_roundtrip.py` et `tests/integration/test_metadata_formats.py` donnent des exemples de fixtures et de préservation. Ils ne prouvent pas la compatibilité avec la version de Rekordbox de l'utilisateur.

Le projet Shovel est déclaré dans l'application sur l'hôte `tofik-local`, au chemin `/home/tofik/apps/shovel`. Ses schémas, exports et API n'ont pas été inspectés. Cette information ne garantit pas un accès depuis la session Luna.

## Decision Log

2026-10-01, utilisateur — Collection annoncée d'environ 2 850 fichiers, formats MP3, FLAC, WAV, AIFF et M4A ; usages principaux Rekordbox et MTEE. La version de Rekordbox est décrite comme la dernière ; son numéro exact n'est pas encore relevé.

2026-10-01, utilisateur — Valider les propositions par lots au départ, puis automatiser les cas fiables. Le seuil et les règles d'automatisation seront décidés après les résultats ; aucun score textuel n'est une probabilité de correction.

2026-10-01, utilisateur — Aucun accès à l'API SoundCloud. Spotify fonctionne avec une application en mode développement. Shovel est un projet fonctionnel de découverte Spotify, notamment à partir des artistes suivis, avec un historique des morceaux vus. Ce constat utilisateur ne garantit aucun endpoint ni accès supplémentaire pour MTEE.

2026-10-01, utilisateur — Reporter les pochettes. Le téléchargement TIDAL reste non prioritaire. Le guide `cover_art_guide.md` est un contexte pour plus tard, pas une instruction d'installation ou de téléchargement pour cette étude.

2026-10-01, utilisateur — Préférer `Titre.ext` quand les métadonnées sont compatibles, et `Artiste - Titre.ext` sinon. Le titre conserve son indication de version. Le titre seul reste souhaité malgré les homonymes ; aucune règle de suffixe de collision n'a été expressément validée. Le diagnostic signale ces collisions sans choisir un renommage définitif.

2026-10-01, utilisateur — Les fichiers sont déjà utilisés dans Rekordbox ; une réanalyse est acceptable. Cela n'est pas une autorisation de supprimer sa base ou ses données. Une réanalyse ne prouve pas une reconstruction des playlists et hot cues ; l'étude ne les modifie pas.

2026-10-01, Codex — Retenir un inventaire exhaustif léger, puis 100 fichiers au hasard et 50 cas difficiles. Le nombre 150 est un budget d'étude proposé, pas une exigence statistique ni un engagement de précision. La partie ciblée sera rapportée séparément.

2026-10-01, Codex — Exécuter l'étude sans réseau obligatoire. Les URL déjà contenues dans les fichiers et les exports locaux éventuellement fournis sont des indices utilisables. L'absence d'API SoundCloud n'est pas à compenser par des endpoints privés, cookies récupérés ou identifiants tiers. Ne pas solliciter de clé Spotify pour terminer ce lot.

2026-10-01, Codex — Ajouter au JSONL les tags bruts et la vue normalisée fournie par `MetadataReader`, afin de rendre visibles les alias et divergences au lieu de prendre l'une des deux vues pour une vérité exhaustive. L'inventaire rechargé reste une photographie figée et ne réécrit pas les données de sélection.

2026-10-01, Codex — Mutagen peut signaler par `ValueError` une clé Vorbis absente; traiter cette exception comme l'absence de l'alias, sans déclarer le fichier FLAC illisible. La première exécution est conservée comme trace locale, puis un nouveau dossier d'exécution devient la source du rapport.

2026-10-01, Codex — Conserver uniquement les identifiants musicaux locaux issus de champs explicitement identifiés et les URL de domaines musicaux reconnus; retirer paramètres et fragments d'URL et ignorer les champs dont le nom évoque un jeton ou un secret. Ne pas inférer de nouvel identifiant externe.

## Périmètre et exclusions

Luna crée un petit outil de diagnostic et ses tests synthétiques, l'exécute depuis les sources sur les racines explicitement indiquées, puis examine ses résultats. Aucun changement QML, table Artists, migration SQLite, extension navigateur, tagging, renommage, déplacement, conversion, téléchargement, extraction de pochettes, analyse BPM/tonalité ou fingerprinting audio n'est requis. Les services d'écriture existants ne sont pas appelés. Les maquettes produit et la taxonomie viendront après cette étude.

Ne pas lancer `scripts/build_windows.ps1` ni `scripts/smoke_packaged.ps1`. Ne pas créer de nouvelle session, contacter une autre session ou déléguer l'exécution automatiquement : l'utilisateur lancera Luna lui-même.

## Contexte technique et fichiers à consulter

Commencer par `AGENTS.md`, `PLANS.md`, l'addendum correspondant de `PLAN.md` et ce plan. Utiliser le graphe pour cibler les composants avant leur lecture ; la source prévaut sur le graphe. Inspecter l'état Git et ne pas intégrer les changements préexistants à ce lot.

Relire `src/mtee/services/metadata_reader.py`, `src/mtee/domain/metadata.py`, les adaptateurs de `src/mtee/services/metadata_adapters/`, `tests/unit/test_metadata_reader.py` et les tests d'intégration cités plus haut. Réutiliser les bibliothèques déjà verrouillées dans `pyproject.toml` et `uv.lock`. Ne pas modifier les composants de production pour enrichir le diagnostic : la lecture brute complémentaire appartient à l'outil d'étude.

## Jalon 102.0 — Racines et sorties

Si les racines audio ne figurent pas dans le message de lancement, demander une seule fois leur chemin et attendre cette donnée avant le scan. Ne pas parcourir les disques ou dossiers personnels pour deviner la collection. Plusieurs racines sont possibles ; leur donner des alias locaux `R1`, `R2`, etc. Exclure les jonctions et liens symboliques par défaut et dédupliquer les chemins physiques recouverts par plusieurs racines. Les copies physiques distinctes restent des fichiers distincts ; les hard links éventuels sont signalés.

Créer une sortie datée sous `.local/validation/102/<run_id>/`, extérieure aux racines scannées. Vérifier que `.local/` est ignoré par Git avant d'y écrire des données. Ne jamais versionner les noms de morceaux, artistes personnels, chemins, exports de collection, audio, bases, jetons ou cookies. Les sorties restent locales ; l'utilisateur choisira celles qu'il transmet dans cette conversation.

Un nouveau lancement utilise un nouveau dossier ; ne pas écraser les résultats précédents. Enregistrer version du script, commit de base, paramètres, versions Python/Mutagen, date et graine. Une photographie de l'inventaire, et non la graine seule, définit un tirage reproductible.

## Jalon 102.1 — Outil à créer et tests

Créer `scripts/audit_mapping_sample.py` et `tests/unit/test_mapping_sample_audit.py`. L'outil doit pouvoir être appelé sans fenêtre MTEE et ne doit importer aucun service d'écriture ni initialiser une base. Si une décomposition est nécessaire, conserver ses modules d'aide sous `scripts/` et documenter leurs chemins. Ne pas créer un moteur de production à ce stade.

Le contrat de commande proposé est : `--root` répétable, `--output`, `--seed` (défaut 102), `--random-size` (défaut 100), `--targeted-size` (défaut 50). Un mode `--inventory-input` recharge un inventaire existant pour reproduire la sélection sans rescanner ; il est incompatible avec `--root`. Créer ces options pendant ce jalon : elles ne sont pas présentées comme existantes aujourd'hui.

Tests utiles : tirage reproductible sur inventaire figé indépendamment de l'ordre d'énumération ; absence de doublons entre sous-échantillons ; petites populations ; formats rares ; fichiers illisibles ; données Unicode et valeurs multiples ; conservation des indications remix/live/extended ; collision Windows après assainissement ; racines recouvertes et sortie dans une racine refusée ; empreinte SHA-256 inchangée de fixtures synthétiques avant/après le parcours complet. Inclure un WAV synthétique sans tags et un WAV avec tags pour distinguer absence de métadonnées et format non pris en charge. Utiliser les fixtures disponibles pour les autres formats sans imposer l'installation d'un nouveau runtime.

## Jalon 102.2 — Inventaire et tirage

### Inventaire léger de toute la collection

Énumérer récursivement MP3, FLAC, WAV, AIFF/AIF et M4A, sans filtrer les fichiers illisibles hors du rapport. Classer les autres extensions par nombre, sans lire des documents personnels. Ne pas convertir AIF en AIFF ; relever la différence éventuelle de prise en charge par MTEE.

Pour chaque fichier, produire une ligne JSON structurée : `item_id` local opaque, alias de racine, chemin relatif privé, extension, conteneur et codec détectés lorsque disponibles, taille, `mtime_ns`, durée, statut/erreur de lecture, valeurs titre/artistes/album/artiste d'album/genre/date/BPM/tonalité, version ID3 si disponible, noms des champs texte et identifiants/URL musicaux pertinents déjà présents. Préserver les listes et valeurs originales. Ne pas sérialiser les blocs binaires ni le contenu des images ; ne pas rechercher les pochettes.

Lire les tags bruts de façon ciblée pour distinguer un manque réel, un alias non lu par MTEE, des valeurs contradictoires et une métadonnée composée uniquement d'espaces. Conserver les indices de provenance et les formes de crédits comme hypothèses séparées. Ne pas déduire qu'un fichier vient de SoundCloud parce qu'il n'a pas de tags. Écarter secrets, paramètres de téléchargement signés et données non musicales des exports destinés au retour ; une URL de page musicale canonique peut être conservée.

Relever les statistiques fichier avant/après chaque lecture. Signaler les fichiers modifiés ou disparus pendant l'étude et les exclure des conclusions stables, sans les remplacer silencieusement dans un tirage figé. Ne pas employer `atime` pour conclure à une modification. Expliquer l'écart entre les quelque 2 850 fichiers annoncés et les fichiers effectivement observés.

### Sélection reproductible : deux groupes séparés

Trier l'inventaire stable par alias de racine et chemin relatif avant le tirage. Tirer uniformément, sans remise, `min(100, N)` fichiers avec la graine 102 ; ce groupe porte le label `random`. Ne pas le rééquilibrer après observation des résultats.

Sélectionner ensuite `min(50, N - random_count)` fichiers supplémentaires avec le label `targeted`, selon les priorités ci-dessous. L'ordre entre candidats équivalents est déterminé par une permutation reproductible avec une graine dérivée documentée. Un fichier peut porter plusieurs motifs, mais il compte une seule fois.

| Priorité | Motif à couvrir dans la partie ciblée |
|---|---|
| 1 | Compléter la présence de chaque format jusqu'à cinq fichiers dans l'échantillon total, si la population le permet ; choisir d'abord les formats les plus rares |
| 2 | Titre et artiste absents, puis artiste seul absent : jusqu'à quinze ajouts |
| 3 | Divergence titre/nom de fichier, séparateurs multiples, crédits composés, remix/edit/bootleg/live/extended : jusqu'à quinze ajouts |
| 4 | Noms d'artistes proches, caractères/accents/casse, plusieurs valeurs, provenance ou identifiant externe existant, collisions de noms : compléter le budget |
| 5 | Si des places restent, tirage uniforme parmi les fichiers restants |

Arrêter dès le budget total ciblé atteint. Documenter les quotas non remplis et les catégories absentes ; ne pas inventer de cas pour atteindre 150. Les fichiers illisibles restent éligibles. Ne pas fusionner des artistes en séparant aveuglément `&`, `/`, `x` ou `feat.`. La comparaison normalisée ne remplace jamais la forme affichée originale.

Les statistiques exhaustives viennent de l'inventaire. Les observations manuelles du groupe `random` et celles du groupe `targeted` ont des dénominateurs séparés ; ne pas présenter le pourcentage combiné des 150 comme une estimation de toute la collection. Aucun taux de succès d'identification ne peut être calculé sur des propositions non vérifiées.

## Jalon 102.3 — Revue locale et propositions

Examiner chaque ligne sélectionnée en rapprochant tags bruts, vue MTEE, nom, dossier et indices de provenance. Produire une proposition de titre, indication de version, artistes/crédits et nom final uniquement quand des indices la soutiennent ; garder les champs inconnus vides. Conserver les variantes possibles au lieu de choisir arbitrairement.

Employer les statuts `supported_by_local_evidence`, `needs_review`, `insufficient_evidence` et `unreadable`. Le premier signifie une cohérence des indices locaux, pas une identité musicale prouvée. Pour une confirmation externe ou humaine, conserver un champ distinct `verification_status` avec `not_checked`, `confirmed` ou `rejected`, l'auteur de la vérification et sa preuve. Au démarrage, toutes les identifications sont `not_checked`.

Chaque proposition a une justification concrète, les champs sources, les contradictions, une prochaine action et un éventuel lien existant. Exemples de prochaine action : demander à l'utilisateur, examiner une URL SoundCloud déjà présente, comparer à un export Shovel, rechercher le titre une fois les crédits établis. Les nouveaux identifiants Spotify/SoundCloud restent vides en l'absence de preuve.

Regrouper les variantes d'artiste en candidats de rapprochement, avec le nombre de fichiers concernés dans l'inventaire et des exemples de l'échantillon. Distinguer artiste principal, featuring, remixeur et compte de publication quand les données le permettent. Une proximité de nom n'autorise pas une fusion. Mesurer combien de fichiers pourraient bénéficier d'une seule décision de groupe sans les déclarer corrigés.

Simuler le renommage dans les dossiers actuels, sans déplacer ni aplatir la collection. `Titre.ext` est la préférence ; conserver remix/version dans le titre. Si le titre est inconnu, ne proposer aucun nom. La branche `Artiste - Titre.ext` nécessite une incompatibilité documentée ; si Rekordbox n'a pas été testé, garder `compatibility_status=not_tested` plutôt que conclure à l'incompatibilité. Détecter noms Windows réservés, caractères interdits, noms vides, points/espaces terminaux, longueurs et collisions sans casse après assainissement. Comparer aux autres fichiers existants du dossier, y compris hors échantillon. Marquer les suffixes éventuels comme options non validées. Aucun écrasement.

Ne pas lancer une intégration Shovel ou une campagne de recherches web dans ce lot. Si l'utilisateur fournit déjà un export local exploitable, noter son schéma et utiliser ses identifiants comme indices séparés, avec la provenance. `Vu dans Shovel`, `suivi/aimé` et `possédé localement` restent trois relations différentes. L'absence d'export n'empêche pas la clôture.

Préparer dans le rapport dix à vingt cas prioritaires à faire confirmer par l'utilisateur : groupes à fort impact, versions ambiguës, fichiers sans artiste, collisions. Ne pas attendre toutes les réponses pour livrer le diagnostic. Ces cas sont une file de revue, pas un taux de précision mesuré. La compatibilité effective Rekordbox est reportée à un essai sur copies ; relever sa version exacte seulement si elle est facilement disponible ou fournie, sinon écrire « non relevée ».

## Jalon 102.4 — Livrables et retour à cette conversation

Tous les fichiers ci-dessous contenant des données de collection restent dans le dossier privé de la session. Ils doivent être lisibles en UTF-8. JSON/JSONL sont les formats canoniques ; un CSV de revue peut être ajouté avec protection contre les valeurs interprétables comme des formules par un tableur.

| Fichier privé | Contenu |
|---|---|
| `run.json` | Paramètres, versions, graine, racines privées et erreurs globales |
| `inventory.jsonl` | Inventaire complet et indices locaux, sans contenu binaire |
| `sample.jsonl` | Sélection figée, labels random/targeted et motifs |
| `review.jsonl` | Propositions, raisons, contradictions et vérifications par item_id |
| `artist_candidates.json` | Variantes et groupes possibles, sans fusion appliquée |
| `rename_preview.jsonl` | Noms proposés, obstacles, collisions et compatibilité non vérifiée |
| `summary.json` | Compteurs avec dénominateurs et catégories inconnues |
| `rapport-retour.md` | Rapport autonome à transmettre dans la présente conversation |

Le rapport commence par le nombre de fichiers observés, les formats, l'état de lecture, les tags titre/artiste absents et la taille effective des deux groupes. Il présente ensuite les familles de problèmes et leurs exemples, les regroupements d'artistes à fort impact, les limites des propositions, les collisions, les dix à vingt décisions prioritaires, puis les recommandations pour le prochain lot. Il distingue ce qui a été mesuré exhaustivement, observé dans le groupe aléatoire, choisi dans le groupe ciblé et non vérifié.

Pour faciliter le partage, `rapport-retour.md` et `summary.json` n'incluent aucun chemin absolu, secret ou export brut de base ; référencer les `item_id` et alias. Le rapport peut contenir les titres et artistes utiles à la revue, explicitement présentés comme données personnelles à transmettre volontairement. La version destinée au dépôt dans `docs/validation/102-echantillonnage-mapping-tagging.md` contient seulement la procédure, les tests synthétiques, l'état de réalisation et les limites, sans exemples ni contenu de la collection.

L'utilisateur transmet en priorité `rapport-retour.md` et `summary.json`. Si une ambiguïté exige davantage de détails, il peut joindre les lignes concernées de `review.jsonl` et `artist_candidates.json`. Aucun fichier audio n'est nécessaire pour ce premier retour.

## Commandes d'exécution après création de l'outil

Depuis la racine MTEE, commencer par l'état Git et les chemins. Les commandes d'audit et de test suivantes ne deviennent utilisables qu'après le jalon 102.1. Remplacer les chemins d'exemple par les racines fournies par l'utilisateur ; ne jamais les exécuter littéralement.

    git status --short --branch
    git check-ignore .local/validation/102/probe.txt
    uv run ruff check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py
    uv run ruff format --check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py
    uv run pytest tests/unit/test_mapping_sample_audit.py tests/unit/test_metadata_reader.py
    uv run python scripts/audit_mapping_sample.py --root 'D:\CHEMIN_FOURNI_PAR_UTILISATEUR' --output '.local/validation/102/run-001' --seed 102 --random-size 100 --targeted-size 50

Exécuter d'abord le parcours complet sur fixtures synthétiques et vérifier leurs empreintes avant/après, puis sur la collection. Compléter les fichiers JSON de propositions et le rapport lors de la revue : le script d'inventaire n'est pas supposé reconnaître automatiquement des identités musicales. Si `uv.lock` ou l'environnement doit être synchronisé, suivre `PLANS.md` ; aucun téléchargement de binaire d'analyse audio n'est nécessaire.

## Critères d'acceptation et reprise

Le même inventaire et les mêmes paramètres produisent les mêmes identifiants sélectionnés. Le nombre total est `min(150, N)` lorsque les paramètres par défaut sont employés, sans répétition. Les comptes d'erreur et les exclusions sont explicites. Les petits corpus et catégories vides sont acceptés avec justification. Tous les items sélectionnés ont une entrée de revue, y compris les inconnus et illisibles.

Aucun fichier audio, tag, nom ou base MTEE/Rekordbox n'a été écrit par l'outil. Les tests sur copies synthétiques vérifient l'intégrité par SHA-256 ; les observations de taille/mtime sur la collection détectent des changements ordinaires mais ne constituent pas une preuve cryptographique exhaustive. Toute modification concurrente est signalée avec sa limite, sans être attribuée arbitrairement à l'outil.

En cas d'interruption, conserver les sorties partielles et leur état incomplet. Reprendre à partir de l'inventaire figé ou créer une nouvelle session si les sources ont changé. Aucun nettoyage récursif ni restauration de fichiers audio n'est requis. Une erreur d'accès isolée n'arrête pas tout le diagnostic ; une racine invalide ou une sortie imbriquée dans la collection arrête avant le scan.

Le rapport peut conclure qu'une part importante ne peut pas être identifiée avec les seuls indices locaux. C'est un résultat valable. Ne pas extrapoler une fiabilité d'automatisation ni annoncer une compatibilité Rekordbox non testée. L'étude s'arrête à la remise des résultats ; l'implémentation du catalogue et l'application de corrections demandent un prochain cadrage.

## Livraison Git

À la préparation : vérifier les liens, l'UTF-8 et le diff des seuls documents, puis commit documentaire et push conformément à `PLANS.md`. Aucun test applicatif ni scan réel n'est annoncé.

À l'exécution par Luna : maintenir les quatre sections de suivi, tester l'outil, exécuter réellement son parcours depuis les sources, puis committer explicitement le script, ses tests synthétiques et les documents autorisés. Examiner les fichiers indexés, ne pas inclure les modifications préexistantes ni `.local/`. Faire `git diff --cached --check`, inspecter le diff, synchroniser prudemment le distant et pousser sans force. Vérifier la publication. Un blocage réseau doit être rapporté sans inventer un push réussi. Aucun build Windows.

Sujet indicatif du commit d'exécution : `Ajoute le diagnostic local pour préparer le mapping musical`. Le corps décrit la lecture seule, le tirage, les contrôles réalisés et les limites externes. Le rapport final indique les chemins des deux fichiers à retourner, les commandes effectivement exécutées et le commit publié.

## Outcomes & Retrospective

L'étude a été exécutée le 2026-10-01 depuis les sources. L'inventaire final et l'échantillon, les propositions de revue et l'aperçu de renommage sont conservés sous `.local/validation/102/run_final_03/`; ils contiennent des données personnelles et restent ignorés par Git. Le rapport destiné au retour et `summary.json` se trouvent dans ce même dossier. L'inventaire détaillé a été vérifié stable par taille et `mtime_ns` autour de la lecture. Les sorties et exemples de collection n'ont pas été copiés dans le dépôt.

Les propositions restent des indices, jamais des confirmations d'identité. Aucune écoute, recherche réseau, connexion Shovel, appel Spotify/SoundCloud, export Rekordbox, écriture de tag ou renommage n'a été fait. La version de Rekordbox n'est pas relevée et la compatibilité n'est pas testée. Les décisions utilisateur sur les 20 cas prioritaires et les rapprochements d'artistes restent en attente; aucune automatisation ne peut être déduite de ce rapport.

Contrôles réellement exécutés : onze tests ciblés via `rtk proxy uv run python -m pytest tests/unit/test_mapping_sample_audit.py -q`; `uv run ruff check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py`; `uv run ruff format --check scripts/audit_mapping_sample.py tests/unit/test_mapping_sample_audit.py`; validation de la structure JSON/JSONL et des compteurs des livrables locaux; `git diff --check`. L'exclusion `.local/validation/102/` a été confirmée par `git check-ignore`. Aucun build Windows n'a été lancé. Le rapport versionné ne contient pas de données de collection.

## Consigne prête à copier dans Luna

    Exécute le plan « Plans d'exécution/102-echantillonnage-mapping-tagging.md » de MTEE jusqu'au rapport d'échantillonnage. Lis AGENTS.md et PLANS.md. Si je n'ai pas donné les racines de ma collection, demande-moi uniquement ces chemins avant de scanner. Crée et teste l'outil de diagnostic, inventorie toute la collection en lecture seule, puis examine au maximum 100 fichiers aléatoires et 50 cas ciblés selon le plan. Ne modifie aucun audio, tag, nom de fichier ni base MTEE/Rekordbox. Aucun accès API SoundCloud ; Spotify en mode développement n'est pas une dépendance de ce lot. Ne développe ni extension, ni catalogue Artists, ni traitement de pochettes, ni intégration TIDAL/Shovel. Produis rapport-retour.md et summary.json dans le dossier privé prévu, ainsi que les fichiers de détail. Sépare observations, hypothèses et confirmations ; termine même si des fichiers restent non identifiés. Maintiens le plan, vérifie les résultats et publie uniquement l'outillage, les tests synthétiques et la documentation sans données personnelles. Préserve les changements Git préexistants. Aucun build Windows. Termine en donnant les liens des deux fichiers que je dois rapporter à la conversation de cadrage.

Révision documentaire : 2026-10-01 — Protocole initial adapté à l'absence d'API SoundCloud, au mode développement Spotify et au report des pochettes.
Révision d'exécution : 2026-10-01 — Jalon 102.1 réalisé : ajout de l'outil autonome, de la sortie JSONL de l'inventaire et de l'échantillon, de la comparaison des tags bruts et normalisés, et des tests synthétiques. Le scan réel attend les chemins explicites de la collection.
Révision de clôture : 2026-10-01 — Exécution de 102.0 à 102.4, correction d'un faux état illisible Mutagen/FLAC, ajout de tests sur les alias et identifiants musicaux, revue locale de l'échantillon, production du rapport privé et ajout du rapport de validation sans données personnelles.
