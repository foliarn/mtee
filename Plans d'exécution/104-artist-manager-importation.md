# Étape 104 — Identification des artistes et Artist manager

ExecPlan préparé le 2 octobre 2026, à maintenir selon `PLANS.md`. Il remplace le [plan 103](103-artistes-revue-mapping.md), dont les maquettes ont été refusées. La demande actuelle porte sur ce plan ; sa préparation ne lance ni migration ni modification de la collection.

## Résultat attendu et ordre de livraison

À partir du job Analysis de MTEE, toute la collection enregistrée reçoit des propositions d'artistes et de titres. Une interface intégrée permet de les corriger et de les confirmer en trois catégories successives. La confirmation crée les associations définitives, renomme les fichiers `Artiste(s) - Titre.ext` et propose une case facultative pour écrire également les tags. Le travail reprend après fermeture et une réanalyse ne réinitialise aucune décision.

La livraison A réalise les tables, l'alimentation par Analysis, le backend et une interface de traitement utilisable sur toute la collection. La livraison B ajoute ensuite la vraie navigation Artists et les pages artistes au-dessus de ce même outil. « Temporaire » concerne la place de l'interface de traitement dans le parcours : ses composants et ses services seront conservés.

Le [sketch fourni par l'utilisateur](../docs/ux/104-artist-manager-sketch.png) et les décisions ci-dessous forment le contrat d'interface. La nouvelle demande remplace le parcours de maquettes autonomes de 103 par cette réalisation intégrée. La structure du sketch doit être respectée ; ses couleurs d'annotation et son fond blanc ne remplacent pas le thème de MTEE. La livraison B constitue une étape ultérieure, après retour sur A.

## Progress

- [x] 2026-10-02 — Recueillir les décisions, examiner le socle et rédiger le nouveau plan.
- [x] 2026-10-02 — Archiver le sketch et signaler que 103 est remplacé.
- [ ] 104.1 — Créer les contrats, la migration et la persistance.
- [ ] 104.2 — Alimenter le parcours depuis Analysis sur toute la collection.
- [ ] 104.3 — Implémenter correction, confirmation, tags et renommage reprenables.
- [ ] 104.4 — Intégrer l'interface de traitement conforme au sketch.
- [ ] 104.5 — Vérifier la livraison A et la rendre disponible depuis les sources.
- [ ] 104.6 — Réaliser la navigation et les pages Artists de la livraison B.
- [ ] 104.7 — Vérifier B, actualiser la documentation, committer et pousser.

## Décisions utilisateur et périmètre

| Sujet | Contrat retenu |
|---|---|
| Collection | Tous les morceaux enregistrés dans MTEE, pas un nouvel échantillon de 150 fichiers. Les nouveaux fichiers passent par le scan habituel. |
| Métadonnées | Même un artiste trouvé dans les tags doit être confirmé. Sa provenance est conservée séparément de la correction. |
| Ordre initial | Métadonnées, puis propositions, puis cas à renseigner. Finir une catégorie avant d'accéder à la suivante. |
| Base déjà peuplée | Si des artistes établis existent à l'initialisation du parcours, accès libre aux catégories. |
| Correction | Bouton Edit par ligne ; aucune checkbox de sélection dans les listes. |
| Validation du lot | Uniquement les résultats du filtre courant, avec le nombre concerné et une fenêtre de confirmation. |
| Tags | Case `Also update file tags` dans la confirmation ; désactivée par défaut. Le renommage fait partie de l'opération même si cette case reste vide. |
| Séparation | Uniquement la virgule et `&`, y compris dans `Skream & Benga`. Ni `x`, ni `feat.`, ni `ft.` ne deviennent des séparateurs automatiques. |
| Noms | Regrouper les variantes de casse et d'espacement. `MPH` reste en majuscules ; sinon retenir la graphie observée le plus souvent. Un renommage manuel devient prioritaire. |
| Identités | A+ et Ev sont des artistes à part entière. Un crédit composé ne devient pas l'alias d'un artiste unique. Aucune fusion approximative automatique. |
| Versions | Remix, flip et bootleg restent dans le titre. Le remixer est également crédité comme artiste. Ajouter l'artiste original seulement s'il apparaît explicitement dans les informations disponibles. |
| Fichiers | Tous les formats suivent `Artiste A, Artiste B - Titre.ext`. Un nom déjà conforme reste tel quel. Collision : suffixe numérique automatique avant l'extension. |
| Analyse suivante | Un morceau déjà inscrit dans ce parcours ne le recommence pas, même lors d'une réanalyse audio forcée. |
| Suppression d'artiste | Confirmation et case facultative pour retirer cet artiste des tags des fichiers concernés. Aucun fichier audio supprimé. |
| Validation technique | Compilation/chargement, un test backend simple couvrant les familles de cas, aucun test UI et aucun build EXE. |

Les pochettes, genres, identifiants et recherches Spotify/SoundCloud, Shovel, extension Chromium et téléchargement TIDAL restent différés. Aucun appel réseau n'est nécessaire. Les textes promotionnels ne deviennent pas des champs ou des écrans dédiés.

## Socle vérifié et précautions d'intégration

Le dépôt contient Python 3.12, PySide6/QML, SQLite et Mutagen. `src/mtee/persistence/database.py` possède déjà migrations et sauvegarde cohérente. À la préparation, la dernière migration est `018_playback_session.sql` ; utiliser `019_artist_manager.sql` si ce numéro reste disponible au début du développement.

`tracks.track_id` est un UUID ; `track_locations` porte le chemin et les métadonnées réellement lues ; `root_tracks` porte les appartenances aux racines. `LibraryRepository.move_location_in_transaction` sait actualiser un emplacement et ses racines sans changer l'UUID. Les anciennes migrations d'opérations fichiers ne prouvent pas l'existence d'un service actuel de renommage : vérifier leur schéma avant de réutiliser une table, puis créer le service manquant.

`MetadataReader` conserve plusieurs valeurs artiste dans un `MetadataSnapshot`. En revanche, `MetadataPatch` accepte actuellement une chaîne par champ. `MetadataEditService`, les adaptateurs Mutagen, `FileReplacement`, `FileAccessCoordinator` et l'historique de métadonnées fournissent des protections utiles. Leur interface doit évoluer pour les crédits multiples sans casser l'éditeur actuel. Le support en lecture d'une extension, notamment `.aif`, ne prouve pas son support en écriture.

`AnalysisService.pending()` sélectionne actuellement les morceaux dont l'analyse audio ou la waveform manque. Ajouter une phase artiste uniquement à `analyze_track()` oublierait les morceaux dont l'audio est déjà à jour. Il faut adapter la sélection et l'orchestration, pas forcer un nouveau décodage de toute la collection.

Les composants `SideBar.qml`, `ActivityBar.qml`, `PlaylistsPane.qml`, `TrackListView.qml`, `PlaylistHeader.qml` et `Mtee/Theme.qml` fournissent les motifs visuels à reprendre. Plusieurs de ces fichiers, ainsi que les modèles et le service Analysis, comportent déjà des modifications locales à la préparation : les relire au début du développement et préserver ces changements. Ne pas les inclure par inadvertance dans un commit documentaire.

## Modèle de données — jalon 104.1

Créer `src/mtee/domain/artists.py` et `src/mtee/persistence/artist_repository.py`. Les noms ci-dessous sont proposés pour la migration ; conserver les invariants si une table existante peut être adaptée proprement.

| Table | Données et contraintes utiles maintenant |
|---|---|
| `artists` | UUID, nom affiché, clé normalisée, origine du nom automatique/manuelle, état provisoire/établi/retiré, dates. Clé active unique pour casse/espaces équivalents. Un profil provisoire n'est pas un artiste confirmé. |
| `artist_name_observations` | Artiste, morceau, graphie source, provenance. Unicité par morceau/provenance/graphie pour qu'une réanalyse ne gonfle pas la fréquence. Sert au choix de graphie, pas à une fusion floue. |
| `artist_aliases` | Variantes explicitement rattachées lors d'une fusion ou d'une correction ; unicité cohérente avec la normalisation. Une collaboration ne produit pas automatiquement d'alias. |
| `track_artist_review` | Une ligne unique par `track_id` : catégorie, état, cohorte initiale éventuelle, source et révision observées, instantané original des artistes/titre, titre proposé, version des règles, version de décision et dates. |
| `track_artist_credits` | Crédit proposé ou confirmé, morceau, artiste, ordre. Un artiste ne figure qu'une fois dans un même crédit ; conserver séparément la provenance original/remixer si connue. Les propositions n'alimentent pas les compteurs définitifs. |
| `artist_workflow` | État persistant du premier parcours : mode guidé/libre, catégorie accessible, cohorte de lancement, fin du premier parcours. La création des profils ne change pas ce mode. |
| Journal d'application | Opération, items par morceau, décisions avant/après, révisions, chemin avant/cible/final, choix tags, référence à l'historique existant, étapes et erreurs. Réutiliser les tables existantes si leurs garanties conviennent, sinon créer `artist_operations` et `artist_operation_items`. |

L'artiste doit pouvoir être renommé ou fusionné sans changer son UUID. La suppression retire le profil de la navigation et conserve les informations nécessaires à une annulation ciblée. Ne pas supprimer en cascade l'historique d'une décision. Les champs de profils distants et les images pourront être ajoutés quand leur fonctionnalité sera réalisée.

La normalisation applique Unicode NFC, trim, espaces consécutifs réduits et comparaison sans casse. Elle conserve accents, ponctuation et signes comme `+`. L'ordre des artistes reste celui du crédit proposé ou modifié. La graphie majoritaire est déterministe ; en cas d'égalité, conserver la graphie déjà choisie, sinon la première observation dans un ordre de morceaux stable. Les observations de toute la passe initiale sont prises en compte avant d'appliquer les noms aux fichiers. Une graphie fixée manuellement ne change plus au prochain import.

La migration sauvegarde SQLite par le mécanisme existant, s'exécute dans une transaction et ne lit/modifie aucun audio. La suppression puis recréation d'un profil ne doit pas faire oublier que ses morceaux sont déjà entrés dans le parcours.

### États et navigation

Séparer trois axes : provenance/catégorie (`from_tags`, `suggested`, `needs_input`), revue (`pending`, `confirmed`) et état d'application (`queued`, `running`, `succeeded`, `failed`, `cancelled`). Un conflit d'écriture n'est pas une nouvelle catégorie musicale. Une décision peut être confirmée et son application rester à reprendre ; la progression initiale attend aussi la résolution de ces applications incomplètes.

Au premier démarrage du dispositif, déterminer le mode avant toute création de profil provisoire. Zéro artiste établi implique un parcours guidé persistant. Sinon, le mode est libre. Une fois le mode guidé commencé, les premières confirmations ne le déverrouillent pas prématurément. Une fois terminé, il ne se réactive pas si l'utilisateur retire tous ses artistes.

La première passe d'analyse constitue une cohorte stable : enregistrer les UUID prévus avant de commencer. Fermer puis reprendre cette passe ne réduit pas sa portée. Les ajouts ultérieurs restent enregistrés sans rallonger indéfiniment la cohorte initiale. Attendre la fin de l'inscription de cette cohorte pour autoriser sa confirmation et calculer ses catégories vides ; un résultat encore en cours d'arrivée n'est pas une catégorie terminée. Une catégorie réellement vide est immédiatement terminée. Une catégorie est terminée lorsque tous ses morceaux ont été confirmés et appliqués, ou explicitement transférés vers `Needs input` via Edit parce qu'ils nécessitent une saisie. Un filtre qui masque les lignes restantes ne termine jamais une catégorie. Les erreurs conservent le verrou avec une explication et une action de reprise.

## Alimentation par Analysis — jalon 104.2

Créer `src/mtee/services/artist_identification_service.py`, puis brancher ce service dans `analysis_service.py`, `models/analysis_model.py` et `app.py` avec les mécanismes de jobs existants. Aucun appel fichier direct depuis QML.

L'état initial d'Artist manager propose `Analyze collection`, qui lance ce même job avec tous les `track_id` de toutes les racines enregistrées, dédupliqués par UUID. C'est le point d'entrée de la première cohorte complète ; aucun second moteur d'import n'est créé. Les fichiers non encore catalogués doivent d'abord être scannés. Les lancements Analysis habituels restent limités à leur sélection et peuvent alimenter la revue ; ils ne doivent pas faire passer une sélection partielle pour une initialisation de toute la collection. Après cette initialisation, les nouveaux morceaux passent par les prochains jobs Analysis.

Le job sélectionne l'union des morceaux dont l'audio nécessite un traitement et de ceux qui n'ont pas de ligne `track_artist_review`. Pour chacun, exécuter uniquement les phases nécessaires. Un audio à jour peut ainsi recevoir une proposition artiste sans recalcul de BPM, tonalité ou waveform. `force=True` force l'audio ; il ne réinitialise pas la revue artiste.

L'inscription de chaque morceau est transactionnelle et idempotente : un deuxième lancement concurrent rencontre la contrainte unique et conserve la première décision. Un morceau en attente, modifié manuellement, confirmé ou en erreur d'application est déjà inscrit. Une réanalyse ne remplace ni ses propositions ni ses liens. Le scanner continue de rafraîchir les observations physiques sans écraser les corrections du catalogue.

La lecture et l'inscription utilisent une révision stable. Coordonner cette phase avec l'écriture BPM/key facultative déjà présente dans Analysis : lire après cette écriture si elle a lieu, sinon lire directement, puis vérifier que la révision correspond toujours à l'instantané. Un échec du décodage audio ne doit pas empêcher une proposition issue de métadonnées lisibles ; rapporter distinctement les deux résultats. Une lecture instable reste une erreur reprenable, pas un morceau prétendument traité avec une proposition vide.

Le job expose progression, erreurs par morceau et annulation. Une annulation conserve les inscriptions terminées et permet de poursuivre les autres. La phase artiste elle-même ne renomme et ne tague rien. L'écriture BPM/key préexistante garde son réglage indépendant ; elle n'autorise pas l'écriture des nouveaux champs artiste/titre.

### Règles de proposition

1. Lire toutes les valeurs du champ artiste, les séparer uniquement sur virgule et `&`, retirer les éléments vides et dédupliquer les identités en gardant leur ordre. Si des artistes exploitables existent, classer dans `From tags`. Conserver le titre musical et sa version ; signaler dans Edit une contradiction explicite avec le nom de fichier sans remplacer silencieusement les tags.
2. Sinon, prendre le préfixe avant le séparateur de crédit ` - ` dans le nom sans extension, puis appliquer le même découpage. Ne pas découper le tiret interne d'un nom. Accepter les noms inconnus en casse mixte : ni catalogue préexistant ni capitales obligatoires. Un préfixe vide, numérique seul ou manifestement inexploitable laisse le morceau dans `Needs input`. Les conventions de tirets sans espaces ou les noms ambigus restent à renseigner plutôt que d'inventer une frontière.
3. Reconnaître les formes explicites `Title (Artist Remix)`, `Title (Artist Flip)` et `Title (Artist Bootleg)`, y compris les variantes entre crochets. Elles donnent un crédit proposé au remixer et gardent le descripteur de version dans le titre. Avec un original explicitement identifié, conserver original puis remixer ; sans original, uniquement le remixer. Appliquer uniquement les séparateurs autorisés au crédit extrait. Une mention `Remix` sans nom ne permet pas d'inventer un artiste.
4. Les cas exploitables de remix/flip/bootleg sans tags vont dans `Suggested`. Le descripteur ne suffit pas à les envoyer tous dans `Needs input`. En cas de plusieurs interprétations, conserver une proposition éditable si les éléments explicites le permettent ; sinon demander la saisie.
5. Si le titre du tag manque, proposer celui du nom de fichier après extraction fiable du crédit, en conservant la version. Un titre toujours indéterminable nécessite Edit avant confirmation. La présence d'un artiste ne suffit pas à autoriser un nom de fichier vide ou technique.

Ces heuristiques sont des propositions, pas une mesure de confiance. Le script d'étude 102 fournit des exemples et des règles réutilisables après lecture ; ses JSON personnels ne deviennent pas la base de production. Les virgules ou `&` saisis dans **une ligne d'artiste de la modale** restent littéraux : le découpage automatique concerne l'ingestion, afin que l'utilisateur puisse recomposer un nom si nécessaire.

## Corrections et application — jalon 104.3

Créer `src/mtee/services/artist_manager_service.py` pour les décisions et `artist_file_service.py` pour leur application. Les modèles Qt appellent ces services. Les opérations lourdes, copies, empreintes et écritures quittent le thread graphique.

### Edit et opérations artistes

Edit ouvre une modale avec nom actuel du fichier, titre éditable, une ligne par artiste préremplie, boutons d'ajout/retrait et aperçu du futur nom. Chaque champ artiste propose les profils existants filtrés par la saisie. Choisir une suggestion attache son UUID ; saisir un nouveau nom puis enregistrer crée un profil provisoire réutilisable. Une saisie libre ne doit pas écraser le nom d'un profil sélectionné implicitement.

`Save changes` conserve le brouillon et ses liens proposés ; il ne touche pas aux fichiers. La modale permet `Needs input` lorsqu'une proposition est inexploitable. Pas de bouton Skip/Rejet ni de mécanisme de lignes décochées. Un morceau avec crédit/titre incomplet reste non confirmable, avec une explication courte.

Le menu artiste propose `Rename`, `Merge into…`, `Delete artist`. Rename conserve l'identité et verrouille la graphie manuelle. Merge demande une destination explicite, déduplique les crédits et préserve leur ordre. Delete détache le profil ; si le morceau n'a plus d'artiste, il passe dans `Needs input`. Les autres crédits restent présents. Les actions portent sur les associations connues, jamais sur une recherche textuelle approximative dans toute la collection.

Pour les associations déjà confirmées, ces opérations présentent le nombre de morceaux touchés et une confirmation. Rename/Merge proposent `Also update file tags` ; Delete propose `Also remove this artist from file tags`. Les chemins sont recalculés avec les crédits restants ; un morceau sans artiste conserve son ancien fichier jusqu'à sa correction, au lieu de produire ` - Title.ext`. Sur des associations encore proposées, les modifications restent des brouillons jusqu'à la confirmation de leur catégorie.

### Confirmation d'un lot

Le bouton affiche `Confirm N tracks`. Il vise tous les résultats du filtre courant, y compris hors de la portion visible à l'écran, et exclut les éléments déjà appliqués. Figer les UUID, versions de décisions et révisions quand la fenêtre s'ouvre ; ne pas recalculer un autre périmètre au clic final. Si une ligne du résultat est incomplète, afficher son nombre et demander de la corriger ou de la transférer via Edit ; ne pas appliquer discrètement un sous-ensemble.

Depuis une liste d'artistes, traduire les artistes filtrés en morceaux distincts et présenter `N artists · M tracks`. Valider le crédit complet de chaque morceau, jamais uniquement l'artiste par lequel il apparaît dans ce filtre. La modale explicite ce périmètre, le renommage et la case tags. Les modifications survenues pendant son ouverture exigent une nouvelle prévisualisation.

Une fois confirmé, enregistrer les décisions et l'opération persistante, puis appliquer par morceau. Les succès sortent de la file à traiter ; les erreurs restent visibles et reprenables avec leur cause. Les associations confirmées servent au catalogue même si l'application est en erreur, mais cette erreur reste signalée et bloque la fin du parcours initial.

### Noms de fichiers et écritures

Construire le nom avec les noms canoniques ordonnés, séparés par `, `, puis ` - `, puis le titre. Garder extension et dossier. Le titre inclut `(X Remix)` ou son libellé de version existant ; X apparaît également dans les artistes. L'assainissement des caractères interdits Windows s'applique uniquement au nom de fichier, pas au titre musical stocké. Prévoir noms réservés, point/espace final et longueur totale ; une réduction nécessaire est visible dans l'aperçu.

Un nom déjà conforme ne déclenche pas de déplacement. Pour un nom occupé par un autre fichier, réserver `… (2).ext`, puis `… (3).ext`, etc., en tenant compte de Windows, des fichiers hors catalogue et des autres items du même lot. Le suffixe reste une propriété du chemin, pas du titre ni des tags. Une destination suffixée attribuée est mémorisée : les reprises ne lui ajoutent pas un second suffixe. Aucune primitive de remplacement ne doit écraser un fichier à cette destination.

Si la case tags est cochée, écrire artiste(s) et titre via les adaptateurs et les protections de `MetadataEditService`. Étendre `MetadataPatch` avec une représentation typée de plusieurs valeurs artiste, compatible avec ses appelants actuels. Au niveau d'un format qui ne restitue pas les valeurs séparément, employer une sérialisation documentée et stable ; garder les UUID et l'ordre dans la base. Vérifier effectivement MP3, FLAC, WAV, AIFF/AIF et M4A : une capacité absente produit un statut explicite, pas une réussite fictive. Conserver tous les champs inconnus, pochettes, BPM, tonalité et autres métadonnées non ciblées. Delete retire uniquement les valeurs de l'artiste concerné en préservant les coartistes ; ne pas toucher à Album Artist par défaut.

Séquence d'application : précontrôle de révision et du fichier, réservation du nom, écriture facultative des tags sur copie protégée, renommage sans écrasement, actualisation transactionnelle de l'emplacement et du journal. Réutiliser `move_location_in_transaction`, l'historique de tags et les protections de remplacement. Définir un seul propriétaire du verrou fichier pour éviter de reprendre le même verrou à l'intérieur de `MetadataEditService`.

Conserver le `track_id`, les liens playlists, la file, les analyses et l'historique. Rafraîchir les modèles sur le thread Qt et les chemins utilisés par le lecteur. Un fichier occupé par la lecture peut rester en attente explicite ; aucune perte d'identité ni interruption silencieuse n'est acceptable.

`track_locations.metadata_json` reste l'observation des tags réels. Si la case n'est pas cochée, les crédits corrigés vivent dans le catalogue et les pages Artists utilisent ces crédits ; ne pas prétendre avoir écrit le fichier. Les parties existantes de MTEE fondées sur les tags doivent pouvoir distinguer cette source du crédit corrigé, sans falsifier le snapshot.

### Reprise et annulation

SQLite et le système de fichiers ne forment pas une transaction commune. Journaliser avant chaque mutation et marquer chaque phase terminée avec sa révision/empreinte. Si les tags réussissent puis le renommage échoue, la reprise ne réécrit pas les tags. Si le renommage réussit mais la mise à jour SQLite échoue, retrouver le fichier à la destination journalisée et vérifier son identité avant de réparer l'emplacement. Une interruption ne doit jamais être présentée comme un succès intégral.

Annuler un job arrête les items non commencés et termine proprement l'item en cours. `Undo` restaure de manière ciblée les décisions et, lorsque les sources correspondent encore aux révisions attendues, les tags et chemins journalisés. Une modification externe ou un chemin de retour occupé crée un conflit visible ; ne pas écraser un fichier pour réussir l'annulation. Un profil utilisé depuis par une autre opération n'est pas supprimé par l'annulation de sa création initiale.

## Interface intégrée — jalon 104.4

Ajouter l'activité `Artist manager`, son panneau latéral et sa vue dans le routage existant. Créer les modèles `artist_manager_model.py` et `artists_model.py`, puis des composants QML ciblés : `ArtistManagerPane.qml`, `ArtistReviewView.qml`, `ArtistReviewTrackList.qml`, `ArtistListView.qml`, `ArtistEditDialog.qml`, `ArtistConfirmDialog.qml`. Adapter les noms au découpage réel, sans accès QML aux fichiers.

La sidebar de A contient `Identification`, déplié par défaut, avec `From tags`, `Suggested`, `Needs input`. Les deux premiers possèdent `Tracks` et `Artists` ; le dernier possède `Tracks`. Les catégories verrouillées restent visibles et expliquent brièvement quelle étape finir. Leurs compteurs reflètent les éléments restant à traiter. `Suggested` remplace « Suppositions » ; `From tags` évite d'annoncer « Confirmed » avant validation.

La zone principale est une liste occupant la largeur disponible : titre de page et nombre, recherche locale, bouton `Confirm N tracks`, en-têtes triables, puis lignes. Pour les morceaux : `Filename`, `Artists`, `Edit`. Les noms d'artistes sont cliquables ; avant B, ils ouvrent la liste de leurs morceaux dans la revue. Pour les artistes : `Artist`, `Tracks`, `Edit` ouvrant Rename/Merge/Delete. Tri par nom de fichier ou artiste, comme dans le sketch. Les artistes multiples restent distinguables et les textes longs sont tronqués avec infobulle.

Réutiliser `Theme.qml` : fonds chrome/sidebar/editor existants, texte primaire/secondaire, accents citron et rose, séparateurs discrets, typographie et marges communes. À la préparation, le thème prévoit sidebar 240, treeRowHeight 24, rowHeight 56 et coverSize 40 ; consommer les tokens, sans les recopier en valeurs figées. Reprendre AppMenu/AppMenuItem, les dialogues et barres de défilement de l'application.

La maquette 103 refusée ne sert pas de composition : conserver la liste pleine largeur du sketch, des actions locales et des modales. Les détails techniques d'extraction restent hors de la page principale. Pas de panneau permanent de comparaison, cartes de statistiques, badges de confiance en série ni nouvelle palette.

Prévoir explicitement : analyse en cours avec résultats qui arrivent, état vide, aucun résultat de recherche, catégorie terminée, verrou de progression, fichier indisponible et opération en erreur. Ne pas changer la page active à chaque arrivée de résultat. Les dialogues conservent la saisie en cas d'erreur ; Échap ferme sans appliquer, Entrée n'engage une opération que sur son bouton prévu. La barre de confirmation et les colonnes restent utilisables à la largeur minimale supportée par MTEE.

## Vérification de A — jalon 104.5

Respecter la demande : aucun test UI automatisé, aucune campagne exhaustive supplémentaire et aucun packaging. Créer **une fonction de test backend paramétrée** dans `tests/unit/test_artist_manager_contract.py`, avec de petites données synthétiques et des fichiers temporaires. Chaque scénario vérifie une sortie métier observable ; les branches simples du parseur ne justifient pas chacune un test séparé.

| Famille dans cette fonction | Résultat à contrôler |
|---|---|
| Métadonnées multiples, virgules et `&` | Profils distincts et ordre correct ; pas de validation automatique ; A+ et Ev conservés. |
| `x`, `feat.`, tiret interne ; nom recomposé en Edit | Aucun découpage supplémentaire ; correction manuelle littérale persistante. |
| Graphies/MPH | Déduplication casse/espaces, graphie majoritaire, priorité du renommage manuel, pas de fusion floue. |
| Préfixe et absence de données | Proposition pour un nom inconnu en casse mixte ; cas inexploitable à renseigner ; titre requis. |
| Remix/flip/bootleg | Version dans le titre ; original explicite + remixer, sinon remixer seul ; artiste non dupliqué. |
| Analyse et réanalyse | Audio à jour mais revue absente traité ; même ID réanalysé ignoré par la revue ; correction intacte ; reprise après interruption. |
| Navigation | Mode initial persistant, catégorie vide sautée, filtre sans déverrouillage, base peuplée libre, suppression sans retour au mode initial. |
| Confirmation filtrée | UUID exacts du résultat, comptage unique depuis artistes, rejet d'une décision devenue obsolète, aucun élément masqué traité. |
| Renommage | Tous formats, no-op, caractères Windows, collision `(2)`, suffixe stable en reprise, UUID/playlist conservés. |
| Tags facultatifs | Case vide : contenu du fichier intact après renommage. Case cochée : relire artiste/titre et vérifier conservation des tags inconnus/pochettes sur copies. |
| Opérations artistes | Rename/Merge/Delete, coartistes conservés, dernier artiste retiré vers Needs input, annulation sans perte de modification ultérieure. |
| Échec/reprise | Source modifiée, fichier occupé, échec après tags ou après renommage ; reprise de la phase manquante sans écrasement. |

Utiliser les petits fichiers/constructeurs de fixtures déjà disponibles pour chaque adaptateur ; les écritures réelles se font exclusivement sur des copies temporaires. Simuler le décodeur audio et les pannes, pas la persistance entière. Si une extension ne peut pas être écrite par le socle, vérifier l'erreur de capacité au lieu de fabriquer une réussite. Garder l'ensemble rapide ; ne pas analyser les milliers d'audios dans ce test.

Commandes prévues, depuis la racine du dépôt, après création des fichiers concernés :

    uv run python -m compileall -q src/mtee
    uv run pytest -q tests/unit/test_artist_manager_contract.py
    uv run python -m mtee --data-dir .local/validation/104/smoke --smoke-test

Le smoke est un contrôle de chargement/compilation de la fenêtre, pas un test d'interactions UI. S'assurer que tous les nouveaux composants QML sont effectivement compilés/chargés pendant ce contrôle, y compris les vues derrière Loader ; adapter le chargement de contrôle si nécessaire. Exécuter Ruff sur les seuls fichiers Python modifiés. Distinguer les diagnostics préexistants de ceux du lot ; ne pas annoncer que tout compile si un composant ajouté n'a pas été chargé.

L'utilisateur réalise la recette interactive de A depuis les sources : Analysis sur la collection, trois catégories dans l'ordre, corrections par Edit, confirmation du nombre filtré, tags optionnels et noms obtenus. Avant toute application réelle, l'agent vérifie les écritures sur copies par le test backend. Documenter séparément contrôles automatiques, observation manuelle réellement faite et recette utilisateur restante. Ne pas lancer de scénario UI automatisé en ajoutant une autre étiquette.

## Vraies pages Artists — jalon 104.6, livraison B

Après retour sur A, compléter la même sidebar avec `Artists` au-dessus d'`Identification`. Déplier Artists affiche les profils établis par ordre alphabétique, dans une liste défilante comme l'explorer. Cliquer le parent ouvre le catalogue ; cliquer un nom ouvre sa page. Les profils provisoires restent dans les catégories de revue. Ne pas réimporter les données pour cette transition.

Le catalogue contient exactement `#`, vignette de remplacement, `Artist`, `Tracks`. Le compteur est le nombre de `track_id` distincts associés par un crédit confirmé ; deux fichiers physiques distincts peuvent compter deux fois, deux rôles sur le même morceau ne comptent qu'une fois. Une association temporairement indisponible reste identifiable, sans disparition silencieuse du catalogue. Renommer/fusionner/supprimer reste accessible via les menus déjà réalisés.

Créer `ArtistsView.qml` et `ArtistView.qml` et les routes de workspace nécessaires. La page individuelle reprend la présentation de la page playlist : vignette, nom, nombre de morceaux et commandes de lecture existantes, puis liste des morceaux. Retirer description, créateur et fonctions propres à une playlist. Réutiliser ou extraire la présentation de `PlaylistHeader.qml` ; ne pas fabriquer une fausse playlist pour satisfaire ses dépendances. Reprendre `TrackListView` et les interactions de lecture adaptées, en gardant l'identité des morceaux.

Les images sont des placeholders cohérents avec l'application. Aucun téléchargement d'image et aucune gestion de genre/profil distant n'entrent dans B. Le branchement de lecture, navigation et historique utilise les modèles existants. Les filtres et tris des pages artistes ne changent pas ceux de l'explorer ou des playlists.

## Critères de livraison et Git — jalons 104.5 et 104.7

A est livrable lorsque le job alimente la revue pour tous les morceaux demandés, que les décisions persistent, que la réanalyse les respecte, que les trois étapes et Edit fonctionnent et que la confirmation applique noms/tags selon le choix. Les erreurs réelles doivent être visibles et reprenables. B est livrable lorsque le catalogue et les pages artistes utilisent ces mêmes données et composants sans réinitialisation.

Créer `docs/validation/104-artist-manager.md` pendant le développement pour noter environnement, commandes, résultats, limites par format et recette restante. Actualiser ce plan à chaque jalon. Ne pas cocher une recette utilisateur absente. Pour chaque livraison, inspecter l'état Git et les différences, indexer explicitement les fichiers du lot, vérifier `git diff --cached --check`, committer avec un message détaillé via un fichier temporaire, puis pousser selon `PLANS.md`. Préserver le travail local d'autres tâches. Aucun build Windows n'est demandé.

Une sauvegarde de base avant migration permet une restauration complète seulement tant qu'aucune opération sur fichiers n'a commencé. Après application, utiliser le journal et l'annulation ciblée ; une restauration aveugle de la base seule recréerait des chemins obsolètes.

## Surprises & Discoveries

2026-10-02 — L'existence dans `tracks` ne signifie pas « déjà passé dans la revue » : le scanner enregistre les morceaux avant Analysis. L'état dédié évite à la fois l'oubli de la collection actuelle et la remise à zéro lors d'une réanalyse.

2026-10-02 — Les propositions ne peuvent pas devenir des artistes établis dès leur création : cela ouvrirait les catégories suivantes au milieu du premier parcours. Le mode initial est donc mémorisé avant la création des profils et conservé jusqu'à la fin.

2026-10-02 — Les adaptateurs et l'historique de tags existent, mais le patch métier reste scalaire. Le passage aux crédits multiples exige une adaptation réelle du backend ; changer uniquement la chaîne affichée serait insuffisant.

2026-10-02 — `LibraryRepository.move_location_in_transaction` offre une mise à jour des racines et de l'emplacement, mais l'application fichiers et sa reprise doivent être orchestrées séparément. Une transaction SQLite ne couvre pas un renommage Windows.

## Decision Log

2026-10-02, utilisateur — Refuser la maquette 103, fournir un sketch et demander un plan pour tables, collection complète, frontend intégré et backend, puis vraie page Artists.

2026-10-02, utilisateur — Exiger la confirmation des métadonnées, retirer les checkboxes de lignes, corriger avec Edit et limiter les lots au résultat filtré annoncé. Conserver une checkbox d'écriture des tags dans les confirmations.

2026-10-02, utilisateur — Renommer tous les fichiers `Artiste(s) - Titre`, tous formats ; conserver les versions dans le titre et créditer le remixer. Créditer l'original seulement s'il apparaît. Autoriser le suffixe automatique en cas de collision.

2026-10-02, utilisateur — Utiliser uniquement virgule et `&` comme séparateurs. Faire passer l'identification dans Analysis, sans recommencer les morceaux déjà traités. Imposer les étapes au premier parcours, puis autoriser la navigation libre.

2026-10-02, Codex — Nommer les catégories `From tags`, `Suggested`, `Needs input`, regroupées sous `Identification` ; mémoriser mode initial et inscription par morceau ; préserver un état d'application distinct de la décision. Ces choix rendent les demandes exécutables sans ajouter de tri par cases cochées.

2026-10-02, Codex — Séparer la livraison A utilisable et la livraison B de catalogue, avec réemploi des composants. Le sketch et les réponses remplacent la direction de 103 ; aucune validation de ses captures n'est supposée acquise.

## Outcomes & Retrospective

Préparation documentaire uniquement. Le schéma, les modules et les commandes de vérification ci-dessus décrivent le travail à venir ; aucune migration, écriture audio ou implémentation de ce plan n'a été exécutée pendant sa rédaction. Le développement doit encore mesurer les capacités réelles par format et réaliser les contrôles indiqués. Les vérifications de cette préparation portent sur l'encodage, les liens, les références existantes et la cohérence du diff.

Contrôles documentaires exécutés le 2026-10-02 : lecture UTF-8 des cinq documents ajoutés/modifiés, résolution des liens du nouveau plan et des renvois vers 104, identité binaire de la copie du sketch, présence des quatre sections de suivi et `git diff --check`. Résultat : contrôles réussis ; Git signale seulement des normalisations CRLF/LF dans le workspace. La migration la plus récente a été revérifiée : 018. Aucun test applicatif n'a été lancé pour cette préparation.

## Consigne prête à transmettre pour la livraison A

    Lis AGENTS.md, PLANS.md et le plan 104-artist-manager-importation.md dans Plans d'exécution.
    Implémente la livraison A, jalons 104.1 à 104.5, sur le code actuel en préservant les modifications locales existantes.
    Respecte le sketch lié dans le plan et les composants/thème de MTEE : liste pleine largeur, sidebar arborescente et Edit en modale.
    Le job Analysis doit alimenter toute la collection une seule fois par morceau ; une réanalyse conserve la revue et ses corrections.
    Aucun fichier utilisateur ne doit être renommé ou tagué avant sa confirmation dans l'application. Vérifie les écritures sur copies.
    Aucun test UI, aucune nouvelle campagne d'échantillonnage, aucun build Windows. Fais les contrôles de compilation/chargement et l'unique test backend paramétré du plan.
    Actualise le plan et le rapport de validation, committe et pousse uniquement les fichiers du lot. Termine par le bilan réel et la recette utilisateur à effectuer.
    La livraison B, jalons 104.6 et 104.7, viendra après le retour sur A.

Révision du 2026-10-02 : remplace le plan 103 après rejet de sa maquette et intègre les dernières décisions de renommage, crédits remix et alimentation par Analysis.
