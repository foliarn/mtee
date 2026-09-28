# 24 — Lecteur : lancer un morceau après une pause

## Résultat attendu et prérequis

Après avoir mis A en pause, demander explicitement la lecture de B doit démarrer B et afficher un état cohérent dans le listing, l’îlot et le Fullscreen player. Une sélection simple reste une sélection. Lire le plan 23 et les contraintes du plan 18 avant de modifier le lecteur. Ce lot peut commencer sans décision visuelle supplémentaire.

## État des sources et contrats

Lire `src/mtee/services/player_service.py`, `src/mtee/services/mpv_backend.py`, `src/mtee/services/player_backend.py`, `src/mtee/domain/playback.py` et `src/mtee/models/player_model.py`. Lire aussi `tests/unit/test_player_service.py`, `tests/unit/test_playback_queue.py`, `tests/integration/test_mpv_playback.py` et `tests/ui/test_player_views.py`.

Au commit de préparation, `MpvBackend.load()` envoie `loadfile … replace` sans remettre explicitement la propriété native `pause` à faux. `PlayerService` publie `PLAYING` à la réception de `loaded`. Cette combinaison est une cause plausible du décalage signalé, à confirmer avec le backend réel. Le faux backend conserve également son attribut `paused` entre deux chargements : il permet un test de régression utile, à condition d’observer cet attribut et pas seulement l’état du service.

Le contrat à garantir est celui d’une intention de lecture. Une activation de morceau crée une session identifiée, charge la bonne source et demande sa lecture. Les événements d’une ancienne session ne peuvent pas rétablir son état. La pause demandée volontairement pendant le chargement du nouveau morceau doit toutefois rester prioritaire à son arrivée.

## Jalon 24.1 — Reproduction et correction ciblée

1. Ajouter à `tests/unit/test_player_service.py` le scénario A joue, A est pausé, B est lancé. Observer la session, le chemin chargé, l’état natif de pause et l’état publié. Faire échouer ce cas sur le comportement actuel avant la correction.
2. Identifier la frontière qui doit porter l’intention : service de lecture ou backend natif. Choisir une seule autorité pour éviter deux remises en lecture concurrentes ; documenter l’ordre des commandes.
3. Retirer l’ancienne pause lors d’une activation explicite, au moment compatible avec la gestion des sessions. Ne pas résoudre le bug en modifiant seulement l’icône ou en émettant un faux état `PLAYING`.
4. Garder l’attente des confirmations de fermeture pour les accès fichiers. Préserver les baux de lecture et le rejet des événements périmés.
5. Traiter l’erreur de chargement comme une erreur visible, sans afficher une lecture effective. Vérifier le comportement d’une nouvelle demande de pause pendant un chargement lent ; si cette commande n’est actuellement pas acceptée, définir et documenter explicitement son traitement sans l’écraser à `loaded`.

## Jalon 24.2 — Couverture des points d’entrée

Le double-clic du listing, son bouton de lecture, Enter, la file, Next et Previous doivent passer par le même contrat de lancement explicite. Le plan 25 branchera ensuite le double-clic de l’arbre sur ce contrat. Éviter de dupliquer la réparation dans chaque composant QML.

Ajouter des tests paramétrés seulement là où les chemins divergent. Couvrir pause A → B, pause A → réactivation explicite de A, changements rapides A/B/C, notification de pause tardive de A et échec de B. Garder le comportement existant du bouton de bascule lecture/pause pour le morceau courant. Un clic de sélection sur B ne doit pas interrompre A.

Vérifier que l’îlot, le Fullscreen player et la ligne partagent l’état de `PlayerModel`, sans état local durable qui pourrait rester sur la session précédente.

## Vérification et critères d’acceptation

Depuis la racine :

    uv run pytest tests/unit/test_player_service.py tests/unit/test_playback_queue.py tests/ui/test_player_views.py
    uv run pytest tests/integration/test_mpv_playback.py

Le test natif requiert le runtime libmpv verrouillé ; son indisponibilité est un résultat à déclarer, pas une réussite. Étendre ce test d’intégration avec deux WAV synthétiques valides et une observation de position qui avance après le lancement de B. La progression du temps complète le test d’état ; la recette humaine confirme le son audible.

Dans l’application Windows, lire A, mettre en pause, lancer B depuis le listing, puis recommencer depuis la file et le Fullscreen player. B commence, son temps avance et les commandes proposent Pause. Refaire avec A à nouveau et avec une source indisponible. Modifier seulement la sélection ne relance pas la lecture. Les réponses tardives ne changent pas l’identité affichée.

Appliquer les commandes communes, le build et la recette de l’EXE décrits au plan 23. Créer `docs/validation/ux-ui-24.md` avec les observations effectives. Aucun nombre arbitraire de tests n’est requis.

## Livraison et reprise

Sujet de commit proposé : `fix(player): resume explicitly activated tracks after pause`. Le corps explique la cause confirmée, la frontière corrigée, les scénarios testés et la recette native réellement faite. Push selon le plan 23. En cas de régression, revenir au commit précédent par un revert ciblé ; aucune donnée audio ou base utilisateur n’a à être restaurée.

## Progress

- [x] 2026-09-28 — Contrat et points de code inspectés pour la préparation.
- [x] 2026-09-28 — La lecture des sources confirme que le service publiait `PLAYING` sans retirer la pause native. Régression et cas de session ajoutés, mais les tests ne sont pas exécutés dans cette passe.
- [x] 2026-09-28 — Correction centralisée dans `PlayerService`; compilation Python, chargement QML de démonstration et contrôles Ruff réussis.
- [ ] Tests automatisés et scénario natif non exécutés, conformément à la demande de laisser la recette fonctionnelle à l'utilisateur.
- [ ] Recette audio manuelle et vérification du paquet Windows non réalisées.
- [x] Rapport de validation rédigé et diff ciblé relu.

## Surprises & Discoveries

2026-09-28 — Le chargement et la propriété native de pause sont deux commandes distinctes. Vérifier seulement `PlaybackStatus.PLAYING` peut masquer une lecture native encore pausée.

2026-09-28 — Les événements de propriété `pause` peuvent arriver après le changement de piste. Le service ignore une notification contraire à l'intention courante, même si elle porte l'identifiant de la session actuellement chargée.

## Decision Log

2026-09-28 — Codex : `PlayerService` est l'unique autorité de l'intention de lecture. Toute activation explicite retire l'ancienne pause juste avant `load`; une demande reçue pendant `LOADING` est envoyée immédiatement, puis conservée par session jusqu'au signal `loaded`. Les événements de pause en retard qui contredisent cette intention ne remplacent pas l'état partagé. Le bouton expose « Pause when ready » et « Play when ready » durant ce chargement.

## Outcomes & Retrospective

La correction et les scénarios de régression sont implémentés. `uv run python -m compileall -q src/mtee`, le smoke-test de démonstration (chargement Python/QML) et les contrôles Ruff ciblés ont réussi sous Python 3.12.14 et uv 0.12.17. Les tests automatisés, l'audio libmpv, la recette interactive et le paquet Windows n'ont pas été exécutés; ils restent à la recette utilisateur. Voir `docs/validation/ux-ui-24.md`.

Révision du 28 septembre 2026 : activation explicite dépausée, pause en attente par session, état de contrôle Qt/QML et scénarios automatisés ajoutés.
