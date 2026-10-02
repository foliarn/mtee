# Étape 103 — Catalogue Artists et revue locale du mapping

**Remplacé le 2026-10-02 par le [plan 104 — Artist manager](104-artist-manager-importation.md).** L'utilisateur a refusé les maquettes de 103 et fourni un nouveau sketch. Leur préparation reste un fait historique ; elles ne sont pas validées et les jalons fonctionnels ci-dessous ne doivent pas être exécutés. Les règles de renommage et d'application ont également changé : suivre 104.

ExecPlan à maintenir selon `PLANS.md`. Il succède à l'étude 102 : l'utilisateur a demandé que `run_followup_02` soit la dernière itération d'échantillonnage et que le projet continue. Ce document prépare la première tranche fonctionnelle ; la revue des maquettes précède son implémentation, conformément à `PLAN.md`.

## Objectif et résultat observable

MTEE permet de consulter un catalogue d'artistes, de proposer les artistes et le titre d'un fichier, puis de corriger et valider ces propositions par lots. Les décisions sont enregistrées localement et persistent au redémarrage. Les noms et tags des fichiers restent inchangés pendant ce lot : une décision de catalogue et une écriture audio sont deux actions distinctes. L'application des tags et des renommages fera l'objet du lot suivant, construit sur les décisions réellement validées.

Le premier résultat examinable est une maquette QML des vues `Artists` et `Match review`, avec des données fictives. Après son accord, l'utilisateur pourra faire la revue de sa collection directement dans MTEE, sans nouvelles séries de scripts d'échantillonnage.

## Progress

- [x] 2026-10-01 — Préparer le plan suivant après la dernière contre-lecture de l'étude 102.
- [x] 2026-10-02 — 103.0 — Préparer les maquettes QML, le lanceur et les captures synthétiques ; porte de validation utilisateur ouverte.
- [ ] Consigner la validation utilisateur de ces maquettes avant le code fonctionnel.
- [ ] 103.1 — Définir les contrats de catalogue, de propositions et les migrations.
- [ ] 103.2 — Porter les règles utiles du diagnostic dans un service de propositions testé.
- [ ] 103.3 — Implémenter les modèles Qt et les vues validées.
- [ ] 103.4 — Vérifier persistance, conflits, révisions et revue par lots depuis les sources.
- [ ] Actualiser le rapport de validation, committer et pousser les fichiers du lot.

## Surprises & Discoveries

La contre-lecture finale a vérifié l'identité SHA-256 de l'inventaire et de l'échantillon réutilisés, la correspondance des identifiants des lignes de revue et de renommage, et le passage des vingt tests de `tests/unit/test_mapping_sample_audit.py`. Les résultats détaillés et leurs données personnelles restent dans `.local/validation/102/run_followup_02/`.

Le nouveau diagnostic nettoie les préfixes d'artiste et préserve les valeurs multiples, mais propose moins d'artistes que la version précédente. La lecture de `_parse_filename_metadata` et `propose_metadata` dans `scripts/audit_mapping_sample.py` explique ce recul : les artistes déjà connus sont privilégiés, puis un repli exige un préfixe en capitales. Des crédits plausibles en casse mixte ou des collaborations inconnues restent vides. Ce défaut entre dans les exigences du service de production ; il ne motive pas une quatrième passe de l'échantillon.

La liste des vingt cas du rapport est filtrée sur la présence d'artistes et de titres proposés. Elle ne suffit donc pas à évaluer les cas non résolus. La maquette devra montrer aussi des fichiers inconnus, sans contradiction détectable parce que les preuves manquent. L'absence de contradiction ne constitue pas une mesure de fiabilité.

`MetadataReader` et `LibraryRepository` existent. `MetadataSnapshot` conserve plusieurs artistes, alors que `MetadataPatch` dans `src/mtee/domain/metadata_edit.py` accepte actuellement une chaîne par champ. L'écriture future de plusieurs artistes nécessitera un contrat explicite et des essais par format ; ne pas convertir dès maintenant une liste d'identités en une chaîne séparée arbitrairement par des virgules.

