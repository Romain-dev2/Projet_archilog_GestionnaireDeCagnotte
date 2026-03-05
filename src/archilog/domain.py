"""
archilog — domain.py
─────────────────────────────────────────────────────────────────────────────
Couche domaine / logique métier.

Rôle de ce fichier :
  - Orchestrer les appels au Repository (data.py)
  - Implémenter le calcul d'équilibre (qui doit combien à qui)
  - Exposer une interface propre à views.py sans exposer SQL

Ce fichier ne contient AUCUN accès direct à la base de données.
Toutes les requêtes SQL passent par CagnotteRepository (data.py).

Algorithme d'équilibre (calculer) :
  1. Calculer la somme dépensée par participant via le repository
  2. Calculer la part individuelle = total / nb participants
  3. Calculer le solde de chaque participant (dépensé - part)
  4. Appliquer l'algorithme glouton min-créditeur / min-débiteur pour
     minimiser le nombre de transactions
─────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .data import CagnotteRepository


# ── DTOs (Data Transfer Objects) ──────────────────────────────────────────
# Objets simples utilisés pour transporter les données entre les couches.
# Pas de logique ici — juste des conteneurs typés.
# L'utilisation de @dataclass permet l'égalité structurelle (==) dans les tests.

@dataclass
class CagnotteDTO:
    nom: str
    description: str | None = None


@dataclass
class DepenseDTO:
    participant: str
    montant: float
    date: str | None = None
    libelle: str | None = None
    id: int | None = None


class CagnotteService:
    """
    Service principal de l'application.
    Instancié une seule fois dans views.py au démarrage de l'app Flask.
    Instancié par fixture dans les tests (conftest.py).

    Toutes les méthodes publiques de cette classe constituent l'API interne
    du domaine : ni views.py ni cli.py n'accèdent directement au repository.
    """

    def __init__(self):
        self.repo = CagnotteRepository()

    # ── Cagnottes ─────────────────────────────────────────────────────────

    def lister_cagnottes(self) -> List[CagnotteDTO]:
        """Retourne toutes les cagnottes sous forme de DTOs."""
        return [CagnotteDTO(**row) for row in self.repo.lister_cagnottes()]

    def creer_cagnotte(self, nom: str, description: str) -> bool:
        """
        Crée une nouvelle cagnotte.
        Retourne True si créée, False si le nom existe déjà.
        """
        return self.repo.creer_cagnotte(nom, description)

    def supprimer_cagnotte(self, nom: str):
        """Supprime la cagnotte et toutes ses dépenses + remboursements."""
        self.repo.supprimer_cagnotte(nom)

    def get_participants(self, nom: str) -> List[str]:
        """
        Retourne la liste unifiée et dédupliquée des participants :
          - Participants fixes enregistrés dans la colonne JSON
          - Participants déduits des dépenses existantes

        Garantit que même après un import CSV (qui ne met pas à jour la colonne JSON),
        tous les participants sont visibles dans l'autocomplétion.
        """
        fixes         = self.repo.get_participants(nom)
        from_depenses = self.repo.participants_depuis_depenses(nom)
        # dict.fromkeys préserve l'ordre d'insertion (garanti depuis Python 3.7) :
        # les participants fixes apparaissent en premier, les "découverts" ensuite.
        merged        = list(dict.fromkeys(fixes + from_depenses))
        return merged

    def maj_participants(self, nom: str, participants: List[str]):
        """Écrase la liste fixe de participants d'une cagnotte."""
        self.repo.maj_participants(nom, participants)

    # ── Dépenses ──────────────────────────────────────────────────────────

    def lister_depenses(self, nom: str) -> List[DepenseDTO]:
        """Retourne toutes les dépenses d'une cagnotte sous forme de DTOs."""
        return [DepenseDTO(**row) for row in self.repo.lister_depenses(nom)]

    def get_depense(self, depense_id: int) -> Optional[DepenseDTO]:
        """Retourne une dépense par son id, ou None si introuvable."""
        row = self.repo.get_depense(depense_id)
        if not row:
            return None
        return DepenseDTO(
            id=row["id"],
            participant=row["participant"],
            montant=row["montant"],
            date=row["date"],
            libelle=row["libelle"],
        )

    def ajouter_depense(self, cagnotte: str, participant: str, montant: float,
                        date_str: str | None, libelle: str | None = None):
        self.repo.ajouter_depense(cagnotte, participant, montant, date_str, libelle)

    def modifier_depense(self, depense_id: int, participant: str, montant: float,
                         date_str: str | None, libelle: str | None):
        self.repo.modifier_depense(depense_id, participant, montant, date_str, libelle)

    def supprimer_depenses_par_indices(self, nom: str, indices: list[int]):
        """
        Supprime les dépenses aux positions données (indices 0-based).
        Nettoie automatiquement la liste des participants après suppression.
        """
        self.repo.supprimer_depenses_par_indices(nom, indices)

    def importer_depenses_csv(self, cagnotte: str, depenses: list[dict]) -> int:
        """Insère en masse des dépenses pré-parsées depuis un CSV."""
        return self.repo.importer_depenses_csv(cagnotte, depenses)

    # ── Calcul d'équilibre ─────────────────────────────────────────────────

    def calculer(self, nom: str) -> Dict[str, Any]:
        """
        Calcule qui doit quoi à qui pour équilibrer les dépenses.

        Algorithme glouton :
          1. Calculer le solde de chaque participant (montant payé - part individuelle)
          2. Séparer créditeurs (solde > 0) et débiteurs (solde < 0)
          3. À chaque étape, faire payer le plus petit débiteur au plus petit créditeur
          4. Répéter jusqu'à ce qu'il n'y ait plus de débiteur ni de créditeur

        Cet algorithme ne minimise pas forcément le nombre de transactions,
        mais produit des résultats stables et lisibles.

        Retourne :
          total           : somme totale des dépenses
          part            : montant idéal par participant
          transactions    : liste de {debiteur, crediteur, montant, signature, effectue}
          par_participant : liste de {nom, total} triée par montant décroissant
        """
        depenses_par_participant = self.repo.somme_par_participant(nom)
        if not depenses_par_participant:
            return {
                "total": 0.0, "part": 0.0, "transactions": [],
                "par_participant": [],
            }

        total = sum(s for _, s in depenses_par_participant)
        n     = len(depenses_par_participant)
        part  = total / n if n else 0.0

        # Calcul des soldes : positif = a trop payé (créditeur), négatif = a trop peu payé (débiteur)
        soldes     = {p: s - part for p, s in depenses_par_participant}
        crediteurs = {p: s  for p, s in soldes.items() if s > 0}
        debiteurs  = {p: -s for p, s in soldes.items() if s < 0}  # valeur absolue

        effectues    = self.repo.get_remboursements_effectues(nom)
        transactions = []

        # Algorithme glouton : appaire le plus petit débiteur avec le plus petit créditeur
        while crediteurs and debiteurs:
            c = min(crediteurs, key=crediteurs.get)
            d = min(debiteurs,  key=debiteurs.get)
            m = min(crediteurs[c], debiteurs[d])
            # La signature identifie de façon déterministe le remboursement :
            # même format attendu dans la table remboursements_effectues.
            sig = f"{d}|{c}|{round(m, 2):.2f}"
            transactions.append({
                "debiteur":  d, "crediteur": c,
                "montant":   round(m, 2),
                "signature": sig,
                "effectue":  sig in effectues,
            })
            crediteurs[c] -= m
            debiteurs[d]  -= m
            # Retire les participants dont le solde est soldé (< 1 centime)
            if abs(crediteurs[c]) < 1e-9: del crediteurs[c]
            if abs(debiteurs[d])  < 1e-9: del debiteurs[d]

        return {
            "total":           round(total, 2),
            "part":            round(part,  2),
            "transactions":    transactions,
            "par_participant": sorted(
                [{"nom": p, "total": round(s, 2)} for p, s in depenses_par_participant],
                key=lambda x: x["total"], reverse=True
            ),
        }

    def toggle_remboursement(self, nom: str, signature: str) -> bool:
        """
        Bascule l'état d'un remboursement.
        Retourne True si désormais effectué, False si annulé.
        """
        return self.repo.toggle_remboursement(nom, signature)