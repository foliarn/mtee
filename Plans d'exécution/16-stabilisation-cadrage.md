# 16 — Cadrage et validation de la stabilisation

## Résultat et prérequis

Rétablir une application Windows utilisable pour parcourir une bibliothèque, lire de longs morceaux, afficher les pochettes, modifier les métadonnées, convertir et envoyer un fichier à la corbeille. Ce plan cadre les lots 17 à 22; il ne constitue pas à lui seul une preuve de comportement. Prérequis : branche de travail `fix`, état Git inspecté et changements locaux étrangers préservés.

## État établi et périmètre

Le dépôt possède une application PySide6/QML, une base SQLite migrée, un lecteur libmpv, un cache waveform, une chaîne FFmpeg, des jobs Qt et un moteur d’opérations fichiers. L’analyse calculée a été ajoutée avec le commit 625dc0b et ses licences avec 8cc8f25. Le graphe du 2026-09-25 situe les classes d’analyse dans le démarrage, les modèles, les migrations et les tests. Les performances signalées par le plan fourni restent des critères à reproduire, pas des mesures déjà obtenues.

Le produit conserve les tags BPM/Key présents dans les fichiers. L’analyse calculée, les commandes et panneaux associés, les contrôles de zoom/déplacement/A-B et les opérations Rename/Move/Copy/presse-papiers/glisser-déposer sont retirés. La waveform reste monochrome et cliquable pour déplacer la lecture. La corbeille Windows réelle est conservée. Aucun nettoyage de données personnelles ni réinstallation n’est prévu.

## Contrats transversaux

Les propriétés QML lisent des instantanés préparés. Les services exécutent les accès fichiers, SQLite, Mutagen et processus externes hors du thread graphique. Le modèle Qt est muté dans ses slots sur son thread propriétaire. Toute demande asynchrone transporte une génération et une révision; seul le résultat courant est appliqué. Progression, position, queue, identité du morceau et catalogue ont des notifications distinctes. Les jobs se terminent par un résultat métier cohérent ou une erreur structurée. Les publications n’écrasent jamais une destination existante; l’échec de la corbeille ne supprime rien définitivement.

## Ordre, recette et critères de fin

Exécuter les plans 17, 18, 19, 20, 21, puis 22. Chaque lot consigne cause, changement, parcours réellement exercé et limite. La compilation Windows vérifie le paquet produit, pas la recette souris/clavier, le comportement natif de libmpv ou le recyclage réel. Les scénarios de bibliothèque volumineuse, lecture stable, changements rapides, annulation de processus silencieux, conservation des métadonnées et fermeture restent « non vérifiés » tant qu’ils ne sont pas observés.

Mesurer séparément cache froid/chaud et calcul actif sur un jeu synthétique documenté, sans relever les seuils. Une vérification absente n’empêche pas les commits de développement, mais interdit de déclarer la stabilisation validée.

## Reprise après erreur

Reprendre depuis le dernier commit de lot. Les migrations sont transactionnelles et précédées d’une sauvegarde cohérente. Une base dont l’historique ne correspond pas aux migrations connues est refusée clairement; ne pas la rétrograder, l’effacer ou réutiliser le numéro 010. Garder les copies de recette isolées et restaurables.

## Progress

- [x] 2026-09-25 — Périmètre reçu, état Git inspecté et branche `fix` créée.
- [ ] Lots 17–22 : développement et preuves à inscrire pendant l’exécution.

## Surprises & Discoveries

- 2026-09-25 — Modifications locales préexistantes dans `.gitignore`, `AGENTS.md` et `.codex/`; elles restent hors des commits de stabilisation.
- 2026-09-25 — La migration 010 est la plus récente au départ; son historique doit être traité sans effacer les bases existantes.

## Decision Log

- 2026-09-25 — Créer la série 16–22 avant les lots afin de respecter la gouvernance du dépôt et de distinguer exigences observées et hypothèses.
- 2026-09-25 — L’instruction utilisateur de compiler autorise le build même si le document source interdisait build et correctifs pendant la seule phase de préparation documentaire.

## Outcomes & Retrospective

À compléter après le lot 22. Au moment du cadrage, aucun parcours de recette n’est déclaré corrigé; la compilation finale et les vérifications natives restent à réaliser.
