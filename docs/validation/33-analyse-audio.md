# Validation — étape 33, analyse audio (BPM, tonalité, waveform)

Rapport rédigé le 2026-09-30 pour l'[ExecPlan 33](../../Plans%20d'ex%C3%A9cution/33-analyse-audio.md). Environnement : Windows 11 Professionnel 10.0.26200, Python 3.12, PySide6 6.9.3, NumPy 2.5.3, FFmpeg embarqué du dépôt (`vendor/ffmpeg`), plateforme Qt `offscreen`. Tout ce qui suit a été exécuté depuis les sources ; le paquet Windows n'a pas été construit.

## Ce qui a été observé

### Précision du tempo (signaux synthétiques)

Boucles de batterie dont les coups suivent exactement la grille (option de swing), décodées comme le fait l'application (test d'intégration) ou injectées directement dans l'extracteur. Plage 70–180.

| Signal | Attendu | Trouvé | Écart |
|---|---|---|---|
| house 128 BPM, 120 s | 128,000 | 128,000 | 0,000 |
| house 127,98 BPM, 120 s | 127,980 | 127,980 | 0,000 |
| house 124,37 BPM, 90 s | 124,370 | 124,370 | 0,000 |
| garage 130 BPM avec swing 0,35, 120 s | 130,000 | 130,004 | +0,004 |
| garage 133,3 BPM avec swing 0,2, 200 s | 133,300 | 133,300 | 0,000 |
| house 150 BPM, 30 s | 150,000 | 150,000 | 0,000 |
| house 126 BPM, 20 s / 40 s (bord de la boucle) | 126,000 | 126,022 / 125,986 | +0,022 / −0,014 |
| dérive linéaire 128 → 128,64 BPM (0,5 %) | 128,320 | 128,318 | −0,002 |
| dérive linéaire 128 → 130 BPM (1,5 %) | 129,000 | 128,964 | −0,036 |

Aucune valeur n'est renvoyée pour : silence, bruit blanc, nappes d'accords sans rythme, boucle de 5 s (trop courte). Une boucle de 10 s est reconnue (128,007).

Ambiguïté demi/double tempo : pour une boucle « dnb » à 174 BPM et une boucle « hiphop » à 90 BPM, avec la plage 70–180 qui admet les deux représentants, le calcul choisit respectivement 87 et 180. Le comportement dépend donc de la musique et de la plage ; restreindre la plage (par exemple 90–180) tranche. Un test vérifie le repli dans la plage (128 BPM dans 40–100 donne 64,00).

### Tonalité (signaux synthétiques)

Progressions d'accords I–IV–V–I en position fondamentale, 24 tonalités : 24/24 reconnues, avec et sans batterie par-dessus, et avec un désaccord de +30 cents et −40 cents. Le silence et le bruit blanc ne donnent aucune tonalité (le contraste entre les douze classes de hauteur est trop faible). Une batterie synthétique dont la grosse caisse a une hauteur fixe reçoit une tonalité, ce qui est un comportement voulu de l'attention portée aux basses ; une piste faite uniquement de percussions peut donc recevoir la hauteur de sa grosse caisse. Les profils de tonalité sont ceux de la littérature (Krumhansl-Kessler 1982, Temperley 2005).

### Tonalité sur la collection réelle (correction du 2026-09-30)

Après un premier essai, l'utilisateur a constaté que beaucoup de morceaux ne recevaient aucune tonalité, quel que soit le format : sur 194 morceaux analysés, 125 sans tonalité et aucun sans BPM. Le seuil de corrélation de la première version, réglé sur des signaux synthétiques propres, rejetait la musique réelle.

Référentiel : 92 morceaux de la bibliothèque de l'utilisateur portent une tonalité écrite par un autre outil (Camelot ou classique, très majoritairement mineure : 86 mineures, 6 majeures). Ces tags servent de référence imparfaite, pas de vérité. Seul le décodage a été fait, en lecture seule ; aucun fichier ni tag n'a été modifié, et aucun titre n'est consigné ici.

| Version | Aucune tonalité | Exacte | Quinte | Relative | Parallèle | Autre |
|---|---|---|---|---|---|---|
| première version (pondération racine carrée, 80–5 000 Hz, seuil 0,45) | 43 | 24 | 24 | 7 | 10 | 27 |
| version 2 (pondération puissance 1,5, harmoniques, basses, 80–2 500 Hz, seuil 0,35) | 3 | 49 | 9 | 7 | 10 | 14 |

Pour la première version, les colonnes détaillent la meilleure des 24 tonalités, seuil ignoré ; pour la version 2, elles détaillent les 89 résultats renvoyés par le code de production sur les morceaux entiers. « Quinte » et « relative » sont des voisins sur la roue Camelot (compatibles pour le mixage harmonique) ; « parallèle » a la même tonique avec l'autre mode. Le taux de tonalité exacte parmi les résultats renvoyés est de 55 % et 73 % sont exacts, à une quinte ou relatifs.

