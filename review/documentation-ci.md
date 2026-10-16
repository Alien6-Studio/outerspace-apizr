# Cycle documentaire indépendant

Une révision du site comprenant `mkdocs.yml`, le README, les outils de build ou
les exemples déclenchait toute la qualification produit. La PR du guide
d’architecture exécutait ainsi près de 7 000 tests, dont un test Attest échouait
sur Python 3.14 avant que le processus enfant ait fini de démarrer.

## Routage

Le classificateur accepte désormais les fichiers documentaires explicitement
déclarés, les pages/médias/overrides existants, les fichiers réguliers sous
`examples/`, les rapports Markdown et les inventaires de la refonte. Le README,
CHANGELOG et `mkdocs.yml` ne nécessitent plus une qualification produit complète.
Les outils du site possèdent une liste précise ; un script inconnu reste produit.

Le diff complet reste comparé à la merge-base pour une PR. Déplacements depuis
le produit, mélanges documentation/code, fichiers exécutables, symlinks et
comparaisons indisponibles ne permettent pas de prendre le chemin rapide.
Les sources, plugins, dépendances racine, contrats JSON publiés, scripts de
distribution, classificateur et workflows conservent la qualification complète.
Les 17 contextes obligatoires et les règles de branche sont conservés.

Le diff initial du guide, `c2601ded…` → `90ca070a…`, est vérifié avec le nouveau
classificateur : **product=false, examples=true**. La présente correction reste
elle-même une modification CI et de test produit ; sa première qualification
GitHub est donc complète.

## Environnement et contrôles

[`tools/docs/`](../tools/docs/README.md) est un projet uv virtuel, avec un lockfile,
une venv et une configuration pytest séparés. Il possède 43 entrées verrouillées,
dont le projet virtuel ; les 42 dépendances reprennent les versions, sources et
hashes d’archives déjà revus dans le lock racine. Un test bloque tout ajout ou
changement qui contournerait la revue de dépendances existante.

L’option [`uv --project`](https://docs.astral.sh/uv/reference/cli/) sélectionne cet
environnement tout en gardant les chemins de commande relatifs à la racine du
dépôt. Aucun Apizr, plugin OCI, Attest ou MCP n’y est installé ; un contrôle de
la présence des modules vérifie cette séparation dans le workflow.

Le chemin documentaire conserve DCO, les sept hooks génériques d’intégrité,
Ruff sur les outils concernés, les tests de routage/publication/conservation,
les contrôles de version publique, MkDocs strict et la validation HTML.
Les hooks produit, Pyright global, builds coordonnés, Docker et Attest restent
sur le chemin produit. Les conditions de publication du site et la vérification
du contenu HTTPS exact restent actives, avec le même artefact construit une fois.

Les exemples utilisent les roues publiques dans des environnements temporaires
hors checkout. Les extras HTTP/MCP et le pilote TypedDict s’exécutent dans leur
environnement d’exemple, sans ajouter leurs dépendances à la venv documentaire.
Le nouveau paramètre `smoke_readme.py --example-python` conserve le comportement
des autres qualifications lorsqu’il n’est pas fourni. Seul le chemin produit
construit et teste aussi une roue candidate. Les qualifications de livraison
avec Docker/Attest restent distinctes du cycle documentaire.

## Stabilité du test signalé

Le test Attest conservait un budget de 300 ms pour quatre diagnostics différents.
Les cas de dépassement de sortie et de code de sortie non nul ont maintenant
cinq secondes pour démarrer et terminer. Le cas timeout conserve ses 300 ms et
les quatre diagnostics exacts restent exigés. Aucun timeout ni comportement
de production n’est modifié.

## Validation locale

macOS arm64, Python 3.12.13 pour les outils ; Python 3.11.14 pour la roue publique :

- **145 tests documentaires réussis** dans la venv indépendante, en 120 s.
- Présence de `apizr`, `apizr_oci`, `apizr_attest`, `apizr_mcp` : absente dans cette venv.
- MkDocs strict réussi ; **137 HTML** validés, liens/ancres/canoniques/médias compris.
- README courant 0.4.5, migration, sélection et TypedDict REST/MCP : réussis hors
  checkout ; le Quickstart historique 0.3 exécuté par ce pilote réussit aussi.
- Trois scénarios installés du site, quote/route/research : réussis contre 0.4.5.
- Les quatre cas du test Attest et le test processus absent/échéance expirée :
  **5 réussis** ; les délais de production restent inchangés.
- Ruff global, formatage, Pyright global puis contrôle des deux scripts modifiés :
  réussis ; Pyright indique zéro erreur et zéro avertissement.
- Gate de composition des packages et tous les hooks pre-commit : réussis.
- Les sept hooks génériques sont aussi exécutés depuis la venv documentaire,
  indépendamment des hooks produit : réussis.

Les inventaires JSON/CSV ne changent que les empreintes des deux pages de
contribution révisées. Les fichiers/URLs historiques, vidéos, image hero,
styles et widget Git natif restent conservés par les contrôles existants.
Aucune version, publication PyPI, release ou tag n’est créé.

## Correction de la fixture DCO

Les six matrices Linux/macOS du commit `582c7a20…` échouaient sur les mêmes
quatre cas DCO : leur fixture interceptait encore `uv`, alors que le workflow
appelait désormais directement `python3`. Le checkout temporaire ne contenait
donc pas `scripts/check_dco.py`. La fixture copie maintenant le vrai validateur
et exécute le shell du workflow sans simuler son lanceur. Les refus de sign-offs
absents et de branches sans ancêtre audité restent exigés.

Les **18 tests DCO réussissent en 1 s** dans la venv documentaire, sans Apizr.
Ils sont ajoutés au début du workflow Documentation pour détecter cette
régression avant les contrôles plus longs. Le lot documentaire complet atteint
**163 tests réussis en 118 s** ; les commandes locales et inventaires sont adaptés.

Le job Python 3.12 présentait aussi un échec distinct du test d’interruption du
téléchargement de plugin : code 2 au lieu de 130. Ce test réussit isolément
en 1,6 s ; aucun diagnostic accepté ni délai produit n’est élargi pour le masquer.
