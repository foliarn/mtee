# Validation 06b — Correctifs de recette

Ce rapport sépare la preuve disponible, l'implémentation, les tests automatisés
et la recette interactive. Une ligne « non commencé » ne signifie pas que le
retour utilisateur a été réfuté. Les traces brutes restent sous
`.local/validation/06b/` et ne sont pas versionnées.

## Environnement et livraison

- Date : 2026-09-25 ; Windows 11 x64 ; Python 3.12.14 ; PySide6/Qt 6.9.3.
- Révision de départ : `d93e3ba` (`origin/main` identique après fetch).
- `uv sync --locked` : réussi.
- Distribution A0 : build réussi avec PyInstaller 6.22.2 ; EXE de 2,26 Mo ;
  le manifeste de libmpv et le hash DLL ont été validés par le script de build.
- Les modifications préexistantes à `.gitignore`, `AGENTS.md` et `.codex/`
  sont étrangères à ce rapport et ne sont pas indexées.

## Résultats par retour

| ID | Reproduit | Implémenté | Testé | Recetté | Preuve, limite et sous-jalon |
|---|---|---|---|---|---|
| R01 | À confirmer | Non | Non | Non | Définition des covers par taille/DPI à traiter en A1. |
| R02 | Confirmé dans les sources | Non | Non | Non | Scan au démarrage confirmé par `WorkspaceModel.resumeRoots`; correction incrémentale en A2. |
| R03 | Confirmé dans les sources | Non | Non | Non | Adaptateur actuellement WAV seulement selon `docs/validation/05-metadonnees.md`; B après runtime FFmpeg. |
| R04 | Confirmé dans les sources | Non | Non | Non | Bitrate numérique sans unité lisible; formatter partagé à traiter en A1. |
| R05 | Reproduit partiellement | Partiel | Tests ciblés réussis | Recette Windows interactive non faite | Le harnais a observé deux sorties `0xC0000005` sur 20 cycles Python avant le changement (cycles 14 et 19), puis 0/20 après. Le journal Application contient aussi un événement antérieur distinct pour `MTEE.exe` dans `qwindows.dll` à 00:43:45. Aucun lien causal établi entre ces événements. A0 traite le détachement du filtre, les ressources mpv et la fermeture SQLite temporisée ; paquet et scénarios natifs restent à valider. |
| R06 | Confirmé dans les sources | Non | Non | Non | mtime existe, date de création et colonnes absentes; A3 puis C. |
| R07 | Reproduit le 2026-09-25 dans un moteur QML offscreen | Non | Expérience déjà consignée en 06b | Non | Les séquences exposées par Qt échouent à `Array.isArray`, les en-têtes ne suivent pas le choix; correction A1. |
| R08 | Confirmé dans les sources, geste réel non reproduit | Non | Non | Non | Les opérations existantes couvrent seulement une partie des parcours; A3. |
| R09 | Confirmé dans les sources | Non | Non | Non | Préférence initiale false et non persistée; A1. |
| R10 | Hypothèse statique | Non | Non | Non | Dépendance hover/visibilité repérée, scintillement à reproduire; A1. |
| R11 | Confirmé dans les sources | Non | Non | Non | `source` absent dans les deux covers lecteur; A1. |
| R12 | Confirmé dans les sources | Non | Non | Non | Motif générique du seul adaptateur WAV; B. |
| R13 | Confirmé dans les sources | Non | Non | Non | Menu navigue dans MTEE au lieu d'appeler Windows Explorer; A3. |
| R14 | Cause exacte non confirmée | Non | Non | Non | Navigation vers le parent et resets de modèle identifiés; saut exact à instrumenter en A2. |

## A0 — Diagnostic natif et fermeture

### Changements

- `scripts/diagnose_windows_runtime.py` lance un nombre borné de sous-processus,
  avec répertoire de données isolé, délai et rapport sans chemins utilisateur.
- `WindowFrame.detach()` retire le filtre pendant que l'application existe ;
  le runtime l'appelle avant l'arrêt des services.
- `MpvBackend.close()` ne détruit plus son contexte ni son répertoire DLL si le
  thread d'événements survit au délai de jointure ; l'arrêt est signalé.
