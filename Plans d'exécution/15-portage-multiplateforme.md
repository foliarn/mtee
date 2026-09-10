# 15 — Vérifier un portage Linux et macOS après stabilisation Windows

## Objectif et résultat observable

Un utilisateur Linux ou macOS peut installer une distribution construite pour son système et retrouver les fonctions locales déjà livrées sur Windows, avec des chemins, raccourcis et sorties audio adaptés. Le rapport distingue précisément les systèmes, architectures et fonctionnalités essayés. Un code qui paraît portable ne constitue pas un portage validé.

Ce plan vivant suit `PLANS.md` et le jalon dédié annoncé dans le contrôle commun final de `PLAN.md`. Il est différé, hors de la première trajectoire Windows, et se déclenche par une décision de portage séparée. Sa présence dans l'index ne lance pas ce développement maintenant.

## Progress

- [x] (2026-09-10) Plan différé préparé ; aucun système supplémentaire n'est déclaré pris en charge.
- [ ] Fixer la version Windows de référence et la matrice de cibles à vérifier.
- [ ] Vérifier les dépendances natives et produire un prototype par système.
- [ ] Adapter chemins, corbeille, accès fichiers, ressources et raccourcis.
- [ ] Construire et tester chaque distribution sur une machine propre du système cible.
- [ ] Rejouer les parcours Windows pour détecter les régressions.
- [ ] Consigner la matrice réelle de support, créer le commit et vérifier le push.

## Surprises & Discoveries

Au stade de la planification, les seules contraintes acquises sont Windows en premier et une architecture compatible avec un futur portage. Les machines de test, dépendances natives distribuables et signatures des paquets supplémentaires ne sont pas encore vérifiées. Consigner ici les observations par OS avec version, architecture et reproduction.

## Decision Log

Décision du 10 septembre 2026, Codex : porter un instantané stable des fonctions locales réellement livrées. Les intégrations tierces éventuellement reportées ne bloquent pas le portage du cœur ; leur absence reste affichée. Motif : préserver le fonctionnement autonome demandé.

Décision du 10 septembre 2026, Codex : construire sur chaque système cible, sans supposer qu'un exécutable Windows peut être transformé en distribution Linux ou macOS. Une première cible par système limite le périmètre de qualification ; toute extension de la matrice exige sa propre recette.

Décision du 10 septembre 2026, Codex : commencer l'étude par Linux x86_64 et macOS arm64, puis figer les versions d'OS selon les machines disponibles et le support des dépendances au moment du portage. Ce choix est une proposition de validation, pas une promesse de support ou une nécessité d'achat de matériel.

## Outcomes & Retrospective

Non exécuté. À la clôture, indiquer pour chaque cible : livré et testé, expérimental, ou non vérifié, avec les fonctions réellement exercées et limites. Une seule plateforme validée n'autorise pas à déclarer l'ensemble Linux/macOS livré.

## Contexte et prérequis

MTEE utilise Python 3.12, PySide6/Qt Quick, Mutagen, SQLite, libmpv, et FFmpeg/ffprobe à partir de la conversion. Les bibliothèques d'analyse et éventuels modèles sont introduits par leurs étapes. `src/mtee/domain/` est indépendant de la plateforme, `services/` contient les opérations, `models/` présente les données Qt et `qml/` porte l'interface anglaise. Le packaging Windows fournit déjà `dist/MTEE/MTEE.exe` via `scripts/build_windows.ps1`.

Le socle expose `--data-dir`, `--demo` et `--smoke-test`. Les données de recette sont isolées de la collection personnelle. `track_id` reste un UUID interne stable ; `SourceRevision(size_bytes,mtime_ns,file_id,generation)` observe les changements, avec identifiant système facultatif. Ne pas transformer un chemin Unix en identité et ne pas appliquer partout les règles d'insensibilité à la casse Windows.

