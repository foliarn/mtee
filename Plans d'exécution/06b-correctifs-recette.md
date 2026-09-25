# Complément 06b — Correctifs de recette et raccord aux étapes 07 à 10

ExecPlan préparé le 2026-09-25 et maintenu pendant l'exécution. Suivre `PLANS.md` et `AGENTS.md`. Les chemins sont relatifs à la racine du dépôt. Les numéros de ligne désignent le commit de référence `b180b120d7f63104a7d9cc3218fb0af2aceeb5b1` et servent de repères ; relire les symboles si le code a évolué. Les résultats implémentés et les limites vérifiées sont consignés dans `docs/validation/06b-correctifs-recette.md`.

## Objectif et résultat observable

Résoudre les quatorze retours de recette ci-dessous sans construire une seconde application autour des services existants. L'utilisateur retrouve sa bibliothèque au démarrage, lit avec des pochettes adaptées à la taille affichée, modifie les métadonnées des formats vérifiés, personnalise les colonnes, conserve sa position de navigation et déplace ou copie ses fichiers par des commandes cohérentes. Les dates de fichiers deviennent des colonnes puis des critères du moteur de recherche du plan 10.

Ce complément accompagne les jalons clés 07 à 10. Les étapes 11 et suivantes restent hors du travail nocturne. L'ordre produit conversion → waveform → analyse → organisation demeure. Le qualificatif « implémenté » des étapes 00 à 06 ne vaut pas acceptation de toutes leurs limites : le rapport 05 documente une écriture limitée au WAV, et les recettes 04/05 distinguent tests offscreen, écoute réelle et distribution Windows propre.

## Progress

- [x] 2026-09-25 — Lire les plans 07, 08, 09 et 10, `PLANS.md`, le contrat produit et les sources concernées.
- [x] 2026-09-25 — Reformuler les 14 retours, clarifier les colonnes figées et la conservation du scroll avec l'utilisateur.
- [x] 2026-09-25 — Reproduire le défaut de colonnes dans un moteur QML offscreen avec une bibliothèque synthétique isolée.
- [x] 2026-09-25 — Consulter le journal Windows et identifier deux événements concernant MTEE, sans attribuer arbitrairement le crash de python.exe.
- [ ] A0 — Protections de fermeture et 20/20 smoke après changement; cause native toujours non démontrée et la suite intégration+UI a reproduit un incident intermittent (détails dans `docs/validation/06b-correctifs-recette.md`). À rouvrir avant de qualifier R05 de corrigé.
- [x] A1 — Colonnes, îlot, pochettes, bitrate et survol implémentés; 6 tests ciblés passent, paquet reconstruit et 20/20 smoke. La recette multi-DPI et audio réel reste à faire.
- [x] A2 — Reprise silencieuse/priorité basse, relecture des seuls fichiers nouveaux/modifiés et modèles Qt incrémentaux vérifiés sur 140 WAV temporaires; vrai redémarrage et grande bibliothèque réelle restent à recetter.
- [ ] A3 — Ajouter dates de fichiers, révélation Windows, destinations et interactions de fichiers.
- [ ] Valider et livrer A avant le développement fonctionnel de 07.
- [x] B — Après runtime/fixtures, adaptateurs ID3, Vorbis et MP4 étendus, lecture Key corrigée; round-trip sur copies synthétiques, conservation et Undo testés. La recette manuelle par format reste non réalisée.
- [x] 2026-09-25 — Prérequis de B/07 : runtime FFmpeg x64 verrouillé dans `resources/native/ffmpeg/manifest.json`, distribution vérifiée et 9 fixtures synthétiques disponibles localement; résultats dans `docs/validation/07-conversion.md`.
- [ ] Achever 07, puis 08 et 09 avec les contrôles de non-régression de ce document.
- [ ] Préparer la revue 10 sur les analyses réelles et consigner la décision utilisateur.
- [ ] C — Après cette revue, intégrer les dates aux critères typés de 10 et achever 10.
- [ ] Compléter les preuves, limites, commits et publications de chaque sous-jalon.

## Surprises & Discoveries

2026-09-25 — Graphe code-review-graph à jour sur `b180b12`, puis vérification dans les sources. Graphify a servi à localiser `ArtworkProvider`, `WorkspaceModel`, `MetadataEditorModel`, `PlayerService` et la fermeture. Les relations Qt/QML dynamiques doivent être vérifiées dans le code et les tests, même si le graphe ne les expose pas.

2026-09-25 — Expérience sur une fixture WAV générée, base temporaire, audio simulé indisponible, rescans désactivés uniquement dans le harnais : avant activation d'Album, `tab.hiddenColumns` vaut `["album","duration","format","filename"]`. Après `toggleColumn(tabId, "album")`, Python et QML voient `["duration","format","filename"]`, mais `columns.keys` reste `["title","artist","genre","bpm","key"]`. `Array.isArray(tab.hiddenColumns)` et `Array.isArray(tab.columnOrder)` valent tous deux `false`. La cause de R07 est reproduite ; la simple assertion de persistance Python ne la détecte pas. `islandEnabled` vaut également `false` dans cette instance réelle.

2026-09-25 — Lecture des événements Application/1000 des trois derniers jours : le 24 septembre à 19:01:36 et le 25 septembre à 00:43:45, heure locale, `MTEE.exe` échoue dans `qwindows.dll` 6.9.3.0, exception `0xc0000005`, offset `0x3fce`. Aucun événement python.exe n'est apparu dans cette requête bornée. Ces événements ne prouvent ni l'identité du crash signalé ni une faute de Qt lui-même : une corruption en amont peut se manifester dans ce module.

2026-09-25 — `docs/validation/05-metadonnees.md` confirme explicitement la restriction aux WAV PCM/ID3v2.4. Les tests UI actuels de fichiers appellent notamment `acceptTrackDrop(...)` directement : ils ne démontrent pas qu'un geste de glisser-déposer réel aboutit. Le test de visibilité des deux lecteurs utilise `DemoWorkspace` ; il ne prouve pas la valeur par défaut du workspace réel.

Les causes du scintillement, du saut de scroll et du crash restent à reproduire dans leur parcours exact. Les défauts statiques associés sont identifiés ci-dessous ; ne pas transformer une piste plausible en diagnostic certain.

2026-09-25 — A0 — Après les mesures de fermeture, les 20 fermetures minimales Python et 20 du paquet sont sans échec. En revanche, `pytest -q` et le groupe intégration+UI ont produit une exception native intermittente `0xe24c4a02` pendant la lecture/fermeture libmpv, suivie d'un access violation dans pytest-qt; le groupe d'intégration seul a réussi 25/25. Les modules impliqués et la relation causale ne sont pas établis. Les garde-fous de durée de vie restent utiles, mais le crash utilisateur n'est pas corrigé au sens causal.

