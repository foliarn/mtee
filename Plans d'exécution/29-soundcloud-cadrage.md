# 29 — Capture SoundCloud : cadrage, contrats et décisions

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il cadre une nouvelle capacité demandée le 29 septembre 2026 : une extension Chrome qui repère les téléchargements gratuits proposés sur SoundCloud, remplit les formulaires des passerelles (« download gates ») Droploud, Hypeddit et Bandcamp, télécharge les fichiers, puis les remet à MTEE pour un futur tri manuel ou automatique vers les dossiers de la collection. Sa rédaction ne modifie ni l'application ni l'extension, qui n'existe pas encore.

## Résultat attendu et portée

À la fin de la série 29–32, l'utilisateur ouvre un morceau SoundCloud, clique sur un bouton `Send to MTEE` injecté dans la page, complète au besoin les étapes qui engagent son compte, puis retrouve le fichier dans une boîte de réception MTEE (`Inbox`) avec sa provenance : page SoundCloud, passerelle, artiste, titre affiché et date de capture. Depuis cette boîte, il range le morceau dans un dossier de sa collection, d'abord manuellement, puis par des règles qui proposent une destination.

La série se découpe en quatre plans exécutables séparément :

| Plan | Livrable | Dépend de |
|---|---|---|
| 29 — ce document | Étude des sites, contrat de remise extension → MTEE, politique d'automatisation, décisions utilisateur | Rien dans le code ; démarrable immédiatement |
| [30 — Extension Chrome](30-soundcloud-extension.md) | Extension MV3 : détection, passerelles, téléchargement, manifeste de capture | 29 ; indépendant du code Python |
| [31 — Inbox MTEE](31-soundcloud-inbox-mtee.md) | Ingestion des captures, provenance en base, vue `Inbox` | 29, 30 (au moins une capture réelle), clôture de la série 23–28, maquette validée |
| [32 — Tri vers les dossiers](32-soundcloud-tri-dossiers.md) | Tri manuel puis règles de tri automatique | 31, décision sur le déplacement, étape 10 pour les règles fondées sur des tags |

Hors périmètre : publication sur le Chrome Web Store, extraction d'un flux audio non proposé au téléchargement, contournement d'une passerelle, résolution de CAPTCHA, génération de commentaires, prise en charge d'autres navigateurs, écriture automatique des tags à partir de la page.

## Sources et état vérifié

Lire `AGENTS.md`, `PLAN.md` (addendum du 29 septembre), `PLANS.md`, ce plan, puis le plan exécuté. Les plans 14 (contrats externes vérifiés avant tout adaptateur), 17 (retraits), 21 (corbeille) et 10 (vocabulaire des tags non validé) fixent des contraintes reprises ici.

État inspecté le 29 septembre 2026 sur `main`, commit `a783620`. Les modifications locales de `.gitignore`, `AGENTS.md` et `.codex/` appartiennent à l'utilisateur et restent hors des commits de cette série.

Constats issus des sources :

- `src/mtee/services/library_scanner.py` reconnaît les suffixes audio via `AUDIO_SUFFIXES` et ignore déjà les fichiers temporaires de conversion MTEE ; un dossier de captures peut donc être parcouru par le scanner existant, à condition d'ignorer les téléchargements incomplets de Chrome (`.crdownload`).
- `src/mtee/persistence/library_repository.py` conserve `move_location_in_transaction` et `copy_location_in_transaction`, mais aucun appelant n'existe depuis le lot 17, qui a retiré les actions Move/Copy/Rename. Le tri vers un dossier réintroduit donc une opération retirée : c'est une décision utilisateur, pas un choix technique ordinaire.
- La dernière migration est `014_trash_recycle_identity.sql` ; la numéro 010 est réservée comme migration retirée (`_RETIRED_MIGRATIONS` dans `database.py`). La provenance des captures demandera la prochaine migration libre au moment de l'étape 31.
- Le plan 10 n'a pas d'accord de vocabulaire ; aucun critère fondé sur des tags personnalisés ne peut être livré avant cet accord.
- Node.js v24.13.0 est présent sur la machine de développement (`C:\Program Files\nodejs\node.exe`). Il n'est pas une dépendance de MTEE ; il sert uniquement aux tests de l'extension.

Constats externes, à confirmer pendant le jalon 29.1 (recherche web du 29 septembre 2026, non reproduite dans un navigateur) :

