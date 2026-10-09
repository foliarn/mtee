# Étape 110 — Genre Manager en plugin : classer, vérifier et ranger sa bibliothèque

ExecPlan préparé le 9 octobre 2026 selon [PLANS.md](../PLANS.md). Référence produit : [PLAN.md](../PLAN.md). Il remplace le [plan 109](109-genres-morceaux-manager-tri.md) pour les genres des morceaux et leur interface. Les réponses utilisateur de cette conversation sont transcrites ci-dessous ; les propositions de conception sont identifiées comme telles.

**Révision du 9 octobre, après revue :** l'utilisateur demande l'exécution du plan sur les maquettes corrigées, avec une fidélité stricte aux espacements et alignements du front MTEE. Il demande aussi de ne pas rétablir la migration historique 021 : la base sera repeuplée avec cette version. Cette décision remplace les passages de compatibilité 021 ci-dessous.

## Objectif et résultat observable

L'utilisateur remet principalement en ordre une bibliothèque existante. Il travaille dossier par dossier, ou depuis une playlist. Un dossier House contient déjà presque uniquement de la House ; l'essentiel du travail consiste à distinguer Deep House, Minimal House, Disco House, etc., et à corriger les morceaux mal placés. Il connaît certains morceaux et doit en écouter d'autres. Le lecteur reste utilisable ; attribuer un genre, un tag ou valider une sélection ne démarre jamais la lecture.

L'entrée est `Plugins > Genre Manager`. Cet espace propose le classement des morceaux, une vraie page d'administration du catalogue et une vue des attributions aux artistes incertaines. Les listes ordinaires de MTEE ne portent plus une barre de classement permanente. Les genres et tags sont locaux à MTEE, sans écriture dans les métadonnées audio.

Chaque morceau possède une liste ordonnée de genres : le premier est principal et détermine son dossier physique ; les suivants sont secondaires. Des tags libres, tels que ceux que l'utilisateur décidera de créer, s'ajoutent indépendamment. Une installation neuve comporte **zéro tag libre prédéfini**. La vérification est explicite : `Mark as reviewed` porte sur la sélection. Après revue, `Organize files` propose les déplacements des seuls morceaux vérifiés du dossier ou de la playlist, puis les applique après examen. House seul reste valable et se range directement dans House.

Le parcours doit aussi permettre de classer quelques nouveaux morceaux sans recommencer la revue de la collection. Les genres des artistes se déduisent des morceaux avec une attribution prudente : un remix UKG de Madonna ne suffit pas à donner UKG à Madonna. Un crédit incertain ne bloque ni le classement ni le rangement du morceau.

## Progress

- [x] 2026-10-09 — Recueillir les décisions utilisateur et distinguer les questions de disposition laissées aux maquettes.
- [x] 2026-10-09 — Lire les règles et le plan 109, actualiser le graphe et vérifier les points d'intégration dans les sources et tests pertinents.
- [x] 2026-10-09 — Rédiger le plan de remplacement et actualiser la référence produit ainsi que l'index.
- [x] 2026-10-09 — 110.0 : établir l'état de départ, les copies 020/021 et les mesures de référence sur données isolées.
- [x] 2026-10-09 — 110.1 : produire les deux maquettes QML manipulables, leurs états, captures et dossier de revue.
- [x] 2026-10-09 — Réviser les maquettes après le premier retour 110.2 : cadre MTEE, sources, catalogue défilant, listes et pied de page ; préparer six nouvelles captures.
- [x] 2026-10-09 — 110.2 : revue utilisateur des maquettes corrigées et accord pour appliquer le plan ; conserver les deux gestes proposés en attendant l'usage réel.
- [x] 2026-10-09 — 110.3 : livrer le registre différé, le domaine, la migration 022, les décisions et sessions persistées sur copies, avec refus sûr de l'ancienne 021.
- [ ] 110.4 — Brancher le classement, le catalogue, les tags, la revue et la reprise de session selon les maquettes retenues.
- [ ] 110.5 — Livrer l'aperçu et le rangement physique récupérable, vérifiés sur copies.
- [ ] 110.6 — Livrer les genres déduits des artistes et la vue Uncertain, sans écraser les crédits manuels.
- [ ] 110.7 — Achever la recette depuis les sources, les mesures, la documentation et la publication.

## Surprises & Discoveries

Le 9 octobre, `HEAD` vaut `1eab96e30d71c5318baaf4426fecb0d5a65ba6b7` sur `main`. Le commit `1eab96e` remet les fichiers suivis dans leur état antérieur à l'exécution de 109. Après `git fetch origin`, aucune divergence avec `origin/main` n'est observée à cet instant. Les fichiers de l'ancienne implémentation des genres et sa migration 021 sont absents du checkout ; ils restent consultables dans l'historique. Ne pas prendre les anciens rapports de livraison pour la description du code actuel.

Des modifications locales concernent notamment le lecteur, la file, le modèle de liste, les interactions QML et leurs tests. Elles préexistent à cette préparation et ne sont ni modifiées, ni indexées par celle-ci. Les répertoires `.agents/`, `.codex/` et `skills-lock.json` restent également hors livraison. Revérifier l'état au début de chaque jalon, car ces travaux peuvent avancer en parallèle.

`Sidebar.qml` contient encore un simple emplacement réservé pour Plugins ; aucun contrat de chargement de plugin n'y est implémenté. `EditorGroup.qml` sélectionne les vues par type d'onglet. `WorkspaceModel`, `TrackListModel`, `JobService` et le lecteur sont des points d'intégration disponibles, pas un motif pour replacer toute la logique des genres dans le modèle central.

Les migrations présentes vont jusqu'à `020_artist_enrichment.sql`. `Database.migrate()` refuse une base plus récente et contrôle l'historique des migrations. Une base ayant exécuté 109 peut donc encore contenir 021 même après le retrait du code. **L'état de la base personnelle n'a pas été lu pendant cette préparation.** Le rollback Git ne prouve ni la suppression ni la conservation effective de ses données.

`FileMoveService.move()` conserve le `track_id`, coordonne les accès, refuse les collisions et les déplacements entre volumes, puis actualise la bibliothèque. `LibraryRepository.move_location_in_transaction()` recalcule les appartenances aux racines enregistrées. Le service actuel ne constitue pas, à lui seul, un journal durable de rangement par lot avec reprise après interruption entre disque et SQLite. Le nouveau parcours doit compléter ce contrat, sans annoncer une atomicité globale inexistante.

`track_artist_credits` distingue `artist` et `remixer`, avec un état `confirmed`. Les rôles Producer/DJ/Singer/MC des profils sont d'une autre nature. La liste d'artistes corrigée manuellement et les genres éventuellement présents historiquement dans leurs profils doivent rester séparés des nouvelles contributions calculées.

Le soupçon de lag est un retour utilisateur, **pas un diagnostic établi**. Aucun lancement, benchmark, test applicatif, accès à la base personnelle ou build Windows n'a été effectué pour cette préparation documentaire. Le graphe aide à localiser les sources ; ses résultats partiels, notamment QML, ne prouvent pas l'absence d'un comportement.

