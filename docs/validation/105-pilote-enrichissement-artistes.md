# Validation 105 — pilote artistes et revue web locale

Le 5 octobre 2026, essai réel exécuté depuis les sources. Le front est un outil autonome de rapports et de revue, conformément à la dernière demande utilisateur. Aucune interface, migration ou fonctionnalité MTEE modifiée par ce lot. Le suivi Spotify reste manuel.

## Résultats observés

La base existante contient 1 976 artistes établis, 382 provisoires et 2 828 morceaux. Le snapshot utilisé contient les 2 812 morceaux à crédits/revue confirmés ; les profils provisoires ne deviennent pas des identités externes à rechercher.

L'échantillon ciblé couvre 50 morceaux distincts et 42 artistes. Tous les sélecteurs ont trouvé le nombre demandé. Couverture structurelle : 36 crédits solo, 14 collaborations, 5 remixes, 2 bootlegs/edits/flips et 7 cas de noms courts ; catégories cumulables, donc compteurs non additionnables. Aucune catégorie structurelle demandée n'est absente. Cette sélection ciblée n'est pas représentative statistiquement de toute la collection.

MusicBrainz : 42 recherches terminées, dont un résultat vide ; 95 appels HTTP, 106,015 secondes, aucun cache préexistant utilisé et aucune interruption. « Recherche réussie » signifie réponse du fournisseur, pas identité correcte. Un score textuel élevé ne vaut pas une confirmation. Le complément web et l'audit des dossiers sont réalisés par l'agent dans la session ; ils ne constituent pas un script LLM autonome sans supervision.

L'audit IA propose 36 profils Spotify et 31 SoundCloud. Les 42 identités sont réparties en 33 rapprochées, 7 à consolider et 2 non résolues. Seize dossiers ont au moins un point à vérifier. Le tri proposé compte 36 garder, 3 bloat possible et 3 à déterminer. Les rôles sont cumulatifs : 28 Producer, 17 DJ, 10 Singer et 5 MC. Les contradictions restent visibles, notamment homonymes, liens communautaires partagés, deux IDs possibles pour un artiste et genres discordants. Les rôles de carrière insuffisamment sourcés sont explicitement à consolider.

Les 42 décisions personnelles du pilote livré restent à faire. Aucun test navigateur n'a validé un artiste à la place de l'utilisateur : les écritures de recette utilisent une copie indépendante. Aucun audio ouvert, modifié ou renommé par l'outil. Les images et une taxonomie des genres ne sont pas validées. Tokens IA et prix total non exposés/non mesurés ; ne pas les annoncer comme zéro.

## Outil livré

`scripts/artist_enrichment_pilot.py` : snapshot SQLite en lecture seule, sélection reproductible, dossiers d'artistes, recherche MusicBrainz avec cache et checkpoint, import d'observations sourcées, rapport Markdown et CSV initial de revue. Bibliothèque standard uniquement. Les erreurs fournisseur restent distinctes des réponses vides ; les erreurs sont retentables, les succès sont conservés à la reprise.

`scripts/artist_pilot_server.py` et `scripts/artist-pilot-web/` : serveur lié à `127.0.0.1`, tableaux artistes/morceaux et bilan. Recherche sur artistes/titres, filtres rôles/tri/revue/anomalies, dossiers sourcés, candidats et genres bruts séparés. Correction de l'identité, des URLs, des rôles et de Bass-related ; tri et notes personnels ; sauvegarde atomique dans `review.json` ; export CSV des décisions à jour. Ce JSON n'écrase ni les observations IA ni le CSV initial, importé tant que le JSON n'existe pas.

Les profils corrigés remplacent les boutons de profil du dossier après sauvegarde. Les champs restent protégés pendant la requête. Host/Origin contrôlés, fichiers statiques limités à une liste autorisée, chemins audio et catalogue complet non servis. Export CSV protégé contre l'interprétation des notes comme formules.

## Contrôles effectués

- 22 cas Pytest passent pour la lecture sans modification, les crédits confirmés, la sélection/couverture, les liens canoniques, le cache/les reprises, les réponses invalides, les preuves obligatoires, la préservation de revue et les accès HTTP/sauvegardes séparées.
- Ruff check/format sur les deux scripts et leurs deux fichiers de tests ; compilation Python ; `node --check scripts/artist-pilot-web/app.js` ; `git diff --check`.
- Recette navigateur : recherche, dossier et sources, reprise de notes/identité après rechargement, filtre MC (5 dossiers), onglet des 50 morceaux, bilan des profils/coûts. Sur copie : sauvegarde, rejet d'une URL d'album Spotify, correction d'un profil, actualisation du bouton et téléchargement CSV contrôlé (42 lignes, correction incluse).
- Captures privées desktop 1360 × 950, mobile 390 × 844 et panneau Codex réel. Vérification de la composition et de l'absence de débordement global au format mobile. Le dossier desktop dispose d'un défilement interne ; la capture pleine page ne déroule pas ce panneau.
- Revue visuelle par un sous-agent frais : deux corrections matérielles demandées, puis verdict `ship` portant sur ces deux corrections résolues. Documentation visuelle propre à l'outil ; aucun thème MTEE modifié. Détecteur exécuté une fois : avertissement d'onglet souligné classé faux positif (boutons sans arrondi).
- Le graphe ne référence pas encore les nouveaux scripts ; son rayon nul ne prouve pas une absence d'impact. Le périmètre autonome est vérifié dans les imports et les sources.