- Droploud (`droploud.com`) propose des passerelles dont les étapes, choisies par l'artiste, peuvent comprendre e-mail, abonnement SoundCloud, like et repost. Ses conditions sont publiées sur `https://droploud.com/legal/gate-terms`.
- Hypeddit (`hypeddit.com`) propose des passerelles combinant e-mail et actions sur plusieurs plateformes. Des sources de 2026 rapportent que SoundCloud a suspendu l'accès API de Hypeddit et que les étapes SoundCloud y sont devenues facultatives. L'extension suit l'interface affichée ; elle ne suppose pas que cet état est durable.
- Bandcamp propose des sorties gratuites ou « name your price » ; certaines délivrent le lien immédiatement, d'autres l'envoient par e-mail. Les artistes peuvent utiliser un domaine personnalisé.

## Décisions de conception proposées

Ces choix sont proposés pour être confirmés au jalon 29.3. Ils ne valent pas accord utilisateur.

**Remise par dossier plutôt que par serveur local.** L'extension télécharge chaque capture dans `<dossier Téléchargements de Chrome>/MTEE Inbox/<capture_id>/` et y écrit en dernier un manifeste `capture.json`. MTEE lit ce dossier. Motifs : Chrome n'autorise l'extension à écrire que sous son dossier de téléchargements ; MTEE n'a pas besoin d'être ouvert pendant la capture ; aucun port local n'est exposé aux pages web ; aucune clé de registre n'est créée. Un hôte de messagerie native (« native messaging ») reste une amélioration ultérieure possible pour afficher l'état de MTEE ou ouvrir la capture, après accord, puisqu'il exige un manifeste enregistré dans `HKCU`.

**Le manifeste est le marqueur de fin.** Un dossier sans `capture.json` valide est une capture en cours ou abandonnée ; MTEE l'ignore. L'extension n'écrit le manifeste qu'après l'événement de téléchargement terminé pour chaque fichier.

**Automatisation graduée.** L'extension automatise ce qui ne parle pas au nom de l'utilisateur et laisse la main pour ce qui engage son compte :

| Étape de passerelle | Comportement par défaut | Réglable |
|---|---|---|
| Détection du lien gratuit, ouverture de la passerelle | Automatique après clic sur `Send to MTEE` | Non |
| E-mail, nom, pays | Remplis depuis les options locales | Oui : désactivable |
| Connexion SoundCloud/Spotify/autre (OAuth) | Jamais automatique : l'utilisateur consent | Non |
| Follow, like, repost | L'extension met l'étape en évidence et attend le clic | Oui : `Ask` ou `Auto` par type d'action |
| Commentaire | Jamais généré ni posté par l'extension | Non |
| CAPTCHA, anti-robot | Pause, l'utilisateur agit | Non |
| Bouton de téléchargement final | Automatique | Non |

**Pas de contournement.** Aucune requête fabriquée vers l'API d'une passerelle, aucune étape exigée sautée, aucune capture de flux audio. Si un morceau n'offre ni téléchargement SoundCloud natif ni lien vers une passerelle prise en charge, l'extension l'indique et s'arrête.

**Tri découplé de la capture.** La capture ne place rien directement dans la collection. Une capture arrive dans `Inbox` ; le tri est une étape séparée, réversible et journalisée. Les métadonnées lues sur la page sont des observations de provenance, jamais écrites dans le fichier sans action explicite (même règle que le plan 14).

**Code dans le dépôt MTEE.** L'extension vit dans `extensions/soundcloud-capture/`, en JavaScript ES modules sans étape de compilation, documenté par JSDoc. Motif : le projet est Python/uv ; une chaîne TypeScript ajouterait un outil de build pour quelques centaines de lignes. Le contrat `capture.json` est défini une fois dans `docs/integrations/soundcloud-capture.md` et testé des deux côtés.

**Installation locale.** L'extension est chargée « non empaquetée » en mode développeur de Chrome. Un script produit une archive dans `dist/` (non versionnée) ; aucune publication sur le Chrome Web Store n'est faite sans décision séparée.

## Contrat de capture (version 1)

