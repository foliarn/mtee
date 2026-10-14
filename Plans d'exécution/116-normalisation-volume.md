# Étape 116 — Normalisation du volume de lecture (type Spotify)

ExecPlan vivant rédigé le 2026-10-14. Suivre `PLANS.md` à la racine. L'étape ajoute à l'analyse existante la mesure de la sonie intégrée (ITU-R BS.1770-4 / EBU R128) et du pic d'échantillon, puis applique à la lecture un gain par morceau, pour que des morceaux d'origines différentes s'écoutent à un niveau voisin. Elle ne modifie jamais les fichiers : ni tags, ni signal.

## Objectif et résultat observable

Un morceau analysé par **Analyze** (clic droit, comme pour le BPM et la tonalité) reçoit une sonie intégrée en LUFS et un pic en dBFS, conservés dans la base à côté du BPM et de la tonalité. À la lecture, libmpv applique à ce morceau un gain en dB calculé ainsi : cible − sonie, sans jamais monter le pic au-delà de −1 dBFS. Le gain est fixé **avant le premier échantillon** du morceau. Le curseur de volume de l'utilisateur continue de s'appliquer par-dessus.

Dans la page Settings, groupe **Playback** de l'onglet General : un interrupteur **Normalize loudness** (activé par défaut) et un choix **Loudness target** (Quiet −23 LUFS, Normal −14 LUFS, Loud −11 LUFS, Normal par défaut). Un morceau sans sonie mesurée joue sans gain.

## Progress

État au 2026-10-14 : implémenté depuis les sources, testé sur signaux synthétiques, sur deux fichiers de vérification et sur le lancement réel du runtime (base vide). Non écouté.

- [x] Lecture du plan 33, des modules d'analyse, du lecteur, de libmpv et de la page Settings.
- [x] Vérification libmpv : propriété `volume-gain` (dB, appliquée avant le volume), lecture et écriture confirmées (voir Surprises).
- [x] Mesure : pondération K (deux biquads de BS.1770-4), gating absolu −70 LUFS et relatif −10 LU, blocs de 400 ms toutes les 100 ms, pic d'échantillon. Module `src/mtee/services/analysis/loudness.py`.
- [x] Migration `025_track_loudness.sql` (colonnes ajoutées à `track_analysis`), dépôt `save_loudness` et `loudness_is_current`.
- [x] Analyze : sonie manquante détectée par `pending`, mesurée seule si le tempo et la tonalité sont à jour, mesurée avec eux sinon, forcée par **Re-analyze**.
- [x] Jamais écrite dans les tags : seuls BPM et tonalité sont envoyés à l'éditeur de tags (test d'intégration sur un fichier réel).
- [x] Gain : `domain/loudness.py` (cible, plafond de pic, cas sans donnée), `PlayerService._open_index` (gain fixé entre le volume et le chargement), `set_normalization` (morceau en cours mis à jour à la modification).
- [x] Réglages : `PlaybackSettingsModel` (clé `playback/normalization`, JSON), exposé au workspace réel et à la démo ; deux lignes QML dans le groupe Playback.
- [x] Tests unitaires, d'intégration (analyse réelle, migration, libmpv) et d'interface (ligne de réglage).
- [x] Vérification de bout en bout par `.local/e2e_116.py` (base neuve dans `.local/run-116`).
- [ ] Écoute : non réalisée, impossible depuis l'environnement.
- [ ] Recette souris/clavier sur la collection réelle de l'utilisateur : non réalisée.
- [ ] Construction et vérification de l'EXE : non demandées, non réalisées.

## Surprises & Discoveries

**libmpv refuse les gains positifs au-delà de +12 dB par défaut.** Sondé sur la DLL vendue (`vendor/mpv/libmpv-2.dll`, 2026-10-14) : `volume-gain` accepte −96 à +12 dB ; une valeur de +30 dB est refusée (erreur −9) et la valeur précédente reste en vigueur. Les bornes sont modifiables à l'exécution : `volume-gain-max` passé à 40 dB, +30 dB accepté et relu. Le backend fixe donc les deux bornes à l'initialisation (`GAIN_LIMITS_DB`).

**Les exemples du brief correspondent à un seul canal plein.** Mesure directe (`.local/loud_probe.py`) à 48 kHz : un sinus 997 Hz pleine échelle sur un seul canal donne −3,01 LUFS, comme demandé ; le même sinus sur les deux canaux identiques donne 0,0 LUFS (+3,01 LU pour deux canaux, selon la norme) ; un sinus 1 kHz de crête −20 dBFS sur deux canaux donne −20,0 LUFS, et non −23. L'implémentation suit la norme, pas l'exemple « stéréo » du brief ; les tests vérifient les valeurs de la norme.

