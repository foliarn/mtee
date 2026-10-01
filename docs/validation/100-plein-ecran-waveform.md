# Validation — Fullscreen player et waveform (plan 100)

Rapport du 1er octobre 2026 pour le plan [100-plein-ecran-waveform](../../Plans%20d'exécution/100-plein-ecran-waveform.md). Il distingue ce qui a été **exécuté**, ce qui est **vérifié par un test automatisé** et ce qui **n'a pas pu être observé** : aucune session interactive avec souris, pavé tactile ou écoute n'a eu lieu pendant cette exécution.

## Environnement

Windows 11 Pro 10.0.26200, Python 3.12.14, PySide6 6.9.3, NumPy 2.5.3, `uv` avec l'environnement verrouillé du dépôt, FFmpeg et libmpv du dossier `vendor/` (runtime embarqué du projet). Les tests Qt tournent avec la plateforme hors écran (rendu logiciel). Aucun build `dist/MTEE.exe` n'a été fait ni lancé : la livraison est vérifiée depuis les sources seulement.

Livraisons, dans l'ordre (`git log --oneline 905cd3f..HEAD`) : `a9c47cd` maquette 100.0, `6160ddd` hauteur de carte, `60e30fe` 100.1, `f51574a` 100.2, `119c04d` 100.3, `d4cd5c9` 100.4, `04b2656` 100.5, `3a25d13` 100.6. Chaque lot a été appliqué sur une copie propre du dépôt (worktree temporaire) avant son commit, pour séparer ses résultats du travail extérieur non commité de l'arbre principal (voir plus bas).

## Commandes exécutées

Depuis la racine du dépôt. Toutes ont réussi (code de sortie 0) dans l'arbre principal à la fin du jalon 100.6 et après ajout des tests de 100.7.

    uv run pytest tests/ui/test_fullscreen_waveform.py tests/ui/test_player_views.py tests/unit/test_waveform_points.py tests/integration/test_analysis_repository.py
    uv run pytest tests/unit/test_waveform_points.py tests/unit/test_waveform_levels.py tests/unit/test_scrub_session.py tests/unit/test_player_service.py tests/integration/test_analysis_repository.py tests/ui/test_waveform_view_100.py tests/ui/test_fullscreen_waveform.py
    uv run pytest tests/unit/test_cover_palette.py tests/unit/test_cover_accent_model.py tests/ui/test_fullscreen_player_100.py tests/ui/test_player_views.py tests/ui/test_demo_navigation.py tests/unit/test_playback_queue_groups.py
    uv run pytest tests/integration/test_analysis_pipeline.py tests/integration/test_waveform_model.py tests/ui/test_waveform_view_speed.py
    uv run python -m mtee --demo --smoke-test

La commande du plan qui contient `tests/unit/test_workspace_model.py` n'a pas été retenue telle quelle : ce fichier échoue déjà sur le HEAD de départ (`905cd3f`).

### Balayage complet comparé au HEAD de départ

Chaque fichier de `tests/unit`, `tests/integration` et `tests/ui` a été lancé séparément, sur un worktree propre à `905cd3f` (avant le plan 100) puis sur l'arbre principal.

- Échecs présents dès `905cd3f` : `test_browser_navigation`, `test_convert_view`, `test_incremental_scan_and_scroll`, `test_metadata_editor`, `test_conversion_queue::test_advanced_settings_cycle_only_available_output_values`, `test_icon_provider::test_every_icon_renders_in_the_requested_colour`, `test_workspace_model::test_navigation_keeps_each_panel_selection_and_restores_it`.
- Échecs supplémentaires dans l'arbre principal seulement : `test_conversion_ffmpeg` (quatre cas), `test_conversion_queue::test_queue_accepts_files_reviews_an_output_and_starts_on_explicit_second_action`, `test_playlists_ui`, `test_track_drag_98`, `test_empty_selection`. Sur un worktree à `3a25d13` (tous mes commits, sans le travail extérieur non commité), `test_conversion_ffmpeg`, `test_playlists_ui` et `test_track_drag_98` passent, et la seconde assertion de `test_conversion_queue` aussi ; `test_empty_selection` n'y existe pas (fichier extérieur non suivi). Ces échecs viennent donc du travail extérieur non commité de l'arbre principal, pas des commits du plan ; la cause exacte de `test_conversion_ffmpeg` (état de `Cover art` du rapport de métadonnées) n'a pas été recherchée.
- Aucun test qui passait à `905cd3f` n'échoue à cause des commits du plan.

### Contrôles de code

`uv run ruff check src tests scripts` : 27 erreurs, le même nombre qu'à `905cd3f`, toutes préexistantes (lignes longues et imports de modules étrangers au plan). `ruff format --check` : aucun des fichiers à reformater n'est un fichier du plan, hors lignes de `demo_workspace.py` et `workspace_model.py` qui appartiennent au travail extérieur. `pyright` sur les fichiers créés ou modifiés par le plan : sans erreur, à l'exception de motifs de typage de PySide déjà présents dans `tests/integration/test_waveform_model.py` (`Property` utilisé comme valeur). Le décompte global de `pyright` (50 erreurs) n'a pas pu être comparé au HEAD de départ : le worktree de comparaison ne résout pas les imports de la même façon.

## Mesures

| Mesure | Résultat | Conditions |
|---|---|---|
| Repeinte du Canvas de la waveform à 1440 px (repeinte et capture) | médiane 2,4 à 2,7 ms | `test_a_repaint_at_full_width_is_fast`, rendu logiciel hors écran ; seuil du plan 8 ms |
| `bar_levels()` sur 1200 points | 0,26 ms (240 barres), 0,42 ms (480), 0,80 ms (1000) | un essai de 100 appels, thread principal |
| Latence du seek libmpv (reprise de la chaîne audio) | WAV médiane 1,5 ms (p95 1,8), FLAC 1,7 ms (p95 1,9), MP3 1,7 ms (p95 1,9) | `scripts/measure_seek_latency.py`, `ao=null`, bruit rose de 120 s, 30 seeks par format, sonde à 1 ms ; exclut le tampon d'un vrai périphérique |
| Première peinture de la vue de waveform | sous la seconde (budget du test) | `test_the_first_paint_of_a_full_waveform_is_immediate` |

La latence de G7 est donc mesurée sur le moteur, pas jusqu'au haut-parleur.

## Matrice de recette

Légende : **Auto** = vérifié par test automatisé ; **Partiel** = une partie seulement l'est ; **Non observé** = demande une session interactive ou l'écoute.

| Cas | Statut | Preuve et limite |
|---|---|---|
| FS-01 | Partiel | Auto : plein écran affiché, île visible avec l'icône `exit-fullscreen`, panneau droit masqué, aucun éditeur de tags, une seule icône de sortie (`test_the_island_stays_with_an_exit_icon_and_there_is_no_tag_editor`). Non asserté : barre d'activités visible et sidebar masquée (code inchangé). |
| FS-02 | Auto | `test_the_exit_icon_and_an_activity_leave_fullscreen` (règle du modèle `setActivity`). Clic réel sur une icône de la barre d'activités : non observé. |
| FS-03 | Auto | `test_without_a_track_fullscreen_only_says_to_play_one`, `test_without_a_track_pages_do_not_exist` (molette, touche, `setFullscreenPage` sans effet). |
| FS-04 | Auto | `test_the_source_name_opens_the_source_without_playing`, `test_the_source_name_opens_the_playing_folder`. |
| FS-05 | Partiel | Auto : palette (vive, pâle assombrie au contraste 4,5:1, grise sans accent, `dark` plus sombre), modèle d'accent (hors thread, cache, résultat périmé ignoré, accent précédent conservé pendant le calcul). Non observé : le fondu d'environ 1 s (`fsAccentFade`), l'ombre du repli et le rendu du dégradé dans la fenêtre réelle. |
| FS-06 | Partiel | Auto : le marquee défile quand le texte déborde et reste immobile sinon ; genre vide masqué ; `Unknown artist`. Non observé : l'aller-retour avec pauses à l'œil. |
| FS-07 | Partiel | Auto : pochette masquée à 880 px, carte conservée. Non asserté : absence de chevauchement des icônes. |
| FS-08 | Partiel | Auto : le cœur bascule le like de la piste jouée, l'icône Play suit l'état du lecteur, le menu `…` a les six entrées dans l'ordre et cible la piste jouée. Non asserté : l'icône `check` de `+` pour une piste déjà dans une playlist. |
| FS-09 | Auto | `test_edit_info_in_the_real_workspace_replaces_the_selection_in_the_source` (workspace réel, autre piste sélectionnée, Info ouvert, lecture intacte). |
| WF-01 | Partiel | Auto : hauteurs normalisées par piste et deux sections à −3 dB d'au moins 20 % d'écart. Observation à l'œil sur une vraie piste à drops : captures de la maquette seulement. |
| WF-02 | Auto | Couleurs des trois lignes du tableau, temps du haut au survol et hors survol, aucun seek au survol. |
| WF-03 | Auto | `test_scrubbing_through_the_model_seeks_plays_and_never_ends_the_track` : clic en pause, saut et lecture. |
| WF-04 | Partiel | Auto : maintien immobile sans seek supplémentaire (domaine et modèle). Non observé : la coloration qui reste sous la souris pendant 3 s. |
| WF-05 | Partiel | Auto : coupure unique au mouvement rapide, reprise au ralentissement, silence sans publication de `muted` ni de `volume` (service). Non observé : l'écoute, et donc le réglage des seuils (100.3). |
| WF-06 | Auto | `test_leaving_by_the_left_holds_the_start`. |
| WF-07 | Auto | Sortie à droite puis relâchement dehors : morceau suivant ; retour avant relâchement : rien (domaine) ; via `PlayerModel` : silence puis morceau suivant. |
| WF-08 | Auto | Piste non seekable (ni survol ni scrub), génération (barres plates et pourcentage), indisponible (message et Retry), erreur de lecture (message, Retry et Next dans la carte, reste de la carte intact). |
| WF-09 | Partiel | Auto : `pending()` retient une piste dont seule la waveform est périmée, son traitement n'écrit ni tags, ni BPM, ni tonalité, corrections manuelles et fichier intacts (empreinte SHA-256), `Re-analyze` refait tout (`test_analysis_pipeline.py`, WAV synthétiques). Non fait : une analyse générale lancée depuis l'application sur une collection de recette. |
| PG-01 | Partiel | Auto : une encoche de molette, pavé tactile au seuil, `PgDown`/`PgUp`/`Down`/`Up`, flèches, bouton Queue de l'île ; au repos les couches sont exactement sur l'une des deux cibles. Non observé : l'animation de 350 ms à l'œil, le pavé tactile réel. |
| PG-02 | Auto | `test_the_wheel_over_the_list_never_changes_the_page` (butée haute et butée basse). |
| PG-03 | Auto | `test_the_visible_bottom_of_the_card_is_not_clickable_on_page_two`. |
| PG-04 | Auto | Changement de piste en page 2 : reste en page 2 ; redimensionnements ; réouverture en page 1. |
| Q-01 | Auto | Sections `Next in queue` et `Next from: <source>` (rôle `queueGroup`), titre courant en `Theme.primary`. |
| Q-02 | Auto | Voile Play au survol (structure), clic sur la pochette de l'occurrence d'un doublon : la bonne occurrence est jouée. |
| Q-03 | Auto | `Remove from queue` retire la seule occurrence et n'existe pas sur la ligne courante ; `Go to folder` ; `Edit info` sélectionne la piste et ouvre Info. |
| Q-04 | Partiel | Auto : un seul `moveQueueEntry` au relâchement, Échap annule. Non asserté : le même ordre dans le panneau Queue de 99 et au `Next` suivant (même modèle de service, non comparé visuellement). |
| TD-01 | Partiel | Auto : douze champs, nom du dossier sans chemin, `—` pour les valeurs absentes. Piste « complète » : seulement les données de la démo et de fichiers WAV synthétiques. |

## Limites et écarts à connaître

- Les valeurs de la maquette sont celles que l'utilisateur a laissées passer avec « parfait continue », hauteur de carte +60 px comprise. Les seuils du scrub (100 ms, 2000 px/s, 80 ms, 60 ms) n'ont **pas** été ajustés à l'écoute.
- Aucune analyse générale n'a été lancée sur une collection réelle : ni les waveforms de l'utilisateur ni leur recalcul en v2 n'ont été observés.
- La pochette arrondie utilise `MultiEffect`, qui ne s'affiche pas avec le rendu logiciel hors écran : à vérifier dans la fenêtre native.
- Le `+` de la carte et celui de l'île ne fonctionnent pas pour une piste absente de l'onglet quand une playlist est ouverte (comportement existant de `localTrackIds`).
- Les douze champs de Track details sont conservés sans validation explicite de la liste.
- Le panneau Queue du plan 99 n'a pas de sections.
- Retour arrière : le `load_waveform` de `905cd3f` compare d'abord la version de la ligne (1 attendu, 2 stocké) et renvoie `None` sans lire le BLOB de 6 octets par point ; la waveform serait recalculée, sans migration à défaire. Lecture du code seulement, non exécutée.
- Aucun build, aucune vérification du paquet Windows.
