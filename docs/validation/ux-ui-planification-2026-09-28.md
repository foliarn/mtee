# Préparation des plans UX/UI — 28 septembre 2026

## Portée et sources

Préparation documentaire à partir de la page [MTEE — UX/UI](https://app.notion.com/p/3e9d502f2cc080c3b7c4ce2a24c067e5), de ses deux captures et des réponses utilisateur dans cette conversation. État applicatif inspecté : `main`, `adf3f49`. Les sources QML, modèles Qt, service de lecture, waveform, session et tests pertinents ont été lus après orientation par les graphes du dépôt.

Les plans 23 à 28 couvrent 18 demandes identifiées P1, E1–E2, S1–S2, R1–R2, C1–C7 et W1–W4. Un point de couverture correspond à une demande testable, pas à une estimation de taille de développement.

## Décisions enregistrées

Le tri de référence est la création décroissante sans flèche. Les colonnes ont une configuration globale mémorisée. La recherche conserve texte et résultats lorsqu’elle perd le focus. Le double-clic dans l’arbre joue une cible masquée sans la révéler ni effacer la recherche. Trois variantes de waveform seront comparées avant le choix visuel.

## Contrôles documentaires réalisés

Les six fichiers de plans ont été relus pour leur couverture et leurs dépendances. Un contrôle Python a vérifié l’UTF-8, les quatre sections de suivi, les cases à cocher limitées à Progress et les liens locaux présents dans ces documents. Les 41 références complètes à des fichiers ont été contrôlées : aucun chemin inattendu manquant ; les nouveaux tests, rapports et le dossier de revue sont identifiés comme livrables à créer. Les liens de l’index vers les six plans existent. `git diff --check` n’a signalé aucune erreur de whitespace.

Le fetch d’`origin` a réussi et `HEAD...origin/main` ne présentait pas de divergence avant le commit documentaire. Les changements locaux préexistants de `.gitignore`, `AGENTS.md` et `.codex/` restent hors périmètre. La confirmation du push et son hash sont fournis dans le compte rendu de conversation, afin d’éviter un hash auto-référentiel dans ce document.

## Limites

Aucun code applicatif modifié. Aucun test applicatif, build, parcours GUI ou essai audio natif exécuté pendant cette préparation. Les constats de source ne sont pas présentés comme une reproduction des bugs. Les maquettes prévues par les plans sont des livrables futurs ; aucun choix visuel de waveform n’est annoncé comme validé.
