# Revue des maquettes 103.0 — Artists et Match review

## Ce qui est soumis à validation

Ces maquettes montrent le catalogue `Artists` et la revue `Match review` avec uniquement des données fictives stockées en mémoire. Elles n'ouvrent aucune collection, n'enregistrent pas de décision et ne modifient aucun tag ni fichier. La porte 103.0 s'arrête ici : le backend et la persistance attendent la validation explicite de ces vues.

La direction visuelle reprend le thème sombre et les accents citron/rose de MTEE. `Artists` présente les artistes séparément des collaborations, les alias à rattacher explicitement, les liens de profil saisis manuellement et les morceaux associés. A+ et Ev apparaissent comme deux identités distinctes. Aucun rapprochement n'est fait automatiquement et aucune pochette d'artiste n'est affichée.

`Match review` juxtapose les tags actuels et la proposition, expose les raisons et les avertissements, laisse corriger le crédit artiste et le titre, et affiche le nom de fichier qui résulterait du titre proposé. Les collaborations gardent une liste ordonnée dont les membres peuvent être ajoutés, retirés et déplacés en mode édition. Un crédit non résolu reste visible. Les actions `Accept`, `Edit`, `Reject`, `Skip` et `Unresolved` sont présentées avec une confirmation d'acceptation par lot qui indique le nombre de décisions et précise qu'elle les enregistrerait dans MTEE.

## Parcours et états représentés

Les lignes de démonstration couvrent les tags absents, un artiste inconnu en casse mixte, une collaboration, un alias seulement probable, plusieurs valeurs artiste/titre, un texte suspect d'encodage, des annotations retirées, un fichier modifié depuis la proposition, une absence de preuve, une version musicale conservée et une collision de renommage. Les actions ne sont que des interactions de maquette ; aucun état n'est enregistré.

Captures incluses dans ce dossier :

- [Artists](review-103-artistes-mapping/artists.png)
- [Match review](review-103-artistes-mapping/review.png)
- [Confirmation de validation par lots](review-103-artistes-mapping/batch.png)
- [Fenêtre étroite](review-103-artistes-mapping/narrow.png)
- [Liste vide](review-103-artistes-mapping/empty.png)
- [Calcul en cours](review-103-artistes-mapping/loading.png)
- [Erreur récupérable](review-103-artistes-mapping/error.png)
- [Fichier modifié](review-103-artistes-mapping/changed.png)
- [Valeurs multiples](review-103-artistes-mapping/multi.png)
- [Encodage suspect](review-103-artistes-mapping/encoding.png)
- [Collision de nom](review-103-artistes-mapping/collision.png)

## Ouvrir les maquettes depuis les sources

Depuis la racine du dépôt :

```powershell
uv run python scripts/review_mapping_103.py
```

La scène initiale est `Match review`. Pour afficher une variante précise, passer `--scene artists`, `review`, `batch`, `narrow`, `empty`, `loading`, `error`, `changed`, `multi`, `encoding` ou `collision`. Pour régénérer toutes les captures dans leur dossier :

```powershell
uv run python scripts/review_mapping_103.py --capture-dir docs/ux/review-103-artistes-mapping
```

## Validation demandée

Merci de valider les deux vues et la confirmation par lots, ou d'indiquer les changements souhaités. En particulier, vérifier la distinction entre identité d'artiste et crédit de collaboration, la place des états non résolus, les informations du panneau de revue et la densité en fenêtre étroite. Le jalon suivant dépend de cet accord ; aucune proposition d'échantillon 102 n'est confirmée par ces maquettes.