2026-09-25 — A1 — `Array.from` fixe le choix d'Album dans le menu avec un vrai `WorkspaceModel`; `HoverHandler` maintient les actions visibles pendant les passages Play↔Info simulés. Le provider rend 256 px depuis une fixture synthétique 300×120. Le paquet contrôlé reste à 2,26 Mo et passe 20/20 démarrages isolés. Les scènes covers réelles rapides, DPI Windows interactif, toutes colonnes et redémarrage complet restent hors des tests ciblés.

2026-09-25 — A2 — Fixture UI de 140 WAV: deuxième passage silencieux n'a fait aucune lecture Mutagen; changement + ajout ont fait deux lectures, retrait disparu après scan complet. Un `QTest.mouseDClick` sur la ligne 84 a lancé son UUID sans fermer le dossier; la ligne d'ancrage est restée en tête après mutations, sans `modelReset` liste/arbre. Les modèles Qt sont diffés par identifiant. Une validation groupée avec `test_browser_navigation.py` a écrit `Windows fatal exception 0xe24c4a02` du thread libmpv, mais pytest a terminé 20 réussis/2 ignorés; aucune attribution causale. Le paquet A2 a aussi passé 20/20 démarrages isolés.

2026-09-25 — A3 partiel (R06/R13) — migration 007, collecte UTC en ns, colonnes masquées Date created/Date modified, Info et demande d'ouverture Explorer via argument structuré implémentés. Suite ciblée 22/22, Ruff/formateur/pyright propres; paquet 2,27 Mo, hash libmpv vérifié, 20/20 smoke isolés. Copy, mise à jour après conversion, choix de destination et geste de déplacement restent à implémenter; Explorer jamais vérifié manuellement. A3 non clos.

2026-09-25 — A3 partiel (R08) — migration 008 crée un journal isolé des copies; les copies vérifient taille/SHA-256, gardent la source, enregistrent un nouvel UUID et n'ont pas d'Undo. Les dossiers catalogués alimentent Move to/Copy to; le presse-papiers MTEE conserve un snapshot d'UUID et le collage ouvre un aperçu, y compris avec un dossier vide actif. Les tests automatiques vérifient copie, collision et récupération temporaire. QtTest n'a pas déclenché le parcours natif Drag/Drop : le test existant valide seulement le routage direct du dépôt. A3 reste ouvert.

2026-09-25 — 07/runtime et fixtures — BtbN `lgpl-shared` FFmpeg `n9.0.2-3-ga5923073bf-20260924`, archive 76 974 101 octets et SHA-256 verrouillé; ffmpeg/ffprobe et sept DLL vérifiés. Les encodeurs annoncés incluent AAC, ALAC, FLAC, MP3, Vorbis et Opus. Neuf fichiers 3 s générés sous `.local/fixtures/07/audio`, chacun identifié par ffprobe; AAC ADTS et M4A AAC sont `aac`, M4A ALAC est `alac`. Une deuxième génération destinée aux tests de métadonnées ajoute une PNG synthétique dans `.local/fixtures/07-metadata/audio`. Un build PyInstaller de test a d'abord dupliqué les DLL à la racine via son analyse PE; la copie explicite après build règle le doublonnage, conservant un seul ensemble runtime dans le répertoire interne. Paquet Windows total : 412 961 278 octets. Une copie sous `%TEMP%`, hors checkout et lancée depuis son propre dossier, a passé `MTEE.exe --smoke-test` (code 0) et régénéré les neuf fixtures avec le runtime copié. Ce n'est pas une machine Windows propre ni une recette interactive.

2026-09-25 — B (R03/R12) — Adaptateurs ID3 WAV PCM v2.4, MP3/AIFF PCM v2.3 et v2.4, Vorbis comments FLAC/Ogg Vorbis/Opus, et M4A AAC/ALAC. Tests de service sur copies synthétiques : neuf champs modifiés puis annulés dans chacun des huit conteneurs/formats éditables, hash PCM décodé égal avant/après, tags hors patch et pochettes vérifiés; couverture incluant répétitions existantes, total de piste, marqueurs inconnus, atomes et reprise Undo. AIFC compressé portant une extension AIFF est refusé après inspection FORM. 21 tests ciblés réussis, Ruff et Pyright propres. AAC/ADTS reste explicitement non éditable. Date ID3v2.3 refusée après échec d'un round-trip Mutagen TYER/TDRC; titre et autres champs v2.3 sont vérifiés. M4A BPM = entier 1–1000 dans `tmpo`, Key = atome libre UTF-8 `initialkey`; la relecture de cet atome est ajoutée à `MetadataReader`. Le paquet reconstruit est à 412 978 343 octets; copie externe smoke code 0 et neuf fixtures régénérées avec le runtime copié. Recette UI et tests manuels sur chaque format/version non réalisés; A0/R05 et A3 manuel restent ouverts.

## Decision Log

2026-09-25 — Codex — Répartir ce complément en A avant 07, B dans le début de 07 et C dans 10. B réutilise FFmpeg pour générer et vérifier des fixtures audio ; le runtime n'est pas ajouté rétroactivement aux livraisons A/B historiques. Les interfaces d'adaptateurs peuvent être préparées en A, mais les formats ne deviennent éditables qu'après leurs preuves.

2026-09-25 — Utilisateur — « Les colonnes ne changent pas quand je choisis un nouveau critère » désigne le choix des colonnes, pas encore le moteur de filtres avancés. Le double-clic sur le titre 84 d'une liste de 100 doit laisser le scroll en place, sans retour au dossier parent.

2026-09-25 — Codex — Les colonnes Date created et Date modified sont des données factuelles de fichiers, indépendantes du vocabulaire de tags. Leur collecte et affichage appartiennent à A ; les requêtes composées/enregistrées appartiennent à C après la revue du plan 10.

2026-09-25 — Codex — Conserver l'architecture et la maquette approuvées. Les esquisses de nouveaux menus de destination, du presse-papiers et des dates décrites ici sont à rendre examinables pendant A3 ; une refonte générale demanderait la revue produit prévue par le dépôt. Les correctifs ordinaires n'ont pas besoin d'une nouvelle autorisation de développement.

2026-09-25 — Codex — Contrat proposé pour le presse-papiers : Ctrl+A sélectionne, Ctrl+C copie, Ctrl+X coupe, Ctrl+V présente l'aperçu correspondant. Une copie conserve la source et reçoit un nouvel UUID ; un déplacement conserve l'UUID. Ne jamais faire supprimer une source par un raccourci présenté comme Copy. Mettre cette décision à jour si l'utilisateur précise explicitement un autre comportement avant l'exécution.

2026-09-25 — Codex — Le journal de Copy utilise une table `file_copy_operations` dédiée (migration 008), afin de ne pas élargir le journal transactionnel Move/Undo sans récupération compatible. Les copies n'offrent pas Undo tant que la corbeille stricte n'est pas vérifiée.

## Outcomes & Retrospective

