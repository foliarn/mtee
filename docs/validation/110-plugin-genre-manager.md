# Plan 110 — Rapport de préparation et de validation

Date : 9 octobre 2026. Référence : [ExecPlan 110](../../Plans%20d'ex%C3%A9cution/110-plugin-genre-manager.md). Ce rapport distingue le travail documentaire actuel de l'implémentation future.

## Préparation documentaire

Le plan reprend les réponses utilisateur concernant le plugin, les sources dossiers/playlists, l'écoute volontaire, les deux variantes à essayer, les genres ordonnés, les noms complets sous House, les tags libres sans préremplissage, Reviewed et les changements qui l'invalident. Il ajoute le rangement du lot vérifié, les genres déduits des artistes avec abstention et la vue Uncertain proposée. Info et les listes ordinaires restent à maquetter ultérieurement.

La demande antérieure d'attendre avant de rédiger a été respectée pendant les questions. La demande suivante de passage au plan autorise cette préparation ; elle n'autorise pas à considérer une maquette examinée ou un rangement réel effectué.

La référence produit et l'index désignent 110 comme plan actif. Un avis de remplacement est ajouté à 109 en préservant son historique. Les choix de disposition, le coût de validation après pinceau, le retrait du dernier genre et les destinations précises sont explicitement à éprouver pendant la revue.

## Constat du dépôt

Au début de cette préparation, branche `main`, révision `1eab96e30d71c5318baaf4426fecb0d5a65ba6b7`. `git fetch origin` puis comparaison `HEAD...origin/main` ne montrent aucune divergence. Ce commit retire les fichiers de l'exécution de 109. Les corrections locales du lecteur, de la file et des listes ainsi que leurs nouveaux tests sont laissées hors de ce travail.

Le graphe code-review-graph a été actualisé, puis les sources et tests ont été lus. Les points vérifiés comprennent le placeholder Plugins de `Sidebar.qml`, la sélection de vues dans `EditorGroup.qml`, `FileMoveService`, son modèle et ses tests, `LibraryRepository.move_location_in_transaction`, `Database` et les tests de migration, `PlaylistService.rows`, ainsi que le schéma des crédits d'artistes. Le SQL historique 021 a été lu dans le commit `4de9320` pour cadrer une adaptation future compatible ; il n'a pas été restauré par cette tâche.

La migration maximale du checkout est 020. La base personnelle n'a pas été ouverte et sa version n'est pas présumée. Les garanties de reprise durable des mouvements par lot sont des exigences futures : elles ne sont pas déduites du seul retour arrière immédiat de `FileMoveService`.

## Contrôles documentaires

Les contrôles de cette préparation portent sur les liens relatifs des documents modifiés, les chemins existants cités comme points d'intégration, l'encodage UTF-8, les sections obligatoires de l'ExecPlan, la cohérence avec les décisions de la conversation et les diffs Git. Les chemins futurs sont expressément présentés comme des livrables à créer, avec jalon et contrat de commande.

Contrôles exécutés le 9 octobre : lecture UTF-8 des cinq documents de cette préparation sans caractère de remplacement ; résolution de tous leurs liens Markdown locaux sans cible manquante ; présence des quatre sections obligatoires ; cases à cocher limitées à Progress ; existence des points d'intégration cités comme actuels. Le package `src/mtee/plugins/` est confirmé absent et décrit comme futur. `git diff --check` passe ; les avertissements de normalisation CRLF/LF ne sont pas des erreurs de contenu. La relecture du plan couvre les décisions recueillies et distingue les comportements encore proposés pour les maquettes.

Le message final de la tâche donnera la preuve de publication sans ajouter un commit uniquement pour y inscrire son propre hash. Les changements applicatifs préexistants continuent d'évoluer pendant cette préparation ; seuls les cinq fichiers documentaires sont destinés à son commit.

## Ce qui reste non réalisé

Aucun prototype créé ou lancé, aucune maquette approuvée, aucun changement Python/QML, aucune migration exécutée, aucun test applicatif, aucun benchmark et aucune recette du lecteur ne sont réalisés par cette préparation. Aucun fichier musical n'a été déplacé, renommé ou réécrit. Aucun build ni smoke-test du paquet Windows.

Le soupçon de lag reste à mesurer. Le protocole de 110.0/110.7 doit séparer le socle, le plugin inutilisé, le plugin actif et la reprise après fermeture. Les anciens résultats de 109 ne valent pas mesures de 110.

## Prochaine étape

Lors d'une demande d'exécution, commencer par 110.0 puis préparer 110.1 sur données fictives et fichiers synthétiques. Faire essayer les deux variantes avec les mêmes tâches, recueillir les réponses textuellement et consigner la revue 110.2 avant le branchement fonctionnel. Le présent rapport sera ensuite enrichi avec les résultats réels de chaque jalon, en séparant tests automatisés, observations de l'agent, retours utilisateur et opérations sur données personnelles.
