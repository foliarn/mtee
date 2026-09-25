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
- A3 dates/Explorer: build PyInstaller réussi (2,27 Mo), empreinte libmpv
  vérifiée, puis 20/20 smoke isolés de l'EXE réussis. La recette UI Explorer
  reste à faire.
- A3 copies/destinations: build PyInstaller réussi (2,28 Mo), empreinte libmpv
  vérifiée, 20/20 smoke isolés de l'EXE réussis. Les fixtures vérifient le
  hash, l'UUID distinct, la source intacte, la collision et un temporaire
  récupérable. Le geste souris de drag natif n'a pas été prouvé par QtTest.
- Les modifications préexistantes à `.gitignore`, `AGENTS.md` et `.codex/`
  sont étrangères à ce rapport et ne sont pas indexées.

## Résultats par retour

| ID | Reproduit | Implémenté | Testé | Recetté | Preuve, limite et sous-jalon |
|---|---|---|---|---|---|
| R01 | À confirmer | Oui | Provider sur fixture image synthétique, 256 px demandé | Recette Windows multi-DPI non faite | La cover suit désormais la taille physique avec paliers jusqu'à 1024 px; le provider garde une limite et un cache. La source haute résolution du retour utilisateur n'est pas disponible. |
| R02 | Confirmé dans les sources | Oui | Fixture UI 140 WAV: 0 relecture inchangée; modification/nouveauté relues, suppression retirée; sans reset | Redémarrage réel d'un même profil et collection volumineuse non recettés | La reprise est prioritaire basse, masquée de l'arbre et des tâches; les références restent lors d'un scan incomplet/hors ligne. Le test appelle `resumeRoots()` sur un catalogue déjà indexé, sans fermer/réouvrir le processus. |
| R03 | Confirmé dans les sources | Non | Non | Non | Adaptateur actuellement WAV seulement selon `docs/validation/05-metadonnees.md`; B après runtime FFmpeg. |
| R04 | Confirmé dans les sources | Oui | Formatter testé; donnée brute conservée | Non | Affichage `kbps` arrondi et valeur inconnue lisible. |
| R05 | Reproduit partiellement | Partiel | 20/20 smoke EXE; SEH `0xe24c4a02` imprimé de nouveau pendant un groupe intégration + UI (tests terminés) | Recette Windows interactive non faite | Le harnais a observé deux sorties `0xC0000005` sur 20 cycles Python avant A0 (cycles 14 et 19), puis 0/20 après et 0/20 sur l'EXE reconstruit. Des suites de tests ont également imprimé le fatal SEH du thread libmpv, sans module fautif prouvé ni lien causal établi avec l'accès mémoire utilisateur ou `qwindows.dll`. A0 apporte des protections de durée de vie, pas un correctif causal prouvé. |
| R06 | Confirmé dans les sources | Partiel | Dates unitaires, migration et lecture catalogue testées; nouveau fichier copié obtient son identité et ses dates propres | Recette Windows UI non faite | Migration 007 stocke les dates en ns UTC, sans ctime de repli; colonnes Date created/Date modified et Info sont raccordés. Le déplacement et Copy actualisent via l'observation destination; conversion reste à raccorder; filtres dates réservés à C. |
| R07 | Reproduit le 2026-09-25 dans un moteur QML offscreen | Oui | Menu d'Album réel, en-tête affiché; tests ciblés | Recette interactive non faite | `Array.from` normalise les séquences Qt et le choix met à jour les colonnes. Le test ne couvre pas encore toutes les colonnes, leur réordre, largeur et redémarrage. |
| R08 | Confirmé dans les sources; geste réel non reproduit | Partiel | Copies hashées sur fixtures, UUID distinct, collision, source intacte et interruption/journal vérifiés; destinations de catalogue, modèle clavier unitaire et menu QML chargés; drag vérifié par appel direct seulement | Recette souris Windows, mosaïque, sidebar, 100 éléments et 2 panneaux non faite | Le nouveau journal Copy ne propose aucun Undo; les copies interrompues sont signalées sans toucher à leur source. `Ctrl+A/C/X/V` est raccordé au panneau actif, mais les raccourcis QML n'ont pas été validés par un vrai geste souris/clavier dans l'application. Le drag réel reste un point de reprise. |
| R09 | Confirmé dans les sources | Oui | Tests d'initialisation et persistance du workspace | Recette audio Windows non faite | L'îlot apparaît par défaut; le choix false est conservé après réouverture. |
| R10 | Hypothèse statique | Partiel | Test UI franchit Play ↔ Info, clic Play unique | Recette DPI Windows non faite | Le `HoverHandler` de ligne garde les actions visibles pendant les passages simulés. Le scintillement de la recette n'a pas été observé manuellement sur Windows. |
| R11 | Confirmé dans les sources | Oui | Binding aux données du morceau joué; provider d'artwork testé séparément | A/B/C avec images distinctes non fait | Les deux lecteurs utilisent `playingTrack.coverUrl`, non la sélection de l'inspecteur. Le scénario rapide avec fichiers et retours périmés reste à recetter. |
| R12 | Confirmé dans les sources | Non | Non | Non | Motif générique du seul adaptateur WAV; B. |
| R13 | Confirmé dans les sources | Partiel | Adaptateur vérifié avec chemin accentué, espace, virgule et apostrophe; fixture manquante refusée | Ouverture Explorer réelle non recettée | Le menu transmet maintenant l'UUID au modèle; Windows reçoit un vecteur d'arguments sans shell. Succès indique la demande envoyée, pas la sélection confirmée par Explorer. |
| R14 | Reproduit dans fixture UI | Oui | Double-clic réel QTest sur la ligne 84/140; morceau actif, dossier inchangé, ancre conservée pendant modification/ajout/suppression | Recette interactive à un pixel, 2 panneaux et plein écran non faite | La ligne et l'arbre n'émettent pas de reset complet; les changements structurels utilisent les signaux Qt incrémentaux. |

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

