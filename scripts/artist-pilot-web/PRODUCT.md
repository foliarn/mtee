# Outil de revue des artistes

<!-- impeccable:product-schema 1 -->

## Platform

web

## Utilisateur et objectif

Outil personnel pour examiner un pilote de 50 morceaux issus d’une collection de DJ. Rendre les artistes recherchables, distinguer leurs métiers, vérifier leurs profils externes et proposer le tri du bloat. Le goût de l’utilisateur décide du tri et du suivi Spotify, après écoute.

## Périmètre confirmé

Front web local autonome pour les rapports, tableaux, sources et revue. MTEE fournit les crédits existants en lecture seule ; cet outil ne s’intègre pas à son interface, ne change pas ses données et n’effectue aucune action Spotify. Producer, DJ, Singer et MC peuvent se cumuler. Bass-related concerne la carrière ; la présence dans une collection bass ne suffit pas à l’établir. Les genres d’artiste et les genres de morceaux restent distincts.

## Implémentation du pilote

Mode de revue demandé le 5 octobre : les propositions inchangées sont acceptées par défaut. L'utilisateur corrige les exceptions dans un tableau pleine largeur, puis enregistre ses corrections en une fois. Aucun compteur de dossiers à traiter, aucune confirmation individuelle et aucun bouton Suivant. Les identités introuvables et informations absentes restent signalées, sans invention. La recherche et le défilement continu doivent rester utilisables pour 2 000 artistes ; seules les corrections sont écrites.

HTML/CSS/JavaScript servis par Python standard sur 127.0.0.1. Choix technique ordinaire effectué pour garder l’outil local simple ; la préférence de framework demandée dans la conversation demeure ouverte. Construction directe dans le code pour cet outil de tableaux ; aucun réglage de workflow durable déduit du silence de l’utilisateur.

## Preuves disponibles

Snapshot privé, échantillon, candidats MusicBrainz et observations IA sourcées dans le dossier de pilote ignoré par Git. Les données personnelles et les captures de recette ne sont pas versionnées. Les décisions humaines sont stockées séparément. Les images, la taxonomie et une automatisation LLM payante ne sont pas validées par ce pilote.
