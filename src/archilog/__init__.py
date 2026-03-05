"""
archilog/__init__.py
─────────────────────────────────────────────────────────────────────────────
Point d'entrée du package Python `archilog`.

Ce fichier est volontairement vide : il déclare le répertoire comme un
package Python importable (PEP 328) sans exécuter aucun code au chargement.

Pourquoi ne rien exporter ici :
    Les modules sont volumineux et ont des effets de bord à l'import
    (création de l'engine SQLAlchemy dans data.py, instanciation du service
    dans views.py). Les importer tous ici forcerait ces effets à chaque
    `import archilog`, y compris dans les tests et la CLI.

    Chaque point d'entrée importe ce dont il a besoin explicitement :
        - flask run  → views.py (charge app, service, data)
        - archilog   → cli.py  (charge click + domain à la demande)
        - pytest     → conftest.py contrôle l'ordre des imports

Structure du package :
    archilog/
    ├── __init__.py      ← ce fichier (vide)
    ├── config.py        ← FLASK_SECRET_KEY, DATABASE_URL depuis l'environnement
    ├── data.py          ← engine SQLAlchemy, metadata, CagnotteRepository
    ├── domain.py        ← CagnotteService (orchestration sans HTTP)
    ├── views.py         ← routes Flask, instancie CagnotteService au niveau module
    ├── cli.py           ← groupe Click `archilog`, commandes CRUD
    ├── static/          ← CSS, JS, SVG sprite
    └── templates/       ← templates Jinja2 (base.html, composants, pages)
─────────────────────────────────────────────────────────────────────────────
"""