# 18 — Notifications, tâches et lecteur

## Résultat et prérequis

Limiter le travail déclenché par les progressions et ticks du lecteur, garder une seule liste de tâches et fermer proprement jobs, accès audio et SQLite. Le lot 17 précède ce travail; lire les contrats de `JobService`, `WorkspaceModel`, `PlayerService` et leurs modèles avant toute modification.

## Causes à vérifier et changements

Confirmer dans les sources que les progressions ne provoquent pas de rafraîchissement du catalogue et que `ConversionQueueModel` ignore les jobs étrangers. Séparer position, état, morceau courant/métadonnées/pochette, queue et catalogue. Les tâches visibles viennent seulement de `JobsListModel`; retirer la liste parallèle et le bouton de tâche fictive du mode réel.

`JobService` mémorise la progression la plus récente, regroupe les émissions à 100 ms par job et publie immédiatement les transitions d’état. Une minuterie différée est annulée à l’état terminal. Ne pas utiliser un timer pour déplacer du travail synchrone hors du thread graphique.

La file de lecture consomme un instantané d’identité, ordre et disponibilité préparé dans le catalogue. Pas de `Path.is_file()` par titre sur chaque refresh ni de requête SQLite par ligne au clic Play. Les chargements de morceau sont prioritaires; les réponses dépassées libèrent leurs ressources. Les vingt entrées d’historique affichées sont les seules conservées. L’inspection de tags est à la demande, asynchrone et cache UUID/révision; les capacités d’écriture sont revalidées dans le worker.

Un worker retourne un résultat structuré; le slot Qt applique l’état. Annulation, échec, conflit, succès et lots partiels gardent leur sens. La fermeture interdit de nouveaux travaux, annule/arrête préparations et processus, finit les écritures à une frontière sûre, attend les utilisateurs de SQLite et conserve le verrou de lecture jusqu’à confirmation native de fermeture. Si la fermeture libmpv échoue, le verrou n’est pas libéré comme si la source était fermée.

## Vérification et reprise

Vérifier qu’un tick stable ne déclenche ni parcours de dossier, ni inspection de tags, ni reconstruction de file. Exercer progression groupée et état terminal immédiat, jobs étrangers, changements rapides de morceau et fermeture pendant lecture/préparation. Les ctypes restent conformes au runtime libmpv verrouillé. Le crash natif demeure distinct tant qu’il n’est pas diagnostiqué.

Après interruption, conserver l’état du job et les verrous; redémarrer seulement après constat de la fermeture effective du backend.

## Progress

- [ ] Corriger les notifications et les sources de rafraîchissement identifiées.
- [ ] Consigner instrumentation et observations réelles du lecteur.

## Surprises & Discoveries

À renseigner avec traces de demande, commande native, événements, arrêt et libération du verrou.

## Decision Log

- 2026-09-25 — La position ne notifie que les consommateurs temporels; elle ne signifie pas que contenu du morceau ou queue a changé.

## Outcomes & Retrospective

À compléter. Les seuls démarrages UI ou tests de démonstration ne valident pas la fermeture native.
