# Étape 106 — Types, dossiers, filtres et artistes masqués

ExecPlan du 7 octobre 2026, selon `PLANS.md`. Suite du catalogue du [plan 104](104-artist-manager-importation.md) et de l'enrichissement du [plan 105](105-pilote-enrichissement-artistes.md) : la table `artist_enrichment_reviews` (rôles, Bass-related, tags, décision) entre dans l'application. Aucun fichier audio n'est lu ni écrit par cette étape.

## Objectif et décisions de l'utilisateur

- Types = rôles de l'enrichissement : Producer, DJ, Singer, MC, cumulables. Un artiste multi-types apparaît dans chacun de ses dossiers ; un artiste sans rôle va dans « No role ».
- Sidebar Artists : un dossier par type (Producer, DJ, Singer, MC) plus « No role », chacun listant ses artistes. Un clic sur un dossier ouvre le catalogue filtré sur ce type.
- Liste : filtres par nom (recherche existante), par type (multi-sélection, OU) et par nombre de morceaux (minimum), colonne Type, molette ×4.
- `idgaf` : artistes masqués par défaut dans la liste et la sidebar ; interrupteur « Show hidden artists » commun aux deux.
- Édition depuis MTEE, sur la page de l'artiste (« Edit profile ») et par clic droit (liste et sidebar) : types, Bass-related (inconnu/oui/non), idgaf, tags libres. `idgaf` et la décision `exclude` changent ensemble ; une autre décision (`uncertain`, `pending`) est conservée tant que l'artiste reste visible.
- Nettoyage de la base : suppression de tous les artistes sans aucun morceau, après validation de la liste par l'utilisateur.
- Aucune maquette demandée : la proposition est réalisée directement (captures dans la section Contrôles).

## Progress

- [x] 2026-10-07 — Lire la table, la liste et la sidebar actuelles ; poser les questions, recueillir les réponses.
- [x] 2026-10-07 — Commit `e1f5344` des travaux en cours antérieurs (tag editor, déplacement par glisser-déposer, tâches), poussé.
- [x] 2026-10-07 — Liste des 406 orphelins produite (`.local/validation/106/orphan-artists.md`, ignoré par Git) et validée par l'utilisateur.
- [x] 2026-10-07 — Migration 020, domaine `artist_profile`, dépôt, service et modèles (types, filtres, masqués, profil).
- [x] 2026-10-07 — QML : dossiers de la sidebar, barre de filtres, colonne Type, molette rapide, dialogue de profil, en-tête de page artiste, menus contextuels.
- [x] 2026-10-07 — Script `scripts/clean_orphan_artists.py` (liste, sauvegarde, suppression) exécuté sur la base réelle.
- [ ] Recette interactive de l'utilisateur (clics réels, ressenti de la molette).

## Décisions techniques

- **Migration 020** (`020_artist_enrichment.sql`) : `CREATE TABLE IF NOT EXISTS` identique au script externe `scripts/artist-review-migrations/001_artist_enrichment.sql`, plus `INSERT OR IGNORE` de la version 1 de `artist_enrichment_schema`. L'application ou l'outil de revue peuvent créer la table en premier ; `ReviewDatabase` accepte toujours `[(1,)]`. La version applicative passe de 19 à 20 ; les tests de migration sont mis à jour.
- **Écriture** (`ArtistRepository.save_artist_profile`) : un seul `INSERT … ON CONFLICT DO UPDATE` qui ne touche que décision, rôles, Bass-related, tags et `record_json`. Liens Spotify/SoundCloud, notes, validation et observations sourcées restent intacts ; `record_json` conserve ses clés inconnues. Une nouvelle ligne reçoit `identity_decision = 'accepted'`.
- **Masqué** = tag `idgaf` ou décision `exclude`. Les tags libres n'affichent jamais `idgaf` : c'est l'interrupteur.
- **Modèles** : `catalog` (filtres de l'utilisateur), `catalog.all` (compte de la sidebar) et `catalog.<Producer|DJ|Singer|MC|none>` (dossiers) ; les filtres s'appliquent côté Python, hors thread graphique pour la lecture, avec réinitialisation du modèle au-delà de 40 lignes modifiées pour que filtrer 2 000 artistes reste fluide.
- **Nombre de morceaux** : un minimum unique (« Min tracks »), pas de tranches.
- **Nettoyage** : orphelin = aucune ligne dans `track_artist_credits`. Le script supprime aussi ses observations, alias et ligne d'enrichissement, ignore les violations de clé étrangère préexistantes, garde un orphelin vers lequel un artiste crédité a été fusionné, sauvegarde par l'API SQLite avant d'écrire et vérifie `quick_check`.

## Contrôles effectués

- Tests : `tests/unit/test_artist_profile.py` (normalisation, création et édition de ligne, synchro idgaf/exclude, conservation des champs, adoption de la table d'un autre outil, filtres OU/minimum/recherche, masqués), `tests/unit/test_clean_orphan_artists.py` (liste sans écriture, sauvegarde, suppression, protection des fusions), `tests/ui/test_artist_profile_ui.py` (application réelle sur une base temporaire : dossiers, puces, interrupteur, édition depuis la page artiste), migrations 20. Ruff et format propres sur les fichiers du lot.
- Recette depuis les sources sur une copie cohérente de la base réelle : 1 615 artistes visibles (1 969 avec les masqués), dossiers Producer 1 422 / DJ 1 398 / Singer 154 / MC 91 / No role 17, filtre MC+Singer avec minimum 3 morceaux = 38 artistes ; captures hors écran de la liste, des filtres et d'une page artiste. Aucun avertissement QML.
- Base réelle (`%APPDATA%\MTEE\MTEE\mtee.sqlite3`) : 406 artistes orphelins (383 provisional, 23 retired) supprimés avec 395 observations et 24 lignes d'enrichissement ; sauvegarde `mtee.sqlite3.before-orphan-cleanup-20261007T122958Z.bak` ; `quick_check` ok ; relance de la liste : 0 orphelin. MTEE et le serveur de revue étaient ouverts pendant l'opération ; il faut relancer MTEE. La migration 020 ne s'appliquera à cette base qu'au prochain démarrage de l'application (sauvegarde automatique de version).
- Non vérifié : recette interactive de l'utilisateur, réglage fin de la vitesse de molette (×4 pour la liste, ×3 pour la sidebar), build Windows (non demandé).

## Surprises & Discoveries

- Les 406 orphelins sont des profils bruts de noms non découpés (« Habstrakt Roderick Porter ») restés après la confirmation des crédits, et 23 artistes `retired` ; aucun n'était référencé par une fusion ni un alias ; toutes les pistes de leurs observations ont une revue `confirmed`.
- Le catalogue ne comptait déjà que les artistes crédités sur des fichiers présents : les orphelins étaient invisibles dans la liste, seulement présents en base.
- Échecs de tests existants avant ce lot (non traités) : `test_conversion_queue` (2), `test_icon_provider`, `test_workspace_model::navigation`, `test_analysis_ui::analysis tab` ; trois sont reproduits sur `1b7dd3c`.

## Outcomes & Retrospective

Livré et vérifié depuis les sources ; recette utilisateur et push : voir le commit de clôture.
