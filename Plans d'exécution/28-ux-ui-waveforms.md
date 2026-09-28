# 28 — Waveforms : lisibilité, couleurs et repère temporel

## Résultat attendu et décision utilisateur

Rendre les changements de passages plus faciles à discerner, afficher un repère temporel avec la tête de lecture et assombrir la portion déjà lue. L’utilisateur demande de comparer des variantes monochrome, 3 bandes et RGB dans l’interface avant de choisir. La maquette retenue doit être validée avant le développement fonctionnel du nouveau rendu.

Lire les plans 23, 19 et 22, puis `docs/ux/specification.md`. L’addendum du 25 septembre limite la waveform à une vue monochrome cliquable. La présente demande ouvre une étude visuelle de couleur ; elle n’autorise pas automatiquement toutes les anciennes fonctions waveform. La boucle A/B, l’édition, les cues, les beatgrids et l’analyse musicale restent hors périmètre.

Le « zoom in » du brouillon est traité d’abord comme une demande de meilleure lisibilité de la vue complète. Aucun zoom temporel interactif ou déplacement horizontal n’est ajouté sans une révision explicite du périmètre. Une vue complète permet toujours de cliquer une position dans tout le morceau.

## Sources et constats à vérifier

Lire `src/mtee/qml/components/WaveformView.qml`, `WaveformPreview.qml`, `src/mtee/qml/views/FullscreenPlayer.qml`, `src/mtee/models/waveform_model.py`, `src/mtee/services/waveform_service.py`, `waveform_cache.py` et `src/mtee/domain/waveform.py`. Lire `tests/unit/test_waveform_reduction.py`, `test_waveform_timing.py`, `tests/integration/test_waveform_cache.py` et `tests/ui/test_fullscreen_waveform.py`.

`WaveformView.qml` dessine chaque min/max comme un trait de hauteur presque totale, dans une couleur uniforme. Le curseur repeint actuellement l’ensemble du Canvas. `_display_samples()` sélectionne un niveau de pyramide d’au plus 1 200 points et prend les extrema des canaux. Le cache conserve des extrema d’amplitude ; il ne contient ni énergie par bande ni RMS. La capture Notion montre de longues plages presque pleines. Elle ne permet pas de conclure que le signal audio est réellement écrêté.

Réduire le nombre de points en regroupant encore des extrema peut rendre la silhouette plus pleine. Un zoom vertical peut également accentuer cette impression. La correction ne doit pas être choisie uniquement à partir de l’intuition « moins de traits = plus précis ». Comparer les données avant de fixer le traitement.

## Jalon 28.1 — Corpus de comparaison et diagnostic borné

Préparer trois sources synthétiques ou copies de recette : signal avec intro calme et passages denses, signal à impulsions séparées avec silence, signal avec changements entre graves/médiums/aigus à niveau global comparable. Ajouter si possible un morceau long de recette autorisé, sans le versionner. Noter durée, dimensions de la vue, niveau de pyramide retenu et nombre de points.

Comparer le rendu actuel à un rendu de densité adaptée à la largeur. Vérifier que le problème vient de la réduction, de la géométrie ou des propriétés réelles du morceau. Conserver les extrema pour ne pas effacer des événements courts. Si une enveloppe RMS est utile, la présenter comme une mesure d’énergie complémentaire : elle ne se reconstruit pas honnêtement depuis le seul min/max.

Produire un diagnostic court dans `docs/ux/review-ux-ui-2026-09.md`. Aucune mesure de performance ni amélioration de lisibilité ne doit être annoncée avant observation.

## Jalon 28.2 — Trois variantes examinables

Présenter les trois variantes avec exactement les mêmes passages, largeur, hauteur et position de lecture. Utiliser le thème réel de MTEE et ajouter une capture intégrée au Fullscreen player. La vue monochrome peut comparer une silhouette plus lisible, une densité de traits adaptée et, si justifié, une enveloppe d’énergie distinguée des pics.

| Variante | Question à examiner | Données nécessaires en version fonctionnelle |
|---|---|---|
| Monochrome | Géométrie et densité suffisent-elles à distinguer les passages ? | Extrema existants ; RMS seulement si retenu et réellement calculé |
| 3 bandes | La superposition graves/médiums/aigus facilite-t-elle le repérage ? | Amplitudes ou énergies calculées dans trois bandes définies |
| RGB | Une couleur composite par instant reste-t-elle claire dans le thème Acid ? | Trois valeurs de bande avec une règle de mélange documentée |

« Inspiré de Rekordbox » décrit ici une direction visuelle. Ne pas annoncer la reproduction exacte d’un algorithme propriétaire. Les maquettes peuvent employer des données synthétiques explicitement étiquetées ; elles ne doivent pas colorer arbitrairement des extrema réels en prétendant montrer leur fréquence.

Pour chaque variante, montrer début, milieu et fin, pause et lecture, zone déjà lue assombrie et temps attaché au curseur. Mettre la lisibilité du curseur à l’abri des couleurs de bande. Présenter aussi une largeur réduite et un état Preparing/error sans données. Le marqueur ne doit pas sortir de l’écran aux extrémités.

