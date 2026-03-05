"""
archilog — cli.py
Interface ligne de commande (Click).

Toutes les commandes passent par CagnotteService :
aucun accès direct à la base de données ici.

Usage :
    archilog --help
    archilog creation --nom "Vacances" --description "Été 2025"
    archilog lister
    archilog ajout --cagnotte "Vacances" --participant "Alice" --montant 50
    archilog calcul --nom "Vacances"
    archilog export --nom "Vacances"
"""

import csv
from datetime import date
import re
from pathlib import Path

import click

from .domain import CagnotteService
from .data import get_db_path


class NoSortGroup(click.Group):
    """Groupe Click qui conserve l'ordre de déclaration des commandes.

    Par défaut Click trie les commandes alphabétiquement dans le --help,
    ce qui nuit à la lisibilité du workflow naturel (création → ajout → calcul).
    """
    def list_commands(self, ctx):
        return list(self.commands.keys())


@click.group(cls=NoSortGroup)
@click.pass_context
def cli(ctx):
    """Gestion de cagnottes partagées."""
    ctx.ensure_object(dict)
    # Le service est stocké dans le contexte Click pour être partagé entre
    # les sous-commandes sans être réinstancié à chaque appel.
    ctx.obj["service"] = CagnotteService()


# ── Accède à la base de donnés  ───────────────────────────────────────────────

@cli.command("db-path")
def db_path():
    """Afficher le chemin du fichier SQLite utilisé par Archilog."""
    click.echo(get_db_path())


# ── Cagnottes ─────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--nom",         prompt="Nom de la cagnotte")
@click.option("--description", prompt="Description (optionnelle — Entrée pour valider)", default="")
@click.pass_context
def creation(ctx, nom, description):
    """Créer une nouvelle cagnotte."""
    ok = ctx.obj["service"].creer_cagnotte(nom, description)
    if ok:
        click.echo(f"Cagnotte « {nom} » créée.")
    else:
        click.echo(f"Erreur : la cagnotte « {nom} » existe déjà.")


@cli.command()
@click.pass_context
def lister(ctx):
    """Lister toutes les cagnottes."""
    cagnottes = ctx.obj["service"].lister_cagnottes()
    if not cagnottes:
        click.echo("Aucune cagnotte.")
        return
    for c in cagnottes:
        click.echo(f"  • {c.nom} : {c.description or ''}")


@cli.command()
@click.option("--nom", prompt="Nom de la cagnotte")
@click.pass_context
def suppression(ctx, nom):
    """Supprimer une cagnotte et toutes ses dépenses."""
    ctx.obj["service"].supprimer_cagnotte(nom)
    click.echo(f"Cagnotte « {nom} » supprimée.")


# ── Dépenses ──────────────────────────────────────────────────────────────────

def _today_fr() -> str:
    # Passée comme callable (et non comme valeur) à Click via default=_today_fr :
    # l'évaluation est différée à l'invocation de la commande, garantissant
    # la date du jour réelle et non la date au moment du chargement du module.
    return date.today().strftime("%d/%m/%Y")


@cli.command()
@click.option("--cagnotte",    prompt="Nom de la cagnotte")
@click.option("--participant", prompt="Nom du participant")
@click.option("--montant",     prompt="Montant (€)", type=float)
@click.option("--libelle",     prompt="Libellé (optionnel - Entrée pour continuer)", default="")
@click.option(
    "--date",
    "date_str",
    default=_today_fr,
    prompt="Date (JJ/MM/AAAA) — Entrée pour aujourd'hui",
    show_default=False,
)
@click.pass_context
def ajout(ctx, cagnotte, participant, montant, libelle, date_str):
    """Ajouter une dépense à une cagnotte."""
    ctx.obj["service"].ajouter_depense(
        cagnotte, participant, montant, date_str, libelle or None
    )


@cli.command("afficher")
@click.option("--nom", prompt="Nom de la cagnotte")
@click.pass_context
def afficher_depenses(ctx, nom):
    """Afficher les dépenses d'une cagnotte."""
    depenses = ctx.obj["service"].lister_depenses(nom)
    if not depenses:
        click.echo(f"Aucune dépense dans « {nom} ».")
        return
    click.echo(f"\nDépenses de « {nom} » :")
    for d in depenses:
        libelle = f" — {d.libelle}" if d.libelle else ""
        click.echo(f"  #{d.id}  {d.participant} : {d.montant:.2f} € le {d.date or '?'}{libelle}")