Fixer dans `docs/portability/support-matrix.md` le commit Windows de référence, les fonctions incluses, les OS et architectures précis, les versions de Python/Qt et des binaires natifs, la disponibilité des environnements et les exclusions. Les dépendances compatibles et leurs licences doivent être vérifiées dans leurs sources officielles à cette date, puis consignées avec URL et version. Un changement de Python imposé par une dépendance se traite comme une migration distincte vérifiée aussi sous Windows.

## Plan de travail et jalons

### Jalon 15.1 — Prouver les dépendances sur chaque cible

Sur une machine Linux et une machine macOS disponibles, installer l'environnement verrouillé et ouvrir le mode démo. Évaluer séparément le chargement libmpv, un décodage FFmpeg et les imports numériques. Consigner les bibliothèques système encore requises et les ressources Qt. Un démarrage du mode démo ne valide pas l'audio ni l'analyse.

Créer un prototype de distribution par cible, sans fonctions nouvelles. Préférer un répertoire autonome pour Linux et une application `.app` pour macOS, à confirmer selon les outils et licences vérifiés. Le résultat doit retrouver ses ressources depuis n'importe quel répertoire courant. Si une bibliothèque impose une contrainte système, la documenter explicitement ou réduire la cible plutôt que supposer sa présence.

### Jalon 15.2 — Isoler les différences du système

Créer `src/mtee/services/platform_runtime.py` pour sélectionner les adaptateurs. Réutiliser `src/mtee/services/platform/windows_file_ops.py` du plan 06 et ajouter `src/mtee/services/platform/linux_file_ops.py` et `macos_file_ops.py`. Étendre le protocole `PlatformFileOps` existant lorsque nécessaire, sans créer une seconde implémentation Windows concurrente. Faire converger les accès existants vers des contrats étroits : découverte de dépendances natives, identité et comparaison de chemins, corbeille, ouverture d'un dossier dans le gestionnaire système. Éviter les imports Windows au chargement du paquet sur une autre plateforme.

Le service de chemins garde la forme originale affichée et compare selon les propriétés vérifiées du volume. Tester casse sensible et insensible, Unicode composé/décomposé, caractères réservés, chemins longs, fichiers cachés et liens symboliques. Ne pas fusionner deux fichiers distincts à cause d'une normalisation. Les racines absentes restent disponibles pour une reconnexion ; aucune migration ne réécrit arbitrairement des chemins d'un autre système.

Réutiliser les choix de sécurité des opérations physiques : collisions sans écrasement, copie vérifiée entre volumes et corbeille uniquement. L'adaptateur Linux/macOS doit prouver qu'il signale une corbeille indisponible sans supprimer définitivement. Les erreurs de permissions et les fichiers ouverts n'ont pas forcément les mêmes comportements que sous Windows ; les traduire en résultats explicites et conserver le journal d'opérations.

Adapter les raccourcis aux conventions Qt et au système, en particulier Command sur macOS. Tester que Espace ne vole pas le focus de saisie et que les menus restent accessibles. Utiliser les chemins de données et cache fournis par Qt pour chaque OS. Vérifier la lecture sur les sorties audio réellement disponibles, leur changement et leur disparition pendant une session.

### Jalon 15.3 — Construire des distributions reproductibles

Créer `scripts/build_desktop.py` avec `--target windows-x64|linux-x64|macos-arm64`. Le script refuse un hôte/architecture incompatibles, invoque la spécification de packaging adaptée, propage les erreurs et produit un manifeste de versions et hashes des fichiers de la distribution. Conserver `scripts/build_windows.ps1` comme entrée existante appelant la construction Windows, sans casser les commandes des étapes précédentes.

Ajouter les spécifications nécessaires sous `packaging/` et documenter les sorties `dist/MTEE-linux-x64/MTEE` et `dist/MTEE-macos-arm64/MTEE.app/Contents/MacOS/MTEE`. Embarquer ou déclarer explicitement les bibliothèques nécessaires, leurs notices et leurs conditions de redistribution. Mettre à jour `THIRD_PARTY_NOTICES.md` pour les composants effectivement inclus.