Le 9 octobre, durant l'exécution de 110.0–110.1, deux autres commits ont intégré les corrections locales du lecteur et des listes (`fb71560`, `ec31b84`). Les maquettes ont été créées dans `src/mtee/qml/prototypes/genre_manager_110/` avec un contrôleur en mémoire, hors application principale. Les mesures ont été reprises sur `ec31b84` avec 2 800 références fictives : médianes de cinq passes, démarrage de démonstration hors écran 1 994 ms, dossier House de 340 pistes 21 ms, playlist de 2 800 pistes 965 ms. Sur la fenêtre QML de l'application courante, l'ouverture d'un dossier a pris 350 ms et celle de la playlist 2 144 ms dans un essai chacune. Cinq gestes programmatiques suivis d'un `grabWindow` donnent 35 ms de médiane pour le scroll et 4 ms pour la sélection ; ils ne mesurent pas le clic au pointeur. Cinq commandes Play sur un WAV fictif, avec la sortie native silencieuse, atteignent `Playing` en médiane 30 ms. Ces chiffres ne prouvent ni l'écoute audible ni la fluidité interactive sur machine utilisateur. Les bases 020 et 021 historiques synthétiques passent `PRAGMA integrity_check`, mais l'adaptation 021 vers 110 n'a pas été exécutée.

La lecture native du WAV fictif a atteint l'état `Playing` dans le lanceur avec sortie audio de test silencieuse. Le son audible, la fluidité interactive et les gestes au pointeur doivent encore être examinés par l'utilisateur dans les deux variantes. Les captures QML à 1440 × 900 et 1100 × 760 montrent des surfaces chargées, sans constituer cet accord.

Premier retour 110.2 : les captures initiales ne ressemblaient pas suffisamment à MTEE et des textes étaient mal centrés. Le contrôle visuel de la révision compare donc le cadre de fenêtre, la barre d'activité, l'onglet, le titre de dossier, les listes et le lecteur à la capture de l'application fournie par l'utilisateur. Le catalogue fictif contient désormais 29 genres dans une liste défilante. La source House n'attribue aucun genre à l'ouverture ; seule l'action explicite de lot modifie les morceaux. La revue de confort et le choix final entre sélection et pinceau restent ouverts.

## Decision Log

2026-10-09 — Exécution 110.3 — Le schéma 022 a été créé sans fichier 021 dans l'arbre actif. `Database.migrate()` conserve son contrôle strict de l'historique : une ancienne 021 n'est ni acceptée ni écrasée. Le banc historique 110 utilise désormais une copie de schéma 020 figée dans son répertoire isolé ; il ne recrée plus de fixture 021. Le plugin ne s'instancie pas lors des parcours ordinaires : le registre n'expose alors que ses métadonnées. Le catalogue de 31 genres est semé en une transaction à la première ouverture, et les tags restent vides. Les sessions gardent le lot, le filtre et le mode ; les lectures de playlist sont groupées. La revue impose un genre explicite et ne démarre jamais depuis un nom de dossier.

2026-10-09 — Utilisateur — Remplacer la barre intrusive de 109 par un plugin accessible dans Plugins. L'objectif principal est une remise en ordre ponctuelle de la bibliothèque, puis un parcours simple pour les nouveaux morceaux. Les dossiers et playlists sont les unités de travail.

2026-10-09 — Utilisateur — Conserver le lecteur et son déclenchement volontaire. Préparer **les deux variantes** sélection puis attribution, et pinceau, afin de les essayer avant de conclure. Ne pas imposer aujourd'hui une variante définitive ni considérer l'ancienne maquette 109 comme approuvée pour cette refonte.

2026-10-09 — Utilisateur — Premier genre attribué principal, suivants secondaires ordonnés. Préciser House par Deep donne Deep House en principal. Afficher la famille House et le nom complet Deep House ; seuls les sous-genres de House reçoivent systématiquement ce nom composé. Prévoir un changement facile du principal.

2026-10-09 — Utilisateur — Le pinceau ajoute puis retire au nouveau clic, pour les genres et les tags. Les tags sont créés par l'utilisateur, sans vocabulaire initial, et peuvent s'appliquer à n'importe quel morceau. Tout reste dans la base locale, sans métadonnées audio.

2026-10-09 — Utilisateur — Validation explicite de la sélection, également dans le parcours pinceau. Affichages All tracks et To review. Un changement effectif de genre ou de leur ordre remet à vérifier ; un changement de tag ne le fait pas. House seul peut être validé.

2026-10-09 — Utilisateur — Répartir les fichiers selon le genre principal, après traitement d'un dossier ou d'une playlist. House seul reste dans House. Le rangement peut porter sur les 80 morceaux vérifiés d'un lot de 100 ; les 20 autres restent en place.

2026-10-09 — Utilisateur — Déduire les genres des artistes avec les crédits et les indices Remix/Flip/Bootleg du titre. Ne rien attribuer automatiquement en cas d'incertitude. Une vue Uncertain dans Genre Manager est une piste retenue pour les maquettes. Les tags comme banger restent propres aux morceaux.

2026-10-09 — Utilisateur — L'affichage futur dans Info et, de façon discrète et configurable, dans les listes ordinaires est souhaité, mais sera maquetté ultérieurement. Ne pas l'inclure discrètement dans cette livraison.

2026-10-09 — Conception du plan — Implémenter un **module interne fourni avec MTEE**, chargé à l'ouverture de son espace, avec un petit registre de plugins. Cette décision répond à l'isolation produit et au chargement différé ; elle ne crée ni API publique d'extensions, ni installation distante, ni nouveau framework applicatif.

2026-10-09 — Conception du plan — Proposer un espace Classify, un catalogue Genres avec administration des tags, et Uncertain. Source de travail, palette et commandes sont contextualisées. La disposition et les gestes secondaires restent à éprouver en 110.1–110.2, pas acquis par ce texte.

2026-10-09 — Conception initiale du plan, **remplacée par la correction utilisateur ci-dessous** — L'ancienne proposition de restaurer le contrat SQL historique 021 ne s'applique plus. L'ancien ordre arbitraire des hybrides ne devient jamais une décision utilisateur de genre principal.

2026-10-09 — Exécution 110.1 — Garder les maquettes dans un lanceur séparé qui réutilise `Theme.qml` et `PlayerService`. Le branchement de l'entrée Plugins au produit attend la revue 110.2. Les sources House, playlist et nouveaux titres, les tags, Reviewed, Undo, erreur/retry et l'aperçu sont des états fictifs réinitialisés au changement de source ; les variantes partagent l'état de leur session courante. Ce choix préserve les modifications locales puis publiées du lecteur et des listes pendant le travail de maquette.

2026-10-09 — Utilisateur, premier retour 110.2 — Conserver la navigation latérale, mais réaligner les maquettes sur le style et les listes de MTEE et corriger le centrage des textes. Pour les sources, garder `FOLDER` et faire du nom le bouton ouvrant une fenêtre interne à onglets Dossiers/Playlists, avec pourcentage de progression ; supprimer les boutons de source concurrents. Un dossier House ne classe rien automatiquement ; proposer une attribution de genre à ses morceaux, choisie explicitement. Mettre les commandes du plugin sous le titre et retirer la palette latérale droite. Prévoir 20+ genres défilants, `New root genre` et un `+` ancré à droite de chaque racine. Placer `Move files` dans le pied de page près de `Undo`. Le retour ne valide pas encore la variante d'interaction ni les destinations physiques.