Exécution en cours. A0 garde des protections de durée de vie mesurées, mais les suites intégration/UI ont de nouveau imprimé le SEH libmpv; le lien avec le crash utilisateur n'est pas prouvé et R05 reste ouvert. A1 et A2 sont testés sur fixtures; le paquet A2 a réussi 20/20 démarrages isolés. A3 est partiel : dates et Explorer (sans recette manuelle), copie hashée sur fixtures, destinations catalogue et presse-papiers sont implémentés; le paquet A3 a réussi 20/20 smoke isolés. Le drag natif, le vrai collage/clavier, l'ouverture Explorer et les contrôles multi-panneaux restent à prouver ou raccorder. Le runtime et B sont exécutés sur copies synthétiques, et non en recette UI; le jalon 07 reste à achever. Aucune collection personnelle n'a été utilisée ou modifiée.

## Ordre de travail pour la session nocturne

| Passage | Travail autorisé et dépendances | Condition de passage |
| --- | --- | --- |
| A0 à A3, ce document | Stabilisation des fonctions existantes ; dates/colonnes et interactions de fichiers | Tests appropriés, comportement vérifié, paquet contrôlé ; limitations identifiées individuellement |
| Début de [07](07-conversion.md) | Inspection, capacités et runtime FFmpeg/ffprobe ; création de fixtures synthétiques redistribuables ou locales | Binaires verrouillés, provenance et paquet vérifiés |
| B, ce document | Adaptateurs de métadonnées et matrice d'écriture ; réutilisables pour le transfert de tags de 07 | Round-trip sur copies synthétiques, Undo, contenu audio et tags/pochettes non ciblés contrôlés; recette manuelle reste non réalisée |
| Suite de 07 | Aperçu, file de conversion, validation et filiation | Recette 07 et non-régression A/B |
| [08](08-waveform.md) | Waveform sur le lecteur désormais visible et illustré | Même PlayerService, pochettes/timeline/navigation conservées |
| [09](09-analyse-sans-ml.md) | Analyse sur le décodage commun | Provenances séparées, corrections manuelles conservées |
| Revue [10](10-tags-recherche-playlists.md) | Préparer `docs/decisions/10-tags-review.md` à partir des résultats réels | Accord explicite sur le vocabulaire ; le silence nocturne n'en tient pas lieu |
| C et suite de 10 | Recherche avec dates, filtres enregistrés, tags approuvés et playlists | Recette finale transversale |

Ne pas exécuter 11+ par anticipation. Si la revue 10 n'a pas déjà eu lieu, terminer le dossier examinable, enregistrer le point de reprise et s'arrêter avant son implémentation fonctionnelle. Ne pas attendre passivement une réponse pendant la nuit. Cette revue n'empêche pas de terminer auparavant tous les correctifs de A/B et les jalons 07 à 09.

Si un défaut bloquant reste reproductible, ne pas déclarer le passage validé. Achever les travaux indépendants qui restent sûrs, conserver les preuves et une reprise précise. Un crash reproductible pendant les écritures interdit de déclarer celles-ci acceptées. L'absence de matériel pour un profil de platine n'empêche pas la conversion générique selon 07. L'absence d'une machine Windows propre doit rester une limite de distribution explicite, pas un succès inventé.

## Inventaire reformulé et diagnostic

| ID | Problème compris et résultat attendu | État du diagnostic | Placement |
| --- | --- | --- | --- |
| R01 | Les covers de la mosaïque sont floues ; utiliser la définition disponible adaptée à la vue et au DPI | Plafond 96 px confirmé ; qualité des covers personnelles non examinée | A1 |
| R02 | Chaque démarrage réindexe visiblement les dossiers ; afficher le catalogue conservé et vérifier discrètement les changements | Scan complet et messages confirmés | A2 |
| R03 | Les tags paraissent tous non modifiables ; rendre éditables les formats/champs dont l'écriture est vérifiée | Restriction volontaire à WAV confirmée, reste du plan 05 incomplet | B |
| R04 | Le bitrate brut est difficile à lire ; afficher par exemple `320 kbps` | Entier bits/s converti en texte sans unité confirmé | A1 |
| R05 | Une erreur de lecture mémoire ferme le processus ; supprimer le crash et disposer d'un diagnostic exploitable | Cause du crash python.exe inconnue ; événements Qt/MTEE observés | A0 |
| R06 | Ajouter création et modification du fichier aux dates exploitables | mtime stocké, création et exposition UI absentes | A3 puis C |
| R07 | Choisir une colonne ne modifie pas la liste | Conversion séquence Qt/Array JavaScript reproduite | A1 |
| R08 | Move doit être accessible par glisser-déposer, sélection/presse-papiers et destinations cataloguées | Fonction partielle, extension d'interactions nécessaire | A3 |
| R09 | Play ne fait pas apparaître le petit lecteur | Préférence initialisée à false et non persistée confirmée | A1 |
| R10 | Les boutons Play et Info clignotent sous la souris | Dépendance circulaire probable entre hover de la ligne et visibilité du bouton | A1 |
| R11 | Aucune vraie cover dans l'îlot ni Fullscreen player | Liaison `source` manquante confirmée dans les deux vues | A1, contrôle en 08 |
| R12 | Le message « Writing has not been verified for this audio format » est opaque | Motif générique émis par l'unique adaptateur WAV | B avec R03 |
| R13 | Show in Explorer n'ouvre pas l'Explorateur Windows sur le fichier | Commande raccordée à l'explorateur interne confirmée | A3 |
| R14 | Double-cliquer loin dans la sidebar fait remonter la liste au parent ; rien ne doit bouger | Ouverture du parent au premier clic et resets de modèle identifiés ; parcours exact à instrumenter | A2 |

### R01 — Définition des pochettes

Sources : `src/mtee/persistence/library_repository.py::_track_view` (vers 520) produit `image://artwork/<uuid>/<generation>/96`. `src/mtee/models/artwork_provider.py::requestImage` borne ensuite par le minimum entre ce 96 et `requested_size`. `src/mtee/qml/Mtee/CoverArt.qml` agrandit cette image sans demander de définition liée à la taille affichée. La mosaïque de `src/mtee/qml/components/TrackListView.qml` utilise exactement la même URL que la miniature de ligne. `src/mtee/services/artwork_service.py::thumbnail` sait pourtant accepter jusqu'à 1024 pixels et refuse d'agrandir artificiellement la source.

Correctif : exposer l'identité/révision de la cover indépendamment de la taille, puis demander depuis le composant une taille physique `ceil(taille logique × devicePixelRatio)` bornée. Utiliser quelques paliers documentés pour éviter une nouvelle entrée de cache à chaque pixel de redimensionnement. Une simple propriété `sourceSize` ne suffira pas tant que l'URL `/96` impose le plafond. Conserver chargement asynchrone, contrôle de révision avant/après, limite LRU de 128 Mio et limites de décompression. Une invalidation doit atteindre le cache Qt comme le cache Python. Préférer l'image de couverture frontale lorsqu'elle est identifiée ; vérifier extraction FLAC/Ogg/MP4 avant de conclure qu'une pochette est absente. Un bloc `metadata_block_picture` est une structure FLAC encodée, pas directement un PNG/JPEG après base64.