## A1 — Covers, colonnes, bitrate, îlot et survol

### Changements et contrôles

- Les covers demandent au provider des tailles physiques graduées selon la
  taille QML et le DPI; une fixture PNG synthétique de rapport 300×120 confirme
  que la requête 256 retourne une image supérieure au placeholder 96 et
  conserve son aspect. Le cache demeure borné à 1024 px.
- Les colonnes Qt sont normalisées par `Array.from`. Le test QML utilise un
  `WorkspaceModel` réel, choisit Album dans le menu, puis vérifie l'en-tête.
  Bitrate est ajoutable et triable, caché par défaut; l'affichage lit
  `bitrateText` sans remplacer la donnée numérique stockée.
- `islandEnabled` vaut vrai par défaut, se persiste et restaure un choix faux.
  Les deux lecteurs lient leur artwork au cover URL du morceau joué.
- Un `HoverHandler` de ligne agrège le survol; le test déplace le curseur entre
  Play et Info, attend sans oscillation, puis vérifie un seul changement de
  morceau au clic Play.
- Tests ciblés: `uv run pytest tests/ui/test_column_selection.py
  tests/ui/test_track_hover.py tests/unit/test_workspace_model.py
  tests/unit/test_artwork_provider.py tests/unit/test_bitrate_format.py` —
  6 réussis. Ruff, `ruff format --check .` (149 fichiers) et Pyright réussis.
- `pwsh -NoProfile -File scripts/build_windows.ps1`: réussi, PyInstaller
  6.22.2, `dist/MTEE/MTEE.exe` 2,26 Mo, manifeste/hash libmpv contrôlés.
- Diagnostic de ce paquet après A1: 20/20 lancements fermés avec code 0,
  0 expiration, répertoires de données distincts.

### Limites et incident pendant la suite complète