2026-10-09 — Utilisateur, suite de 110.2 — « let's go pour ça » approuve l'implémentation des maquettes révisées, avec une apparence fidèle au front MTEE actuel et des espacements et alignements soignés. Conserver la sélection et le pinceau comme deux gestes accessibles dans le plugin ; aucun choix exclusif n'a été formulé. Le rangement exige une correspondance de destination explicite dans l'aperçu avant tout déplacement.

2026-10-09 — Utilisateur, correction de migration — « non reset tout ne rétablis pas la 021 », puis « Applique le plan tout de même, on repopulera la base avec cette nouvelle version ». Ne pas restaurer, modifier ou rejouer l'ancienne 021. Partir du schéma versionné jusqu'à 020, créer une migration 022 à numéro distinct, et tester sur une base isolée reconstruite. Une base ayant enregistré l'ancienne 021 restera refusée par le contrôle d'historique ; l'utilisateur a choisi de la repeupler. Ne pas ouvrir ou effacer sa base personnelle.

## Périmètre et points qui remplacent 109

Ce plan réactive explicitement le rangement physique et l'agrégation prudente par artiste, qui étaient hors de 109. Il remplace aussi les genres de même poids par un ordre principal/secondaires, et l'absence de suivi par un état Reviewed. Cet état signifie « classement vérifié », jamais « morceau écouté ». Aucune écoute automatique ni transition forcée au morceau suivant n'est ajoutée par le plugin ; les fonctions normales de la file de lecture restent disponibles.

Ne reconduire automatiquement ni la barre globale, ni les méta-familles, ni l'éditeur de filtres booléens avancés, ni la suppression forcée du catalogue de 109. Le premier périmètre comprend la recherche, les genres/tags, les vues de revue, le catalogue et le rangement. Les données historiques de fonctionnalités non exposées sont préservées. Le nettoyage historique des artistes du plan 107 n'est pas relancé et aucun enrichissement distant n'est ajouté.

Le plugin ne renomme pas les fichiers audio : il conserve leur nom et leur extension et les déplace vers les dossiers convenus. Pas de duplication pour représenter plusieurs genres. Pas de réécriture des titres, crédits, pochettes ou tags embarqués. Pas de suppression automatique des dossiers sources vides. Les collisions sont rapportées, sans écrasement ni suffixe automatique inventé. Les mouvements entre volumes seront explicitement indisponibles dans ce premier parcours ; ce choix technique est visible dès l'aperçu et n'est pas une compatibilité livrée.

Les publications ne contiennent ni collection personnelle, ni base, ni correspondances de chemins personnels, ni captures nominatives. Les preuves utilisent des morceaux fictifs et des fichiers synthétiques ou des copies autorisées. La compilation et le smoke-test de l'EXE restent hors de cette demande.

## Parcours proposé à éprouver en maquette

### Entrée, sources et retour à MTEE

Cliquer Plugins montre la liste des modules, dont Genre Manager. Ouvrir ce dernier remplace le contenu de la sidebar par sa navigation avec un retour explicite `Plugins`, et ouvre une page dédiée dans l'éditeur. Les onglets ordinaires, la file et la lecture sont conservés. Revenir à Explorer restitue sa navigation ; ne pas vider définitivement son état. Le module n'affiche pas de tableau de bord intermédiaire sans utilité.

Proposition de composition : la sidebar porte `Classify`, `Genres` et `Uncertain`, la page Classify porte le choix du dossier ou de la playlist et la liste, une palette compacte sert à l'attribution. Le catalogue occupe une page entière. Tester cette composition à 1440 × 900 et à largeur réduite ; le placement exact de la palette n'est pas imposé. Conserver le vocabulaire graphique de MTEE, la police et les composants natifs QML.

À la première ouverture, choisir une source existante. Ensuite, proposer la dernière session et un changement de source par clic sur son nom dans l'en-tête, sous le libellé `FOLDER` ou `PLAYLIST`. Une fenêtre interne à MTEE propose deux onglets et affiche la progression en pourcentage dans les listes de sources. Afficher le périmètre et son nombre de morceaux ; la récursion d'un dossier doit être explicite, sans inclure à l'insu de l'utilisateur toute sa racine. La proposition par défaut est le contenu direct, avec `Include subfolders` facultatif. Une playlist est une liste de références aux fichiers existants, pas une destination physique. Le nom d'un dossier, même House, ne décide jamais le genre principal d'un morceau. Une action distincte permet de choisir puis d'appliquer un genre aux morceaux du dossier, sans taguer le dossier lui-même.

La session conserve les identifiants de ses morceaux, son ordre, ses filtres et sa progression. Les déplacements ne vident pas au milieu d'une opération le lot que l'utilisateur examine. Un rechargement de source est explicite ; les nouveaux morceaux apparaissent à vérifier. On peut reprendre la revue après fermeture. Une même piste présente dans plusieurs playlists partage ses genres et son statut, tandis que la sélection et le pinceau sont propres à la session.

### Deux variantes comparables

Les variantes utilisent la même liste fictive, les mêmes genres et les mêmes scénarios. Elles sont basculables dans le prototype pour comparaison, sans changer les données. Le choix de conserver les deux dans le produit final reste ouvert jusqu'à l'essai utilisateur.

| Intention | Variante sélection puis attribution | Variante pinceau |
|---|---|---|
| Choisir les cibles | Sélection simple, Ctrl/Maj et sélection de résultats annoncés | Choisir un genre ou un tag actif, puis sa zone de marquage sur chaque ligne |
| Attribuer | Cliquer un élément de palette l'ajoute à la sélection ; état mixte intelligible | Le marqueur ajoute ou retire cet élément sur un seul morceau |
| Retirer par lot | Action nommée et contextualisée ; un état mixte n'inverse pas aveuglément chaque piste | Sélection ordinaire disponible pour la même action de lot |
| Jouer | Commande Play explicite, distincte de la sélection | Même commande Play, hors cible de peinture |
| Vérifier | `Mark as reviewed` porte sur les identifiants sélectionnés | Même commande ; peindre ne signifie pas sélectionner ni vérifier |
| Changer de principal | Déplacer la puce avant les autres, ou `Make primary` accessible au clavier/menu | Même geste sur les affectations existantes |

Dans les deux variantes, montrer seulement les affectations réellement présentes, leur ordre et la famille utile. Ne pas afficher une palette complète de tous les genres sur chaque ligne. Distinguer visuellement et au clavier sélection, lecture, présence du pinceau et revue. Un clic de marquage consomme son événement ; il ne joue pas, ne sélectionne pas accidentellement et ne commence pas un déplacement de fichier. Le glisser de puce réordonne les genres ; il ne déclenche pas le glisser de morceaux.

Le marqueur change immédiatement d'apparence avec un état d'enregistrement observable, puis confirme le succès. Une erreur reste lisible près de l'action, sans annoncer de succès ; elle propose une reprise et conserve le contexte. `Undo` et Ctrl+Z annulent une opération locale complète, sans détourner Ctrl+Z de la saisie de texte. Le retour visuel indique le résultat concret, par exemple `Deep House added to 3 tracks`, pas un compteur opaque seul.

