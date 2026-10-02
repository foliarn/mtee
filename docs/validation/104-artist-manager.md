# Validation de l'étape 104 — Identification des artistes et Artist manager

Rapport rédigé le 2 octobre 2026 pendant le développement des jalons 104.1 à 104.6 du [plan 104](../../Plans%20d'exécution/104-artist-manager-importation.md). Il distingue ce qui a été exécuté, ce qui a été observé à l'écran hors écran (plateforme Qt `offscreen`) et ce qui reste à faire par l'utilisateur. Aucun paquet Windows n'a été construit (consigne du dépôt et du plan).

## Environnement

Windows 11, Python 3.12.14, PySide6 6.9.3, Mutagen 1.48.1, FFmpeg épinglé de `vendor/ffmpeg` (utilisé uniquement pour fabriquer des fichiers de test), schéma SQLite 19 (`019_artist_manager.sql`). Toutes les données de test sont synthétiques (WAV silencieux ou courts fichiers FFmpeg) dans des dossiers temporaires ou sous `.local/validation/104/`, jamais versionnés.

## Commandes exécutées et résultats

Depuis la racine du dépôt :

    uv run python -m compileall -q src/mtee
    uv run pytest -q tests/unit/test_artist_manager_contract.py
    uv run python -m mtee --data-dir .local/validation/104/smoke --smoke-test
    uv run python scripts/validate_artist_manager_104.py

La compilation réussit. Le test de contrat (une fonction paramétrée, 16 familles de cas) réussit. Le smoke test sort avec le code 0. Le script `scripts/validate_artist_manager_104.py` charge la fenêtre réelle hors écran sur une petite bibliothèque synthétique et vérifie que chaque composant ajouté est effectivement instancié, y compris ceux qui sont derrière un `Loader` (panneau latéral, pages de revue, catalogue, page artiste, trois dialogues) : zéro avertissement QML avant la fermeture. Le message `QFontDatabase: Cannot find font directory` de la plateforme hors écran est ignoré par le script, il ne vient pas de MTEE.

`ruff check` et `ruff format` passent sur les fichiers ajoutés. Les lignes trop longues déjà présentes dans `media_probe.py`, `trash_service.py` et `library_repository.py` (ligne `mark_recycled`) sont antérieures au lot.

Les tests de migration (`test_database_migrations.py`, `test_playback_repository.py`) attendaient la version 18 comme dernière ; leurs listes ont été actualisées pour la version 19. Le reste de la suite a été exécuté fichier par fichier : les échecs observés (`test_icon_provider` pour l'icône `heart`, `test_workspace_model` navigation, `test_conversion_queue`, `test_playlist_exchange`, plusieurs fichiers `tests/ui/`) existent à l'identique sur une copie propre de `HEAD` (vérifié sur un `git worktree`) et ne sont pas liés à ce lot. La suite `tests/ui` complète plante dans cet environnement (violation d'accès Qt), avec ou sans ce lot ; elle a donc été lancée par fichier.

## Ce que le test de contrat couvre réellement

Les écritures se font sur des copies temporaires, avec la vraie base, les vrais dépôts, le vrai service d'application des fichiers et le vrai écrivain de tags ; seul le décodeur audio de l'analyse est remplacé.

| Famille | Contrôlé |
|---|---|
| Métadonnées multiples | `A+`, `Ev & MPH` : trois profils distincts dans l'ordre, catégorie `from_tags`, aucune validation automatique, hash du fichier inchangé, aucun artiste établi avant confirmation. |
| Séparateurs | `X x Y`, `Jay-Z feat. Kid` restent un seul nom ; `Smith, John` saisi dans Edit reste littéral et survit à une nouvelle identification. |
| Graphies | `mph`, `MPH`, `Mph` → un profil `MPH` ; `Skream`/`skream` regroupés, `Skrem` non fusionné ; renommage manuel prioritaire et ancien nom rattaché par alias. |
| Préfixes | Nom inconnu en casse mixte proposé ; `01 - …`, absence de séparateur, titre sans caractère lisible → à renseigner, non confirmable. |
| Remix, flip, bootleg | Version conservée dans le titre ; original puis remixer ; remixer seul sans original ; pas de doublon ; `(Remix)` sans nom n'invente rien ; crochets et `&`. |
| Analyse | Audio à jour mais revue absente : traité sans décodage ; annulation puis reprise ; `force=True` ne touche ni correction ni version de décision. |
| Navigation | Mode guidé persistant, filtre qui masque tout sans terminer la catégorie, déblocage ordonné, catégorie vide terminée, fin du parcours puis mode libre même après suppression de tous les artistes, base déjà peuplée libre. |
| Lots | UUID exacts du filtre, `N artists · M tracks` sans doubles comptes, rejet d'une décision devenue obsolète, lignes masquées intactes. |
| Noms de fichiers | WAV, MP3, FLAC, AIFF, AIF, M4A (AAC), OGG, Opus : renommage `Artiste, Artiste - Titre.ext`, hash identique case tags vide, caractères Windows remplacés, no-op sur nom conforme, collisions `(2)`, `(3)`, `(5)` en évitant un fichier hors catalogue. |
| Tags facultatifs | Mêmes huit formats : artiste et titre relus, tag inconnu et pochette conservés. |
| Opérations artistes | Rename, Merge, Delete, coartistes conservés, dernier artiste retiré → `Needs input` sans fichier ` - Titre`. |
| Undo | Restauration du nom, des tags et de la décision ; fichier modifié depuis → conflit sans écrasement. |
| Échecs | Source modifiée, fichier en lecture par le lecteur, erreur après les tags (reprise sans réécrire les tags), erreur après le renommage (reprise sans second suffixe). |
| Catalogue | Compteurs par morceau distinct, tri alphabétique, lignes de la page artiste dans l'ordre des fichiers. |

## Limites par format et décisions de conception prises pendant l'exécution

Le crédit est écrit comme **une seule valeur** `Artiste A, Artiste B` (`serialize_artists`) dans les formats testés ; relu puis découpé sur virgule et `&`, il redonne les mêmes noms. L'ordre et les UUID restent dans la base. L'écrivain existant refusait d'éditer un champ qui contient plusieurs valeurs ; un patch de crédit (`MetadataPatch.from_credit`, `replace_aliases=True`) autorise désormais le remplacement des champs artiste et titre pour ID3 et MP4 (FLAC, Ogg et Opus le permettaient déjà). L'extension `.aif` est désormais reconnue par l'adaptateur ID3 (elle l'était pour la lecture seulement) et vérifiée sur une copie. M4A est vérifié en AAC ; l'ALAC, l'ADTS et les WAV non PCM restent refusés ou non vérifiés dans ce lot : un format sans capacité d'écriture donne `Tags not written: …` visible sur la ligne et le renommage a lieu quand même.

Autres décisions : le verrou d'un morceau est pris deux fois, séparément (écrivain de tags, puis renommage), jamais imbriqué ; un lecteur qui a le fichier ouvert fait échouer l'élément avec `The file is playing or in use` et l'élément reste en file ; l'annulation ciblée couvre les confirmations, pas les opérations Rename/Merge/Delete d'artiste ; l'onglet Artists et les pages artiste ne sont pas restaurés au redémarrage (comme Settings, Convert et Tasks) ; un artiste renommé garde son ancien nom en alias pour les futures importations ; le remixer est ajouté au crédit aussi quand les tags donnent déjà l'artiste.

Un défaut visuel réel a été trouvé et corrigé pendant l'observation : `reuseItems` laissait des lignes de l'onglet précédent dans la liste de revue.

## Observation à l'écran (hors écran, non native)

Le script a produit et lu les captures dans `.local/validation/104/ui/` : panneau latéral vide avec `Analyze collection`, état vide, `From tags` après analyse, `Suggested` verrouillé puis ouvert après confirmation, dialogues Edit, Confirm et Merge, catalogue Artists, page d'un artiste. L'ordre de confirmation et les noms obtenus ont été contrôlés sur disque. La couverture arrondie de la page artiste (MultiEffect) ne se rend pas sur le moteur logiciel hors écran, comme pour la page playlist.

## Non observé, à faire par l'utilisateur

Recette interactive sur la vraie collection depuis les sources : lancer `Analyze collection`, parcourir les trois catégories dans l'ordre, corriger avec Edit (suggestions d'artistes, ajout et retrait de lignes), confirmer le nombre annoncé avec puis sans `Also update file tags`, vérifier les noms obtenus, tester un fichier en cours de lecture, Rename/Merge/Delete d'un artiste, `Undo the last confirmation`, la page d'un artiste et la lecture depuis cette page. Non mesuré : durée d'inscription et fluidité des listes sur plusieurs milliers de morceaux ; aucun test UI automatisé n'a été ajouté (consigne du plan). Navigation clavier des suggestions d'artistes (flèches) non implémentée : seules la souris et la saisie filtrent la liste.
