# Archilog

> Gestion de cagnottes partagées — calcul automatique des remboursements entre participants.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=flat-square&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00?style=flat-square&logoColor=white)
![Click](https://img.shields.io/badge/Click-8.1+-4CAF50?style=flat-square&logoColor=white)
![HTML](https://img.shields.io/badge/HTML5-Templates-E34F26?style=flat-square&logo=html5&logoColor=white)
![CSS](https://img.shields.io/badge/CSS3-Style-1572B6?style=flat-square&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![SVG](https://img.shields.io/badge/SVG-Sprite-FFB13B?style=flat-square&logo=svg&logoColor=black)
![Jinja2](https://img.shields.io/badge/Jinja2-Templates-B41717?style=flat-square&logoColor=white)

---

**Auteur :** Romain Messager — 2ᵉ année de BUT Informatique, IUT de Vélizy  
**Cours :** Architecture Logicielle — Michel Védrine

> Toutes les commandes de ce README sont écrites pour **Windows PowerShell**.

---

## Table des matières

1. [Fonctionnalités](#fonctionnalités)
2. [Architecture](#architecture)
3. [Prérequis](#prérequis)
4. [Du .tar.gz au projet opérationnel — démarrage rapide](#du-targz-au-projet-opérationnel--démarrage-rapide)
5. [Lancer l'interface web](#lancer-linterface-web)
6. [Utiliser le CLI](#utiliser-le-cli)
7. [Exécuter les tests](#exécuter-les-tests)
8. [Variables d'environnement](#variables-denvironnement)
9. [Structure du projet](#structure-du-projet)
10. [Dépannage](#dépannage)

---

## Fonctionnalités

### Interface web (Flask)
- Créer, consulter et supprimer des cagnottes
- Ajouter, modifier et supprimer des dépenses
- Calcul automatique de l'équilibre : *qui doit combien à qui*
- Import de dépenses depuis un fichier CSV (séparateur `;` ou `,` auto-détecté, encodage UTF-8 / UTF-8 BOM)
- Export des dépenses en CSV
- Mode sombre / clair (bascule persistée dans le navigateur)
- Interface responsive, accessible (WCAG AA)

### Interface en ligne de commande (Click)
- CRUD complet sur les cagnottes et les dépenses
- Calcul de l'équilibre en terminal
- Export CSV depuis le terminal
- Mode interactif : toutes les options peuvent être saisies via prompt

---

## Architecture

Le projet suit une architecture **n-tier** telle que présentée en cours :


| Couche      | Fichier               | Rôle                                                                    |
|-------------|-----------------------|-------------------------------------------------------------------------|
| **views**   | `views.py` + `cli.py` | Interfaces utilisateur (HTTP et terminal)                               |
| **domain**  | `domain.py`           | Logique métier — `CagnotteService`                                      |
| **data**    | `data.py`             | Accès base de données — `CagnotteRepository` (SQLAlchemy Core, pas ORM) |
| **storage** | fichier `.db`         | SQLite via le système de fichiers                                       |

---

## Prérequis

- Python **3.11** ou supérieur
- [`uv`](https://docs.astral.sh/uv/#installation) — gestionnaire de paquets et de projets

Vérifier les versions dans PowerShell :

```powershell
python --version
uv --version
```

Si `uv` n'est pas installé :
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Si `Python` n'est pas installé :
```powershell
winget install Python.Python.3.14
```

---

## Du .tar.gz au projet opérationnel — démarrage rapide

Cette section couvre le chemin complet : de l'archive reçue jusqu'à pouvoir
lancer l'application, le CLI et les tests — sans rien oublier.

---

### Étape 1 — Extraire l'archive

```powershell
# Créer un dossier de travail et s'y placer
mkdir archilog-projet
cd archilog-projet

# Mettre le .tar.gz dans le dossier
mv ../messager_romain.tar.gz # chemin relatif

# Extraire l'archive
tar -xzf messager_romain.tar.gz

# Se placer dans le dossier extrait
cd archilog-0.1
```

> **Important :** toutes les commandes `uv` doivent être lancées depuis le
> dossier contenant `pyproject.toml`. C'est la règle rappelée dans le cours :
> *"toujours se positionner au même niveau que le pyproject.toml"*.

Vérifier qu'on est au bon endroit :

```powershell
ls pyproject.toml   # doit afficher le fichier sans erreur
```

---

### Étape 2 — Installer les dépendances

Avec tests :
```powershell
uv sync --extra dev
```
Sans tests :
```powershell
uv sync
```

`uv sync` lit `pyproject.toml`, crée automatiquement `.venv\`, et installe :
- les dépendances de production : Click, Flask, SQLAlchemy, Playwright
- `--extra dev` : ajoute `pytest` pour pouvoir lancer les tests

> Pas besoin d'activer le `.venv` manuellement :
> `uv run` s'en charge automatiquement à chaque commande.

---

### Étape 3 — Vérifier le CLI

```powershell
uv run archilog --help
```

Si la liste des commandes s'affiche, l'installation est correcte.

```powershell
uv run archilog db-path # Vérifier aussi l'emplacement de la base de données
```

---

### Étape 4 — Lancer l'interface web

```powershell
uv run flask --app archilog.views --debug run
```
En cas d'erreur du style :
```powershell
error: Failed to spawn: `flask`
  Caused by: Une stratégie de contrôle d’application a bloqué ce fichier. (os error 4551)
```
Faire :
```powershell
uv run python -m flask --app archilog.views --debug run
```

Ouvrir [http://127.0.0.1:5000](http://127.0.0.1:5000) dans le navigateur.

```powershell
CTR+C  # pour quitter Flask
```

---

### Étape 5 — Lancer les tests

```powershell
uv run pytest tests -v
```

Si tous les tests passent en vert, l'installation est complète et fonctionnelle.

---

### Récapitulatif — les 5 commandes essentielles

```powershell
# 1. Extraire l'archive
tar -xzf messager_romain.tar.gz ; cd archilog-0.1

# 2. Installer tout (prod + dev)
uv sync --extra dev

# 3. Vérifier le CLI
uv run archilog --help

# 4. Lancer l'interface web en mode debug
uv run flask --app archilog.views --debug run

# 5. Lancer les tests
uv run pytest tests -v
```

---

## Lancer l'interface web

### Mode développement (recommandé, avec rechargement automatique)

```powershell
uv run flask --app archilog.views --debug run
```
```powershell
CTR+C  # pour quitter Flask
```

Le flag `--debug` active :
- le **rechargement automatique** à chaque modification d'un fichier Python
- le **débogueur interactif** dans le navigateur en cas d'erreur

### Changer le port

```powershell
uv run flask --app archilog.views --debug run --port 8080
```

Application accessible sur [http://127.0.0.1:8080](http://127.0.0.1:8080).

> La base SQLite est créée automatiquement au premier lancement.
> Obtenir son emplacement : `uv run archilog db-path`

---

## Utiliser le CLI

Chaque commande peut être appelée avec ses options en argument ou en mode
interactif (Click affiche un prompt pour les options manquantes).

### Aide

```powershell
uv run archilog --help
uv run archilog creation --help
```

### Cagnottes

```powershell
# Créer une cagnotte
uv run archilog creation --nom "Vacances été" --description "Séjour à Marseille"

# Mode interactif (Click demande les valeurs une par une)
uv run archilog creation

# Lister toutes les cagnottes
uv run archilog lister

# Supprimer une cagnotte et toutes ses dépenses
uv run archilog suppression --nom "Vacances été"
```

### Dépenses

```powershell
# Ajouter une dépense (le backtick ` est le caractère de continuation de ligne PowerShell)
uv run archilog ajout `
  --cagnotte "Vacances été" `
  --participant "Alice" `
  --montant 42.50 `
  --libelle "Restaurant" `
  --date "15/06/2025"
# --date est optionnel : la date du jour est utilisée si absente

# Afficher les dépenses d'une cagnotte
uv run archilog afficher --nom "Vacances été"

# Supprimer des dépenses d'un participant (mode interactif)
uv run archilog supprimer --cagnotte "Vacances été" --participant "Alice"
# → affiche la liste des dépenses d'Alice numérotées par indice
# → saisir  "0,2"  pour supprimer les indices 0 et 2
# → saisir  "tout" pour tout effacer
```

### Calcul et export

```powershell
# Calculer qui doit combien à qui
uv run archilog calcul --nom "Vacances été"

# Exporter les dépenses en CSV (crée "Vacances été.csv" dans le répertoire courant)
uv run archilog export --nom "Vacances été"
```

### Utilitaire

```powershell
# Afficher le chemin du fichier SQLite utilisé
uv run archilog db-path
```

---

## Exécuter les tests

Besoin de la dépendance `pytest` pour pouvoir lancer les tests :
```powershell
uv sync --extra dev
```
en cas d'erreur :
```powershell
uv run  # config le .venv
uv sync --extra dev
```
Puis :
```powershell
# Tous les tests (sortie compacte)
uv run pytest tests -v

# Sortie détaillée (nom complet de chaque test)
uv run pytest tests -vv

# Filtrer par nom de test ou de classe
uv run pytest tests -v -k "calcul"
uv run pytest tests -v -k "TestFlash"

# Un fichier précis
uv run pytest tests/test_domain.py -v
uv run pytest tests/test_cli.py -v
```

Les tests utilisent une base SQLite **en mémoire** : rien n'est écrit sur
le disque, chaque test repart d'une base vide, l'ordre d'exécution est
sans importance.

| Fichier          | Ce qui est testé                                                          |
|------------------|---------------------------------------------------------------------------|
| `test_smoke.py`  | Routes HTTP — codes de statut et redirections (PRG)                       |
| `test_routes.py` | Intégration Flask — HTML rendu, messages flash, isolation inter-cagnottes |
| `test_domain.py` | Logique métier — calculs d'équilibre, CRUD, participants                  |
| `test_cli.py`    | Toutes les commandes Click                                                |

---

## Variables d'environnement

| Variable              | Valeur par défaut               | Description                                                                                                                      |
|-----------------------|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `ARCHILOG_SECRET_KEY` | clé aléatoire (non persistante) | Clé Flask pour signer les sessions et les messages flash. **À définir si on veut des sessions persistantes entre redémarrages.** |
| `ARCHILOG_DB_PATH`    | voir ci-dessous                 | Chemin complet vers le fichier SQLite. Utile pour utiliser une base de test séparée.                                             |

**Emplacement par défaut de la base :**

| OS            | Chemin                                |
|---------------|---------------------------------------|
| Windows       | `%APPDATA%\archilog\archilog.db`      |
| Linux / macOS | `~/.local/share/archilog/archilog.db` |

Définir une variable pour la session PowerShell en cours :

```powershell
$env:ARCHILOG_SECRET_KEY = "une-chaine-longue-et-secrete"
$env:ARCHILOG_DB_PATH    = "C:\tmp\archilog_dev.db"

uv run flask --app archilog.views --debug run
```

---

## Structure du projet

```
archilog-0.1/
│
├── src/archilog/               # Package Python principal
│   ├── __init__.py             # Vide — déclare le package
│   ├── config.py               # SECRET_KEY depuis l'environnement
│   ├── data.py                 # SQLAlchemy Core + CagnotteRepository
│   ├── domain.py               # CagnotteService — logique métier pure
│   ├── views.py                # Routes Flask (interface web)
│   ├── cli.py                  # Commandes Click (interface terminal)
│   │
│   ├── static/
│   │   ├── css/style.css       # Feuille de style (dark mode, WCAG AA)
│   │   └── js/
│   │       ├── depenses.js     # Tableau dépenses : tri, recherche, AJAX
│   │       ├── home.js         # Sélection multiple, suppression groupée
│   │       ├── main.js         # Dark mode, toast, combobox participants
│   │       └── selection.js    # Gestion sélection partagée
│   │
│   └── templates/              # Templates Jinja2
│       ├── base.html           # Layout de base (dark mode anti-flash, toast)
│       ├── macros.html         # Macros Jinja2 réutilisables
│       ├── components/         # Toast, modals, onglets, SVG sprite
│       ├── cagnottes/          # Pages liste et création
│       └── pages/              # Vue d'ensemble, dépenses, équilibre, import CSV
│
├── tests/
│   ├── conftest.py             # Fixtures pytest (base en mémoire, client Flask)
│   ├── test_smoke.py           # Tests HTTP basiques
│   ├── test_routes.py          # Tests d'intégration Flask
│   ├── test_domain.py          # Tests logique métier
│   └── test_cli.py             # Tests CLI Click
│
└── pyproject.toml              # Dépendances, entrypoint CLI, config pytest
```

L'entrypoint CLI déclaré dans `pyproject.toml` :

```toml
[project.scripts]
archilog = "archilog.cli:cli"
```

`uv run archilog` → appelle le groupe Click `cli` dans `src/archilog/cli.py`.

---

## Dépannage

### `uv run archilog` : commande introuvable

S'assurer d'être dans le bon répertoire :

```powershell
ls pyproject.toml   # doit afficher le fichier
```

Puis relancer l'installation :

```powershell
uv sync --extra dev
uv run archilog --help
```

---

### `ModuleNotFoundError: No module named 'archilog'`

Toujours utiliser `uv run` et non `python` directement :

```powershell
# ✗ Ne pas faire
python -m archilog

# ✓ Faire
uv run archilog --help
uv run flask --app archilog.views --debug run
```

---

### Les messages flash disparaissent après redémarrage du serveur

`ARCHILOG_SECRET_KEY` n'est pas définie : Flask génère une nouvelle clé
aléatoire à chaque démarrage, ce qui invalide les sessions précédentes.

```powershell
$env:ARCHILOG_SECRET_KEY = "une-chaine-longue-et-secrete"
uv run flask --app archilog.views --debug run
```

---

### Erreur à l'import CSV : « Aucune ligne valide »

Vérifier les points suivants :

- **Encodage :** UTF-8 attendu (avec ou sans BOM — les deux sont acceptés).
- **Colonnes obligatoires :** `participant` et `montant`.
  Alias acceptés : `nom` → `participant`, `description` → `libelle`.
- **Séparateur :** `;` ou `,` — détecté automatiquement.
- **Montants :** format français `12,50` converti automatiquement en `12.5`.
- Les lignes avec participant vide ou montant invalide sont ignorées silencieusement.

Format minimal accepté :

```
participant;montant
Alice;42.50
Bob;30.00
```

---

### Réinitialiser la base de données

```powershell
# Localiser le fichier
uv run archilog db-path

# Supprimer (irréversible — adapter le chemin affiché)
Remove-Item "$env:APPDATA\archilog\archilog.db"

# La base est recrée automatiquement au prochain lancement
uv run archilog lister
```

---

### Les tests échouent avec des erreurs d'import

S'assurer que `pytest` est bien installé (groupe `dev`) :

```powershell
uv sync --extra dev
uv run pytest tests -v
```

---

*Projet pédagogique — Architecture Logicielle, IUT de Vélizy*