Recette : fixture avec image détaillée 1200×1200, puis image basse définition 64×64, absente, corrompue et non carrée. Comparer ligne, mosaïque et plein écran à 100/150/200 % DPI avec la cover source. Montrer par dimensions retournées que la mosaïque ne reçoit plus 96 px ; conserver le ratio et un repli neutre. Ne pas promettre de restaurer les détails d'une source déjà petite. Étendre `tests/unit/test_artwork_service.py`, créer `tests/unit/test_artwork_provider.py` et compléter le test UI des covers.

### R02 — Catalogue restauré et vérification discrète

Sources : `src/mtee/app.py::_build_runtime` appelle `workspace.resumeRoots()` (vers 239). `src/mtee/models/workspace_model.py::resumeRoots` (645) relance `rescanRoot` pour toutes les racines ; son worker appelle `MetadataReader.read` pour chaque entrée, même inchangée. `_on_scan_batch` et `_on_scan_finished` publient les messages Indexed/Indexing complete. `LibraryRepository.begin_scan` expose l'état scanning et `ExplorerPane.qml` l'affiche. Ce travail est déjà en arrière-plan : il faut surtout le rendre incrémental et non intrusif.

Correctif : restaurer immédiatement le catalogue SQLite, puis programmer une réconciliation discrète de faible priorité. Séparer son intention de celle d'Add folder/Rescan explicites. Réutiliser les métadonnées et la génération des fichiers dont `SourceRevision` correspond ; lire seulement les fichiers nouveaux ou modifiés et réessayer les erreurs pertinentes. Énumérer les sous-dossiers avec mémoire bornée : le mtime de la racine seule ne permet pas de garantir qu'aucun descendant n'a changé. Les nouveautés apparaissent par mises à jour regroupées, sans reset de toute la vue.

Ne pas afficher pour cette routine de messages de progression, de toast de fin, d'état Scanning dans l'arbre ni de tâche de routine visible. Conserver un état technique interne et les erreurs/action requise dans un diagnostic approprié. Les scans explicitement demandés gardent leur progression et annulation. Une déconnexion garde les entrées et les marque indisponibles ; seul un parcours complet réussi peut conclure à une disparition. Revalider les chemins avant lecture/écriture même si le catalogue est conservé. Refuser la publication d'un ancien scan annulé lorsque sa génération a été remplacée.

Recette : deux démarrages successifs du même catalogue ; au second, zéro relecture Mutagen des fichiers inchangés, aucune notification de réindexation, UI utilisable dès restauration. Ajouter/modifier/retirer une copie entre les démarrages ; vérifier découverte, invalidation des caches et références conservées. Tester dossier déconnecté, accès partiel, annulation et Rescan demandé pendant la routine. Adapter `tests/ui/test_browser_navigation.py` et `tests/ui/test_file_actions.py`, qui dépendent actuellement du scan au démarrage : préparer explicitement le catalogue lorsqu'un scan n'est pas l'objet du test. Compléter `tests/integration/test_scan_recovery.py` et créer `tests/integration/test_incremental_refresh.py`.

### R03 et R12 — Écriture des tags et explication des restrictions

Sources : `src/mtee/services/metadata_writer.py::MetadataEditService` utilise uniquement `_wav_id3` dans `capabilities`, l'inspection, la préparation, la sauvegarde forcée `v2_version=4` et la vérification. `src/mtee/services/metadata_adapters/id3.py::Id3WaveAdapter` refuse tout autre conteneur et ID3v2.3 ; sa constante `reason_unverified` produit le message signalé. `src/mtee/models/metadata_editor_model.py::_fields_for_sources` consulte ces capacités ; `src/mtee/qml/components/FieldEditor.qml`/`InfoPanel.qml` suivent l'état éditable. Voir `docs/metadata-mapping.md`, `docs/validation/05-metadonnees.md` et les tests metadata existants.

Correctif B : extraire un contrat d'adaptateur par famille réelle de tags : détection, capacités par champ, inspection, préparation, sauvegarde respectant la version, photographie des données non modifiées et vérification après écriture. Remplacer les usages WAV codés en dur dans le service, y compris sa validation des slots et la sauvegarde. Réutiliser le journal, le fichier temporaire voisin, `FileReplacement`, les verrous, les révisions et Undo. Le format est déterminé par inspection ; une extension seule n'autorise pas l'écriture.

Traiter successivement MP3/ID3v2.3 et v2.4, FLAC/Vorbis comments, MP4/M4A AAC et ALAC, AIFF/ID3, Ogg Vorbis et Opus ; garder les WAV déjà pris en charge. Ajouter les modules correspondants sous `src/mtee/services/metadata_adapters/`, sans imposer `save(v2_version=4)` aux autres familles. Les fichiers AAC/ADTS bruts dont les tags ne permettent pas un aller-retour sûr restent explicitement non modifiables. Ne pas activer un format simplement parce que Mutagen sait le lire.

Chaque adaptateur doit préserver tags inconnus, pochettes (octets et attributs), valeurs/slots non ciblés, alias et total de piste. Choisir explicitement la politique des dates ID3v2.3 et valeurs BPM/Key MP4, et la consigner dans la matrice. Ne pas transformer sans accord une valeur multiple en chaîne unique. Une ambiguïté bloque le champ concerné, pas toutes les éditions sûres du format. Les capabilities doivent être calculées en worker, indexées par UUID/révision et invalidées après mutation : aujourd'hui leur consultation peut rouvrir les WAV depuis une propriété UI.

Le message utilisateur doit expliquer le motif et l'action utile : format/version non pris en charge, champ ambigu, source non inscriptible, lecture active ou récupération nécessaire. Afficher par exemple `MP3 metadata editing is unavailable in this build` uniquement si c'est vrai, et un motif de champ spécifique sinon. Les caractéristiques techniques (durée, codec, bitrate, taille, chemin) restent en lecture seule. Modifier R12 ne consiste pas à masquer le motif ni à rendre tous les champs éditables.

Recette : après installation du runtime de 07, générer les fixtures dans un répertoire isolé ; consigner la recette et les droits. Pour chaque format/version activé, modifier un champ, relire, redémarrer, faire Undo et comparer les données non ciblées. Vérifier le contenu audio via une empreinte du flux audio ou du PCM décodé avant/après avec le même décodeur, en plus des vérifications de conteneur ; une empreinte du fichier entier doit naturellement changer après édition. Tester sélection mixte, conflit externe, fichier lu, permissions, sauvegarde interrompue et récupération. Étendre `tests/unit/test_metadata_edit.py`, `tests/integration/test_metadata_roundtrip.py`, `tests/integration/test_metadata_recovery.py`, `tests/ui/test_metadata_editor.py`. Une matrice partielle reste partielle, avec les formats manquants listés ; elle ne clôture pas tout R03.

