# Idée différée — import de playlists Spotify

Le 2026-09-30, l'utilisateur demande de conserver cette idée dans un Markdown, mais de ne pas l'ajouter au plan à réaliser. L'intégration Spotify est donc exclue de la livraison des playlists locales : aucun jalon, service, migration spécifique ou bouton Spotify à implémenter maintenant. Ce document est une mémoire de l'idée, pas un ExecPlan.

## Intention conservée

Proposer ultérieurement l'import par URL et par compte connecté, dont les playlists privées accessibles. L'utilisateur indique que sa configuration Spotify Developer est déjà prête ; aucun identifiant ni secret n'est demandé, copié ou versionné ici, et aucun accès réel n'a été testé pendant ce cadrage.

Rapprocher chaque morceau avec toute la bibliothèque locale et créer une playlist avec les fichiers disponibles. Les titres sans correspondance doivent garder leur position, titre et artiste dans une ligne informative grisée, être ignorés pendant la lecture et proposer `Find a local match` pour une association manuelle. L'utilisateur n'a pas retenu une recherche automatique après chaque scan.

L'interdiction de doublons décidée pour les playlists locales devra être conciliée avec les éventuelles répétitions Spotify lors d'un futur cadrage. Un import ponctuel ne constitue pas une demande de synchronisation continue. Les likes MTEE restent indépendants des likes Spotify.

## Documentation consultée le 2026-09-30

- [Get Playlist Items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items) documente une lecture réservée aux playlists possédées par le compte connecté ou auxquelles il collabore, avec refus 403 dans les autres cas.
- [Guide des changements de février 2026](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) décrit les restrictions du mode Development et les nouveaux endpoints.
- [Authorization Code with PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow) fournit le flux d'autorisation à réévaluer pour une application desktop sans secret client embarqué.

Ces capacités devront être revérifiées au moment de reprendre l'idée. Une URL publique arbitraire sans connexion n'est pas une capacité acquise. Un repli CSV/JSON a été évoqué, mais l'utilisateur n'a pas décidé de ce parcours avant de reporter l'intégration.

## Contraintes à garder pour une reprise

L'intégration reste facultative et ne bloque ni les playlists locales ni la lecture hors connexion. Les opérations réseau passent par les services Python hors du thread graphique. Les références Spotify ne deviennent pas des identités de fichiers locaux, ne réécrivent pas leurs tags et ne justifient pas l'association automatique d'un remix, live ou autre version sur la seule ressemblance du titre. Le flux importe des références, pas l'audio Spotify.

Lors d'une reprise explicitement demandée, distinguer documentation, accès accordés et essai réel ; préciser les correspondances ambiguës, les répétitions, la portabilité, les erreurs et le devenir des données à la déconnexion. Les contrats historiques du plan 14 peuvent être consultés alors, sans activer Shovel ni ses autres jalons.
