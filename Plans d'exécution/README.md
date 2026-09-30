# MTEE — index des plans d'exécution

Ces plans traduisent `PLAN.md` en étapes de développement vérifiables. Lire d'abord [les règles d'exécution](../PLANS.md). Les fichiers décrivent l'implémentation à venir : leur préparation ne signifie pas que l'application existe déjà.

## Playlists locales — 2026-09-30

Demande explicite de playlists fonctionnelles avec persistance, dossiers imbriqués, épingles, likes locaux, pochette/mosaïque, ordre manuel et import/export léger ou ZIP avec audio. Les décisions sont consignées dans `docs/decisions/34-playlists.md`. La maquette est préparée pour revue ; les services, modèles et migration restent à implémenter après sa validation. Ce périmètre n'active ni tags sémantiques, ni vues intelligentes, ni les autres fonctions de l'ancien plan 10. L'intégration Spotify est reportée par l'utilisateur et conservée uniquement dans `docs/ideas/spotify-playlists.md`.

| Plan | Catégorie et dépendances |
|---|---|
| [34 — Playlists locales](34-playlists-locales.md) | Revue QML, migration sauvegardée, backend local, modèles Qt, interface et échanges ; après le socle actuel et validation de la nouvelle maquette, sans attendre une revue de vocabulaire de tags |

## Analyse audio — 2026-09-30

Demande explicite de l'utilisateur : réintroduire l'analyse pour le BPM, la tonalité et la waveform, avec stockage permanent, un onglet de réglages et un lancement par clic droit. Le périmètre est limité à ces trois valeurs ; les silences, la loudness et les tags sémantiques restent hors périmètre.

| Plan | Catégorie et dépendances |
|---|---|
| [33 — Analyse audio](33-analyse-audio.md) | BPM précis, tonalité, waveform permanente, onglet Analysis, menus clic droit ; implémenté depuis les sources, recette réelle et build non réalisés |

## Capture SoundCloud — préparation du 2026-09-29

Cette série répond à la demande d’une extension Chrome qui récupère les téléchargements gratuits proposés sur SoundCloud (téléchargement natif, Droploud, Hypeddit, Bandcamp) et les enregistre dans `Downloads/Songs`. Elle soutient ensuite l’artiste par un like, un repost et un commentaire choisi dans la liste de l’utilisateur. Les réponses utilisateur du 29 septembre sont consignées dans `docs/decisions/29-soundcloud-capture.md` : seule l’extension est développée maintenant. Elle est préparée, non implémentée.

| Plan | Catégorie et dépendances |
|---|---|
| [29 — Cadrage et contrats](29-soundcloud-cadrage.md) | Étude des voies réelles, prototypes du manifeste et des archives, décisions ; documentaire |
| [30 — Extension Chrome](30-soundcloud-extension.md) | Extension MV3 : détection, passerelles, `Downloads/Songs`, extraction zip, lots de playlist, actions de soutien ; après 29.1–29.2, sans toucher au code Python |
| [31 — Inbox MTEE](31-soundcloud-inbox-mtee.md) | Reporté par l’utilisateur ; à réviser avant reprise |
| [32 — Tri vers les dossiers](32-soundcloud-tri-dossiers.md) | Abandonné par l’utilisateur ; conservé comme trace |

## Correctifs UX/UI — préparation du 2026-09-28

Cette série traduit la page Notion « MTEE — UX/UI » et les réponses utilisateur du 28 septembre. Elle poursuit les correctifs de l’existant sans déclarer la stabilisation entièrement validée ni réactiver les anciennes fonctionnalités différées. La demande actuelle porte sur les plans ; leur présence n’autorise pas à implémenter toute la série.