### R04 — Débit lisible en kbps

Sources : `src/mtee/persistence/library_repository.py::_track_view` expose `technical.bitrate` en bits/s (vers 510) ; `WorkspaceModel.infoFile` (390–406) applique `str` sans formatage. La présentation technique réutilisée dans les lecteurs et les futures colonnes doit suivre la même convention.

Correctif : conserver une valeur numérique en bits/s pour tri/recherche/conversion et ajouter un formatage de présentation partagé en base 1000. Exemple 320000 → `320 kbps`, valeur absente/non positive → `—`. Fixer un arrondi commun pour le VBR, sans transformer cette estimation en valeur exacte. Ne pas stocker `320 kbps` à la place du nombre. Tester le formatter, Info, la future colonne Bitrate et les vues qui l'affichent ; un tri numérique de 96, 128, 320 doit rester correct.

### R05 — Violation d'accès native

Signal utilisateur : instruction `0x00007FFF9A8F825A`, lecture de `0x000000000000008F`, processus `python.exe`. L'adresse seule ne désigne pas une fonction stable ; ne pas promettre un correctif à partir de celle-ci.

Sources à inspecter en priorité : `src/mtee/platform/windows_frame.py::_NativeFilter`, `WindowFrame.attach`, `_handle_native` et les appels ctypes Win32 ; `src/mtee/app.py::_shutdown_services` ; `src/mtee/services/mpv_backend.py::close` ; `src/mtee/services/jobs.py::shutdown` ; `src/mtee/models/artwork_provider.py::requestImage` ; `src/mtee/persistence/database.py::close`. Constats statiques : le filtre natif est installé sans méthode explicite de retrait ; `MpvBackend.close` détruit son contexte après un join de deux secondes sans vérifier que le thread est arrêté ; le shutdown des jobs peut retourner avec des workers actifs puis la base est fermée ; les lectures d'images Qt n'appartiennent pas au pool JobService. Ces risques doivent être traités selon une reproduction, sans attribuer chacun au crash rapporté.

A0 commence par un harnais de sous-processus avec fichiers synthétiques et données dédiées. Enregistrer versions Python/PySide/Qt/libmpv, backend graphique, scénario et codes de sortie, puis événements Windows et traces disponibles. Comparer démarrage/fermeture, lecture/changement rapide, mosaïque en chargement, maximisation/restauration et fermeture pendant jobs. Isoler successivement cadre natif, audio et chargement d'images dans le harnais de diagnostic ; ne pas supprimer une fonctionnalité en production pour cacher le défaut. Vérifier signatures/restypes ctypes, largeur des handles, pointeurs et ordre de destruction. Contrôler les DLL du paquet et leur provenance avant tout changement de version.

Implémenter une fermeture idempotente : refuser les nouveaux travaux, arrêter timers/callbacks, retirer le filtre natif pendant que l'application et la fenêtre existent, attendre la fin effective des consommateurs puis libérer leurs ressources. Un timeout ne prouve pas qu'un worker est mort. Ne pas fermer SQLite ni détruire un contexte mpv encore accessible. Le mécanisme exact doit être compatible avec le thread Qt et mesuré ; éviter une attente bloquante infinie sur l'UI. Traiter aussi l'échec partiel de démarrage.

Créer `scripts/diagnose_windows_runtime.py` et `tests/integration/test_runtime_shutdown.py` pendant A0. Le script doit offrir `--help`, un répertoire de données explicite, un nombre borné de cycles, un timeout par enfant et un rapport sans chemins privés. Les tests Qt/plateforme utilisent des enfants séparés pour qu'un crash ne tue pas la suite. Les tests natifs ne peuvent pas être remplacés par `QT_QPA_PLATFORM=offscreen`. Le bruit SEH LuaJIT `0xe24c4a02` déjà documenté dans `docs/native-dependencies.md` est distinct de l'access violation `0xc0000005` ; désactiver faulthandler n'est pas un correctif.

Acceptation : même scénario fautif avant/après si reproductible, puis série bornée proposée de 20 cycles par scénario déterminant dans Python et l'EXE ; aucune violation d'accès ni thread orphelin. Ce nombre est une cible de recette, pas une preuve universelle. Si le crash utilisateur demeure non reproduit, livrer l'instrumentation et les risques réellement corrigés, inscrire « crash d'origine non confirmé résolu » et garder R05 ouvert. Lire le journal est une preuve complémentaire, pas une reproduction.

### R06 — Dates du système de fichiers

Sources : `src/mtee/domain/tracks.py::SourceRevision.observe` recueille taille, `st_mtime_ns` et identité ; `src/mtee/persistence/migrations/002_library.sql` stocke mtime mais aucune date de création. `_track_view`, les constantes de colonnes de `WorkspaceModel` et `TrackListView.qml` n'exposent pas ces dates. Ne pas confondre la date musicale du tag avec celle du fichier ou la date d'ajout au catalogue.

Correctif A3 : ajouter des valeurs nullable `file_created_at_ns` et `file_modified_at_ns` (noms définitifs à harmoniser avec le domaine), recueillies en worker. Réutiliser mtime existant ; prendre la création via `st_birthtime_ns` sous Python 3.12/Windows. Une plateforme sans birthtime donne une absence, jamais un faux équivalent Unix ctime. Garder la création hors du contrat `SourceRevision` : c'est une propriété descriptive, pas un nouvel identifiant. Prévoir migration transactionnelle et sauvegarde, remplissage progressif des anciennes lignes et index utiles.

Afficher Date created et Date modified dans le sélecteur de colonnes et Info ; conserver timestamp UTC numérique en stockage, affichage local avec convention explicite. Rafraîchir après édition, déplacement, copie et conversion ; présenter les dates réellement observées sur la destination, sans inventer de conservation. Une copie a une identité propre ; sa date ne doit pas être héritée automatiquement du morceau source. Tester aussi un déplacement inter-volume dont l'adaptateur conserve certains attributs.

Correctif C : enregistrer `file.created_at` et `file.modified_at` comme champs de date du registre `src/mtee/domain/search.py` de 10, avec avant/après/intervalle/présence et politique explicite des valeurs inconnues. Les bornes de journée sont traduites du fuseau local vers UTC ; la borne supérieure d'une journée est le début du jour suivant, y compris aux changements d'heure. Utiliser SQL paramétré, comparer les nombres, et vérifier critères sauvegardés/réouverts. Ajouter `tests/unit/test_file_dates.py` en A3, puis étendre les tests search de 10 en C.

### R07 — Colonnes figées

Sources et cause reproduite : `src/mtee/qml/components/TrackListView.qml` (35–39) utilise `Array.isArray` pour `tab.columnOrder` et `tab.hiddenColumns`. Les séquences venant de `WorkspaceModel.groups` ne satisfont pas ce test. Le menu appelle correctement `WorkspaceModel.toggleColumn`, et la base reçoit le bon état ; le calcul de `columns` remplace toutefois cet état par les defaults.