## Decision Log

2026-10-01, utilisateur — Arrêter les itérations de l'étude après `run_followup_02` et poursuivre le projet. Les propositions de cet échantillon ne sont pas pour autant validées individuellement.

2026-10-01, utilisateur — Le résultat recherché est artistes et titre, sans mentions promotionnelles ni champ consacré à leur conservation. A+ et Ev sont des artistes dans les collaborations explicitement signalées. Une collaboration est un crédit composé ; elle n'est pas un alias d'un seul de ses membres.

2026-10-01, Codex — Construire d'abord une revue persistante dans MTEE, avec validation manuelle par lots et raisons lisibles. Ne pas figer un seuil d'automatisation à partir des taux de propositions ou de non-contradiction de l'étude.

2026-10-01, Codex — Les artistes inconnus peuvent recevoir une hypothèse issue du nom ou du titre brut, indépendamment de leur casse. Cette hypothèse reste à valider et peut conserver un crédit composé non résolu. L'absence du dictionnaire ne doit pas devenir une interdiction de proposer.

2026-10-01, Codex — Conserver les versions musicales identifiantes, comme Remix, Extended, VIP, Sped Up Version et un nom de mix. Retirer les annotations clairement promotionnelles, techniques ou de catalogue. Les chaînes ambiguës restent éditables et signalées ; ne pas effacer automatiquement toutes les parenthèses ou tous les chiffres.

2026-10-01, Codex — Ce lot fonctionne localement. Aucun accès API SoundCloud, aucune dépendance obligatoire à Spotify/Shovel, aucun traitement de pochettes, genres ou téléchargement TIDAL. Les profils Spotify/SoundCloud peuvent être saisis manuellement sous forme de liens ; leur vérification externe reste distincte de l'identité locale.

2026-10-02, Codex — La première maquette réutilise le thème MTEE existant, avec navigation Artists/Match review et scénarios synthétiques. Les actions de correction et de validation ne changent qu'un état de démonstration en mémoire. Le backend, les décisions persistantes et toute lecture/écriture de collection restent hors périmètre jusqu'à la validation explicite des vues.

## Périmètre et prérequis

Lire `AGENTS.md`, `PLAN.md`, `PLANS.md` et ce plan. Utiliser les graphes pour cibler la lecture, puis examiner les sources et tests. Les scripts et rapports du plan 102 sont des données de recherche et une source de scénarios : ils ne deviennent pas une API publique ni une dépendance d'exécution de l'application.

Inspecter les composants actuels sous `src/mtee/domain/metadata.py`, `domain/tracks.py`, `persistence/library_repository.py`, `persistence/database.py`, `services/metadata_reader.py`, `services/jobs.py`, `models/workspace_model.py` et les composants de navigation QML. Les fichiers applicatifs peuvent contenir des modifications non committées préexistantes ; ne pas les écraser ni les inclure aveuglément dans le commit du lot.

Ne pas lire une collection en parcourant le disque sans racine fournie. Une étude privée n'est pas nécessaire pour reproduire ou tester les fonctionnalités : les fixtures sont synthétiques. Le numéro de migration sera choisi à l'implémentation en inspectant les migrations présentes, jamais présumé à partir de ce document.

## Jalon 103.0 — Maquettes examinables

Créer `docs/ux/mockups/Mapping103Review.qml`, un lanceur `scripts/review_mapping_103.py` et `docs/ux/review-103-artistes-mapping.md`. Ces fichiers sont à créer durant ce jalon ; la commande proposée ci-dessous n'existe pas avant leur création. Réutiliser les composants, dimensions, polices et couleurs MTEE existants. Lire les compétences de design applicables pendant ce travail.