| Plan | Catégorie et dépendances |
|---|---|
| [23 — Cadrage et guide Luna](23-ux-ui-cadrage.md) | Décisions, couverture Notion, ordre, commandes communes et consignes prêtes à copier |
| [24 — Lecteur](24-ux-ui-lecteur.md) | Lancement effectif après pause ; premier correctif |
| [25 — Explorer](25-ux-ui-explorer.md) | Double-clic, sélection/révélation et conservation de l’ancre ; après 24 |
| [26 — Défilement et recherche](26-ux-ui-defilement-recherche.md) | Molette, scrollbars, focus et alignement ; après 25, maquette d’en-tête avant code concerné |
| [27 — Colonnes et tri](27-ux-ui-colonnes-tri.md) | Profil global, dates, covers, retrait de # et tri à trois états ; maquette confirmée par l’utilisateur, après 26 |
| [28 — Waveforms](28-ux-ui-waveforms.md) | Branche monochrome retenue ; lisibilité, repère de lecture et portion lue ; après 27 |

Le défaut de tri retenu est la date de création décroissante, sans flèche. Quitter la recherche conserve texte et résultats. Une cible masquée par cette recherche peut être jouée depuis l’arbre sans être révélée. Les colonnes sont configurées globalement. Le 29 septembre, l’utilisateur retient uniquement le rendu waveform monochrome et rejette les trois bandes.

## Stabilisation — trajectoire du 2026-09-25

La trajectoire fonctionnelle historique est suspendue jusqu’à la clôture de cette stabilisation. Les sept documents ci-dessous décrivent d’abord le cadrage et la validation, puis les six lots. Leur état distingue préparation, développement et recette ; une compilation réussie ne vaut pas validation manuelle. La série 23–28 ci-dessus prépare les nouveaux retours UX/UI sur la version issue de ces travaux.

| Plan | Livrable et prérequis |
|---|---|
| [16 — Cadrage et validation](16-stabilisation-cadrage.md) | Périmètre, contrats, preuves et coordination; préalable aux lots |
| [17 — Retirer l’analyse et les fonctions abandonnées](17-stabilisation-lot-01-retraits.md) | Retrait ciblé, compatibilité de migration, QML et packaging |
| [18 — Notifications, tâches et lecteur](18-stabilisation-lot-02-jobs-lecteur.md) | Progressions bornées, file légère, annulation et fermeture |
| [19 — Explorer, pochettes et waveform](19-stabilisation-lot-03-explorer-waveform.md) | Navigation asynchrone, cache de cover et calcul de waveform |
| [20 — Conversion fiable](20-stabilisation-lot-04-conversion.md) | Aperçus, processus annulables et publication reprenable |
| [21 — Corbeille Windows](21-stabilisation-lot-05-corbeille.md) | Recyclage natif, confirmation et résultats par fichier |
| [22 — Suite et distribution](22-stabilisation-lot-06-livraison.md) | Tests maintenus, fixtures reproductibles, CI et build final |

Ne pas poursuivre les étapes fonctionnelles 07–15 ci-dessous avant cette clôture. Elles sont conservées comme historique; leur présence dans l’index ne signifie plus qu’elles sont l’ordre actif.

La numérotation sépare la préparation technique, la revue des maquettes et chacune des livraisons fonctionnelles. Elle sépare également ML et Spotify/Shovel, réunis dans la section 4.11 du document initial mais distingués par les livraisons J et K. Le portage est un jalon ultérieur, hors de la première trajectoire Windows.

