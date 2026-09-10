# 01 — Construire le socle desktop et une première distribution Windows

## Objectif et résultat observable

Depuis une installation Python propre, MTEE ouvre une fenêtre sombre QML en anglais, affiche son état de démarrage et se ferme proprement. Une distribution autonome produit le même résultat sur Windows sans Python installé. Ce jalon rend possibles les maquettes et les fonctionnalités suivantes sans anticiper le lecteur, la conversion ou l'analyse.

Ce plan vivant respecte `PLANS.md` à la racine et couvre `PLAN.md` §1, §4.0 et l'étude Rekordbox préalable prévue au §2.

## Progress

- [x] (2026-09-10) Plan préparé ; aucun code du socle n'est encore réalisé.
- [x] (2026-09-10) Vérifier les dépendances Python/QML et la stratégie de distribution Windows.
- [x] (2026-09-10) Créer le paquet, la fenêtre et le thème local.
- [x] (2026-09-10) Créer les contrats de données, la persistance et les tâches en arrière-plan.
- [x] (2026-09-10) Documenter l'étude Rekordbox et les décisions de dépendances natives.
- [x] (2026-09-10) Exécuter les tests et fabriquer la distribution Windows ; contrôle après empaquetage réussi sur le poste de développement.
- [ ] Vérifier la distribution sur une machine Windows propre, sans Python, uv ni Qt.
- [ ] Faire vérifier le parcours interactif de la fenêtre par l'utilisateur.
- [x] (2026-09-10) Mettre à jour les preuves et créer le commit détaillé.
- [x] (2026-09-10) Confirmer le push de l'étape.

## Surprises & Discoveries

Au moment de la planification, le dépôt n'a pas de `pyproject.toml`, `uv.lock`, code applicatif ni tests. Les chemins et commandes ci-dessous étaient des livrables à créer.

Réalisation du 10 septembre 2026 : `uv` était absent de la machine, qui ne disposait que de Python 3.14. Il a été installé dans l'espace utilisateur après accord explicite, et son répertoire `Scripts` reste hors du `PATH` : chaque commande de la recette l'ajoute à la session.

Un modèle Qt exposé à QML sans référence Python est supprimé par le ramasse-miettes : la table apparaissait vide, sans message d'erreur. Les modèles sont désormais retenus par l'objet d'exécution d'`app.py`.

`Connection.executescript` valide la transaction en cours avant d'exécuter son script, ce qui priverait les migrations de leur caractère transactionnel. Les scripts sont découpés avec `sqlite3.complete_statement` et rejoués instruction par instruction.

La plateforme Qt `offscreen` des tests ne fournit aucune police : le texte s'affiche en caractères manquants. Les captures de recette sont donc prises avec la plateforme Windows réelle.

Le paquet complet `PySide6` embarquait 190 Mo de `Qt6WebEngineCore.dll` inutilisé, pour une distribution de 377 Mo.

## Decision Log

Décision du 10 septembre 2026, Codex : introduire Mutagen dès le socle pour lire les métadonnées de la livraison A ; l'écriture reste réservée au plan 05. Le tableau de la livraison A impose leur affichage, même si §4.3 mentionne l'ajout de Mutagen à l'étape d'édition.

Décision du 10 septembre 2026, Codex : privilégier d'abord une distribution PyInstaller en répertoire, plus facile à inspecter pour les ressources QML et DLL. Une expérience sous Windows doit confirmer ce choix avant verrouillage ; si elle échoue, évaluer l'outil de déploiement PySide6 et consigner le remplacement. Aucune version exacte n'est présentée comme déjà compatible.

Décision du 10 septembre 2026, Codex : introduire les identifiants et révisions de source sans développer les tables de toutes les fonctions futures. Les migrations ultérieures ajoutent leur propre schéma.

