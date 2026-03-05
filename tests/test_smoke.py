"""
tests/test_smoke.py
─────────────────────────────────────────────────────────────────────────────
Smoke tests : vérifient que les routes HTTP répondent correctement.

On ne teste PAS la logique métier ici (→ voir test_domain.py).
On vérifie que :
  - Les pages s'affichent sans planter (200)
  - Les actions POST redirigent bien (302) — pattern PRG
  - Les exports ont le bon Content-Type
  - Les endpoints JSON (AJAX) répondent avec le bon format

Toutes les fixtures viennent de conftest.py (client, reset_db autouse).

Organisation :
    1. Page d'accueil
    2. Création de cagnotte
    3. Ajout de dépense
    4. Suppression de dépenses
    5. Suppression de cagnottes (simple + multiple)
    6. Export CSV
    7. Import CSV
    8. Routes JSON / AJAX (modal édition, toggle remboursement)
    9. Pages de détail (overview, équilibre, ajout)
─────────────────────────────────────────────────────────────────────────────
"""

import io


# ── Helpers ───────────────────────────────────────────────────────────────
# Fonctions utilitaires pour éviter la répétition dans les tests.
# Convention :
#   - Sans suffixe  → follow_redirects=False → on teste le 302
#   - Suffixe _f    → follow_redirects=True  → on consomme les messages flash
#                                               et on obtient la page finale


def _creer_cagnotte(client, nom="Vacances", description="Test"):
    """POST création cagnotte SANS suivre la redirection → pour tester le 302."""
    return client.post(
        "/cagnotte/create",
        data={"nom": nom, "description": description},
        follow_redirects=False,
    )


def _creer_cagnotte_f(client, nom="Vacances", description="Test"):
    """POST création cagnotte EN suivant la redirection → consomme le flash.
    À utiliser quand l'assertion porte sur la page finale et non sur le 302."""
    return client.post(
        "/cagnotte/create",
        data={"nom": nom, "description": description},
        follow_redirects=True,
    )


