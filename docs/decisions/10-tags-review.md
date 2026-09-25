# Dossier de revue — étape 10, vocabulaire des tags et usages de recherche

Préparé le 2026-09-25 à partir des résultats réels de la validation 09.
Ce dossier expose des mesures calculées et des exemples de requêtes à
examiner. Il ne constitue ni l'accord utilisateur, ni un vocabulaire adopté,
ni l'autorisation d'implémenter l'étape 10.

Maquette statique : [recherche et tags](10-tags-review-mockup.html). Les
valeurs visibles sont celles de la fixture synthétique; les contrôles sont
illustratifs et ne sauvegardent rien.

## Base examinable

Une fixture WAV synthétique de 14 s (PCM 16 bits, mono, 22 050 Hz) a été
analysée. Elle contient un accord construit en do majeur, des impulsions à
120 BPM et deux plages silencieuses connues totalisant 2 s. Les valeurs
observées sont :

- tempo calculé : 117,4538 BPM; variantes affichées : 58,7269 et 234,9077 BPM;
- tonalité estimée : do majeur;
- loudness intégré : −18,0 LUFS; crêtes séparées : −4 dBFS et −4 dBTP;
- technique : WAV `pcm_s16le`, durée 14 s, mono, 22 050 Hz, 16 bits;
- les cinq analyseurs ont persisté leurs résultats avec versions; la copie du
  fichier conserve son SHA-256.

Les détails et commandes sont dans
[`docs/validation/09-analyse-sans-ml.md`](../validation/09-analyse-sans-ml.md).
Il s'agit d'une seule fixture synthétique, sans corpus utilisateur, référence
d'écoute réelle ou annotation indépendante. Elle valide le fonctionnement du
pipeline, pas l'exactitude générale des analyses ni l'utilité d'un vocabulaire
de genres, d'humeurs ou d'énergie.

## Exemples de recherche à discuter

Ces exemples utilisent les champs calculés présents et rendent leur
provenance explicite. Ils servent à discuter des besoins, pas à figer la
syntaxe de recherche :

1. **Estimated tempo between 112 and 123 BPM** — devrait inclure la fixture
   synthétique (117,45 BPM); il faut décider si les valeurs confirmées
   manuellement sont recherchées séparément ou incluses par défaut.
2. **Estimated key is C major** — retourne la fixture synthétique; une valeur
   `uncertain`, absente ou périmée ne devrait pas être présentée comme une
   confirmation musicale.
3. **Integrated loudness at or below −18 LUFS** — la fixture se situe à la
   limite; la recherche doit afficher l'unité et distinguer la valeur calculée
   de toute métadonnée écrite.
4. **Has one or more detected silence intervals** — la fixture contient deux;
   le seuil utilisé (−60 dB, durée minimale 0,5 s) reste visible dans la
   provenance et n'est pas un tag sémantique.

Le rapport de validation 09 note qu'aucune recette de recherche dans
l'application ni comparaison avec une vraie bibliothèque n'a été réalisée.

## Décisions utilisateur à consigner

1. Quel usage doit être le premier : retrouver par métadonnées/faits mesurés,
   organiser manuellement par tags, ou les deux?
2. Les tags personnels doivent-ils être des libellés libres, un vocabulaire
   contrôlé défini ensemble, ou les deux? Quels exemples réels justifient
   chaque terme et sa cardinalité simple/multiple?
3. Quelles sources de tempo et tonalité doivent être disponibles comme champs
   distincts : tag écrit, calcul, correction manuelle, ou valeur effective
   explicitement choisie?
4. Les analyses `uncertain`, `stale`, `not applicable` et manquantes doivent-
   elles être filtrées séparément ou exclues d'une recherche de valeurs
   disponibles?
5. Confirmer ou rejeter toute proposition de vocabulaire seulement après
   examen de morceaux réels choisis par l'utilisateur. Aucun terme d'humeur,
   d'énergie ou de style n'est présumé.

## Maquette fonctionnelle proposée pour la revue

Présenter une recherche structurée avec champ, opérateur et valeur, en
affichant à côté la provenance (file metadata, computed, manual override),
l'unité et l'état. Présenter séparément la création d'un tag manuel avec nom,
type et cardinalité encore à décider. Un exemple de fiche peut afficher le
tempo calculé 117,45 BPM et une confirmation distincte; aucune modification de
tag fichier ne se fait automatiquement.

Cette maquette textuelle ne remplace pas une maquette visuelle ou un test de
compréhension. Ne pas construire ni livrer de fonctionnalité de tag/recherche
avant d'avoir consigné l'accord explicite et le vocabulaire versionné.

## Compte-rendu de revue — à remplir après réponse explicite

- Date et contexte : à renseigner.
- Termes acceptés, définition, cardinalité et cas utiles : à renseigner.
- Termes rejetés ou à revoir : à renseigner.
- Provenance/état des analyses dans les recherches : à renseigner.
- Accord explicite de commencer l'implémentation de l'étape 10 : non consigné.
