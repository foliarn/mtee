# 17 — Retirer l’analyse et les fonctions abandonnées

## Résultat et prérequis

Retirer l’analyse calculée ainsi que les commandes de waveform et d’opérations fichiers abandonnées, tout en conservant lecture, tags présents, édition, conversion et waveform monochrome cliquable. Le cadrage 16 et l’inspection des commits 625dc0b/8cc8f25 sont les prérequis.

## Modifications et contrats

Supprimer de façon ciblée le domaine, le service, le dépôt, le modèle, les analyseurs, panneaux, branchements de démarrage, commande `--analysis-smoke-test`, fixtures et tests propres à l’analyse. Retirer la migration 010 sans réattribuer ce numéro; avant migration, comparer les versions/noms enregistrés aux scripts livrés. L'historique exact `010_audio_analysis` reste un historique retiré connu : conserver sa ligne et toutes ses tables/données, faire la sauvegarde SQLite cohérente existante, puis appliquer les migrations ultérieures. Refuser les autres historiques inconnus. Les versions futures commencent au-dessus de 010.

Retirer librosa, NumPy, SciPy, leurs dépendances devenues inutiles et les licences de packaging associées. Garder les licences FFmpeg, libmpv et des composants maintenus. Ne pas confondre l’objet `PyInstaller.Analysis` avec la fonction produit.

Retirer zoom, déplacement horizontal, boucle A/B, leurs signaux, propriétés, commandes mpv et contrôles de démonstration. Retirer `destinationFolders`, les actions Rename/Move/Copy, le presse-papiers de fichiers, le glisser-déposer et leur code exclusivement dédié. Préserver les primitives partagées d’écriture sans remplacement, d’édition de tags et de corbeille. Aucune donnée utilisateur n’est nettoyée.

## Vérification et critères de fin

Vérifier les références Python/QML après le retrait, le chargement des vues réelle et démo, les imports et la résolution des dépendances. Contrôler une base neuve, une copie avec historique connu et une copie ayant la migration 010 : l'historique exact est mis à niveau sans supprimer ses tables/données, avec sauvegarde v10; un historique différent reste refusé sans mutation. Vérifier que les tags BPM/Key restent éditables. Le lot est fini lorsque les commandes et fonctions abandonnées sont absentes du chemin fonctionnel et les composants maintenus restent reliés.

## Reprise après erreur

Restaurer uniquement les éléments manquants depuis le commit précédent, sans réintroduire l’intégration d’analyse. Ne jamais diminuer le numéro de schéma ni modifier les données source lors d’une reprise.

## Progress

- [x] Retraits ciblés effectués dans le domaine, les services, les modèles, la démo, les vues, la CLI et les dépendances; le presse-papiers et les contrôles de fichiers abandonnés sont retirés.
- [x] La migration 010 reste absente et les migrations ultérieures gardent leurs numéros; imports Python critiques, compilation syntaxique et lint QML passent (avertissements existants de bindings non qualifiés).
- [x] Compatibilité de la migration retirée 010 ajoutée : les données et la ligne `audio_analysis` sont gardées, les migrations 011–014 sont appliquées et une sauvegarde v10 précède leur application; l'historique inconnu reste refusé.
- [x] Test d'intégration sur une base synthétique v10 : données applicatives et d'analyse conservées, sauvegarde cohérente, et seconde ouverture sans nouvelle migration.
- [x] Le nouvel EXE ouvre la base utilisateur par défaut; le schéma 10 est passé à 14 après sauvegarde v10, et la fenêtre MTEE est visible.

## Surprises & Discoveries

- 2026-09-25 — L’inventaire des commits indique que l’analyse touche app.py, workspace, démo, QML, migrations, dépendances et packaging.
- 2026-09-26 — La base utilisateur existante en lecture seule porte exactement `user_version=10` et les migrations 1–10, dont `audio_analysis`. La migration 010 ne fait qu'ajouter ses tables d'analyse; les migrations 011–014 sont indépendantes de ces tables. Le premier build retirait silencieusement cette base parce que l'application GUI n'a pas de flux stderr visible.

## Decision Log

- 2026-09-25 — Garder le trou de migration 010 comme historique permanent.
- 2026-09-25 — BPM/Key lus ou écrits dans le média sont des métadonnées source, pas des résultats d’analyse.
- 2026-09-26 — À la demande explicite de l'utilisateur de démarrer avec sa base complète, conserver sans modification les tables et l'historique de `010_audio_analysis`, créer la sauvegarde v10 avant 011–014, et assouplir uniquement cette migration historique connue. Aucune autre migration retirée ou inconnue n'est admise.

## Outcomes & Retrospective

L'analyse produit, ses services/dépôts/modèles/vues et tests dédiés ont été retirés, ainsi que zoom, déplacement horizontal, boucle A/B, presse-papiers et anciennes opérations Move/Copy/Rename. Les dépendances directes devenues inutiles ont été retirées. `uv run --no-sync python -m compileall -q src` et les imports des modèles/services critiques passent. Aucun démarrage applicatif, test automatisé ou migration sur copie de base n'a été exécuté. Le build Windows est consigné au lot 22; le refus de migration 010 reste validé statiquement uniquement.

Révision du 2026-09-26 : le refus absolu de la migration 010 empêchait le démarrage d'une base réelle pourtant compatible avec les migrations suivantes. Le correctif conserve les trois tables d'analyse et leurs enregistrements comme données historiques inutilisées, conserve la ligne de migration 010, et applique 011–014 après sauvegarde cohérente. Le test d'intégration sur une copie synthétique v10 passe; le build et l'ouverture de la base utilisateur sont documentés au lot 22.