**Pic mesuré au taux d'analyse inférieur au pic réel.** L'analyse décode à 22 050 Hz, ce qui coupe le contenu au-dessus d'environ 10 kHz. Sur le fichier `loud.wav` (crête réelle −0,92 dBFS à 44,1 kHz), le pic mesuré à 22 050 Hz vaut −1,67 dBFS. Le plafond de −1 dBFS est donc respecté pour le signal analysé, mais une boost calculée à partir de ce pic peut dépasser −1 dBFS sur le fichier d'origine d'environ ce même écart (ici 0,75 dB). Voir Decision Log et Outcomes.

**Décalage de sonie au taux d'analyse.** Mêmes fichiers : −44,64 LUFS à 44,1 kHz contre −44,83 à 22 050 Hz ; −14,80 contre −14,98. Décalage stable d'environ −0,18 LU, dû à la bande coupée.

**Référence indépendante.** `ffmpeg -af ebur128` (binaire vendu, utilisé seulement comme oracle hors application) donne −44,6 LUFS et −30,8 dBFS sur `quiet.wav`, −14,8 LUFS et −0,9 dBFS sur `loud.wav`, à 44,1 kHz : le mesureur MTEE, lancé sur les mêmes fichiers au même taux, donne −44,64 / −14,80 et les mêmes pics à 0,01 près.

**Les coefficients K se déduisent du taux.** Les coefficients publiés à 48 kHz sont retrouvés à 1e-9 près par la transformée bilinéaire des paramètres analogiques de la norme (méthode de libebur128). Le même calcul sert à 22 050 Hz, sans rééchantillonnage.

**Les tests existants figent la version de schéma.** Quatre assertions `schema_version() == 23` et des listes de migrations appliquées se terminaient par 23 ; elles passent à 25 (et `test_genre_manager_upgrade` attend `[22, 23, 25]`).

## Decision Log

2026-10-14 — Claude, sur le brief : migration numérotée `025_track_loudness.sql`. Les numéros 021 et 024 sont absents de la chaîne ; `discover_migrations` n'exige pas de suite continue, donc aucune migration intermédiaire n'est créée.

2026-10-14 — Claude, choix technique : la sonie et le pic sont stockés dans `track_analysis` (colonnes `integrated_lufs`, `sample_peak_dbfs`, `loudness_version`), à côté du BPM et de la tonalité. `LOUDNESS_ALGORITHM_VERSION = 1` est indépendant de la version du tempo : une mise à jour de la tonalité ne refait pas la sonie. Un silence (ou un morceau de moins de 400 ms) est enregistré avec des valeurs NULL et la version courante : il est analysé et joue à 0 dB.

2026-10-14 — Claude, choix technique : une passe de décodage unique suffit. Le mesureur est alimenté par les mêmes blocs PCM que l'analyse. Quand tempo et tonalité sont à jour mais la sonie manque, seule la sonie est mesurée (pas de tempo, pas de tonalité, pas de nouvelle écriture de tags). Un morceau complet sans rien à faire n'est pas décodé.

2026-10-14 — Claude, choix technique : la pondération K est dérivée pour le taux d'analyse (22 050 Hz) par transformée bilinéaire des paramètres analogiques de la norme ; le filtrage est une convolution FFT par recouvrement-ajout avec la réponse impulsionnelle tronquée à 8 192 échantillons (décroissance bien au-dessous de 1e-30). Pas de SciPy, pas de rééchantillonnage.

2026-10-14 — Claude, choix technique : mono et stéréo. Le décodage d'analyse produit deux canaux ; un fichier mono est donc mesuré comme stéréo identique, c'est-à-dire comme il s'entend sur une sortie stéréo. Il lit environ 3 dB de plus qu'un mesureur BS.1770 appliqué au seul fichier mono. Choix retenu, car c'est ce que l'utilisateur entend.

2026-10-14 — Claude, choix technique : le gain positif est plafonné à `−1 dBFS − pic` (et à zéro si le pic est déjà au plafond) ; un gain négatif n'est jamais plafonné. Un gain positif sans pic mesuré est refusé (0 dB). Aucune autre borne sur le gain demandé, hormis les limites libmpv `[−96, +40]` : un morceau très faible peut donc recevoir une forte amplification limitée seulement par le plafond de pic (le jeu de fichiers de vérification « quiet » reçoit +30,5 dB). À revoir par l'utilisateur après écoute.