La vue `Artists` montre nom, alias, nombre de morceaux associés et liens de profils éventuellement saisis. Une fiche permet de voir les morceaux liés, de corriger le nom et de distinguer les personnes des crédits de collaboration. Prévoir une commande explicite pour rattacher un alias ; ne pas fusionner automatiquement les homonymes ou noms proches. Les pochettes d'artistes sont reportées.

La vue `Match review` montre une liste filtrable et un panneau de détail : nom du fichier, artistes/titre actuels, artistes/titre proposés, raisons, conflits, édition manuelle et aperçu `Titre.ext`. Le détail expose les éléments disponibles sans imposer les clés techniques JSON. Une proposition de collaboration permet d'ajouter, retirer et réordonner les artistes ; un crédit non résolu demeure visible tant qu'aucune identité n'est choisie.

Les actions sont `Accept`, `Edit`, `Reject`, `Skip` et une acceptation de la sélection. Prévoir une confirmation de lot montrant le nombre de propositions concernées et les valeurs changées. Le libellé de validation précise qu'elle enregistre les décisions dans MTEE. Une décision rejetée ne revient pas automatiquement au prochain calcul. Un état `Unresolved` peut être conservé sans empêcher les autres décisions.

Présenter au moins les états suivants : tags complets, nom exploitable sans tags, artiste inconnu en casse mixte, collaboration inconnue, alias probable, champ à plusieurs valeurs, encodage suspect, annotation technique, vraie version musicale, absence totale de preuve, collision de nom et fichier modifié depuis la proposition. Les exemples sont fictifs. Montrer aussi une fenêtre étroite, une liste vide, le calcul en cours et une erreur récupérable.

Lancer les maquettes depuis les sources, produire des captures sans chemins ni noms personnels et un dossier de revue synthétique. Soumettre ces éléments à l'utilisateur. Arrêter avant le backend tant que cette maquette n'a pas d'accord explicite consigné ; cette porte provient de `PLAN.md` et d'`AGENTS.md`, pas d'une nouvelle validation des échantillons.

## Jalon 103.1 — Identités et décisions persistantes

Après accord, créer les contrats sous `src/mtee/domain/artists.py` et `src/mtee/domain/mapping_review.py`, puis `src/mtee/persistence/artists_repository.py` et `mapping_review_repository.py` avec une migration transactionnelle sauvegardée selon `PLANS.md`.

Un artiste possède un UUID interne stable et un nom choisi. Les alias conservent la graphie observée et le statut de leur rattachement ; le nom normalisé n'est pas une clé unique d'identité, car deux artistes peuvent porter le même nom. Un profil externe appartient à une plateforme et garde URL, identifiant facultatif et état de vérification. Un compte de label SoundCloud ne devient pas implicitement un artiste.

Les crédits relient un `track_id` local aux artistes avec ordre et rôle lorsqu'il est connu. Un crédit source composé peut rester non résolu. Préserver les `track_id` actuels, les playlists et les chemins ; ne pas ajouter maintenant une déduplication d'enregistrements musicaux. L'identifiant `item_id` d'un rapport 102 n'est pas le `track_id` de la bibliothèque.

Une proposition conserve observation source, révision du fichier, valeurs candidates, origine de chaque champ, version du moteur, raisons et état. Les décisions possibles comprennent pending/accepted/rejected/skipped/unresolved, avec historique et auteur local. Les conflits de source et l'état d'application aux fichiers sont des dimensions distinctes ; `accepted` n'est jamais synonyme de tags écrits.

Les décisions explicites priment sur un recalcul. Rendre possible leur révision sans perdre l'historique. Lorsqu'une proposition acceptée s'appuie sur un fichier ensuite modifié, conserver la décision mais signaler qu'elle doit être revalidée avant toute écriture future. Ne pas forcer un artiste inconnu à entrer dans une identité provisoire partagée par tous les fichiers.

## Jalon 103.2 — Service de propositions local