Décision du 10 septembre 2026, Claude : retenir `PySide6-Essentials` plutôt que le paquet complet. Les add-ons apportent Qt WebEngine et Quick3D, inutilisés par MTEE ; la distribution passe de 377 Mo à 138 Mo et le contrôle après empaquetage reste vert. Un module d'add-on redevenu nécessaire ferait l'objet d'une nouvelle décision et d'un nouveau verrou.

Décision du 10 septembre 2026, Claude : placer le module QML sous `src/mtee/qml/Mtee/` avec son `qmldir`, au lieu du `qml/theme/Theme.qml` proposé. Le nom du répertoire doit correspondre à l'URI du module importé, y compris sur un système sensible à la casse ; `Main.qml` reste à la racine de `qml/`.

Décision du 10 septembre 2026, Claude : ne pas télécharger les fichiers de Geist Sans. Le mécanisme d'enregistrement est livré et la police de repli du système est utilisée ; l'ajout des fichiers et de leur licence est décrit dans `LICENSES/README.md`.

Décision du 10 septembre 2026, Claude : ajouter `scripts/smoke_packaged.ps1`. L'exécutable distribué est fenêtré, donc un appel direct depuis un shell rend la main sans code de sortie lisible ; le script attend le processus et propage son code.

Décision du 10 septembre 2026, Claude : renoncer aux noms `JobCancelled` et `FileAccessTimeout` au profit de `JobCancelledError` et `FileAccessTimeoutError`, conformément à la règle de nommage des exceptions appliquée par Ruff.

## Outcomes & Retrospective

Résultat obtenu le 10 septembre 2026 sur Windows 11 10.0.26200 (AMD64) : la fenêtre QML s'ouvre avec ses zones nommées et des données fictives, écrit ses réglages dans le répertoire prévu, conserve un réglage après redémarrage et se ferme proprement. Contrôles verts : `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, 59 tests, démarrage `--smoke-test` depuis les sources, construction `dist/MTEE/MTEE.exe` et contrôle après empaquetage. Versions verrouillées dans `uv.lock` et expliquées dans `docs/architecture/dependencies.md` ; recette détaillée dans `docs/validation/01-socle-technique.md`.

Limites assumées : la distribution n'a pas été essayée sur une machine Windows propre, faute d'une telle machine ; le parcours interactif n'a pas été exercé par un humain ; les fichiers de Geist Sans ne sont pas versionnés et `Segoe UI` sert de repli ; l'intégration continue n'a pas encore été exécutée ; les études Rekordbox et libmpv restent des questions documentées, sans export ni binaire observés. L'étape n'est donc pas déclarée entièrement recettée sur ces points.

Publication : commit `807803a974769b730065ea59dad5be7e342a6375` poussé sur `origin/main` (`https://github.com/foliarn/mtee.git`), `git rev-parse HEAD` et `git rev-parse origin/main` identiques après `git fetch origin`.

## Contexte et prérequis

L'étape 00 doit avoir créé le dépôt et publié les documents. À partir de la racine, créer une arborescence Python `src/mtee/`. `app.py` assemble les services et charge QML ; `__main__.py` appelle l'entrée de l'application. Les répertoires `domain/`, `services/`, `models/`, `persistence/` et `qml/` séparent respectivement données métier, opérations, modèles Qt, stockage SQLite et présentation.

QML est le langage de description visuelle de Qt Quick. Les modèles Qt présentent des données aux vues et reçoivent leurs actions. Les services Python effectuent le travail ; un service ne doit pas dépendre d'un élément visuel. Le thread graphique est le fil d'exécution qui traite interactions et dessin : les accès longs n'y sont pas exécutés.

Python 3.12 est le point de départ imposé par `PLAN.md`. Vérifier la disponibilité de `uv`, puis installer Python avec `uv python install 3.12` si nécessaire. Consulter les documentations officielles des bibliothèques au moment du choix des versions, consigner leurs URL et versions dans `docs/architecture/dependencies.md`, puis verrouiller l'ensemble dans `uv.lock`. Ne pas installer FFmpeg, ffprobe, NumPy, SciPy ou librosa ici.