Le coût de la sélection après peinture est un sujet explicite de l'essai : effectuer plusieurs marquages, écouter, puis valider une sélection. Si ce geste paraît laborieux, réviser la maquette avant le branchement ; ne pas introduire silencieusement une validation automatique à la place de la décision utilisateur.

### Catalogue, création et tags

La page Genres permet de parcourir l'arbre et de créer, renommer, déplacer, ordonner, archiver et restaurer des définitions. Les UUID restent stables. Une zone d'édition dans la page remplace le manager modal. La création rapide depuis la palette se fait sur place, avec un parent clairement visible ; elle ne nécessite pas une succession de pop-ups. L'utilisateur doit distinguer créer une définition et l'attribuer à des morceaux.

Pour les tags, afficher un état vide utile au départ et une saisie de création. Aucun mot, notamment banger, n'est injecté comme tag applicatif par défaut. Le prototype simule sa création par l'utilisateur. Les tags sont des puces indépendantes et réutilisables, applicables au pinceau et à une sélection, sans hiérarchie ni ordre principal. Le libellé `Create tag` concerne la définition ; l'attribution et le retrait sont contextualisés, sans les boutons globaux incompréhensibles `+ Tag` / `− Tag`.

Les suppressions ordinaires se limitent aux définitions inutilisées et sans descendants. Pour une définition utilisée, proposer l'archivage ; préserver sa lecture sur les morceaux existants. Une suppression forcée n'est pas nécessaire pour atteindre ce premier parcours. Les alias et la recherche doivent distinguer les homonymes sans exiger d'apprendre des identifiants techniques.

### Revue, filtres et rangement

`All tracks` conserve les morceaux vérifiés à leur place avec une coche. `To review` ne montre que ceux qui restent à vérifier ; après une validation réussie, les lignes concernées quittent cette vue. Attendre la fin du geste et maintenir une ancre de scroll et un focus cohérents pour éviter qu'un second clic touche un autre morceau. La lecture en cours et sa file ne changent pas quand une ligne disparaît.

Le bouton de revue annonce sa sélection, par exemple `Mark 12 as reviewed`. Aucun morceau masqué n'est inclus tacitement. Le nombre total vérifié porte sur la session complète et se distingue du nombre de résultats filtrés. Un changement effectif de genres ou de leur ordre invalide la revue dans toutes les sessions ; une opération sans effet, un tag ajouté, une lecture ou un mouvement de fichier ne l'invalide pas.

`Organize files` ouvre un aperçu dans l'espace du plugin, portant par défaut sur tous les morceaux Reviewed du lot courant, même si To review les masque. Le titre et les effectifs rendent ce périmètre explicite ; aucun filtre ne doit faire confondre sélection, résultats et lot. L'utilisateur vérifie les destinations avant `Move N files`. Le bilan distingue déplacés, déjà en place, laissés à vérifier, conflits et éléments occupés. Le genre principal donne une destination unique ; les secondaires et les tags ne dupliquent pas les fichiers.

### Uncertain et artistes

La vue Uncertain regroupe les **attributions de genres aux artistes** non résolues, pas les morceaux encore à vérifier musicalement. Elle montre le morceau, ses crédits actuels, l'extrait utile du titre et le motif d'abstention. Elle permet de ne rien décider ou de choisir explicitement les artistes contributeurs parmi les crédits existants, sans refaire leur identification. Le nom et la place de cette vue restent à valider visuellement.

## Invariants métier et choix de conception à vérifier

### Genres ordonnés et familles

Un genre possède un UUID, un parent éventuel, un nom, des alias, un ordre de catalogue et un état d'archivage. L'arbre est acyclique et n'impose pas une profondeur maximale de deux niveaux. L'ordre du catalogue est indépendant de l'ordre des genres d'un morceau. Les assignations d'un morceau sont uniques, ordonnées et sans ancêtre redondant stocké comme genre secondaire.

Ajouter un premier genre le rend principal. Ajouter un genre distinct le place à la fin. Ajouter un descendant d'une affectation existante précise celle-ci à la même position : `[House]` devient `[Deep House]`, puis `[Deep House, Minimal House]`. La famille House est déduite et affichée séparément ; elle ne prend pas la première place devant Deep House. Un genre d'une autre famille s'ajoute en secondaire jusqu'à une promotion explicite. Le réordonnancement préserve l'ordre relatif des autres genres.

Pour House, les sous-genres initiaux deviennent Tech House, Bass House, Minimal House, Deep House, Disco House et French House, avec leurs alias courts sous House. Ne pas transformer Deep sous Dubstep en Deep House, ni changer les autres familles par une règle de suffixe globale. Le vocabulaire de départ des autres familles vient de la taxonomie de 109 ; ses correspondances de dossiers personnels ne sont pas réappliquées automatiquement.

Deux choix complémentaires sont proposés pour les maquettes : retirer le principal promeut le secondaire suivant ; retirer la dernière affectation explicite laisse le morceau sans genre et à vérifier. Ce second choix remplace la restauration implicite de famille de 109, non reconfirmée dans ce cadrage ; le montrer avant de le figer. Une famille seulement héritée doit avoir un indicateur distinct et ne pas masquer une suppression de tous ses descendants sous une simple décoche. Le pinceau bascule une affectation explicite, pas un sous-arbre implicite.

Renommer un genre ou ses alias ne change pas son identité ni, à lui seul, la revue des morceaux. Déplacer un genre dans l'arbre change son sens et potentiellement sa destination : invalider les aperçus de rangement et proposer comme règle la remise à vérifier des morceaux affectés. Ce cas doit figurer dans la revue du catalogue. Aucun renommage ou reparentage de catalogue ne déplace immédiatement des fichiers.

### État Reviewed et révisions

Conserver une révision de classement, distincte des révisions de tags et des révisions physiques du fichier. Le marqueur Reviewed référence la révision de classement validée. Chaque modification effective des genres ou de leur ordre incrémente cette révision ; un ajout/retrait de tag ne l'incrémente pas. Les nouveaux morceaux et les affectations importées ou amorcées commencent à vérifier.

La proposition est de demander au moins une affectation pour `Mark as reviewed`, tout en acceptant une famille seule. Montrer ce cas vide en maquette et consigner la décision, sans en faire une contrainte utilisateur déjà confirmée. Un lot de validation possède des identifiants et révisions attendues ; il ne valide jamais une correction concurrente que l'utilisateur n'a pas vue. Une erreur empêche le faux affichage d'une revue réussie.

Undo restaure l'état précédent des genres et de la revue dans une nouvelle opération contrôlée, sans écraser une modification ultérieure indépendante. Les opérations sur tags disposent de leur propre précondition pour ne pas annuler accidentellement une revue plus récente. Sauvegarder et reprendre la session ne signifie pas figer indéfiniment une ancienne version de la piste.

### Amorçage sur la nouvelle base

La base reconstruite commence sans affectations de genres de morceaux et sans tags libres. Aucun ordre de préférence n'est inféré depuis un nom de dossier ou depuis le catalogue. Une ancienne base 021 n'est pas migrée par cette étape, conformément à la décision utilisateur ci-dessus.

