# 28 — Waveforms monochromes : densité et repère temporel

## Résultat attendu et décision utilisateur

Rendre les changements de passages plus faciles à discerner, afficher un repère temporel avec la tête de lecture et assombrir la portion déjà lue.

Décision explicite du 29 septembre 2026 : l’utilisateur garde uniquement la variante monochrome montrée dans les captures ; les trois bandes ne répondent pas au besoin. La comparaison et l’implémentation 3 bandes/RGB sont closes. Aucun sélecteur de couleur n’est ajouté.

Lire les plans 23, 19 et 22, puis `docs/ux/specification.md`. La waveform demeure une vue monochrome complète et cliquable. Le zoom temporel, le déplacement horizontal, la boucle A/B, l’édition, les cues, les beatgrids et l’analyse musicale restent hors périmètre.

## Sources et constats à vérifier

Lire `src/mtee/qml/components/WaveformView.qml`, `WaveformPreview.qml`, `src/mtee/qml/views/FullscreenPlayer.qml`, `src/mtee/models/waveform_model.py`, `src/mtee/services/waveform_service.py`, `waveform_cache.py` et `src/mtee/domain/waveform.py`. Lire `tests/unit/test_waveform_reduction.py`, `test_waveform_timing.py`, `tests/integration/test_waveform_cache.py` et `tests/ui/test_fullscreen_waveform.py`.

`WaveformView.qml` dessine chaque min/max comme un trait de hauteur presque totale, dans une couleur uniforme. Le curseur repeint actuellement l’ensemble du Canvas. `_display_samples()` sélectionne un niveau de pyramide d’au plus 1 200 points et prend les extrema des canaux. Le cache conserve des extrema d’amplitude ; il ne contient ni énergie par bande ni RMS. La capture Notion montre de longues plages presque pleines. Elle ne permet pas de conclure que le signal audio est réellement écrêté.

Le code ne fournit aucun corpus utilisateur ni mesure de performance. Le développement reste donc prudent : regrouper les extrema déjà sélectionnés dans un budget de pixels, conserver leur minimum et maximum, et séparer la couche dynamique du curseur. Ne pas annoncer de gain mesuré.

## Jalon 28.1 — Diagnostic borné et densité adaptée

Réutiliser la pyramide min/max et le cache existants. Adapter uniquement la réduction de présentation à la largeur du Canvas. Chaque regroupement reprend le minimum et le maximum de tous les points couverts afin de préserver les crêtes courtes déjà conservées par le niveau fourni.

Ne pas ajouter de RMS ou de nouveau calcul audio : les extrema seuls ne le permettent pas honnêtement. Ne pas transformer les captures synthétiques de revue en mesure du rendu audio réel. La validation de lisibilité sur une collection appartient à la recette utilisateur.

Documenter les limites de l’observation dans `docs/validation/ux-ui-28.md` ; aucune mesure de performance ni amélioration constatée ne sera annoncée sans recette.

## Jalon 28.2 — Choix visuel déjà validé

Les captures comparatives historiques restent dans `docs/ux/review-ux-ui-2026-09.md` pour conserver le contexte de la décision. L’utilisateur a retenu le monochrome ; il n’est pas nécessaire de représenter de nouveau les variantes rejetées dans l’application ni de solliciter une autre approbation.

La rangée waveform garde une seule couleur de données. Le curseur utilise un neutre de contraste constant ; la partie lue est assombrie par transparence pour que ses variations restent visibles. La capture reste historique, pas une preuve de performance.

## Jalon 28.3 — Implémenter seulement le rendu retenu

Implémenter uniquement le rendu monochrome sur le cache actuel. Ne pas modifier `WaveformData`, la version du cache, le décodage local ni les modèles de données ; aucune dépendance audio supplémentaire n’est justifiée pour cette amélioration de présentation.

Le regroupement de présentation utilise seulement les extrema reçus. Ne pas supprimer des points au hasard, ajouter de faux creux, appliquer un gain par segment ou masquer les vraies crêtes. Aucun calcul RMS ni de bandes de fréquence n’est ajouté.

