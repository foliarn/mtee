# Décisions — capture SoundCloud (plan 29)

Questions posées le 29 septembre 2026 à la suite du cadrage initial de la série 29–32, et réponses de l'utilisateur reçues le même jour dans la conversation de planification. Les formulations des réponses sont résumées ; les conséquences pour les plans sont indiquées à droite.

| # | Question | Réponse utilisateur (2026-09-29) | Conséquence |
|---|---|---|---|
| 1 | Politique d'automatisation des étapes de passerelle | Après un téléchargement réussi, liker, reposter et poster un commentaire choisi dans une liste écrite par l'utilisateur, même lorsque la passerelle ne l'exige pas, pour soutenir les artistes | Nouvelles « actions de soutien » au plan 30 ; les étapes exigées par une passerelle sont automatiques ; consentement OAuth et CAPTCHA restent manuels |
| 2 | Données de formulaire | E-mail, nom, etc. gérables dans l'extension | Page d'options : profils de formulaire modifiables, stockés localement |
| 3 | Emplacement des téléchargements | `Downloads/Songs` | Sous-dossier `Songs` du dossier Téléchargements de Chrome, fichiers à plat |
| 4 | Envois groupés | Oui pour les playlists, pas pour les likes | Commande `Download playlist` sur les pages de playlist uniquement |
| 5 | Réintroduire un déplacement depuis une Inbox MTEE | Non pour l'instant : seulement télécharger ; l'intégration MTEE viendra plus tard | Plan 31 reporté ; aucun code Python dans cette série |
| 6 | Critères de tri automatique | Abandonner le tri | Plan 32 abandonné |
| 7 | Extraire les archives `.zip` | Oui | Extraction dans l'extension lorsque l'archive peut être lue par elle (plan 30) |

## Choix complémentaires proposés par Claude

Ces choix ordinaires complètent les réponses et peuvent être ajustés sans nouvelle série de questions.

- Le commentaire est tiré au hasard dans la liste de l'utilisateur, en évitant les derniers commentaires utilisés ; `{artist}` et `{title}` sont remplacés par les valeurs affichées sur la page.
- Aucune action de soutien n'est faite deux fois sur un même morceau : l'état « déjà liké/reposté » est lu avant de cliquer (ces boutons sont des bascules) et l'historique local mémorise les commentaires postés.
- Les actions de soutien sont espacées par un délai aléatoire, et un plafond quotidien réglable s'applique, notamment pendant un lot de playlist. Motif : des commentaires répétés et rapides peuvent être traités comme du spam par SoundCloud et exposer le compte à des restrictions.
- Chaque action de soutien peut être désactivée séparément dans les options.
- Un petit fichier de provenance par téléchargement est écrit dans `Songs/_mtee/`, désactivable, afin de préparer l'intégration MTEE ultérieure sans encombrer le dossier des morceaux.