| Plan | Référence `PLAN.md` | Livrable et prérequis |
|---|---|---|
| [00 — Initialiser Git](00-git-et-gouvernance.md) | Demande utilisateur | Dépôt, règles, plans, commit et push initiaux |
| [01 — Préparer le socle](01-socle-technique.md) | §1, §4.0, étude précoce §2 | Environnement, fenêtre QML, persistance, tâches, distribution Windows ; après 00 |
| [02 — Valider les maquettes](02-maquettes-ux.md) | §3, jalon distinct | Interface révisée et validée le 2026-09-24 : barre d'activités, onglets, listes Spotify, îlot, Fullscreen player, Convert ; après 01, avant fonctions |
| [03 — Explorer les dossiers](03-explorateur.md) | A, §4.1 | Arborescence, onglets, deux panneaux, Table/Artwork et tags lus ; après 02 |
| [04 — Lire les morceaux](04-lecteur.md) | B, §4.2 | libmpv, file stable, îlot de lecture et Fullscreen player ; après 03 |
| [05 — Éditer les métadonnées](05-metadonnees.md) | B, §4.3 | Sauvegarde par champ, multisélection, annulation et conflits ; après 04 |
| [06 — Gérer les fichiers](06-fichiers.md) | C, §4.4 | Renommer, déplacer et mettre à la corbeille ; après 05 |
| [06b — Corriger les retours de recette](06b-correctifs-recette.md) | Recette utilisateur du 2026-09-25, §3 et §4.1–4.4 | A avant 07 : stabilité, navigation, lecteur, colonnes et fichiers ; B au début de 07 : métadonnées ; C avec 10 : critères de dates |
| [07 — Convertir](07-conversion.md) | D, §4.5 | FFmpeg/ffprobe, copies vérifiées et jobs annulables ; après 06 |
| [08 — Afficher la waveform](08-waveform.md) | E, §4.6 | Cache, zoom, repère de lecture et boucle A/B ; après 07 |
| [09 — Analyser sans ML](09-analyse-sans-ml.md) | F, §4.7 | Mesures, tempo et tonalité, résultats versionnés ; après 08 |
| [10 — Organiser et rechercher](10-tags-recherche-playlists.md) | G, §4.8 | Revue du vocabulaire, tags, filtres et playlists ; après 09 |
| [11 — Extraire et éditer](11-edition-audio.md) | H, §4.9 | Extraits, coupes, fondus et variantes ; après 10 |
| [12 — Échanger avec Rekordbox](12-rekordbox.md) | I, §4.10 | Import XML, export, rapport des compatibilités ; après 11 |
| [13 — Évaluer ML et similarité](13-ml-similarite.md) | J, première partie §4.11 | Évaluation sur corpus, suggestions locales ; après 12 |
| [14 — Relier Spotify/Shovel](14-spotify-shovel.md) | K, seconde partie §4.11 | Contrats vérifiés et connexion facultative ; après 13 dans l'ordre de livraison |
| [15 — Porter sur Linux/macOS](15-portage-multiplateforme.md) | Contrôle commun final | Jalon différé, activé séparément après stabilisation Windows |

Chaque plan contient ses propres critères d'acceptation, cas d'échec, procédures de reprise et modèle de commit détaillé. Une étape est livrée après vérification du comportement depuis les sources et du push. Le build Windows ne fait pas partie de la clôture ordinaire d'une tâche ou d'un jalon : il est exécuté seulement si la demande porte explicitement sur le packaging ou la distribution, même lorsqu'un ancien plan contient une commande de build. Les commits de développement ne sont créés qu'après les travaux correspondants ; le dépôt documentaire reçoit d'abord son commit de préparation.

Pour la suite nocturne préparée le 2026-09-25, suivre l'ordre détaillé dans [06b](06b-correctifs-recette.md) : correctifs A, début de 07 (runtime et fixtures), complément métadonnées B, fin de 07, 08, 09, puis revue 10 et complément C. Le dossier de revue du vocabulaire doit être prêt avant de solliciter l'utilisateur ; sans accord explicite déjà consigné, la session s'arrête à ce dossier avant l'implémentation fonctionnelle de 10. Les étapes 11+ restent hors de cette session. Le complément contient une consigne de lancement prête pour GPT-6 Luna.

Les choix ajoutés par les plans sont des propositions opérationnelles : UUID internes stables, services nommés, caches révisés, tests ciblés et chemin de packaging. Les versions précises et la distribution des dépendances natives sont vérifiées puis verrouillées à l'étape qui les introduit. Les maquettes et la taxonomie comportent une revue utilisateur explicite ; Spotify, Shovel, les modèles ML et les profils de platines dépendent de preuves recueillies lors de leur étude.

Le travail parallèle porte sur des modules ou tests isolés après stabilisation de leurs contrats. L'intégration et les pushes restent séquentiels. Les étapes 03 à 14 suivent l'ordre produit même lorsqu'une dépendance technique pourrait permettre de commencer plus tôt.

Pour lancer le développement, demander par exemple : « Exécute le prochain jalon du plan concerné depuis les sources, maintiens son suivi, puis crée le commit détaillé et pousse-le. » Demander séparément un build si une distribution Windows est voulue. L'accord sur les maquettes ne se déduit pas de l'accord sur le développement du socle.
