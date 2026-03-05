"""
tests/test_domain.py
─────────────────────────────────────────────────────────────────────────────
Tests unitaires de la couche domaine — on appelle CagnotteService directement,
sans passer par HTTP ni par les templates.

Avantage : on contrôle exactement les données en entrée et on vérifie
le résultat au centime près, sans bruit lié au rendu HTML.

Fixture injectée depuis conftest.py : `service` (CagnotteService isolé sur
une base SQLite en mémoire réinitialisée avant chaque test).

Organisation :
    1. Cagnottes CRUD           — créer, lister, supprimer, unicité du nom
    2. Dépenses CRUD            — ajouter, modifier, supprimer par indice
    3. Calcul d'équilibre       — cas simples et cas limites (valeurs exactes)
    4. Participants             — autocomplétion et nettoyage automatique
    5. Import CSV               — couche domaine (sans HTTP)
    6. Retour booléen création  — contrat d'interface de creer_cagnotte()
    7. Persistance participants — colonne JSON d'autocomplétion
    8. Remboursements           — toggle AJAX et état dans calculer()
    9. get_depense              — lecture d'une dépense par identifiant
─────────────────────────────────────────────────────────────────────────────
"""


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# Fonctions utilitaires partagées entre les tests pour éviter la répétition.
# Convention : pas d'assertion ici — leur rôle est uniquement de préparer
# l'état de la base avant la partie "Act + Assert" du test.
# ══════════════════════════════════════════════════════════════════════════

def _setup(service, nom="TestCagnotte"):
    """Crée une cagnotte de test et retourne son nom."""
    service.creer_cagnotte(nom, "cagnotte de test")
    return nom


def _depense(service, cagnotte, participant, montant):
    """Ajoute une dépense sans libellé ni catégorie et retourne le service
    pour permettre le chaînage : _depense(...).lister_depenses(...)."""
    service.ajouter_depense(cagnotte, participant, montant, "15/06/2025")
    return service


# ══════════════════════════════════════════════════════════════════════════
# 1. Cagnottes CRUD
# ══════════════════════════════════════════════════════════════════════════

def test_creer_et_lister_cagnotte(service):
    """Créer une cagnotte → elle apparaît dans la liste."""
    service.creer_cagnotte("Voyage", "Un voyage")
    cagnottes = service.lister_cagnottes()

    noms = [c.nom for c in cagnottes]
    assert "Voyage" in noms


def test_supprimer_cagnotte(service):
    """Supprimer une cagnotte → elle disparaît de la liste."""
    service.creer_cagnotte("ASupprimer", "")
    service.supprimer_cagnotte("ASupprimer")

    noms = [c.nom for c in service.lister_cagnottes()]
    assert "ASupprimer" not in noms


def test_supprimer_cagnotte_supprime_ses_depenses(service):
    """Supprimer une cagnotte → ses dépenses disparaissent aussi.
    On recrée la cagnotte après suppression pour vérifier qu'il n'y a pas
    de dépenses orphelines (FK ON DELETE CASCADE)."""
    service.creer_cagnotte("AvecDep", "")
    service.ajouter_depense("AvecDep", "Alice", 50.0, "01/01/2025")

    service.supprimer_cagnotte("AvecDep")

    service.creer_cagnotte("AvecDep", "")
    assert service.lister_depenses("AvecDep") == []


def test_cagnotte_nom_unique(service):
    """Créer deux cagnottes avec le même nom → une seule en base."""
    service.creer_cagnotte("Doublon", "première fois")
    service.creer_cagnotte("Doublon", "deuxième fois")  # doit être ignoré silencieusement

    cagnottes = [c for c in service.lister_cagnottes() if c.nom == "Doublon"]
    assert len(cagnottes) == 1


def test_lister_cagnottes_vide(service):
    """Sans création → liste vide."""
    assert service.lister_cagnottes() == []


# ══════════════════════════════════════════════════════════════════════════
# 2. Dépenses CRUD
# ══════════════════════════════════════════════════════════════════════════