## Plan de travail et jalons

### Jalon 1 — Prouver l'installation et le packaging minimal

Créer `pyproject.toml` avec le paquet `mtee`, le layout `src`, la dépendance Python 3.12, PySide6 et Mutagen. SQLite vient de la bibliothèque standard. Le groupe de développement contient pytest, pytest-qt pour les interactions Qt, Ruff, Pyright et PyInstaller. Définir les chemins de découverte des tests et les règles de Ruff et Pyright dans le même fichier. Épingler Python dans `.python-version` et produire `uv.lock` après résolution réussie.

Créer d'abord `src/mtee/__init__.py`, `__main__.py`, `app.py` et `qml/Main.qml` avec une fenêtre minimale. Une expérience de packaging doit produire une fenêtre sans dépendre du répertoire courant. Créer `packaging/mtee.spec`, qui embarque le paquet, les ressources QML, les plugins Qt indispensables et leurs bibliothèques natives, et `scripts/build_windows.ps1`, qui appelle le build, propage son code d'erreur et produit `dist/MTEE/MTEE.exe`. Éviter les imports QtMultimedia et les modules inutilisés. La preuve est un démarrage sur une machine Windows propre et l'absence d'erreurs de chargement QML/DLL.

### Jalon 2 — Établir l'entrée applicative et le thème

Dans `app.py`, créer `create_application(argv)` puis `main(argv=None) -> int`, configurer organisation/nom de l'application, gérer les arguments et charger la fenêtre avec des chemins de ressources indépendants du répertoire courant. Toute erreur fatale de ressource retourne un code non nul et une explication en anglais. `--smoke-test` attend la création de la fenêtre puis quitte ; ce mode ne remplace pas une recette interactive.

Créer `qml/theme/Theme.qml` et les composants nécessaires à une fenêtre 1440 × 900 : fond `#080E18`, panneaux `#111B2B`, surfaces actives `#1B2A40`, textes `#EDF2FA` et `#A5B3C7`, accent/focus `#80B5FF`. Intégrer Geist Sans et sa licence sous `src/mtee/resources/fonts/` et `LICENSES/`. Le thème définit 14 px pour le texte courant, 36 px de hauteur de ligne, rayons 12 px et 6–8 px. Le socle affiche des zones nommées et des données fictives, sans explorateur fonctionnel.

### Jalon 3 — Définir stockage, identité et tâches

Créer `domain/tracks.py` avec `TrackId` basé sur UUID et `SourceRevision(size_bytes:int, mtime_ns:int, file_id:str|None, generation:int)`. La révision est un contrôle de modification, pas une identité cryptographique. Créer `domain/time.py` avec `TimeRange(start_us:int,end_us:int)` valide pour `0 <= start_us < end_us`, fin exclue. Réserver les références source/dérivé à des UUID différents ; ne pas remplir prématurément leurs tables.

Créer `services/app_paths.py` pour obtenir les dossiers de données, cache et logs via `QStandardPaths`, ou sous `--data-dir` pour la recette. Aucun fichier utilisateur n'est écrit dans le dépôt ou à côté de l'exécutable. `--demo` sélectionne une source fictive et un stockage isolé ; il ne charge pas les racines ou paramètres de l'utilisateur. Créer `persistence/database.py`, `migrations/001_initial.sql` et `settings_repository.py` avec transactions, numéro de schéma et sauvegarde cohérente avant migration. Une base trop récente doit être refusée clairement, sans être recréée silencieusement.