Correctif : normaliser une fois les séquences Qt dans un vrai tableau JavaScript (par exemple `Array.from` sur une séquence valide) ou exposer un modèle de colonnes Qt explicite. Distinguer liste vide voulue et donnée absente. Ne pas corriger uniquement `hiddenColumns` : traiter ordre, largeurs et autres usages concernés par le même contrat. Centraliser définitions/labels/clés de tri plutôt qu'ajouter plusieurs listes divergentes pour dates et bitrate. Title reste le repère obligatoire de la ligne ; toutes les colonnes facultatives restent configurables.

Créer `tests/ui/test_column_selection.py` pendant A1. Il doit utiliser `WorkspaceModel` réel, cliquer le menu, vérifier les en-têtes et cellules réellement visibles immédiatement, puis après changement d'onglet et redémarrage. Tester tous les éléments facultatifs, suppression de toutes les colonnes facultatives, ordre, largeur, les deux groupes et nouvelle date. Conserver le test unitaire de persistance existant ; il ne couvre pas cette frontière QML. Éviter qu'un clic détruise le menu ou perde le focus avant validation.

### R08 — Déplacement, presse-papiers et destinations

Sources : `src/mtee/qml/components/TrackRow.qml` déclare `DragHandler` et MIME UUID ; `TrackListView.qml::acceptTrackDrop`/`DropArea` et `WorkspaceModel.previewMoveBetweenGroups` n'acceptent que deux groupes distincts. La mosaïque et `ExplorerPane.qml` n'ont pas de parcours équivalent. `TrackListView.qml::Keys.onPressed` sait Ctrl+A, mais quitte immédiatement si le dossier est vide, et ne gère ni copie ni collage. `FileActionsMenu.qml` ouvre Move avec destination vide. `FileOperationService.preview` n'accepte que rename/move/trash. `LibraryRepository.roots()` et `folders(root_id)` fournissent déjà les dossiers découverts, dont les dossiers vides.

Correctif : créer un modèle de destinations à partir du catalogue, exposant toutes les racines et leurs dossiers, avec chemins désambiguïsés, état disponible et recherche si la liste est longue. Le sous-menu `Move to` permet d'atteindre tous ces dossiers, puis ouvre l'aperçu existant ; `Choose folder…` reste accessible. Une sélection de destination ne lance jamais une mutation. Revalider son existence, les collisions et les accès à l'exécution.

Unifier le routage du déplacement depuis liste, mosaïque, onglet de dossier et dossier de sidebar vers le même `FileOperationModel`/service. Autoriser une destination dans le même groupe, un dossier vide et les deux panneaux ; capturer UUID et destination au début de l'action. Implémenter le cycle réel du drag jusqu'au drop : l'appel direct à `acceptTrackDrop` n'est pas une preuve de geste souris. Le dépôt sur soi-même doit être un no-op explicite. Le réordonnancement futur d'une playlist appartient au plan 10 et ne doit pas déplacer de fichiers.

Ajouter `src/mtee/models/file_clipboard_model.py` et le raccord QML. Ctrl+A agit sur les titres visibles du panneau actif ; les champs de texte gardent Ctrl+A/C/X/V natifs. Ctrl+C conserve un instantané d'UUID à copier, Ctrl+X un instantané à déplacer, Ctrl+V utilise le dossier de destination actif et affiche l'aperçu. Le collage doit fonctionner dans un dossier vide ; il ne doit pas être rejeté par le garde `count === 0`. Capturer les références puis résoudre leur chemin actuel via le catalogue, revalider les révisions et signaler les sources disparues. Après déplacement réussi, retirer les éléments terminés du presse-papiers de coupe ; garder les échecs relançables. Distinguer ce presse-papiers de fichiers des affectations de playlist.

Pour Copy, étendre explicitement le domaine/service/journal avec un type copy : écrire vers un temporaire voisin, vérifier les octets, publier sans remplacement, enregistrer un nouvel UUID, conserver la source. Ne pas détourner move en supprimant une étape critique. Si Undo copy est proposé, vérifier identité/empreinte et utiliser la corbeille ; si indisponible, refuser sans suppression permanente. La prise en charge des fichiers collés depuis une application externe n'est pas nécessaire à ce correctif : signaler clairement un contenu non pris en charge, sans lancer de shell depuis QML.

Tests : véritables gestes et raccourcis dans `tests/ui/test_file_actions.py`, cas mosaïque/sidebar/dossier vide, un et deux panneaux, multisélection de 100 titres et champs texte. Compléter `tests/unit/test_file_operation_preview.py` et `tests/integration/test_file_moves.py`, créer `tests/integration/test_file_copies.py`. Vérifier annulation, collision tardive, source modifiée, indisponibilité et reprise ; copies/déplacements se testent exclusivement sur fixtures.

### R09 — Apparition de l'îlot à la lecture

Sources : `WorkspaceModel.__init__` (128) fixe `_island_enabled = False`. `Main.qml` (18) exige playingId et islandEnabled. `setIslandEnabled` (903) ne persiste pas la préférence, `_persist` ne l'écrit pas et `WorkspaceRepository.DEFAULT_WORKSPACE` ne la connaît pas.

Correctif : valeur par défaut vraie pour une session sans préférence, sauvegarde/validation/restauration d'`islandEnabled` dans le document de workspace. Respecter un false explicitement choisi via View/Settings, y compris après redémarrage ; ne pas forcer true à chaque Play. Distinguer absence de morceau, pause, masquage volontaire et plein écran. Garder un seul `PlayerService` et la marge basse déjà prévue pour la liste.

Recette : workspace réel neuf, double-clic/Entrée/Play/menu/sidebar → îlot visible à chargement du morceau ; pause le conserve ; plein écran le masque puis restaure son état ; préférence masquée conservée au prochain démarrage. Compléter `tests/ui/test_player_views.py` avec backend simulé et workspace réel, puis recette audio Windows.

### R10 — Survol stable des boutons Play et Info

Sources : `src/mtee/qml/components/TrackRow.qml` (22, 93–105, fin du fichier) définit hovered par le MouseArea de fond, puis rend visibles des `IconButton` superposés en fonction de ce même hovered. Chaque `src/mtee/qml/Mtee/IconButton.qml` possède son propre MouseArea. Le transfert du survol vers le bouton peut invalider sa visibilité et recommencer le cycle. C'est une hypothèse ciblée à prouver par mouvements de souris ; ne pas affirmer qu'un changement d'icône lié à l'état audio est le même défaut.

Correctif proposé : un `HoverHandler` de ligne couvrant aussi ses enfants, ou un état de survol agrégé stable, indépendant de la visibilité des boutons. Réserver la géométrie des actions ; utiliser une visibilité/opacity cohérente, sans laisser un bouton transparent intercepter les clics lorsqu'il doit être inactif. Préserver commandes clavier et indications de focus. Vérifier qu'un clic Play/Info n'est pas également reçu comme sélection/double lecture par la ligne.