## Jalon 28.4 — Curseur, temps et portion lue

Utiliser la position et la durée rapportée par le moteur du lecteur comme référence temporelle. Tant qu’une durée valide manque, garder le contrôle de seek simple ; ne pas inventer une durée depuis le tag. La conversion en microsecondes reste à la frontière du modèle. La tête est bornée dans la vue complète et se déplace correctement après un seek, un redémarrage et un changement de morceau. La durée publique historique du lecteur conserve son repli sur les métadonnées ; la waveform lit une propriété distincte sans repli.

Séparer le dessin des données de la couche légère du curseur/assombrissement. La progression ne recalcule pas la réduction ni ne repeint les points à chaque tick. Un changement de largeur, de données ou de thème déclenche le dessin nécessaire. Garder les Canvas existants ; aucune infrastructure plus complexe n’est justifiée.

Dessiner le trait de lecture avec un contraste constant, un petit repère si utile et un libellé temporel `m:ss` ou `h:mm:ss`. Conserver le trait au bon x ; déplacer seulement l’étiquette lorsqu’elle approche d’un bord. Une règle temporelle discrète peut utiliser des graduations adaptées à la largeur si la maquette la retient. Ne pas superposer plusieurs indications inutiles au même endroit.

À gauche du trait, assombrir les mêmes données sans faire disparaître leurs variations. À droite, garder la luminance nominale. La limite suit exactement le curseur, y compris à 0 et à la fin ; une pause conserve le partage. Les couleurs ne sont pas le seul repère de position. Le clic sur la waveform reste disponible dans les deux zones et demande la même position qu’avant.

Quand un nouveau morceau charge, retirer les données du précédent. Les états Preparing, erreur, source absente et cache invalide restent lisibles. Une erreur d’écriture cache ne doit pas empêcher d’utiliser les données mémoire valides. La navigation et la lecture continuent pendant la génération.

## Vérifications et commandes

Étendre les tests existants. Ajouter des fixtures déterministes non vides au test UI : le test de démo actuel avec `samples == []` prouve le chargement de la vue, pas sa lisibilité. Si des bandes sont retenues, créer au jalon 28.3 `tests/unit/test_waveform_bands.py`, avec sinusoïdes aux bandes choisies, silence, changements de bande, canaux asymétriques et transitions aux limites de blocs. Si une RMS est retenue, tester son calcul avec des signaux d’énergie connue.

Depuis la racine :

    uv run pytest tests/unit/test_waveform_reduction.py tests/unit/test_waveform_timing.py tests/integration/test_waveform_cache.py tests/ui/test_fullscreen_waveform.py

Exécuter le nouveau test de bandes uniquement s’il a été créé pour la variante choisie. Vérifier conservation des impulsions, bornes temporelles, ancien/nouveau cache, changement rapide de source et annulation. Les tests QML observent des données non vides, les coordonnées du repère et les deux zones ; les captures servent à examiner la lisibilité réelle.

Recette : source courte et longue, cache froid et chaud, fenêtre large et étroite, échelles Windows 100 % et 150 %, pause/seek/changement rapide. Le son ne se coupe pas pendant le calcul ; le curseur suit la position ; aucun ancien résultat ne revient sur le nouveau morceau. Mesurer temps de génération, mémoire et réactivité de navigation sur la même machine avant/après. Rapporter les valeurs et leur contexte, sans inventer une cible de performance issue de `PLAN.md`.

Créer `docs/validation/ux-ui-28.md`, puis appliquer la clôture Windows et Git du plan 23. Mettre à jour les attentes des anciens tests « monochrome » uniquement après validation du nouveau rendu ; conserver les protections qui interdisent le retour du zoom/A-B hors périmètre.

## Livraison et reprise

