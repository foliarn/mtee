# MTEE — index des plans d'exécution

## MVP v0.1 — 2026-10-14

Cadrage décidé en discussion avec l'utilisateur : publier MTEE v0.1 (dépôt public, portfolio) sans plugins, Genre Manager ni Artist manager. Étapes réalisées dans des worktrees puis fusionnées sur `main` ; la recette interactive de l'utilisateur reste à faire pour chacune.

| Plan | Contenu et état |
|---|---|
| [111 — Retrait des managers du cœur](111-retrait-managers-du-coeur.md) | Artist manager déplacé dans `plugins/`, migrations 019/020/022/023 propres aux plugins, interface des plugins masquée ; fusionné (`30b6a6d`) |
| [112 — Vue Artists depuis les tags](112-vue-artistes-depuis-tags.md) | Règles de découpage, choix utilisateur (migration 026), index, vue Artists, liens d'artistes, top artistes ; maquette validée, fusionné (`8f95263`, `0062a05`) |
| [113 — Journal d'écoute](113-journal-ecoutes.md) | Écoutes permanentes (migration 024), seuil de 30 s, prêt pour une future synchronisation ; fusionné (`234416a`) |
| [114 — Paramètres et profil](114-parametres-et-profil.md) | Paramètres en onglets internes, page Profil, données et confidentialité (sauvegarde, restauration) ; maquette validée avec correction de disposition, fusionné (`d0f9233`, `6058161`) |
| [115 — Statistiques du profil](115-statistiques-profil.md) | Périodes calendaires, totaux, tops, graphique, colonnes Plays / Last played ; fusionné avec 114 |
| [116 — Normalisation du volume](116-normalisation-volume.md) | Loudness mesurée par Analyze (migration 025), gain par morceau, plafond de pic −2 dBFS et +12 dB ; fusionné (`febff03`, `6058161`) |
| [117 — Contrôles média Windows](117-controles-media-windows.md) | SMTC : touches multimédias, casques, panneau Windows ; fusionné (`7515166`) |
| [118 — Nettoyage approfondi](118-nettoyage-profond.md) | Base de référence (lint, types, tests), inventaire du code mort et des prototypes, puis base verte, lint, nettoyage sémantique et découpage des monolithes ; phases 1 à 4 faites (code mort et prototypes supprimés, scripts archivés, base de tests rétablie hors un plantage à plusieurs runtimes, ruff et pyright à 0, exceptions revues), phases 5-6 à venir |
| [118b — Découpage de WorkspaceModel](118b-decoupage-workspace-model.md) | Façade QML inchangée, 11 modules collaborateurs extraits, workspace_model.py 3 526 → 3 078 lignes ; fusionné (`0d49cdb`) |

Suite prévue : nettoyage approfondi du code, préparation du dépôt public (réécriture de l'historique, documents privés séparés), logo, puis publication de v0.1.0. Licence décidée : GPL-3.0-or-later (`ca35119`).

## Genre Manager en plugin — préparation du 2026-10-09

Le [plan 110 — Genre Manager en plugin](110-plugin-genre-manager.md) est la référence active et remplace 109. Il transcrit le cadrage utilisateur : travail par dossier ou playlist, genre principal et secondaires ordonnés, tags libres initialement vides, validation Reviewed, rangement physique des seuls morceaux vérifiés et genres d'artistes déduits avec abstention sur les remix incertains.

Ordre d'exécution : état initial et mesures (110.0), deux maquettes QML manipulables sélection/pinceau (110.1), **essai et revue explicite de l'utilisateur (110.2)**, module interne et données neuves (110.3), classement/catalogue/revue (110.4), rangement récupérable (110.5), artistes et Uncertain (110.6), recette et publication (110.7). Les maquettes 110.1 ont été révisées après un premier retour visuel ; l'utilisateur a ensuite autorisé le branchement fonctionnel fidèle au front MTEE. Le [dossier de revue](../docs/ux/review-110-genre-manager.md) distingue les captures historiques du prototype et celles des quatre pages intégrées. Les copies 020/021 du banc initial sont historiques : 021 n'a pas été restaurée, et le schéma livré emploie 022 puis 023. Le ressenti au pointeur et l'écoute audible restent à vérifier dans l'application interactive.

Prérequis : socle courant après rollback `1eab96e`, préservation des travaux du lecteur et des listes publiés séparément, lecture de `PLANS.md`, inventaire de compatibilité des bases 020/021 sur copies. L'ancienne interface n'est pas à rétablir. Info et les listes ordinaires attendent leurs maquettes ultérieures. Aucun packaging automatique. Le prototype reste isolé de l'application principale ; voir le [rapport de validation](../docs/validation/110-plugin-genre-manager.md).

## Genres des morceaux et workflow de tri — préparation du 2026-10-07

Historique remplacé par 110 : les descriptions ci-dessous conservent le cadrage du 7 octobre et ne doivent pas être exécutées en parallèle du nouveau plan.

Le [plan 109 — Genres des morceaux, manager et tri](109-genres-morceaux-manager-tri.md) est la référence opérationnelle issue du [brief 108](../docs/decisions/108-arbre-des-genres.md) et des clarifications du 7 octobre. Il comporte deux lots : **1. Associer les genres précis des dossiers aux morceaux ; 2. Implémenter le manager complet, la création rapide, le pinceau et les filtres ET/OU/exclusion, puis retirer les anciens genres d'artistes de 107**. Les tags locaux, méta-familles, Ctrl+Z, sauvegardes et suppression forcée depuis les paramètres sont inclus.

Prérequis : socle actuel et lecture des contrats 10, 106 et 107 ; maquettes ciblées et revue avant le code fonctionnel, tableau réel vérifié avant application groupée. Le vocabulaire et le classement sans genre principal sont validés. Aucun suivi d'écoute, lecture automatique ni variante de puces par ligne. Aucun fichier de la collection n'est modifié ; son rangement physique viendra plus tard. Cette préparation ne lance pas l'implémentation. [Rapport documentaire](../docs/validation/109-genres-morceaux-manager-tri.md).

Ces plans traduisent `PLAN.md` en étapes de développement vérifiables. Lire d'abord [les règles d'exécution](../PLANS.md). Les fichiers décrivent l'implémentation à venir : leur préparation ne signifie pas que l'application existe déjà.

## Pilote autonome d'enrichissement — 2026-10-05

Le [plan 105 — Pilote artistes](105-pilote-enrichissement-artistes.md) couvre un essai de 50 morceaux, les candidats MusicBrainz, un complément web audité et la revue humaine dans un front web local. À la demande de l'utilisateur, ce front est un outil d'étude séparé : aucune intégration à MTEE ni action de suivi Spotify. Les données et décisions personnelles restent ignorées par Git. Ce pilote n'ajoute pas de prérequis aux livraisons applicatives.

## Artist manager — préparation du 2026-10-02

Le [plan 104 — Identification des artistes et Artist manager](104-artist-manager-importation.md) est la référence active après le refus des maquettes 103. Il reprend le sketch utilisateur et toutes les décisions : collection complète alimentée par Analysis, inscription unique par morceau, parcours initial en trois étapes, correction par Edit, confirmation du résultat filtré, renommage systématique `Artiste(s) - Titre` et tags facultatifs. Les séparateurs sont uniquement virgule et `&` ; original explicite et remixer sont crédités, les versions restent dans le titre.

Ordre : livraison A (104.1–104.5), tables/backend et interface de traitement intégrée ; retour utilisateur ; livraison B (104.6–104.7), catalogue et pages Artists au-dessus de la même sidebar. Le plan contient la consigne pour exécuter A. Préparation documentaire uniquement ; aucun test UI et aucun build Windows prévus. Le plan 103 et ses captures restent historiques, sans validation acquise. Les paragraphes du 1er octobre ci-dessous ne définissent plus cette implémentation.

État du 2 octobre 2026 : A et B sont réalisés dans le code (rapport `docs/validation/104-artist-manager.md`) ; la recette interactive de l'utilisateur reste à faire.

## Échantillonnage mapping et tagging — préparation du 2026-10-01

Suite du 2026-10-01 : l'utilisateur clôt les itérations d'étude après `run_followup_02`. Le [plan 103 — Catalogue Artists et revue locale](103-artistes-revue-mapping.md) prépare les maquettes, puis une revue persistante avec correction manuelle et validation par lots. Il intègre les limites du diagnostic ; les maquettes sont à examiner avant le backend. Les écritures de tags et renommages effectifs appartiendront au lot suivant. La description de préparation 102 ci-dessous est historique ; ses propositions ne sont pas devenues des confirmations d'identité.

Le [plan 102 — Échantillon de la collection](102-echantillonnage-mapping-tagging.md) prépare une étude à lancer avec Luna : inventaire local en lecture seule, puis 100 fichiers aléatoires et 50 cas ciblés au maximum, propositions argumentées et rapport à retourner à la conversation de cadrage. La collection annoncée comprend environ 2 850 fichiers MP3/FLAC/WAV/AIFF/M4A pour MTEE et Rekordbox. Aucun accès API SoundCloud ; Spotify en mode développement n'est pas requis pour cette étude. Les pochettes et TIDAL sont reportés. Ce plan ne réactive ni les anciennes intégrations, ni le renommage effectif, ni le développement de l'extension. Il contient une consigne prête à copier dans Luna et les fichiers attendus. Préparation uniquement ; aucun échantillon exécuté ni build Windows.

## Playlists et interactions des morceaux — préparation du 2026-10-01

Le [plan 98 — Playlists, glisser-déposer et Play/Pause](98-playlists-glisser-deposer-play-pause.md) couvre uniquement les features Notion 2, 3 et 4 et le bonus d'édition par titre/survol de pochette. Il précise la création immédiate avec un nom fondé sur le nombre de playlists présentes, les indicateurs et le réordonnancement par lots dans List/Artwork, et le bouton Play/Pause à gauche des pochettes, hors file d'attente. Les décisions utilisateur, les fichiers à modifier, les jalons, les tests et 24 cas de recette sont inclus pour Luna. La préparation est documentaire ; la maquette ciblée reste à préparer et valider avant le code fonctionnel. Aucun build Windows n'est prévu.

## Contrôles de lecture et navigation — préparation du 2026-10-01

Le [plan 99 — File, commandes de lecture, navigation et désélection](99-controles-lecture-file-navigation.md) traduit exclusivement les features 9 à 13 de la page Notion « MTEE — fixes & idées / Segmentation » et les deux séries de réponses utilisateur du 1er octobre. La numérotation des features Notion est indépendante des anciens ExecPlans 09–13.

## Refonte du Fullscreen player — préparation du 2026-10-01

Le [plan 100 — Refonte du Fullscreen player et de sa waveform](100-plein-ecran-waveform.md) transcrit deux séries de réponses utilisateur. Il couvre la carte principale colorée d'après la pochette, la waveform RMS à barres avec survol et scrub audio, deux pages séparées par une transition sans état intermédiaire, et la page 2 (Artiste provisoire, Track details, Queue). Livré le 1er octobre 2026 (jalons 100.0 à 100.7) ; le rapport [docs/validation/100-plein-ecran-waveform.md](../docs/validation/100-plein-ecran-waveform.md) liste ce qui est vérifié automatiquement et ce qui reste à observer dans une session interactive. Le numéro sert seulement à distinguer ce plan des précédents. Aucun build Windows n'est prévu.

## Retours de recette — préparation du 2026-10-01

Le [plan 101 — Sélection, sidebar, file et historique, tâches, couleur du plein écran et playlists](101-retours-sidebar-file-taches-playlists.md) transcrit une liste de retours et quatre séries de réponses utilisateur. Il couvre la désélection complète, le clic des dossiers de l'Explorer, le rafraîchissement des dossiers ouverts, l'historique d'écoute persistant, la page Tasks, la couleur d'accent du plein écran et l'en-tête de playlist façon Spotify. Une porte de revue a arrêté l'exécution après les maquettes ; le panneau Queue/History (101.9) et le menu « Add to playlist » compact (101.10) ont suivi après l'accord de l'utilisateur. Livré le 1er octobre 2026 (jalons 101.0 à 101.11) ; le rapport [docs/validation/101-retours-sidebar-file-taches-playlists.md](../docs/validation/101-retours-sidebar-file-taches-playlists.md) liste les contrôles réels et la recette U1–U13 à faire par l'utilisateur. Pas de tests UI demandés à l'agent ; aucun build Windows n'est prévu.

Il prépare l'ajout FIFO par clic droit, les doublons et ajouts conservés lors d'un changement de morceau, la file réordonnable par glisser-déposer et persistée avec courant/position restaurés en pause, Espace hors saisie, l'historique de toutes les pages par panneau via les boutons latéraux, Précédent à trois secondes et la désélection au clic dans le vide. Il repose sur le socle actuel et les playlists du plan 34. La revue de maquette de file précède son implémentation ; la préparation du plan n'est pas une autorisation de développement. Aucun build Windows n'est prévu.

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
