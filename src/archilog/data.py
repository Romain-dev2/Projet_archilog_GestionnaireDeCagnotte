"""
archilog — data.py
─────────────────────────────────────────────────────────────────────────────
Couche d'accès aux données — Repository SQLAlchemy Core (SQLite).

Rôle de ce fichier :
  - Définir le schéma de la base de données (tables + colonnes)
  - Exécuter les requêtes SQL via SQLAlchemy Core (pas d'ORM)
  - Exposer des méthodes CRUD simples à CagnotteService (domain.py)

Ce fichier ne contient AUCUNE logique métier.
Toutes les règles de gestion (calcul d'équilibre, validation, etc.) sont
dans domain.py.

Tables :
  cagnottes              → une cagnotte par ligne, colonne `participants` en JSON
  depenses               → dépenses liées à une cagnotte par nom (FK)
  remboursements_effectues → signatures des remboursements marqués effectués

Note : `engine` est remplacé par la fixture conftest.py lors des tests,
ce qui redirige tous les accès vers une base SQLite en mémoire.
─────────────────────────────────────────────────────────────────────────────
"""

# ── Connexion à la base ───────────────────────────────────────────────────
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from json import JSONDecodeError
from contextlib import contextmanager
from typing import List, Tuple, Optional, Iterator

from sqlalchemy.engine import Engine, Connection
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Float, Text,
    ForeignKey, select, func, delete, text, event,
)
from sqlalchemy.exc import IntegrityError, OperationalError


def _default_db_path() -> Path:
    """Calcule le chemin du fichier SQLite selon la plateforme.

    Priorité :
      1. Variable d'environnement ARCHILOG_DB_PATH (surcharge explicite).
      2. Répertoire "app data" standard : %APPDATA% (Windows) ou
         $XDG_DATA_HOME / ~/.local/share (Linux/macOS).

    Le répertoire parent est créé automatiquement si nécessaire.
    """
    # Surcharge explicite via variable d'environnement (tests, CI, Docker…)
    env = os.getenv("ARCHILOG_DB_PATH")
    if env:
        p = Path(env).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # Emplacement "app data" cross-platform
    if os.name == "nt":  # Windows
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:  # Linux/macOS
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    db_dir = base / "archilog"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "archilog.db"


# Chemin résolu une seule fois au chargement du module.
# conftest.py remplace `engine` APRÈS ce calcul, donc DB_PATH n'est jamais
# utilisé en test — la valeur calculée ici n'a pas d'importance dans ce cas.
DB_PATH = _default_db_path()


def get_db_path() -> str:
    """Retourne le chemin absolu du fichier SQLite utilisé."""
    return str(DB_PATH)