Créer `services/jobs.py` et `domain/jobs.py` : `JobService.submit(task) -> JobId`, `cancel(job_id)`, états `queued`, `running`, `succeeded`, `failed`, `cancelled`, progression bornée et erreur structurée avec code. Un worker réalise la tâche ; les signaux mettent les modèles à jour sur le thread Qt. La fermeture refuse de laisser des travaux incomplets invisibles et attend ou annule proprement selon leur nature. Pour les travaux durables introduits par les fonctions suivantes, un redémarrage après arrêt brutal traduit l'ancien travail actif en `failed` avec code `interrupted`, libellé Interrupted, sans inventer un succès. Créer `services/file_access.py` et son `FileAccessCoordinator` pour les accès concurrents par `track_id`, avec acquisition limitée dans le temps et libération garantie. L'application de base n'effectue encore aucune écriture audio.

### Jalon 4 — Étudier les frontières et installer les contrôles

Créer `docs/architecture/overview.md` expliquant les couches et le sens de leurs appels. Dans `docs/architecture/rekordbox-exchange-study.md`, étudier un petit XML représentatif et sa documentation officielle : identifiants, URI de chemins, temps de cues et grilles, unités, réimports. Documenter les observations et questions sans implémenter l'importeur. Les microsecondes internes et les relations de dérivés préparent ces conversions sans supposer leur compatibilité.

Étudier la disponibilité et les conditions de redistribution de libmpv pour l'étape 04 ; consigner l'architecture cible et la procédure future de chargement DLL. Ne pas rendre mpv obligatoire pour démarrer A. Vérifier séparément les licences de Python, Qt/PySide6, la police et l'outil de packaging ; produire `THIRD_PARTY_NOTICES.md` à partir des composants réellement distribués. Le choix de licence du code MTEE reste à décider avant publication d'une version open source sous une licence nommée ; ne pas en attribuer une sans décision.

Créer `tests/unit/test_app_paths.py`, `test_source_revision.py`, `test_jobs.py`, `test_file_access.py`, `tests/integration/test_database_migrations.py` et `tests/ui/test_application_smoke.py`. Tester les cas d'échec réels plutôt que l'existence des classes. Ajouter `.github/workflows/ci.yml` sur Windows pour installation verrouillée, contrôles de code, tests et construction de l'artefact ; ne pas y ajouter un déploiement ou une publication de release automatique.

## Étapes concrètes

Toutes les commandes partent de `C:/Users/flori/Desktop/dev/MTEE`. La première création du verrou suit la déclaration des dépendances ; les reprises ordinaires utilisent le verrou existant.

    uv --version
    uv python install 3.12
    uv python pin 3.12
    uv lock
    uv sync --locked
    uv run python --version
    uv run python -m mtee --demo

La version Python affichée doit appartenir à 3.12. Après création du code, des tests et du script décrits :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_app_paths.py tests/unit/test_source_revision.py tests/unit/test_jobs.py tests/unit/test_file_access.py tests/integration/test_database_migrations.py tests/ui/test_application_smoke.py
    uv run python -m mtee --data-dir .local/validation/01 --smoke-test
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/01-packaged --smoke-test

Chaque commande doit terminer avec code 0 ; un test ignoré faute de dépendance native reste une absence de validation à traiter. Installer la distribution complète en répertoire sur une machine Windows propre, puis exécuter aussi sans `--smoke-test` pour examiner la fenêtre et sa fermeture.

## Validation et acceptation

Depuis un clone propre, `uv sync --locked` suffit à installer l'environnement documenté, sans résolution opportuniste. La fenêtre s'ouvre avec ses ressources, sur un chemin contenant espaces et accents et quel que soit le répertoire courant. Elle écrit ses données dans le répertoire prévu et conserve un réglage simple après redémarrage. `--demo` ne lit ni n'altère les paramètres réels.

Une tâche artificielle de deux secondes laisse déplacer la fenêtre et reçoit une annulation ; une tâche échouée affiche une erreur contrôlée et ne reste pas « running ». Les tests de migration prouvent la conservation des données, le retour transactionnel après échec et le refus d'un schéma trop récent. Le test de verrou par fichier montre que deux écritures ne se chevauchent pas et qu'un échec libère l'accès.

