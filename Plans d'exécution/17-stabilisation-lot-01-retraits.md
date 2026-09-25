# 17 — Retirer l’analyse et les fonctions abandonnées

## Résultat et prérequis

Retirer l’analyse calculée ainsi que les commandes de waveform et d’opérations fichiers abandonnées, tout en conservant lecture, tags présents, édition, conversion et waveform monochrome cliquable. Le cadrage 16 et l’inspection des commits 625dc0b/8cc8f25 sont les prérequis.

## Modifications et contrats

Supprimer de façon ciblée le domaine, le service, le dépôt, le modèle, les analyseurs, panneaux, branchements de démarrage, commande `--analysis-smoke-test`, fixtures et tests propres à l’analyse. Retirer la migration 010 sans réattribuer ce numéro; avant migration, comparer les versions/noms enregistrés aux scripts livrés et refuser explicitement un historique inconnu ou retiré. Les versions futures commencent au-dessus de 010.

Retirer librosa, NumPy, SciPy, leurs dépendances devenues inutiles et les licences de packaging associées. Garder les licences FFmpeg, libmpv et des composants maintenus. Ne pas confondre l’objet `PyInstaller.Analysis` avec la fonction produit.

Retirer zoom, déplacement horizontal, boucle A/B, leurs signaux, propriétés, commandes mpv et contrôles de démonstration. Retirer `destinationFolders`, les actions Rename/Move/Copy, le presse-papiers de fichiers, le glisser-déposer et leur code exclusivement dédié. Préserver les primitives partagées d’écriture sans remplacement, d’édition de tags et de corbeille. Aucune donnée utilisateur n’est nettoyée.

## Vérification et critères de fin

Vérifier les références Python/QML après le retrait, le chargement des vues réelle et démo, les imports et la résolution des dépendances. Contrôler une base neuve, une copie avec historique connu et une copie ayant la migration 010 : cette dernière est refusée clairement, sans mutation ni effacement. Vérifier que les tags BPM/Key restent éditables. Le lot est fini lorsque les commandes et fonctions abandonnées sont absentes du chemin fonctionnel et les composants maintenus restent reliés.

## Reprise après erreur

Restaurer uniquement les éléments manquants depuis le commit précédent, sans réintroduire l’intégration d’analyse. Ne jamais diminuer le numéro de schéma ni modifier les données source lors d’une reprise.

## Progress

- [ ] Inventaire des références et suppression ciblée.
- [ ] Vérifications de migration, QML et packaging consignées après exécution.

## Surprises & Discoveries

- 2026-09-25 — L’inventaire des commits indique que l’analyse touche app.py, workspace, démo, QML, migrations, dépendances et packaging.

## Decision Log

- 2026-09-25 — Garder le trou de migration 010 comme historique permanent.
- 2026-09-25 — BPM/Key lus ou écrits dans le média sont des métadonnées source, pas des résultats d’analyse.

## Outcomes & Retrospective

À compléter avec fichiers réellement supprimés, commandes exécutées, résultats et limites résiduelles.