def test_ajouter_et_lister_depenses(service):
    """Ajouter 2 dépenses → lister retourne 2 éléments."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 40.0)
    _depense(service, cagnotte, "Bob",   60.0)

    depenses = service.lister_depenses(cagnotte)
    assert len(depenses) == 2


def test_depense_contient_bons_champs(service):
    """Les champs d'une dépense correspondent à ce qu'on a saisi."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Alice", 42.5, "20/06/2025", libelle="Courses")

    dep = service.lister_depenses(cagnotte)[0]
    assert dep.participant == "Alice"
    assert dep.montant     == 42.5
    assert dep.libelle     == "Courses"


def test_depense_sans_libelle(service):
    """Une dépense créée sans libellé → libelle est None."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Bob", 10.0, "01/06/2025")

    dep = service.lister_depenses(cagnotte)[0]
    assert dep.libelle is None


def test_modifier_depense(service):
    """Modifier une dépense → les nouvelles valeurs sont en base."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Alice", 30.0, "01/06/2025")

    dep = service.lister_depenses(cagnotte)[0]
    service.modifier_depense(dep.id, "Bob", 99.0, "02/06/2025", "Modifié")

    dep_modif = service.get_depense(dep.id)
    assert dep_modif.participant == "Bob"
    assert dep_modif.montant     == 99.0
    assert dep_modif.libelle     == "Modifié"


def test_supprimer_depense_par_indice(service):
    """Supprimer la dépense à l'index 0 → liste vide."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 50.0)

    service.supprimer_depenses_par_indices(cagnotte, [0])
    assert service.lister_depenses(cagnotte) == []


def test_supprimer_plusieurs_depenses(service):
    """Supprimer indices 0 et 1 sur 3 → reste 1 dépense."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 10.0)
    _depense(service, cagnotte, "Bob",   20.0)
    _depense(service, cagnotte, "Alice", 30.0)

    service.supprimer_depenses_par_indices(cagnotte, [0, 1])
    assert len(service.lister_depenses(cagnotte)) == 1


def test_supprimer_indice_hors_limites_ne_plante_pas(service):
    """Supprimer un indice qui n'existe pas → pas d'exception (ignoré)."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 10.0)
    # indice 5 n'existe pas — doit être ignoré silencieusement
    service.supprimer_depenses_par_indices(cagnotte, [5])
    assert len(service.lister_depenses(cagnotte)) == 1


# ══════════════════════════════════════════════════════════════════════════
# 3. Calcul d'équilibre
#    Cœur de la logique métier — les calculs sont documentés manuellement
#    pour qu'on puisse relire et vérifier sans faire tourner les tests.
#    L'algorithme est glouton (domain.py) : il appaire le débiteur le plus
#    important avec le créditeur le plus important à chaque itération.
# ══════════════════════════════════════════════════════════════════════════

def test_calculer_cagnotte_vide(service):
    """Sans dépenses → tout à zéro, aucune transaction."""
    cagnotte = _setup(service)
    result   = service.calculer(cagnotte)

    assert result["total"]        == 0.0
    assert result["part"]         == 0.0
    assert result["transactions"] == []


def test_calculer_un_seul_participant(service):
    """Un seul participant → total correct, aucune transaction.
    Quand il n'y a qu'un participant, part = total et solde = 0 → personne
    ne doit rien à personne."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 60.0)

    result = service.calculer(cagnotte)
    assert result["total"] == 60.0
    assert result["part"]  == 60.0
    assert result["transactions"] == []


def test_calculer_cas_simple_deux_personnes(service):
    """
    Cas simple — 2 participants :
        Alice paie 90 €, Bob paie 30 €
        total = 120 €, part = 60 €
        Alice solde = 90 - 60 = +30 (créditeur)
        Bob   solde = 30 - 60 = -30 (débiteur)
        → Bob doit 30 € à Alice
    """
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 90.0)
    _depense(service, cagnotte, "Bob",   30.0)

    result = service.calculer(cagnotte)
    assert result["total"] == 120.0
    assert result["part"]  == 60.0
    assert len(result["transactions"]) == 1

    t = result["transactions"][0]
    assert t["debiteur"]  == "Bob"
    assert t["crediteur"] == "Alice"
    assert t["montant"]   == 30.0