Créer `tests/ui/test_track_hover.py` : entrer dans la ligne, maintenir la souris sur Play et Info, franchir leurs frontières, cliquer, réutiliser un delegate après scroll et tester pause/lecture. Vérifier absence de bascules répétées de visibilité sur curseur immobile et une seule action par clic. Confirmer dans la fenêtre Windows aux DPI retenus.

### R11 — Covers dans les deux lecteurs

Sources : `src/mtee/qml/components/PlayerIsland.qml` (37–43) et `src/mtee/qml/views/FullscreenPlayer.qml` (242–247) ne donnent à `CoverArt` que `pattern`, sans `source`. `PlayerModel.playingTrack` provient déjà du catalogue et dispose de `coverUrl`.

Correctif : relier les deux covers aux données du morceau joué avec le contrat dimension/révision de R01. Ne pas les relier à la sélection de l'inspecteur. Le plein écran demande sa propre résolution ; le provider rejette les retours périmés. Recette : jouer A, sélectionner B, passer en plein écran, jouer C rapidement, modifier/remplacer la cover sur une copie via parcours autorisé et rafraîchir ; aucune cover d'une sélection ou requête précédente ne remplace celle du morceau joué. Cas absent/corrompu neutre. Tester dans `tests/ui/test_player_views.py` avec images identifiables, et garder cette vérification lors de 08.

### R13 — Révéler le fichier dans Windows Explorer

Source : `src/mtee/qml/components/TrackContextMenu.qml` (40–45) raccorde Show in Explorer à `setActivity("explorer")` puis `openFolder(menu.folderId)`. Aucune ouverture Windows n'a lieu.

Correctif : ajouter `src/mtee/services/platform/shell_reveal.py` et une commande Qt qui capture le `trackId` cliqué, résout son chemin actuel et demande au shell Windows d'ouvrir le dossier avec ce fichier sélectionné. Préférer l'API documentée `SHOpenFolderAndSelectItems` avec initialisation COM et libération des ressources correctes, ou un lancement d'Explorer à arguments structurés dont espaces/virgules/Unicode sont vérifiés. Ne pas fabriquer de commande shell QML. Conserver une commande distincte `Reveal in MTEE` seulement si elle est utile, sans lui attribuer le libellé Windows.

Recette : fichier avec espaces, accents, apostrophe et virgule, disque inaccessible, entrée supprimée, fichier déplacé depuis ouverture du menu. Une erreur est visible ; ne pas annoncer une révélation réussie à partir du seul code de retour d'un processus. Créer `tests/unit/test_shell_reveal.py` avec adaptateur simulé, compléter le test menu UI, puis vérifier visuellement l'Explorer Windows et sa sélection. Cette commande ne modifie pas les fichiers.

### R14 — Position de navigation conservée

Sources : `ExplorerPane.qml::onClicked` (119) ouvre le dossier parent dès le premier clic d'un morceau ; `onDoubleClicked` lance ensuite Play. `FolderTreeModel.refresh` fait un `beginResetModel` inconditionnel (vers 95). `WorkspaceModel._refresh_library`/`_refresh_models` les déclenchent notamment pendant les scans. L'arbre n'a pas de contrat de conservation du premier item visible/offset. L'origine exacte du saut peut combiner navigation, recréation et mise à jour asynchrone.

Correctif : instrumenter le premier item visible, son offset, currentIndex/currentItem, les expansions et les resets pendant le double-clic sur le titre 84. Un clic sélectionne et un double-clic lit sans recentrer ni refermer le parent ; ne pas déclencher une navigation qui déplace le viewport. Si l'ouverture d'un onglet parent reste nécessaire au contexte, elle doit préserver la sidebar et sa sélection. Rendre un refresh identique sans effet et utiliser les signaux de changement de données pour les modifications non structurelles. Lors d'un changement structurel, restaurer l'ancre par UUID/identifiant de dossier et décalage visuel, pas par un numéro de ligne devenu faux. Si l'ancre disparaît, conserver le voisin le plus proche selon une règle testée.

Recette : au moins 100 titres, titre 84 visible au milieu du viewport, double-clic puis délai couvrant une mise à jour de jobs : morceau 84 joué, sélection 84, mêmes expansions, même item visible au même décalage à un pixel près. Répéter avec scan incrémental actif, colonnes changées, deux panneaux et passage plein écran/retour. Créer `tests/ui/test_sidebar_scroll.py` et compléter les tests du modèle. Une tolérance d'un pixel est une règle de test proposée, pas une mesure déjà observée.

## Interfaces partagées et migrations

Le découpage domaine/services/modèles Qt/QML reste celui du dépôt. QML ne parcourt pas les disques et ne lance pas de commandes système. Les travaux de métadonnées, images, stats, copie et réconciliation quittent le thread UI ; leurs retours comportent UUID, révision et identifiant de requête. Les signaux modifient les modèles sur le thread Qt. `FileAccessCoordinator` demeure commun aux lectures, mutations et futurs décodeurs ; R01 ne doit pas introduire une lecture concurrente non coordonnée avec un remplacement de source.

Définir et tester les contrats suivants dans leurs modules de A/B avant de multiplier les appelants : demande de cover par UUID/révision/taille ; réconciliation avec intention silencieuse/explicite ; registre de colonnes typées et formatters ; références de presse-papiers capturées ; destination de catalogue validée ; adaptateur de tags avec préservation et capacités par champ. Les noms proposés de nouveaux modules ne prouvent pas leur existence aujourd'hui.

La prochaine migration libre suit actuellement `006_file_operation_phases.sql`. Relire la liste à l'exécution : ne pas attribuer le même numéro aux dates, à copy et au futur plan 07. Sauvegarder SQLite avec son API de backup, tester depuis une copie v6, faire la migration transactionnelle puis tester une seconde ouverture sans duplication. Les anciennes dates inconnues restent NULL pendant le remplissage. Toute nouvelle clé de workspace doit aussi être autorisée dans `_validated`, sinon elle sera éliminée à l'enregistrement.

Ne pas remettre à zéro la collection pour faire passer les tests. Les UUID existants, sélections, emplacements, historiques et données de récupération restent utilisables. Les caches de cover et de waveform sont jetables ; les écritures, overrides et playlists ne le sont pas.

## Étapes concrètes et preuves à produire

Depuis la racine, commencer par :

    git status --short
    git branch --show-current
    git log -5 --oneline
    uv sync --locked

Au moment de la préparation, `.gitignore`, `AGENTS.md` et `.codex/` contenaient du travail étranger à ce plan. Réinspecter et préserver ces changements ; ne pas les indexer par commodité. Vérifier les instructions locales et utiliser le graphe pour cibler le code, puis lire les implémentations et les tests.

