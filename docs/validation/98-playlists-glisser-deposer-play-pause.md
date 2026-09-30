# Validation du plan 98 — 2026-10-01

## Périmètre et environnement

Maquette révisée validée explicitement par l'utilisateur (« Oui ») avant l'implémentation. Contrôles depuis les sources sous Windows, Python 3.12, PySide6/QML, avec la fixture synthétique créée par `scripts/create_playlists_98_fixture.py` dans `.local/validation/98/manual-01`. Aucun paquet Windows n'a été construit. Les données de validation restent hors Git.

La fixture contient six WAV de 18 secondes, deux pochettes, plusieurs dossiers, trois playlists et une référence de morceau absent. Sa recréation dans `manual-02` a produit six empreintes SHA256 identiques à `manual-01` après les contrôles. Une seconde exécution sur `manual-01` a refusé le dossier non vide, comme prévu.

## Vérifications effectuées

| Contrôle | Résultat observé |
|---|---|
| Tests ciblés repository, service, création, UI playlists, survol, colonnes, ordre pur, drag List/Artwork, démo | 45 réussis (`rtk proxy uv run pytest … -q`). Les tests de drag envoient de vrais événements souris Qt, observent l'aperçu pendant le geste et vérifient l'ordre persistant. |
| Fenêtre native Windows (`QT_QPA_PLATFORM=windows`) | Les tests de création, playlist et drag passent. Les captures `playlist.png` et `playlist-paused.png` dans `.local/validation/98/captures/` ont été inspectées : icône à gauche de la pochette, Play/Shuffle sous la grande pochette et alignés avec Search/List/Artwork. Le test de survol passe seul ; un passage groupé a eu une intermittence de position du pointeur. |
| Chargement depuis les sources | `uv run python -m mtee --data-dir .local/validation/98/manual-01 --smoke-test` : code 0. |
| Lecture libmpv réelle sur WAV de fixture | Position environ 1,05 s en lecture, 1,18 s en pause puis 1,75 s après reprise ; file de cinq entrées inchangée, `backend_error` vide. Le script ponctuel a toutefois quitté avec le code 1 après son affichage final ; ce contrôle n'est donc pas considéré comme une recette libmpv entièrement réussie. |
| Qualité statique | Ruff ciblé sur les fichiers Python modifiés : réussi. `git diff --check` : réussi. Pyright global : 34 erreurs, aucune dans les fichiers Python modifiés du plan 98. Ruff global : 36 erreurs dans 13 fichiers, hors du contrôle ciblé. |
| Tests supplémentaires | `tests/ui/test_player_views.py::test_space_goes_to_search_while_a_track_is_playing` et `tests/unit/test_workspace_model.py::test_navigation_keeps_each_panel_selection_and_restores_it` échouent : leurs vues de dossier sont vides au point d'assertion. L'origine n'est pas établie ; les deux tests ne sont pas déclarés validés. |

## Cas d'acceptation

`Automatisé` signifie un test dédié de comportement, parfois avec backend de lecture factice. `Partiel` indique que le parcours complet en fenêtre native n'a pas été reproduit. Aucun cas marqué partiel n'est assimilé à une recette utilisateur complète.

| Cas | État et preuve |
|---|---|
| A01 | Automatisé : menu compact sans import interrompu dans les tests UI. |
| A02 | Partiel : entrée Resume et hauteur conditionnelle vérifiées dans la source et la maquette ; parcours d'import interrompu réel non joué. |
| A03 | Automatisé : création sans dialogue, nom 01 et ouverture dans les tests UI. |
| A04 | Automatisé : décompte transactionnel, dossiers et playlists nommées dans les tests repository. |
| A05 | Automatisé : suppression, homonymie et UUID distincts dans les tests repository. |
| A06 | Partiel : décompte en base et exclusion de Liked tracks vérifiés ; séquence complète renommer/déplacer/redémarrer non rejouée. |
| A07 | Automatisé : créations successives via file de jobs dans les tests de création. |
| A08 | Partiel : création depuis le menu d'ajout et ajout de sélection vérifiés en UI ; toutes les variantes de menu ne sont pas rejouées séparément. |
| A09 | Partiel : contexte d'ambiguïté et suppression compensatrice vérifiés en code et tests ciblés ; injection d'erreur et reprise complète non rejouées. |
| A10 | Automatisé : titre activable, renommage et persistance dans le test UI playlist. |
| A11 | Partiel : voile de survol et sélecteur QML inspectés ; annulation native d'une image et mosaïque non rejouées ensemble. |
| A12 | Automatisé et capture native : état Play/Pause, emplacement réservé et coordonnées de ligne testés. |
| A13 | Partiel : composant partagé par dossiers, playlists et likes ; matrice complète filtres/panneaux/pochettes masquées non jouée. |
| A14 | Partiel : file et position observées avec libmpv réel, mais sortie du script de contrôle à code 1. |
| A15 | Automatisé pour List et cible sidebar ; Artwork testé comme source de réordonnancement. Traversée Artwork vers sidebar non vérifiée directement. |
| A16 | Automatisé : lot de deux en ordre de clic inverse, aperçu du premier visible ; lot de trois non testé directement. |
| A17 | Partiel : insertion List, insertion Artwork après dernier et persistance testées ; toutes les frontières de rangée ne le sont pas. |
| A18 | Automatisé pour la permutation pure d'un lot non contigu ; la branche sans écriture sur ordre identique est vérifiée dans le code, sans assertion de base dédiée. |
| A19 | Automatisé pour vue triée ; autres cibles incompatibles contrôlées en source et par leurs conditions de drop. |
| A20 | Automatisé pour Échap ; perte d'activation, sortie de fenêtre et fermeture d'onglet non rejouées directement. |
| A21 | Partiel : version initiale transmise et refus de version périmée dans le modèle ; suppression concurrente pendant un geste non rejouée. |
| A22 | Partiel : objet aperçu hors delegate et minuterie de défilement vérifiés en source ; liste longue et source hors champ non jouées. |
| A23 | Partiel : référence absente présente dans la fixture ; combinaison réordonnancement puis ajout incompatible non rejouée. |
| A24 | Partiel : rechargement des ordres dans les tests repository/UI ; relance native complète sur le même data-dir non effectuée. |

## Limites de la livraison

Les cas partiels ci-dessus nécessitent encore une recette interactive complète, particulièrement les imports interrompus, les états concurrents et les longues listes. Les deux tests de navigation et recherche en échec demandent un diagnostic distinct avant de déclarer toute la suite verte. Le plan 99 et la file d'attente n'ont pas été modifiés.
