# MTEE — index des plans d'exécution

Ces plans traduisent `PLAN.md` en étapes de développement vérifiables. Lire d'abord [les règles d'exécution](../PLANS.md). Les fichiers décrivent l'implémentation à venir : leur préparation ne signifie pas que l'application existe déjà.

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

Chaque plan contient ses propres critères d'acceptation, cas d'échec, procédures de reprise et modèle de commit détaillé. Une étape est livrée après vérification du comportement, de la distribution Windows et du push. Les commits de développement ne sont créés qu'après les travaux correspondants ; le dépôt documentaire reçoit d'abord son commit de préparation.

Pour la suite nocturne préparée le 2026-09-25, suivre l'ordre détaillé dans [06b](06b-correctifs-recette.md) : correctifs A, début de 07 (runtime et fixtures), complément métadonnées B, fin de 07, 08, 09, puis revue 10 et complément C. Le dossier de revue du vocabulaire doit être prêt avant de solliciter l'utilisateur ; sans accord explicite déjà consigné, la session s'arrête à ce dossier avant l'implémentation fonctionnelle de 10. Les étapes 11+ restent hors de cette session. Le complément contient une consigne de lancement prête pour GPT-6 Luna.

Les choix ajoutés par les plans sont des propositions opérationnelles : UUID internes stables, services nommés, caches révisés, tests ciblés et chemin de packaging. Les versions précises et la distribution des dépendances natives sont vérifiées puis verrouillées à l'étape qui les introduit. Les maquettes et la taxonomie comportent une revue utilisateur explicite ; Spotify, Shovel, les modèles ML et les profils de platines dépendent de preuves recueillies lors de leur étude.

Le travail parallèle porte sur des modules ou tests isolés après stabilisation de leurs contrats. L'intégration et les pushes restent séquentiels. Les étapes 03 à 14 suivent l'ordre produit même lorsqu'une dépendance technique pourrait permettre de commencer plus tôt.

Pour lancer le développement, demander par exemple : « Exécute le plan 01, maintiens son suivi, valide la distribution Windows, puis crée le commit détaillé et pousse-le. » L'accord sur les maquettes ne se déduit pas de l'accord sur le développement du socle.
