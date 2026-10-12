# Rapport de réalisation — site et documentation Apizr

## Organisation et périmètre

Le site anglais comprend désormais six entrées principales : **Start here,
Examples, User guide, Developer guide, Operations guide, Reference**. L'accueil
reste accessible par le logo. Les guides suivent respectivement le travail
Python/notebook, l'intégration dans une application et l'exploitation d'un service.
Les commandes détaillées, contrats, architecture, releases, legacy et contribution
sont accessibles sous Reference. L'installation et les notions communes gardent
une source canonique.

Avant : accueil, parcours de démarrage et documentation technique regroupant
usage, intégration, anciens composants et contribution. Après : choix d'un résultat,
six scénarios téléchargeables et progression distincte par public, avec les
références détaillées toujours disponibles. Le devis et la tournée démontrent
le chemin direct sans Run ; les scénarios scientifiques démontrent le chemin
optionnel Inspect → Run → Compare → Expose.

La branche documentaire `docs/site-reader-journeys` part de `master` au commit
`1eaffadd2fda3ec3ca9d512948090848bbfc88a5`. La mission autorise explicitement
cette exception à AGENTS.md, qui mentionne encore la branche de développement
`0.4.5`. La gouvernance générale est conservée. Aucun code produit, contrat,
numéro de paquet, tag ou archive de release n'a été modifié.

## Audit, contenu ajouté et contenu conservé

[La matrice JSON](page-migration.json) et [sa version CSV](page-migration.csv)
couvrent les **104 pages publiques initiales et 759 ancres de contenu** : source,
URL, public, besoin, statut, décision, destination et validation. Chaque ancienne
URL est conservée. Les pages de compatibilité déjà présentes gardent leurs ancres,
leur lien canonique et leur exclusion de la recherche. [La couverture fonctionnelle](feature-coverage.md)
relie les affirmations aux sources, contrats et qualifications.

**26 nouvelles pages** apportent les parcours : Start here ; quatre chapitres User
guide ; six Developer guide ; sept Operations guide ; galerie et six scénarios ;
concepts communs. Les chapitres comprennent objectifs, prérequis, actions,
vérification, limites et suite du parcours.

**14 pages existantes ont été révisées** : accueil, guide data science, inspection,
Runs, exposition d'expérience, exposition de dépôt, CI, collections clientes,
index Reference, invocation d'extension, livraison multi-destination, vue
d'architecture, principes d'artefacts et contrat d'evidence expérimentale.
Les principales réécritures portent sur l'accueil et le parcours data science ;
les autres corrections sont ciblées et identifiées dans la matrice.
**90 pages restent textuellement conservées**, après évaluation et repositionnement.
Les preuves et contrats historiques ne sont pas réécrits rétrospectivement.
Le README et celui de l'exemple fraude sont actualisés.

MkDocs Material, palette, modes clair/sombre, logo et **image hero originale**
sont conservés. Toutes les vidéos restent présentes et activées volontairement ;
la transcription complète de l'accueil et le JavaScript vidéo sont conservés.
Les cartes de parcours, le focus clavier et le dégagement des titres sous le
grand logo améliorent la navigation sans framework supplémentaire.

Le widget Git **natif de Material**, rétabli dans le composant `source`, affiche
le dépôt et les données GitHub après consentement. Le navigateur a effectivement
affiché **v0.4.5, 4 étoiles et 0 fork**. C'est la présentation demandée sur la
capture ; aucune étiquette documentaire personnalisée n'est utilisée. Analytics
et GitHub restent désactivés par défaut. Ce widget affiche les informations
GitHub prises en charge par Material ; aucun sélecteur de branches artificiel
ou déploiement de documentation multiversion n'est ajouté.

## Scénarios exécutés

Qualification sur **macOS 27.0.1 arm64**. Les exemples utilisent les paquets
publics Apizr **0.4.5** installés dans des environnements hors checkout, avec
CPython **3.11.14**. Les outils du dépôt utilisent CPython **3.12.13**. La fixture
Docker utilise Ubuntu 24.04/Python 3.12 pour le core et des images de service
Linux amd64/Python 3.14 ; Docker Engine 29.1.5 et Continuum Attest 0.1.0 réel.

| Scénario | Résultat observé | Preuve retenue |
| --- | --- | --- |
| A — Comparer deux expériences fraude | Deux Runs réussis ; mêmes code/paramètres/seed ; données, modèles et métriques différents ; aucune conclusion causale | [science/public-proof.json](evidence/science/public-proof.json), [diff](evidence/science/diff.json) |
| B — Partager une prédiction | Même `{"predictions":[[1,0.8127568160788873]]}` REST/MCP ; trois formes invalides refusées par chaque transport ; modèle périmé refusé | [science/transport.json](evidence/science/transport.json), contrôles indépendants et galerie dans `public-proof.json` |
| C — Partager un devis | **9 180 cents**, inventaire public limité à `api.quote`, entrée invalide et rupture de stock vérifiées ; deux bundles de l'API Python réellement appelés | [examples/results.json](evidence/examples/results.json), journaux HTTP/MCP du compilateur |
| D — Donner un outil de calcul | SDK MCP réel : warehouse → library → cafe → museum → warehouse, **12 minutes** ; destination inconnue traitée | `route-call.txt`, archive et commandes identifiées dans `examples/results.json` |
| E — Recherche inachevée | REST/MCP utilisables malgré l'expérience indépendante inachevée ; défaut réel du helper nécessaire refusé ; correction légitime rétablit le plan | `research-refusal.txt` et `examples/results.json` |
| F — Remise vérifiable | Construction, push TLS authentifié, pull par digest depuis un daemon indépendant, puis mêmes devis REST/MCP sans source/bundle monté ; core inchangé | [application-delivery-proof.json](evidence/delivery/application-delivery-proof.json), [outcome](evidence/delivery/outcome.json) |
| F optionnel — Attest | Signature, timestamp RFC 3161 et vérification transportée hors ligne réussis ; **23 cas de refus**, dont preuves altérées | [attest-results.json](evidence/delivery/attest-results.json), [attest-refusals.json](evidence/delivery/attest-refusals.json) |