Pour une distribution macOS destinée au téléchargement public, étudier la signature et la notarisation avec la documentation Apple actuelle et l'identité de développeur réellement disponible. Les secrets restent dans le mécanisme de secrets de la CI ; aucune identité ou signature n'est inventée. Une application non signée peut servir aux essais locaux, mais ne doit pas être annoncée prête à être distribuée au public. Ne pas demander un certificat avant d'avoir produit le paquet et un besoin concret.

### Jalon 15.4 — Qualifier puis déclarer le support réel

Créer `tests/unit/test_platform_paths.py`, `tests/integration/test_platform_file_operations.py` et `tests/integration/test_native_runtime.py`. Réutiliser les tests fonctionnels existants, en remplaçant uniquement les dépendances système par les adaptateurs de la cible. Les tests spécifiques à un OS indiquent clairement pourquoi ils ne s'exécutent pas sur un autre ; les ignorer sur toutes les cibles ne vaut pas couverture.

Étendre `.github/workflows/ci.yml` avec une matrice de cibles effectivement disponibles. Les tests automatisés et la construction exécutent des contrôles locaux reproductibles ; les scénarios de vrai son, corbeille et paquets téléchargés sont complétés sur les postes cibles. Publier la matrice réelle dans `docs/portability/support-matrix.md`, et garder les cases non vérifiées comme telles.

## Étapes concrètes

Toutes les commandes suivantes partent de la racine du clone sur le système testé. Après création du script et des tests, utiliser le même verrou :

    uv sync --locked
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_platform_paths.py tests/integration/test_platform_file_operations.py tests/integration/test_native_runtime.py
    uv run pytest
    uv run python -m mtee --demo --smoke-test

La suite complète est justifiée ici par le changement transversal de système. Documenter les tests exclus et la cible qui les couvre. Sous Linux, dans le shell du système :

    uv run python scripts/build_desktop.py --target linux-x64
    ./dist/MTEE-linux-x64/MTEE --data-dir .local/validation/15-linux --smoke-test

Sous macOS arm64, dans le shell du système :

    uv run python scripts/build_desktop.py --target macos-arm64
    ./dist/MTEE-macos-arm64/MTEE.app/Contents/MacOS/MTEE --data-dir .local/validation/15-macos --smoke-test

Sous Windows, dans PowerShell :

    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/15-windows --smoke-test

Ouvrir ensuite chaque distribution sans `--smoke-test`. Lancer depuis un emplacement différent du dépôt et vérifier l'absence de dépendance au Python de développement. Les recettes manuelles suivent le périmètre du commit de référence.

## Validation et acceptation

Sur chaque cible annoncée, parcourir des dossiers, redémarrer pour retrouver les onglets, lire les formats promis, changer de vue sans coupure, éditer puis relire des tags, déplacer une copie et la mettre à la corbeille. Vérifier collisions, permissions et erreurs. Une indisponibilité de corbeille doit conserver le fichier.

Convertir un lot avec annulation, afficher une waveform longue, lancer les analyses livrées, retrouver une playlist après déplacement et exporter un passage. Contrôler les hashes des originaux pour toutes les opérations censées les préserver. Tester les fonctions optionnelles présentes, mais maintenir le cœur opérationnel hors connexion et sans modèle facultatif installé.

Mesurer navigation et calculs sur le corpus de référence dans des conditions consignées ; un résultat plus lent conduit à une limite documentée ou à une correction, pas à un seuil déplacé après coup. Vérifier fenêtres aux échelles disponibles, menus natifs, raccourcis, sélection de fichiers et changement de périphérique audio.

L'acceptation exige une distribution reproductible, un parcours réussi sur chaque cible annoncée, des dépendances/licences documentées et une absence de régression du périmètre Windows. Un Linux x86_64 testé ne valide ni toutes les distributions Linux ni ARM ; un macOS arm64 testé ne valide pas Intel. Inscrire ces limites dans la documentation d'installation et l'interface de diagnostic.