@cli.command("supprimer")
@click.option("--cagnotte",    prompt="Nom de la cagnotte")
@click.option("--participant", prompt="Nom du participant")
@click.pass_context
def supprimer_depenses(ctx, cagnotte, participant):
    """Supprimer une ou plusieurs dépenses d'un participant."""
    service  = ctx.obj["service"]
    depenses = service.lister_depenses(cagnotte)
    # Filtre les dépenses du participant demandé avant d'afficher le menu
    dep_part = [d for d in depenses if d.participant == participant]

    if not dep_part:
        click.echo(f"Aucune dépense pour {participant} dans « {cagnotte} ».")
        return

    click.echo(f"\nDépenses de {participant} :")
    for i, d in enumerate(dep_part):
        libelle = f" — {d.libelle}" if d.libelle else ""
        click.echo(f"  #{d.id} (index {i}) : {d.montant:.2f} € le {d.date or '?'}{libelle}")

    ids_input = click.prompt("\nIndices à supprimer (0,1,… ou 'tout')")
    # `all_ids` contient les ids de TOUTES les dépenses (pas seulement celles du participant)
    # pour pouvoir convertir les indices globaux utilisés par le repository.
    all_ids   = [d.id for d in depenses]

    if ids_input.strip().lower() == "tout":
        indices = [all_ids.index(d.id) for d in dep_part if d.id in all_ids]
    else:
        part_indices = [int(x.strip()) for x in ids_input.split(",") if x.strip().isdigit()]
        indices      = [all_ids.index(dep_part[i].id) for i in part_indices
                        if 0 <= i < len(dep_part) and dep_part[i].id in all_ids]

    service.supprimer_depenses_par_indices(cagnotte, sorted(indices, reverse=True))
    click.echo(f"{len(indices)} dépense(s) supprimée(s).")


# ── Calcul ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--nom", prompt="Nom de la cagnotte")
@click.pass_context
def calcul(ctx, nom):
    """Calculer qui doit quoi à qui dans une cagnotte."""
    result = ctx.obj["service"].calculer(nom)

    if not result["transactions"] and result["total"] == 0:
        click.echo(f"Aucune dépense dans « {nom} ».")
        return

    click.echo(f"\nRépartition pour « {nom} » :")
    click.echo(f"  Total : {result['total']:.2f} €  |  Part : {result['part']:.2f} €\n")

    click.echo("Par participant :")
    for p in result["par_participant"]:
        click.echo(f"  {p['nom']} : {p['total']:.2f} €")

    if result["transactions"]:
        click.echo("\nTransactions nécessaires :")
        for t in result["transactions"]:
            # ✓ indique que le remboursement a été marqué effectué dans la base
            statut = " ✓" if t["effectue"] else ""
            click.echo(f"  {t['debiteur']} → {t['crediteur']} : {t['montant']:.2f} €{statut}")
    else:
        click.echo("\nTout est équilibré !")


# ── Export CSV ────────────────────────────────────────────────────────────────

def _write_depenses_csv(writer, depenses):
    """Écrit l'en-tête puis les lignes dans un writer CSV déjà ouvert.

    Factorisée ici pour être réutilisée par la commande `export` (CLI) et
    la route `export_csv` (views.py) sans dupliquer le format des colonnes.
    """
    writer.writerow(["#", "Participant", "Montant", "Date", "Libellé"])
    for i, d in enumerate(depenses, 1):
        writer.writerow([
            i,
            d.participant,
            d.montant,
            d.date or "",
            d.libelle or "",
        ])


def _safe_export_filename(nom: str) -> str:
    s = nom.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^A-Za-z0-9 _.-]", "_", s)
    s = s.strip(" ._")
    if not s:
        s = "export"
    upper = s.upper()
    reserved = {"CON","PRN","AUX","NUL"} | {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)}
    if upper in reserved:
        s = f"{s}_"
    return s + ".csv"


@cli.command()
@click.option("--nom", prompt="Nom de la cagnotte")
@click.pass_context
def export(ctx, nom):
    """Exporter les dépenses d'une cagnotte en CSV."""
    depenses = ctx.obj["service"].lister_depenses(nom)
    path     = Path(_safe_export_filename(nom)).name

    # Le fichier est créé dans le répertoire de travail courant.
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        _write_depenses_csv(writer, depenses)

    click.echo(f"Exporté dans {path} ({len(depenses)} ligne(s)).")


if __name__ == "__main__":
    cli()