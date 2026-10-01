# MTEE — consignes du dépôt

La référence produit est `PLAN.md`. L'interface est en anglais, la documentation du projet en français. MTEE est une application desktop Python 3.12 / PySide6 / QML, sans Electron ni WebView, Windows en premier et autonome localement.

Pour chaque fonctionnalité importante ou refonte, lire `PLANS.md`, puis l'ExecPlan correspondant dans `Plans d'exécution/`. Un ExecPlan est le document opérationnel de l'étape, à maintenir pendant sa réalisation. L'index `Plans d'exécution/README.md` indique l'ordre et les prérequis. Une demande de préparation des plans n'est pas une demande d'implémentation de toute l'application.

Préserver l'ordre des livraisons et les validations utilisateur explicitement prévues dans `PLAN.md` : maquettes avant code fonctionnel, vocabulaire des tags après les premiers résultats d'analyse. Préparer les éléments examinables avant ces revues. Pour les choix techniques ordinaires, avancer et documenter la décision.

Séparer sources audio, métadonnées écrites, analyses calculées, corrections manuelles et fichiers dérivés. QML passe par des modèles Qt et services Python ; aucun accès direct au système de fichiers ni aux commandes système. Les accès longs quittent le thread graphique. Aucun FFmpeg/ffprobe dans les livraisons A/B.

Tester les opérations d'écriture sur des copies. Préserver les tags inconnus et les pochettes, éviter les écrasements, ne jamais substituer une suppression définitive à une corbeille indisponible. Ne versionner ni collections personnelles, ni bases locales, ni identifiants, ni binaires téléchargés.

À chaque étape implémentée : tests adaptés, vérification manuelle du comportement depuis les sources, mise à jour de l'ExecPlan, commit détaillé, puis push vers `origin`. Ne pas lancer `scripts/build_windows.ps1` ni `scripts/smoke_packaged.ps1` automatiquement en fin de tâche, de jalon ou avant un commit/push. Construire et vérifier l'EXE uniquement si la demande porte explicitement sur le packaging ou une distribution Windows ; un changement de code, de dépendance ou de ressource ne suffit pas à déclencher ce build. Noter les contrôles réellement effectués, sans présenter le paquet comme validé s'il ne l'a pas été. La branche initiale est `main` et l'URL est `https://github.com/foliarn/mtee.git`. Inspecter l'état existant avant de modifier Git ; ne pas forcer un push ni écraser le travail d'autrui. Les sous-jalons peuvent recevoir des commits intermédiaires.

Les commandes applicatives décrites dans les plans sont à créer durant les étapes indiquées ; elles ne prouvent pas l'existence actuelle d'une application. Consigner les résultats réellement observés, et distinguer validation du plan, développement, recette et push.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**This project has a knowledge graph. Start with the code-review-graph
MCP tools to narrow scope, then read the source.** The graph is cheaper than scanning files and
gives you structural context (callers, dependents, test coverage) that file search cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

### Verify in the source

- Narrow scope with the graph, then read the source. Do not change code from graph output alone.
- For any non-trivial change, read the implementation and the relevant tests before concluding.
- Verify the exact source when touching behavior, database logic, migrations, retries, fallbacks,
  recovery, or compatibility code.
- When the graph and the source disagree, the source wins. The graph may be stale or may not
  model that relationship.
- An empty graph result can mean "not indexed" or "not statically visible", not "does not exist".

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. If the graph may be stale, run `code-review-graph update` before querying it.
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
<!-- /code-review-graph MCP tools -->