# URL de connexion SQLAlchemy construite à partir du chemin résolu.
# `as_posix()` garantit des slashes même sous Windows (sqlite:///C:/…).
ENGINE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# `engine` est un attribut module-level volontairement mutable :
# conftest.py le remplace par un engine SQLite en mémoire avant chaque suite
# de tests, redirigeant ainsi 100 % des accès DB sans sous-classer le repo.
engine: Engine = create_engine(ENGINE_URL, echo=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except sqlite3.Error:
        pass
    except AttributeError:
        pass


# -----------------------------------------------------------------------------
# Helpers de connexion/transaction
# -----------------------------------------------------------------------------

@contextmanager
def _tx_conn() -> Iterator[Connection]:
    """Ouvre une transaction et yield une Connection.

    À utiliser pour toute opération INSERT / UPDATE / DELETE.
    Le commit est émis automatiquement à la sortie du bloc `with` ;
    un rollback est effectué en cas d'exception.

    Note: certains IDE (PyCharm) peuvent mal inférer le type de engine.begin() selon
    les stubs SQLAlchemy installés. Centraliser ici évite d'avoir 16 warnings identiques.
    """
    with engine.begin() as conn:  # type: ignore[call-arg]
        yield conn


@contextmanager
def _rx_conn() -> Iterator[Connection]:
    """Ouvre une connexion sans transaction explicite (lecture).

    SQLAlchemy émet un BEGIN implicite par défaut ; engine.connect() sans
    engine.begin() laisse le driver gérer l'isolation — suffisant pour les SELECT.
    À utiliser uniquement pour les requêtes SELECT afin d'éviter de verrouiller la base.
    """
    with engine.connect() as conn:
        yield conn


metadata = MetaData()

# ── Définition des tables ─────────────────────────────────────────────────

# `participants` est stockée en JSON dans une colonne TEXT plutôt qu'en table
# relationnelle pour simplifier la gestion de l'autocomplétion : la liste peut
# être mise à jour sans migration de schéma.
cagnottes_table = Table(
    "cagnottes", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nom", String, unique=True, nullable=False),
    Column("description", Text),
    Column("participants", Text),  # liste JSON des participants connus (autocomplétion)
)

# La FK sur `cagnotte` (nom) plutôt que sur l'id est un choix de simplicité :
# le nom est la clé métier immuable utilisée partout dans les URLs.
depenses_table = Table(
    "depenses", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cagnotte", String, ForeignKey("cagnottes.nom", onupdate="CASCADE", ondelete="CASCADE"), nullable=False),
    Column("participant", String, nullable=False),
    Column("montant", Float, nullable=False),
    Column("date", String, nullable=True),  # format DD/MM/YYYY
    Column("libelle", Text, nullable=True),
)

# La "signature" (debiteur|crediteur|montant) identifie un remboursement de façon
# déterministe : elle est recalculée à chaque appel de `calculer()` et comparée
# à ce tableau pour savoir si le remboursement a déjà été effectué.
remboursements_table = Table(
    "remboursements_effectues", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cagnotte", String, ForeignKey("cagnottes.nom", onupdate="CASCADE", ondelete="CASCADE"), nullable=False),
    Column("signature", String, nullable=False),  # format "debiteur|crediteur|montant"
)


def _normalize_signature(signature: str) -> str | None:
    try:
        parts = signature.split("|")
        if len(parts) != 3:
            return signature
        debiteur, crediteur, montant_s = parts
        montant = float(str(montant_s).replace(",", "."))
        montant_norm = f"{montant:.2f}"
        return f"{debiteur}|{crediteur}|{montant_norm}"
    except sqlite3.Error:
        pass
    except AttributeError:
        pass


class CagnotteRepository:
    """
    Accès aux données. Toutes les méthodes ouvrent leur propre transaction
    via `with engine.begin() as conn`. L'attribut module `engine` est
    résolu à chaque appel → patchable depuis les tests sans sous-classer.
    """

    def __init__(self):
        # Crée les tables si elles n'existent pas, puis applique les migrations
        metadata.create_all(engine)
        self._migrate()

    @staticmethod
    def _migrate():
        """
        Ajoute les colonnes manquantes pour les bases existantes.

        Permet de faire évoluer le schéma sans outil de migration externe (Alembic).
        Chaque migration est idempotente : elle est silencieusement ignorée si la
        colonne existe déjà (SQLite lève OperationalError dans ce cas).

        Protection:
        - whitelist stricte sur le triplet (table, colonne, type)
        - validation d'identifiants SQLite (table/col) pour éviter un pattern injectable
        """
        migrations = [
            ("cagnottes", "participants", "TEXT"),
            ("depenses", "libelle", "TEXT"),
        ]

        def _is_ident(s: str) -> bool:
            # identifiant SQLite simple: lettres/chiffres/underscore, ne commence pas par un chiffre
            return bool(s) and (s[0].isalpha() or s[0] == "_") and all(
                ch.isalnum() or ch == "_" for ch in s
            )

        def _norm_sql_type(s: str) -> str:
            # Normalise " text  " -> "TEXT" (et évite des variantes triviales)
            return " ".join(s.strip().upper().split())

        # Whitelist sur le triplet complet (conceptuellement correct)
        allowed_triplets = {
            (t, c, _norm_sql_type(dt)) for (t, c, dt) in migrations
        }

        with _tx_conn() as conn:
            for table, col, dtype in migrations:
                dtype_n = _norm_sql_type(dtype)
                candidate = (table, col, dtype_n)

                # 1) whitelist triplet
                if candidate not in allowed_triplets:
                    raise ValueError(f"Migration non autorisée (whitelist triplet): {candidate}")

                # 2) identifiants safe
                if not _is_ident(table) or not _is_ident(col):
                    raise ValueError("Identifiant SQL invalide dans migration.")

                # 3) applique la migration si la colonne n'existe pas déjà
                try:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {dtype_n}'))
                except OperationalError:
                    # SQLite lève souvent OperationalError si la colonne existe déjà.
                    # On ignore pour rendre la migration idempotente.
                    pass

            # Assure des FK avec ON UPDATE/DELETE CASCADE (rebuild idempotent)
            def _fk_needs_rebuild(table_name: str) -> bool:
                try:
                    fks = conn.execute(text(f"PRAGMA foreign_key_list('{table_name}')")).all()
                except sqlite3.Error:
                    return False
                except AttributeError:
                    return False

                if not fks:
                    return True

                for fk in fks:
                    # fk columns: (id, seq, table, from, to, on_update, on_delete, match)
                    on_update = (fk[5] or "").upper()
                    on_delete = (fk[6] or "").upper()
                    if on_update != "CASCADE" or on_delete != "CASCADE":
                        return True

                return False

            def _rebuild_depenses() -> None:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS depenses__new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "cagnotte VARCHAR NOT NULL,"
                    "participant VARCHAR NOT NULL,"
                    "montant FLOAT NOT NULL,"
                    "date VARCHAR,"
                    "libelle TEXT,"
                    "FOREIGN KEY(cagnotte) REFERENCES cagnottes(nom) ON UPDATE CASCADE ON DELETE CASCADE"
                    ")"
                ))
                conn.execute(text(
                    "INSERT INTO depenses__new (id,cagnotte,participant,montant,date,libelle) "
                    "SELECT id,cagnotte,participant,montant,date,libelle FROM depenses"
                ))
                conn.execute(text("DROP TABLE depenses"))
                conn.execute(text("ALTER TABLE depenses__new RENAME TO depenses"))
                conn.execute(text("PRAGMA foreign_keys=ON"))

            def _rebuild_remboursements() -> None:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS remboursements_effectues__new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "cagnotte VARCHAR NOT NULL,"
                    "signature VARCHAR NOT NULL,"
                    "FOREIGN KEY(cagnotte) REFERENCES cagnottes(nom) ON UPDATE CASCADE ON DELETE CASCADE"
                    ")"
                ))
                conn.execute(text(
                    "INSERT INTO remboursements_effectues__new (id,cagnotte,signature) "
                    "SELECT id,cagnotte,signature FROM remboursements_effectues"
                ))
                conn.execute(text("DROP TABLE remboursements_effectues"))
                conn.execute(text("ALTER TABLE remboursements_effectues__new RENAME TO remboursements_effectues"))
                conn.execute(text("PRAGMA foreign_keys=ON"))

            if _fk_needs_rebuild("depenses"):
                _rebuild_depenses()
            if _fk_needs_rebuild("remboursements_effectues"):
                _rebuild_remboursements()

    # ── Cagnottes ─────────────────────────────────────────────────────────

    @staticmethod
    def lister_cagnottes() -> List[dict]:
        """Retourne toutes les cagnottes (nom + description)."""
        stmt = select(cagnottes_table.c.nom, cagnottes_table.c.description)
        with _rx_conn() as conn:
            rows = conn.execute(stmt).all()
        return [{"nom": nom, "description": desc} for nom, desc in rows]

    @staticmethod
    def creer_cagnotte(nom: str, description: str) -> bool:
        """
        Insère une nouvelle cagnotte.
        Retourne True si créée, False si le nom existe déjà (IntegrityError).

        L'unicité est garantie par la contrainte UNIQUE sur la colonne `nom`.
        On préfère attraper IntegrityError plutôt que de faire un SELECT préalable
        pour éviter une race condition entre la vérification et l'insertion.
        """
        try:
            with _tx_conn() as conn:
                conn.execute(cagnottes_table.insert().values(
                    nom=nom, description=description, participants='[]'
                ))
            return True
        except IntegrityError:
            return False

    @staticmethod
    def supprimer_cagnotte(nom: str) -> None:
        """Supprime la cagnotte et toutes ses dépenses + remboursements associés.

        L'ordre de suppression respecte les contraintes FK :
        remboursements → dépenses → cagnotte.
        """
        with _tx_conn() as conn:
            conn.execute(delete(remboursements_table).where(remboursements_table.c.cagnotte == nom))
            conn.execute(delete(depenses_table).where(depenses_table.c.cagnotte == nom))
            conn.execute(delete(cagnottes_table).where(cagnottes_table.c.nom == nom))

    @staticmethod
    def get_participants(nom: str) -> List[str]:
        """Lit la liste JSON des participants connus (colonne `participants`).

        Cette liste est mise à jour à chaque ajout de dépense via `_ajouter_participant`,
        mais PAS lors d'un import CSV en masse (voir `importer_depenses_csv`).
        """
        stmt = select(cagnottes_table.c.participants).where(cagnottes_table.c.nom == nom)
        with _rx_conn() as conn:
            row = conn.execute(stmt).scalar_one_or_none()
        if not row:
            return []
        try:
            return json.loads(row)
        except (JSONDecodeError, TypeError):
            # Colonne corrompue ou NULL inattendu : on retourne une liste vide
            # plutôt que de planter l'autocomplétion.
            return []

    @staticmethod
    def participants_depuis_depenses(nom: str) -> list[str]:
        """
        Retourne les participants présents dans la table depenses pour une cagnotte,
        sans charger toutes les dépenses (SELECT DISTINCT).

        Complémente get_participants() pour les participants ajoutés via import CSV,
        qui ne mettent pas à jour la colonne JSON de la cagnotte.
        """
        stmt = (
            select(func.distinct(depenses_table.c.participant))
            .where(depenses_table.c.cagnotte == nom)
            .order_by(depenses_table.c.participant)
        )
        with _rx_conn() as conn:
            return [p for (p,) in conn.execute(stmt).all() if p]

    @staticmethod
    def maj_participants(nom: str, participants: List[str]) -> None:
        """Écrase la liste JSON des participants de la cagnotte."""
        with _tx_conn() as conn:
            conn.execute(
                cagnottes_table.update()
                .where(cagnottes_table.c.nom == nom)
                .values(participants=json.dumps(participants, ensure_ascii=False))
            )

    # ── Dépenses ──────────────────────────────────────────────────────────

    @staticmethod
    def lister_depenses(nom: str) -> List[dict]:
        """Retourne toutes les dépenses d'une cagnotte, triées par id (ordre d'insertion)."""
        stmt = (
            select(
                depenses_table.c.id,
                depenses_table.c.participant,
                depenses_table.c.montant,
                depenses_table.c.date,
                depenses_table.c.libelle,
            )
            .where(depenses_table.c.cagnotte == nom)
            .order_by(depenses_table.c.id)
        )
        with _rx_conn() as conn:
            rows = conn.execute(stmt).all()
        return [
            {"id": id_, "participant": p, "montant": m, "date": d, "libelle": l}
            for id_, p, m, d, l in rows
        ]

    @staticmethod
    def get_depense(depense_id: int) -> Optional[dict]:
        """Retourne une dépense par son identifiant, ou None si introuvable."""
        stmt = select(depenses_table).where(depenses_table.c.id == depense_id)
        with _rx_conn() as conn:
            row = conn.execute(stmt).one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "cagnotte": row.cagnotte,
            "participant": row.participant,
            "montant": row.montant,
            "date": row.date,
            "libelle": row.libelle,
        }

    def ajouter_depense(self, cagnotte: str, participant: str, montant: float,
                        date_str: Optional[str], libelle: Optional[str] = None) -> None:
        """Insère une dépense et met à jour la liste JSON des participants (autocomplétion)."""
        with _tx_conn() as conn:
            conn.execute(depenses_table.insert().values(
                cagnotte=cagnotte,
                participant=participant,
                montant=montant,
                date=date_str,
                libelle=libelle or None,
            ))
            row = conn.execute(
                select(cagnottes_table.c.participants)
                .where(cagnottes_table.c.nom == cagnotte)
            ).scalar_one_or_none()
            try:
                existants = json.loads(row) if row else []
            except (JSONDecodeError, TypeError):
                existants = []
            if participant not in existants:
                conn.execute(
                    cagnottes_table.update()
                    .where(cagnottes_table.c.nom == cagnotte)
                    .values(participants=json.dumps(existants + [participant], ensure_ascii=False))
                )
        # Mise à jour de l'autocomplétion dans une transaction séparée :
        # si elle échoue, la dépense est quand même enregistrée.
        self._ajouter_participant(cagnotte, participant)

    def _ajouter_participant(self, cagnotte: str, participant: str) -> None:
        """Ajoute le participant à la liste JSON s'il n'y est pas déjà (autocomplétion)."""
        existants = self.get_participants(cagnotte)
        if participant not in existants:
            self.maj_participants(cagnotte, existants + [participant])

    @staticmethod
    def modifier_depense(depense_id: int, participant: str, montant: float,
                         date_str: Optional[str], libelle: Optional[str]) -> None:
        """Met à jour les champs d'une dépense existante identifiée par son id."""
        with _tx_conn() as conn:
            conn.execute(
                depenses_table.update()
                .where(depenses_table.c.id == depense_id)
                .values(
                    participant=participant,
                    montant=montant,
                    date=date_str,
                    libelle=libelle or None,
                )
            )

    @staticmethod
    def _lister_ids(nom: str) -> List[int]:
        """Retourne la liste ordonnée des ids de dépenses d'une cagnotte.

        Utilisée par supprimer_depenses_par_indices pour convertir des positions
        (indices 0-based) en identifiants réels avant suppression.
        """
        # TODO: _tx_conn ouvre une transaction en écriture pour une lecture pure ;
        #       _rx_conn suffirait ici. Non corrigé car _lister_ids est privée et
        #       appelée uniquement juste avant une transaction d'écriture.
        stmt = (
            select(depenses_table.c.id)
            .where(depenses_table.c.cagnotte == nom)
            .order_by(depenses_table.c.id)
        )
        with _tx_conn() as conn:
            return [r[0] for r in conn.execute(stmt).all()]

    @staticmethod
    def supprimer_depenses_par_indices(nom: str, indices: List[int]) -> None:
        """
        Supprime les dépenses aux positions (indices 0-based dans la liste ordonnée).
        Après suppression, nettoie la liste JSON des participants pour retirer
        ceux qui n'ont plus aucune dépense restante.

        Tout est fait dans la même transaction pour éviter les états incohérents.
        """
        if not indices:
            return
        with _tx_conn() as conn:
            ids_all = [r[0] for r in conn.execute(
                select(depenses_table.c.id)
                .where(depenses_table.c.cagnotte == nom)
                .order_by(depenses_table.c.id)
            ).all()]
            ids_to_delete = [ids_all[i] for i in indices if 0 <= i < len(ids_all)]
            if not ids_to_delete:
                return
            # Suppression des dépenses
            conn.execute(delete(depenses_table).where(depenses_table.c.id.in_(ids_to_delete)))
            # Participants encore actifs (lu sur la même connexion → voit le DELETE ci-dessus)
            encore_actifs = {
                r[0] for r in conn.execute(
                    select(depenses_table.c.participant)
                    .where(depenses_table.c.cagnotte == nom)
                    .distinct()
                ).all()
            }
            # Mise à jour de la liste JSON dans la même transaction
            row = conn.execute(
                select(cagnottes_table.c.participants)
                .where(cagnottes_table.c.nom == nom)
            ).scalar_one_or_none()
            actuels = json.loads(row) if row else []
            filtres = [p for p in actuels if p in encore_actifs]
            if filtres != actuels:
                conn.execute(
                    cagnottes_table.update()
                    .where(cagnottes_table.c.nom == nom)
                    .values(participants=json.dumps(filtres, ensure_ascii=False))
                )

    @staticmethod
    def importer_depenses_csv(nom: str, depenses: List[dict]) -> int:
        """Insère en masse les dépenses pré-parsées dans une seule transaction.

        Contrairement à ajouter_depense(), cette méthode ne met PAS à jour la
        colonne JSON participants pour des raisons de performance (import potentiellement
        large). Les participants importés restent néanmoins accessibles via
        participants_depuis_depenses() (SELECT DISTINCT sur la table depenses).
        """
        with _tx_conn() as conn:
            for d in depenses:
                conn.execute(
                    depenses_table.insert().values(
                        cagnotte=nom,
                        participant=d["participant"],
                        montant=d["montant"],
                        date=d.get("date"),
                        libelle=d.get("libelle"),
                    )
                )

        return len(depenses)

    @staticmethod
    def somme_par_participant(nom: str) -> List[Tuple[str, float]]:
        """Retourne la somme des dépenses par participant pour une cagnotte.

        Utilisée par CagnotteService.calculer() pour construire les soldes
        avant d'appliquer l'algorithme glouton d'équilibre.
        """
        stmt = (
            select(depenses_table.c.participant, func.sum(depenses_table.c.montant))
            .where(depenses_table.c.cagnotte == nom)
            .group_by(depenses_table.c.participant)
        )
        with _rx_conn() as conn:
            rows = conn.execute(stmt).all()
        return [(p, m or 0.0) for p, m in rows]

    # ── Remboursements effectués ───────────────────────────────────────────

    @staticmethod
    def get_remboursements_effectues(nom: str) -> set:
        """Retourne l'ensemble des signatures des remboursements marqués effectués."""
        stmt = select(remboursements_table.c.signature).where(
            remboursements_table.c.cagnotte == nom
        )
        with _rx_conn() as conn:
            return {_normalize_signature(r[0]) for r in conn.execute(stmt).all()}

    @staticmethod
    def toggle_remboursement(nom: str, signature: str) -> bool:
        """
        Bascule l'état d'un remboursement :
          - S'il existe → supprimé (non effectué) → retourne False
          - S'il n'existe pas → inséré (effectué) → retourne True

        Le check et l'action sont dans la même transaction pour éviter
        les doublons en cas d'appels concurrents.
        """
        signature = _normalize_signature(signature)
        check = select(func.count()).select_from(remboursements_table).where(
            remboursements_table.c.cagnotte == nom,
            remboursements_table.c.signature == signature,
        )
        with _tx_conn() as conn:
            exists = conn.execute(check).scalar_one() > 0
            if exists:
                conn.execute(delete(remboursements_table).where(
                    remboursements_table.c.cagnotte == nom,
                    remboursements_table.c.signature == signature,
                ))
                return False
            else:
                conn.execute(remboursements_table.insert().values(
                    cagnotte=nom, signature=signature
                ))
                return True