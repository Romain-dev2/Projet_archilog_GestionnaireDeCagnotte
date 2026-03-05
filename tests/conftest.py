"""
tests/conftest.py
─────────────────────────────────────────────────────────────────────────────
Configuration pytest partagée pour tous les tests.

POURQUOI L'ORDRE D'IMPORT EST CRITIQUE :
    data.py  → crée `engine` au niveau module  (sqlite fichier réel)
    views.py → exécute `service = CagnotteService()` à l'import
               → CagnotteRepository.__init__ → metadata.create_all(engine)
               → si engine = fichier réel → on pollue la vraie base

SOLUTION APPLIQUÉE :
    1. import archilog.data          → engine fichier créé (lazy, pas connecté)
    2. archilog.data.engine = ...    → remplacé par engine :memory:
    3. metadata.create_all(engine)   → tables créées en mémoire
    4. import archilog.views         → service instancié avec le bon engine ✓

    Toutes les méthodes du Repository font `with engine.begin()` où `engine`
    est résolu dans le namespace du module data à chaque appel.
    Remplacer l'attribut module suffit à rediriger 100 % des accès DB.

ISOLATION ENTRE TESTS :
    La fixture `reset_db` (autouse=True) drop et recrée toutes les tables
    avant chaque test. Les tests sont donc complètement indépendants les uns
    des autres — l'ordre d'exécution n'a aucune importance.

STRUCTURE PROJET ATTENDUE :
    src/
      archilog/         ← package
        static/
        templates/
        __init__.py
        cli.py
        data.py
        domain.py
        views.py

    tests/              ← ce dossier
      conftest.py
      test_smoke.py
      test_domain.py
    pyproject.toml

LANCEMENT :
    python -m pytest tests -v                        # tous les tests
    python -m pytest tests -vv                       # tous les tests + vision sur chaque tests
    python -m pytest tests/test_smoke.py -v          # smoke tests uniquement
    python -m pytest tests/test_domain.py -v         # tests domaine uniquement
    python -m pytest tests -v -k "calcul"            # filtre par nom
─────────────────────────────────────────────────────────────────────────────
"""

import sys
import os

import pytest
from sqlalchemy import create_engine

# ── Chemin vers le package ─────────────────────────────────────────────────
# Ajuste sys.path pour que `import archilog` fonctionne sans pip install -e .
# __file__ = .../tests/conftest.py → on remonte d'un niveau vers la racine du
# projet, puis on cherche src/ (layout standard) ou la racine directement.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC  = os.path.join(_ROOT, "src")

# Essaie src/ d'abord (layout src/archilog/), puis la racine (layout plat).
for _path in (_SRC, _ROOT):
    if os.path.isdir(os.path.join(_path, "archilog")):
        if _path not in sys.path:
            sys.path.insert(0, _path)
        break


# ══════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 — Importer data ET patcher engine AVANT tout autre import archilog
#
# On utilise une base SQLite en mémoire partagée (cache=shared) plutôt que
# sqlite:///:memory: standard, car le mode "shared" permet à plusieurs
# connexions d'accéder à la même base dans le même process.
# C'est nécessaire quand Flask et le Repository ouvrent des connexions
# séparées dans le même test (ex : client HTTP + CagnotteService direct).
# ══════════════════════════════════════════════════════════════════════════
import archilog.data as _data                         # noqa: E402

_ENGINE_TEST = create_engine(
    "sqlite:///file::memory:?cache=shared&uri=true",
    echo=False,      # passer à True pour voir le SQL en cas de debug
    future=True,
    # check_same_thread=False : SQLite interdit par défaut l'accès multi-thread ;
    # on le désactive car Flask peut servir des requêtes dans des threads différents.
    # uri=True : nécessaire pour les URLs SQLite de la forme "file:...?..."
    connect_args={"check_same_thread": False, "uri": True},
)

# ← Patch central : tout accès ultérieur à _data.engine pointe vers la base de test.
_data.engine = _ENGINE_TEST
# Crée les tables (cagnotte, depense, remboursement) dans la base en mémoire.
_data.metadata.create_all(_ENGINE_TEST)


# ══════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 — Importer l'app Flask (service instancié ici, engine déjà patché)
#
# views.py crée un CagnotteService() au niveau module → CagnotteRepository
# → metadata.create_all(engine). Comme engine est déjà patché, tout pointe
# vers la base en mémoire. L'ordre des imports (data avant views) est donc
# non négociable.
# ══════════════════════════════════════════════════════════════════════════
from archilog.views import app as _app               # noqa: E402

_app.config["TESTING"]    = True
# SECRET_KEY fixe pour les tests : Flask en a besoin pour signer les cookies
# de session (messages flash). Une valeur quelconque suffit en test.
_app.config["SECRET_KEY"] = "test-secret-key"


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_db():
    """
    Remet la base à zéro AVANT chaque test.

    autouse=True → s'applique automatiquement à TOUS les tests de la suite
    sans injection explicite dans la signature de la fonction de test.

    Stratégie drop_all + create_all (plutôt que DELETE FROM) :
      - Garantit que les séquences d'auto-increment sont réinitialisées.
      - Évite les effets de bord liés aux contraintes FK pendant les deletes.
      - L'ordre d'exécution des tests n'a donc aucune importance.
    """
    _data.metadata.drop_all(_ENGINE_TEST)
    _data.metadata.create_all(_ENGINE_TEST)
    yield
    # Pas de teardown après le yield : le prochain reset_db drop de toute façon.


@pytest.fixture
def client(reset_db):  # injection explicite de reset_db → ordre garanti
    """
    Client HTTP Flask pour simuler des requêtes sans serveur réel.
    Utilisé dans test_smoke.py et test_routes.py pour tester les routes HTTP.

    reset_db est injecté explicitement (en plus de autouse) pour garantir
    que la base est vidée AVANT que le premier client envoie sa requête.
    Sans cela, l'ordre d'application des fixtures autouse vs fixtures
    nommées n'est pas garanti à 100 % selon la version de pytest.
    """
    with _app.test_client() as c:
        yield c


@pytest.fixture
def service():
    """
    CagnotteService pointant sur la base de test en mémoire.
    Utilisé dans test_domain.py pour tester la logique métier directement,
    sans passer par HTTP ni par le rendu HTML.

    reset_db (autouse=True) s'applique automatiquement → la base est déjà
    vide quand cette fixture est demandée.
    """
    from archilog.domain import CagnotteService
    return CagnotteService()