Créer `src/mtee/services/mapping_service.py`. Il utilise les observations de bibliothèque, un complément de lecture brute lorsque nécessaire et le catalogue des alias validés. Les lectures longues et calculs quittent le thread graphique par les services de tâches existants. Le moteur ne modifie pas les tags ni les décisions confirmées.

Traiter séparément extraction de candidats et acceptation d'identité. Générer des hypothèses à partir de `Artiste - Titre` même si l'artiste est inconnu, en tenant compte des noms avec tirets, du préfixe le plus long connu, de la ponctuation et des séparateurs imparfaits. Un crédit comme `Alpha & Beta` peut être proposé entier avec une décomposition candidate, sans fusion ni identité certaine. Une règle explicite confirmée sur un alias peut ensuite éclairer les autres morceaux.

Préserver toutes les valeurs artistes et toutes les possibilités de titre. Extraire un artiste depuis le tag titre est autorisé avec une provenance correcte : ne pas attribuer au tag une hypothèse provenant du nom de fichier. Comparer les crédits structurés pour éviter les faux conflits dus aux séparateurs. Ne jamais conclure que l'absence de conflit entre deux champs vides est une preuve de correction.

Nettoyer un préfixe artiste dans le titre seulement lorsque le crédit correspond à la proposition. Préserver remixeurs et versions sans substituer systématiquement le remixeur à l'artiste original. Retirer les annotations reconnues ; exposer une édition directe pour les autres. Signaler les problèmes d'encodage, sans inventer un nom corrigé.

L'aperçu de renommage utilise les métadonnées proposées, même si les tags actuels sont absents. Il reste une prévisualisation. Vérifier les collisions entre toutes les destinations proposées et les fichiers du dossier, les règles Windows et les extensions. Ne pas assimiler la lecture Mutagen à la compatibilité d'écriture Rekordbox. Ne choisir aucun suffixe automatique de collision sans décision utilisateur.

## Jalon 103.3 — Intégration Qt et validation par lots

Créer `src/mtee/models/artists_model.py` et `mapping_review_model.py`, puis les vues QML aux chemins cohérents avec le dépôt. Les noms exacts sont à consigner après la maquette. Brancher les vues au shell avec les modèles Qt ; aucun accès direct QML au système de fichiers ou aux commandes.

Le calcul sur une sélection présente progression, annulation et erreurs individuelles. L'acceptation d'un lot prend une photographie des propositions réellement sélectionnées afin qu'un changement de filtre n'en change pas la portée. Les validations enregistrent atomiquement les décisions locales ; les éléments devenus obsolètes sont signalés individuellement. Les erreurs ne sont pas présentées comme des succès partiels silencieux.

Permettre recherche d'un artiste, choix d'une identité existante, création volontaire, ajout d'alias, correction du titre et réordonnancement des crédits. Montrer séparément les décisions enregistrées et les tags actuels du fichier. Le résultat est utilisable hors connexion et après redémarrage.

## Jalon 103.4 — Vérification et recette

Créer les tests métier `tests/unit/test_mapping_service.py`, les tests de persistance `tests/integration/test_mapping_review_repository.py` et les tests Qt `tests/ui/test_mapping_review.py`. Les fixtures reprennent les formes observées avec des noms synthétiques. Vérifier particulièrement les régressions entre les versions du diagnostic : artiste inconnu en casse mixte, collaborations, tirets internes et imparfaits, plusieurs valeurs, titre contenant l'artiste, vraies versions, annotations, caractères corrompus, collisions et non-réapparition des candidats rejetés.

Tester aussi homonymes, sauvegarde et migration, reprises après interruption, annulation du calcul, révisions concurrentes, acceptation stable d'un lot et persistance des décisions manuelles. Sur un corpus synthétique, vérifier les empreintes audio avant/après le parcours pour démontrer l'absence d'écriture de ce lot. Les tests ne doivent pas se limiter à reproduire l'algorithme de parsing.