def test_calculer_cas_equilibre_parfait(service):
    """
    Tout le monde paie la même chose → aucune transaction.
        Alice=30, Bob=30, Carol=30 → total=90, part=30, solde=0 pour tous
    """
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 30.0)
    _depense(service, cagnotte, "Bob",   30.0)
    _depense(service, cagnotte, "Carol", 30.0)

    result = service.calculer(cagnotte)
    assert result["total"]        == 90.0
    assert result["part"]         == 30.0
    assert result["transactions"] == []


def test_calculer_trois_participants_desequilibres(service):
    """
    3 participants déséquilibrés :
        Alice=120, Bob=60, Carol=0.01 (minimum pour exister en base)
        Part ≈ 60 — on teste la structure plutôt que les valeurs exactes.
        Carol est le débiteur (a le moins payé).
    """
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 120.0)
    _depense(service, cagnotte, "Bob",    60.0)
    _depense(service, cagnotte, "Carol",   0.01)  # 0.01 pour que Carol existe en base

    result = service.calculer(cagnotte)
    assert result["total"] > 0
    assert len(result["transactions"]) >= 1

    # Carol est débiteur (a le moins payé)
    debiteurs = [t["debiteur"] for t in result["transactions"]]
    assert "Carol" in debiteurs


def test_calculer_cas_net_trois_personnes(service):
    """
    Cas net sans virgule flottante ambiguë :
        Alice=100, Bob=50, Carol=150 → total=300, part=100
        Alice solde =   0 → ni créditeur ni débiteur (ignoré par l'algo)
        Bob   solde = -50 → débiteur
        Carol solde = +50 → créditeur
        → Bob doit 50 € à Carol (une seule transaction)
    """
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 100.0)
    _depense(service, cagnotte, "Bob",    50.0)
    _depense(service, cagnotte, "Carol", 150.0)

    result = service.calculer(cagnotte)
    assert result["total"] == 300.0
    assert result["part"]  == 100.0
    assert len(result["transactions"]) == 1

    t = result["transactions"][0]
    assert t["debiteur"]  == "Bob"
    assert t["crediteur"] == "Carol"
    assert t["montant"]   == 50.0


def test_calculer_par_participant_tri_decroissant(service):
    """par_participant est trié par montant décroissant (pour les barres de répartition)."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Bob",   10.0)
    _depense(service, cagnotte, "Alice", 80.0)
    _depense(service, cagnotte, "Carol", 40.0)

    result  = service.calculer(cagnotte)
    totaux  = [p["total"] for p in result["par_participant"]]
    assert totaux == sorted(totaux, reverse=True)


def test_calculer_plusieurs_depenses_meme_participant(service):
    """Les dépenses multiples d'un même participant sont bien agrégées.
    Alice : 30 + 70 = 100. Bob : 40.
    total = 140, part = 70 → Alice +30, Bob -30 → Bob doit 30 à Alice."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 30.0)
    _depense(service, cagnotte, "Alice", 70.0)  # total Alice = 100
    _depense(service, cagnotte, "Bob",   40.0)

    result = service.calculer(cagnotte)
    assert result["total"] == 140.0
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["debiteur"]  == "Bob"
    assert result["transactions"][0]["crediteur"] == "Alice"
    assert result["transactions"][0]["montant"]   == 30.0


# ══════════════════════════════════════════════════════════════════════════
# 4. Participants
# ══════════════════════════════════════════════════════════════════════════

