# Étape 107 — Premier jet : genres depuis les dossiers

ExecPlan du 7 octobre 2026, selon `PLANS.md`. Premier tri par genre, avant la revue du vocabulaire des tags : les artistes reçoivent comme puce (tag d'artiste du [plan 106](106-artistes-types-filtres-masques.md)) le genre déduit du dossier de leurs morceaux. Aucun fichier audio n'est lu ni écrit.

## Décisions de l'utilisateur

- Racine lue : `foliarn` (le dossier `mixs` n'est pas lu). Un dossier de premier niveau donne un genre, un sous-dossier donne un second genre (`d&b/jump up` donne `Drum & Bass` et `Jump Up`).
- `d&b` devient `Drum & Bass` ; les autres noms sont repris avec des majuscules (`hard techno` → `Hard Techno`, `ukg` → `UKG`).
- Remix, bootleg, flip, edit, rework, refix, mashup, VIP : seul le remixeur reçoit le genre. Remixeur introuvable parmi les crédits : personne n'est tagué, le morceau est listé.
- Dossiers ignorés par défaut : `zzZ`, `Artists`, `foliarn`, `dj blc` (modifiable avec `--ignore`).
- Pas de seuil de morceaux dans ce premier jet. Les noms bruités (`Dubstep (Le Reste)`, `Neurofunk (Je Crois)`) sont repris tels quels, leur nettoyage relève de la revue du vocabulaire.

## Progress

- [x] 2026-10-07 — Lire la structure : 2 813 morceaux dans `foliarn`, 31 dossiers, 319 artistes dans plusieurs dossiers ; chiffrer les marqueurs de remix.
- [x] 2026-10-07 — `domain/folder_genres.py`, `services/folder_genre_service.py`, `ArtistRepository.set_folder_genres`, `scripts/genres_from_folders.py` (rapport, sauvegarde, application).
- [x] 2026-10-07 — Rapport produit (`.local/validation/107/`, ignoré par Git), puis application sur la base réelle après l'accord « vas-y ».
- [ ] Revue du rapport par l'utilisateur ; recette dans MTEE (sidebar, page artiste).

## Décisions techniques

- **Origine du remixeur** : les crédits `remixer` de la base quand ils existent (292 morceaux) ; sinon les marqueurs `(Nom Remix)` lus dans le titre confirmé, le titre d'origine et le nom de fichier. Un marqueur absent du titre final mais retrouvé dans les autres sources est signalé (6 cas dans la collection actuelle, ce qui rejoint les cas rencontrés par l'utilisateur).
- **Rapprochement** nom du marqueur / crédit par mots entiers : `Zero's Brace Position` contient `Zero`, `CODE PANDORUM x CASTER` contient `Code:Pandorum` et `CASTER`, `Jaybee` retrouve `Jaybee (UK)`, `Pola & Bryson` n'est pas aussi lu `Pola`. Un marqueur de style seul (`Jungle VIP`, `DJ Edit`, `Drum and Bass Remix`) ou sans nom (`VIP`, `Extended Mix`) ne désigne personne : l'artiste d'origine garde le morceau.
- **Stockage** dans `artist_enrichment_reviews.tags_json` ; `record_json` garde `genre_sources` (nombre de morceaux par genre) et `genre_added` (puces ajoutées par le script). Un nouveau passage retire exactement `genre_added`, jamais une puce tapée par l'utilisateur, même identique à un genre. Rôles, Bass-related, décision, `idgaf`, liens, notes et observations ne bougent pas.
- La longueur maximale d'une puce passe de 40 à 64 caractères (`Dance (Electronica - Kaytra - French Touch)` fait 43).

## Contrôles effectués

- Tests : `tests/unit/test_folder_genres.py` (noms, dossiers, marqueurs, règle du remixeur, plan sur une bibliothèque temporaire, application, conservation des puces de l'utilisateur, nouveau passage) et `tests/unit/test_artist_profile.py` ; Ruff et format propres.
- Base réelle : 2 813 morceaux lus, 36 genres, **1 603 artistes** reçoivent au moins un genre (Drum & Bass 453, Jump Up 249, House 212…), 52 remix à remixeur introuvable laissés sans puce (`unresolved-remixes.csv`), 14 morceaux sans crédit ignorés ; sauvegarde `mtee.sqlite3.before-folder-genres-20261007T125907Z.bak` ; `quick_check` ok ; les 354 artistes masqués le restent. MTEE et le serveur de revue étaient ouverts.
- Non vérifié : affichage dans MTEE (la liste montre les types, pas encore les puces de genre), build Windows (non demandé).

## Surprises & Discoveries

- Le gros des cas non résolus est un `Edit` d'un tiers non crédité (`(Jayfor Edit)`) : le remixeur n'a jamais été dans les crédits, ce qui correspond au constat de l'utilisateur sur les artistes disparus. Les créer comme artistes les rendrait taguables ; non fait sans demande.
- Les sous-dossiers de `d&b` (`4x4`, `Dancefloor`, `Washed Up`…) deviennent des genres autonomes ; à regrouper à la revue du vocabulaire.

## Outcomes & Retrospective

Premier jet appliqué ; recette utilisateur et push : voir le commit de clôture.