Définir dans `docs/integrations/soundcloud-capture.md`, au jalon 29.2 :

    MTEE Inbox/
      <capture_id>/                 UUID v4 généré par l'extension
        <nom de fichier fourni par le serveur, assaini>
        [fichiers supplémentaires éventuels, par exemple une archive .zip]
        capture.json                écrit en dernier

    capture.json
    {
      "schema": "mtee.capture/1",
      "capture_id": "<uuid>",
      "created_at_utc": "2026-09-29T12:34:56Z",
      "extension_version": "0.1.0",
      "source": {
        "platform": "soundcloud",
        "page_url": "https://soundcloud.com/<artist>/<track>",
        "track_title": "<tel qu'affiché>",
        "artist_display": "<tel qu'affiché>",
        "artwork_url": "<facultatif>",
        "tags_displayed": ["<genre affiché>"]
      },
      "route": {
        "kind": "soundcloud_native | droploud | hypeddit | bandcamp",
        "gate_url": "<facultatif>",
        "steps": [{"kind": "email", "mode": "autofill"}, {"kind": "follow", "mode": "user"}]
      },
      "files": [
        {"name": "<nom relatif>", "size_bytes": 12345678, "mime": "audio/mpeg",
         "final_url_host": "<hôte seul>", "completed_at_utc": "..."}
      ]
    }

Le manifeste ne contient ni adresse e-mail, ni jeton, ni cookie, ni URL de téléchargement signée complète (seul l'hôte est conservé). Un champ absent reste absent. MTEE refuse un `schema` inconnu en l'affichant comme capture non lisible, sans la supprimer. Toute évolution incompatible crée `mtee.capture/2`.

## Plan de travail et jalons

### Jalon 29.1 — Étudier les pages réelles

Avec l'utilisateur, ouvrir dans Chrome au moins un exemple par voie : téléchargement SoundCloud natif, lien vers Droploud, lien vers Hypeddit, lien vers Bandcamp (sortie gratuite directe et sortie envoyée par e-mail si disponible), et un morceau sans téléchargement. Relever pour chacun : où apparaît le lien sur SoundCloud (bouton d'achat, menu `More`, description), la redirection éventuelle par `gate.sc`, les domaines traversés, les étapes et leur ordre, les champs de formulaire, les pop-ups OAuth, le nom et le type du fichier final, et le déclencheur du téléchargement (lien direct, requête après clic, archive).

Consigner les conditions d'utilisation consultées (SoundCloud, Droploud, Hypeddit, Bandcamp) et ce qu'elles disent de l'automatisation, avec URL et date. Ne pas copier les pages : noter la structure utile (rôles, textes de boutons, attributs stables) pour reconstruire des fixtures synthétiques au plan 30.

Résultat attendu : `docs/integrations/soundcloud-capture.md`, section « Observations », avec une ligne par voie : `observé`, `documenté seulement` ou `non disponible`. Une voie non observée n'est pas développée au plan 30.

### Jalon 29.2 — Fixer le contrat de remise

Rédiger le contrat ci-dessus dans `docs/integrations/soundcloud-capture.md` et le prototyper à la main : dans Chrome, vérifier depuis la console d'une extension minimale jetable (hors dépôt) que `chrome.downloads.download` accepte un sous-dossier relatif et une URL `data:application/json` pour le manifeste. Si l'URL `data:` est refusée, retenir la génération du manifeste par un document hors écran (`chrome.offscreen`) avec `URL.createObjectURL`, et le consigner.

Vérifier aussi le comportement lorsque l'utilisateur a activé « Demander où enregistrer chaque fichier » dans Chrome : le téléchargement doit alors être détecté comme sorti de `MTEE Inbox` et signalé, pas perdu en silence.

### Jalon 29.3 — Recueillir les décisions utilisateur

Préparer `docs/decisions/29-soundcloud-capture.md` avec les questions ci-dessous, chacune accompagnée d'une recommandation, puis consigner les réponses datées. Le développement du plan 30 attend ces réponses ; le silence ne vaut pas accord.

