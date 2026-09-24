# Étape 08 — Waveform et Fullscreen player complet

ExecPlan vivant rédigé le 2026-09-10, à exécuter selon `PLANS.md` à la racine. Il réalise `PLAN.md` §4.6 et Fullscreen player du §3 après la conversion. Les chemins désignent les fichiers attendus de l'implémentation ; les tests et le push restent à effectuer.

## Objectif et résultat observable


Dans **Fullscreen player**, l'utilisateur voit une waveform du morceau joué, déplace sa tête de lecture, zoome et définit une boucle A/B. Ouvrir cette vue ou revenir à l'explorateur conserve le morceau, la position, la file et la disposition des onglets. Le calcul d'une waveform longue laisse l'interface et la lecture disponibles.

La représentation est un aperçu amplitude/temps, avec enveloppes minimales et maximales ; elle ne prétend pas être un spectrogramme ou un résultat d'analyse musicale. Pendant son calcul, la barre de progression classique reste utilisable. La waveform n'écrit jamais dans le fichier source.

## Progress


État au 2026-09-10 : plan préparé, aucun jalon de développement exécuté.

- [ ] Vérifier le service de lecture et le décodage commun de l'étape 07.
- [ ] Créer le calcul borné, les niveaux de détail et le cache versionné.
- [ ] Relier les coordonnées temporelles et la tête de lecture à PlayerService.
- [ ] Ajouter zoom, navigation, sélection et boucle A/B accessibles au clavier.
- [ ] Vérifier invalidation, annulation, fichiers longs et restauration de la vue.
- [ ] Tester le paquet Windows et consigner les preuves.
- [ ] Créer le commit détaillé et vérifier sa présence sur origin/main.

## Surprises & Discoveries


Aucune observation mesurée au stade du plan. Inscrire ici les codecs dont la timeline décodée diffère de la durée déclarée, les écarts de position mpv et les limites de rendu Qt rencontrées, avec fixture, versions et mesure.

## Decision Log


2026-09-10 — Codex — Le même `PlayerService` pilote l'îlot de lecture et **Fullscreen player**. La waveform commande sa position et lit son état ; elle ne crée pas un second lecteur.

2026-09-10 — Codex — Les repères du domaine sont des microsecondes entières sur la timeline décodée. Le rendu convertit ces valeurs en coordonnées et le service mpv adapte en secondes, ce qui évite de propager des pixels ou des arrondis de vue dans les données.

2026-09-10 — Codex — Le cache utilise une réduction min/max multirésolution, produite par blocs. Les niveaux adaptés au zoom sont chargés à la demande ; on ne conserve pas tous les échantillons PCM en mémoire.

## Outcomes & Retrospective


Non exécuté. Décrire après validation la fluidité constatée, les durées de calcul, mémoire utilisée, précision de seek/boucle et codecs limités. Documenter le comportement de repli lorsque la waveform n'est pas disponible.

## Contexte et prérequis


L'étape 04 apporte lecture/position/file communes ; l'étape 07 apporte FFmpeg/ffprobe versionnés et `MediaDecodeService`. Les étapes 02/03 ont validé les maquettes, les deux groupes d'onglets, la distinction sélection/lecture et la restauration de navigation. Vérifier ces acquis avant de remplacer la barre seule par une waveform.

`track_id` est un UUID stable indépendant du chemin. `SourceRevision(size_bytes, mtime_ns, file_id, generation)` est immuable ; `file_id` est optionnel et `generation` est persistée. Toute mutation connue incrémente la génération. Une révision différente invalide prudemment le cache, y compris après une écriture de tags ; le token ne démontre pas à lui seul l'identité du contenu.

`JobService` possède annulation, progression et remontée d'erreurs, avec les états `queued`, `running`, `succeeded`, `failed`, `cancelled`. Une interruption au redémarrage devient `failed` avec code `interrupted`. `MediaDecodeService.stream_pcm(source, sample_rate, channels, cancellation)` produit des blocs de PCM accompagnés de leur format et timeline ; ses lectures passent par `FileAccessCoordinator`. Adapter si nécessaire ce contrat dans le service existant plutôt que créer un nouveau décodeur dans QML.