Sur Windows propre sans Python, uv ni Qt installés, la distribution ouvre et ferme la même fenêtre sans accès réseau ni DLL provenant du poste de développement. Consigner version Windows, architecture CPU, commande, résultat et provenance des composants. Si cette machine n'est pas disponible, le packaging peut être construit mais la recette autonome reste non validée et l'étape n'est pas annoncée comme livrée.

## Reprise et réexécution

Réutiliser le verrou et les scripts. Régénérer un verrou seulement pour un changement de dépendance explicitement documenté. Avant une migration, conserver la sauvegarde cohérente ; en cas d'échec, laisser la base précédente intacte. Réserver les expérimentations aux dossiers `.local/validation/01*` et vérifier leurs chemins absolus avant tout nettoyage.

Un souci de QML ou DLL dans l'exécutable se diagnostique sur une construction avec sortie console et chemins de ressources consignés ; le corriger dans la spécification de packaging, sans exiger une installation manuelle de Qt sur la machine cible. Préserver les licences et versions lors d'un remplacement d'outil.

## Interfaces et dépendances

Le socle exporte `main`, `TrackId`, `SourceRevision`, `TimeRange`, `JobService`, `FileAccessCoordinator`, un accès SQLite transactionnel et le stockage des réglages. Les modèles Qt contiennent les rôles visibles, jamais la logique d'écriture. Les tables initiales couvrent version de schéma et réglages ; le catalogue est ajouté au plan 03. Le programme reconnaît `--data-dir`, `--demo`, `--smoke-test` et refuse un argument inconnu avec une aide claire.

Les dépendances de production sont Python 3.12, PySide6 et Mutagen. Les autres outils appartiennent au développement ou au packaging. La lecture native viendra au plan 04, FFmpeg au plan 07, les bibliothèques d'analyse au plan 09. Toute évolution de ces contrats est inscrite dans ce plan et répercutée dans les consommateurs concernés.

## Preuves et livraison Git

Créer `docs/validation/01-socle-technique.md` avec les versions, sorties utiles, essais de distribution, observations QML et décisions issues des études. Mettre à jour le suivi avant le commit sans annoncer son futur hash ni un push non réalisé. Depuis la racine, examiner puis indexer seulement les livrables présents :

    git status --short
    git diff --check
    git add -- pyproject.toml uv.lock .python-version src/mtee tests packaging scripts docs LICENSES THIRD_PARTY_NOTICES.md .github/workflows/ci.yml "Plans d'exécution/01-socle-technique.md"
    git diff --cached --check
    git diff --cached

Adapter ce message aux preuves constatées ; les lignes de validation ne sont pas un résultat acquis :

    $message = @'
    feat(core): créer le socle QML et la distribution Windows de MTEE

    Introduire le paquet Python 3.12, le thème local et les ressources embarquées.
    Séparer domaine, modèles Qt, services et persistance ; ajouter identité,
    révisions de fichiers, tâches annulables et migrations transactionnelles.
    Verrouiller les dépendances et documenter les études natives et Rekordbox.

    Validation : préciser ici contrôles exécutés, essais de migration,
    réactivité et résultat sur machine Windows propre.
    Limites : explorateur, lecture, édition et conversion dans les étapes suivantes.
    '@
    $messagePath = Join-Path $env:TEMP 'mtee-01-commit.txt'
    Set-Content -LiteralPath $messagePath -Value $message -Encoding utf8
    git commit --file $messagePath
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Les deux hashes doivent concorder. Si le distant a avancé ou si le push échoue, appliquer la reprise de `PLANS.md` sans forcer ni créer de faux commit de livraison.

Note de révision — 2026-09-10, Codex : création du plan ; avancer la lecture Mutagen pour satisfaire A et rendre explicites le packaging précoce, les études et les contrats partagés.

Note de révision — 2026-09-10, Claude : réalisation de l'étape ; suivi, découvertes, décisions et limites mis à jour d'après les commandes réellement exécutées.

Note de révision — 2026-09-10, Claude : ajout de la preuve de publication du socle.
