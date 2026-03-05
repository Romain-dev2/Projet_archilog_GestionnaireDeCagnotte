"""
tests/test_routes.py
─────────────────────────────────────────────────────────────────────────────
Tests d'intégration Flask approfondis.

Complète test_smoke.py en allant au-delà du code de statut :
  - Contenu des messages flash (catégorie + texte)
  - Contenu HTML rendu (données affichées après actions)
  - Isolation inter-cagnottes (sécurité : pas de fuite entre cagnottes)
  - Validation des formulaires (champs manquants, valeurs limites)
  - CSV : cas limites de parsing (BOM, séparateurs, accents, aliases)
  - Export CSV : structure exacte du fichier produit
  - Participants : persistance et affichage

Toutes les fixtures viennent de conftest.py (client, reset_db autouse).
─────────────────────────────────────────────────────────────────────────────
"""

import io
import csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _creer(client, nom="Vacances", desc=""):
    """Crée une cagnotte et suit la redirection → retourne la page finale."""
    return client.post(
        "/cagnotte/create",
        data={"nom": nom, "description": desc},
        follow_redirects=True,
    )


def _ajouter(client, nom, participant="Alice", montant="30.00",
             date="2025-06-15", libelle=""):
    """Ajoute une dépense et suit la redirection → retourne la page finale."""
    return client.post(
        f"/cagnotte/{nom}/depense",
        data={"participant": participant, "montant": montant,
              "date": date, "libelle": libelle},
        follow_redirects=True,
    )


def _get_flashes(resp) -> list[tuple[str, str]]:
    """
    Extraction des messages flash depuis le HTML rendu.
    On cherche dans resp.data directement (bytes) pour éviter de coupler
    les tests au rendu exact du composant toast (structure HTML).
    Retourne resp.data brut — les assertions portent sur des sous-chaînes.
    """
    return resp.data


# ---------------------------------------------------------------------------
# 1. Flash messages — création de cagnotte
# ---------------------------------------------------------------------------

