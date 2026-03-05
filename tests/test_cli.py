"""
tests/test_cli.py
─────────────────────────────────────────────────────────────────────────────
Tests de l'interface ligne de commande (click.testing.CliRunner).

L'engine est déjà patché vers une base en mémoire par conftest.py.
La fixture reset_db (autouse) garantit l'isolation entre chaque test.

On teste :
  1. db-path    — affiche le chemin en cours
  2. creation   — création, doublon
  3. lister     — liste vide, liste avec cagnottes
  4. suppression — suppression simple
  5. ajout      — ajout d'une dépense
  6. afficher   — liste des dépenses
  7. supprimer  — suppression de dépenses ("tout" ou indice)
  8. calcul     — affichage des transactions
  9. export     — génération du fichier CSV
─────────────────────────────────────────────────────────────────────────────
"""

import csv
from pathlib import Path

import pytest
import contextlib

from click.testing import CliRunner
from typing import cast

import click
from archilog.cli import cli
CLI = cast(click.Command, cli)


# ---------------------------------------------------------------------------
# Fixture CliRunner
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    """CliRunner Click — exécute les commandes CLI sans démarrer de serveur.
    Capture stdout/stderr et permet de simuler une saisie interactive (input=)."""
    return CliRunner()


def _invoke(runner: CliRunner, args: list, user_input: str = ""):
    """
    Helper : invoque la CLI et propage les exceptions non gérées.

    catch_exceptions=False → si la commande lève une exception Python,
    le test échoue avec une traceback claire au lieu d'un exit_code=1 muet.
    C'est le mode recommandé pour les tests unitaires CLI.
    """
    result = runner.invoke(CLI, args, input=user_input, catch_exceptions=False)
    return result


# ---------------------------------------------------------------------------
# 1. db-path
# ---------------------------------------------------------------------------

class TestDbPath:

    def test_db_path_affiche_chemin(self, runner):
        """db-path affiche un chemin non vide (peu importe lequel en test)."""
        result = _invoke(runner, ["db-path"])
        assert result.exit_code == 0
        assert result.output.strip() != ""


# ---------------------------------------------------------------------------
# 2. creation
# ---------------------------------------------------------------------------

class TestCreation:

    def test_creation_succes(self, runner):
        """Créer une cagnotte → sortie confirme le nom et 'créée'."""
        result = _invoke(runner, ["creation", "--nom", "Voyage", "--description", "Été 2025"])
        assert result.exit_code == 0
        assert "Voyage" in result.output
        assert "créée"  in result.output

    def test_creation_doublon(self, runner):
        """Créer deux fois le même nom → sortie mentionne 'existe'."""
        _invoke(runner, ["creation", "--nom", "Dup", "--description", ""])
        result = _invoke(runner, ["creation", "--nom", "Dup", "--description", ""])
        assert result.exit_code == 0
        assert "existe" in result.output

    def test_creation_sans_description(self, runner):
        """Créer une cagnotte sans description → fonctionne normalement."""
        result = _invoke(runner, ["creation", "--nom", "SansDesc", "--description", ""])
        assert result.exit_code == 0
        assert "SansDesc" in result.output


# ---------------------------------------------------------------------------
# 3. lister
# ---------------------------------------------------------------------------

class TestLister:

    def test_lister_vide(self, runner):
        """Sans cagnotte → sortie mentionne 'Aucune'."""
        result = _invoke(runner, ["lister"])
        assert result.exit_code == 0
        assert "Aucune" in result.output

    def test_lister_avec_cagnottes(self, runner):
        """Deux cagnottes créées → les deux apparaissent dans la liste."""
        _invoke(runner, ["creation", "--nom", "Alpha", "--description", "desc"])
        _invoke(runner, ["creation", "--nom", "Beta",  "--description", ""])
        result = _invoke(runner, ["lister"])
        assert result.exit_code == 0
        assert "Alpha" in result.output
        assert "Beta"  in result.output

    def test_lister_affiche_description(self, runner):
        """La description est affichée à côté du nom."""
        _invoke(runner, ["creation", "--nom", "Desc", "--description", "Voyage à Rome"])
        result = _invoke(runner, ["lister"])
        assert "Voyage à Rome" in result.output


# ---------------------------------------------------------------------------
# 4. suppression (cagnotte)
# ---------------------------------------------------------------------------

