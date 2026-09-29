# 30 — Extension Chrome de capture SoundCloud

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il réalise l'extension définie par le [cadrage 29](29-soundcloud-cadrage.md). Il ne commence qu'après les jalons 29.1 à 29.3 : voies observées, contrat `capture.json` v1 prototypé et décisions utilisateur consignées dans `docs/decisions/29-soundcloud-capture.md`.

## Objectif et résultat observable

Sur une page de morceau SoundCloud, un bouton `Send to MTEE` apparaît à côté des actions du morceau. Son état indique la voie détectée : `Direct download`, `Droploud`, `Hypeddit`, `Bandcamp` ou `No free download`. Un clic ouvre la passerelle dans un onglet suivi, remplit les champs autorisés, met en évidence les étapes qui demandent l'utilisateur, déclenche le téléchargement final, puis enregistre fichiers et manifeste dans `MTEE Inbox/<capture_id>/`.

La fenêtre surgissante (« popup ») de l'extension liste les captures récentes avec leur état : `Queued`, `Waiting for you`, `Downloading`, `Waiting for email`, `Done`, `Failed`, avec un message lisible et `Retry` / `Open gate` / `Show in folder`. La page d'options enregistre l'e-mail, le nom, le pays éventuel et la politique `Ask`/`Auto` par type d'action.

L'extension fonctionne sans que MTEE soit lancé. L'interface est en anglais.

## Contexte et prérequis

Lire `AGENTS.md`, `PLANS.md`, le plan 29 et `docs/integrations/soundcloud-capture.md`. Seules les voies marquées `observé` au jalon 29.1 sont développées ; les autres restent affichées comme non prises en charge.

Vocabulaire : une **voie** (« route ») est le moyen de téléchargement d'un morceau ; une **passerelle** (« gate ») est une page tierce qui conditionne le téléchargement à des étapes ; une **capture** est une tentative identifiée par `capture_id`, de la détection au manifeste écrit.

Chrome Manifest V3 impose un service worker non persistant : tout état de capture est conservé dans `chrome.storage.local` et reconstruit au réveil. Les scripts de contenu ne partagent pas de mémoire avec le service worker ; ils échangent des messages typés.

## Plan de travail et jalons

### Jalon 30.1 — Maquette de l'interface de l'extension

Produire `docs/ux/soundcloud-capture-mockup.html`, avec données fictives : bouton injecté dans ses cinq états, popup avec une capture par état, page d'options. Reprendre la palette Acid et Geist Sans de `docs/ux/specification.md` pour la popup et les options ; le bouton injecté reste discret et cohérent avec SoundCloud. Présenter la maquette à l'utilisateur et consigner sa décision dans `docs/decisions/29-soundcloud-capture.md` avant le code d'interface. Le code non visuel des jalons 30.2 et 30.3 peut avancer en parallèle.

### Jalon 30.2 — Squelette, modules purs et tests

Créer `extensions/soundcloud-capture/` :

    extensions/soundcloud-capture/
      manifest.json               MV3, version, permissions minimales
      background.js               service worker : file de captures, téléchargements, manifeste
      lib/routes.js               classification d'URL : SoundCloud, gate.sc, passerelles
      lib/capture.js              création et validation de capture.json v1
      lib/filenames.js            assainissement des noms Windows
      lib/state.js                machine d'états d'une capture, persistance storage.local
      content/soundcloud.js       détection et bouton injecté
      content/gates/droploud.js   automate de passerelle
      content/gates/hypeddit.js
      content/gates/bandcamp.js
      content/selectors.js        sélecteurs par site, versionnés, seul endroit à ajuster
      popup/  options/            HTML, CSS, JS
      tests/                      node:test et fixtures synthétiques

Permissions : `downloads`, `storage`, `tabs` si nécessaire au suivi des onglets. `host_permissions` limitées à `https://soundcloud.com/*`, `https://gate.sc/*`, `https://droploud.com/*`, `https://hypeddit.com/*`, `https://*.bandcamp.com/*`. Les domaines personnalisés Bandcamp passent par `optional_host_permissions` et une demande à l'utilisateur au moment de la capture. Aucun `<all_urls>`.

