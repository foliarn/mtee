# Outil de revue des artistes

<!-- impeccable:product-schema 1 -->

## Platform

web

## Utilisateur et objectif

Outil personnel pour examiner un pilote de 50 morceaux issus d’une collection de DJ. Rendre les artistes recherchables, distinguer leurs métiers, vérifier leurs profils externes et proposer le tri du bloat. Le goût de l’utilisateur décide du tri et du suivi Spotify, après écoute.

## Périmètre confirmé

Front web local autonome pour les rapports, tableaux, sources et revue. MTEE fournit les crédits existants en lecture seule ; cet outil ne s’intègre pas à son interface, ne change pas ses données et n’effectue aucune action Spotify. Producer, DJ, Singer et MC peuvent se cumuler. Bass-related concerne la carrière ; la présence dans une collection bass ne suffit pas à l’établir. Les genres d’artiste et les genres de morceaux restent distincts.

## Implémentation du pilote

Producer et DJ restent deux cases et deux filtres séparés. Par défaut, une proposition Producer coche aussi DJ. Cocher Producer coche DJ dans la ligne et le dossier ; DJ reste modifiable séparément, et une exception enregistrée reste prioritaire. Les preuves de carrière d’origine restent consultables.

Mode de revue révisé le 6 octobre : tableau sans titres explicatifs, pages de 100 artistes maximum, bouton « Valider cette page » actif même sans correction. La validation atomique porte sur les lignes affichées après filtrage ; les brouillons des autres pages restent en attente. Les 42 choix du pilote sont préservés. Producer active toujours DJ, avec exception indépendante possible. Sans information, le tri affiche Garder et Bass-related Non ; les preuves et anciennes valeurs restent distinctes. Écarter conserve l’artiste et lui attribue idgaf dans la revue et l’export.

Le Récap ne contient plus de carte sur le mode de revue ni de texte introductif. Rôles, tri, profils et catégories sont cliquables et ouvrent le tableau filtré. Les genres se traitent par morceau : tags génériques ignorés, tags précis conservés, contradiction House rejetée et signalée seulement avec un contexte explicite sourcé. Aucun genre d’artiste n’est propagé aux morceaux. Les corrections ponctuelles et contextes de carrière sont dans un genre-rules.json privé, séparé des tags observés.

HTML/CSS/JavaScript servis par Python standard sur 127.0.0.1. Choix technique ordinaire effectué pour garder l’outil local simple ; la préférence de framework demandée dans la conversation demeure ouverte. Construction directe dans le code pour cet outil de tableaux ; aucun réglage de workflow durable déduit du silence de l’utilisateur.

## Preuves disponibles

Snapshot privé, échantillon, candidats MusicBrainz et observations IA sourcées dans le dossier de pilote ignoré par Git. Les données personnelles et les captures de recette ne sont pas versionnées. Les décisions humaines sont stockées séparément. Les images, la taxonomie et une automatisation LLM payante ne sont pas validées par ce pilote.


## Collection complète et validations

Depuis le 6 octobre, tous les morceaux sont consultables avec recherche et pages de 100. Artistes contient les dossiers non validés ; Validés contient les validations enregistrées, éditables. Le bouton valide uniquement la page et affiche ensuite le lot suivant. SQLite dans la base du catalogue est la source de vérité lorsque --database est fourni ; le pilote JSON reste historique. Les 42 validations préexistantes sont importées sans doublons. Les autres dossiers restent explicitement À enrichir, sans identité inventée.

Onglet Job autonome : démarrage explicite de l'enrichissement, reprise/pause/arrêt, erreurs et journal. Modèle fixé à GPT-6 Luna / low sur abonnement ChatGPT. Les propositions restent à revoir ; aucun lancement automatique ni suivi Spotify. Contrat : AUTOMATION.md.