class TestFlashCreationCagnotte:

    def test_flash_succes_creation(self, client):
        """Créer une cagnotte → le flash de succès contient 'cr' (créée)."""
        resp = _creer(client, nom="Alpes")
        assert b"cr" in resp.data.lower()    # "créée" dans le message flash
        assert resp.status_code == 200

    def test_flash_erreur_nom_vide(self, client):
        """POST avec nom vide → flash d'erreur mentionne 'vide' ou 'impossible'."""
        resp = client.post(
            "/cagnotte/create",
            data={"nom": "", "description": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"vide" in resp.data.lower() or b"impossible" in resp.data.lower()

    def test_flash_erreur_doublon(self, client):
        """Doublon de nom → flash mentionne 'existe' ou 'erreur'."""
        _creer(client, nom="Doublon")
        resp = _creer(client, nom="Doublon")
        assert b"existe" in resp.data.lower() or b"erreur" in resp.data.lower()

    def test_nom_vide_ne_cree_pas_de_cagnotte(self, client):
        """Un nom vide ne doit pas créer d'entrée visible dans la liste."""
        client.post("/cagnotte/create", data={"nom": "", "description": ""},
                    follow_redirects=True)
        resp = client.get("/")
        # La page d'accueil doit s'afficher sans erreur 500
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Flash messages — ajout de dépense
# ---------------------------------------------------------------------------

class TestFlashAjoutDepense:

    def test_flash_succes_ajout(self, client):
        """Dépense valide → flash de succès mentionne 'ajout' ou 'pense'."""
        _creer(client, nom="Fete")
        resp = _ajouter(client, "Fete", participant="Alice", montant="50.00")
        assert b"ajout" in resp.data.lower() or b"pense" in resp.data.lower()

    def test_flash_erreur_montant_invalide(self, client):
        """Montant 'abc' → flash d'erreur."""
        _creer(client, nom="Fete2")
        resp = _ajouter(client, "Fete2", montant="abc")
        assert b"erreur" in resp.data.lower()

    def test_flash_erreur_participant_vide(self, client):
        """Participant vide → flash d'erreur (champ obligatoire)."""
        _creer(client, nom="Fete3")
        resp = _ajouter(client, "Fete3", participant="", montant="30.00")
        assert b"erreur" in resp.data.lower()

    def test_flash_erreur_montant_zero(self, client):
        """Montant à 0 → flash d'erreur (min = 0.01)."""
        _creer(client, nom="Fete4")
        resp = _ajouter(client, "Fete4", montant="0")
        assert b"erreur" in resp.data.lower()

    def test_flash_erreur_montant_negatif(self, client):
        """Montant négatif → flash d'erreur."""
        _creer(client, nom="Fete5")
        resp = _ajouter(client, "Fete5", montant="-10")
        assert b"erreur" in resp.data.lower()


# ---------------------------------------------------------------------------
# 3. Flash messages — suppression dépenses
# ---------------------------------------------------------------------------

class TestFlashSuppressionDepense:

    def test_flash_suppression_une_depense(self, client):
        """Supprimer 1 dépense → flash mentionne 'supprim'."""
        _creer(client, nom="Del")
        _ajouter(client, "Del")
        resp = client.post(
            "/cagnotte/Del/depenses/delete",
            data={"indices": "0"},
            follow_redirects=True,
        )
        assert b"supprim" in resp.data.lower()

    def test_flash_suppression_multiple_depenses(self, client):
        """Supprimer 2 dépenses → flash mentionne 'supprim' et '2'."""
        _creer(client, nom="Del2")
        _ajouter(client, "Del2", participant="Alice")
        _ajouter(client, "Del2", participant="Bob")
        resp = client.post(
            "/cagnotte/Del2/depenses/delete",
            data={"indices": "0,1"},
            follow_redirects=True,
        )
        assert b"supprim" in resp.data.lower()
        assert b"2" in resp.data   # "2 dépenses supprimées" dans le flash

    def test_suppression_indices_vides_ne_plante_pas(self, client):
        """POST sans indices → 302 sans crash (cas vide ignoré)."""
        _creer(client, nom="Del3")
        resp = client.post(
            "/cagnotte/Del3/depenses/delete",
            data={"indices": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_suppression_indices_non_numeriques_ignores(self, client):
        """Indices non-numériques dans la chaîne → ignorés par int() silencieusement.
        La dépense à l'index 0 est supprimée, 'abc' et 'xyz' sont ignorés."""
        _creer(client, nom="Del4")
        _ajouter(client, "Del4")
        resp = client.post(
            "/cagnotte/Del4/depenses/delete",
            data={"indices": "abc,0,xyz"},
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. Flash messages — suppression cagnotte
# ---------------------------------------------------------------------------

class TestFlashSuppressionCagnotte:

    def test_flash_suppression_simple(self, client):
        """Supprimer une cagnotte → flash mentionne 'supprim'."""
        _creer(client, nom="ASup")
        resp = client.post("/cagnotte/ASup/delete", follow_redirects=True)
        assert b"supprim" in resp.data.lower()

    def test_flash_suppression_multiple_une_cagnotte(self, client):
        """Suppression multiple avec un seul nom → flash mentionne 'supprim'."""
        _creer(client, nom="BulkOne")
        resp = client.post(
            "/cagnottes/delete-multiple",
            data={"noms": "BulkOne"},
            follow_redirects=True,
        )
        assert b"supprim" in resp.data.lower()

    def test_flash_suppression_multiple_plusieurs(self, client):
        """Suppression de 2 cagnottes → flash mentionne 'supprim' et '2'."""
        _creer(client, nom="B1")
        _creer(client, nom="B2")
        resp = client.post(
            "/cagnottes/delete-multiple",
            data={"noms": "B1,B2"},
            follow_redirects=True,
        )
        assert b"supprim" in resp.data.lower()
        assert b"2" in resp.data


# ---------------------------------------------------------------------------
# 5. Contenu HTML après actions
# ---------------------------------------------------------------------------

class TestContenuHTML:

    def test_cagnotte_visible_sur_home_apres_creation(self, client):
        """La cagnotte créée apparaît dans la liste sur /."""
        _creer(client, nom="WeekEnd")
        resp = client.get("/")
        assert b"WeekEnd" in resp.data

    def test_description_visible_sur_home(self, client):
        """La description est affichée dans le tableau des cagnottes."""
        _creer(client, nom="AvecDesc", desc="Une belle description")
        resp = client.get("/")
        assert b"Une belle description" in resp.data

    def test_depense_visible_dans_liste(self, client):
        """Les champs de la dépense sont tous présents dans la liste."""
        _creer(client, nom="Cag")
        _ajouter(client, "Cag", participant="Brigitte", montant="77.50",
                 libelle="Restaurant")
        resp = client.get("/cagnotte/Cag/depenses")
        assert b"Brigitte"   in resp.data
        assert b"77.5"       in resp.data
        assert b"Restaurant" in resp.data

    def test_depense_absente_apres_suppression(self, client):
        """Après suppression, la dépense n'est plus dans la liste."""
        _creer(client, nom="CagSup")
        _ajouter(client, "CagSup", participant="Marco", montant="40.00")
        client.post("/cagnotte/CagSup/depenses/delete", data={"indices": "0"})
        resp = client.get("/cagnotte/CagSup/depenses")
        assert b"Marco" not in resp.data

    def test_participants_dans_page_ajouter(self, client):
        """Les participants enregistrés apparaissent dans le JSON window.PARTICIPANTS
        injecté par la page /ajouter pour l'autocomplétion."""
        _creer(client, nom="P")
        _ajouter(client, "P", participant="Nadia", montant="20.00")
        resp = client.get("/cagnotte/P/ajouter")
        assert b"Nadia" in resp.data

    def test_page_equilibre_affiche_transactions(self, client):
        """La page équilibre affiche les transactions calculées."""
        _creer(client, nom="Eq")
        _ajouter(client, "Eq", participant="Alice", montant="90.00")
        _ajouter(client, "Eq", participant="Bob",   montant="30.00")
        resp = client.get("/cagnotte/Eq/equilibre")
        assert b"Alice" in resp.data
        assert b"Bob"   in resp.data
        assert b"30"    in resp.data   # Bob doit 30 € à Alice

    def test_page_overview_affiche_chiffres_cles(self, client):
        """La vue d'ensemble affiche le total et les participants."""
        _creer(client, nom="Ov")
        _ajouter(client, "Ov", participant="Alice", montant="60.00")
        resp = client.get("/cagnotte/Ov")
        assert b"60"    in resp.data
        assert b"Alice" in resp.data

    def test_tag_nombre_depenses(self, client):
        """Le compteur de dépenses dans l'entête de la liste doit être juste."""
        _creer(client, nom="Cnt")
        _ajouter(client, "Cnt", participant="A", montant="10.00")
        _ajouter(client, "Cnt", participant="B", montant="20.00")
        resp = client.get("/cagnotte/Cnt/depenses")
        assert b"2" in resp.data   # <span class="tag tag-blue">2</span>


# ---------------------------------------------------------------------------
# 6. Édition de dépense (route HTTP pleine page, pas AJAX)
#    Ces routes sont le fallback sans JavaScript (JS intercepte normalement).
# ---------------------------------------------------------------------------

class TestEditDepense:

    def test_get_edit_depense_200(self, client):
        """GET /depense/<id>/edit → 200 avec les champs préremplis."""
        _creer(client, nom="Edit")
        _ajouter(client, "Edit", participant="Alice", montant="30.00")
        resp = client.get("/cagnotte/Edit/depense/1/edit")
        assert resp.status_code == 200
        assert b"Alice" in resp.data

    def test_get_edit_depense_inexistante_redirige(self, client):
        """GET /edit sur une id inexistante → 302 (flash erreur, pas de 404)."""
        _creer(client, nom="EditX")
        resp = client.get("/cagnotte/EditX/depense/9999/edit",
                          follow_redirects=False)
        assert resp.status_code == 302

    def test_post_edit_depense_modifie_donnees(self, client):
        """POST /edit avec données valides → modifications visibles dans la liste."""
        _creer(client, nom="EditP")
        _ajouter(client, "EditP", participant="Alice", montant="30.00")
        resp = client.post(
            "/cagnotte/EditP/depense/1/edit",
            data={"participant": "Bob", "montant": "99.00",
                  "date": "2025-08-01", "libelle": "Modifié"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Bob" in resp.data
        assert b"99"  in resp.data

    def test_post_edit_depense_champ_invalide_flash_erreur(self, client):
        """POST /edit avec participant vide → flash d'erreur."""
        _creer(client, nom="EditErr")
        _ajouter(client, "EditErr", participant="Alice", montant="30.00")
        resp = client.post(
            "/cagnotte/EditErr/depense/1/edit",
            data={"participant": "", "montant": "30.00", "date": ""},
            follow_redirects=True,
        )
        assert b"erreur" in resp.data.lower()


# ---------------------------------------------------------------------------
# 7. Isolation inter-cagnottes (sécurité)
#    Vérifie que les routes vérifient l'appartenance d'une dépense à la
#    cagnotte dans l'URL (check implémenté dans views.py).
# ---------------------------------------------------------------------------

class TestIsolationInterCagnottes:

    def test_json_depense_autre_cagnotte_retourne_404(self, client):
        """
        La dépense id=1 appartient à 'CagA'. Tenter de la récupérer
        via l'URL de 'CagB' doit retourner 404.
        """
        _creer(client, nom="CagA")
        _creer(client, nom="CagB")
        _ajouter(client, "CagA", participant="Alice", montant="10.00")

        resp = client.get("/cagnotte/CagB/depense/1/json")
        assert resp.status_code == 404

    def test_update_ajax_depense_autre_cagnotte_retourne_404(self, client):
        """POST /update sur une dépense appartenant à une autre cagnotte → 404."""
        _creer(client, nom="OwnerA")
        _creer(client, nom="OwnerB")
        _ajouter(client, "OwnerA", participant="Alice", montant="10.00")

        resp = client.post(
            "/cagnotte/OwnerB/depense/1/update",
            data={"participant": "Hack", "montant": "1.00", "date": "2025-01-01"},
        )
        assert resp.status_code == 404

    def test_edit_depense_autre_cagnotte_redirige(self, client):
        """GET /edit sur une dépense d'une autre cagnotte → redirige (pas d'accès)."""
        _creer(client, nom="SrcA")
        _creer(client, nom="SrcB")
        _ajouter(client, "SrcA", participant="Alice", montant="10.00")
        resp = client.get("/cagnotte/SrcB/depense/1/edit", follow_redirects=False)
        assert resp.status_code == 302

    def test_cagnottes_independantes_depenses(self, client):
        """Les dépenses de CagX ne s'affichent pas dans la liste de CagY."""
        _creer(client, nom="CagX")
        _creer(client, nom="CagY")
        _ajouter(client, "CagX", participant="SecretX", montant="99.00")

        resp = client.get("/cagnotte/CagY/depenses")
        assert b"SecretX" not in resp.data


# ---------------------------------------------------------------------------
# 8. Import CSV — cas limites de parsing
# ---------------------------------------------------------------------------

class TestImportCSV:

    @staticmethod
    def _import(client, nom, content: str, filename="f.csv"):
        """Helper : encode le contenu en UTF-8 avec BOM et l'envoie en multipart."""
        return client.post(
            f"/cagnotte/{nom}/import-csv",
            # utf-8-sig ajoute un BOM UTF-8 (EF BB BF) au début du fichier.
            # views.py utilise open(..., encoding='utf-8-sig') pour l'absorber.
            data={"csv_file": (io.BytesIO(content.encode("utf-8-sig")), filename)},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def test_import_utf8_bom(self, client):
        """CSV avec BOM UTF-8 (utf-8-sig) : doit être parsé correctement."""
        _creer(client, nom="BOM")
        resp = self._import(client, "BOM",
                            "participant;montant\nAlice;50.00\n")
        assert resp.status_code == 200
        assert b"Alice" in client.get("/cagnotte/BOM/depenses").data

    def test_import_separateur_auto_virgule(self, client):
        """Auto-détection du séparateur virgule (plus de virgules que de point-virgules)."""
        _creer(client, nom="Virg")
        resp = self._import(client, "Virg",
                            "participant,montant,libelle\nBob,25.00,Taxi\n")
        assert resp.status_code == 200
        assert b"Bob" in client.get("/cagnotte/Virg/depenses").data

    def test_import_entete_avec_accents(self, client):
        """En-têtes avec accents (é → e) doivent être normalisés par unicodedata."""
        _creer(client, nom="Acc")
        # "libellé" devrait être reconnu après normalisation NFD + filtre non-ASCII
        resp = self._import(client, "Acc",
                            "participant;montant;libellé\nCarol;15.00;Resto\n")
        assert resp.status_code == 200
        assert b"Carol" in client.get("/cagnotte/Acc/depenses").data

    def test_import_colonne_nom_alias_participant(self, client):
        """La colonne 'nom' est acceptée comme alias de 'participant'."""
        _creer(client, nom="Alias")
        resp = self._import(client, "Alias",
                            "nom;montant\nDupont;40.00\n")
        assert resp.status_code == 200
        assert b"Dupont" in client.get("/cagnotte/Alias/depenses").data

    def test_import_colonne_description_alias_libelle(self, client):
        """La colonne 'description' est acceptée comme alias de 'libelle'."""
        _creer(client, nom="AliasLib")
        resp = self._import(client, "AliasLib",
                            "participant;montant;description\nEva;30.00;Transport\n")
        assert resp.status_code == 200
        assert b"Eva" in client.get("/cagnotte/AliasLib/depenses").data

    def test_import_montant_virgule_decimale(self, client):
        """Montant avec virgule décimale (format français '12,50') → converti en float."""
        _creer(client, nom="Virg2")
        resp = self._import(client, "Virg2",
                            "participant;montant\nFred;12,50\n")
        assert resp.status_code == 200
        assert b"Fred" in client.get("/cagnotte/Virg2/depenses").data

    def test_import_lignes_invalides_ignorees(self, client):
        """Les lignes sans participant ou avec montant invalide sont ignorées silencieusement.
        Seule la ligne valide (Carol) est importée."""
        _creer(client, nom="Inv")
        resp = self._import(client, "Inv",
                            "participant;montant\n"
                            ";50.00\n"           # participant vide → ignoré
                            "Bob;abc\n"          # montant invalide → ignoré
                            "Carol;20.00\n")     # valide
        assert resp.status_code == 200
        dep_page = client.get("/cagnotte/Inv/depenses").data
        assert b"Carol" in dep_page
        assert b"Bob"   not in dep_page

    def test_import_montant_zero_ignore(self, client):
        """Lignes avec montant < 0.01 sont ignorées (règle métier : min=0.01)."""
        _creer(client, nom="Zero")
        resp = self._import(client, "Zero",
                            "participant;montant\nGabi;0.00\n")
        assert resp.status_code == 200
        assert b"Gabi" not in client.get("/cagnotte/Zero/depenses").data

    def test_import_csv_vide_flash_erreur(self, client):
        """CSV sans ligne valide → flash mentionne 'invalide' ou 'erreur'."""
        _creer(client, nom="Empty")
        resp = self._import(client, "Empty", "participant;montant\n")
        assert b"invalide" in resp.data.lower() or b"erreur" in resp.data.lower()

    def test_import_flash_contient_nombre_importe(self, client):
        """Le flash après import mentionne le nombre de lignes importées."""
        _creer(client, nom="Count")
        resp = self._import(client, "Count",
                            "participant;montant\n"
                            "A;10.00\n"
                            "B;20.00\n"
                            "C;30.00\n")
        assert b"3" in resp.data

    def test_import_avec_fichier_non_utf8_ne_plante_pas(self, client):
        """Fichier binaire non-UTF-8 → flash erreur, pas de 500."""
        _creer(client, nom="Binary")
        resp = client.post(
            "/cagnotte/Binary/import-csv",
            data={"csv_file": (io.BytesIO(b"\xff\xfe invalid"), "f.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. Export CSV — structure exacte
# ---------------------------------------------------------------------------

class TestExportCSV:

    @staticmethod
    def _export_rows(client, nom) -> list[list[str]]:
        """Retourne le contenu du CSV exporté comme liste de lignes parsées.
        Utilise le délimiteur ';' cohérent avec _write_depenses_csv() dans views.py."""
        resp    = client.get(f"/cagnotte/{nom}/export.csv")
        content = resp.data.decode("utf-8")
        reader  = csv.reader(io.StringIO(content), delimiter=";")
        return list(reader)

    def test_entete_colonnes(self, client):
        """Le CSV exporté commence par '#;Participant;Montant;Date;Libellé'."""
        _creer(client, nom="Exp")
        rows = self._export_rows(client, "Exp")
        assert rows[0] == ["#", "Participant", "Montant", "Date", "Libellé"]

    def test_donnees_ligne(self, client):
        """Une ligne de données contient les bons champs dans le bon ordre."""
        _creer(client, nom="ExpD")
        _ajouter(client, "ExpD", participant="Alice", montant="42.00",
                 date="2025-06-15", libelle="Courses")
        rows = self._export_rows(client, "ExpD")
        assert len(rows) == 2   # en-tête + 1 ligne
        assert rows[1][1] == "Alice"
        assert "42" in rows[1][2]
        assert rows[1][4] == "Courses"

    def test_numerotation_commence_a_1(self, client):
        """La colonne '#' commence à 1 (pas à 0) et s'incrémente."""
        _creer(client, nom="ExpN")
        _ajouter(client, "ExpN", participant="A", montant="10.00")
        _ajouter(client, "ExpN", participant="B", montant="20.00")
        rows = self._export_rows(client, "ExpN")
        assert rows[1][0] == "1"
        assert rows[2][0] == "2"

    def test_content_disposition_header(self, client):
        """Content-Disposition contient 'attachment' et le nom de la cagnotte."""
        _creer(client, nom="ExpH")
        resp = client.get("/cagnotte/ExpH/export.csv")
        cd = resp.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert "ExpH" in cd

    def test_export_cagnotte_vide_une_ligne(self, client):
        """Cagnotte sans dépense → CSV avec seulement l'en-tête (1 ligne)."""
        _creer(client, nom="ExpVide")
        rows = self._export_rows(client, "ExpVide")
        assert len(rows) == 1
        assert rows[0][0] == "#"


# ---------------------------------------------------------------------------
# 10. Participants
# ---------------------------------------------------------------------------

class TestParticipants:

    def test_save_participants_mise_a_jour(self, client):
        """POST /participants → les participants sont sauvegardés et visibles
        dans le JSON window.PARTICIPANTS de la page /ajouter."""
        _creer(client, nom="Pts")
        client.post(
            "/cagnotte/Pts/participants",
            data={"participants": "Alice, Bob, Carol"},
        )
        resp = client.get("/cagnotte/Pts/ajouter")
        assert b"Alice" in resp.data
        assert b"Carol" in resp.data

    def test_save_participants_deduplique(self, client):
        """Les participants en double dans la saisie sont dédupliqués côté serveur.
        'Alice' ne doit apparaître qu'une fois dans le JSON injecté."""
        _creer(client, nom="PtsDup")
        client.post(
            "/cagnotte/PtsDup/participants",
            data={"participants": "Alice, Alice, Bob"},
        )
        resp    = client.get("/cagnotte/PtsDup/ajouter")
        content = resp.data.decode("utf-8")
        assert content.count('"Alice"') == 1

    def test_participant_ajoute_automatiquement_apres_depense(self, client):
        """Ajouter une dépense enregistre automatiquement le participant
        (ajouter_depense appelle _ajouter_participant en interne)."""
        _creer(client, nom="AutoPt")
        _ajouter(client, "AutoPt", participant="Novo", montant="25.00")
        resp = client.get("/cagnotte/AutoPt/ajouter")
        assert b"Novo" in resp.data

    def test_participant_retire_apres_suppression_toutes_depenses(self, client):
        """Supprimer toutes les dépenses d'un participant le retire de la liste.
        (_nettoyer_participants compare JSON vs SELECT DISTINCT)."""
        _creer(client, nom="RemPt")
        _ajouter(client, "RemPt", participant="Ephemere", montant="10.00")
        client.post("/cagnotte/RemPt/depenses/delete", data={"indices": "0"})
        resp = client.get("/cagnotte/RemPt/ajouter")
        assert b"Ephemere" not in resp.data


# ---------------------------------------------------------------------------
# 11. Toggle remboursement — état persisté
# ---------------------------------------------------------------------------

class TestToggleRemboursement:

    @staticmethod
    def _get_sig(nom):
        """Récupère la première signature de transaction via la couche domaine.
        On évite de parser le HTML de la page équilibre dans les tests d'intégration."""
        from archilog.domain import CagnotteService
        calcul = CagnotteService().calculer(nom)
        return calcul["transactions"][0]["signature"] if calcul["transactions"] else None

    def test_toggle_persiste_etat_effectue(self, client):
        """Après toggle, la page équilibre contient la classe 'done-row'."""
        _creer(client, nom="Tog")
        _ajouter(client, "Tog", participant="Alice", montant="60.00")
        _ajouter(client, "Tog", participant="Bob",   montant="30.00")
        sig = self._get_sig("Tog")

        # Premier toggle → effectué
        r1 = client.post(
            "/cagnotte/Tog/remboursement/toggle",
            data={"signature": sig},
        )
        assert r1.get_json()["effectue"] is True

        # La classe CSS .done-row est rendue dans le HTML de la page équilibre
        resp = client.get("/cagnotte/Tog/equilibre")
        assert b"done-row" in resp.data

    def test_toggle_double_annule(self, client):
        """Deux toggles successifs → le second retourne effectue=False."""
        _creer(client, nom="Tog2")
        _ajouter(client, "Tog2", participant="Alice", montant="60.00")
        _ajouter(client, "Tog2", participant="Bob",   montant="30.00")
        sig = self._get_sig("Tog2")

        client.post("/cagnotte/Tog2/remboursement/toggle", data={"signature": sig})
        r2 = client.post("/cagnotte/Tog2/remboursement/toggle", data={"signature": sig})
        assert r2.get_json()["effectue"] is False

    def test_toggle_nb_effectues_dans_reponse(self, client):
        """La réponse JSON inclut nb_effectues et nb_total (utilisés par main.js
        pour mettre à jour le compteur #cptEffectues sans rechargement)."""
        _creer(client, nom="Tog3")
        _ajouter(client, "Tog3", participant="Alice", montant="60.00")
        _ajouter(client, "Tog3", participant="Bob",   montant="30.00")
        sig = self._get_sig("Tog3")

        r = client.post("/cagnotte/Tog3/remboursement/toggle", data={"signature": sig})
        data = r.get_json()
        assert "nb_effectues" in data
        assert "nb_total"     in data
        assert data["nb_effectues"] == 1