Ce que l'exploration a montré, sur 200 s du milieu de chaque morceau (le score est une moyenne pondérée à la manière du concours MIREX : exacte 1, quinte 0,5, relative 0,3, parallèle 0,2) : la pondération des pics compte plus que tout (racine carrée : 0,50 de score MIREX ; puissance 1,5 à 2 : 0,58) ; limiter la bande à 2 500 Hz et ajouter la prise en compte des harmoniques inférieurs aident ; ajouter un profil des basses (fenêtre de 0,74 s, 40–250 Hz) avec un poids de 0,25 à 0,5 fait passer de 0,61 à 0,64–0,67, un poids de 1 ou plus dégrade. Ces réglages forment un plateau (beaucoup de combinaisons voisines donnent 0,60–0,62 avant les basses), pas un optimum isolé. La séparation harmonique/percussive par filtres médians améliore aussi, mais coûte plusieurs secondes par morceau ; elle n'est pas retenue. Des gabarits appris sur ces tags (validation croisée en laissant un morceau de côté) donnent 0,71 mais s'appuient sur une bibliothèque à 93 % mineure et n'ont pas été retenus : les profils publiés restent utilisés.

La corrélation devient un indicateur de fiabilité : à 0,6 et plus, environ deux tiers des résultats sont exacts ; entre 0,5 et 0,6, un tiers ; sous 0,5, environ un cinquième. Elle n'est pas affichée dans l'interface.

La version d'analyse passe à 2 : **Analyze** retraite les morceaux déjà analysés avec l'ancienne méthode (les valeurs éditées et les waveforms sont conservées). Non vérifié : la précision sur des bibliothèques d'un autre style, sur des tonalités majeures (6 exemples seulement), et l'exactitude des tags de référence eux-mêmes.

### Waveform : coût avant et après

Mesures sur un WAV synthétique mono de 22,05 kHz, comparant le code de `HEAD` et le nouveau.

| Mesure | Avant | Après |
|---|---|---|
| calcul complet de la waveform, 5 min | 0,71 s | 0,20 s |
| calcul complet de la waveform, 30 min | 5,40 s | 0,42 s |
| temps passé après que le décodage atteint 98 %, 5 min / 30 min | 0,07 s / 0,42 s | 0,01 s / 0,01 s |
| relecture d'une waveform déjà calculée | 20–60 ms (cache disque) | 0,4–0,5 ms (base) |
| analyse complète (tempo + tonalité + waveform), 5 min / 30 min | non applicable | 0,80 s / 5,6 s |

Première peinture de `WaveformView.qml` avec une liste Python, hors écran (`QQmlComponent`), avant : 600 points 0,5 s ; 1 200 points 4,9 s ; 2 400 points 17,2 s. Après, avec un tampon binaire : 14 ms pour 1 200 points, 19 ms pour 8 000. Micro-banc : lire 1 200 éléments d'une liste Python depuis QML coûte 2,5 s, 2 400 éléments 10,7 s ; un `Float32Array` sur un `QByteArray` coûte 1–17 ms. Ces chiffres viennent d'un rendu logiciel hors écran ; la machine de l'utilisateur peut donner d'autres valeurs. C'est ce coût de lecture qui immobilisait le thread graphique quand la waveform passait à `ready`.

### Suite de tests

Commandes exécutées depuis la racine :

    uv run ruff check src tests
    uv run pytest tests/unit tests/integration tests/ui --deselect tests/integration/test_mpv_playback.py

Nouveaux fichiers : `tests/unit/test_musical_key.py`, `test_tempo_analysis.py`, `test_key_analysis.py`, `test_waveform_points.py` ; `tests/integration/test_analysis_repository.py`, `test_analysis_pipeline.py`, `test_waveform_model.py` ; `tests/ui/test_analysis_ui.py`, `test_waveform_view_speed.py`. Les tests de cache et de pyramide de l'ancienne waveform sont supprimés avec le code qu'ils exerçaient ; `test_database_migrations.py` attend maintenant la version 15.

Les tests d'interface pilotent la vraie fenêtre : onglet Analysis (notation, bornes de BPM qui gardent une octave, décimales, parallélisme, écriture des tags), clic droit sur la racine d'une bibliothèque isolée puis clic sur **Analyze folder** (sous-dossiers inclus, résultats visibles dans les lignes, changement de notation immédiat, second lancement sans effet), clic droit sur un morceau de la liste puis **Analyze** et **Re-analyze**.

Résultat sur ce poste : les nouveaux tests passent. Les mêmes échecs préexistants apparaissent avant et après ce travail. Comparaison faite sur une copie de `HEAD` (`git worktree`, supprimée ensuite) : `tests/unit/test_conversion_queue.py` (2), `tests/unit/test_workspace_model.py` (1), `tests/integration/test_conversion_ffmpeg.py` (8), et dans `tests/ui` huit échecs et une erreur identiques (`test_browser_navigation`, `test_column_selection`, `test_convert_view`, `test_incremental_scan_and_scroll`, `test_metadata_editor`, `test_player_views` ×2, `test_track_hover`), dont plusieurs ne réussissent qu'isolés. Sur `HEAD`, la suite complète s'interrompt aussi par une exception native (`0xe24c4a02`), déjà notée à l'étape 09 ; le test natif libmpv a été exclu de l'exécution.