2026-10-14 — Claude, choix technique : le gain est appliqué par la propriété `volume-gain` de libmpv, réglée dans `PlayerService._open_index` entre `set_volume` et `set_paused`/`load`. C'est le seul chemin de chargement (la lecture charge chaque morceau par `loadfile replace` ; aucun préchargement n'existe), donc les transitions automatiques (fin de morceau), les sauts et les reprises passent aussi par ce point. Un changement de réglage pendant la lecture recalcule le gain du morceau en cours (`set_normalization`), sans rechargement.

2026-10-14 — Claude, choix technique : `loudnessLufs` et `samplePeakDbfs` ne sont exposés dans les lignes de morceau que si la mesure est de la version courante et que la durée n'a pas changé (même tolérance que le BPM). Sinon le lecteur joue sans gain jusqu'à la prochaine analyse.

2026-10-14 — Claude, choix technique : réglages stockés en JSON sous `playback/normalization` (`{"enabled": true, "level": "normal"}`), via `SettingsRepository`. `PlaybackSettingsModel` est créé dans `app.py`, rattaché au workspace (réel et démo) ; `PlayerService` reçoit les réglages avant `attach_session`, donc avant l'ouverture éventuelle d'un morceau restauré.

2026-10-14 — Claude, choix technique : aucune écriture de sonie dans les tags, ni ReplayGain, ni limiteur, ni mode album : hors périmètre.

## Outcomes & Retrospective

Livraison depuis les sources, validée sur signaux synthétiques, sur deux fichiers de vérification et sur le runtime réel. Limites : aucune écoute ; mesure non comparée à une collection réelle ; pic mesuré au taux d'analyse (voir Surprises) ; boost potentiellement fort sur un morceau très faible ; plafond de pic ni écouté ni testé sur des inter-échantillons. Les résultats des tests et les contrôles réellement effectués sont consignés dans « Preuves » ci-dessous.

## Contexte et prérequis

Prérequis observés dans le code : analyse de l'étape 33 (`AudioAnalyzer`, `AnalysisService`, `AnalysisRepository`, `MediaDecodeService` en 22 050 Hz stéréo), migrations jusqu'à 023 (les migrations de 015 à 023 sont dans `persistence/migrations/`), `PlayerService` avec `loadfile replace` par morceau, `MpvBackend` avec `volume` et `pause` par propriété, `SettingsView.qml` (groupe Playback des réglages généraux, `ToggleRow` et `ChoiceRow`).

Pas de dépendance nouvelle : NumPy seul (déjà présent).

## Plan de travail et jalons

Jalon 1, mesure. `src/mtee/domain/loudness.py` (`LoudnessResult`, `NormalizationSettings`, `playback_gain_db`), `src/mtee/services/analysis/loudness.py` (`LoudnessMeter`, `k_weighting_sections`).

Jalon 2, persistance. `025_track_loudness.sql`, `TrackAnalysis` étendu, `AnalysisRepository.save_loudness`, `loudness_is_current`, `LibraryRepository` (colonnes et lignes de morceau).

Jalon 3, analyse. `AudioAnalyzer.analyze(..., loudness=False)` (sortie `AnalysisOutcome.loudness`), `AnalysisService.pending` et `_analyze_audio`.

Jalon 4, lecture. `PlayerBackend.set_gain_db`, `MpvBackend.set_gain_db` / `gain_db` / bornes, `PlayerService.set_normalization` et gain dans `_open_index`.

Jalon 5, réglages et interface. `PlaybackSettingsModel`, `workspace_model.py`, `demo_workspace.py`, `app.py`, `SettingsView.qml`.

Jalon 6, tests. Fakes de lecteur mis à jour (sept fichiers de test ont reçu `set_gain_db`) ; faux dépôt d'analyse et faux analyseur de `test_artist_manager_contract.py` complétés (`loudness_is_current`, `save_loudness`, `loudness`) ; assertions de schéma et listes de migrations passées à 25 (`test_database_migrations.py`, `test_genre_manager_upgrade.py`).

## Étapes concrètes