Les archives du site sont extraites hors checkout. Les commandes marquées des
pages sont consommées directement par `smoke_site_examples.py` et
[qualify_science_examples.py](qualify_science_examples.py), qui réutilise le
qualificateur scientifique existant. Les empreintes des commandes et archives
sont conservées dans les résultats. Les bibliothèques scientifiques effectivement
testées sont pandas 3.0.6, NumPy 2.4.6, SciPy 1.17.1, scikit-learn 1.9.1 et
joblib 1.6.0. Elles ne sont pas imposées à l'inspection initiale : un environnement
0.4.5 `[notebook]` sans pandas/NumPy/scikit-learn a inspecté l'archive sans créer
d'artefact ([preuve](evidence/inspection/result.json)).

Le probe d'extension a été installé dans son environnement séparé ; l'API publique
a renvoyé `demo extension reached` puis refusé l'opération `unknown` avec
`plugin_failed`. Les versions actuelles et historiques des quickstarts ont été
testées par `smoke_readme.py` ; les blocs expérimentaux par `smoke_experiment_docs.py`.
Une copie au repos de l’historique a conservé les octets JSON et relu ses quatre
Runs avec la commande documentée ([preuve](evidence/history-backup.json)).

## Contrôles techniques et visuels

Commandes de build et contrôles :

```sh
uv sync --locked --group docs
uv run --locked --group docs mkdocs build --strict
uv run --locked python scripts/check_docs_html.py
python3 scripts/check_package_architecture.py
uv run --locked pytest tests/test_site_refonte.py tests/test_docs_publication.py tests/ci/test_release_consistency.py tests/test_ci_scope.py tests/test_coordinated_distributions.py
```

Le lot ci-dessus réussit : **121 tests**. Un autre lot incluant publication,
cohérence de version, compilateur, portée sélectionnée, runtime expérimental et
extension réussit avec **81 tests** ; ces lots se recouvrent et ne doivent pas
être additionnés. Les contrôles de format et de composition sont appliqués aux
changements. Le contrôle HTML couvre **131 pages HTML**, liens internes, URLs
canoniques, médias, six chemins d'accueil et toutes les anciennes ancres.

Le manifeste de build empreinte désormais toutes les pages HTML et les archives
exécutables. Les contrôles source/build/publication existants restent actifs.
Le workflow ajoute les exemples installés et les tests de préservation ; son
job protégé de publication conserve ses permissions et conditions.

La première exécution de la CI a détecté un lien relatif ajouté au README et
le format d’un bloc Python documentaire. Le lien est devenu absolu et le bloc
respecte le formateur. Pyright a également conduit à vérifier explicitement la
présence d’un bloc de commandes avant de le lire. Ruff sur tout le dépôt et
Pyright passent. La construction coordonnée des quatre wheels et quatre sdists,
leurs métadonnées et leur reconstruction autonome passent aussi, sans modifier
les exigences de ces contrôles ni publier les archives.
Le job `quality` installe aussi le groupe `docs` existant pour vérifier les
imports MkDocs du nouveau hook ; aucune erreur de typage n'est exclue.

Vérification native Chrome du site local : accueil et guides, recherche
`business quote` avec résultats pertinents, modes clair/sombre, focus clavier
visible sur le bouton de copie, navigation du sommaire, tiroir mobile et chapitre
compilateur. À **400 × 497 pixels CSS**, les textes, tableaux Operations et blocs
de code restent utilisables ; les grandes lignes de code gardent le défilement
horizontal Material. Le décalage des ancres a été ajusté pour le logo existant.
Les observations visuelles sont consignées ; aucune capture fabriquée n'est livrée.

## Limites et livraison

Les chemins centraux A–F sont exécutés. Une connexion à un assistant IA particulier,
la nouvelle variante facultative d'analyse MCP et l'exécution sur Windows ne sont
pas revendiquées comme nouvellement qualifiées. Les limites fiscales, de stock,
d'heuristique logistique, de Run local, d'evidence et de confiance Attest restent
explicites sur les pages concernées. Aucun déploiement distant n'a eu lieu.

Les ressources nommées `apizr-registry-*` sont nettoyées par la fixture ; les
serveurs REST créés pour les qualifications sont arrêtés. Les résultats retenus
excluent modèles, données métier, magasins d'authentification et clés privées.
Des essais intermédiaires ont révélé des dépendances de fixture manquantes,
des écritures de bytecode et une incompatibilité de wheels client/service ; les
corrections restent dans les drivers de qualification et conservent les refus et
assertions d'isolation. Les tentatives échouées ne sont pas comptées comme succès.

La livraison passe par un commit DCO et une PR vers `master`, sans fusion ni
publication du site. La publication publique sera celle du workflow protégé
après revue ; aucune réussite de déploiement GitHub Pages n'est anticipée.
