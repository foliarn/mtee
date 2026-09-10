# MTEE — consignes du dépôt

La référence produit est `PLAN.md`. L'interface est en anglais, la documentation du projet en français. MTEE est une application desktop Python 3.12 / PySide6 / QML, sans Electron ni WebView, Windows en premier et autonome localement.

Pour chaque fonctionnalité importante ou refonte, lire `PLANS.md`, puis l'ExecPlan correspondant dans `Plans d'exécution/`. Un ExecPlan est le document opérationnel de l'étape, à maintenir pendant sa réalisation. L'index `Plans d'exécution/README.md` indique l'ordre et les prérequis. Une demande de préparation des plans n'est pas une demande d'implémentation de toute l'application.

Préserver l'ordre des livraisons et les validations utilisateur explicitement prévues dans `PLAN.md` : maquettes avant code fonctionnel, vocabulaire des tags après les premiers résultats d'analyse. Préparer les éléments examinables avant ces revues. Pour les choix techniques ordinaires, avancer et documenter la décision.

Séparer sources audio, métadonnées écrites, analyses calculées, corrections manuelles et fichiers dérivés. QML passe par des modèles Qt et services Python ; aucun accès direct au système de fichiers ni aux commandes système. Les accès longs quittent le thread graphique. Aucun FFmpeg/ffprobe dans les livraisons A/B.

Tester les opérations d'écriture sur des copies. Préserver les tags inconnus et les pochettes, éviter les écrasements, ne jamais substituer une suppression définitive à une corbeille indisponible. Ne versionner ni collections personnelles, ni bases locales, ni identifiants, ni binaires téléchargés.

À chaque étape implémentée : tests adaptés, vérification manuelle du comportement, contrôle de la distribution Windows, mise à jour de l'ExecPlan, commit détaillé, puis push vers `origin`. La branche initiale est `main` et l'URL est `https://github.com/foliarn/mtee.git`. Inspecter l'état existant avant de modifier Git ; ne pas forcer un push ni écraser le travail d'autrui. Les sous-jalons peuvent recevoir des commits intermédiaires.

Les commandes applicatives décrites dans les plans sont à créer durant les étapes indiquées ; elles ne prouvent pas l'existence actuelle d'une application. Consigner les résultats réellement observés, et distinguer validation du plan, développement, recette et push.
