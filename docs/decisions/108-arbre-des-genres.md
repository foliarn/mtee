# 108 — Arbre des genres, genre manager et workflow de tri

Dossier de revue du 7 octobre 2026, première étape du vocabulaire prévu par `PLAN.md` §4.8 et le [plan 10](../../Plans%20d'exécution/10-tags-recherche-playlists.md). Rien n'est encore implémenté. Les genres posés par le [plan 107](../../Plans%20d'exécution/107-genres-depuis-les-dossiers.md) sur les artistes sont un brouillon que ce vocabulaire remplace.

**Garantie** : « retirer », « renommer » et « séparer » portent sur la taxonomie créée ici. Aucun fichier ni dossier de `foliarn/` n'est créé, déplacé, renommé, écrit ou supprimé ; les dossiers servent seulement de point de départ en lecture.

## Décisions de l'utilisateur (7 octobre 2026)

- Un genre principal peut être un sous-genre : « si le son est speed garage, il est UKG ». La famille se déduit.
- Un morceau a **un genre principal obligatoire**, puis des sous-genres. Les **hybrides** (jump up / minimal) sont une fonction à part entière, pour les morceaux et les artistes.
- Méta-familles à part de l'arbre ; « Commercial » est abandonné. Tags personnalisés (Banger, Calm, Euphoric…) hors des métadonnées des fichiers.
- Création à la volée et **genre manager** complet : créer, renommer, déplacer, supprimer genres, sous-genres, méta-familles et tags.
- Deux modes de tri : par lot, sur une page dédiée, et sélectif (page, artiste, sélection). L'utilisateur ne connaît pas tous les artistes et morceaux de tête : il doit pouvoir chercher et écouter pendant qu'il trie.
- Les puces de genre du plan 107 sur les artistes seront retirées quand les genres de morceaux existeront (sauvegarde, réversible).

## Arbre (v1)

- **House** : Tech, Bass, Minimal, Deep, Disco, French
- **UK Garage** : Speed Garage, 2-Step, Bassline
- **Drum & Bass** : Jump Up, Neuro, Liquid, Drumstep, Rollers, Jungle, Minimal, Dancefloor, 4x4
- **Dubstep** : Deep, Tearout, Riddim, Brostep, Trap, plus un style britannique à nommer (voir questions)
- **Techno** : Minimal, Hardgroove, Hard House, Bouncy Techno (alias Nu Trance), Trance
- **Hard Dance** : Hardstyle, Rawstyle, Uptempo, Hard Techno
- **Dance**, **Breaks**, **Baile**, **Rap**, **Future Bass**, **Pop**, **Rock**, **Jazz**, **Classical** : familles, sous-genres à venir
- Un sous-genre appartient à une seule famille ; le même libellé peut exister sous plusieurs familles (Minimal sous House, Techno et Drum & Bass), comme des nœuds distincts affichés avec leur famille.

Méta-familles proposées : **Bass Music** (UK Garage, Dubstep, Drum & Bass, Bass House, Baile), **Hard** (Hard Dance, Hard House, Hardgroove), **Club** (House, Techno, UK Garage).

## Modèle

- **Genres** : arbre avec identifiants stables distincts des libellés ; un renommage garde les affectations ; archivage plutôt que suppression silencieuse ; alias (anciens noms de dossiers, `Nu Trance`).
- **Méta-familles** : regroupements transversaux d'une famille ou d'un sous-genre, plusieurs possibles ; un morceau en hérite par ses genres, jamais affectées directement.
- **Genres d'un morceau** : une liste ordonnée, dont le premier est le principal obligatoire ; la famille est celle de ses ancêtres. Un morceau sans principal est « À classer ». Un hybride est un morceau (ou un artiste) à plusieurs sous-genres affiché « Jump Up / Minimal » ; une recherche sur l'un ou l'autre le trouve.
- **Tags personnalisés** : liste libre de l'utilisateur, hors des métadonnées des fichiers et hors des genres. Stockés dans la base de MTEE uniquement.
- **Artistes** : leurs genres sont un agrégat calculé (genres et nombre de morceaux) ; les actions de tri par artiste appliquent des genres à ses morceaux.
- **Point de départ** : chaque dossier propose un principal et des sous-genres (tableau ci-dessous) avec la provenance « dossier », confirmés par lot. Un morceau n'est que dans un dossier : un second genre (Yosemite : Speed Garage et Hard House) se choisit à la main.

## Workflow de tri proposé

Un seul geste suffit à classer, quel que soit l'endroit.

- **Palette de genres** : une saisie qui filtre l'arbre en tapant (`spe` → Speed Garage), Entrée applique comme principal, Maj+Entrée ajoute un sous-genre ou un hybride, un genre inexistant propose « Créer … » sur place. Les derniers genres utilisés restent en tête, avec des raccourcis 1 à 9.
- **Page Genres (tri par lot)** : liste de morceaux à classer au centre, filtrable (dossier d'origine, artiste, BPM, sans genre, proposition non confirmée), palette à droite. Un clic sur une ligne la joue immédiatement et Espace lit/pause ; la sélection multiple (clic, Maj, Ctrl) puis un genre classe tout le lot ; « Suivant à classer » enchaîne la lecture. Chaque ligne affiche artiste, titre, BPM, la proposition du dossier, et les genres déjà connus de l'artiste pour guider celui qui ne connaît pas le morceau. Les propositions de dossier se confirment par groupe en une action.
- **Tri sélectif** : le même panneau, depuis le clic droit d'une sélection de morceaux, le panneau Info d'un morceau, la page ou la liste d'un artiste (« Genres… »), la liste des artistes. Pour un artiste, l'action s'applique à ses morceaux sans genre confirmé ; l'écraser demande une option explicite et le nombre de morceaux touchés est affiché avant.
- **Genre manager** : une vue en arbre où l'on crée, renomme, glisse un sous-genre vers une autre famille, fusionne ou supprime un genre (avec le nombre de morceaux touchés et une cible de fusion), gère les méta-familles et les tags.

## Point de départ par dossier

Compté sur les 2 813 morceaux de `foliarn` (lecture seule). Le principal est le nœud le plus précis connu.

| Dossier | Morceaux | Principal | Sous-genres proposés |
|---|---|---|---|
| d&b / jump up | 478 | Jump Up | |
| d&b / minimal - dark | 92 | Minimal (Drum & Bass) | |
| d&b / washed up | 72 | Drum & Bass | retiré |
| d&b / liquid | 48 | Liquid | |
| d&b / le reste | 47 | Drum & Bass | retiré |
| d&b / neurofunk | 42 | Neuro | |
| d&b / dancefloor | 30 | Dancefloor | |
| d&b / 4x4 | 12 | 4x4 | |
| d&b / drumstep | 6 | Drumstep | |
| ukg - speed garage & bangers | 262 | Speed Garage | |
| ukg - chill | 195 | UK Garage | retiré (pas un genre) |
| ukg - slow bangers | 103 | UK Garage | retiré (pas un genre) |
| ukg - 2step | 85 | 2-Step | |
| ukg - bassline | 37 | Bassline | |
| dubstep 140 | 206 | Dubstep | style britannique ? |
| dubstep (le reste) | 49 | Dubstep | |
| dubstep cool | 31 | Dubstep | |
| nu trap | 24 | Trap (Dubstep) | |
| house | 202 | House | |
| tech house | 25 | Tech (House) | |
| bass house | 14 | Bass (House) | |
| hard house - nu trance - bouncy stuff | 77 | Hard House | Bouncy Techno |
| hardgroove | 84 | Hardgroove | |
| techno min cool | 36 | Minimal (Techno) | |
| hard techno | 88 | Hard Techno | |
| hard,rawstyle | 8 | Hardstyle | Rawstyle, Uptempo |
| techno, trance | 39 | Techno | Trance |
| breaks - jungle | 75 | Jungle ? | Breaks ? |
| baile | 25 | Baile | |
| rap | 16 | Rap | |
| dance | 54 | Dance | |
| future | 5 | Future Bass | |
| pop | 5 | Pop | |
| chill&atmospheric | 23 | À classer | retiré |
| old school | 16 | À classer | retiré |
| zzZ, Artists, dj blc | 97, 75, 30 | À classer | dossiers qui ne sont pas des genres |

Au départ 241 morceaux sont à classer à la main (39 par les retraits, 202 dans les dossiers qui ne sont pas des genres).

## Questions ouvertes

1. Le style de dubstep britannique (Hamdi, Taiki Nulight) : quel nom de sous-genre, par exemple « 140 » ou « UK » ? C'est ce sous-genre qui recevrait le dossier `dubstep 140`.
2. Hybrides : le premier genre de la liste reste le principal (pour le tri et l'agrégat) mais l'affichage et les filtres traitent « Jump Up / Minimal » comme à parts égales. Est-ce l'effet voulu ?
3. `breaks - jungle` : Jungle en principal (sous Drum & Bass) avec Breaks en second, ou l'inverse ?
4. Tri par artiste : appliquer seulement à ses morceaux sans genre confirmé (écraser sur demande), et un remix d'un tiers reçoit-il le genre de l'artiste ou seulement celui de son dossier ?
5. Supprimer un genre utilisé : proposer une fusion vers un autre genre, ou accepter de laisser les morceaux « À classer » ?
