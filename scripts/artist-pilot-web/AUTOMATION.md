# Enrichissement depuis la revue locale

Le serveur `scripts/artist_pilot_server.py` prépare un worker inactif. L'onglet **Job**
permet de démarrer/reprendre, mettre en pause après le lot, arrêter l'audit en cours
et réessayer les erreurs. Un redémarrage du serveur ne reprend jamais automatiquement.

```powershell
.\.venv\Scripts\python.exe scripts/artist_pilot_server.py --output <dossier-collection> --database <base-sqlite> --port 8765
```

## Contrat

- GPT-6 Luna (`gpt-6-luna`), raisonnement `low`, lots de cinq artistes par défaut
  (réglables de un à dix), un audit à la fois. Aucun changement automatique de modèle.
- `codex login status` doit confirmer une connexion ChatGPT. Le worker retire les
  variables API OpenAI héritées et impose le fournisseur OpenAI et la connexion
  ChatGPT. Il ne configure aucune clé API et refuse une connexion API.
- MusicBrainz d'abord : cache, cadence minimale de 1,1 s, délais/reprises du client
  existant. Les candidats et liens ne deviennent pas automatiquement des identités.
- Audit par recherche web native de Codex, titres locaux pour les homonymes,
  réponse structurée et preuves HTTPS pour les propositions et profils.
  Le prompt reçoit au maximum six titres/collaborations, cinq candidats et deux
  détails MusicBrainz par artiste ; les réponses complètes restent dans le cache local.
- Les artistes validés et les observations déjà présentes sont exclus de la file.
  Les 42 choix historiques restent prioritaires. Une validation pendant un audit
  empêche la publication de sa proposition. Aucune validation humaine automatique.
- Les propositions vont dans `observations.json`, les checkpoints MusicBrainz dans
  `musicbrainz.json`, la file et le journal borné dans `automation.json`. Tous restent
  privés et ignorés par Git. Les écritures sont atomiques. Un verrou système empêche
  deux workers de traiter la même collection simultanément.
- Les corrections humaines restent séparées dans SQLite. Les morceaux, crédits,
  fichiers audio et suivis Spotify ne sont pas modifiés. Aucun genre de morceau
  n'est déduit de la carrière de l'artiste.

## Exploitation

La pause termine et publie le lot actif. Arrêter interrompt Codex et remet le lot
en attente ; une requête MusicBrainz déjà commencée peut finir avant cet arrêt.
Le résultat d'un audit interrompu n'est pas publié. Les recherches MusicBrainz
réussies sont réutilisées à la reprise. Une erreur de collecte, de schéma, de quota,
d'authentification ou de disponibilité du modèle met le job en pause ; aucune
boucle de relance automatique. « Réessayer les erreurs » remet ces artistes en file.
Chaque audit est limité à dix minutes.

Le front interroge le statut toutes les deux secondes dans l'onglet Job. Il affiche
la phase, les artistes du lot, les compteurs, le journal et les tokens que Codex
expose en fin d'audit. Les tokens indiquent le volume observé, pas les quotas restants
du compte. « Actualiser les propositions » recharge les données sans supprimer les
brouillons locaux. La session CLI est éphémère dans un dossier temporaire extérieur
au dépôt ; elle reçoit les noms/titres et candidats, aucun chemin audio ni contenu
de la base. Le schéma et le résultat de cette session sont supprimés à sa fermeture.

Lancement réel volontairement non effectué pendant la préparation : qualité des
recherches et disponibilité du modèle sur le compte à vérifier lors du premier lot.