Sur une base sans genres de morceaux, proposer depuis la source de travail une attribution initiale, par exemple House à un dossier House, avec un aperçu des cibles et du genre choisi. Le nom du dossier est un indice, pas une autorisation d'inférence et d'écriture. L'amorçage explicite ne coche jamais Reviewed et ne remplace pas une correction manuelle, y compris un retrait volontaire de tous les genres. Les anciens tableaux de 109 sont historiques : ne pas rejouer leurs racines, exceptions ou comptes sans nouvelle vérification.

### Genres déduits des artistes

Conserver des contributions séparées, traçables par morceau, artiste, genres, crédits, décision et version de la règle. Ne pas recopier les genres calculés dans les tags manuels du profil. Agréger les genres principaux et secondaires des morceaux vérifiés, dédupliquer les familles et exposer l'origine des contributions. Un classement qui repasse à vérifier suspend sa contribution validée jusqu'à sa nouvelle revue ; les données manuelles des artistes restent intactes.

Utiliser en priorité les rôles de remixer **confirmés sur le morceau**. Les indices du titre Remix, Flip, Bootleg, sans dépendance à la casse, peuvent étayer le rôle si le nom associé correspond sans ambiguïté à un artiste déjà crédité. Ne pas prendre un simple mot avant Remix pour une nouvelle identité, ni faire une fusion approximative de noms. Des indices contradictoires, plusieurs interprétations, un nom absent des crédits ou une version mal identifiée conduisent à Uncertain. Ne pas modifier automatiquement les crédits ni le titre.

Sur un remix identifié, seuls les remixeurs attribués reçoivent ses contributions, pas l'artiste original du seul fait de sa présence. Sur un original attesté, utiliser les contributeurs crédités pertinents. L'absence de Remix/Flip/Bootleg n'est pas à elle seule une preuve d'original : des titres non marqués resteront impossibles à résoudre automatiquement avec certitude. Documenter cette limite ; en cas de rôle/version non établi, s'abstenir. Un choix explicite dans Uncertain prime sur l'heuristique et est invalidé pour réexamen si ses crédits de référence changent. Les tags libres ne sont jamais agrégés sur les artistes.

## Rangement physique : contrat de sécurité et de reprise

### Destinations et aperçu

Une table de correspondance locale relie les UUID de genres à des destinations. Elle peut proposer une arborescence par famille, par exemple `House/Deep House`, `House/Minimal House`, et `House` pour la famille seule. **Les noms exacts de dossiers et la racine sont des propositions à examiner**, pas des choix utilisateur déjà obtenus. Permettre de réutiliser un dossier existant au lieu de créer un doublon orthographique. Un renommage de genre ne réécrit pas silencieusement cette correspondance.

Pour une playlist mélangeant plusieurs dossiers ou racines, exiger une destination explicite et montrer chaque chemin source et cible. Ne jamais déduire une racine depuis le premier morceau de la playlist. Le même `track_id` n'est planifié qu'une fois. Le déplacement modifie le fichier partagé par ses autres playlists ; ses références MTEE suivent l'identifiant. Les références par chemin d'applications externes ne sont pas mises à jour par ce plan : l'aperçu le précise lorsque le rangement est proposé.

L'aperçu porte un identifiant, un instantané du lot, les révisions de classement et de source, le principal choisi, les destinations résolues et les opérations prévues. Il ne crée aucun dossier musical et ne déplace rien. Il identifie collisions existantes et intra-lot, dossiers manquants à créer, noms Windows invalides, destinations hors racine, volumes distincts, sources absentes, fichiers occupés et pistes sans principal confirmé. Refuser les traversées de chemins et revalider les racines résolues, y compris les jonctions, avant mutation.

Une confirmation porte sur cet aperçu concret. Un changement pertinent avant exécution invalide les éléments concernés ou le plan, avec un nouveau résultat à examiner ; ne pas appliquer une ancienne destination après une correction de genre. Les morceaux non vérifiés restent en place. Les affectations de genre et tags ne sont jamais écrites dans l'audio, même lors du déplacement.

### Exécution et journal durable

S'appuyer sur `FileAccessCoordinator`, `JobService` et les primitives de déplacement existantes. Ajouter les préconditions de l'aperçu et un journal durable par fichier avant toute mutation physique. Sérialiser les écritures de classement et de rangement pertinentes pour empêcher un déplacement fondé sur un principal devenu périmé. Le lecteur garde sa priorité : un fichier occupé est différé ou signalé, sans arrêter automatiquement la musique.

Créer uniquement les dossiers annoncés, puis déplacer sans remplacer une destination apparue entre-temps. Sous Windows, vérifier réellement la sémantique sans écrasement utilisée. Une réussite disque et une réussite SQLite sont deux étapes distinctes. Journaliser au minimum préparé, déplacement constaté, bibliothèque actualisée, réussite ou problème récupérable, avec l'identité du fichier attendue. Mettre à jour chemin et appartenances aux racines en conservant `track_id`, playlists, analyse et classements.

Prévoir l'arrêt entre chaque étape : au redémarrage, comparer sources, destinations, révisions et preuves du journal. Quand l'identité ne peut plus être prouvée, laisser l'opération en conflit au lieu d'écraser un chemin ou de considérer le déplacement réussi. Une comparaison SHA-256 peut compléter les révisions pour la reprise critique ; elle s'effectue hors du thread graphique. Le retour arrière existant du service n'est pas un substitut à cette reprise durable.

L'annulation d'un lot en cours arrête les prochaines opérations ; les fichiers déjà déplacés restent décrits dans le bilan. Ne pas présenter ce comportement comme un rollback global. Une action `Undo organization` prépare les mouvements inverses des seules réussites, recontrôle fichiers et destinations, et refuse les conflits ultérieurs. Ne pas restaurer toute la base pour annuler des mouvements partiels. Une sauvegarde SQLite protège les données mais ne constitue pas une sauvegarde des fichiers déplacés.

## Architecture proposée et interfaces à créer

Les chemins ci-dessous désignent des **livrables futurs**, sauf points d'intégration identifiés comme existants. Adapter les noms au dépôt au début de l'exécution en consignant la décision ; ne pas lire une liste de chemins comme la preuve de leur existence.

| Ensemble | Responsabilité et fichiers proposés |
|---|---|
| Entrée Plugins | `src/mtee/plugins/registry.py`, registre statique minimal et fabrique différée ; raccords limités dans `app.py`, `models/workspace_model.py`, `qml/components/Sidebar.qml`, `ActivityBar.qml`, `EditorGroup.qml` |
| Domaine du module | `src/mtee/plugins/genre_manager/domain.py` : arbre, assignations ordonnées, revue, opérations sans effet et transitions |
| Persistance et service | `src/mtee/plugins/genre_manager/repository.py`, `service.py` : lectures groupées, commandes, préconditions, journal et sauvegardes |
| Modèles Qt | `src/mtee/plugins/genre_manager/models.py` : session, catalogue et modifications incrémentales des lignes ; réutilisation de `TrackListModel` quand son contrat convient |
| Artistes | `src/mtee/plugins/genre_manager/artist_attribution.py` : règles conservatrices, contributions et résolution des incertitudes |
| Rangement | `src/mtee/plugins/genre_manager/organizer.py` : correspondances, preview/apply/recover/undo, raccord au service de fichiers existant |
| QML | `src/mtee/qml/plugins/genre_manager/` : page, navigation, liste, palette, catalogue, Uncertain et aperçu de rangement ; réemploi du thème et des primitives existants |
| Prototype isolé | `src/mtee/qml/prototypes/genre_manager_110/`, `scripts/review_genre_manager_110.py` et `docs/ux/review-110-genre-manager.md` |
| Mesures et usage | `scripts/measure_genre_manager_110.py`, `docs/usage/genre-manager.md` et [rapport de validation](../docs/validation/110-plugin-genre-manager.md) |

