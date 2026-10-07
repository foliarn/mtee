# 108 — Arbre des genres : proposition à valider

Dossier de revue du 7 octobre 2026, première étape du vocabulaire prévu par `PLAN.md` §4.8 et le [plan 10](../../Plans%20d'exécution/10-tags-recherche-playlists.md). Rien n'est implémenté : ce document propose, l'utilisateur tranche. Les genres posés par le [plan 107](../../Plans%20d'exécution/107-genres-depuis-les-dossiers.md) sur les artistes sont un brouillon que ce vocabulaire remplace.

**Garantie** : « retirer », « renommer » et « séparer » portent sur la taxonomie créée ici. Aucun fichier ni dossier de `foliarn/` n'est créé, déplacé, renommé, écrit ou supprimé ; les dossiers servent seulement de point de départ en lecture.

## Modèle proposé

- **Famille** : un nœud sans parent (House, UK Garage…). **Sous-genre** : un nœud sous une famille (Speed Garage sous UK Garage). Un sous-genre peut apparaître sous une seule famille ; l'arbre n'a que ces deux niveaux au départ, la structure accepte plus.
- **Un genre principal obligatoire par morceau**, n'importe quel nœud : « Speed Garage » est un principal valide, sa famille (UK Garage) s'en déduit. Puis **zéro ou plusieurs sous-genres** : Yosemite = principal Speed Garage, plus Hard House. Un morceau sans principal est « À classer » ; il ne reçoit jamais de principal deviné.
- **Méta-familles** (Bass Music, Hard, Commercial…) : des regroupements transversaux, à part de l'arbre. Une famille ou un sous-genre peut appartenir à plusieurs méta-familles, et un morceau en hérite par ses genres. Elles ne s'affectent jamais à un morceau directement.
- **Tags personnalisés** (Banger, Calm, Euphoric…) : une liste libre créée et nommée par l'utilisateur, distincte des genres. Stockés dans la base de MTEE uniquement ; MTEE ne les écrit jamais dans les métadonnées des fichiers (le champ Genre des fichiers n'est pas non plus modifié sans demande séparée).
- Identifiants stables distincts des libellés : renommer un genre garde ses affectations. Les anciens noms de dossiers deviennent des alias pour la reprise.
- Les genres vivent sur les **morceaux**, pas sur les artistes. Les genres d'un artiste seront un agrégat calculé, avec le nombre de morceaux. Cela règle aussi le cas des remix : un remix est un morceau, son genre est celui de son dossier, sans avoir à choisir entre original et remixeur.
- Départ : chaque dossier propose un principal et des sous-genres (tableau ci-dessous) avec la provenance « dossier », confirmés par lot comme pour les artistes. Un morceau n'est que dans un dossier : un second genre (Yosemite) se choisit à la main.

## Arbre proposé (v0)

Les termes marqués ? sont des questions ouvertes.

- **House** : Tech House, Bass House
- **UK Garage** : Speed Garage, 2-Step, Bassline
- **Drum & Bass** : Jump Up, Neurofunk, Liquid, Drumstep, Jungle ?, Minimal - Dark ?, Dancefloor ?, 4x4 ?
- **Dubstep** : 140 ?
- **Techno** : Minimal, Hardgroove, Hard House, Bouncy Techno, Hard Techno ?
- **Hard Dance** : Hardstyle, Rawstyle, Uptempo
- **Pop**, **Rock**, **Jazz**, **Classical** : aucun sous-genre observé
- **?** à placer : Breaks, Trap, Baile, Rap, Dance (electronica, french touch), Future, Trance

Méta-familles proposées (une famille ou un sous-genre peut être dans plusieurs) : **Bass Music** (UK Garage, Dubstep, Drum & Bass, Bass House, Trap, Baile ?), **Hard** (Hard Dance, Hard House, Hard Techno, Hardgroove), **Commercial** (Pop, Dance), **Club** (House, Techno, UK Garage).

## Point de départ par dossier

Compté sur les 2 813 morceaux de `foliarn` (lecture seule). Le principal est le nœud le plus précis connu ; sa famille s'en déduit.

