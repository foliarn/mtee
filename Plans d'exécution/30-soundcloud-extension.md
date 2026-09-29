# 30 — Extension Chrome de capture SoundCloud

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il réalise l'extension définie par le [cadrage 29](29-soundcloud-cadrage.md) et les décisions de `docs/decisions/29-soundcloud-capture.md`. Il commence après les jalons 29.1 (voies observées) et 29.2 (mécanismes du manifeste et des archives retenus).

## Objectif et résultat observable

Sur une page de morceau SoundCloud, un bouton `Download` apparaît à côté des actions du morceau. Son libellé secondaire indique la voie détectée : `Direct`, `Droploud`, `Hypeddit`, `Bandcamp`, ou le bouton est grisé avec `No free download`. Sur une page de playlist, `Download playlist` met en file tous les titres offrant une voie prise en charge et indique combien n'en ont pas.

Un clic ouvre la passerelle dans un onglet suivi. L'extension remplit les champs depuis le profil de formulaire, exécute les étapes exigées et attend l'utilisateur pour un consentement OAuth ou un CAPTCHA. Elle déclenche ensuite le téléchargement final et enregistre les fichiers audio dans `Downloads/Songs/`, archives `.zip` extraites. Une fois le téléchargement réussi, elle revient sur la page SoundCloud du morceau pour liker, reposter et commenter si ce n'est pas déjà fait, selon les options.

La popup liste les téléchargements récents et leur état : `Queued`, `Waiting for you`, `Downloading`, `Extracting`, `Waiting for email`, `Supporting`, `Done`, `Failed`. Chaque ligne indique le résultat des actions de soutien (`Liked`, `Reposted`, `Commented`, `Already`, `Skipped`) et propose, selon l'état, `Retry`, `Open gate`, `Open track` ou `Show in folder`. Pendant un lot, la popup montre la progression et permet `Pause` et `Cancel`.

La page d'options permet de gérer :

- les **profils de formulaire** : e-mail, prénom, nom, pays, code postal et champs libres nom/valeur, avec un profil par défaut ;
- la **liste des commentaires** : ajout, modification, suppression et activation de chaque texte, avec les variables `{artist}` et `{title}` ;
- les **actions de soutien** : like, repost et commentaire activables séparément, délai minimal et maximal entre actions, plafond quotidien ;
- les **étapes de passerelle** : `Auto` ou `Ask` pour follow, like, repost et commentaire exigés ;
- les **téléchargements** : nom du sous-dossier (par défaut `Songs`), format Bandcamp préféré, extraction des archives, conservation de la pochette, manifeste de provenance ;
- l'**historique** : consultation, export JSON, effacement.

L'interface est en anglais. L'extension fonctionne sans MTEE.

## Contexte et prérequis

Lire `AGENTS.md`, `PLANS.md`, le plan 29, `docs/decisions/29-soundcloud-capture.md` et `docs/integrations/soundcloud-capture.md`. Seules les voies marquées `observé` au jalon 29.1 sont développées ; les autres sont affichées comme non prises en charge.

Vocabulaire : une **voie** (« route ») est le moyen de téléchargement d'un morceau ; une **passerelle** (« gate ») est la page tierce qui conditionne ce téléchargement ; une **capture** est la tentative pour un morceau, de la détection aux actions de soutien, identifiée par `capture_id` ; un **lot** est l'ensemble des captures créées depuis une playlist.

Manifest V3 impose un service worker non persistant : l'état des captures et des lots est conservé dans `chrome.storage.local` et reconstruit au réveil. Les scripts de contenu échangent avec lui des messages typés. Les données personnelles (profils, commentaires, historique) restent dans `chrome.storage.local`, jamais dans `storage.sync`, les journaux, les manifestes ou le dépôt.

## Plan de travail et jalons

### Jalon 30.1 — Maquette de l'interface