Les modules `lib/` sont purs et testés avec `node --test` : décodage des liens `gate.sc`, reconnaissance des passerelles et rejet des domaines imitant un nom (par exemple `hypeddit.com.evil.example`), assainissement des noms (caractères interdits Windows, noms réservés `CON`, `NUL`…, longueur, points finaux), transitions d'états autorisées, validation du manifeste et absence de champs sensibles.

### Jalon 30.3 — Détection sur SoundCloud

`content/soundcloud.js` observe la navigation de l'application monopage (changements d'historique et `MutationObserver` borné au conteneur du morceau), repère la page de morceau, puis cherche dans l'ordre : téléchargement natif proposé par SoundCloud, lien d'achat pointant vers une passerelle reconnue, lien de passerelle dans la description. Il ne lance aucune requête réseau pour détecter ; il lit la page affichée.

Le bouton est injecté une seule fois par morceau affiché, retiré à la navigation et ne casse pas la mise en page si les sélecteurs échouent. Un sélecteur introuvable produit un diagnostic visible dans la popup (`SoundCloud layout not recognised`) plutôt qu'une erreur silencieuse. Le lot facultatif (décision 29.3-4) ajoute sur les pages de playlist et de likes une commande `Send visible tracks to MTEE` qui alimente la file séquentielle.

### Jalon 30.4 — Automates de passerelle

Un automate par passerelle, piloté par le service worker, s'exécute seulement dans un onglet ouvert par une capture et pour la durée de celle-ci. Il ne s'active jamais sur une passerelle ouverte manuellement hors capture.