Premier livrable : dossier de comparaison et maquettes, avec statut « choix attendu ». Deuxième : rendu choisi et contrats de données nécessaires. Troisième : marqueur, partie lue, recette et distribution. Sujet final proposé : `feat(waveform): improve readability and playback position cues`, adapté au rendu réellement retenu.

Le rollback utilise le commit précédent et l’invalidation contrôlée des seuls caches dérivés concernés. Ne pas supprimer le catalogue ni les corrections utilisateur. Une reprise commence par lire la décision de variante ; elle ne relance pas une comparaison déjà validée.

## Progress

- [x] 2026-09-28 — Capture, sources et comparaison statique préparées ; le signal reste synthétique.
- [x] 2026-09-29 — L’utilisateur retient explicitement le monochrome et rejette les trois bandes ; décision inscrite ici et dans la spécification.
- [x] 2026-09-29 — Contrat min/max conservé ; regroupement de présentation adapté à la largeur et couche de curseur séparée implémentés.
- [x] 2026-09-29 — Repère temporel borné, temps `m:ss`/`h:mm:ss` et assombrissement de la partie lue implémentés.
- [x] 2026-09-29 — Compilation Python, Ruff, lint QML et contrôle de diff réussis ; aucune erreur QML.
- [x] 2026-09-29 — Reconstruction Windows réussie ; QML, notice FFmpeg, libmpv et empreintes FFmpeg vérifiés dans le paquet autonome.
- [x] 2026-09-29 — Tests automatisés et lancement manuel non effectués selon la demande ; recette audio laissée à l’utilisateur, aucune mesure de performance revendiquée.
- [x] 2026-09-29 — Rapport `docs/validation/ux-ui-28.md` rédigé avec les résultats observés et les limites de validation.
- [x] 2026-09-29 — Code du jalon livré par `e907053` (`feat(waveform): improve monochrome density and playback cues`) et poussé sur `origin/main`.

## Surprises & Discoveries

2026-09-28 — La réduction actuelle préserve les extrema et les canaux, mais elle peut donner une silhouette très pleine à l’échelle d’un morceau entier. Son cache ne peut fournir une coloration fréquentielle authentique à lui seul. Le plan doit distinguer dessin QML et calcul des données de visualisation.

## Decision Log

2026-09-28 — Utilisateur : comparer monochrome, 3 bandes et RGB dans des maquettes avant de choisir. Codex : commencer par un diagnostic de densité, garder la vue complète et ne développer que la variante choisie. Aucun accord n’est enregistré pour un zoom temporel ou un sélecteur de trois modes.

2026-09-29 — Utilisateur : « garde uniquement le monochrome » ; les trois bandes ne répondent pas au besoin. Pas de comparaison supplémentaire, de calcul fréquentiel ou de sélecteur permanent.

2026-09-29 — Implémentation : conserver les extrema et le cache ; réduire la densité uniquement pour la largeur visible en agrégeant min/max ; isoler le Canvas de position/assombrissement du Canvas des données.

2026-09-29 — Revue d’impact : la durée publique historique du lecteur conserve son repli sur les métadonnées ; `playbackDuration` expose séparément la durée positive rapportée par le moteur pour éviter un curseur temporel fondé sur un tag.

## Outcomes & Retrospective

L’implémentation utilise le pipeline min/max et la palette monochrome existants. Aucun corpus utilisateur ni mesure de performance n’a été recueilli ; la compilation et le contenu distribué ont été vérifiés, mais la recette fonctionnelle reste à faire par l’utilisateur. Les captures de variantes restent un historique et ne correspondent pas à des modes livrés. Révision du 29 septembre 2026 : choix monochrome enregistré et périmètre réduit au rendu et au repère de lecture.

Livraison du 29 septembre 2026 : commit fonctionnel `e907053` poussé sur `origin/main`. Le commit local antérieur `b39dbe3` sur les décisions SoundCloud a été conservé comme parent et poussé avec la livraison ; aucune modification locale de `.gitignore`, `AGENTS.md` ou `.codex/` n’a été incluse.
