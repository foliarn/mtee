# Validation du plan 99 — contrôles de lecture, file et navigation

Date : 1er octobre 2026. Environnement : Windows, Python 3.12, PySide6, sources du dépôt. Aucune collection personnelle ni base locale n'a été ajoutée au dépôt. Les tests utilisent des fichiers WAV et des bases temporaires.

## Contrôles exécutés

- Maquette 99.0 validée par l'utilisateur avant le code fonctionnel (« Oui go »).
- 99.1 : 22 tests ciblés, Ruff, Pyright et contrôle depuis les sources.
- 99.2 : 18 tests ciblés de migration et de restauration sur copies ; deux runtimes reconstruits. Le smoke-test depuis les sources a quitté avec code zéro.
- 99.3 : 24 tests ciblés, dont le menu et la file dans un test Qt, Ruff et Pyright. Ces tests ont été effectués **avant** la demande ultérieure de l'utilisateur de ne plus lancer de tests UI.
- 99.4 : 36 tests domaine/service et deux tests UI effectués avant cette demande ; bornes de 3 secondes, pause, Repeat all et clics rapprochés couverts.
- 99.5 : test Qt avec backend factice effectué avant cette demande, couvrant Espace sur fond, bouton, file, Settings, Convert et recherche.
- 99.6–99.7 : tests unitaires ciblés du domaine, des modèles par groupe et de la désélection persistée ; aucun test UI ni examen de capture depuis la consigne de l'utilisateur.
- Passe hors UI finale : `uv run pytest tests/unit/test_navigation_history.py tests/unit/test_workspace_model.py::test_clear_selection_is_scoped_to_group_and_persisted tests/unit/test_workspace_model.py::test_same_tab_keeps_distinct_filtered_models_per_group tests/unit/test_workspace_model.py::test_page_history_replays_settings_and_forks_per_group tests/unit/test_player_service.py tests/unit/test_playback_queue_state.py tests/integration/test_playback_repository.py tests/integration/test_playback_session.py -q` : **56 réussis**.
- Contrôles statiques ciblés : `ruff check`, `ruff format --check` et `pyright` sur les six fichiers Python concernés : réussis ; `git diff --check` : réussi.
- Passe large `tests/unit tests/integration` hors `test_mpv_playback.py` : non réussie. Le premier échec isolé est `test_conversion_queue.py::test_queue_accepts_files_reviews_an_output_and_starts_on_explicit_second_action` (`hasPreview` faux avec la fixture locale) ; l'exécution complète a ensuite subi une violation d'accès Windows pendant des workers SQLite. `test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it` échoue toujours sur une attente synchrone de lignes asynchrones, déjà constatée avant 99. Les contrôles statiques globaux signalent aussi des diagnostics hors des fichiers de 99.

Aucune compilation EXE ni recette de paquet n'a été lancée, conformément au dépôt.

## Revue manuelle confiée à l'utilisateur

L'utilisateur a demandé de terminer l'implémentation sans tests UI ni inspection de captures par Codex et se charge lui-même de regarder l'interface. Les cas visuels et physiques de la matrice [ExecPlan 99](../../Plans%20d'exécution/99-controles-lecture-file-navigation.md) restent donc **à confirmer par l'utilisateur**. Vérifier en priorité :

1. Dans List puis Artwork, sélectionner plusieurs morceaux dans un ordre différent de l'ordre affiché ; `Add to queue` doit respecter l'ordre visible. Ajouter une playlist entière depuis la sidebar pendant qu'elle est filtrée puis déplacer et retirer une seule occurrence en Queue et en plein écran.
3. Fermer et rouvrir l'application avec une file, un doublon et une position non nulle : reprise en pause sans son avant Espace, puis lecture à la position conservée.
4. Appuyer sur Espace avec le focus sur fond, liste, bouton, Queue, Settings, Convert, plein écran et champs de saisie ; contrôler l'absence de double action. Maintenir la touche et passer le focus à une autre fenêtre.
5. Avec les boutons physiques arrière/avant de la souris, parcourir dossier, playlist, Settings/Analysis, Convert et activités latérales ; refaire le parcours avec deux groupes, recherche, scroll et sélection différents sur un même onglet.
6. Cliquer sous la dernière ligne, dans une liste vide, entre les tuiles, dans les zones vides de la sidebar et de l'éditeur. Seul le groupe visé doit perdre sa sélection ; Info doit être vide et la lecture inchangée. Vérifier aussi qu'un clic sur un contrôle conserve sa sélection.
7. Écouter les transitions `Previous` autour de 3 secondes, en lecture et en pause, ainsi que deux clics rapides et Repeat all à la première occurrence.

Les événements Qt simulés avant la consigne ne prouvent pas les boutons physiques ni l'écoute. Le diagnostic fatal Windows `0xe24c4a02` observé lors du contrôle natif `MpvBackend.close()` antérieur interdit de présenter le backend natif comme validé. La passe UI groupée antérieure a aussi montré une violation d'accès intermittente pendant un worker SQLite ; le test de file repassait isolément. Ces points restent à vérifier pendant la recette humaine.
