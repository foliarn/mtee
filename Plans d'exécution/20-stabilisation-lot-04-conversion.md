# 20 — Conversion fiable

## Résultat et prérequis

Ouvrir Convert sans exécuter ffprobe/FFmpeg depuis un getter, produire un aperçu annulable et publier des dérivés vérifiés sans écrasement. Prérequis : journalisation, résultat worker/slot Qt et primitives existantes étudiés après les lots 17–19.

## Interfaces, workers et processus

Les capacités passent de `not_loaded` à `loading`, puis `ready` ou `failed`; une seule découverte sert les vues et les formats restent vides pendant l’attente. L’aperçu suit `idle/preparing/ready/failed` et capture sources/révisions, destination et réglages immuables. Tout changement invalide sa génération; une réponse périmée ne peut lancer la conversion. Garder les actions distinctes de préparer et démarrer et interdire le double lancement.

Préparer identifiants de conversion, jobs et états de file avant démarrage des workers. Limiter à deux processus simultanés, sans thread réservé par élément en attente. Utiliser un superviseur commun pour probe/décodage/conversion, drainer stdout/stderr indépendamment, borner files et mémoire stderr, vérifier annulation toutes les 50 ms et quitter même si stdout est silencieux. Annulation : terminate, attente d’une seconde maximum, kill si nécessaire, wait, fermeture des pipes. Tous les lancements utilisent `shell=False`, `stdin=DEVNULL`, `CREATE_NO_WINDOW`.

## Publication, métadonnées et reprise

Créer le temporaire adjacent avec identifiant MTEE et exclure seulement ce motif du scanner. Vérifier sortie et empreinte avant publication. Journaliser source/révision, destination, temporaire, réglages, dérivé et empreinte. Renommer sans remplacement sur le même volume; une erreur SQL après publication n’efface pas le fichier. Au démarrage, traiter les tentatives incomplètes en worker et reconnaître un résultat seulement avec preuve concordante. Une collision préexistante n’est jamais supprimée.

Résoudre explicitement profondeur source inconnue/incompatible et dithering pertinent. Désactiver explicitement la copie automatique de tags quand elle l’est dans l’aperçu. Utiliser les adaptateurs compatibles et rapporter les limites de pochette; ne jamais modifier la source.

## Vérification et reprise

Tester sur copies annulation d’un processus silencieux, deux conversions simultanées, aperçu invalidé par réglage, collision et interruption avant/après publication. Vérifier contenu, empreinte et filiation du dérivé. Une reprise consulte le journal; elle ne déduit pas une réussite de la seule présence d’un chemin.

## Progress

- [ ] Convertir les getters vers snapshots et états explicites.
- [ ] Processus, annulation et publication reprenable à vérifier.

## Surprises & Discoveries

À renseigner depuis la chaîne actuelle et les cas d’échec observés.

## Decision Log

- 2026-09-25 — `os.replace()` n’est pas utilisé pour une destination finale; une collision reste un conflit visible.

## Outcomes & Retrospective

À compléter après les exercices sur copies et le contrôle du runtime Windows distribué.
