# 00 — Initialiser Git et rendre le développement reprenable

## Objectif et résultat observable

Le projet possède un historique Git relié à `https://github.com/foliarn/mtee.git`, et un document opérationnel pour chaque étape de `PLAN.md`. Un contributeur peut cloner le dépôt, identifier la prochaine étape et connaître sa recette et sa procédure de livraison. Cette étape prépare le développement ; elle n'implémente pas l'application.

Ce plan est un document vivant régi par `PLANS.md`, à la racine. Mettre à jour ses quatre sections de suivi lorsque l'initialisation, les contrôles ou la publication avancent.

## Progress

- [x] (2026-09-10 08:54 UTC) Lire `PLAN.md` et consulter les pages officielles OpenAI sur les ExecPlans et `AGENTS.md`.
- [x] (2026-09-10 08:54 UTC) Vérifier que le distant est accessible et sans références ; initialiser la branche locale `main` et le remote `origin`.
- [x] (2026-09-10) Rédiger les seize plans, leurs règles et l'index de couverture.
- [x] (2026-09-10) Contrôler les liens, la couverture fonctionnelle, la cohérence des contrats et le diff.
- [x] (2026-09-10) Créer le commit documentaire détaillé.
- [x] (2026-09-10) Pousser et vérifier la correspondance de `HEAD` avec `origin/main`.

## Surprises & Discoveries

Le dossier initial ne contenait que `PLAN.md` et n'était pas un dépôt Git. La première interrogation de GitHub dans l'environnement réseau restreint a échoué ; la même lecture avec accès réseau autorisé a réussi sans afficher de références, ce qui a confirmé un dépôt vide à cet instant.

La recette OpenAI consultée est archivée. Son organisation documentaire convient à cette demande ; ses anciennes recommandations de modèles ne sont pas adoptées.

## Decision Log

Décision du 10 septembre 2026, Codex : préserver `PLAN.md` et créer `PLANS.md` pour la méthode et `Plans d'exécution/` pour les livraisons. Cela évite de confondre la vision produit avec le suivi de réalisation.

Décision du 10 septembre 2026, Codex : utiliser `main` pour le dépôt vide demandé et corriger la ponctuation finale du lien fourni ; l'URL Git se termine par `.git`, sans virgule. La demande autorise l'initialisation et les pushes. Le commit actuel porte sur les plans, les futurs commits sur les étapes effectivement développées.

Décision du 10 septembre 2026, Claude : retirer l'unique ligne vide finale de `PLAN.md` pour que `git diff --cached --check` sorte sans erreur. Le texte du document de référence reste identique ; seul le caractère de fin de fichier change.


## Outcomes & Retrospective

Initialisation locale réalisée, ensemble documentaire rédigé et recette documentaire exécutée : seize plans numérotés et leur index, quatre sections de suivi par plan, liens de l'index résolus, encodage UTF-8 et fins de ligne LF, `git diff --cached --check` sans erreur.

Livraison du 10 septembre 2026 : commit `06e993cad06bdde2ead8df705998f794c61d2e9e` publié sur `https://github.com/foliarn/mtee.git`, branche `main`, avec `git rev-parse HEAD` et `git rev-parse origin/main` identiques après `git fetch origin`. Aucune fonctionnalité applicative n'est déclarée livrée ; l'étape 01 ouvre le développement.

## Contexte et prérequis

Travailler dans `C:/Users/flori/Desktop/dev/MTEE` avec PowerShell et Git. Au premier relevé, Git 2.52.0.windows.1 était disponible et une identité auteur était déjà configurée. Ne pas modifier l'identité globale. Sur une autre machine sans identité, demander l'identité correcte et la configurer localement au dépôt, sans l'inventer.

Les livrables sont `AGENTS.md`, `PLANS.md`, `.gitignore`, `.gitattributes` et les fichiers numérotés 00 à 15 accompagnés de `Plans d'exécution/README.md`. Le fichier original `PLAN.md` reste inchangé. Les répertoires applicatifs évoqués dans les autres plans sont futurs.

Un remote est le nom local d'une destination Git ; `origin` désigne ici le dépôt GitHub. Un commit enregistre un état local et son explication. Le push envoie les commits au distant ; seule sa vérification permet de déclarer la publication réussie.

## Plan de travail et jalons

### Jalon 1 — Reconnaître le dépôt avant de l'initialiser

Examiner les fichiers et les éventuelles consignes locales. Lire l'état Git, l'URL distante, son historique et la branche par défaut. Si le dossier contient déjà un dépôt correct, le conserver. Si le distant possède un historique, le récupérer et établir une base commune avant d'ajouter les documents ; ne pas écraser ses fichiers ni publier un historique concurrent. Pour un dossier non versionné face à un distant non vide, conserver une copie locale des documents et cloner dans un nouveau dossier de travail, puis réconcilier les contenus.

Dans l'état constaté, initialiser `main` et ajouter `origin` suffit. La preuve est la sortie `No commits yet on main` et l'URL attendue pour fetch et push.

### Jalon 2 — Livrer un ensemble documentaire cohérent

Créer les règles et les plans de l'index, en reprenant chaque exigence de `PLAN.md`. Relier `AGENTS.md` à `PLANS.md`. Séparer la revue des maquettes, les travaux ML et Spotify/Shovel, et le portage ultérieur. Inscrire des commandes et comportements attendus, pas des succès hypothétiques. Exclure de Git les données personnelles, corpus privés, caches, secrets et binaires téléchargés avec `.gitignore` ; normaliser les fins de ligne des sources avec `.gitattributes`.