- `_shutdown_services()` conserve SQLite ouvert lorsqu'un worker dépasse le
  délai, plutôt que de fermer ses connexions sous le worker.
- `--diagnostic-no-native-frame` et `--demo` permettent d'isoler certains
  sous-systèmes lors des prochains essais.

### Contrôles exécutés

- `uv run ruff check .` : réussi.
- `uv run ruff format --check .` : réussi, 144 fichiers conformes.
- `uv run pyright` : 0 erreur, 0 avertissement.
- `uv run pytest tests/unit/test_workspace_model.py tests/unit/test_artwork_service.py tests/unit/test_windows_frame.py tests/integration/test_runtime_shutdown.py tests/integration/test_database_migrations.py` : 25 réussis.
- `uv run python scripts/diagnose_windows_runtime.py --help` : réussi.
- Diagnostic Python avant correctif : 18/20 sorties normales ; cycles 14 et 19
  avec code Windows `3221225477` (`0xC0000005`).
- Diagnostic Python après correctif : 20/20 sorties normales, 0 code d'échec,
  aucune expiration sur le même scénario minimal démarrage/fermeture.
- `pwsh -File scripts/build_windows.ps1` : réussi ; l'EXE et son libmpv intégré
  ont passé les contrôles d'intégrité du script.
- Diagnostic de l'EXE empaqueté : 20/20 sorties normales, 0 expiration avec
  répertoires de données distincts ; l'EXE s'est lancé depuis le dépôt.

### Limites et prochaine action

Ce résultat est une reproduction intermittente du défaut dans un scénario
minimal du processus Python, puis une série sans récidive après correction. Il
ne démontre pas que la faute initiale venait du filtre natif, du thread mpv ou
de Qt ; les trois mesures sont préventives et le lien causal reste une
hypothèse. La répétition de 20 cycles ne couvre pas lecture active, chargement
d'image, maximisation, fermeture pendant job ni paquet autonome. Ne pas
qualifier R05 de résolu avant ces parcours et le diagnostic de l'EXE.

## Journal de suivi

### Progress

- [x] 2026-09-25 — A0 : harnais borné et premiers contrôles de fermeture ajoutés.
- [x] 2026-09-25 — A0 : paquet Windows construit et 20 cycles smoke réussis.
- [ ] A1 — Covers, colonnes, îlot, bitrate et survol.
- [ ] A2 — Réconciliation incrémentale et conservation du scroll.
- [ ] A3 — Dates, révélation Explorer, destinations, déplacement et copie.
- [ ] B — Adaptateurs de métadonnées après runtime FFmpeg/fixtures.
- [ ] 07, 08, 09 ; préparer la revue 10 depuis les analyses réelles.

### Surprises & Discoveries

- 2026-09-25 — Le même harnais Python a reproduit deux access violations sur
  vingt fermetures initiales ; la série de vingt relances après les mesures de
  fermeture n'en a observé aucune. Le taux observé est trop faible pour
  attribuer une cause ou généraliser le résultat.
- 2026-09-25 — L'événement Windows `MTEE.exe`/`qwindows.dll` à 00:43:45 est
  antérieur et distinct des codes d'arrêt Python du harnais. L'événement ne
  confirme pas l'identité du crash signalé par l'utilisateur.

### Decision Log

- 2026-09-25 — Codex — Traiter d'abord les durées de vie natives démontrables
  et protéger SQLite contre les workers survivants ; garder le diagnostic
  d'origine ouvert tant qu'un scénario identique n'est pas reproduit avec
  modules fautifs identifiés.

### Outcomes & Retrospective

A0 implémenté et testé sur le parcours minimal de lancement/fermeture : le
diagnostic Python a échoué 2/20 fois avant les changements puis réussi 20/20
fois après ; l'EXE construit a réussi 20/20 fois. Environnement : Python
3.12.14, PySide6/Qt 6.9.3, Windows 11 x64. La série ne couvre pas les
interactions natives prolongées, lecture, images, maximisation ou jobs actifs.
Les protections réduisent des risques de durée de vie établis dans le code, mais
la cause du crash utilisateur n'est pas prouvée et R05 reste à confirmer. Le
scintillement et le saut de scroll restent des hypothèses non reproduites.