Produire `docs/ux/soundcloud-capture-mockup.html` avec données fictives : bouton injecté dans ses états (morceau et playlist), popup avec une capture par état et un lot en cours, page d'options avec ses six sections. Reprendre la palette Acid et Geist Sans de `docs/ux/specification.md` pour la popup et les options. Le bouton injecté reste sobre et cohérent avec SoundCloud. Présenter la maquette et consigner la décision dans `docs/decisions/29-soundcloud-capture.md` avant le code d'interface. Les jalons 30.2 et 30.3 peuvent avancer en parallèle.

### Jalon 30.2 — Squelette, modules purs et tests

Créer `extensions/soundcloud-capture/` :

    extensions/soundcloud-capture/
      manifest.json               MV3, version, permissions minimales
      background.js               service worker : captures, lots, téléchargements, manifestes
      offscreen.html/.js          si retenu en 29.2 : extraction d'archive, blobs du manifeste
      lib/routes.js               classification d'URL : SoundCloud, gate.sc, passerelles
      lib/capture.js              création et validation du manifeste mtee.capture/1
      lib/filenames.js            assainissement des noms Windows
      lib/state.js                machine d'états, persistance storage.local
      lib/comments.js             tirage, variables {artist}/{title}, rotation
      lib/pacing.js               délais aléatoires, plafond quotidien
      lib/settings.js             schéma et migration des options
      content/soundcloud.js       détection, bouton, lots de playlist
      content/support.js          like, repost, commentaire sur la page du morceau
      content/gates/droploud.js   automate de passerelle
      content/gates/hypeddit.js
      content/gates/bandcamp.js
      content/selectors.js        sélecteurs par site, versionnés, seul endroit à ajuster
      vendor/                     bibliothèque d'extraction zip retenue, avec sa licence
      popup/  options/            HTML, CSS, JS
      tests/                      node:test et fixtures synthétiques

Permissions : `downloads`, `storage`, `offscreen` si retenu, `tabs` si le suivi d'onglets l'exige. `host_permissions` limitées à `https://soundcloud.com/*`, `https://gate.sc/*`, `https://droploud.com/*`, `https://hypeddit.com/*`, `https://*.bandcamp.com/*` et aux hôtes de fichiers observés en 29.1. Les domaines personnalisés Bandcamp passent par `optional_host_permissions`, demandés à l'utilisateur au moment voulu. Aucun `<all_urls>`.

La bibliothèque d'extraction (par exemple fflate, sous licence MIT) est choisie en 29.2. Elle est copiée dans `vendor/` avec sa version et sa licence, puis ajoutée à `THIRD_PARTY_NOTICES.md` ; aucun gestionnaire de paquets n'est introduit pour ce seul fichier.

Tests `node --test` des modules `lib/` :

- décodage des liens `gate.sc` et rejet des domaines imitant un nom, par exemple `hypeddit.com.evil.example` ;
- assainissement des noms : caractères interdits Windows, noms réservés (`CON`, `NUL`…), longueur, points finaux, chemins sortants dans les archives ;
- transitions d'états autorisées et reprise après redémarrage ;
- manifeste valide et sans champ sensible ;
- tirage des commentaires : liste vide, textes désactivés, variables absentes, pas de répétition immédiate ;
- délais et plafond quotidien, y compris le changement de jour.

### Jalon 30.3 — Détection sur SoundCloud et lots de playlist

`content/soundcloud.js` suit la navigation de l'application monopage : changements d'historique, et `MutationObserver` borné au conteneur principal. Sur une page de morceau, il cherche dans l'ordre le téléchargement natif, le lien d'achat vers une passerelle reconnue, puis un lien de passerelle dans la description. La détection lit la page affichée, sans requête réseau.

