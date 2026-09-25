# 19 — Explorer, pochettes et waveform

## Résultat et prérequis

Rendre l’arbre, les pochettes et une waveform longue utilisables sans bloquer Qt. Prérequis : lots 17–18, schéma SQLite vérifié, lecture directe des modèles, providers et vues concernés.

## Navigation et modèles

Ajouter une représentation indexée du parent direct des fichiers/dossiers via une migration supérieure à 010. La requête d’enfants directs retourne seulement UUID, libellé, type, enfants et disponibilité. Charger les branches à la demande dans un worker, conserver le cache après repli et ignorer les générations périmées. Une mise à jour de scan ne rafraîchit que les parents modifiés. Une ouverture déjà active est sans effet. Le clic sur un titre garde une sélection partagée avec la liste centrale.

Remplacer les recherches répétées de ligne par un index UUID→ligne. Appliquer des insertions/suppressions/modifications ciblées; pour le tri complet, remapper les index persistants avec les signaux Qt de layout. Préserver sélection et ancre visible (UUID et décalage). Libérer les modèles sans vue. Les snapshots de session sont des copies indépendantes; sauvegarde regroupée à 300 ms, une seule écriture en cours et dernier snapshot en attente.

## Pochettes et waveform

Le catalogue fournit une URL `image://artwork/UUID/révision`; CoverArt ajoute la taille sans écraser la révision. Invalider au changement de révision, conserver les paliers et ne pas cacher durablement une erreur transitoire.

Une seule waveform est active; les requêtes sont identifiées UUID/révision/configuration et les anciennes réponses sont rejetées. Réduire les blocs PCM avec `array`, min/max, conserver les frames incomplètes aux frontières et les extrema des canaux. Préparer jusqu’à 1200 points hors UI et séparer signal de points, progression et état. Borner le cache avant allocation/décompression; un cache illisible se recalcule. Une erreur d’écriture cache n’invalide pas le résultat mémoire. Garder la barre de recherche simple quand les données manquent.

## Vérification et reprise

Exercer catalogue→QML→provider→image rendue, plusieurs tailles/révisions et erreurs transitoires. Sur une waveform longue, naviguer et demander une seconde génération; l’ancienne ne change ni affichage ni progression. Vérifier frontières PCM, taille/en-tête/décompression du cache, ouverture/repli d’arbre, tri, sélection et ancre visible.

Une migration en échec restaure la sauvegarde cohérente; ne pas reconstruire le catalogue d’un utilisateur. Un cache dérivé invalide est recalculable.

## Progress

- [ ] Requête d’arbre et génération de demande.
- [ ] Révisions de cover et waveform, bornes et vérifications à consigner.

## Surprises & Discoveries

À renseigner après lecture complète des repositories, modèles et signaux réellement impliqués.

## Decision Log

- 2026-09-25 — La waveform calculée reste à la demande pour le morceau courant; aucune indexation globale.
- 2026-09-25 — Le point d’entrée de cover transmet toujours UUID, révision et taille.

## Outcomes & Retrospective

À compléter avec les parcours observés et les limites de recette Windows.