def test_participants_depuis_depenses(service):
    """Les participants apparaissent automatiquement depuis les dépenses
    via SELECT DISTINCT (get_participants fusionne JSON + dépenses existantes)."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 30.0)
    _depense(service, cagnotte, "Bob",   20.0)

    participants = service.get_participants(cagnotte)
    assert "Alice" in participants
    assert "Bob"   in participants


def test_maj_participants_fixes(service):
    """Enregistrer des participants fixes → ils restent disponibles pour
    l'autocomplétion même sans dépense associée."""
    cagnotte = _setup(service)
    service.maj_participants(cagnotte, ["Alice", "Bob", "Carol"])

    participants = service.get_participants(cagnotte)
    assert "Alice" in participants
    assert "Carol" in participants


# ══════════════════════════════════════════════════════════════════════════
# 5. Import CSV (couche domaine)
#    Note : importer_depenses_csv ne met PAS à jour la colonne JSON des
#    participants (trade-off performance pour l'import en masse).
#    get_participants() les retrouve quand même via lister_depenses().
# ══════════════════════════════════════════════════════════════════════════

def test_importer_depenses_csv(service):
    """importer_depenses_csv → retourne le nombre importé et les données sont en base."""
    cagnotte = _setup(service)
    lignes = [
        {"participant": "Alice", "montant": 30.0, "date": "01/06/2025",
         "libelle": "Courses"},
        {"participant": "Bob",   "montant": 20.0, "date": "02/06/2025",
         "libelle": "Transport"},
    ]

    nb = service.importer_depenses_csv(cagnotte, lignes)
    assert nb == 2
    assert len(service.lister_depenses(cagnotte)) == 2


def test_importer_depenses_csv_participants_visibles(service):
    """Après import CSV, les participants sont récupérables via get_participants
    (les dépenses importées alimentent le SELECT DISTINCT)."""
    cagnotte = _setup(service)
    lignes = [
        {"participant": "Dupont", "montant": 50.0, "date": None, "libelle": None},
    ]
    service.importer_depenses_csv(cagnotte, lignes)

    participants = service.get_participants(cagnotte)
    assert "Dupont" in participants


def test_importer_depenses_csv_vide(service):
    """Importer une liste vide → 0 dépenses ajoutées."""
    cagnotte = _setup(service)
    nb = service.importer_depenses_csv(cagnotte, [])
    assert nb == 0
    assert service.lister_depenses(cagnotte) == []


# ══════════════════════════════════════════════════════════════════════════
# 6. Création de cagnotte — contrat du retour booléen
# ══════════════════════════════════════════════════════════════════════════

def test_creer_cagnotte_retourne_true(service):
    """creer_cagnotte renvoie True quand la création réussit."""
    result = service.creer_cagnotte("Nouvelle", "desc")
    assert result is True


def test_creer_cagnotte_doublon_retourne_false(service):
    """creer_cagnotte renvoie False si le nom existe déjà."""
    service.creer_cagnotte("Doublon", "première fois")
    result = service.creer_cagnotte("Doublon", "deuxième fois")
    assert result is False


def test_creer_cagnotte_doublon_ne_cree_pas_de_double(service):
    """Une deuxième tentative avec le même nom n'ajoute pas d'entrée en base."""
    service.creer_cagnotte("Doublon", "")
    service.creer_cagnotte("Doublon", "")
    cagnottes = [c for c in service.lister_cagnottes() if c.nom == "Doublon"]
    assert len(cagnottes) == 1


# ══════════════════════════════════════════════════════════════════════════
# 7. Persistance des participants (autocomplétion)
#    La liste JSON dans la colonne `participants` garde la mémoire des
#    contributeurs SAUF si toutes leurs dépenses sont supprimées
#    (_nettoyer_participants compare JSON vs SELECT DISTINCT).
# ══════════════════════════════════════════════════════════════════════════