Métadonnées du fichier, analyses et overrides manuels restent séparés. Le cache graphique est jetable et ne devient ni un tag ni une analyse confirmée. Les références UI utilisent `track_id` et un identifiant de requête pour empêcher qu'un résultat tardif du morceau précédent remplace la waveform courante.

Préparer des copies courtes et longues, mono/stéréo/multicanal, silence, impulsions à positions connues, MP3 VBR, FLAC, AAC/ALAC en M4A et un fichier corrompu. Générer localement une fixture de deux heures pour le test de mémoire ; elle reste hors Git.

## Plan de travail et jalons


Le premier jalon réutilise `domain/time.py` créé par le socle, enrichit ses conversions si nécessaire et crée `domain/waveform.py`. Le `TimeRange(start_us, end_us)` existant est une plage non vide à fin exclusive, bornée par la durée réellement disponible. `WaveformLevel` décrit taille de bloc, fréquence temporelle et couples min/max par canal. Documenter le traitement des canaux et utiliser la même convention dans les tests et la vue.

Le deuxième jalon ajoute `services/waveform_service.py` et `persistence/waveform_cache.py`. Réduire les blocs décodés en conservant les crêtes, puis agréger plusieurs niveaux. Indexer le cache par UUID, révision, version d'algorithme et paramètres de décodage. Écrire vers un fichier temporaire connu, vérifier sa structure et publier le cache atomiquement. Une annulation ne publie pas un cache incomplet.

Le troisième jalon ajoute `models/waveform_model.py` et un rendu QML/Qt adapté aux points visibles. Une classe de rendu dédiée peut être ajoutée à ce fichier si la primitive QML choisie impose des transferts trop volumineux. Fixer le choix avec une mesure, sans ajouter une dépendance graphique avant de l'avoir justifiée. Le playhead est une superposition légère qui ne recalcule pas l'enveloppe.

Le quatrième jalon enrichit `qml/views/FullscreenPlayer.qml` et `qml/components/WaveformView.qml`. Garder pochette et métadonnées en haut, waveform sur la largeur utile, et masquer l'îlot de lecture. Le zoom conserve un ancrage prévisible au curseur ou à la position de lecture. Montrer **Generating waveform**, **Waveform unavailable** et une relance explicite.

Le cinquième jalon ajoute boucle A/B et validation de la précision. Les bornes appartiennent à la session de lecture, sont visibles, peuvent être déplacées au clavier et deviennent inactives en changeant de morceau. Utiliser le mécanisme de boucle de mpv, adapté derrière le service ; ne pas boucler à l'aide d'un timer QML qui relance le seek.

## Étapes concrètes


Depuis la racine, partir d'un environnement verrouillé et inspecter les changements existants :

    git status --short
    uv sync --locked

Vérifier les types temporels du socle et compléter leurs conversions si nécessaire, notamment fin exclusive, bornes hors durée, conversion secondes/microsecondes et arrondi vers échantillons. Exposer les divisions temporelles comme nombres, jamais comme chaînes déjà formatées utilisées pour les calculs. Ne pas créer une seconde classe `TimeRange` dans le module waveform.

Dans `WaveformService`, demander les blocs au décodeur commun via `JobService`. Vérifier `SourceRevision` au démarrage et avant publication, partager les requêtes identiques et libérer les travaux inutiles quand l'utilisateur change de morceau. Fixer un budget de décodage qui laisse la lecture prioritaire et respecte les limites communes de jobs.

Implémenter les enveloppes min/max et une pyramide. Tester que des impulsions d'un échantillon ne disparaissent pas dans les niveaux réduits et que les canaux silencieux ne créent pas de fausses crêtes. Définir dans le schéma du cache version, nombre de canaux, taux d'échantillonnage, durée et disposition binaire.

Mettre le cache dans le répertoire applicatif dérivé de `--data-dir`, avec quota et éviction des entrées inutilisées. Une corruption ou une version ancienne entraîne un recalcul, jamais une erreur bloquant le lecteur. La suppression d'un cache ne supprime aucun fichier audio.

