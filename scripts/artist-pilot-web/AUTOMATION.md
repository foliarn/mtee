# Pilotage depuis une tâche locale

La tâche ChatGPT/Codex locale recherche elle-même les artistes avec ses outils web,
sur l'abonnement de l'utilisateur. `artist_research_session.py` gère les lots,
MusicBrainz et l'import contrôlé : aucune invocation IA ni clé API. Le serveur web
n'a plus de bouton de lancement ni de worker IA branché. Son onglet Job affiche
la progression et permet de recharger les propositions pour la revue humaine.

Le prompt complet, y compris chemins et commandes, est dans **RESEARCH-PROMPT.md**.
Sa première phase est un contrôle de statut sans recherche ni écriture ; la tâche
attend le lancement de l'utilisateur. Après lancement, elle traite la file sans
demander d'approbation à chaque lot. Les validations restent une étape humaine.

## Script

```powershell
.\.venv\Scripts\python.exe scripts/artist_research_session.py --output <dossier-collection> --database <base-sqlite> status
```

Remplacer `status` par :

- `next --size 5` : réserver ou retrouver le lot actif (un à dix artistes).
- `collect` : chercher seulement ce lot dans MusicBrainz ; aucune recherche IA.
- `progress --message "Recherche : artiste"` : journaliser la recherche du chat.
- `import --result <fichier.json>` : contrôler puis publier les propositions.
- `pause --message "Raison"` : conserver le lot et noter une interruption.

## Reprise et contrôles

Le lot et ses IDs sont persistants. Les réponses sont stockées dans le sous-dossier
privé `research/`, la session dans `research-session.json` et les données MusicBrainz
dans le checkpoint/cache existant. Un verrou système protège les commandes concurrentes.
Les écritures JSON sont atomiques et une interruption entre publication et reçu est
récupérée par `next`. Une erreur de collecte conserve le lot ; relancer `collect`
réutilise ses recherches réussies. Aucun redémarrage automatique et aucune boucle
de relance de l'IA. L'agent peut reprendre un lot après une compaction de contexte.

Le JSON résultat contient exactement `batch_id` et `observations`. Le lot doit être
complet, avec IDs uniques, champs/types stricts, profils canoniques, sources HTTPS
et preuve pour chaque profil. Une identité confirmée nécessite une source ; une
identité non résolue ne reçoit pas de profil. Le schéma ne garantit pas la vérité
des pages : l'IA doit les consulter et l'utilisateur révise les propositions.
Les résultats valides identiques sont idempotents ; un lot clos ne peut être réécrit.

Les artistes validés et déjà enrichis sont exclus de la file. Une validation survenue
pendant la recherche reste prioritaire ; l'import ne modifie jamais les tables de
choix humains, les titres/crédits/audio, les genres des morceaux ni les suivis Spotify.
Le front conserve les brouillons lors du rechargement volontaire des propositions.

Le prompt propose cinq artistes, jusqu'à six titres/collaborations et cinq candidats
MusicBrainz par artiste, deux requêtes web usuelles et quatre si ambigu. Ces limites
visent à borner le temps et le contexte, sans inventer une identité pour remplir une
colonne. Aucune estimation financière ou mesure de tokens de la tâche n'est inventée.

L'ancien module `artist_enrichment_worker.py` reste dans l'historique de la préparation
et conserve ses tests, mais le serveur ne l'instancie plus et refuse son endpoint de
lancement. Aucun audit réel n'a été lancé lors de cette livraison.