QML reçoit des modèles et envoie des intentions typées ; aucun accès direct à SQLite, au système de fichiers ou aux commandes. Les lectures longues, la préparation d'un lot et ses mutations passent hors du thread graphique. Les modèles Qt sont mis à jour sur leur thread. Toutes les commandes métier passent par le service du plugin plutôt que par un accès direct QML ou modèle vers le repository.

Le service expose des lectures groupées de catalogue, session et affectations, puis des commandes explicites : ajouter/retirer un genre ou tag, ordonner les genres, définir le principal, marquer une sélection Reviewed, administrer le catalogue, préparer/appliquer un rangement et résoudre une attribution. Chaque commande porte un identifiant d'opération et des révisions attendues ; le résultat distingue succès, absence d'effet, conflit et échec. Une répétition après timeout ne doit pas inverser deux fois une affectation au pinceau : traduire le clic en intention `present=true/false`, avec précondition, plutôt qu'en toggle aveugle rejoué.

À l'ouverture ordinaire de MTEE, le registre ne charge que les métadonnées du module. Ne pas instancier le catalogue, enrichir toutes les lignes, calculer les agrégats ou lancer un scan parce que le module est disponible. Les connexions aux signaux et caches du plugin sont libérés ou suspendus quand inutiles ; un rangement encore en cours conserve son service et sa visibilité dans Tasks. L'isolement est organisationnel dans le processus Python, pas un prétendu bac à sable de plugins tiers.

Les listes utilisent des requêtes groupées, des identifiants stables et la virtualisation existante. Pas de requête, accès disque ou traversée de tout le catalogue par delegate QML. Mettre à jour les lignes touchées au lieu de réinitialiser la collection. Les résultats asynchrones portent un jeton de session/requête pour ne pas écraser une source ou un pinceau plus récent. L'intégration playlists doit éviter de reproduire le coût par morceau observé dans `PlaylistService.rows()` ; charger les pistes en lot sur un worker sans refondre les comportements hors périmètre.

### Migrations et données durables

Ne pas réintroduire `021_track_genres.sql`. Créer `022_genre_manager.sql` pour la base actuelle 020 et les bases neuves ; le saut du numéro 021 est volontaire et n'en reprend ni le nom ni le contrat. Ne pas forcer `user_version` pour contourner les contrôles.

Utiliser les UUID stables des pistes et artistes. Ajouter un ordre d'affectations, la révision de classement/validation, les sessions et leurs morceaux, les destinations, le journal de rangement et les contributions d'artistes. Aucun tag libre n'est prédéfini.

Sur base 020, la migration crée le stockage puis le module initialise son catalogue à sa première utilisation. Sur historique 021 ou autre inconnu, refuser l'adaptation avec un diagnostic et laisser les données intactes. Aucun nettoyage automatique de schéma résiduel n'est ajouté.

Avant migration, sauvegarder par l'API SQLite dans un chemin unique, hors collection, sans écrasement ; rouvrir la copie et vérifier son intégrité avant de poursuivre. Le `backup_to()` actuel ne suffit pas à garantir à lui seul tous ces contrôles : les ajouter et les tester. Les commandes de restauration doivent être ciblées ; ne pas écraser les corrections d'artistes ni restaurer une ancienne base entière pour adapter le plugin.

## Jalons d'exécution

### 110.0 — État initial et mesures

Relire ce plan entier et les règles, inspecter Git, les changements locaux, les migrations et les points d'intégration. Vérifier ce qui a été intégré depuis la préparation. Créer des fixtures synthétiques dans `.local/validation/110/`, et le script de mesures proposé. Préparer des bases 020 et 021 historiques sur copies pour la compatibilité ; l'inventaire d'une base utilisateur, s'il devient nécessaire lors de l'exécution, est d'abord en lecture seule et reste hors Git.

Mesurer le lancement, l'ouverture d'un dossier et d'une playlist, le scroll, la sélection et la lecture dans le socle de référence. Consigner révision, état local, machine, options et données. Ne pas affirmer que 109 causait le lag sans reproduction. Aucun branchement fonctionnel de genres ne commence dans ce jalon.

### 110.1 — Maquettes manipulables

Créer les composants isolés et le lanceur du tableau d'architecture. Utiliser le thème actuel, un modèle fictif réinitialisable et des fichiers audio synthétiques pour tester de vraies commandes Play explicites avec le lecteur existant dans un runtime isolé. Aucun accès aux données utilisateur. Le lanceur prend `--variant selection` ou `--variant brush`, `--scenario` et `--data-dir` ; ces options sont à créer ici.

Montrer entrée Plugins, remplacement de sidebar, choix de source, House et ses sous-genres, hybride entre familles, liste de playlist, tags initialement vides puis créés, sélection multiple, changement de principal, Reviewed, les deux affichages, erreur/reprise/annulation, catalogue sur page, Uncertain et aperçu de mouvements. Le déplacement reste simulé. Ajouter une session de dix nouveaux morceaux et un exemple de 80 vérifiés sur 100. Les titres sont fictifs.

Consigner dans `docs/ux/review-110-genre-manager.md` les parcours à essayer, captures, gestes et questions réellement ouvertes. Distinguer lecture native effective, états simulés et données persistées seulement dans le prototype. Une capture ou un chargement sans erreur ne vaut pas essai utilisateur. Le passage entre modes ne doit ni perdre les décisions ni rendre l'état du pinceau ambigu.

### 110.2 — Revue utilisateur distincte

Faire essayer les mêmes tâches dans les deux variantes, depuis les sources : classer trois titres connus, écouter un titre, ajouter un secondaire, le promouvoir, ajouter/retirer un tag, valider une sélection et passer de All tracks à To review. Examiner ensuite le catalogue et le rangement. Demander les retours **en texte dans le chat** : l'utilisateur a signalé que le questionnaire structuré de son application bugue.

Résoudre la disposition de sidebar/palette, la variante ou coexistence finale, la validation après peinture, le retrait du dernier genre, la validation d'un morceau sans genre, le reparentage et les correspondances physiques proposées. Ces choix ne doivent pas être demandés abstraitement avant que le résultat soit examinable. Consigner l'accord explicite et les corrections, puis seulement exécuter les surfaces fonctionnelles correspondantes. Le silence ou la demande de « tester les deux » n'est pas cette validation.

### 110.3 — Socle du plugin et données sur copies

