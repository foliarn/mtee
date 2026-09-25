# 22 — Suite de vérification et distribution

## Résultat et prérequis

Garder une suite courte centrée sur les risques concrets, des fixtures reproductibles et un build Windows depuis la branche `fix`. Ce lot clôt les lots 17–21 et met à jour les ExecPlans et les notes de validation avec des observations réelles.

## Modifications

Retirer les tests devenus sans objet avec analyse, zoom/A-B et opérations retirées. Fusionner les tests redondants de getters/valeurs par défaut/démo. Conserver les cas à risque : exclusivité d’accès, révisions, préservation tags/pochettes, collisions, transactions, annulation et reprise. Les tests qui démarrent FFmpeg/libmpv sont classés comme intégration/native, pas unitaires. Remplacer les fixtures `.local` implicites par des fixtures synthétiques générées. Une fixture ou un runtime obligatoire manquant échoue explicitement. Mettre à jour la CI pour installer les runtimes verrouillés nécessaires.

La chaîne courte vise compilation syntaxique Python, pylint centré sur les erreurs et exceptions PySide documentées, validation de syntaxe/imports QML, tests ciblés par lot, parcours E2E séparés pour natif, puis `pwsh -File scripts/build_windows.ps1`. Un build n’est pas un parcours E2E. Exclure Ruff/Pyright de la chaîne obligatoire telle que précisée par le plan de stabilisation.

## Vérification, livraison et reprise

Compiler depuis `fix`, examiner le contenu du paquet, DLL et licences ainsi que le smoke-test si disponible. Le parcours complet paqueté doit être exercé hors checkout sur une installation Windows de référence; si ce n’est pas observé, l’indiquer comme non vérifié. Consigner versions, commandes, environnement et résultat dans `docs/validation/` sans chemin personnel ni collection réelle.

Examiner l’état Git, diffs non indexé/indexé et chaque chemin ajouté. Garder les changements locaux étrangers hors commits. Committer par lot cohérent; push sans force vers `origin/fix`, puis fetch et comparaison de refs. En cas d’échec, préserver le build reproductible et reprendre sans réécrire l’historique.

## Progress

- [ ] Nettoyage des tests obsolètes et fixtures reproductibles.
- [ ] CI et build final réellement exécutés.
- [ ] Notes de validation et publication à confirmer.

## Surprises & Discoveries

À consigner après les builds et parcours; aucun résultat futur n’est anticipé.

## Decision Log

- 2026-09-25 — La demande explicite de compilation autorise le build; les parcours natifs et le recyclage restent des vérifications séparées.

## Outcomes & Retrospective

À compléter avec hash du commit final, preuve de build, push éventuel et limites non validées.