def _ajouter_depense(client, nom_cagnotte, participant="Alice", montant="30.00"):
    """POST ajout dépense SANS suivre la redirection → pour tester le 302."""
    return client.post(
        f"/cagnotte/{nom_cagnotte}/depense",
        data={
            "participant": participant,
            "montant":     montant,
            "date":        "2025-06-15",
            "libelle":     "Test dépense",
        },
        follow_redirects=False,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Page d'accueil
# ══════════════════════════════════════════════════════════════════════════

def test_home_retourne_200(client):
    """GET / → 200 OK."""
    resp = client.get("/")
    assert resp.status_code == 200


def test_home_contient_titre(client):
    """La page d'accueil mentionne 'Archilog'."""
    resp = client.get("/")
    assert b"Archilog" in resp.data


def test_home_liste_vide_par_defaut(client):
    """Aucune cagnotte au départ (base vide)."""
    resp = client.get("/")
    assert b"Aucune cagnotte" in resp.data or b"0" in resp.data


# ══════════════════════════════════════════════════════════════════════════
# 2. Création de cagnotte
# ══════════════════════════════════════════════════════════════════════════

def test_create_cagnotte_redirige(client):
    """POST /cagnotte/create → 302 redirect (pattern PRG)."""
    resp = _creer_cagnotte(client)
    assert resp.status_code == 302


def test_create_cagnotte_redirige_vers_home(client):
    """La redirection après création pointe vers /."""
    resp = _creer_cagnotte(client)
    assert resp.headers["Location"].endswith("/")


def test_create_cagnotte_visible_sur_home(client):
    """Après création, la cagnotte apparaît sur la page d'accueil."""
    _creer_cagnotte(client, nom="WeekEnd Ski")
    resp = client.get("/")
    assert b"WeekEnd Ski" in resp.data


def test_create_cagnotte_nom_vide_ne_plante_pas(client):
    """POST avec nom vide → redirection sans 500 (validation côté serveur)."""
    resp = client.post(
        "/cagnotte/create",
        data={"nom": "", "description": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_create_cagnotte_doublon_redirige(client):
    """Créer deux fois le même nom → 302 (pas de crash, flash d'erreur)."""
    _creer_cagnotte(client, nom="Doublon")
    resp = _creer_cagnotte(client, nom="Doublon")
    assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════════════════
# 3. Ajout de dépense
# ══════════════════════════════════════════════════════════════════════════

def test_ajouter_depense_redirige(client):
    """POST dépense → 302 vers /depenses."""
    _creer_cagnotte(client, nom="Voyage")
    resp = _ajouter_depense(client, "Voyage")
    assert resp.status_code == 302
    assert "depenses" in resp.headers["Location"]


def test_ajouter_depense_montant_invalide_ne_plante_pas(client):
    """Montant non-numérique → 302 sans crash serveur (rejeté par _parse_montant)."""
    _creer_cagnotte(client, nom="Voyage")
    resp = client.post(
        "/cagnotte/Voyage/depense",
        data={"participant": "Bob", "montant": "pas_un_nombre", "date": "2025-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_ajouter_plusieurs_depenses_affiches(client):
    """3 dépenses ajoutées → toutes visibles dans la liste."""
    _creer_cagnotte(client, nom="Trip")
    _ajouter_depense(client, "Trip", "Alice", "50.00")
    _ajouter_depense(client, "Trip", "Bob",   "30.00")
    _ajouter_depense(client, "Trip", "Alice", "20.00")

    resp = client.get("/cagnotte/Trip/depenses")
    assert resp.status_code == 200
    assert b"Alice" in resp.data
    assert b"Bob"   in resp.data


def test_ajouter_depense_montant_zero_ne_plante_pas(client):
    """Montant à 0 → 302 (rejeté silencieusement par la vue, min=0.01)."""
    _creer_cagnotte(client, nom="TestZero")
    resp = client.post(
        "/cagnotte/TestZero/depense",
        data={"participant": "Alice", "montant": "0", "date": "2025-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════════════════
# 4. Suppression de dépenses
# ══════════════════════════════════════════════════════════════════════════

def test_supprimer_une_depense(client):
    """DELETE index 0 → 302."""
    _creer_cagnotte(client, nom="Fete")
    _ajouter_depense(client, "Fete", "Alice", "60.00")

    resp = client.post(
        "/cagnotte/Fete/depenses/delete",
        data={"indices": "0"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_supprimer_depense_inexistante_ne_plante_pas(client):
    """Supprimer un indice hors limites → 302 sans crash (ignoré silencieusement)."""
    _creer_cagnotte(client, nom="Vide2")
    resp = client.post(
        "/cagnotte/Vide2/depenses/delete",
        data={"indices": "99"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════════════════
# 5. Suppression de cagnottes
# ══════════════════════════════════════════════════════════════════════════

def test_supprimer_cagnotte(client):
    """POST /delete → 302 vers /."""
    _creer_cagnotte(client, nom="ASupprimer")
    resp = client.post("/cagnotte/ASupprimer/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_supprimer_cagnotte_avec_depenses(client):
    """Supprimer une cagnotte qui contient des dépenses → 302, pas de crash.
    La suppression en cascade est gérée par ON DELETE CASCADE en SQL."""
    _creer_cagnotte(client, nom="AvecDep")
    _ajouter_depense(client, "AvecDep", "Alice", "50.00")

    resp = client.post("/cagnotte/AvecDep/delete", follow_redirects=False)
    assert resp.status_code == 302


def test_supprimer_cagnotte_disparait_de_home(client):
    """Après suppression, la cagnotte ne s'affiche plus sur /."""
    _creer_cagnotte(client, nom="Fantome")
    client.post("/cagnotte/Fantome/delete", follow_redirects=True)

    resp = client.get("/")
    assert b"Fantome" not in resp.data


def test_confirm_delete_page(client):
    """GET /confirm-delete → 200 avec formulaire de confirmation."""
    _creer_cagnotte(client, nom="AConfirmer")
    resp = client.get("/cagnotte/AConfirmer/confirm-delete")
    assert resp.status_code == 200
    assert b"AConfirmer" in resp.data


def test_confirm_delete_multiple_page(client):
    """GET /confirm-delete-multiple?noms=... → 200 avec liste des noms."""
    _creer_cagnotte(client, nom="C1")
    _creer_cagnotte(client, nom="C2")
    resp = client.get("/cagnottes/confirm-delete-multiple?noms=C1,C2")
    assert resp.status_code == 200
    assert b"C1" in resp.data
    assert b"C2" in resp.data


def test_confirm_delete_multiple_sans_noms_redirige(client):
    """GET /confirm-delete-multiple sans noms → redirige vers / (garde-fou)."""
    resp = client.get("/cagnottes/confirm-delete-multiple?noms=", follow_redirects=False)
    assert resp.status_code == 302


def test_supprimer_multiple_cagnottes(client):
    """POST /delete-multiple → supprime toutes les cagnottes listées."""
    _creer_cagnotte(client, nom="Multi1")
    _creer_cagnotte(client, nom="Multi2")

    resp = client.post(
        "/cagnottes/delete-multiple",
        data={"noms": "Multi1,Multi2"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    resp2 = client.get("/")
    assert b"Multi1" not in resp2.data
    assert b"Multi2" not in resp2.data


# ══════════════════════════════════════════════════════════════════════════
# 6. Export CSV
# ══════════════════════════════════════════════════════════════════════════

def test_export_csv_status_200(client):
    """GET export.csv → 200."""
    _creer_cagnotte(client, nom="Export")
    _ajouter_depense(client, "Export", "Alice", "15.00")

    resp = client.get("/cagnotte/Export/export.csv")
    assert resp.status_code == 200


def test_export_csv_content_type(client):
    """L'export a bien un Content-Type text/csv."""
    _creer_cagnotte(client, nom="Export")
    _ajouter_depense(client, "Export", "Bob", "25.00")

    resp = client.get("/cagnotte/Export/export.csv")
    assert "text/csv" in resp.content_type


def test_export_csv_contient_les_donnees(client):
    """Le CSV exporté contient participant et montant."""
    _creer_cagnotte(client, nom="Export")
    _ajouter_depense(client, "Export", "Charlie", "42.00")

    resp  = client.get("/cagnotte/Export/export.csv")
    texte = resp.data.decode("utf-8")
    assert "Charlie" in texte
    assert "42.0"    in texte


def test_export_csv_cagnotte_vide(client):
    """Export d'une cagnotte sans dépense → 200 avec juste l'en-tête CSV."""
    _creer_cagnotte(client, nom="Vide")
    resp = client.get("/cagnotte/Vide/export.csv")
    assert resp.status_code == 200
    assert b"Participant" in resp.data   # au moins l'en-tête


def test_export_csv_contient_entete(client):
    """Le CSV exporté commence par les colonnes attendues."""
    _creer_cagnotte(client, nom="ExportHeader")
    resp = client.get("/cagnotte/ExportHeader/export.csv")
    texte = resp.data.decode("utf-8")
    assert "Participant" in texte
    assert "Montant"     in texte


# ══════════════════════════════════════════════════════════════════════════
# 7. Import CSV
# ══════════════════════════════════════════════════════════════════════════

def test_import_csv_valide(client):
    """Import d'un CSV bien formé → 302."""
    _creer_cagnotte(client, nom="Import")

    csv_bytes = (
        "participant;montant;date;libelle\n"
        "Alice;50.00;15/06/2025;Restaurant\n"
        "Bob;30.00;16/06/2025;Transport\n"
    ).encode("utf-8")

    # io.BytesIO simule un fichier uploadé sans écrire sur disque.
    resp = client.post(
        "/cagnotte/Import/import-csv",
        data={"csv_file": (io.BytesIO(csv_bytes), "depenses.csv")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_import_csv_donnees_en_base(client):
    """Après import, les dépenses sont bien visibles dans la liste."""
    _creer_cagnotte(client, nom="Import")

    csv_bytes = (
        "participant;montant\n"
        "Dupont;99.00\n"
    ).encode("utf-8")

    client.post(
        "/cagnotte/Import/import-csv",
        data={"csv_file": (io.BytesIO(csv_bytes), "f.csv")},
        content_type="multipart/form-data",
    )

    resp = client.get("/cagnotte/Import/depenses")
    assert b"Dupont" in resp.data


def test_import_csv_sans_fichier_ne_plante_pas(client):
    """POST sans fichier → 302 sans crash (garde-fou côté serveur)."""
    _creer_cagnotte(client, nom="Import2")
    resp = client.post(
        "/cagnotte/Import2/import-csv",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_import_csv_separateur_virgule(client):
    """Import avec séparateur virgule (auto-détecté via comptage) → 302."""
    _creer_cagnotte(client, nom="ImportVirgule")

    csv_bytes = (
        "participant,montant,libelle\n"
        "Alice,25.00,Test\n"
    ).encode("utf-8")

    resp = client.post(
        "/cagnotte/ImportVirgule/import-csv",
        data={"csv_file": (io.BytesIO(csv_bytes), "f.csv")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_import_csv_page_affichage(client):
    """GET /import-csv → page affichée correctement (formulaire + exemple)."""
    _creer_cagnotte(client, nom="ImportPage")
    resp = client.get("/cagnotte/ImportPage/import-csv")
    assert resp.status_code == 200
    assert b"CSV" in resp.data


# ══════════════════════════════════════════════════════════════════════════
# 8. Routes JSON / AJAX
#    Ces endpoints sont consommés par depenses.js et main.js — ils ne sont
#    jamais visités directement par l'utilisateur via le navigateur.
# ══════════════════════════════════════════════════════════════════════════

def test_get_depense_json_not_found(client):
    """GET /depense/999/json → 404 JSON avec champ 'error'."""
    _creer_cagnotte(client, nom="Test")
    resp = client.get("/cagnotte/Test/depense/999/json")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json()["error"] == "not found"


def test_get_depense_json_existante(client):
    """GET /depense/<id>/json → 200 avec les bons champs."""
    _creer_cagnotte(client, nom="Test")
    _ajouter_depense(client, "Test", "Alice", "30.00")

    resp = client.get("/cagnotte/Test/depense/1/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["participant"] == "Alice"
    assert data["montant"]     == 30.0


def test_update_depense_ajax_ok(client):
    """POST /update → 200 JSON avec ok=True et champs mis à jour."""
    _creer_cagnotte(client, nom="Ajax")
    _ajouter_depense(client, "Ajax", "Alice", "30.00")

    resp = client.post(
        "/cagnotte/Ajax/depense/1/update",
        data={
            "participant": "Bob",
            "montant":     "55.00",
            "date":        "2025-07-01",
            "libelle":     "Modifié",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"]          is True
    assert data["participant"] == "Bob"
    assert data["montant"]     == 55.0


def test_update_depense_ajax_not_found(client):
    """POST /update sur id inexistant → 404 JSON."""
    _creer_cagnotte(client, nom="Ajax2")
    resp = client.post(
        "/cagnotte/Ajax2/depense/999/update",
        data={"participant": "Bob", "montant": "10.00", "date": "2025-01-01"},
    )
    assert resp.status_code == 404
    assert resp.is_json


def test_update_depense_ajax_montant_invalide(client):
    """POST /update avec montant non-numérique → 400 JSON."""
    _creer_cagnotte(client, nom="Ajax3")
    _ajouter_depense(client, "Ajax3", "Alice", "20.00")

    resp = client.post(
        "/cagnotte/Ajax3/depense/1/update",
        data={"participant": "Alice", "montant": "abc", "date": "2025-01-01"},
    )
    assert resp.status_code == 400
    assert resp.is_json


def test_toggle_remboursement_ajax(client):
    """POST /remboursement/toggle → JSON avec effectue + nb_effectues."""
    _creer_cagnotte(client, nom="Toggle")
    _ajouter_depense(client, "Toggle", "Alice", "60.00")
    _ajouter_depense(client, "Toggle", "Bob",   "30.00")

    # On récupère la signature depuis la couche domaine directement :
    # évite de parser le HTML de la page équilibre dans un smoke test.
    from archilog.domain import CagnotteService
    svc    = CagnotteService()
    calcul = svc.calculer("Toggle")
    sig    = calcul["transactions"][0]["signature"]

    resp = client.post(
        "/cagnotte/Toggle/remboursement/toggle",
        data={"signature": sig},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "effectue"     in data
    assert "nb_effectues" in data
    assert data["effectue"] is True


def test_toggle_remboursement_ajax_signature_manquante(client):
    """POST /toggle sans signature → 400 JSON (champ obligatoire)."""
    _creer_cagnotte(client, nom="Toggle2")
    resp = client.post("/cagnotte/Toggle2/remboursement/toggle", data={})
    assert resp.status_code == 400
    assert resp.is_json


# ══════════════════════════════════════════════════════════════════════════
# 9. Pages de détail (overview, équilibre, ajout)
# ══════════════════════════════════════════════════════════════════════════

def test_page_overview_200(client):
    """GET /cagnotte/<nom> → 200."""
    _creer_cagnotte(client, nom="Overview")
    resp = client.get("/cagnotte/Overview")
    assert resp.status_code == 200
    assert b"Overview" in resp.data


def test_page_equilibre_200(client):
    """GET /cagnotte/<nom>/equilibre → 200."""
    _creer_cagnotte(client, nom="Equilibre")
    _ajouter_depense(client, "Equilibre", "Alice", "60.00")
    _ajouter_depense(client, "Equilibre", "Bob",   "30.00")

    resp = client.get("/cagnotte/Equilibre/equilibre")
    assert resp.status_code == 200
    assert b"Equilibre" in resp.data


def test_page_equilibre_vide_200(client):
    """GET /equilibre sur une cagnotte vide → 200 sans crash."""
    _creer_cagnotte(client, nom="EquilibreVide")
    resp = client.get("/cagnotte/EquilibreVide/equilibre")
    assert resp.status_code == 200


def test_page_ajouter_200(client):
    """GET /cagnotte/<nom>/ajouter → 200."""
    _creer_cagnotte(client, nom="Ajouter")
    resp = client.get("/cagnotte/Ajouter/ajouter")
    assert resp.status_code == 200


def test_page_new_cagnotte_200(client):
    """GET /cagnotte/new → 200."""
    resp = client.get("/cagnotte/new")
    assert resp.status_code == 200


def test_save_participants(client):
    """POST /participants → 302 (mise à jour liste d'autocomplétion)."""
    _creer_cagnotte(client, nom="Parts")
    resp = client.post(
        "/cagnotte/Parts/participants",
        data={"participants": "Alice, Bob, Carol"},
        follow_redirects=False,
    )
    assert resp.status_code == 302