Créer le registre minimal, le domaine, repository et service, puis la migration neuve 022. Ajouter les index nécessaires aux lectures par morceau, genre, statut de revue et session. Initialiser les genres une seule fois, les tags libres restant vides. Tester sauvegardes, migration 020 vers 022, refus sûr de l'ancienne 021, normalisation des familles, ordre, revue et undo avant toute base réelle.

Créer `tests/unit/test_genre_manager_domain.py`, `tests/integration/test_genre_manager_repository.py`, `tests/integration/test_genre_manager_upgrade.py` ; compléter `tests/integration/test_database_migrations.py`. Les fixtures contiennent des corrections d'artistes existantes pour démontrer leur conservation. Contrôler unicité des rangs et UUID, transactions atomiques, relance idempotente, retrait manuel vide et conflits de révisions. Adapter les règles de style Qt à l'emplacement des nouveaux modèles si nécessaire, de façon ciblée.

### 110.4 — Classement, catalogue et progression

Brancher les pages retenues, les modèles Qt et les commandes de lecture explicites. Conserver le lecteur global et la file ; modifier seulement les raccords nécessaires des composants partagés. Implémenter l'administration en page, la création rapide, les tags, les genres ordonnés, les états d'enregistrement, la sélection, Reviewed, les filtres simples et la reprise de session. Le mode pinceau n'est branché que s'il fait partie du choix issu des essais ; le prototype des deux modes reste disponible comme preuve de comparaison.

Créer `tests/unit/test_genre_manager_session.py` et `tests/ui/test_genre_manager_workflow.py`. Vérifier les intentions au clavier/souris et leur absence d'effets parasites sur lecture, sélection, glisser et file. Contrôler les mêmes pistes visibles dans plusieurs sessions, les filtres après revue, les résultats asynchrones périmés et la fermeture/réouverture. Exercer la session des nouveaux morceaux. Ne pas ajouter les genres/tags à Info ou aux listes ordinaires à cette étape.

### 110.5 — Organiser les fichiers vérifiés

Créer les correspondances de destination et `organizer.py`, les modèles et pages d'aperçu/bilan, puis le journal et la récupération. Étendre les primitives de fichiers existantes pour les préconditions et le journal si nécessaire ; ne pas les contourner par des commandes système QML. Les dossiers à créer sont inclus dans l'aperçu.

Créer `tests/unit/test_genre_organizer.py` et `tests/integration/test_genre_organization_recovery.py`, étendre `tests/unit/test_file_move_service.py` et exercer le parcours QML. Tester uniquement sur copies : cas normal, House seul, secondaire sans copie, playlist multi-dossiers, 80 sur 100, morceau occupé, collisions avant/après aperçu et intra-lot, principal périmé, doublons d'UUID, volume différent, racine invalide, exception SQLite et interruption à chaque phase. Relire après fermeture/réouverture. Vérifier noms, octets, pochettes, identités, références de playlists et analyses conservés.

L'application réelle ultérieure est une action explicite sur l'aperçu de l'application, pas une conséquence d'un test ou du lancement de l'agent. Une étape réussie sur copie ne vaut pas collection personnelle réorganisée. Documenter le retry, l'annulation des prochaines actions et le retour inverse des réussites.

### 110.6 — Artistes et Uncertain

Créer le calcul des contributions, leurs préconditions et la vue de résolution. Consommer les crédits déjà confirmés plutôt que relancer l'identification artistique. Exposer les résultats calculés via une frontière claire vers le catalogue artistes, avec origine visible ; ne pas mélanger ces résultats aux tags manuels ni introduire l'affichage différé des tags sur les listes de morceaux.

Créer `tests/unit/test_genre_artist_attribution.py` et `tests/integration/test_genre_artist_contributions.py`. Couvrir original attesté, remixeur confirmé, Flip/Bootleg dans le titre, identité absente ou ambiguë, remix non marqué, plusieurs remixeurs, contradiction entre titre et rôle, crédits modifiés, décision manuelle de destinataires, revalidation et retrait d'une contribution. La fixture Madonna/remixeur prouve l'absence de genre UKG automatiquement attribué à Madonna pour ce seul remix. Aucun tag banger n'atteint les artistes. Uncertain reste facultatif pour terminer le rangement.

### 110.7 — Recette, performances et livraison

Comparer le socle aux mêmes données avec le plugin jamais ouvert, ouvert, puis quitté. Mesurer sur une vue House de 340 morceaux, une collection fictive de l'ordre de 2 800 et un jeu de 10 000 pour détecter les coûts proportionnels ; ces tailles sont des scénarios, pas une nouvelle mesure de la bibliothèque personnelle. Tester aussi une grande playlist. Rapporter chargement, requêtes, rendu, saisie, clic vers feedback, scroll, lots et mémoire, pendant la lecture.

Objectifs d'ingénierie proposés, à consigner avec leur protocole : feedback de clic au 95e percentile inférieur à 100 ms, première liste de 340 morceaux utilisable en moins d'une seconde sur la machine de référence, absence de pauses répétées du thread graphique supérieures à 50 ms pendant le scroll. Répéter cinq fois les mesures comparables et rapporter médiane et dispersion. Ces seuils sont des propositions du plan, pas des résultats ni des exigences imposées par l'utilisateur. Les latences disque se traduisent par un état de progression, jamais un blocage de l'interface.

Vérifier surtout l'absence de requêtes des genres et de calculs artistes dans les chemins ordinaires tant que le plugin n'est pas chargé. Examiner toute régression reproductible hors dispersion plutôt que masquer un coût par une moyenne. Aucun nombre arbitraire de tests réussis ne tient lieu de preuve. Refaire seulement les contrôles rendus nécessaires par une correction ou un échec restant.

Mettre à jour le guide, la spécification de la surface et le rapport, exercer les parcours manuellement depuis les sources sur copies et publier. Une recette indisponible reste marquée non faite avec une reprise concrète. Pas de build Windows automatique.

## Commandes futures et preuves de recette

Toutes les commandes partent de la racine du dépôt. Les deux scripts de 110.0–110.1 existent depuis l'exécution du 9 octobre et s'appliquent aux données isolées ; les tests et fonctions de 110.3–110.7 ci-dessous restent futurs. Les commandes n'étaient pas à exécuter lors de la préparation documentaire initiale.

Après 110.1, essais séparés des deux variantes, avec données isolées :

    uv run python scripts/review_genre_manager_110.py --variant selection --scenario house --data-dir .local/validation/110/prototype-selection
    uv run python scripts/review_genre_manager_110.py --variant brush --scenario house --data-dir .local/validation/110/prototype-brush

Après 110.3, domaine, données et adaptation :

    uv run python -m pytest tests/unit/test_genre_manager_domain.py tests/integration/test_genre_manager_repository.py tests/integration/test_genre_manager_upgrade.py tests/integration/test_database_migrations.py

Après les jalons correspondants, interactions, rangement et artistes :

    uv run python -m pytest tests/unit/test_genre_manager_session.py tests/ui/test_genre_manager_workflow.py
    uv run python -m pytest tests/unit/test_genre_organizer.py tests/integration/test_genre_organization_recovery.py tests/unit/test_file_move_service.py
    uv run python -m pytest tests/unit/test_genre_artist_attribution.py tests/integration/test_genre_artist_contributions.py