Chaque automate décrit les étapes observées au jalon 29.1 comme une liste déclarative (détection de l'étape, action, condition de fin). Il applique la politique du cadrage : remplissage des champs autorisés, mise en évidence et attente pour OAuth, follow, like, repost et commentaire selon les options, pause sur CAPTCHA, clic sur le bouton final. Délai maximal par étape en attente de l'utilisateur, puis état `Waiting for you` persistant plutôt qu'un échec. L'utilisateur peut toujours reprendre l'onglet à la main ; l'automate détecte l'avancement au lieu de le refaire.

Bandcamp : pour une sortie livrée par e-mail, la capture passe à `Waiting for email`. Lorsque l'utilisateur ouvre le lien reçu dans Chrome, le script de la page de téléchargement Bandcamp rattache la page à la capture par l'URL de la sortie, sélectionne le format préféré (option, par défaut FLAC si proposé, sinon MP3 320) et poursuit.

L'e-mail et le nom sont lus dans `chrome.storage.local` au moment du remplissage, jamais écrits dans le manifeste, les journaux ou les messages d'erreur.

### Jalon 30.5 — Téléchargement et manifeste

Le service worker associe les téléchargements à la capture par l'onglet d'origine et l'URL de référence, puis impose le chemin `MTEE Inbox/<capture_id>/<nom assaini>` via `chrome.downloads.onDeterminingFilename`, sans jamais écraser (`conflictAction: "uniquify"`). Les téléchargements étrangers à une capture ne sont pas touchés. Lorsque tous les fichiers attendus sont terminés (`state: complete`), il écrit `capture.json` selon le mécanisme retenu au jalon 29.2. Un fichier interrompu ou refusé fait passer la capture à `Failed` avec la cause Chrome, sans manifeste.

Une même page SoundCloud déjà capturée avec succès affiche `Already sent` ; un nouvel envoi demande confirmation et crée une capture distincte.

### Jalon 30.6 — Recette et paquet

Tests automatiques (répertoire de travail `extensions/soundcloud-capture`) :

    node --test tests/

Test de bout en bout sur fixtures synthétiques : un petit serveur statique local (`127.0.0.1`) sert des pages reproduisant la structure observée de SoundCloud et des passerelles, avec des fichiers audio synthétiques. Chrome est lancé avec un profil isolé et l'extension non empaquetée (`--user-data-dir` dans `.local/validation/30/chrome-profile`, `--load-extension`). Le moyen de piloter ce Chrome (Playwright Python ajouté au groupe `dev`, ou script Node) est choisi au démarrage du jalon après vérification d'installation, puis consigné. Les fixtures ne contiennent aucune page copiée ni aucun contenu protégé.

Recette réelle, avec l'utilisateur et son compte : un morceau par voie observée, un morceau sans téléchargement, une étape OAuth laissée à l'utilisateur, un CAPTCHA si rencontré, une capture interrompue puis relancée, une capture pendant que MTEE est fermé. Consigner le résultat dans `docs/validation/30-soundcloud-extension.md` sans e-mail, nom de compte ni chemin personnel.

Paquet : créer `scripts/package_extension.ps1`, qui vérifie le manifeste et produit `dist/mtee-soundcloud-capture-<version>.zip` (non versionné).

    pwsh -File scripts/package_extension.ps1

La distribution Windows de MTEE n'est pas modifiée par ce plan ; exécuter néanmoins `uv run python -m compileall -q src/mtee` et le smoke test existant pour prouver l'absence de régression si des fichiers partagés ont changé.

## Validation et acceptation

Accepté lorsque : tests `node --test` réussis ; bout-en-bout synthétique réussi pour chaque voie livrée ; recette réelle réussie pour chaque voie observée, ou échec documenté avec sa cause ; aucune action de compte réalisée sans la politique choisie ; manifeste conforme et sans donnée sensible ; aucune écriture hors `MTEE Inbox` ; archive produite. Une voie dont la recette réelle échoue reste désactivée dans l'extension et marquée comme telle.

## Reprise et réexécution

Les captures en cours survivent au redémarrage du service worker et de Chrome grâce à `storage.local` ; au réveil, une capture dont l'onglet a disparu passe à `Waiting for you` avec `Open gate`. `Retry` crée une nouvelle tentative dans le même dossier de capture tant qu'aucun manifeste n'existe. Lorsqu'un site change de mise en page, seul `content/selectors.js` et les fixtures concernées sont mis à jour, avec une nouvelle version de sélecteurs consignée.

## Interfaces et dépendances

Messages entre scripts et service worker : `{type: "route.detected" | "capture.start" | "gate.step" | "gate.waiting" | "gate.done" | "capture.failed", capture_id, ...}`, validés à la réception. État persistant : `captures/<capture_id>` → `{state, route, source, files, updated_at}`. Contrat externe unique : `capture.json` v1 du plan 29. Aucune dépendance npm n'est ajoutée sans nécessité ; si une l'est, elle est verrouillée (`package-lock.json`) et sa licence ajoutée à `THIRD_PARTY_NOTICES.md`.

## Preuves et livraison Git

    git status --short
    git diff --check
    git add -- extensions/soundcloud-capture scripts/package_extension.ps1 docs/ux/soundcloud-capture-mockup.html docs/decisions/29-soundcloud-capture.md docs/validation/30-soundcloud-extension.md "Plans d'exécution/30-soundcloud-extension.md"
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step30-commit.txt'
    @'
    feat(extension): capture free SoundCloud downloads into MTEE Inbox

    Changes: <routes delivered, gate automation policy, capture.json writer, popup and options>
    Validation: <node tests, synthetic end-to-end, real routes tested with user>
    Limits: <routes disabled, selectors version, manual steps>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Pousser selon `PLANS.md`. Vérifier qu'aucun profil Chrome, archive `dist/` ou fichier audio de recette n'est indexé.

## Progress

- [x] 2026-09-29 — Plan préparé ; attend les jalons 29.1 à 29.3.
- [ ] Maquette popup/options/bouton validée (30.1).
- [ ] Squelette et modules purs testés (30.2).
- [ ] Détection SoundCloud (30.3).
- [ ] Automates des voies observées (30.4).
- [ ] Téléchargement et manifeste (30.5).
- [ ] Recette synthétique et réelle, paquet, rapport, commit et push (30.6).

## Surprises & Discoveries

Non observé à ce stade.

## Decision Log

2026-09-29 — Claude — JavaScript ES modules sans compilation et tests `node --test`. Motif : garder l'outillage minimal dans un dépôt Python ; Node est déjà installé sur la machine de développement.

2026-09-29 — Claude — Sélecteurs isolés dans un seul module versionné et diagnostic visible. Motif : SoundCloud et les passerelles changent leur mise en page sans préavis ; la panne doit être localisée et lisible.

## Outcomes & Retrospective

À compléter après exécution.

Note de révision — 2026-09-29, Claude : création du plan.
