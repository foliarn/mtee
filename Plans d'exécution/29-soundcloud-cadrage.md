# 29 — Capture SoundCloud : cadrage, contrats et décisions

Ce document est un ExecPlan vivant à maintenir selon `PLANS.md`, à la racine du dépôt. Il cadre une capacité demandée le 29 septembre 2026 : une extension Chrome qui repère les téléchargements gratuits proposés sur SoundCloud, remplit les formulaires des passerelles (« download gates ») Droploud, Hypeddit et Bandcamp, télécharge les fichiers dans `Downloads/Songs`, puis soutient l'artiste par un like, un repost et un commentaire choisi par l'utilisateur. Sa rédaction ne modifie ni l'application ni l'extension, qui n'existe pas encore.

## Résultat attendu et portée

À la fin de la série, l'utilisateur ouvre un morceau ou une playlist SoundCloud et clique sur `Download` ou `Download playlist`, un bouton injecté dans la page. L'extension trouve la voie de téléchargement, remplit les formulaires avec les informations enregistrées dans ses options et exécute les étapes exigées par la passerelle. Elle laisse l'utilisateur consentir aux connexions OAuth et résoudre les CAPTCHA, puis enregistre les fichiers audio dans `Downloads/Songs`, archives `.zip` extraites. Après chaque téléchargement réussi, elle like, reposte et commente le morceau sur SoundCloud si ce n'est pas déjà fait, selon les options.

Réponses utilisateur du 29 septembre, consignées dans `docs/decisions/29-soundcloud-capture.md` : seule l'extension est développée maintenant. L'intégration à MTEE ([plan 31](31-soundcloud-inbox-mtee.md)) est reportée ; le tri vers les dossiers ([plan 32](32-soundcloud-tri-dossiers.md)) est abandonné.

| Plan | Livrable | État |
|---|---|---|
| 29 — ce document | Étude des sites, politique d'automatisation, contrat de provenance, décisions | En cours ; décisions recueillies |
| [30 — Extension Chrome](30-soundcloud-extension.md) | Extension MV3 : détection, passerelles, téléchargement, extraction, actions de soutien | Après 29.1–29.2 |
| [31 — Inbox MTEE](31-soundcloud-inbox-mtee.md) | Ingestion dans MTEE | Reporté par l'utilisateur |
| [32 — Tri vers les dossiers](32-soundcloud-tri-dossiers.md) | Tri manuel et règles | Abandonné par l'utilisateur |

Hors périmètre : publication sur le Chrome Web Store, extraction d'un flux audio non proposé au téléchargement, contournement d'une passerelle, résolution de CAPTCHA, consentement OAuth automatique, génération de commentaires par l'extension, envois groupés depuis les likes, autres navigateurs, toute modification du code Python de MTEE.

## Sources et état vérifié

Lire `AGENTS.md`, `PLAN.md` (addendum du 29 septembre), `PLANS.md`, ce plan, `docs/decisions/29-soundcloud-capture.md`, puis le plan exécuté.

État inspecté le 29 septembre 2026 sur `main`, commit `a783620`, puis revu après `7a1dda3`. Les modifications locales de `.gitignore`, `AGENTS.md` et `.codex/` appartiennent à l'utilisateur et restent hors des commits de cette série.

Constats du dépôt utiles à l'intégration ultérieure : `library_scanner.py` reconnaît les suffixes audio via `AUDIO_SUFFIXES` ; `library_repository.py` conserve `move_location_in_transaction` sans appelant depuis le lot 17 ; la dernière migration est `014`. Node.js v24.13.0 est installé sur la machine de développement ; il sert uniquement aux tests de l'extension.

Constats externes à confirmer au jalon 29.1 (recherche web du 29 septembre 2026, non reproduite dans un navigateur) :

- Droploud (`droploud.com`) : étapes choisies par l'artiste, dont e-mail, follow, like et repost SoundCloud ; conditions sur `https://droploud.com/legal/gate-terms`.
- Hypeddit (`hypeddit.com`) : e-mail et actions sur plusieurs plateformes ; selon des sources de 2026, les étapes SoundCloud sont devenues facultatives après la suspension de l'accès API de Hypeddit par SoundCloud.
- Bandcamp : sorties gratuites ou « name your price », lien immédiat ou envoyé par e-mail, domaines personnalisés possibles, albums livrés en `.zip`.

