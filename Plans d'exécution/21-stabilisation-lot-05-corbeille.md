# 21 — Corbeille Windows réelle

## Résultat et prérequis

Supprimer uniquement par recyclage Windows natif, avec confirmation et résultats individuels. Une corbeille indisponible ou un fichier verrouillé ne doit jamais provoquer une suppression définitive. Prérequis : retraits du lot 17 et contrats d’accès/fermeture du lot 18.

## Service, modèle et interaction

Créer un service et modèle Trash dédiés; supprimer les branches Move/Copy/Rename restantes au lieu de les cacher. Menu et touche Suppr affichent une confirmation avec le nombre de fichiers. À la confirmation, capturer UUID et révision, puis revalider avant chaque recyclage. Les appels Shell s’exécutent dans un worker avec initialisation et libération COM sur le même thread et conservent l’identité renvoyée par l’élément recyclé.

Pour un morceau en lecture, proposer l’arrêt et attendre la libération effective du verrou avant de réessayer. Le modèle rapporte succès/échec par fichier; des échecs partiels ne réécrivent pas les résultats antérieurs. Le catalogue n’est actualisé qu’après confirmation de recyclage. Une interruption est journalisée; l’absence d’un chemin n’est pas une preuve de recyclage. La restauration relève de la corbeille Windows, sans Undo MTEE.

## Vérification et critères

Avec une copie synthétique Windows : confirmer le nombre affiché, recycler un fichier, observer son entrée dans la corbeille et le restaurer. Simuler refus, erreur COM, révision modifiée, fichier déjà absent et échec au milieu d’un lot : toute source non recyclée reste intacte et visible avec son erreur. Vérifier arrêt du lecteur et attente du verrou. Aucune API de suppression permanente n’est un repli.

## Reprise après erreur

Reconsulter la corbeille et le journal d’opération avant toute relance. Ne pas retenter aveuglément une opération dont la réponse Shell est incertaine et ne pas supprimer manuellement l’original par chemin.

## Progress

- [ ] Service/model dédié et confirmation.
- [ ] Recyclage et restauration réellement observés sur copie Windows.

## Surprises & Discoveries

À compléter d’après les résultats Shell et les cas de fichiers verrouillés.

## Decision Log

- 2026-09-25 — Pas de repli vers une suppression définitive et pas d’Undo applicatif.

## Outcomes & Retrospective

À compléter; une simulation d’API ne vaut pas une observation dans la corbeille réelle.
