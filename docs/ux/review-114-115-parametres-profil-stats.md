# Revue UX — Paramètres, profil et statistiques (114-115)

Date : 14 octobre 2026. Statut : maquettes isolées, prêtes pour revue. Aucune page réelle n'est remplacée : `SettingsView.qml` reste celui de l'application, et la page Profil n'est pas branchée. Les données sont fictives ; aucune base, aucun réglage, aucun fichier audio n'est lu.

## Ouvrir la maquette

Depuis la racine du dépôt :

    uv run python scripts/review_settings_profile_114.py --view settings --category general --data-dir .local/validation/114/review
    uv run python scripts/review_settings_profile_114.py --view profile --period month --data-dir .local/validation/114/review
    uv run python scripts/review_settings_profile_114.py --view explorer --columns --column-menu --data-dir .local/validation/114/review
    uv run python scripts/review_settings_profile_114.py --view settings --category privacy --dialog restore-confirm --data-dir .local/validation/114/review

Dans la fenêtre, la barre d'activité, les catégories, le sélecteur de période, les boutons « Columns », « Clear history… », « Reset statistics… », « Back up… », « Restore from backup… » et « Remove rule » répondent. Les dialogues se ferment avec Échap ou Cancel. Les modifications sont en mémoire seulement.

## Captures

Toutes les captures sont dans `review-114-115-parametres-profil-stats/`.

