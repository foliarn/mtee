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

- [x] Service, modèle, confirmation, résultats individuels et journal de reprise ajoutés; le lecteur attend la libération du fichier avant une nouvelle tentative.
- [x] `IFileOperation` passe `FOF_ALLOWUNDO`; son callback `PostDeleteItem` fournit l'identité de l'élément placé dans la Corbeille, persistée par la migration 014.
- [x] Compilation Python et imports critiques passent.
- [ ] Recyclage, restauration, fichiers verrouillés et erreurs COM ne sont pas observés sur une copie Windows.

## Surprises & Discoveries

2026-09-25 — `SHFileOperation` ne donne pas le nouvel élément Shell. Le service utilise maintenant `IFileOperationProgressSink::PostDeleteItem` et enregistre le nom d'analyse retourné par l'élément créé dans la Corbeille. L'appel natif n'a pas été exécuté ici.

## Decision Log

- 2026-09-25 — Pas de repli vers une suppression définitive et pas d’Undo applicatif.

## Outcomes & Retrospective

Le chemin applicatif utilise uniquement le recyclage Shell avec `FOF_ALLOWUNDO`; aucune API de suppression définitive n'est utilisée. L'identité Shell du nouvel élément est journalisée dans la migration 014. Aucun essai natif de suppression/restauration n'a été exécuté; la garantie opérationnelle reste à confirmer sur Windows avec un fichier synthétique.