1. Politique d'automatisation : le tableau ci-dessus convient-il ? Follow/like/repost par défaut en `Ask` ?
2. Données de formulaire : quelle adresse e-mail (idéalement dédiée), faut-il remplir nom et pays ?
3. Emplacement : `Téléchargements/MTEE Inbox` convient-il, ou un autre dossier sous Téléchargements ?
4. Lots : faut-il pouvoir envoyer plusieurs morceaux d'une playlist ou des likes en une fois ? Recommandation : oui, en file séquentielle, un onglet de passerelle à la fois, utilisateur présent.
5. Tri manuel (plan 32) : accepter la réintroduction d'une action `Move to folder` limitée aux morceaux de l'Inbox ?
6. Tri automatique : quels critères sont attendus en premier (artiste SoundCloud, genre affiché, BPM/Key des tags, passerelle, playlist SoundCloud d'origine) ? Les critères fondés sur des tags personnalisés attendent l'étape 10.
7. Archives : extraire automatiquement les `.zip` (albums Bandcamp, packs) dans MTEE, ou les laisser à l'utilisateur ?

### Jalon 29.4 — Ordonner la série

Mettre à jour `Plans d'exécution/README.md` et l'addendum de `PLAN.md` selon les réponses. Recommandation : 29 et 30 peuvent avancer pendant la série UX/UI puisqu'ils ne touchent pas le code Python ; 31 et 32 attendent la clôture du plan 28 et leurs maquettes validées.

## Validation et acceptation

Ce plan est documentaire. Il est accepté lorsque : chaque voie a un statut observé/documenté/non disponible avec sources datées ; le contrat v1 est rédigé et prototypé sur les deux points du jalon 29.2 ; les réponses utilisateur sont consignées ; l'index et `PLAN.md` sont à jour. Contrôles : liens relatifs valides, encodage UTF-8, `git diff --check`. Aucun test applicatif n'est annoncé.

## Reprise et réexécution

Les observations sont datées ; une passerelle qui change d'interface demande de refaire la ligne concernée du jalon 29.1, sans rouvrir les autres. Une décision utilisateur modifiée est ajoutée au journal avec sa date ; l'ancienne reste visible.

## Preuves et livraison Git

Depuis la racine du dépôt :

    git status --short
    git diff --check
    git add -- "Plans d'exécution/29-soundcloud-cadrage.md" docs/integrations/soundcloud-capture.md docs/decisions/29-soundcloud-capture.md "Plans d'exécution/README.md" PLAN.md
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step29-commit.txt'
    @'
    docs(capture): record SoundCloud capture study and decisions

    Changes: <routes observed, capture.json v1 contract, automation policy, user answers>
    Validation: <pages examined, prototype results for subfolder and manifest downloads>
    Limits: <routes not observed, open questions>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Pousser selon `PLANS.md` (fetch, comparaison, `git push origin main`, vérification des hashes).

## Progress

- [x] 2026-09-29 — Demande reçue ; dépôt, plans 10, 14, 17 et services concernés inspectés ; série 29–32 préparée.
- [ ] Voies réelles observées et conditions d'utilisation consultées (29.1).
- [ ] Contrat `capture.json` v1 rédigé et prototypé (29.2).
- [ ] Décisions utilisateur consignées (29.3).
- [ ] Index et `PLAN.md` mis à jour selon les décisions, commit et push (29.4).

## Surprises & Discoveries

2026-09-29 — Les primitives `move_location_in_transaction` et `copy_location_in_transaction` subsistent dans `library_repository.py` sans appelant depuis le lot 17. Elles peuvent servir de base au tri, sous réserve de relire leurs tests et de l'accord sur la réintroduction du déplacement.

2026-09-29 — Des sources publiques de 2026 indiquent que les étapes SoundCloud des passerelles Hypeddit sont devenues facultatives après la suspension de son accès API. Non vérifié dans un navigateur.

## Decision Log

2026-09-29 — Claude — Remise par dossier `MTEE Inbox` et manifeste écrit en dernier, plutôt qu'un serveur HTTP local ou un hôte natif. Motif : aucune surface réseau locale, pas d'écriture dans le registre, MTEE peut être fermé pendant la capture.

2026-09-29 — Claude — Aucune action engageant le compte de l'utilisateur n'est automatisée par défaut ; commentaires, consentements OAuth et CAPTCHA restent toujours manuels. Motif : ces actions publient au nom de l'utilisateur et relèvent des conditions des plateformes. À confirmer au jalon 29.3.

2026-09-29 — Claude — Capture et tri séparés par une Inbox. Motif : le déplacement est retiré depuis le lot 17 et les critères de tags attendent l'étape 10 ; la capture peut être livrée sans ces deux dépendances.

## Outcomes & Retrospective

Série préparée à partir du commit `a783620`. Aucune page de passerelle n'a été ouverte, aucun prototype d'extension exécuté, aucune décision utilisateur recueillie. Les constats externes proviennent d'une recherche web et restent à observer.

Note de révision — 2026-09-29, Claude : création du cadrage de la capture SoundCloud et de la série 29–32.