Compléter par les régressions des composants effectivement touchés : listes, playlists, interactions pointeur, lecteur, artistes et migrations. Les tests en cours de création dans le checkout peuvent avoir changé au moment de l'exécution ; vérifier leur présence au lieu de les annoncer comme acquis. Effectuer Ruff, vérification de formatage et Pyright sur le code modifié ; conserver les erreurs préexistantes distinctes des régressions.

Après création du script en 110.0 puis extension en 110.7, mesures comparables :

    uv run python scripts/measure_genre_manager_110.py --mode baseline --data-dir .local/validation/110/perf-baseline --with-ui
    uv run python scripts/measure_genre_manager_110.py --mode plugin --data-dir .local/validation/110/perf-plugin

Le script génère ou utilise des fixtures synthétiques équivalentes, étiquette l'état du plugin et la révision testée, écrit les mesures hors Git et ne modifie pas la collection personnelle. Il ne lance aucune conversion, analyse musicale ou reconstruction d'EXE.

Recette fonctionnelle après préparation effective des données isolées :

    uv run python -m mtee --data-dir .local/validation/110/runtime --smoke-test
    uv run python -m mtee --data-dir .local/validation/110/runtime

Un test QML hors écran ne prouve pas la fluidité ni la lecture native. Conserver/restaurer les variables de plateforme des tests avant un lancement interactif. Les résultats de 109 ne sont pas des tests de 110.

## Critères d'acceptation observables

| Situation | Résultat attendu |
|---|---|
| MTEE ouvert, plugin jamais visité | Pas de barre des genres dans les dossiers/playlists, pas de chargement du catalogue sur leur chemin courant |
| Plugins puis Genre Manager puis Explorer | Navigation dédiée, contexte antérieur restitué, lecture conservée |
| House puis Deep House puis Minimal House | House visible comme famille, Deep House principal, Minimal House secondaire ; noms complets propres à House |
| Promouvoir Minimal House | Ordre changé, destination calculée depuis Minimal House, revue invalidée |
| Marquer au pinceau pendant lecture | Genre/tag basculé visiblement, morceau courant et sélection non modifiés par erreur |
| Jouer volontairement un morceau | Lecture correcte, aucune affectation de genre ni validation implicite |
| Installation neuve puis création de banger | Aucun tag initial ; puce créée volontairement, utilisable dans plusieurs genres |
| Valider House seul | Reviewed conservé après réouverture ; destination House |
| Changer genres / changer tags | Retour à vérifier dans le premier cas seulement |
| All tracks / To review | Coche à position stable / retrait après validation réussie, sans changement de file |
| Deux sessions, même piste | Classement et revue cohérents, pinceau/sélection indépendants |
| Erreur de sauvegarde puis retry/Undo | Aucun faux succès ni double inversion ; préconditions respectées |
| Organiser 80 vérifiés sur 100 | Aperçu des 80, 20 inchangés ; déplacement après examen, bilan réel |
| Playlist composée de plusieurs dossiers | Destination explicite ; chaque fichier déplacé une fois, références MTEE conservées |
| Collision, fichier occupé, ancien aperçu | Conflit ou report visible, aucune perte ni arrêt forcé du lecteur |
| Interruption entre disque et SQLite | Journal relu et état rapproché sans mouvement aveugle ; conflit si preuve insuffisante |
| Annulation après une réussite partielle | Résultats conservés, retour inverse contrôlé et limité aux réussites |
| Madonna et remixeur UKG | Contribution sur le remixeur certain seulement ; ambiguïtés dans Uncertain |
| Cas incertain ignoré | Morceau classable, vérifiable et rangeable sans nouveau chantier de crédits |
| Ancienne base 021 | Refus diagnostiqué sans modification ; la nouvelle base est reconstruite séparément selon la décision utilisateur |
| Nouveaux morceaux | À vérifier, anciens choix conservés, reprise courte du même parcours |

## Documentation, commits et publication

À chaque jalon, actualiser les quatre sections de suivi et [le rapport](../docs/validation/110-plugin-genre-manager.md), en séparant rédaction, code, tests automatisés, recette manuelle, revue utilisateur et opérations réelles. Les maquettes approuvées et ajustements sont consignés dans leur dossier de revue. Les dispositions d'Info et des listes ordinaires attendent une demande et leurs propres maquettes.

Avant commit, inspecter l'état et les diffs ; indexer explicitement les seuls fichiers du jalon. Ne pas inclure les changements locaux du lecteur ou des listes réalisés par un autre travail. Vérifier `git diff --check`, puis `git diff --cached --check` et le contenu indexé. Écrire un message détaillé dans un fichier temporaire et utiliser `git commit --file`. La préparation documentaire reçoit son propre commit ; elle n'annonce aucun test applicatif.

Faire fetch, vérifier la divergence, puis pousser vers la branche autorisée sans réécriture d'historique ni push forcé. Après push, refaire fetch et comparer les révisions locales et distantes. Le compte rendu donne la preuve de publication ; ne pas créer un commit supplémentaire uniquement pour inscrire son propre hash dans le document.

## Outcomes & Retrospective

2026-10-09 — 110.3 est livré sur bases synthétiques : migration 022, 31 genres initiaux, zéro tag libre, décisions avec révisions, reprise de session et chargement groupé des sources. Les 31 tests ciblés passés, Ruff, Pyright et une exécution manuelle sur base temporaire sont consignés dans le rapport. La base personnelle n'a pas été touchée. Les jalons 110.4–110.7 restent ouverts ; les conclusions historiques de préparation ci-dessous décrivent leur état à leurs dates respectives.

2026-10-09 — Le cadrage décrit maintenant un espace de travail dédié, deux variantes à essayer, des genres ordonnés, une revue explicite, un rangement des seuls morceaux vérifiés et des attributions artistes prudentes. Il distingue les décisions utilisateur des propositions d'interaction encore à confronter aux maquettes. Le rollback de 109, les modifications locales en cours et les limites des primitives de fichiers sont pris en compte.

Cette préparation ne livre aucune fonctionnalité et ne garantit aucun gain de performance. Maquettes, choix définitif de variante, migrations, recette applicative, déplacements réels et packaging restent non réalisés. La prochaine exécution commence par 110.0–110.1 et s'arrête à la revue 110.2 avant le branchement fonctionnel.

Révision du 2026-10-09 : création du plan après la série de questions utilisateur, avec remplacement explicite des contrats incompatibles de 109. Contrôles documentaires et publication : voir le rapport et le compte rendu de cette préparation.

Révision du 2026-10-09, exécution : 110.0 et 110.1 sont prêts pour l'essai comparatif. Les deux maquettes QML, le lanceur, quatre captures et [le dossier de revue](../docs/ux/review-110-genre-manager.md) sont livrables. Le banc a préparé des copies synthétiques 020/021 et établi des temps sur les services, la fenêtre QML et la lecture native silencieuse, avec les limites indiquées ci-dessus. La revue 110.2, les choix visuels, les migrations, le rangement et les contributions artistes restent non réalisés. Aucun fichier musical personnel n'a été modifié.