## Décisions de conception

**Deux familles d'actions.** Les *étapes de passerelle* sont celles que la passerelle exige pour libérer le téléchargement. Les *actions de soutien* sont le like, le repost et le commentaire réalisés sur la page SoundCloud du morceau après un téléchargement réussi, qu'ils aient été exigés ou non.

| Action | Comportement | Réglable |
|---|---|---|
| Détection, ouverture de la passerelle | Automatique après clic sur `Download` | Non |
| E-mail, nom, pays et autres champs | Remplis depuis le profil de formulaire des options | Oui : contenu et activation |
| Connexion OAuth (SoundCloud, Spotify…) | Jamais automatique : l'utilisateur consent | Non |
| Follow, like, repost, commentaire exigés par la passerelle | Automatiques ; commentaire tiré de la liste de l'utilisateur | Oui : `Auto` ou `Ask` |
| CAPTCHA, anti-robot | Pause, l'utilisateur agit | Non |
| Bouton de téléchargement final | Automatique | Non |
| Like, repost de soutien après succès | Automatiques si pas déjà actifs sur SoundCloud | Oui : chacun activable |
| Commentaire de soutien après succès | Automatique, tiré de la liste de l'utilisateur, un seul par morceau | Oui : activable, liste modifiable |

**Pas de double action.** Like et repost sont des bascules : leur état est lu avant tout clic et un bouton déjà actif n'est pas touché. Une action exigée par la passerelle et déjà réalisée n'est pas répétée. L'historique local mémorise les commentaires postés par l'extension ; un morceau déjà commenté par elle ne l'est plus.

**Rythme et plafond.** Les actions de soutien sont espacées d'un délai aléatoire. Un plafond quotidien réglable s'applique ; au-delà, les téléchargements continuent, mais sans actions de soutien, et la popup le signale. Les valeurs par défaut sont proposées au plan 30 et mesurées en recette ; elles ne proviennent d'aucune règle publiée par SoundCloud. L'utilisateur est informé que des commentaires répétitifs peuvent être considérés comme du spam par la plateforme.

**Aucun contournement.** Aucune requête fabriquée vers l'API d'une passerelle ou de SoundCloud : toutes les actions passent par l'interface affichée, dans la session de l'utilisateur. Aucune étape exigée n'est sautée et aucun flux audio n'est capturé.

**Emplacement.** Les fichiers audio vont à plat dans `<Téléchargements de Chrome>/Songs/`, sans jamais écraser un fichier : Chrome ajoute un suffixe numéroté en cas de collision. Chrome n'autorise l'extension à écrire que sous son dossier de téléchargements. Si l'utilisateur a activé « Demander où enregistrer chaque fichier », ce choix peut détourner le fichier ; la popup doit alors le signaler.

**Provenance légère pour plus tard.** Un manifeste par téléchargement est écrit dans `Songs/_mtee/<capture_id>.json`, après les fichiers audio. Ce réglage est actif par défaut et désactivable. Il prépare l'intégration MTEE reportée sans encombrer le dossier des morceaux.

**Archives.** Si le fichier final est un `.zip` que l'extension peut lire elle-même, elle l'extrait et n'enregistre que les fichiers audio ; la pochette est conservée si l'option correspondante est active. Si l'archive ne peut être obtenue que par le téléchargement normal de Chrome (lien à usage unique, requête déclenchée par la page), elle est enregistrée telle quelle et signalée `Zip not extracted`. Le choix entre ces deux cas se fait au jalon 29.2.

**Code dans le dépôt MTEE.** L'extension vit dans `extensions/soundcloud-capture/`, en JavaScript ES modules sans compilation, documenté par JSDoc et testé avec `node --test`. Elle est chargée non empaquetée en mode développeur ; aucune publication sur le Chrome Web Store.

## Contrat de provenance (version 1)