def test_ajouter_depense_enregistre_participant(service):
    """Ajouter une dépense → le participant est mémorisé dans la colonne JSON."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Nadia", 50.0, "01/06/2025")

    participants = service.get_participants(cagnotte)
    assert "Nadia" in participants


def test_participant_non_duplique_dans_colonne(service):
    """Deux dépenses du même participant → il n'apparaît qu'une fois
    (dict.fromkeys préserve l'ordre et déduplique en O(n))."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Luca", 30.0, "01/06/2025")
    service.ajouter_depense(cagnotte, "Luca", 20.0, "02/06/2025")

    participants = service.get_participants(cagnotte)
    assert participants.count("Luca") == 1


def test_participants_retires_apres_suppression_depenses(service):
    """
    Supprimer TOUTES les dépenses d'un participant → il quitte l'autocomplétion.

    _nettoyer_participants() dans data.py compare la liste JSON avec les
    participants encore présents en base (SELECT DISTINCT participant) et
    retire ceux qui n'ont plus de dépense associée.
    """
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Marco", 40.0, "01/06/2025")
    service.supprimer_depenses_par_indices(cagnotte, [0])

    participants = service.get_participants(cagnotte)
    assert "Marco" not in participants


# ══════════════════════════════════════════════════════════════════════════
# 8. Remboursements
#    La signature est de la forme "debiteur|crediteur|montant".
#    Elle est générée par calculer() et stockée dans la table remboursement.
#    toggle_remboursement insère ou inverse l'état effectue (upsert).
# ══════════════════════════════════════════════════════════════════════════

def test_toggle_remboursement_true(service):
    """Premier toggle → True (remboursement marqué effectué)."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 60.0)
    _depense(service, cagnotte, "Bob",   30.0)

    calcul = service.calculer(cagnotte)
    assert len(calcul["transactions"]) >= 1
    sig = calcul["transactions"][0]["signature"]

    result = service.toggle_remboursement(cagnotte, sig)
    assert result is True


def test_toggle_remboursement_false(service):
    """Double toggle → retourne False (annule le remboursement)."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 60.0)
    _depense(service, cagnotte, "Bob",   30.0)

    calcul = service.calculer(cagnotte)
    sig    = calcul["transactions"][0]["signature"]

    service.toggle_remboursement(cagnotte, sig)           # → True
    result = service.toggle_remboursement(cagnotte, sig)  # → False
    assert result is False


def test_remboursement_effectue_dans_calcul(service):
    """Après toggle, la transaction est marquée effectue=True dans calculer().
    calculer() joint la table remboursement pour lire l'état persisté."""
    cagnotte = _setup(service)
    _depense(service, cagnotte, "Alice", 60.0)
    _depense(service, cagnotte, "Bob",   30.0)

    sig = service.calculer(cagnotte)["transactions"][0]["signature"]
    service.toggle_remboursement(cagnotte, sig)

    calcul = service.calculer(cagnotte)
    assert calcul["transactions"][0]["effectue"] is True


def test_toggle_remboursement_signature_invalide(service):
    """Toggle avec une signature arbitraire → l'insère quand même (True).
    Il n'y a pas de validation de la signature côté domaine : toute chaîne
    est acceptée comme clé de la table remboursement."""
    cagnotte = _setup(service)
    result = service.toggle_remboursement(cagnotte, "Bob|Alice|99.0")
    assert result is True


# ══════════════════════════════════════════════════════════════════════════
# 9. get_depense
# ══════════════════════════════════════════════════════════════════════════

def test_get_depense_retourne_dto(service):
    """get_depense(id) renvoie un DepenseDTO avec les bons champs."""
    cagnotte = _setup(service)
    service.ajouter_depense(cagnotte, "Claire", 77.0, "10/06/2025", libelle="Repas")

    dep = service.lister_depenses(cagnotte)[0]
    dto = service.get_depense(dep.id)
    assert dto is not None
    assert dto.participant == "Claire"
    assert dto.montant     == 77.0
    assert dto.libelle     == "Repas"


def test_get_depense_inexistante_retourne_none(service):
    """get_depense(id_inconnu) renvoie None (pas d'exception)."""
    assert service.get_depense(9999) is None