`uv run pytest -q` échoue par exception native pendant le test libmpv, puis
l'accès mémoire fautif apparaît dans le teardown pytest-qt. La séquence des
25 tests d'intégration (incluant libmpv) réussit isolément; ajoutée au test UI
de démarrage, elle échoue de façon intermittente avec `0xe24c4a02` dans le
contexte du thread libmpv. Cette trace ne permet pas d'identifier une cause.
Les 20 cycles du paquet ne couvrent que démarrage/fermeture isolés: le crash
reste une hypothèse ouverte, pas un défaut causal corrigé ni une recette
utilisateur réalisée. L'inspection interactive Windows, multi-DPI et avec
lecture réelle n'a pas été faite.

## A2 — Reprise incrémentale et scroll

- `LibraryRepository.unchanged_paths` compare les `SourceRevision` de chaque
  lot avec les références précédentes. Le worker lit les tags seulement pour
  les fichiers nouveaux ou modifiés; `upsert_locations` refuse de réutiliser
  une photographie si la révision a changé entre-temps.
- `resumeRoots()` marque ses opérations comme silencieuses, non visibles dans
  les tâches, de priorité QThreadPool basse, et ne montre pas l'état Scanning
  dans l'arbre. Le scan explicite conserve visibilité, progression et
  disponibilité Scanning. Un lot incomplet ou une racine absente ne marque pas
  les références comme supprimées.
- `TrackListModel` et `FolderTreeModel` émettent insert/move/remove/dataChanged
  au lieu de `modelReset`, et ne notifient rien quand les lignes n'ont pas
  changé.
- Fixture UI temporaire de 140 WAV: `resumeRoots()` sur catalogue déjà indexé
  appelle le lecteur de métadonnées zéro fois et ne réinitialise ni la liste ni
  l'arbre. Après modification d'un fichier, ajout d'un nouveau et suppression
  d'un autre, exactement deux lectures sont effectuées; les lignes reflètent
  les changements sans reset, la ligne 84 reste en haut du viewport à
  l'identifiant près, et le double-clic lance le bon UUID sans quitter le
  dossier. Les sources sont sous `tmp_path`.
- Tests A2: 19 réussis, 2 ignorés sur scans, modèle, dépôt, reprise et UI;
  Ruff, formatage (151 fichiers) et Pyright réussis. Une séquence de validation
  antérieure incluant `test_browser_navigation.py` a émis de nouveau
  `Windows fatal exception 0xe24c4a02` dans le thread libmpv, tout en terminant
  avec code 0 et 20 tests réussis/2 ignorés. Cela renforce l'observation d'un
  incident natif mais n'établit toujours ni module fautif ni cause.
- Paquet reconstruit: PyInstaller 6.22.2; EXE 2,26 Mo; manifeste/hash libmpv
  valides; diagnostic paquet isolé 20/20 code 0, 0 délai.
- Limites: le scénario UI appelle `resumeRoots()` dans le même processus après
  indexation, pas après un vrai redémarrage; pas de gros catalogue réel, racine
  partiellement lisible ni recette écran/DPI/2 panneaux. R05 reste ouvert.

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
- [x] A1 — Covers, colonnes, îlot, bitrate et survol; contrôles ciblés réussis,
  recette Windows interactive restante.
- [x] A2 — Réconciliation silencieuse/incrémentale, lots, mises à jour de
  modèles sans reset et ancre de liste vérifiés sur fixtures; redémarrage réel
  et collection réelle restant à recetter.
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

A1 implémenté et vérifié sur fixtures: 6 tests ciblés réussis, contrôles
statiques propres, paquet Windows reconstruit et 20/20 smoke isolés. Le test
de survol franchit les deux contrôles et vérifie une activation. La recette
multi-DPI et les changements rapides de covers restent à réaliser. La suite
complète a révélé une exception native intermittente autour de libmpv/Qt; le
résultat contredit toute affirmation de résolution générale du crash. Cause
non prouvée; conserver ce point comme hypothèse jusqu'à instrumentation et
recette sur un poste propre.