À décrire dans `docs/integrations/soundcloud-capture.md` au jalon 29.2 :

    Downloads/Songs/
      <fichiers audio, noms fournis par le serveur, assainis>
      _mtee/
        <capture_id>.json        écrit après les fichiers audio

    <capture_id>.json
    {
      "schema": "mtee.capture/1",
      "capture_id": "<uuid v4>",
      "created_at_utc": "2026-09-29T12:34:56Z",
      "extension_version": "0.1.0",
      "source": {
        "platform": "soundcloud",
        "page_url": "https://soundcloud.com/<artist>/<track>",
        "playlist_url": "<facultatif, envoi groupé>",
        "track_title": "<tel qu'affiché>",
        "artist_display": "<tel qu'affiché>",
        "tags_displayed": ["<genre affiché>"]
      },
      "route": {
        "kind": "soundcloud_native | droploud | hypeddit | bandcamp",
        "gate_url": "<facultatif>",
        "steps": [{"kind": "email", "mode": "autofill", "done": true}]
      },
      "files": [
        {"name": "<nom relatif à Songs>", "size_bytes": 12345678, "mime": "audio/mpeg",
         "from_archive": "<nom de l'archive si extrait>", "completed_at_utc": "..."}
      ],
      "support": {"like": "done | already | skipped | failed",
                  "repost": "...", "comment": "posted | skipped | failed"}
    }

Le manifeste ne contient ni adresse e-mail, ni nom saisi, ni texte du commentaire, ni jeton, ni cookie, ni URL de téléchargement signée. Un champ absent reste absent. L'intégration MTEE future refusera un `schema` inconnu sans supprimer le fichier.

## Plan de travail et jalons

### Jalon 29.1 — Étudier les pages réelles

Avec l'utilisateur, ouvrir dans Chrome au moins un exemple par voie : téléchargement SoundCloud natif, Droploud, Hypeddit, Bandcamp (lien direct et, si disponible, lien par e-mail, plus un album en `.zip`), un morceau sans téléchargement et une playlist mêlant ces cas. Relever pour chacun : emplacement du lien sur SoundCloud (bouton d'achat, menu `More`, description), redirection par `gate.sc`, domaines traversés, étapes et ordre, champs de formulaire, fenêtres OAuth, nom et type du fichier final, mode de déclenchement (lien direct lisible, requête après clic, lien à usage unique).

Sur SoundCloud, relever aussi comment se présentent l'état liké/reposté, la zone de commentaire, le message affiché si l'utilisateur n'est pas connecté et le comportement d'une page de playlist longue (chargement progressif des titres).

Consigner les conditions d'utilisation de SoundCloud, Droploud, Hypeddit et Bandcamp relatives à l'automatisation et aux commentaires, avec URL et date. Ne pas copier les pages : noter la structure utile pour les fixtures synthétiques du plan 30. Chaque voie reçoit l'état `observé`, `documenté seulement` ou `non disponible` ; une voie non observée n'est pas développée.

### Jalon 29.2 — Prototyper les points incertains

Avec une extension jetable hors dépôt, vérifier : `chrome.downloads.download` vers `Songs/…` et `Songs/_mtee/…` ; écriture d'un JSON par URL `data:` depuis le service worker, sinon par document hors écran (`chrome.offscreen`) et `URL.createObjectURL` ; lecture d'une archive Bandcamp par `fetch` depuis l'extension avec les cookies de session, puis extraction en mémoire et enregistrement des entrées audio. Mesurer la mémoire sur une archive d'album réelle et fixer un plafond de taille au-delà duquel l'archive est enregistrée sans extraction.

Consigner les résultats et le mécanisme retenu dans `docs/integrations/soundcloud-capture.md`.

### Jalon 29.3 — Décisions utilisateur

Réalisé le 29 septembre 2026 ; voir `docs/decisions/29-soundcloud-capture.md`. Restent à fournir par l'utilisateur avant la recette réelle du plan 30 : la liste des commentaires et les valeurs du profil de formulaire. Ces données sont saisies dans les options de l'extension et ne sont jamais versionnées.

### Jalon 29.4 — Ordonner la série

Index et addendum de `PLAN.md` mis à jour le 29 septembre selon les décisions. Le plan 30 peut avancer pendant les séries en cours puisqu'il ne touche pas le code Python.

## Validation et acceptation