## Reprise et réexécution

Conserver des répertoires de données distincts par OS et par recette. Tester les migrations sur copies ; ne pas partager une même base ouverte entre systèmes ou processus. Une fonction système indisponible retourne un état explicite et laisse accessibles les fonctions indépendantes.

Un échec natif se reproduit avec le même manifeste de composants et une sortie diagnostique. Corriger l'adaptateur ou le packaging, puis rejouer les essais concernés et la régression Windows. Ne pas contourner le problème en modifiant les réglages globaux de sécurité du poste ou en incorporant un chemin absolu de développement.

Si une plateforme ne peut pas être vérifiée, consigner la cause et les étapes restantes, conserver les changements portables utiles et laisser la cible non prise en charge. Les nettoyages portent uniquement sur les répertoires de build et de recette dont les chemins absolus ont été vérifiés.

## Interfaces et dépendances

`PlatformRuntime.native_library(name) -> Path | UnavailableReason` résout une dépendance selon le manifeste de la distribution. `PathPolicy.compare(a,b)` et `file_identity(path)` exposent les règles du volume sans devenir l'identité musicale. `PlatformFileOps.trash_strict(request) -> TrashResult` signale succès, annulation ou erreur et ne comporte aucune option de suppression définitive de secours. Conserver les noms et résultats de l'adaptateur réellement livré au plan 06 ; toute extension du protocole est répercutée dans ses tests Windows.

`FileAccessCoordinator`, `PlayerService`, `JobService`, `SourceRevision` et `TimeRange` conservent leurs contrats ; seuls les adaptateurs et chargements natifs changent. Les messages Qt sont émis sur le thread graphique et les tâches longues restent hors de celui-ci. Les bibliothèques natives doivent correspondre à l'architecture de Python/Qt et du paquet final.

## Preuves et livraison Git

Créer `docs/validation/15-portage-multiplateforme.md` avec commit de référence, machines, versions, contrôles, matrices, manifestes et limites. Mettre à jour la documentation d'installation, ce plan et les notices. Depuis la racine Windows du dépôt, après récupération des changements vérifiés sur les autres systèmes :

    git status --short
    git diff --check
    git add -- src/mtee/services/platform_runtime.py src/mtee/services/platform scripts/build_desktop.py scripts/build_windows.ps1 packaging tests/unit/test_platform_paths.py tests/integration/test_platform_file_operations.py tests/integration/test_native_runtime.py docs/portability docs/validation/15-portage-multiplateforme.md THIRD_PARTY_NOTICES.md .github/workflows/ci.yml "Plans d'exécution/15-portage-multiplateforme.md"
    git diff --cached --check
    git diff --cached

Ajouter individuellement les autres adaptations réellement effectuées après lecture de leur diff. Le message doit nommer les cibles effectivement validées :

    $message = @'
    build(platforms): adapter MTEE aux plateformes desktop vérifiées

    Changements : préciser les systèmes et architectures qualifiés,
    adaptateurs de fichiers, raccourcis et distributions reproductibles.
    Validation : préciser machines propres, contrôles natifs, parcours audio,
    tests transversaux et régression de la version Windows de référence.
    Limites : préciser les cibles non testées et le statut de signature des paquets.
    '@
    $messagePath = Join-Path $env:TEMP 'mtee-15-commit.txt'
    Set-Content -LiteralPath $messagePath -Value $message -Encoding utf8
    git commit --file $messagePath
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main

Les hashes doivent concorder. Répéter les pushes de sous-jalons si Linux et macOS sont livrés séparément, en précisant leur périmètre. En cas d'échec ou divergence, conserver l'historique, suivre `PLANS.md` et ne pas forcer le push. Aucun résultat de recette ni hash de son propre commit n'est anticipé.

Note de révision — 2026-09-10, Codex : création d'un plan de portage différé avec une matrice de support démontrée, afin de distinguer architecture portable et distributions réellement testées.