La vérification doit retrouver les étapes 4.0 à 4.11, A à K, le jalon de maquettes et les contraintes communes. Lire aussi les interfaces à travers les plans : chaque fournisseur précède ses consommateurs, aucune analyse n'écrit implicitement un tag et FFmpeg reste absent de A/B.

### Jalon 3 — Enregistrer et publier la préparation

Examiner les fichiers indexés, écrire un message multiligne détaillé puis créer le commit. Pousser sur `main` et vérifier le hash distant. Les étapes de développement suivantes répètent ce cycle après leurs propres recettes, avec un sujet et un corps spécifiques.

## Étapes concrètes

Depuis la racine du projet, la reconnaissance est réexécutable :

    Set-Location -LiteralPath 'C:/Users/flori/Desktop/dev/MTEE'
    git status --short --branch
    git remote -v
    git ls-remote --symref https://github.com/foliarn/mtee.git HEAD refs/heads/main refs/heads/master

Uniquement si aucun dépôt n'existe et si le distant est vide, exécuter les commandes suivantes. Elles ont déjà été exécutées dans cette préparation ; ne pas ajouter à nouveau un remote existant.

    git init --initial-branch=main
    git remote add origin https://github.com/foliarn/mtee.git

Après création des documents, l'inventaire doit contenir exactement seize fichiers d'étape, plus l'index. Lire les résultats et arrêter toute séquence Git au premier code de sortie non nul.

    Get-ChildItem -LiteralPath "Plans d'exécution" -File | Sort-Object Name | Select-Object Name
    rg '^## ' "Plans d'exécution"
    git diff --check
    git status --short
    git add -- PLAN.md AGENTS.md PLANS.md .gitignore .gitattributes "Plans d'exécution"
    git diff --cached --check
    git diff --cached --stat
    git diff --cached

Préparer le message seulement après la recette, en adaptant les assertions à ses résultats réels :

    $commitMessage = @'
    docs(plan): initialiser MTEE et détailler les étapes de développement

    Contexte : transformer PLAN.md en livraisons exécutables et versionnées.

    Changements : conserver la vision produit ; ajouter les règles ExecPlans,
    l'index et seize plans avec prérequis, interfaces, recettes et reprise.
    Prévoir un commit détaillé et un push vérifié après chaque étape.
    Ajouter les exclusions des données locales et les fins de ligne des sources.

    Validation : couverture de PLAN.md, sections de suivi, liens locaux,
    cohérence des interfaces et contrôle du diff examinés.

    Limites : application non implémentée ; maquettes et validations des
    dépendances, plateformes et services externes prévues dans leurs étapes.
    '@
    $commitMessagePath = Join-Path $env:TEMP 'mtee-00-commit.txt'
    Set-Content -LiteralPath $commitMessagePath -Value $commitMessage -Encoding utf8
    git commit --file $commitMessagePath
    git push -u origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short --branch

Les deux identifiants complets doivent être identiques et l'arbre propre après livraison de toutes les modifications prévues. Ne pas exposer de jeton pour établir cette preuve.

## Validation et acceptation

Vérifier que les plans 00 à 15 sont présents, contiennent les quatre sections de suivi et expliquent leurs prérequis, livrables, interfaces, tests, reprise et commit. Les liens de l'index doivent ouvrir les bons fichiers. Vérifier que les actions de développement ne sont pas cochées comme terminées.

Comparer les documents à `PLAN.md` : le lecteur précède la conversion, la conversion précède l'analyse, les tags avancés et playlists suivent l'analyse, les maquettes ont leur revue propre et les formats natifs ne sont pas réputés testés avant leur recette. Aucun corpus personnel, secret, exécutable ou base applicative ne doit être indexé. `git diff --cached --check` doit sortir sans erreur. Aucun test pytest n'est nécessaire pour cette livraison documentaire.

La publication est acceptée lorsque GitHub contient le même commit que `HEAD` et les documents sont consultables depuis le dépôt. Le compte rendu final indique le hash et la destination effectivement vérifiés.

## Reprise et réexécution

Un échec avant le commit se reprend en corrigeant les documents et l'index Git. Un échec du push se reprend en contrôlant le distant puis en poussant le commit existant. Si une branche apparaît sur GitHub pendant le travail, récupérer son historique et le réconcilier ; ne jamais forcer le push. Un refus d'authentification exige de rétablir l'accès Git, pas de stocker un jeton dans l'URL ou le dépôt.

Après la première publication, une correction documentaire prend un nouveau commit. Un éventuel compte rendu versionné du push fait référence au commit précédent ; il ne tente pas de contenir son propre hash. Préserver `PLAN.md` et les autres travaux existants durant toute reprise.

## Interfaces et dépendances

Cette étape utilise seulement Git, PowerShell et Markdown. `AGENTS.md` constitue le point d'entrée des consignes, `PLANS.md` la méthode et `Plans d'exécution/README.md` la table de correspondance. Aucun gestionnaire Python, moteur audio ou compte tiers additionnel n'est nécessaire.

## Preuves et livraison Git

Preuves initiales observées le 10 septembre 2026 : dépôt distant sans références ; `Initialized empty Git repository` ; branche `main` sans commit ; `origin` pointant vers `https://github.com/foliarn/mtee.git`. Compléter ici ou dans le compte rendu de livraison les contrôles effectivement réalisés. Le message et la séquence du jalon 3 sont ceux de cette étape, et non ceux d'une application déjà fonctionnelle.

Note de révision — 2026-09-10, Codex : création du plan à partir de l'état réel du dossier et de la demande d'initialisation, afin de distinguer préparation des plans et développement futur.

Note de révision — 2026-09-10, Claude : clôture de l'étape après recette documentaire, commit et push vérifié.
