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

- [x] Tests dédiés aux fonctions retirées supprimés et attentes de migration ajustées; aucun test n'a été exécuté.
- [x] Déclenchement CI étendu à `fix` et runtimes FFmpeg verrouillés déjà présents sur l'environnement; compilation Python, imports critiques et lint QML passent.
- [x] Build Windows depuis le commit `6098748` réussi dans un dossier isolé; vérification des runtimes, DLL et licence effectuée par le script.
- [x] Inspection du contenu et empreinte de l'exécutable consignées dans `docs/validation/stabilisation-fix-6098748.md`.
- [x] `fix` intégré à `main` par fast-forward au commit source `4655a5a`, puis poussé sur `origin/main`.
- [x] Distribution GUI recompilée depuis `main` au commit `4655a5a`; smoke-test paqueté réussi avec un profil de données isolé.
- [x] À la demande de l'utilisateur, livraison remplacée par un exécutable PyInstaller monofichier; build et smoke-test réussis depuis `main` au commit source `fe8f41a`, empreinte et limites consignées.
- [x] Compatibilité de la base utilisateur `010_audio_analysis` réparée sans retirer ses tables ni ses données; les migrations 011–014 ont été appliquées après sauvegarde v10. Le test paqueté sur une copie de cette base passe et l'EXE ouvre maintenant le profil habituel.
- [x] EXE monofichier reconstruit depuis le commit `b9945bf` et placé seul dans `dist/MTEE.exe`; build, vérification des ressources, smoke-test et fenêtre GUI validés.
- [x] Branche `fix` supprimée localement et sur `origin`; anciens paquets/dossiers de compilation et profils de démonstration créés pour la recette supprimés. `dist` ne garde que `MTEE.exe`.
- [ ] Parcours natifs avec bibliothèque audio réelle et opérations d'écriture non exécutés; ils restent à faire sur une copie de recette.

## Surprises & Discoveries

2026-09-25 — Au commit `6098748`, le build isolé a réussi; le smoke-test paqueté et les parcours natifs n'avaient pas été exécutés.

- 2026-09-25 — Le build standard a produit l'exécutable, puis PyInstaller a échoué en nettoyant `dist/MTEE` car `libmpv-2.dll` était verrouillée. Le script accepte maintenant des répertoires de sortie et de travail alternatifs pour compiler sans toucher à cet artefact.
- 2026-09-25 — Le build Windows GUI de `main` produit un EXE de 2,83 Mio dans une distribution en dossier de 1 982 fichiers. Le smoke-test avec le profil local existant refuse la migration retirée `010_audio_analysis` et laisse la base intacte; le même paquet démarre avec un répertoire de données isolé.
- 2026-09-25 — La livraison finale monofichier est un EXE de 231 568 186 octets (220,84 Mio), avec Qt/QML et les runtimes intégrés. Le smoke-test passe avec un profil séparé; les anciens répertoires d'essai ont été retirés après fermeture de la branche `fix`.
- 2026-09-26 — Le nouvel EXE accepte uniquement l'historique v10 connu `audio_analysis`, en préservant ses tables et sa ligne de migration. Une copie cohérente de la base utilisateur s'est migrée jusqu'à v14 avec ses lignes d'analyse intactes; le smoke-test paqueté puis le lancement normal avec le profil habituel ont réussi.

## Decision Log

- 2026-09-25 — La demande explicite de compilation autorise le build; les parcours natifs et le recyclage restent des vérifications séparées.
- 2026-09-25 — `fix` est fusionné à `main` par fast-forward après vérification que les modifications locales non commitées ne recouvrent pas les chemins de la branche. Pour la recette utilisateur, le lanceur de distribution passe un profil séparé afin de ne pas réutiliser une base issue de l'ancienne migration.
- 2026-09-25 — À la demande de l'utilisateur, la sortie Windows passe à un EXE monofichier; les DLL et ressources QML sont intégrées et leur présence dans l'archive PyInstaller est vérifiée.

## Outcomes & Retrospective

Compilation syntaxique, imports critiques et lint QML passent. Le build de `main` au commit source `4655a5a` a produit `dist/main-prod-4655a5a/MTEE/MTEE.exe`; le script a vérifié les runtimes FFmpeg/libmpv et la licence FFmpeg. Le paquet complet et l'empreinte sont consignés dans `docs/validation/stabilisation-main-4655a5a.md`. Le smoke-test isolé passe et l'application GUI a été lancée. Le profil de données historique est refusé sans modification à cause de `010_audio_analysis`; le lanceur de test fournit un profil distinct. La recette audio/natale et la suite automatisée ne sont pas réalisées dans cette validation.

Livraison monofichier initiale au commit source `fe8f41a` (220,84 Mio) consignée dans `docs/validation/main-singlefile-fe8f41a.md`. Après constat que la base utilisateur portait le schéma 10, le traitement de l'historique exact `010_audio_analysis` a été adapté pour garder tables, lignes et historique, puis appliquer 011–014 avec sauvegarde. Le build issu de `b9945bf` fait 231 570 914 octets; SHA-256 `AE963B28A554C0E0E7D55AC3578626452193790D19AD195C1B7E8B0B83EF420F`. La copie cohérente de la base utilisateur s'est ouverte jusqu'au schéma 14 sans différence de nombre de lignes dans les tables déjà présentes; la sauvegarde v10 `mtee.sqlite3.v10.20260926T110154Z.backup` a été créée à côté de la base. `dist` ne contient que le nouvel EXE, ouvert sur le profil par défaut. La lecture audio réelle et les écritures sur fichiers audio restent non vérifiées.