Le dossier de revue contient les captures, les avantages observés, les coûts techniques et une recommandation motivée. Demander le choix une fois ce dossier prêt. Enregistrer la réponse dans ce plan et la spécification. La réponse de préparation « comparer trois variantes » n’est pas une approbation des trois rendus fonctionnels ni une demande de sélecteur permanent dans Settings.

## Jalon 28.3 — Implémenter seulement le rendu retenu

### Branche monochrome

Si cette variante est retenue, conserver le cache actuel lorsque les données suffisent. Adapter la réduction d’affichage au budget de pixels et rendre les pics courts visibles. Ne pas supprimer des points au hasard, ajouter de faux creux, appliquer un gain par segment ou masquer les vraies crêtes pour rendre le résultat plus joli. Si le diagnostic justifie une enveloppe RMS, effectuer son calcul dans le worker et versionner les nouvelles données comme décrit ci-dessous.

### Branche 3 bandes ou RGB

Si une variante fréquentielle est retenue, calculer les données nécessaires hors du thread graphique, à la demande pour le morceau courant. Les extrema existants ne suffisent pas à retrouver les bandes. Définir précisément fréquences de coupure, traitement des canaux, mesure par fenêtre, normalisation commune au morceau, règle de couleur et résolution temporelle. Les valeurs sont des choix d’implémentation à justifier par le corpus du jalon 28.1 ; elles ne sont pas imposées par le brouillon Notion.

Réutiliser le décodage local existant. Étudier d’abord les capacités du runtime livré avant d’ajouter une dépendance. Si une bibliothèque devient nécessaire, documenter licence, taille, temps de calcul et inclusion Windows. Aucun retour des services d’analyse BPM/Key ou de l’indexation globale. Ces données restent des caches de visualisation, jamais des tags ni des résultats musicaux écrits sur les sources.

Étendre le contrat `WaveformData` ou une structure de rendu dédiée avec une version explicite. La clé de cache comprend source, révision, version d’algorithme et configuration pertinente. Un ancien cache monochrome reste lisible pour le rendu qui sait l’utiliser ou est recalculé proprement pour la nouvelle représentation. Ne pas traiter des octets anciens comme un nouveau format. Limiter taille, mémoire et décompression avant allocation ; ignorer un résultat devenu périmé.

Les modes monochrome/3 bandes/RGB sont des branches de décision, pas trois implémentations à livrer d’office. Si la variante retenue dépasse le budget technique convenu, présenter le résultat de l’étude et une option de réduction concrète avant de changer le choix visuel.

## Jalon 28.4 — Curseur, temps et portion lue

Utiliser la position et la durée du lecteur comme référence temporelle. Tant qu’une durée valide manque, garder le contrôle de seek simple et l’état de préparation ; ne pas inventer une durée. La conversion en microsecondes reste à la frontière du modèle. La tête est bornée dans la vue complète et se déplace correctement après un seek, un redémarrage et un changement de morceau.

Séparer si possible le dessin coûteux des données et la couche légère du curseur/assombrissement. La progression n’a pas à recalculer la réduction ni repeindre inutilement tous les points à chaque tick. Un changement de largeur, de données ou de thème déclenche le dessin nécessaire. Mesurer avant de remplacer le Canvas par une infrastructure plus complexe.

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

- [x] 2026-09-28 — Capture, sources et demande de comparaison des variantes inspectées.
- [x] 2026-09-28 — Diagnostic du contrat de données existant documenté ; comparaison et grille d’extrémités synthétiques rendues dans la planche commune.
- [ ] Corpus représentatif et comparaison effective de la densité du rendu terminés ; aucun signal audio ni mesure de performance observé à cette revue.
- [ ] Choix visuel explicite enregistré et spécification mise à jour.
- [ ] Données et rendu de la variante retenue implémentés.
- [ ] Marqueur et portion lue vérifiés.
- [ ] Tests, mesures, recette Windows, distribution, rapport, commit et push terminés.

## Surprises & Discoveries

2026-09-28 — La réduction actuelle préserve les extrema et les canaux, mais elle peut donner une silhouette très pleine à l’échelle d’un morceau entier. Son cache ne peut fournir une coloration fréquentielle authentique à lui seul. Le plan doit distinguer dessin QML et calcul des données de visualisation.

## Decision Log

2026-09-28 — Utilisateur : comparer monochrome, 3 bandes et RGB dans des maquettes avant de choisir. Codex : commencer par un diagnostic de densité, garder la vue complète et ne développer que la variante choisie. Aucun accord n’est enregistré pour un zoom temporel ou un sélecteur de trois modes.

2026-09-28 — Codex : captures comparatives synthétiques, sans prétendre analyser l’audio. Monochrome recommandé pour réutiliser les extrema et le cache actuels ; 3 bandes et RGB demandent un calcul fréquentiel réel, une configuration versionnée et un coût de cache. Choix utilisateur encore attendu dans `docs/ux/review-ux-ui-2026-09.md`.

## Outcomes & Retrospective

Le pipeline existant a été lu et la planche des variantes, positions et états d’erreur est prête. Les énergies affichées sont synthétiques. Aucun corpus audio, calcul de bande, mesure ni code de waveform n’a été traité ; le choix visuel et la comparaison effective de la densité restent requis. Révision du 28 septembre 2026 : ajout des captures synthétiques et du diagnostic exact du pipeline.