class TestSuppression:

    def test_suppression_simple(self, runner):
        """Supprimer une cagnotte existante → sortie mentionne 'supprimée'."""
        _invoke(runner, ["creation", "--nom", "ADel", "--description", ""])
        result = _invoke(runner, ["suppression", "--nom", "ADel"])
        assert result.exit_code == 0
        assert "supprimée" in result.output

    def test_suppression_retire_de_la_liste(self, runner):
        """Après suppression, la cagnotte n'apparaît plus dans 'lister'."""
        _invoke(runner, ["creation", "--nom", "Gone", "--description", ""])
        _invoke(runner, ["suppression", "--nom", "Gone"])
        result = _invoke(runner, ["lister"])
        assert "Gone" not in result.output

    def test_suppression_cagnotte_inexistante_ne_plante_pas(self, runner):
        """Supprimer une cagnotte qui n'existe pas → pas d'exception, exit 0."""
        result = _invoke(runner, ["suppression", "--nom", "Inexistante"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 5. ajout (dépense)
# ---------------------------------------------------------------------------

class TestAjout:

    def test_ajout_depense(self, runner):
        """Ajouter une dépense complète → exit 0."""
        _invoke(runner, ["creation", "--nom", "Cag", "--description", ""])
        result = _invoke(runner, [
            "ajout",
            "--cagnotte",    "Cag",
            "--participant", "Alice",
            "--montant",     "50.0",
            "--libelle",     "Courses",
            "--date",        "15/06/2025",
        ])
        assert result.exit_code == 0

    def test_ajout_visible_dans_afficher(self, runner):
        """La dépense ajoutée est visible dans 'afficher'."""
        _invoke(runner, ["creation", "--nom", "CagAff", "--description", ""])
        _invoke(runner, [
            "ajout",
            "--cagnotte", "CagAff", "--participant", "Bob",
            "--montant",  "30.0",   "--libelle",     "",
            "--date",     "01/07/2025",
        ])
        result = _invoke(runner, ["afficher", "--nom", "CagAff"])
        assert "Bob" in result.output
        assert "30"  in result.output


# ---------------------------------------------------------------------------
# 6. afficher (dépenses)
# ---------------------------------------------------------------------------

class TestAfficher:

    def test_afficher_cagnotte_vide(self, runner):
        """Cagnotte sans dépense → sortie mentionne 'Aucune'."""
        _invoke(runner, ["creation", "--nom", "Vide", "--description", ""])
        result = _invoke(runner, ["afficher", "--nom", "Vide"])
        assert result.exit_code == 0
        assert "Aucune" in result.output

    def test_afficher_affiche_libelle(self, runner):
        """Le libellé de la dépense est visible dans la sortie."""
        _invoke(runner, ["creation", "--nom", "Lib", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "Lib", "--participant", "Carol",
            "--montant", "25.0", "--libelle", "AirBnB", "--date", "01/06/2025",
        ])
        result = _invoke(runner, ["afficher", "--nom", "Lib"])
        assert "AirBnB" in result.output

    def test_afficher_affiche_tous_les_participants(self, runner):
        """Plusieurs participants → tous apparaissent dans la sortie."""
        _invoke(runner, ["creation", "--nom", "Multi", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "Multi", "--participant", "X",
            "--montant", "10.0", "--libelle", "", "--date", "01/06/2025",
        ])
        _invoke(runner, [
            "ajout", "--cagnotte", "Multi", "--participant", "Y",
            "--montant", "20.0", "--libelle", "", "--date", "02/06/2025",
        ])
        result = _invoke(runner, ["afficher", "--nom", "Multi"])
        assert "X" in result.output
        assert "Y" in result.output


# ---------------------------------------------------------------------------
# 7. supprimer (dépenses d'un participant)
#    La commande est interactive : elle affiche les dépenses du participant
#    et demande "tout" ou un index à supprimer.
# ---------------------------------------------------------------------------

class TestSupprimerDepenses:

    def test_supprimer_depenses_tout(self, runner):
        """Saisir 'tout' → toutes les dépenses du participant sont supprimées."""
        _invoke(runner, ["creation", "--nom", "DSup", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "DSup", "--participant", "Alice",
            "--montant", "10.0", "--libelle", "", "--date", "01/06/2025",
        ])
        _invoke(runner, [
            "ajout", "--cagnotte", "DSup", "--participant", "Alice",
            "--montant", "20.0", "--libelle", "", "--date", "02/06/2025",
        ])
        # input="tout\n" simule la saisie interactive de l'utilisateur
        result = runner.invoke(
            CLI,
            ["supprimer", "--cagnotte", "DSup", "--participant", "Alice"],
            input="tout\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "supprimée" in result.output

        # Vérification que la cagnotte est bien vide après suppression
        aff = _invoke(runner, ["afficher", "--nom", "DSup"])
        assert "Aucune" in aff.output

    def test_supprimer_depenses_par_indice(self, runner):
        """Saisir '0' → supprime la dépense à l'index 0 dans la liste filtrée."""
        _invoke(runner, ["creation", "--nom", "DIdx", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "DIdx", "--participant", "Alice",
            "--montant", "10.0", "--libelle", "", "--date", "01/06/2025",
        ])
        _invoke(runner, [
            "ajout", "--cagnotte", "DIdx", "--participant", "Alice",
            "--montant", "20.0", "--libelle", "", "--date", "02/06/2025",
        ])
        # input="0\n" : supprime l'index 0 parmi les dépenses d'Alice
        result = runner.invoke(
            CLI,
            ["supprimer", "--cagnotte", "DIdx", "--participant", "Alice"],
            input="0\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "1 dépense(s)" in result.output

    def test_supprimer_depenses_participant_absent(self, runner):
        """Participant sans dépense → sortie mentionne 'Aucune', exit 0."""
        _invoke(runner, ["creation", "--nom", "DNoOne", "--description", ""])
        result = runner.invoke(
            CLI,
            ["supprimer", "--cagnotte", "DNoOne", "--participant", "Fantôme"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Aucune" in result.output


# ---------------------------------------------------------------------------
# 8. calcul
# ---------------------------------------------------------------------------

class TestCalcul:

    def test_calcul_cagnotte_vide(self, runner):
        """Cagnotte sans dépense → sortie mentionne 'Aucune' (pas de transaction)."""
        _invoke(runner, ["creation", "--nom", "CV", "--description", ""])
        result = _invoke(runner, ["calcul", "--nom", "CV"])
        assert result.exit_code == 0
        assert "Aucune" in result.output

    def test_calcul_affiche_transaction(self, runner):
        """Les transactions sont affichées avec '→' (débiteur → créditeur)."""
        _invoke(runner, ["creation", "--nom", "CCalc", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "CCalc", "--participant", "Alice",
            "--montant", "90.0", "--libelle", "", "--date", "01/06/2025",
        ])
        _invoke(runner, [
            "ajout", "--cagnotte", "CCalc", "--participant", "Bob",
            "--montant", "30.0", "--libelle", "", "--date", "02/06/2025",
        ])
        result = _invoke(runner, ["calcul", "--nom", "CCalc"])
        assert result.exit_code == 0
        assert "→"     in result.output   # flèche de direction
        assert "Bob"   in result.output
        assert "Alice" in result.output
        assert "30"    in result.output

    def test_calcul_equilibre_parfait(self, runner):
        """Dépenses équilibrées → sortie mentionne 'équilibré' (pas de transaction)."""
        _invoke(runner, ["creation", "--nom", "CEq", "--description", ""])
        for nom in ["A", "B", "C"]:
            _invoke(runner, [
                "ajout", "--cagnotte", "CEq", "--participant", nom,
                "--montant", "30.0", "--libelle", "", "--date", "01/06/2025",
            ])
        result = _invoke(runner, ["calcul", "--nom", "CEq"])
        assert "équilibré" in result.output

    def test_calcul_affiche_total_et_part(self, runner):
        """La sortie inclut 'Total' et 'Part' (récapitulatif en tête de calcul)."""
        _invoke(runner, ["creation", "--nom", "CTot", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "CTot", "--participant", "A",
            "--montant", "60.0", "--libelle", "", "--date", "01/06/2025",
        ])
        result = _invoke(runner, ["calcul", "--nom", "CTot"])
        assert "60"    in result.output
        assert "Total" in result.output
        assert "Part"  in result.output


# ---------------------------------------------------------------------------
# 9. export CSV
#    runner.isolated_filesystem() crée un répertoire temporaire et s'y place.
#    Le fichier est créé dans ce répertoire avec le nom <cagnotte>.csv.
# ---------------------------------------------------------------------------

class TestExport:

    def test_export_cree_fichier(self, runner, tmp_path):
        """La commande export crée un fichier <nom>.csv dans le répertoire courant."""
        _invoke(runner, ["creation", "--nom", "Exp", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "Exp", "--participant", "Alice",
            "--montant", "42.0", "--libelle", "Dîner", "--date", "01/06/2025",
        ])
        with cast(contextlib.AbstractContextManager[str], cast(object, runner.isolated_filesystem(temp_dir=tmp_path))):
            result = _invoke(runner, ["export", "--nom", "Exp"])
            assert result.exit_code == 0
            assert "Exporté" in result.output
            assert Path("Exp.csv").exists()

    def test_export_contenu_csv(self, runner, tmp_path):
        """Le fichier CSV exporté contient l'en-tête et les données correctes."""
        _invoke(runner, ["creation", "--nom", "ExpC", "--description", ""])
        _invoke(runner, [
            "ajout", "--cagnotte", "ExpC", "--participant", "Bob",
            "--montant", "15.0", "--libelle", "Café", "--date", "05/06/2025",
        ])
        with cast(contextlib.AbstractContextManager[str], cast(object, runner.isolated_filesystem(temp_dir=tmp_path))):
            ...
            _invoke(runner, ["export", "--nom", "ExpC"])
            with open("ExpC.csv", newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[0][1] == "Participant"   # en-tête colonne 2
            assert rows[1][1] == "Bob"           # donnée colonne 2
            assert "15" in rows[1][2]            # montant

    def test_export_cagnotte_vide(self, runner, tmp_path):
        """Exporter une cagnotte vide → exit 0 et '0 ligne(s)' dans la sortie."""
        _invoke(runner, ["creation", "--nom", "ExpVide", "--description", ""])
        with cast(contextlib.AbstractContextManager[str], cast(object, runner.isolated_filesystem(temp_dir=tmp_path))):
            ...
            result = _invoke(runner, ["export", "--nom", "ExpVide"])
            assert result.exit_code == 0
            assert "0 ligne(s)" in result.output