Exécuter les parcours manuels depuis les sources avec une base isolée : ouvrir Artists, calculer des propositions, corriger une collaboration, accepter/rejeter un lot, redémarrer et vérifier les décisions, puis modifier une copie audio extérieurement et observer l'obsolescence. Utiliser des copies et relever les contrôles réellement effectués. Créer `docs/validation/103-artistes-revue-mapping.md` sans donnée de collection.

## Commandes, acceptation et reprise

Depuis la racine du dépôt, les commandes suivantes deviennent disponibles aux jalons créant les fichiers concernés :

    uv run python scripts/review_mapping_103.py
    uv run pytest tests/unit/test_mapping_service.py tests/integration/test_mapping_review_repository.py tests/ui/test_mapping_review.py
    uv run ruff check src/mtee tests scripts/review_mapping_103.py
    uv run python -m mtee --data-dir .local/validation/103/manual

Adapter les vérifications de types et formatage au périmètre réellement modifié, selon `PLANS.md`. Aucun build Windows automatique. Ne pas relancer toute la collecte 102 pour valider le moteur. L'échantillon privé peut éclairer une recette facultative, mais aucune proposition de ce rapport n'est importée comme acceptée.

Le lot est terminé lorsque les vues approuvées permettent la revue, que les décisions persistent, que les inconnus restent traitables et que les fichiers audio sont inchangés. Les profils externes sont des liens saisis, pas une intégration annoncée fonctionnelle. Les futures écritures de tags puis renommages nécessitent encore la gestion des artistes multiples, les capacités par format, les copies de test, la reprise et la recette Rekordbox ; leur absence n'est pas masquée dans l'interface.

En cas d'erreur de migration, préserver la sauvegarde et consigner l'échec sans recréer la base personnelle. Les calculs peuvent être repris par lot sans perdre les décisions. Les tâches interrompues suivent les états existants de `JobService`.

## Livraison Git

Contrôler les seuls fichiers de ce lot, les liens, l'UTF-8 et les diffs. Indexer explicitement sans collection ni rapports privés. Maintenir ce plan et le rapport de validation. Après les contrôles et la recette depuis les sources, créer un commit détaillé et pousser sans force, puis comparer HEAD et origin. Les changements applicatifs préexistants sont préservés. Des commits de maquettes et de sous-jalons sont possibles ; la publication des maquettes ne vaut pas validation utilisateur.

## Outcomes & Retrospective

Le jalon 103.0 est livré dans `docs/ux/mockups/Mapping103Review.qml`, `scripts/review_mapping_103.py`, `docs/ux/review-103-artistes-mapping.md` et les captures de `docs/ux/review-103-artistes-mapping/`. Les onze scénarios ont été lancés depuis les sources et capturés sans avertissement QML. La maquette présente explicitement A+ et Ev comme artistes séparés, les collaborations et crédits non résolus sans fusion automatique, ainsi que les états de revue demandés. Aucun service, modèle Qt, migration, accès à une collection ou modification de fichier audio n'a été ajouté. Les jalons suivants restent bloqués par la validation de l'interface demandée par `PLAN.md` ; aucune proposition de l'étude 102 n'est confirmée par la maquette.

## Consigne prête à copier dans Luna

    Prépare le jalon 103.0 de « Plans d'exécution/103-artistes-revue-mapping.md ». L'étude 102 est terminée : ne demande pas de nouvelle passe d'échantillonnage. Lis AGENTS.md, PLANS.md et les compétences applicables, puis crée les maquettes QML Artists et Match review avec données fictives, leur lanceur et un dossier de revue. Montre les cas inconnus, collaborations, corrections par lots, titres nettoyés et aperçus de renommage. Vérifie les maquettes depuis les sources, maintiens le plan, commite et pousse uniquement les fichiers du jalon. Préserve les changements préexistants. Soumets les maquettes à ma validation avant le backend, conformément aux règles du dépôt. Aucun audio modifié, aucune API, aucune pochette, aucun build Windows.
