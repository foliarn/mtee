# 23 — Correctifs UX/UI : cadrage et guide pour GPT‑6 Luna

## Résultat attendu et portée

Transformer les retours de la page [MTEE — UX/UI](https://app.notion.com/p/3e9d502f2cc080c3b7c4ce2a24c067e5) en cinq lots courts, exécutables séparément. La page et ses deux captures ont été lues le 28 septembre 2026. Ce dossier prépare le travail ; aucune modification de l’application n’est réalisée pendant sa rédaction.

Les plans 24 à 28 décrivent respectivement le lecteur, l’arborescence, le défilement et la recherche, les colonnes et le tri, puis les waveforms. Chaque plan donne le comportement, les sources à lire, les tâches, les tests et la recette. Les chemins sont relatifs à la racine du dépôt. L’interface reste en anglais, les documents en français.

« UX/UI only » signifie ici corriger les interactions et la présentation des fonctions existantes. Cela peut nécessiter un changement ciblé d’un modèle Qt, de l’état du lecteur ou des préférences. Cela n’autorise aucune reprise de l’analyse musicale, des playlists, de l’édition audio ou des opérations fichiers abandonnées. Les éventuels calculs nécessaires aux couleurs de waveform constituent une extension technique distincte à chiffrer et borner dans le plan 28.

## Sources et état vérifié

Lire `AGENTS.md`, `PLAN.md`, `PLANS.md`, ce plan, puis le plan de catégorie choisi. Les plans 16, 18, 19 et 22 expliquent les contraintes de stabilisation. La référence visuelle est `docs/ux/specification.md` : palette Acid, gris neutres, lime et magenta, Geist Sans, angles droits, interface desktop Qt Quick.

Le point de départ inspecté est `main`, commit `adf3f49`. Les modifications locales préexistantes de `.gitignore`, `AGENTS.md` et `.codex/` appartiennent au contexte utilisateur et doivent rester hors des commits de ce dossier. Vérifier à nouveau cet état au démarrage de chaque lot.

Le graphe code-review-graph correspondait au HEAD inspecté. Ses recherches et graphify ont servi à situer les composants ; les constats ci-dessous viennent ensuite des sources. Les scénarios de bugs n’ont pas été reproduits en lançant l’application pendant la planification. Les causes proposées sont donc des pistes à confirmer par une reproduction ciblée.

Le plan 22 atteste une distribution monofichier et des smoke-tests, mais conserve des réserves sur la recette native. Cette série poursuit les corrections de l’existant ; elle ne déclare pas les anciens lots intégralement validés et ne rouvre pas les livraisons historiques 07–15.

## Décisions utilisateur et choix de préparation

Les réponses utilisateur du 28 septembre 2026 sont intégrées ci-dessous. Les choix ordinaires complémentaires sont identifiés séparément. Le choix de la variante waveform reste soumis à la revue de maquettes prévue par `PLAN.md`.

| Sujet | Attente précisée | Décision |
|---|---|---|
| Tri de référence | Remplace la mention titre croissant du brouillon | Date de création décroissante au lancement et au retour au défaut ; aucune flèche dans cet état |
| Recherche « active » | Focus séparé du filtre et du tri | Échap et clic ailleurs retirent le focus ; texte et résultats filtrés restent ; clic sur une ligne du même listing conserve le focus si la recherche le possédait |
| Colonnes | « Amovible » et portée des réglages | Glisser-déposer des en-têtes, menu de visibilité, préférences globales mémorisées |
| Waveform | Monochrome, 3 bandes ou RGB | Comparer trois maquettes avant de choisir un rendu |
| Cible masquée par la recherche | Exception au double-clic arbre → révélation | Conserver la recherche et jouer le morceau sans le révéler dans la liste |

Autres choix ordinaires proposés : largeurs de colonnes comprises dans le profil global ; pochettes visibles par défaut ; option de pochettes limitée au tableau, la grille Artwork gardant ses images ; temps du curseur en `m:ss` puis `h:mm:ss` ; scrollbar visible 1 200 ms après la dernière interaction avant son fondu ; accélération initiale de molette de 1,25. Le tri manuel reste propre à l’onglet pendant une session et revient au défaut au redémarrage, alors que les colonnes personnalisées persistent. Ces paramètres sont à documenter et peuvent être ajustés après la recette, sans élargir le périmètre.

La suggestion « zoom in un peu » est interprétée comme un besoin de rendre les passages discernables. Le plan 28 étudie d’abord l’échantillonnage d’affichage, la densité et l’enveloppe. Si un véritable zoom temporel devient le choix retenu, il faut réviser explicitement son périmètre et ses interactions avant de le coder.

## Couverture de la note Notion

| Identifiant | Demande | Plan et preuve attendue |
|---|---|---|
| P1 | Après pause, lancer un autre morceau doit le jouer | 24 : backend non pausé, temps qui avance, commandes cohérentes |
| E1 | Double-clic arbre → sélectionner, révéler et lire | 25 : UUID sélectionné, ligne visible, une seule activation ; si masqué par la recherche, lecture sans révélation |
| E2 | L’arbre ne saute plus en haut en ouvrant/cliquant un dossier | 25 : ancre visible stable, y compris au retour du worker |
| S1 | Défilement plus rapide dans l’arbre et les listes | 26 : déplacement mesuré à molette identique, pavé tactile préservé |
| S2 | Scrollbar visible au moins une seconde | 26 : maintien après interaction puis fondu |
| R1 | Sortir de la recherche avec Échap/clic ailleurs, exception sur une ligne | 26 : focus, texte, filtre et raccourcis vérifiés séparément |
| R2 | Recherche alignée avec les boutons | 26 : centres verticaux communs, pas de chevauchement |
| C1 | Toutes les colonnes déplaçables et masquables | 27 : Title compris, menu et glisser-déposer |
| C2 | Dates de création et de modification disponibles | 27 : colonnes et tri numériques, valeurs absentes lisibles |
| C3 | Afficher/masquer les covers | 27 : option persistée, commandes de lecture toujours accessibles |
| C4 | Supprimer la colonne # | 27 : aucun numéro ordinal ni en-tête # dans le listing |
| C5 | Trois états de tri | 27 : ascendant, descendant, défaut ; état explicite |
| C6 | Tri par défaut sur la création du fichier | 27 : nouveaux onglets et retour au défaut |
| C7 | Base Title, Artist, Date created, BPM, Key | 27 : ordre exact sur profil neuf et après réinitialisation |
| W1 | Waveform plus précise et moins pleine visuellement | 28 : comparaison sur mêmes données et mêmes dimensions |
| W2 | Étudier 3 bandes/RGB dans l’UI | 28 : variantes, décision visuelle puis données adéquates si retenues |
| W3 | Marqueur temporel et trait de suivi | 28 : repère lisible, alignement aux bornes et après seek |
| W4 | Partie déjà lue plus sombre | 28 : séparation exacte à la tête de lecture, lecture et pause |

## Ordre d’exécution et taille des sessions

Exécuter 24, puis 25, puis 26, puis 27, puis 28. L’ordre permet de fiabiliser la lecture avant le double-clic, puis la navigation avant les modifications de mise en page. Une session Luna traite un seul jalon cohérent et termine par une note de reprise. Les fichiers `workspace_model.py` et `TrackListView.qml` sont partagés : intégrer les changements séquentiellement.

Pour 26, 27 et 28, préparer les états de maquette indiqués avant le code fonctionnel concerné. Une maquette QML avec données fictives et captures suffit ; conserver la direction graphique déjà validée. Regrouper les captures dans `docs/ux/review-ux-ui-2026-09.md`, à créer au premier jalon de maquettes. Présenter des choix concrets, puis consigner la décision utilisateur. Une demande d’exécuter le dossier n’est pas une validation anticipée d’une variante encore inexistante. Les correctifs 24 et 25 restaurent des interactions demandées et n’ajoutent pas de direction visuelle à valider.

Chaque catégorie peut recevoir des commits intermédiaires. Avant de déclarer une catégorie livrée : tests pertinents, parcours manuel depuis les sources, mise à jour de son plan et du rapport, commit détaillé et push vérifié. Reconstruire et vérifier la distribution Windows seulement si le packaging, les dépendances ou les ressources embarquées changent, ou avant une version à distribuer ; noter le report dans les autres cas. Ne pas transformer une simple réussite de compilation en preuve d’interaction ou d’audio.

## Contrats communs

La sélection, le morceau en lecture et le focus clavier sont trois états distincts. L’identité est `track_id`, jamais un index de ligne durable. Un tri ou un résultat asynchrone peut déplacer la ligne sans modifier l’identité sélectionnée. L’arbre conserve son ancre, tandis que la liste centrale peut défiler intentionnellement pour révéler la cible d’un double-clic.

Les accès fichiers, SQLite, décodages et calculs longs restent dans les services et workers existants. Les mutations de modèles Qt sont appliquées sur leur thread propriétaire. Les réponses asynchrones transportent une génération ; une ancienne navigation ne doit pas sélectionner ou lancer un morceau dans un autre onglet.

Utiliser un profil `--data-dir` isolé et des fixtures synthétiques. Aucune écriture sur une collection personnelle pour la recette. Aucune migration de catalogue ne doit être créée pour une préférence d’affichage déjà stockable dans la session. Si le format de session évolue, adapter sa validation et sa reprise sans effacer racines, onglets ou sélection.

## Commandes communes et preuves de livraison

Depuis la racine du dépôt, les commandes suivantes existent déjà. Exécuter les tests détaillés du lot après avoir adapté ou ajouté les cas annoncés. Les nouveaux fichiers de test sont explicitement signalés dans chaque plan.

    uv sync --locked
    uv run python -m compileall -q src/mtee
    uv run python -m mtee --demo --data-dir .local/validation/ux-ui-demo --smoke-test
    uv run python -m mtee --data-dir .local/validation/ux-ui-live --smoke-test
    git diff --check

Pour la recette interactive, relancer la dernière commande sans `--smoke-test`, puis ajouter uniquement le dossier synthétique de recette. Vérifier le chargement QML sans erreur de binding/import et les parcours souris/clavier. Le plan 22 remplace la chaîne Ruff/Pyright obligatoire par une chaîne courte ; ne pas installer de nouveaux outils de lint pour ce dossier. Si un contrôle supplémentaire est effectivement utilisé, noter sa commande et son résultat.

Pour une catégorie qui déclenche un contrôle de distribution selon `PLANS.md` :

    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/smoke_packaged.ps1 -DataDir .local/validation/ux-ui-packaged

Exercer alors aussi le scénario du lot dans `dist/MTEE.exe` avec un profil isolé. Si le binaire est verrouillé, utiliser les options existantes `-DistDirectory` et `-WorkDirectory` avec des chemins distincts ; lancer alors explicitement cet EXE alternatif, puisque `smoke_packaged.ps1` vise toujours `dist/MTEE.exe`. Ne pas fermer de force une session utilisateur. Le test sur Windows propre hors checkout demeure une preuve distincte à consigner si effectué.

Créer `docs/validation/ux-ui-NN.md` pour chaque catégorie NN. Y inscrire le commit source, les commandes, les fixtures, la taille de fenêtre, le facteur d’échelle Windows, le périphérique de défilement, les résultats et les limites. Les captures utilisent des titres et chemins synthétiques.

Examiner `git status --short`, `git diff`, puis indexer uniquement les fichiers du lot. Vérifier `git diff --cached --check` et `git diff --cached`. Écrire le message multiligne dans un fichier temporaire avec une here-string PowerShell non interpolée, puis `git commit --file <fichier>`. Ne pas recopier un nombre de tests ou un résultat encore non observé.

La branche inspectée est `main`. Avant le push, faire `git fetch origin` et examiner `git log --oneline --left-right HEAD...origin/main`. Intégrer les divergences compatibles sans réécriture ; ne jamais forcer. Si la branche n’a pas changé, pousser avec `git push origin main`, refaire `git fetch origin`, puis comparer `git rev-parse HEAD` à `git rev-parse origin/main`. Si une branche de travail est nécessaire, utiliser `codex/ux-ui-<categorie>` et annoncer sa destination réelle. Les anciens plans mentionnant `fix` ne demandent pas de recréer cette branche supprimée.

## Consignes prêtes à copier pour Luna

Pour commencer le premier lot :

    Lis AGENTS.md, PLAN.md, PLANS.md, les plans 23 et 24 dans Plans d'exécution/.
    Exécute uniquement le plan 24. Vérifie d'abord les sources et reproduis le bug
    pause A → lancement B. Maintiens les quatre sections de suivi. Utilise des
    données de recette isolées. Termine par les tests ciblés, la recette native,
    le packaging si le lot le modifie, un commit détaillé et un push vérifié. Décris toute
    validation que tu n'as pas pu réaliser. Préserve les changements locaux étrangers.

Pour une catégorie suivante, remplacer NN par 25, 26, 27 ou 28 :

    Lis AGENTS.md, PLAN.md, PLANS.md, le plan 23 et le plan NN de la série UX/UI.
    Exécute son prochain jalon inachevé, après vérification des prérequis et des
    décisions utilisateur. Prépare toute maquette requise avant sa revue. Avance
    sur les tâches indépendantes autorisées. Ne réintroduis aucune fonction
    abandonnée. Mets à jour le plan, les preuves et la note de reprise. À la clôture
    du lot, vérifie le packaging si le lot le modifie, committe et pousse sans force.

Après chaque session, la note de reprise donne : dernier jalon terminé, fichiers modifiés, validations réellement passées, décision encore nécessaire, prochaine action précise. Éviter « tout est fait » si une maquette, une recette ou le push manque.

## Progress

- [x] 2026-09-28 — Page Notion et deux captures lues ; sources et tests pertinents inspectés.
- [x] 2026-09-28 — Cinq catégories, couverture et consignes de reprise préparées.
- [x] 2026-09-28 — Réponses sur tri, colonnes, recherche, variantes et cible masquée intégrées.
- [ ] Maquettes concernées préparées et décisions visuelles consignées.
- [ ] Plans 24–28 implémentés, vérifiés et livrés.

## Surprises & Discoveries

2026-09-28 — Les colonnes de dates et leur tri existent déjà dans les modèles ; le menu ne les expose pas. `Title` est forcé visible dans QML. Les contrôles de lecture des lignes partagent l’espace du numéro ordinal : retirer # exige de préserver ces commandes. Le test de waveform en démo utilise des samples vides ; il ne valide pas sa lisibilité.

## Decision Log

2026-09-28 — Codex : préparer des plans versionnés par catégorie à partir de la source Notion, sans modifier cette page ni le code fonctionnel. Limiter les changements Python aux contrats nécessaires aux interactions. Utilisateur : création décroissante sans flèche au défaut, colonnes globales, conservation de la recherche hors focus, lecture sans révélation d’une cible filtrée et comparaison des trois rendus de waveform.

2026-09-29 — Utilisateur : arrêter le repackaging à chaque itération et jalon. Les catégories se vérifient depuis les sources ; le binaire autonome est reconstruit aux points définis dans `PLANS.md`.

## Outcomes & Retrospective

Dossier de planification préparé à partir du commit `adf3f49`. Les réponses utilisateur sont intégrées. Structure, encodage, liens et 41 références de chemins vérifiés ; rapport dans `docs/validation/ux-ui-planification-2026-09-28.md`. Aucun correctif applicatif, test d’application, build ou parcours natif n’est annoncé comme réalisé par cette préparation. Le commit et la confirmation du push sont donnés dans le compte rendu de conversation.

Révision du 28 septembre 2026 : création du cadrage et de la couverture complète du brouillon Notion.

Révision du 29 septembre 2026 : adaptation des contrôles de distribution au cycle de développement rapide. Les builds déjà consignés dans les lots 24–28 restent des faits historiques.