Sur une page de playlist, `Download playlist` fait défiler la liste jusqu'au chargement de tous les titres. Il lit pour chacun le lien du morceau et, si la page de playlist ne suffit pas, ouvre la page du morceau dans l'onglet de travail pour détecter sa voie. Il crée ensuite une capture par titre admissible. Les titres déjà téléchargés d'après l'historique sont ignorés par défaut, avec l'option de les inclure. La file est séquentielle : une seule passerelle ouverte à la fois, avec un délai entre deux titres. Un titre en `Waiting for you` bloque la file jusqu'à action de l'utilisateur, ou est mis de côté si l'utilisateur clique `Skip`. Les pages de likes n'ont pas de commande de lot.

Un sélecteur introuvable produit un diagnostic dans la popup (`SoundCloud layout not recognised`) et ne casse pas la page.

### Jalon 30.4 — Automates de passerelle

Un automate par passerelle, piloté par le service worker, ne s'exécute que dans un onglet ouvert par une capture, et seulement pendant celle-ci. Chaque automate décrit les étapes observées en 29.1 sous forme déclarative : détection de l'étape, action, condition de fin. Il remplit les champs depuis le profil choisi et réalise en `Auto` les follow, like, repost et commentaire exigés (commentaire tiré de la liste). Il met en évidence et attend les étapes en `Ask`, les consentements OAuth et les CAPTCHA, puis clique sur le bouton final. Chaque étape a un délai d'attente ; au-delà, la capture passe à `Waiting for you` au lieu d'échouer. L'utilisateur peut toujours reprendre l'onglet à la main ; l'automate constate l'avancement sans refaire l'étape. Les étapes réalisées sont notées dans `route.steps` pour éviter de les répéter en soutien.