### Migration 015 sur une copie de la base réelle

La migration a été appliquée à une copie cohérente (API de sauvegarde SQLite, ouverture en lecture seule de l'original) de la base de l'utilisateur : schéma 14 avec 2 764 morceaux et l'historique 1–14 dont la migration 010 retirée. Résultat : migration 15 appliquée, tables `track_analysis` et `track_waveforms` créées, tables d'analyse de la migration 010 conservées, sauvegarde `v14` créée, second passage sans effet. L'original n'a pas été modifié.

### Conflits de tags (FLAC, Ogg, Opus)

Un fichier qui stocke un champ sous deux noms de tag (`KEY` et `INITIALKEY`, `BPM` et `TEMPO`) refusait toute édition de ce champ (« … has multiple tag aliases; editing is disabled »). Quand l'écriture des tags est activée, l'analyse met désormais ces valeurs de côté comme conflit au lieu d'échouer, et la liste **Tag conflicts** de l'activité Tasks propose de remplacer : le code supprime tous les anciens noms et valeurs du champ et écrit la nouvelle valeur sous `INITIALKEY`, `BPM`, `DATE`, `COMMENT` ou `TRACKNUMBER`.

Vérifié sur un FLAC produit par FFmpeg à partir d'un signal synthétique et doté de `KEY`/`INITIALKEY`, `BPM`/`TEMPO`, d'un tag inconnu et d'une image : refus par défaut ; avec le remplacement de la clé, `KEY` disparaît, `INITIALKEY` porte la nouvelle valeur, `BPM` et `TEMPO` restent tels quels, le titre, l'artiste, le tag inconnu et l'image sont intacts et la signature MD5 de l'audio du FLAC ne change pas ; en résolvant un conflit de clé et de tempo, `KEY` et `TEMPO` disparaissent et `INITIALKEY` et `BPM` portent les valeurs calculées ; un champ non ambigu écrit avec le remplacement se comporte comme une édition normale ; un champ à plusieurs valeurs sous un seul nom compte aussi comme conflit ; une valeur éditée par l'utilisateur depuis l'enregistrement du conflit n'est pas remplacée ; une piste sortie de la bibliothèque est signalée. Dans la vraie fenêtre : le conflit apparaît avec le message d'état, le bouton de remplacement corrige le fichier et retire la ligne, un échec reste affiché avec sa raison, et les boutons d'abandon retirent une ou toutes les lignes.

Non vérifié : l'aspect avec la vraie police (le volet de 240 px a été contrôlé sur une capture sans texte lisible) ; les fichiers de la bibliothèque réelle de l'utilisateur (aucun n'a été modifié) ; MP3 et M4A, dont les adaptateurs n'ont pas ce type d'ambiguïté et ignorent l'option.

Limites : le remplacement supprime définitivement l'ancienne valeur du second nom ; l'**Undo** de l'éditeur de métadonnées ne restaure qu'une valeur, sous le nom standard. Le rafraîchissement différé de l'explorateur ne s'exécute plus quand l'arrêt des tâches a commencé (il levait une exception à la fermeture).

### Capture

Aucune capture n'est versionnée : le mode `offscreen` n'a pas de police et affiche des carrés à la place du texte. La mise en page de l'onglet Analysis (onglets General/Analysis, choix Camelot/Classique, boutons − / +, choix des décimales, interrupteur) a été contrôlée sur une capture hors écran, sans lecture possible du texte.

## Non vérifié

- Précision du tempo et de la tonalité sur de la vraie musique, notamment des pistes à tempo variable, des mixes, des sons peu tonals.
- Comportement et durée sur de très gros dossiers, mémoire, réactivité de l'interface pendant un lot, choix du nombre d'analyses en parallèle.
- Recette manuelle avec la vraie police et la plateforme Windows ; lecture d'un morceau dont la waveform vient d'être stockée dans l'application complète (le test d'intégration utilise un faux lecteur).
- Écriture des tags sur des formats autres que WAV (ID3 dans un WAV vérifié) ; le M4A n'accepte qu'un BPM entier et l'application l'arrondit.
- Paquet Windows : `scripts/build_windows.ps1` n'a pas été lancé (consigne du dépôt).

## Limites connues

Un peu plus d'un morceau sur deux de la bibliothèque de l'utilisateur reçoit la même tonalité qu'un autre outil, et près d'un sur cinq est à une quinte ou relatif : la tonalité est une aide, pas une vérité. Le drapeau « valeur éditée » n'est pas retiré par **Undo** de l'éditeur de métadonnées. Modifier la plage de BPM ne change pas les résultats déjà stockés : il faut **Re-analyze**. Les anciennes tables d'analyse de la migration 010 restent inertes. Le cache disque `waveforms` de l'ancienne version n'est plus lu et n'a pas été supprimé.
