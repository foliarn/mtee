# Étude préalable de l'échange Rekordbox

Étude demandée par `PLAN.md` §2 et le plan 01. Elle prépare les identifiants, les emplacements et les repères temporels ; elle ne déclenche aucune implémentation. L'import et l'export appartiennent au plan 12.

## Statut des observations

Aucun export Rekordbox réel n'était disponible sur la machine de développement le 10 septembre 2026, et la documentation officielle n'a pas été consultée pendant cette session. Les points ci-dessous sont donc des **hypothèses de travail à confirmer**, accompagnées de la vérification qui les tranchera. Aucune compatibilité n'est déclarée acquise.

## Questions que l'étude doit trancher

Le fichier d'échange attendu est un XML « DJ Playlists » exporté par Rekordbox. Les éléments à vérifier sont les suivants.

**Identifiants.** L'attribut `TrackID` d'un morceau est-il stable entre deux exports de la même collection, et après un déplacement du fichier ? MTEE n'adopte pas cet identifiant comme identité : `TrackId` reste un UUID interne, et une table de correspondance associera `track_id` et identifiant Rekordbox. Vérification : exporter deux fois la même collection, déplacer un fichier, comparer les identifiants.

**Emplacements.** Le chemin est écrit sous forme d'URI dans l'attribut `Location`. À confirmer : le préfixe exact utilisé sous Windows, l'encodage des espaces et des caractères accentués, le traitement de la lettre de lecteur et celui d'un chemin réseau. Vérification : exporter un morceau dont le dossier contient un accent et une espace, puis comparer l'URI au chemin réel.

**Temps.** Les repères de cues et les points de grille sont exprimés en secondes décimales dans les exports connus, tandis que MTEE utilise des microsecondes entières. À confirmer : le nombre de décimales conservées, la règle d'arrondi appliquée par Rekordbox à la réimportation, et la présence éventuelle d'un décalage lié au début du fichier ou au format encodé. Vérification : poser un cue à une position connue, exporter, réimporter et mesurer l'écart.

**Grilles et tempo.** Les éléments de tempo décrivent-ils une grille constante ou une suite de segments ? Comment sont représentés un morceau sans grille et un morceau à tempo variable ? Vérification : exporter un morceau à tempo fixe et un morceau visiblement variable.

**Cues et boucles.** Quels types de repères existent, comment sont distingués un hot cue, un memory cue et une boucle, et quelles informations sont perdues lorsqu'un type est absent du modèle de MTEE ? Vérification : créer un exemplaire de chaque type et lire l'export.

**Réimportation.** Rekordbox accepte-t-il un XML modifié par un tiers, et quelles informations écrase-t-il lors de la relecture d'une collection existante ? Vérification : réimporter un export non modifié, puis un export dont un champ neutre a changé, sur une collection de test.

## Conséquences déjà prises dans le socle

Les temps internes sont des entiers en microsecondes, ce qui permet de représenter sans perte des positions exprimées en secondes décimales à six décimales et rend la règle de conversion explicite au moment de l'échange.

`TimeRange` exclut sa borne de fin ; une boucle importée sera donc convertie avec une règle écrite, et non par une coïncidence d'arrondi.

`Derivation`, prévu par les règles communes, reliera un morceau source, sa révision et un fichier dérivé. Une conversion antérieure à un export Rekordbox pourra ainsi porter la correspondance des emplacements et, lorsqu'elle est vérifiée, celle des temps.

`SourceRevision` sert à repérer qu'un fichier a changé depuis le dernier échange ; l'identité, elle, ne dépend jamais du chemin.

## Ce que l'étude ne conclut pas

Elle ne conclut ni sur la version de Rekordbox visée, ni sur la compatibilité des platines, ni sur la complétude des champs. Le plan 12 établira le rapport des compatibilités à partir d'exports réels, avec les mesures correspondantes.