| Écran | Capture |
|---|---|
| Settings › General | [settings-general-1440x900.png](review-114-115-parametres-profil-stats/settings-general-1440x900.png) |
| Settings › Library (règles de nom d'artiste, données fictives) | [settings-library-1440x900.png](review-114-115-parametres-profil-stats/settings-library-1440x900.png) · [1100 × 760](review-114-115-parametres-profil-stats/settings-library-1100x760.png) |
| Settings › Playback | [settings-playback-1440x900.png](review-114-115-parametres-profil-stats/settings-playback-1440x900.png) |
| Settings › Analysis | [settings-analysis-1440x900.png](review-114-115-parametres-profil-stats/settings-analysis-1440x900.png) |
| Settings › Keyboard shortcuts | [settings-shortcuts-1440x900.png](review-114-115-parametres-profil-stats/settings-shortcuts-1440x900.png) |
| Settings › Data & privacy | [settings-privacy-1440x900.png](review-114-115-parametres-profil-stats/settings-privacy-1440x900.png) |
| Settings › About | [settings-about-1440x900.png](review-114-115-parametres-profil-stats/settings-about-1440x900.png) |
| Dialogue : vider l'historique | [dialog-clear-history-1440x900.png](review-114-115-parametres-profil-stats/dialog-clear-history-1440x900.png) |
| Dialogue : réinitialiser les statistiques | [dialog-reset-statistics-1440x900.png](review-114-115-parametres-profil-stats/dialog-reset-statistics-1440x900.png) |
| Dialogue : restauration de base | [dialog-restore-confirm-1440x900.png](review-114-115-parametres-profil-stats/dialog-restore-confirm-1440x900.png) |
| Profil, cette semaine | [profile-week-1440x900.png](review-114-115-parametres-profil-stats/profile-week-1440x900.png) |
| Profil, ce mois | [profile-month-1440x900.png](review-114-115-parametres-profil-stats/profile-month-1440x900.png) · [1100 × 760](review-114-115-parametres-profil-stats/profile-month-1100x760.png) |
| Profil, toute la durée | [profile-all-1440x900.png](review-114-115-parametres-profil-stats/profile-all-1440x900.png) |
| Explorateur, colonnes optionnelles | [explorer-columns-1440x900.png](review-114-115-parametres-profil-stats/explorer-columns-1440x900.png) |
| Explorateur, menu « Columns » ouvert | [explorer-columns-menu-1440x900.png](review-114-115-parametres-profil-stats/explorer-columns-menu-1440x900.png) |

## Ce qui change dans les paramètres

Chaque réglage réel est conservé à une seule place. Les lignes factices sont retirées.

| Élément actuel | Destination | Statut |
|---|---|---|
| Afficher l'île du lecteur | Playback › Player | conservé, réglage réel |
| Ouvrir dossiers et playlists en onglets d'aperçu | General › Tabs | conservé, réglage réel |
| Normaliser le volume, cible Quiet / Normal / Loud | Playback › Loudness | conservé, réglage réel (étape 116) |
| Notation des tonalités, BPM min et max, décimales, analyses en parallèle, écrire les tags | Analysis | conservés, réglages réels |
| Nom du créateur des playlists | Profile › nom affiché | déplacé ; la valeur stockée est migrée |
| Liste des raccourcis (texte fixe) | Keyboard shortcuts | remplacée par la liste vérifiée dans `Main.qml`, `TrackListView.qml`, `InfoPanel.qml` et `TitleBar.qml` (16 entrées) |
| Remember the queue between sessions | — | **retiré** : l'interrupteur ne reliait à rien ; la file est restaurée à chaque démarrage |
| Library › Folders « Music » et « Add folder » | — | **retiré** : valeur fixe ; l'entrée « Add folder… » du menu est déjà désactivée en v0.1 |
| Appearance › Theme « Acid (dark) » et Density « Comfortable » | — | **retirés** : pas de catégorie Apparence en v0.1 |

Nouveautés de la maquette : Library › Artist name rules (données fictives ; le backend vient de l'étape 112), Data & privacy, About.

## Parcours à essayer

1. Ouvrir **Settings › Library**, supprimer une règle, vérifier le message et la liste.
2. Ouvrir **Settings › Data & privacy**. Essayer « Clear history… » puis Cancel, puis confirmer : le compteur passe à 0 et les statistiques ne bougent pas.
3. Essayer « Reset statistics… » : toutes les valeurs reviennent à zéro, l'axe du graphique reste.
4. Essayer « Restore from backup… » : le dialogue décrit ce qui se passe au redémarrage ; « Schedule restore » affiche l'état planifié et propose « Cancel restore ».
5. Ouvrir **Profile**, changer la période : les totaux, le graphique et les trois classements changent. Modifier le nom et enregistrer. « Change picture… » et « Remove picture » changent l'avatar de la maquette.
6. Ouvrir **Explorer**, puis « Columns » : cocher « Plays » et « Last played ». Cliquer l'en-tête « PLAYS » pour trier.

## Choix ouverts pour l'utilisateur

1. **General** ne contient qu'un réglage réel (onglets d'aperçu). Garder la catégorie telle quelle, déplacer ce réglage vers Library, ou supprimer General ?
2. **Remember the queue** a été retiré parce qu'il ne faisait rien. Voulez-vous une vraie option « ne pas restaurer la file au démarrage » ? C'est une nouvelle fonction, non prévue dans le brief.
3. **Période par défaut** : « This month » est proposé. Alternative : « This week ».
4. **Libellés des totaux** : « Plays » compte les écoutes qui comptent (30 s, ou fin d'un morceau court). « Listening sessions » compte toutes les écoutes, y compris les écoutes courtes. Garder ces deux libellés, ou renommer la seconde (par exemple « Listens ») ?
5. **Top artists** reste vide tant que l'étape 112 n'est pas fusionnée ; la page affiche alors un message. La maquette montre des données fictives pour juger la mise en page. Accepter cet état transitoire ?
6. **Avatar** : formats PNG, JPEG, WebP, BMP et GIF, 10 Mo au plus, copie telle quelle sans recadrage. Alternative : recadrage carré de 256 px, plus propre mais qui modifie l'image.
7. **Nom affiché** vide par défaut : les playlists affichent alors « MTEE », comme avant. Alternative : demander un nom à la première ouverture du profil.
8. **Clear listening history** vide seulement le panneau History (les 100 dernières entrées). Les statistiques sont conservées. Confirmer ce sens.
9. **Reset statistics** supprime tous les événements d'écoute ; l'identifiant de l'installation est conservé. Le texte précise que l'action est irréversible.
10. **Restore database** : la restauration est planifiée, puis appliquée au prochain démarrage, après une copie de l'actuelle dans le dossier de restauration. Ces copies ne sont jamais supprimées automatiquement : fixer une règle de conservation ?
11. **Back up database** : le nom proposé contient l'heure UTC ; le dossier est celui que vous choisissez. Dossier par défaut à proposer ?
12. **Colonnes Plays et Last played** : désactivées par défaut. Alternative : activées.
13. **About** : la licence de MTEE est indiquée « non décidée », comme dans `THIRD_PARTY_NOTICES.md`. Le texte doit être validé par l'auteur.
14. **Keyboard shortcuts** : « Delete » ne fonctionne que dans l'Explorateur ; le libellé « Move selected files to the Recycle Bin » reste à valider.

## Limites de cette revue

- Données fictives. Les chiffres, les morceaux et les règles de nom d'artiste sont inventés ; les totaux ne sont pas recalculés à partir de l'écoute réelle.
- L'avatar est un visuel généré (« AL »), pas une image de l'utilisateur.
- Les captures ont été faites depuis les sources, sur l'écran de la machine de développement. Les clics ne sont pas rejoués automatiquement : les vérifications faites sont le chargement sans erreur QML pour chaque écran, les captures, et un script qui appelle directement les actions du prototype (catégorie, période, règle, dialogues, colonnes, nom affiché, avatar). Le comportement au pointeur doit être vu par l'utilisateur.
- Les détails d'un morceau (inspecteur, colonnes « Plays » et « Last played » dans les détails) ne sont pas maquettés : à présenter au prochain passage.
- La version affichée dans About (« 0.1.0 ») est écrite en dur dans la maquette ; la page réelle la lira dans le paquet de MTEE.
- Le fichier `SettingsView.qml` actuel, son menu, et la page Profil réelle n'ont pas été modifiés.