Créer `docs/validation/06b-correctifs-recette.md` en A0. Une ligne par R01 à R14 doit contenir état reproduit/implémenté/testé/recetté, commande ou scénario, preuve, limite et sous-jalon. R05 distingue le crash signalé, les événements du paquet et les risques de shutdown. Conserver traces et dumps bruts sous `.local/validation/06b/` ; ne versionner que des extraits anonymisés. Les captures doivent utiliser des fixtures et ne pas révéler de chemins privés.

Les nouveaux scripts et tests nommés ci-dessus sont à créer dans leur sous-jalon avant d'utiliser les commandes correspondantes. Pour A, exécuter les contrôles communs et les suites pertinentes, notamment :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_workspace_model.py tests/unit/test_artwork_service.py tests/unit/test_windows_frame.py
    uv run pytest tests/ui/test_column_selection.py tests/ui/test_player_views.py tests/ui/test_track_hover.py tests/ui/test_sidebar_scroll.py
    uv run pytest tests/integration/test_incremental_refresh.py tests/integration/test_file_moves.py tests/integration/test_file_copies.py
    uv run pytest tests/unit/test_file_dates.py tests/unit/test_shell_reveal.py tests/ui/test_file_actions.py tests/integration/test_database_migrations.py
    uv run pytest tests/integration/test_runtime_shutdown.py

Les tests unitaires/UI offscreen et le natif sont des preuves différentes. Exécuter le harnais natif après sa création, dans des sous-processus bornés. S'il manque une surface de contrôle natif, écrire exactement quels gestes n'ont pas été testés et préparer le parcours manuel ; ne pas appeler un test offscreen « recette interactive ».

Pour B, lancer les tests metadata cités, les tests de capacités ajoutés et ceux du transfert de métadonnées de 07. Pour C, compléter `tests/unit/test_search_criteria.py`, `tests/integration/test_search_persistence.py` et `tests/ui/test_search_playlists.py` créés par 10. Les formats indisponibles doivent échouer explicitement dans la recette de livraison au lieu d'être tous ignorés.

Chaque sous-jalon applicatif comprend aussi :

    uv run python -m mtee --data-dir .local/validation/06b-live
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/06b-package --smoke-test

Puis lancer le paquet sans smoke-test et exercer les parcours réels sur copies. Utiliser des sous-répertoires A/B/C distincts ou sauvegarder les données avant migration. Vérifier un lancement hors checkout, résolution des bibliothèques natives, absence de dépendance fortuite au PATH et les mêmes interactions dans le paquet. Ne pas reconstruire le paquet après chaque changement de libellé ; le contrôler à la livraison cohérente de chaque sous-jalon, et après un changement natif/packaging significatif.

## Recette transversale avant fin de 09 et fin de 10

Partir d'une bibliothèque de fixtures persistée contenant au moins 100 titres, plusieurs dossiers dont un vide, des pochettes de qualités différentes et les formats effectivement activés. Redémarrer : catalogue visible, pas de réindexation ostensible. Activer Album, Bitrate, Date created et Date modified ; ordre et choix persistent. Se placer au titre 84, lire, sélectionner un autre morceau : scroll stable, îlot visible et cover du morceau joué. Maintenir la souris sur Play/Info : pas de scintillement.

Éditer un tag pris en charge et faire Undo ; vérifier cover et contenu audio. Déplacer par menu puis par geste, copier/coller vers un dossier vide, annuler une collision, révéler le fichier final dans Windows. Les références de lecture restent valides selon le protocole de libération des fichiers et l'UUID d'un déplacement ne change pas. Une copie reçoit un UUID distinct.

Avec 07, convertir une copie pendant la lecture puis vérifier le dérivé, ses tags et ses propres dates ; les analyses ne sont pas copiées automatiquement. Avec 08, ouvrir/fermer le plein écran et zoomer sans modifier la sélection de navigation. Avec 09, analyser pendant que réconciliation et navigation restent réactives ; ne pas écraser tags ou confirmations. Avec 10 validé, rechercher une plage de dates puis déplacer un morceau : filtres, playlist et provenance restent cohérents, sans reconstruire silencieusement la file de lecture.

Enfin fermer pendant un chargement d'image et un job contrôlé, puis rouvrir : aucune écriture incomplète présentée comme réussie, aucun crash natif dans les scénarios vérifiés, récupération traçable si interrompue. Consigner séparément ce qui demeure non reproduit ou dépend d'une recette utilisateur.

## Reprise, livraison Git et consigne de lancement

À chaque pause, mettre à jour Progress, découvertes, décisions et résultats ; laisser une prochaine action exécutable et le scénario restant en échec. Ne pas cocher une correction sur la seule modification du code. Committer par sous-jalon cohérent, avec problème, solution et validations réellement observées. Mettre à jour le plan 07/08/09/10 concerné en même temps que ce complément.

Avant publication :

    git status --short
    git diff --check
    git fetch origin
    git log --oneline --left-right HEAD...origin/main

Indexer uniquement les chemins examinés avec `git add -- <chemins explicites>`, jamais `git add .`. Examiner `git diff --cached --check` et `git diff --cached`, écrire le message dans une here-string PowerShell non interpolée et un fichier temporaire puis `git commit --file <fichier>`. Publier selon `PLANS.md` sans force, intégrer toute avance distante après examen, puis confirmer par fetch et comparaison de HEAD/origin/main. Les preuves de push se rapportent après l'opération, sans hash auto-référentiel.

Consigne prête à donner à Luna :

    Lis AGENTS.md, PLANS.md et intégralement « Plans d'exécution/06b-correctifs-recette.md ».
    Exécute A0 à A3, puis le début de 07 jusqu'au runtime FFmpeg et aux fixtures,
    puis B, puis termine 07, 08 et 09 dans cet ordre. Maintiens les ExecPlans,
    teste sur des copies, contrôle le paquet Windows, committe par sous-jalon
    cohérent et pousse sans force. Ne modifie pas les changements étrangers.
    Prépare ensuite la revue 10 à partir des analyses réelles. Si son accord
    explicite est déjà consigné, exécute C et le reste de 10 ; sinon termine
    le dossier examinable et laisse ce point de reprise. N'exécute pas 11+.
    Distingue correctif prouvé, hypothèse de crash et recette non réalisée.

## Références techniques vérifiées pendant la préparation

Les comportements observés dans ce document proviennent d'abord des sources locales et de l'expérience décrite. Les documentations suivantes servent aux contrats à vérifier contre les versions verrouillées : [types séquence QML](https://doc.qt.io/qt-6/qtqml-typesystem-sequencetypes.html), [MouseArea](https://doc.qt.io/qt-6/qml-qtquick-mousearea.html), [timestamps Python 3.12](https://docs.python.org/3.12/library/os.html#os.stat_result.st_birthtime_ns) et [SHOpenFolderAndSelectItems](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems). La documentation ne constitue pas une preuve que le comportement applicatif a été validé.

Note de révision — 2026-09-25, Codex : préparation du complément, inventaire des 14 retours, causes confirmées distinguées des hypothèses, ordre de raccord 07–10 et reprise nocturne explicités. Développement et recette des correctifs à effectuer.