Aucun build Windows, test du paquet ni modification de dépendance requis pour ce front autonome. Les fichiers production déjà modifiés dans le workspace appartiennent à un autre travail et ne sont pas inclus dans ce lot.

Publication du lot : commit `9595607`, push vers `origin/main` réussi le 5 octobre 2026. Aucun fichier de collection, rapport personnel, cache fournisseur ou décision utilisateur inclus.

## Relancer et poursuivre

### Révision après retour utilisateur — revue par exceptions

Le parcours initial est remplacé : les valeurs inchangées sont acceptées par défaut et exportables immédiatement. L'acceptation par défaut n'est pas une consultation individuelle des preuves ; la provenance est conservée dans la colonne `acceptance` de l'export (`default` ou `correction`). Les identités non résolues restent non résolues et les profils absents restent vides. Les observations IA restent inchangées.

Tableau pleine largeur avec rôles cumulables, Bass-related et tri éditables. Dossier facultatif pour les sources, URLs et notes ; fermeture/changement de dossier conserve les brouillons. Un bouton global enregistre uniquement les artistes modifiés. Aucun Suivant ni compteur à faire. Chargement de 100 lignes à la fois, ajout automatique au défilement et recherche sur le jeu entier.

Recette sur copie : deux artistes corrigés ensemble, notes conservées en changeant de dossier, sauvegarde puis rechargement. Fixture fictive de 2 000 artistes : 100 lignes initiales, 200 après défilement, recherche directe du dernier artiste sans pagination. Captures desktop et mobile sans débordement global ; sur petit écran le tableau défile horizontalement. La base réelle et les décisions utilisateur ne sont pas utilisées comme support d'écriture de recette.

Tests supplémentaires : propositions effectives/export sans 2 000 écritures, lot invalide entièrement refusé, corrections précédentes préservées, retrait explicite d'un profil et retour de Bass-related à inconnu, compatibilité des anciens tris pending. Les contrôles de la version initiale ci-dessus restent historiques ; cette révision a son propre contrôle final et sa publication.

Clôture technique le 6 octobre 2026 : 28 tests passent, Ruff check/format, compilation Python, syntaxe JavaScript et diff sans erreur. La fixture de volume inclut aussi un CSV initial de 2 000 lignes pending : seules les deux corrections sont écrites. Les notes des anciens CSV restent conservées même sans décision de tri. Le pilote réel est rouvert avec ses 50 morceaux et 42 artistes ; sa correction utilisateur préexistante reste prioritaire sur les propositions. Aucun test de sauvegarde sur le dossier réel.

Révision publiée dans `d23c4d8` le 6 octobre : push vers origin/main et fetch de confirmation réussis, sans divergence. Données/captures restent privées et les changements production préexistants ne sont pas inclus.

6 octobre — Producer/DJ regroupés en une case et un filtre communs, dans les lignes et le dossier. Recette sur copie : décocher puis recocher le groupe et sauvegarder ; le filtre retrouve 28 artistes du pilote. Contrôle JavaScript et actualisation du front réel sans écriture de recette sur ce dernier. Les observations IA originales ne sont pas réécrites.

Depuis la racine, après création du pilote :

```powershell
.\.venv\Scripts\python.exe scripts/artist_pilot_server.py --output <dossier-prive-du-pilote> --port 8765
```

Ouvrir `http://127.0.0.1:8765`. Les données réelles restent dans le dossier privé `.local/validation/105/`, ignoré par Git. Ctrl+C arrête le serveur ; le JSON de revue permet la reprise. Une copie `ui-check` contient exclusivement les décisions fictives de recette et ne doit pas être importée comme revue utilisateur.

Pour un autre échantillon, `prepare` exige un nouveau dossier. Les sélecteurs sont une liste JSON d'objets contenant `category`, `artists` (noms), `count` et, facultativement, `title_pattern`. `musicbrainz` reprend le même dossier. `report` importe une liste d'observations portant les IDs locaux, les rôles/tri proposés, sources, liens prouvés et problèmes ; les décisions humaines restent indépendantes.

La prochaine étape utile est la revue des dossiers ambigus et du bloat possible, puis la comparaison des choix personnels avec les propositions. Les corrections d'identité doivent précéder toute utilisation en découverte. Ne pas dériver les genres d'un morceau uniquement des genres de ses artistes. Un rôle Producer n'indique pas automatiquement que l'utilisateur aime toute sa discographie.

Clarification du 6 octobre : le regroupement initial est remplacé par deux cases séparées ; Producer active DJ par défaut et à la coche, avec exception DJ possible. 29 tests passent, dont défaut Producer/DJ, conservation d’une exception enregistrée et des preuves originales ; Ruff et syntaxe JavaScript passent. Recette des cases et sauvegarde sur copie, actualisation du pilote réel sans écriture de recette.