Exposer position, fenêtre visible, état de chargement et plage A/B à QML par `WaveformModel`. Interdire les retours de résultats périmés avec UUID, révision et numéro de requête. Réutiliser les commandes seek de `PlayerService` et ses notifications de position.

Ajouter commandes clavier documentées pour zoom, déplacement et bornes A/B. Préserver Espace dans les champs de texte ; le focus waveform permet lecture/pause selon le contrat existant. Vérifier le hit testing à différents facteurs DPI et la lisibilité des marqueurs indépendamment de leur couleur.

Créer `tests/unit/test_waveform_reduction.py`, `tests/unit/test_waveform_timing.py`, `tests/integration/test_waveform_cache.py` et `tests/ui/test_fullscreen_waveform.py`. Les premiers utilisent de petits tableaux synthétiques ; l'intégration décode de vrais fixtures et la vue utilise un lecteur simulé, complété par un parcours manuel avec mpv.

Exécuter les contrôles après implémentation :

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest tests/unit/test_waveform_reduction.py tests/unit/test_waveform_timing.py tests/integration/test_waveform_cache.py tests/ui/test_fullscreen_waveform.py
    uv run python -m mtee --data-dir .local/validation/08
    pwsh -File scripts/build_windows.ps1
    & .\dist\MTEE\MTEE.exe --data-dir .local/validation/08-packaged --smoke-test

Ouvrir ensuite le paquet sans `--smoke-test` pour un parcours complet avec fichier long, zoom et boucle. Vérifier que FFmpeg est trouvé depuis un dossier extérieur au dépôt et que le cache reste dans le `--data-dir` prévu.

## Validation et acceptation


Une impulsion synthétique à 1 s, 5 s et 30 s apparaît dans le bloc temporel correspondant à chaque niveau. À l'échelle affichée, l'écart visuel maximal est un bloc de réduction plus un pixel ; enregistrer l'échelle et les valeurs numériques. Le seek cible cette timeline avec une tolérance adaptée au codec et mesurée avant validation.

Sur PCM, le moteur de boucle respecte les bornes demandées avec une tolérance visée de 20 ms ; pour les formats avec délai ou seek moins précis, consigner la valeur constatée et afficher les limites utiles. Ne pas promettre une édition précise à l'échantillon à partir de cette seule boucle de lecture.

Lancer un calcul sur deux heures d'audio. Instrumenter un signal de réactivité UI : viser le 95e percentile sous 100 ms sur la machine de référence. Observer la mémoire maximale et vérifier qu'elle ne croît pas comme le PCM complet ; documenter matériel, durée, fréquence, canaux et budget réellement retenu.

Passer rapidement entre trois morceaux, puis revenir au premier. Aucun résultat tardif ne remplace le morceau courant ; la lecture et sa file restent identiques. À cache disponible, la vue affiche les données sans redécoder le morceau et l'ouverture doit viser moins d'une seconde sur la machine de référence.

Modifier une copie source pendant le calcul puis après mise en cache. Le premier résultat est rejeté ; le second est invalidé. Déplacer la source dans MTEE conserve son UUID et recalcule seulement si sa révision le nécessite. Une entrée de cache tronquée, supprimée ou ancienne déclenche un recalcul contrôlé.

Contrôler retour à l'explorateur, inspecteur suivant la sélection, Fullscreen player suivant la lecture, disposition à deux panneaux et largeur réduite. Tester annulation, disque déconnecté et fichier corrompu : la barre de progression classique reste disponible lorsque la waveform ne l'est pas.

Consigner les contrôles, captures à 1440 × 900 et DPI réel, temps et limites dans `docs/validation/08-waveform.md`. Vérifier les SHA-256 des sources de test avant/après pour confirmer qu'aucun décodage ni cache ne les a modifiées.

## Reprise et réexécution


Le calcul est déterministe à version et paramètres constants. Une tâche interrompue peut être recommencée depuis la source ; la première livraison n'a pas besoin de reprendre un flux PCM au milieu. Les caches complets valides sont réutilisés, les fichiers temporaires appartiennent à des jobs identifiés.