Ce plan est documentaire. Il est accepté lorsque chaque voie a un statut observé/documenté/non disponible avec sources datées, que les prototypes du jalon 29.2 ont donné un mécanisme retenu pour le manifeste et pour les archives, et que les décisions sont consignées. Contrôles : liens relatifs, encodage UTF-8, `git diff --check`. Aucun test applicatif n'est annoncé.

## Reprise et réexécution

Les observations sont datées ; une passerelle qui change d'interface demande de refaire sa seule ligne du jalon 29.1. Une décision utilisateur modifiée est ajoutée au journal et au fichier de décisions avec sa date ; l'ancienne reste visible.

## Preuves et livraison Git

Depuis la racine du dépôt :

    git status --short
    git diff --check
    git add -- "Plans d'exécution/29-soundcloud-cadrage.md" docs/integrations/soundcloud-capture.md docs/decisions/29-soundcloud-capture.md
    git diff --cached --check
    git diff --cached

    $mteeCommitMessage = Join-Path $env:TEMP 'mtee-step29-commit.txt'
    @'
    docs(capture): record SoundCloud route study and prototypes

    Changes: <routes observed, provenance contract, manifest and zip mechanisms>
    Validation: <pages examined, prototype measurements>
    Limits: <routes not observed, open points>
    '@ | Set-Content -LiteralPath $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitMessage

Pousser selon `PLANS.md` (fetch, comparaison, `git push origin main`, vérification des hashes).

## Progress

- [x] 2026-09-29 — Demande reçue ; dépôt, plans 10, 14, 17 et services concernés inspectés ; série 29–32 préparée.
- [x] 2026-09-29 — Réponses utilisateur consignées ; périmètre réduit à l'extension, actions de soutien ajoutées, 31 reporté, 32 abandonné (29.3, 29.4).
- [ ] Voies réelles observées et conditions d'utilisation consultées (29.1).
- [ ] Manifeste, écriture dans `Songs/_mtee/` et extraction d'archive prototypés (29.2).
- [ ] Liste de commentaires et profil de formulaire saisis par l'utilisateur dans l'extension (avant recette 30).

## Surprises & Discoveries

2026-09-29 — Les primitives `move_location_in_transaction` et `copy_location_in_transaction` subsistent dans `library_repository.py` sans appelant depuis le lot 17. Sans objet tant que le tri est abandonné.

2026-09-29 — Des sources publiques de 2026 indiquent que les étapes SoundCloud des passerelles Hypeddit sont devenues facultatives. Non vérifié dans un navigateur. Cela motive les actions de soutien demandées par l'utilisateur.

## Decision Log

2026-09-29 — Claude — Remise par fichiers dans le dossier Téléchargements plutôt qu'un serveur HTTP local ou un hôte natif. Motif : aucune surface réseau locale, pas d'écriture dans le registre, MTEE n'a pas besoin d'être ouvert.

2026-09-29 — Claude — Proposition initiale : aucune action engageant le compte automatisée, commentaires jamais postés. Remplacée le même jour par la décision utilisateur ci-dessous.

2026-09-29 — Utilisateur — Après un téléchargement réussi, liker, reposter et commenter avec un texte choisi dans sa propre liste, même si la passerelle ne l'exige pas, pour soutenir les artistes. Claude — Appliquer avec lecture d'état avant clic, un commentaire par morceau, délais et plafond quotidien ; OAuth et CAPTCHA restent manuels.

2026-09-29 — Utilisateur — Téléchargements dans `Downloads/Songs` ; envois groupés depuis les playlists, pas depuis les likes ; extraction des `.zip` ; profil de formulaire géré dans l'extension ; intégration MTEE reportée ; tri abandonné.

2026-09-29 — Claude — Conserver un manifeste de provenance désactivable dans `Songs/_mtee/`. Motif : faible coût, et prépare l'intégration MTEE reportée sans décision supplémentaire.

## Outcomes & Retrospective

Série préparée à partir du commit `a783620`, décisions intégrées après `7a1dda3`. Aucune page de passerelle ouverte, aucun prototype d'extension exécuté. Les constats externes proviennent d'une recherche web et restent à observer.

Note de révision — 2026-09-29, Claude : création du cadrage ; même jour, intégration des réponses utilisateur (actions de soutien, `Downloads/Songs`, playlists, archives, report de 31, abandon de 32).