| Dossier | Morceaux | Principal | Sous-genres proposés |
|---|---|---|---|
| d&b / jump up | 478 | Jump Up | |
| d&b / minimal - dark | 92 | Drum & Bass | Minimal - Dark ? |
| d&b / washed up | 72 | Drum & Bass | retiré |
| d&b / liquid | 48 | Liquid | |
| d&b / le reste | 47 | Drum & Bass | retiré |
| d&b / neurofunk | 42 | Neurofunk | |
| d&b / dancefloor | 30 | Drum & Bass | Dancefloor ? |
| d&b / 4x4 | 12 | Drum & Bass | 4x4 ? |
| d&b / drumstep | 6 | Drumstep | |
| ukg - speed garage & bangers | 262 | Speed Garage | |
| ukg - chill | 195 | UK Garage | retiré (pas un genre) |
| ukg - slow bangers | 103 | UK Garage | retiré (pas un genre) |
| ukg - 2step | 85 | 2-Step | |
| ukg - bassline | 37 | Bassline | |
| dubstep 140 | 206 | Dubstep | 140 ? |
| dubstep (le reste) | 49 | Dubstep | |
| dubstep cool | 31 | Dubstep | |
| house | 202 | House | |
| tech house | 25 | Tech House | |
| bass house | 14 | Bass House | |
| hard house - nu trance - bouncy stuff | 77 | Hard House | Bouncy Techno ; Nu Trance ? |
| hardgroove | 84 | Hardgroove | |
| techno min cool | 36 | Minimal | |
| hard techno | 88 | Hard Techno | famille Techno ou Hard Dance ? |
| hard,rawstyle | 8 | Hardstyle | Rawstyle, Uptempo |
| techno, trance | 39 | Techno | Trance ? |
| breaks - jungle | 75 | Breaks ? | Jungle ? |
| nu trap | 24 | Trap ? | |
| baile | 25 | Baile ? | |
| rap | 16 | Rap ? | |
| dance | 54 | Dance ? | |
| future | 5 | Future ? | |
| pop | 5 | Pop | |
| chill&atmospheric | 23 | À classer | retiré |
| old school | 16 | À classer | retiré |
| zzZ, Artists, dj blc | 97, 75, 30 | À classer | dossiers qui ne sont pas des genres |

Conséquence des retraits : 39 morceaux (chill&atmospheric, old school) n'ont plus aucun genre et attendent un classement manuel ; 119 morceaux de Drum & Bass (washed up, le reste) et 298 d'UK Garage (chill, slow bangers) gardent la famille de leur dossier ; 202 morceaux d'`Artists`, `zzZ` et `dj blc` restent À classer, ces dossiers n'étant pas des genres. Au total 241 morceaux sont À classer à la main au départ.

## Questions ouvertes

1. Un genre principal peut-il être un sous-genre (Speed Garage) avec la famille déduite ? (proposé : oui)
2. Hard House est sous Techno dans ton arbre : Hard Techno aussi, ou sous Hard Dance ? Que devient « Nu Trance » (retiré ou sous-genre) et « Bouncy Techno » a-t-il d'autres compagnons que tu voulais lister ?
3. « Dubstep 140 » : sous-genre « 140 » ou simple Dubstep ? Y a-t-il d'autres sous-genres de Dubstep à créer ?
4. Sous-dossiers de Drum & Bass : Minimal - Dark, Dancefloor, 4x4 sont-ils des sous-genres ou, comme « chill », des étiquettes à retirer ? Où va Jungle (sous Drum & Bass, ou famille à part avec Breaks) ?
5. Familles à créer pour Trap, Baile, Rap, Dance, Future, Trance, ou elles restent sous « ? » ?
6. « Techno, trance » : les deux (Techno principal, Trance en sous-genre) ?
7. Méta-familles : la liste proposée convient-elle, et que mets-tu dans « Commercial » ?
8. Les puces de genre posées sur les artistes par le plan 107 : les retirer quand les genres de morceaux existeront (réversible, sauvegarde) ?