Le nettoyage ne vise que des chemins de cache connus sous le répertoire de données autorisé. Vérifier le chemin absolu avant toute suppression. Une absence de cache ou un échec de nettoyage ne supprime ni fichier source ni métadonnées.

Si un problème de rendu impose une autre primitive Qt, conserver les contrats de domaine et de cache. Documenter les mesures avant/après dans le journal de décisions et retester la précision temporelle ainsi que les interactions concernées.

## Interfaces et dépendances


`WaveformService.request(track_id, source_revision, config) -> JobId` partage un calcul identique et retourne un résultat immutable. `load_window(cache_key, start_us, end_us, pixel_width) -> WaveformWindow` choisit le niveau de détail et ne renvoie que les données utiles. `invalidate(track_id, revision)` rend les entrées incompatibles indisponibles.

`PlayerService.seek(position_us)`, `set_ab_loop(TimeRange | None)` et les notifications de position sont l'unique autorité de lecture. Si le service existant expose des secondes, ajouter un adaptateur unique et documenter l'arrondi. Les boutons des deux vues commandent ce même service.

`WaveformModel` expose lecture, plage visible, état du job, erreurs et marqueurs. Il applique les signaux sur le thread Qt et ne décode pas d'audio. La sélection `TimeRange` sera réutilisable par l'étape 11, mais aucune exportation n'est ajoutée ici.

Réutiliser Python, Qt et les binaires de l'étape 07. Ajouter NumPy seulement si la réduction vectorisée apporte un bénéfice mesuré ; si ajouté, verrouiller sa version et vérifier son embarquement Windows. Librosa et les modèles ML ne sont pas nécessaires à cette étape.

## Preuves et livraison Git


Renseigner les sections vivantes, les mesures et les limitations avant le commit. Vérifier les changements étrangers ; ajuster la liste aux fichiers réellement créés, et ajouter individuellement les éventuels fichiers partagés modifiés après inspection.

    git status --short
    git diff --check
    git add -- src/mtee/domain/time.py src/mtee/domain/waveform.py src/mtee/services/waveform_service.py src/mtee/persistence/waveform_cache.py src/mtee/models/waveform_model.py src/mtee/qml/views/FullscreenPlayer.qml src/mtee/qml/components/WaveformView.qml tests/unit/test_waveform_reduction.py tests/unit/test_waveform_timing.py tests/integration/test_waveform_cache.py tests/ui/test_fullscreen_waveform.py docs/validation/08-waveform.md "Plans d'exécution/08-waveform.md"
    git diff --cached --check
    git diff --cached

Le message suivant doit être complété avec les observations exactes ; ne pas déclarer une tolérance ou un test non vérifié :

    git fetch origin
    git log --oneline --left-right HEAD...origin/main
    $mteeCommitMessage = @'
    feat(waveform): add cached waveform to the fullscreen player

    Changes: add bounded waveform generation, versioned cache, zoom,
    playhead seeking and A/B looping through the shared player.
    Validation: replace with exact timeline, long-file and Windows package results.
    Limits: replace with measured codec precision and rendering constraints.
    '@
    $mteeCommitFile = Join-Path $env:TEMP 'mtee-08-commit.txt'
    Set-Content -LiteralPath $mteeCommitFile -Value $mteeCommitMessage -Encoding utf8
    git commit --file $mteeCommitFile
    git push origin main
    git fetch origin
    git rev-parse HEAD
    git rev-parse origin/main
    git status --short

Comparer les deux révisions, puis rapporter le commit et le push réellement observés dans la livraison. En cas de rejet distant, conserver le commit, examiner l'avance du dépôt et résoudre sans push forcé. Ne pas ajouter dans ce commit son propre hash ni une preuve de push qui n'existe pas encore.

Note de révision — 2026-09-10, Codex : création et harmonisation avec PLANS.md, identités stables, services communs et preuves futures explicités ; aucun développement ou test prétendu réalisé.