Bandcamp : pour une sortie livrée par e-mail, la capture passe à `Waiting for email`. Quand l'utilisateur ouvre le lien reçu dans Chrome, le script de la page de téléchargement Bandcamp rattache la page à la capture par l'URL de la sortie. Il choisit le format préféré (par défaut FLAC s'il est proposé, sinon MP3 320) et poursuit.

### Jalon 30.5 — Téléchargement, extraction et manifeste

Le service worker associe les téléchargements à une capture par l'onglet d'origine et l'URL de référence. Il impose le chemin `Songs/<nom assaini>` via `chrome.downloads.onDeterminingFilename`, avec `conflictAction: "uniquify"`, et ne touche pas aux téléchargements étrangers à une capture.

Archives : si le lien final est lisible par l'extension selon le mécanisme retenu en 29.2, l'archive est lue en mémoire dans la limite du plafond mesuré. Seuls les fichiers audio sont enregistrés dans `Songs/`, plus la pochette si l'option est active ; les chemins internes sont aplatis, assainis, et ne peuvent jamais sortir de `Songs/`. Au-delà du plafond, ou si le lien n'est pas lisible, l'archive est enregistrée telle quelle et la capture marquée `Zip not extracted`.

Lorsque tous les fichiers sont complets, le manifeste est écrit dans `Songs/_mtee/<capture_id>.json` si l'option est active. Un fichier interrompu fait passer la capture à `Failed` avec la cause Chrome ; les actions de soutien ne sont alors pas lancées.

### Jalon 30.6 — Actions de soutien

Après un téléchargement réussi, le service worker ouvre ou réutilise un onglet sur la page SoundCloud du morceau, puis confie la suite à `content/support.js` :

1. Vérifier que l'utilisateur est connecté ; sinon `Skipped: not signed in`, sans autre action.
2. Vérifier le plafond quotidien ; s'il est atteint, `Skipped: daily limit`.
3. Like : lire l'état du bouton ; s'il est déjà actif ou réalisé comme étape de passerelle, `Already` ; sinon cliquer, puis vérifier que l'état est devenu actif.
4. Repost : même règle. Si SoundCloud propose un menu (repost simple ou avec légende), choisir le repost simple.
5. Commentaire : si l'historique indique un commentaire de l'extension sur ce morceau, ou si l'étape de passerelle en a posté un, `Already`. Sinon tirer un texte actif de la liste, remplacer `{artist}` et `{title}`, saisir et envoyer, puis vérifier son apparition. Liste vide : `Skipped: no comments`.
6. Espacer chaque action d'un délai aléatoire compris entre les bornes des options.

Valeurs par défaut proposées, à ajuster après la recette : délai de 4 à 12 s entre actions, 20 s minimum entre deux titres d'un lot, plafond de 30 morceaux soutenus par jour. Ce sont des garde-fous de conception, pas des limites publiées par SoundCloud. Une erreur ou un état inattendu arrête les actions de soutien de ce morceau, sans nouvel essai automatique, et laisse le téléchargement `Done`. En cas d'échec, l'extension n'essaie jamais de « défaire » une action : un clic de plus sur une bascule pourrait annuler un like légitime.

### Jalon 30.7 — Recette et paquet

Tests automatiques, depuis `extensions/soundcloud-capture` :

    node --test tests/

Bout-en-bout synthétique : un serveur statique local (`127.0.0.1`) sert des pages reproduisant la structure observée de SoundCloud (morceau, playlist, état liké/reposté, zone de commentaire) et des passerelles, avec des fichiers audio et des archives synthétiques. Chrome est lancé avec un profil isolé (`.local/validation/30/chrome-profile`) et l'extension non empaquetée. Le pilote (Playwright Python dans le groupe `dev`, ou script Node) est choisi au début du jalon après vérification d'installation. Les fixtures ne contiennent aucune page copiée ni aucun contenu protégé ; les sélecteurs de production sont remplacés par ceux des fixtures au moyen d'un réglage de test, sans code conditionnel en production.

Cas couverts : chaque voie livrée ; morceau sans voie ; morceau déjà liké et reposté ; déjà commenté par l'extension ; utilisateur non connecté ; plafond atteint ; liste de commentaires vide ; archive valide, archive trop grosse, archive piégée (`../`, noms réservés) ; collision de noms ; lot de playlist avec titres mixtes, pause, reprise et annulation ; service worker redémarré en cours de capture.

Recette réelle, avec l'utilisateur, son compte et sa liste de commentaires : un morceau par voie observée, une archive Bandcamp, un morceau déjà liké, une étape OAuth laissée à l'utilisateur, une playlist courte. Vérifier sur SoundCloud qu'aucun like ni repost existant n'a été retiré et qu'un seul commentaire a été posté par morceau. Consigner le résultat dans `docs/validation/30-soundcloud-extension.md`, sans e-mail, nom de compte, texte de commentaire ni chemin personnel.

Paquet : créer `scripts/package_extension.ps1`, qui valide `manifest.json` et produit `dist/mtee-soundcloud-capture-<version>.zip` (non versionné).

    pwsh -File scripts/package_extension.ps1

La distribution Windows de MTEE n'est pas concernée ; aucun fichier sous `src/` n'est modifié par ce plan.

## Validation et acceptation

Le plan est accepté lorsque :

- les tests `node --test` et le bout-en-bout synthétique réussissent pour chaque voie livrée ;
- la recette réelle réussit pour chaque voie observée, ou son échec est documenté avec sa cause ;
- aucun like ni repost existant n'est inversé ;
- aucun commentaire n'est posté deux fois ni en dehors de la liste de l'utilisateur ;
- consentement OAuth et CAPTCHA restent toujours à l'utilisateur ;
- aucune écriture n'a lieu hors de `Songs/` et `Songs/_mtee/`, et les archives extraites ne peuvent pas en sortir ;
- les manifestes ne contiennent pas de donnée sensible ;
- l'archive de l'extension est produite.

Une voie dont la recette réelle échoue reste désactivée et marquée comme telle.

## Reprise et réexécution

Les captures et lots en cours survivent au redémarrage du service worker et de Chrome grâce à `storage.local`. Au réveil, une capture dont l'onglet a disparu passe à `Waiting for you`, avec `Open gate` ou `Open track`. `Retry` relance le téléchargement tant qu'aucun fichier complet n'existe. Si le téléchargement a déjà réussi, `Retry` relance seulement les actions de soutien restantes, qui relisent l'état avant d'agir. Lorsqu'un site change de mise en page, seuls `content/selectors.js` et les fixtures concernées sont mis à jour, avec une nouvelle version de sélecteurs consignée.

## Interfaces et dépendances

Messages entre scripts et service worker : `{type, capture_id, ...}` avec `type` parmi `route.detected`, `batch.start`, `capture.start`, `gate.step`, `gate.waiting`, `gate.done`, `download.done`, `support.result`, `capture.failed`. Chaque message est validé à la réception.

État persistant :

- `captures/<id>` → `{state, route, source, files, support, batch_id, updated_at}` ;
- `batches/<id>` → `{playlist_url, capture_ids, cursor, paused}` ;
- `history/<page_url>` → `{downloaded_at, commented_at}` ;
- `settings` → options versionnées.

Contrat externe unique : manifeste `mtee.capture/1` du plan 29. Seule dépendance tierce prévue : la bibliothèque d'extraction zip, copiée dans `vendor/`.

## Preuves et livraison Git

    git status --short
    git diff --check
    git add -- extensions/soundcloud-capture scripts/package_extension.ps1 THIRD_PARTY_NOTICES.md docs/ux/soundcloud-capture-mockup.html docs/decisions/29-soundcloud-capture.md docs/validation/30-soundcloud-extension.md "Plans d'exécution/30-soundcloud-extension.md"
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step30-commit.txt'
    @'
    feat(extension): download free SoundCloud tracks and support artists

    Changes: <routes delivered, gate automata, Songs folder, zip extraction, support actions, options>
    Validation: <node tests, synthetic end-to-end, real routes tested with user>
    Limits: <routes disabled, selectors version, pacing defaults, manual steps>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Des commits intermédiaires par jalon sont autorisés. Pousser selon `PLANS.md`. Vérifier qu'aucun profil Chrome, archive `dist/`, fichier audio de recette, profil de formulaire ou liste de commentaires n'est indexé.

## Progress

- [x] 2026-09-29 — Plan préparé ; décisions utilisateur intégrées (profils de formulaire, `Downloads/Songs`, lots de playlist, extraction zip, actions de soutien).
- [ ] Maquette popup/options/bouton validée (30.1).
- [ ] Squelette et modules purs testés (30.2).
- [ ] Détection SoundCloud et lots de playlist (30.3).
- [ ] Automates des voies observées (30.4).
- [ ] Téléchargement, extraction et manifeste (30.5).
- [ ] Actions de soutien (30.6).
- [ ] Recette synthétique et réelle, paquet, rapport, commit et push (30.7).

## Surprises & Discoveries

Non observé à ce stade.

## Decision Log

2026-09-29 — Claude — JavaScript ES modules sans compilation et tests `node --test`. Motif : outillage minimal dans un dépôt Python ; Node est déjà installé sur la machine de développement.

2026-09-29 — Claude — Sélecteurs isolés dans un seul module versionné, avec diagnostic visible. Motif : SoundCloud et les passerelles changent leur mise en page sans préavis ; la panne doit être localisée et lisible.

2026-09-29 — Utilisateur — Like, repost et commentaire tiré de sa liste après chaque téléchargement réussi, même non exigés. Claude — Lecture d'état avant tout clic, un commentaire par morceau, délais aléatoires et plafond quotidien, aucune tentative d'annulation automatique. Motif : les boutons sont des bascules et des commentaires répétitifs peuvent être signalés comme spam.

2026-09-29 — Utilisateur — Lots depuis les playlists uniquement. Claude — File séquentielle, une passerelle à la fois, titres déjà téléchargés ignorés par défaut.

## Outcomes & Retrospective

À compléter après exécution.

Note de révision — 2026-09-29, Claude : création du plan ; même jour, intégration des réponses utilisateur.