Depuis la racine du dépôt (le répertoire de travail est la racine de la branche de l'étape) :

    uv sync --locked
    uv run pytest -q tests/unit/test_loudness_meter.py tests/unit/test_loudness_gain.py tests/unit/test_playback_settings_model.py
    uv run pytest -q tests/integration/test_track_loudness.py tests/integration/test_mpv_gain.py
    uv run pytest -q tests/unit/test_player_service.py tests/unit/test_playback_queue.py
    uv run pytest -q tests/ui/test_playback_normalization_ui.py
    uv run ruff check <fichiers touchés>

Les fichiers de vérification (non versionnés) se génèrent avec `uv run python .local/make_fixtures_116.py`, puis le bout en bout avec `uv run python .local/e2e_116.py` (base neuve dans `.local/run-116`, jamais la base de l'utilisateur).

## Validation et acceptation

Vérifié par les tests :

- coefficients K à 48 kHz égaux aux valeurs publiées (1e-9) ;
- sinus pleine échelle sur un canal : −3,01 LUFS ; deux canaux identiques : +3,01 LU ; sinus −20 dBFS stéréo : −20,0 LUFS, à 48 kHz et à 22 050 Hz ;
- silence et signal de moins de 400 ms : pas de sonie, pic renseigné ; gating absolu et relatif ; résultat indépendant du découpage du flux ;
- gain : cible − sonie, plafond de pic, pas de gain sans donnée, réglage désactivé, limites libmpv, niveaux ;
- réglages : défaut activé à Normal, persistance, valeurs corrompues ;
- analyse : sonie stockée, jamais dans les tags, morceau ancien recevant seulement sa sonie sans toucher au tempo ni à la tonalité, Re-analyze complet ;
- migration 025 sur une base contenant une analyse ancienne ;
- lecteur : gain réglé avant chaque chargement, transition automatique, réglage modifié pendant la lecture, réglage désactivé ;
- libmpv réel : gain écrit puis relu, +30 dB accepté, bornes respectées ;
- interface : ligne d'interrupteur et choix de niveau modifient les réglages.

Vérifié hors tests, sur le runtime réel (`.local/e2e_116.py`, base neuve, deux WAV stéréo de 24 s) :

- schéma 25 à l'initialisation ;
- scan, puis Analyze par le workspace, sans modifier les fichiers (SHA-256 identiques) ;
- valeurs stockées : `loud.wav` −14,980 LUFS / −1,672 dBFS ; `quiet.wav` −44,827 LUFS / −31,519 dBFS ; version 1 ;
- lecture : gain natif relu +0,672 dB pour `loud.wav` et +30,519 dB pour `quiet.wav`, égaux au calcul sur les valeurs stockées ; ordre des appels : gain, chargement, gain, chargement ;
- niveau Loud en cours de lecture : gain natif inchangé (+30,519, limité par le plafond de pic de ce fichier) ; désactivation : 0,0 dB.

Non vérifié : l'écoute ; le comportement sur la collection réelle ; la qualité du plafond sur de la musique réelle ; le temps de calcul sur une très longue piste (mesuré séparément, voir Preuves).

## Reprise et réexécution

Un morceau analysé avant cette étape n'a pas de sonie : **Analyze** la mesure sans toucher au tempo ni à la tonalité. Un changement de `LOUDNESS_ALGORITHM_VERSION` rend toutes les mesures à recalculer par Analyze. Le plan de lecture n'attend pas l'analyse : un morceau non mesuré joue à 0 dB.

## Interfaces et dépendances

`AudioAnalyzer.analyze(source, revision, *, tempo_range, tonality, loudness, expected_duration_us, is_cancelled, report_progress) -> AnalysisOutcome` (`outcome.loudness` est un `LoudnessResult` quand la mesure est demandée).

`AnalysisRepository.save_loudness(track_id, loudness, source_duration_us)`, `loudness_is_current(analysis, duration_us)`.

`PlayerService.set_normalization(settings: NormalizationSettings)`.

`PlayerBackend.set_gain_db(value: float)` ; `MpvBackend.gain_db() -> float` (lecture pour les contrôles).

`PlaybackSettingsModel` : propriétés `normalizationEnabled`, `normalizationLevel` ; slots `setNormalizationEnabled(bool)`, `setNormalizationLevel(str)` ; signal `changed`. Workspace : propriété `playbackSettings`, méthode `attach_playback_settings`.

## Preuves et livraison Git

Résultats des commandes, mesures et limites : section précédente et « Preuves » ci-dessous. Le commit ajoute explicitement le code, les tests, la migration et ce plan, sans les fichiers de `.local/` ni `vendor/` (ignorés).

Preuves (2026-10-14, environnement : Windows 11, Python 3.12.14 via `uv`, PySide6 6.9.3, libmpv et FFmpeg vendus dans `vendor/`) :

- Tests unitaires `uv run pytest tests/unit -q` : 3 échecs, tous présents au commit de base (`test_conversion_queue::test_advanced_settings_cycle_only_available_output_values`, `test_icon_provider::test_every_icon_renders_in_the_requested_colour`, `test_workspace_model::test_navigation_keeps_each_panel_selection_and_restores_it`). Les tests nouveaux passent.
- Tests d'intégration `uv run pytest tests/integration -q` : 4 échecs, tous présents au commit de base (`test_playback_repository::test_migration_from_17_keeps_data_and_creates_consistent_backup`, trois dans `test_playlist_exchange.py`, avec `'Context' object has no attribute 'report_items'`). Les tests nouveaux passent.
- Tests d'interface, un fichier à la fois (le dossier entier plante sur cette machine) : `test_playback_normalization_ui.py` et `test_column_selection.py`, `test_waveform_view_100.py`, `test_waveform_view_speed.py`, `test_fullscreen_waveform.py`, `test_track_list_wide_table.py`, `test_track_list_pointer.py`, `test_info_panel_staging.py`, `test_artist_profile_ui.py`, `test_file_move_drag.py`, `test_info_panel_messages.py`, `test_genre_manager_110_prototype.py`, `test_genre_manager_workflow.py`, `test_playlist_creation_98.py`, `test_track_hover.py`, `test_track_list_column_resize.py`, `test_track_list_drag_perf.py` : réussis. Les autres fichiers présentent des échecs ou des arrêts identiques à ceux du commit de base, relancés sur une copie de la base (`test_analysis_ui`, `test_player_views`, `test_incremental_scan_and_scroll`, `test_fullscreen_player_100` avec arrêt, `test_demo_navigation`, `test_playback_queue_ui`, `test_player_island_links` avec arrêt, `test_metadata_editor`, `test_browser_navigation`, `test_convert_view`, `test_playlists_ui`, `test_track_drag_98`).
- Arrêts natifs intermittents, hors de cette étape : l'exception Windows `0xe24c4a02` survient dans le thread d'événements de libmpv (`MpvBackend._event_loop`, appel à `mpv_wait_event`). Sur la copie de la base, `test_mpv_playback.py` plante 2 fois sur 5 et `test_application_smoke.py` 5 fois sur 8. Sur la branche, `test_mpv_playback.py` plante 2 fois sur 6 et `test_application_smoke.py` 7 fois sur 8 ; avec les deux écritures de bornes de gain désactivées (expérience, restaurée ensuite), 2 fois sur 4. Les échantillons sont trop petits pour attribuer la différence : le plantage existe au commit de base et tient à la fermeture du moteur natif, non corrigée ici. Suivi à ouvrir séparément.
- Mesure : `LoudnessMeter` sur flux stéréo bruité au taux d'analyse, dans un thread de travail : 1,74 s pour 5 min, 8,14 s pour 30 min (`.local/meter_timing.py`).
- Contrôle de formatage et de lint sur les fichiers touchés : `ruff format --check` propre ; `ruff check` propre sauf une ligne préexistante (`library_repository.py`, E501, à la requête `SELECT size_bytes,…` non modifiée).
- Exactitude face à une référence indépendante (`ffmpeg -af ebur128=peak=sample`, binaire vendu, hors application et hors tests) sur les deux fichiers de vérification à 44,1 kHz : MTEE −44,64 / −14,80 LUFS contre −44,6 / −14,8 ; pic −30,76 / −0,92 dBFS identique à ffmpeg. Au taux d'analyse (22 050 Hz) : −44,83 / −14,98 LUFS, pic −31,52 / −1,67 dBFS.
- Bout en bout `uv run python .local/e2e_116.py` (base neuve dans `.local/run-116`, schéma 25, scan réel, Analyze réel, lecture réelle avec sortie audio) : valeurs stockées conformes ci-dessus, fichiers inchangés (SHA-256 identiques), gains natifs relus +0,672 dB (`loud.wav`) et +30,519 dB (`quiet.wav`), égaux au calcul sur les valeurs stockées ; ordre d'appel `gain, load, gain, load` ; niveau Loud en cours de lecture et désactivation appliqués immédiatement.
- Exactitude du mesureur sur signaux synthétiques (tests) : voir « Validation et acceptation ».
- Ce qui n'a pas été fait : `scripts/build_windows.ps1` et `scripts/smoke_packaged.ps1` ne sont pas lancés (non demandés) ; aucune poussée, aucune fusion.

Note de révision — 2026-10-14, Claude : création de l'étape, implémentation, vérification sur le runtime réel ; écoute et recette réelle non réalisées.
