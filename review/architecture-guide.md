# Extraction du guide d’architecture

Le site possède une entrée principale **Architecture guide**, entre Operations
guide et Reference. Elle contient une introduction et six chapitres : vue
d’ensemble, composants, compilation, expériences et identités, exécution,
extensions et livraison. Cinq chapitres explicatifs et l’index sont nouveaux ;
la vue d’ensemble existante est enrichie. Douze diagrammes illustrent les
responsabilités et les flux, dont une séquence transport → worker.

Les 23 pages existantes de l’ancien groupe Reference / Architecture ont leur
place dans ce guide. Les spécifications sont regroupées en compilation statique,
preuves expérimentales, génération/exécution, intégrité/sécurité. Les fichiers,
URLs, ancres et contrats sont conservés ; aucune redirection n’est nécessaire.
L’organisation interne du code et l’ADR de packaging restent dans Contributing.

L’accueil, Start here, Reference et le README orientent vers le nouvel index.
Les matrices JSON/CSV indiquent les destinations actuelles et les empreintes des
pages révisées, sans modifier l’inventaire historique de 104 pages et 759 ancres.
Le test de navigation est adapté à la septième entrée demandée ; les contrôles
de conservation des médias, consentements et anciens liens restent actifs.

## Sources des explications et diagrammes

| Sujet | Sources relues |
| --- | --- |
| Composants et dépendances | [Inventaire des packages](../architecture/packages.toml), [organisation du code](../docs/architecture/code-organization.md), [compilateur public](../docs/reference/compiler-api.md), [MCP d’analyse](../docs/reference/apizr-mcp-server.md) |
| Découverte, sélection, génération | [scanner](../src/apizr/repository/scanner.py), [planner](../src/apizr/exposure/planner.py), [compilation](../src/apizr/workspace/compiler.py), [bundle](../docs/architecture/repository-bundle-v1.md) |
| Plan, Run et ressources | [pont expérimental](../src/apizr/experiments/exposure.py), [contrat des preuves](../docs/architecture/experiment-evidence-v1.md), [exposition](../docs/getting-started/user-guide/experiment-exposure.md) |
| Transport, import et worker | [runtime de dépôt](../docs/architecture/governed-repository-runtime.md), [transport gouverné](../docs/architecture/governed-transport-runtime-v1.md), [profil strict](../docs/architecture/subprocess-deny.md) |
| Extensions et autorité | [invocation moderne](../docs/reference/extension-invocation.md), [politique opérateur](../docs/reference/operator-policy.md) |
| Images et preuves de livraison | [identités](../docs/architecture/delivery-identities.md), [plugin OCI](../docs/reference/oci-service-plugin.md), [Attest](../docs/reference/attest-delivery-plugin.md) |

Le chemin direct conserve l’absence de Run obligatoire. Les deux usages MCP,
les helpers privés, les limites de l’exécution locale, le conteneur de service
et le worker OCI par appel sont distingués. Les preuves établissent leurs
liaisons documentées, sans promesse de causalité, de build supervisé ou
d’approbation organisationnelle.

## Rendu et vérification

Les diagrammes utilisent l’[intégration native Mermaid de Material](https://squidfunk.github.io/mkdocs-material/reference/diagrams/).
Les clôtures SuperFences emploient leur formateur par défaut, ce qui préserve
la lecture YAML sans constructeur Python. Aucun paquet ni framework frontend
n’est ajouté au dépôt. Le thème charge Mermaid à la demande depuis son CDN
standard ; le rendu des diagrammes dépend de JavaScript et de ce chargement.
Le texte explicatif et les contrats restent disponibles indépendamment du rendu.

Les diagrammes utilisent leur [taille naturelle](https://mermaid.js.org/config/schema-docs/config-defs-base-diagram-config-properties-usemaxwidth.html)
pour conserver des libellés lisibles. Le dépassement horizontal reste dans une
région défilable avec focus clavier visible. Chaque SVG possède un titre et une
description accessibles ; les couleurs et polices suivent Material.

Vérifications locales sur macOS arm64, Python 3.12.13 :

- `mkdocs build --strict` : réussi ; 137 pages HTML.
- `scripts/check_docs_html.py` : liens internes, ancres, canoniques, anciens
  médias et sept entrées d’accueil vérifiés.
- Tests `test_site_refonte`, `test_docs_publication`,
  `ci/test_release_consistency` et `test_ci_scope` : **101 réussis**.
  Le premier lancement sous sandbox ne pouvait pas ouvrir les sockets des
  fixtures HTTPS ; la relance avec ces écoutes locales autorisées réussit.
- Gate d’architecture : composition, façades et dépendances vérifiées.
- Ruff : contrôle global réussi ; 1 068 fichiers déjà formatés.
- Pyright avec l’interpréteur du projet : zéro erreur et zéro avertissement.
  Le lancement sans cet interpréteur ne résolvait pas les dépendances de la venv.
- Tous les hooks pre-commit réussissent, dont YAML, composition et clés privées.
- Après correction de taille des diagrammes, les six tests de conservation sont
  revérifiés et réussissent ; ils sont déjà compris dans le lot de 101.
- Chrome natif : les douze diagrammes sont réellement rendus ; palettes claire
  et sombre observées, desktop et viewport mobile 400 × 497, menu du guide,
  focus visible et défilement horizontal au clavier de la séquence vérifiés.
  La fenêtre temporaire et le serveur local sont arrêtés après vérification.

Les pages du guide sont déclarées dans les surfaces critiques du build. Leurs
HTML et la feuille de style restent liés à la source par les empreintes de
publication existantes. Aucun comportement produit, paquet, tag, archive publiée,
exemple exécutable ou workflow de publication n’est modifié.

La branche `docs/architecture-guide` part de `master` au commit
`c2601ded39246c93c117de384045f6af0adf6486`. La mention `0.4.5` dans AGENTS reste
incohérente avec CONTRIBUTING ; l’exception documentaire de la mission autorise
cette branche depuis master, sans modifier la gouvernance du dépôt.
