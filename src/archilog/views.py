"""
archilog — views.py
─────────────────────────────────────────────────────────────────────────────
Couche présentation Flask : routes HTTP, parsing des formulaires, rendu HTML.

Ce fichier ne contient AUCUNE logique métier ni accès SQL direct.
Toutes les opérations passent par `service` (CagnotteService).

Conventions :
  - Les routes GET rendent un template.
  - Les routes POST redirigent (pattern PRG : Post/Redirect/Get) pour éviter
    la double soumission lors d'un rechargement de page.
  - Les routes /json et /update répondent en JSON (consommées par le JS front).
  - Les messages flash sont affichés par le composant toast (components/toast.html).
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import date
import csv
import io

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, flash
from .domain import CagnotteService
from .config import Config

# `app` est l'instance Flask partagée. Elle est importée par conftest.py pour
# construire le client de test. Ne pas renommer sans mettre à jour conftest.py.
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# Instance unique du service métier pour toute la durée de vie de l'application.
# Remplacée implicitement dans les tests via le patch de `archilog.data.engine`
# (le service instancié ici utilisera l'engine déjà patché par conftest.py).
service = CagnotteService()


# ── Helpers de parsing formulaires ────────────────────────────────────────

def _to_iso_input(date_fr: str | None) -> str:
    """Convertit 'DD/MM/YYYY' -> 'YYYY-MM-DD' pour remplir <input type='date'>.

    Retourne une chaîne vide si la date est absente ou mal formée.
    """
    if not date_fr:
        return ""
    parts = date_fr.split("/")
    if len(parts) != 3:
        return ""
    dd, mm, yyyy = parts
    if not (dd.isdigit() and mm.isdigit() and yyyy.isdigit()):
        return ""
    return f"{yyyy}-{mm}-{dd}"


def _parse_date(date_raw: str) -> str:
    """Convertit une date ISO (YYYY-MM-DD) reçue d'un <input type='date'>
    en format FR (DD/MM/YYYY) stocké en base.
    Retourne la date du jour si date_raw est vide ou invalide.
    """
    if date_raw:
        try:
            d = date.fromisoformat(date_raw)
            return d.strftime("%d/%m/%Y")
        except ValueError:
            pass
    # Fallback : date du jour — jamais de dépense sans date en base.
    return date.today().strftime("%d/%m/%Y")


def _parse_montant(montant_str: str) -> float | None:
    """Parse un montant texte en float. Retourne None si invalide."""
    try:
        return float(montant_str)
    except ValueError:
        return None


def _read_depense_form():
    """
    Lit et nettoie les champs d'une dépense depuis request.form.

    Retour:
        (participant, montant, date_str, libelle)
        - participant: str (vide si non fourni)
        - montant: float | None (None si invalide)
        - date_str: str au format 'DD/MM/YYYY' (fallback = aujourd'hui)
        - libelle: str | None (None si vide)

    Factorisé ici pour éviter la duplication entre add_depense, edit_depense
    et update_depense_ajax qui lisent exactement les mêmes champs.
    """
    participant = request.form.get("participant", "").strip()
    montant = _parse_montant(request.form.get("montant", "").strip())
    date_str = _parse_date(request.form.get("date", "").strip())
    libelle = request.form.get("libelle", "").strip() or None
    return participant, montant, date_str, libelle


def _today_iso() -> str:
    """Retourne la date du jour au format ISO, pour préremplir <input type='date'>."""
    return date.today().isoformat()


# ── Home ──────────────────────────────────────────────────

@app.route("/")
def home():
    """Page d'accueil : liste toutes les cagnottes existantes."""
    cagnottes = service.lister_cagnottes()
    return render_template("pages/cagnottes/home.html", cagnottes=cagnottes)


@app.route("/cagnotte/new")
def new_cagnotte():
    """Affiche le formulaire de création d'une nouvelle cagnotte."""
    return render_template("pages/cagnottes/new_cagnotte.html")


@app.route("/cagnotte/create", methods=["POST"])
def create_cagnotte():
    """Traite la soumission du formulaire de création (POST).

    Valide le nom, crée la cagnotte via le service, flash le résultat,
    puis redirige vers l'accueil (pattern PRG).
    """
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Impossible de créer la cagnotte : le nom est vide.", "error")
    elif service.creer_cagnotte(nom, description):
        flash("Cagnotte créée avec succès.", "success")
    else:
        flash("Erreur : cette cagnotte existe déjà.", "error")
    return redirect(url_for("home"))


# ── Onglets cagnotte ──────────────────────────────────────

@app.route("/cagnotte/<nom>")
def cagnotte_detail(nom: str):
    """Vue d'ensemble d'une cagnotte : chiffres clés, dernières dépenses, remboursements."""
    depenses = service.lister_depenses(nom)
    calcul = service.calculer(nom)
    participants = sorted(service.get_participants(nom))
    # last5 : 5 dernières dépenses en ordre chronologique inverse pour l'affichage
    last5 = list(reversed(depenses[-5:]))
    return render_template("pages/cagnotte_details/cagnotte.html", nom=nom, depenses=depenses,
                           last5=last5, calcul=calcul, participants=participants)


@app.route("/cagnotte/<nom>/depenses")
def cagnotte_depenses(nom: str):
    """Liste complète des dépenses d'une cagnotte avec filtrage et tri côté client."""
    depenses = service.lister_depenses(nom)
    participants = sorted(service.get_participants(nom))
    return render_template("pages/cagnotte_details/depenses.html", nom=nom,
                           depenses=depenses, participants=participants)


@app.route("/cagnotte/<nom>/equilibre")
def cagnotte_equilibre(nom: str):
    """Page d'équilibre : transactions nécessaires pour solder les dépenses."""
    calcul = service.calculer(nom)
    return render_template("pages/cagnotte_details/equilibre_depenses.html", nom=nom, calcul=calcul)


@app.route("/cagnotte/<nom>/ajouter")
def cagnotte_ajouter(nom: str):
    """Formulaire d'ajout d'une nouvelle dépense à la cagnotte."""
    participants = sorted(service.get_participants(nom))
    return render_template("pages/cagnotte_details/new_depense.html", nom=nom,
                           participants=participants, today=_today_iso())


# ── CRUD dépenses ─────────────────────────────────────────

@app.route("/cagnotte/<nom>/depense", methods=["POST"])
def add_depense(nom: str):
    """Traite l'ajout d'une dépense (POST). Valide montant ≥ 0.01 et participant non vide."""
    # Lecture et nettoyage des champs du formulaire (factorisé)
    participant, montant, date_str, libelle = _read_depense_form()
    if participant and montant is not None and montant >= 0.01:
        service.ajouter_depense(nom, participant, montant, date_str, libelle)
        flash("Dépense ajoutée.", "success")
    else:
        flash("Erreur lors de l'ajout de la dépense.", "error")
    return redirect(url_for("cagnotte_depenses", nom=nom))


@app.route("/cagnotte/<nom>/depense/<int:depense_id>/edit", methods=["GET", "POST"])
def edit_depense(nom: str, depense_id: int):
    """Formulaire d'édition d'une dépense existante (page dédiée, sans AJAX).

    GET  → affiche le formulaire prérempli.
    POST → valide et enregistre les modifications.

    La dépense est cherchée parmi celles de `nom` pour empêcher l'accès
    inter-cagnottes : une dépense d'une autre cagnotte retourne une redirection.
    """
    # ✅ Empêche l'accès à une dépense d'une autre cagnotte
    depenses_cagnotte = service.lister_depenses(nom)
    depense = next((d for d in depenses_cagnotte if d.id == depense_id), None)
    if not depense:
        return redirect(url_for("cagnotte_depenses", nom=nom))

    if request.method == "POST":
        participant, montant, date_str, libelle = _read_depense_form()
        if participant and montant is not None and montant >= 0.01:
            service.modifier_depense(depense_id, participant, montant, date_str, libelle)
            flash("Dépense modifiée.", "success")
        else:
            flash("Erreur lors de la modification.", "error")
        return redirect(url_for("cagnotte_depenses", nom=nom))

    # Conversion de la date stockée (DD/MM/YYYY) vers ISO pour l'input HTML
    date_input = _to_iso_input(depense.date)
    participants = sorted(service.get_participants(nom))
    return render_template(
        "pages/cagnotte_details/edit_depense.html",
        nom=nom,
        depense=depense,
        date_input=date_input,
        participants=participants,
        today=_today_iso(),
    )


@app.route("/cagnotte/<nom>/depense/<int:depense_id>/json")
def get_depense_json(nom: str, depense_id: int):
    """Retourne les données d'une dépense en JSON pour le modal AJAX (depenses.js).

    Vérifie que la dépense appartient bien à `nom` avant de répondre
    pour éviter une fuite d'informations inter-cagnottes.
    """
    # On récupère uniquement les dépenses de cette cagnotte
    depenses_cagnotte = service.lister_depenses(nom)

    # On cherche l'id dans cette cagnotte (évite la fuite inter-cagnottes)
    depense = next((d for d in depenses_cagnotte if d.id == depense_id), None)
    if not depense:
        return jsonify({"error": "not found"}), 404

    date_input = _to_iso_input(depense.date)
    return jsonify({
        "id": depense.id,
        "participant": depense.participant,
        "montant": depense.montant,
        "date": date_input,
        "libelle": depense.libelle or "",
    })


@app.route("/cagnotte/<nom>/depense/<int:depense_id>/update", methods=["POST"])
def update_depense_ajax(nom: str, depense_id: int):
    """Mise à jour AJAX — réponse JSON consommée par depenses.js.

    Même protection inter-cagnottes que get_depense_json.
    Retourne 400 si les données sont invalides, 404 si la dépense est introuvable.
    """
    # Vérifie d'abord que la dépense appartient bien à la cagnotte de l'URL
    depenses_cagnotte = service.lister_depenses(nom)
    depense = next((d for d in depenses_cagnotte if d.id == depense_id), None)
    if not depense:
        return jsonify({"error": "not found"}), 404

    participant, montant, date_str, libelle = _read_depense_form()

    # Validation côté serveur (en plus de l'éventuelle validation côté front)
    if not participant or montant is None or montant < 0.01:
        return jsonify({"error": "invalid data"}), 400

    service.modifier_depense(depense_id, participant, montant, date_str, libelle)

    # La réponse JSON est consommée par depenses.js pour mettre à jour la ligne
    # du tableau sans rechargement de page.
    return jsonify({
        "ok": True,
        "participant": participant,
        "montant": montant,
        "date": date_str,
        "libelle": libelle or "",
    })


@app.route("/cagnotte/<nom>/depenses/delete", methods=["POST"])
def delete_depenses(nom: str):
    """Supprime une ou plusieurs dépenses identifiées par leurs indices 0-based.

    Le formulaire envoie une chaîne d'indices séparés par des virgules (ex: "0,2,5").
    Les indices non-numériques sont silencieusement ignorés.
    """
    raw = request.form.get("indices", "")
    try:
        indices = sorted(
            {int(i.strip()) for i in raw.split(",") if i.strip().isdigit()},
            reverse=True,
        )
    except ValueError:
        indices = []
    if indices:
        service.supprimer_depenses_par_indices(nom, indices)
        n = len(indices)
        if n == 1:
            flash("Dépense supprimée.", "warning")
        else:
            flash(f"{n} dépenses supprimées.", "warning")
    return redirect(url_for("cagnotte_depenses", nom=nom))


# ── Import / Export CSV ───────────────────────────────────

@app.route("/cagnotte/<nom>/import-csv", methods=["GET", "POST"])
def import_csv_route(nom: str):
    """Import de dépenses depuis un fichier CSV.

    GET  → affiche la page d'import avec les instructions de format.
    POST → parse le fichier, valide les lignes, insère les dépenses valides.

    Auto-détection du séparateur (virgule vs point-virgule) basée sur la
    première ligne. Encodage attendu : UTF-8 (avec ou sans BOM utf-8-sig).
    """
    if request.method == "GET":
        return render_template("pages/cagnotte_details/import_csv.html", nom=nom)

    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Fichier CSV invalide.", "error")
        return redirect(url_for("cagnotte_depenses", nom=nom))

    try:
        # utf-8-sig gère le BOM Windows (Excel enregistre souvent avec BOM)
        content = file.stream.read().decode("utf-8-sig")
    except (UnicodeDecodeError, OSError):
        flash("Fichier CSV invalide.", "error")
        return redirect(url_for("cagnotte_depenses", nom=nom))

    # Détection du séparateur : on compte les occurrences sur la première ligne
    first_line = content.split("\n")[0]
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    depenses = []
    total_rows = 0

    for row in reader:
        total_rows += 1
        # Normalisation des noms de colonnes : strip, lowercase, accents → ASCII
        norm = {k.strip().lower().replace("é", "e").replace("è", "e"): v.strip()
                for k, v in row.items() if k}
        # `nom` est accepté comme alias de `participant` pour la compatibilité
        participant = (norm.get("participant") or norm.get("nom") or "").strip()
        if not participant:
            continue
        # Virgule décimale (format français) → point
        raw_m = (norm.get("montant") or "").replace(",", ".")
        try:
            montant = float(raw_m)
        except ValueError:
            continue
        if montant < 0.01:
            continue
        # `description` est accepté comme alias de `libelle`
        depenses.append({
            "participant": participant,
            "montant": montant,
            "date": norm.get("date") or None,
            "libelle": norm.get("libelle") or norm.get("description") or None,
        })

    if total_rows == 0 or not depenses:
        flash("Fichier CSV invalide.", "error")
        return redirect(url_for("cagnotte_depenses", nom=nom))

    imported = service.importer_depenses_csv(nom, depenses)

    valid_rows = len(depenses)
    ignored = total_rows - valid_rows

    # Messages flash distincts selon import total vs partiel
    if imported == valid_rows:
        msg = f"Import réussi — {imported} ligne{'s' if imported > 1 else ''} importée{'s' if imported > 1 else ''}."
        if ignored > 0:
            msg += f" ({ignored} ligne{'s' if ignored > 1 else ''} ignorée{'s' if ignored > 1 else ''} car invalide{'s' if ignored > 1 else ''}.)"
        flash(msg, "success")
    else:
        msg = f"Import partiel : {imported} ligne{'s' if imported > 1 else ''} sur {valid_rows} importée{'s' if imported > 1 else ''}."
        if ignored > 0:
            msg += f" ({ignored} ligne{'s' if ignored > 1 else ''} ignorée{'s' if ignored > 1 else ''} car invalide{'s' if ignored > 1 else ''}.)"
        flash(msg, "info")

    return redirect(url_for("cagnotte_depenses", nom=nom))


@app.route("/cagnotte/<nom>/export.csv")
def export_csv(nom: str):
    """Exporte toutes les dépenses de la cagnotte en CSV (séparateur `;`, UTF-8).

    Retourne une réponse avec Content-Disposition: attachment pour déclencher
    le téléchargement dans le navigateur.
    """
    depenses = service.lister_depenses(nom)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["#", "Participant", "Montant", "Date", "Libellé"])

    for i, d in enumerate(depenses, 1):
        writer.writerow([i, d.participant, d.montant, d.date or "", d.libelle or ""])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=depenses_{nom}.csv"
        },
    )


# ── Participants ──────────────────────────────────────────

@app.route("/cagnotte/<nom>/participants", methods=["POST"])
def save_participants(nom: str):
    """Enregistre la liste fixe des participants (autocomplétion manuelle).

    Les participants sont fournis sous forme de chaîne CSV dans le champ
    `participants` du formulaire (ex: "Alice, Bob, Carol").
    La liste est triée et dédupliquée côté serveur avant sauvegarde.
    """
    raw = request.form.get("participants", "")
    participants = sorted([p.strip() for p in raw.split(",") if p.strip()])
    service.maj_participants(nom, participants)
    return redirect(url_for("cagnotte_detail", nom=nom))


# ── Remboursements — AJAX toggle ─────────────────────────

@app.route("/cagnotte/<nom>/remboursement/toggle", methods=["POST"])
def toggle_remboursement(nom: str):
    """Bascule l'état d'un remboursement via AJAX — réponse JSON consommée par main.js.

    Retourne en plus le compteur global effectués/total pour mettre à jour
    l'interface sans rechargement de la page équilibre.
    """
    signature = request.form.get("signature", "")
    if not signature:
        return jsonify({"error": "missing"}), 400
    effectue = service.toggle_remboursement(nom, signature)
    calcul = service.calculer(nom)
    nb_effectues = sum(1 for t in calcul["transactions"] if t["effectue"])
    return jsonify({
        "effectue": effectue,
        "nb_effectues": nb_effectues,
        "nb_total": len(calcul["transactions"]),
    })


# ── Suppression cagnottes ─────────────────────────────────

@app.route("/cagnotte/<nom>/confirm-delete")
def confirm_delete(nom: str):
    """Page de confirmation avant suppression d'une seule cagnotte."""
    return render_template("pages/cagnottes/confirm_delete.html", nom=nom)


@app.route("/cagnottes/confirm-delete-multiple")
def confirm_delete_multiple():
    """Page de confirmation pour la suppression multiple de cagnottes.

    Les noms sont passés en query string (noms=A,B,C) depuis la barre de
    sélection de la page d'accueil. Redirige vers / si aucun nom fourni.
    """
    raw = request.args.get("noms", "")
    noms = [n.strip() for n in raw.split(",") if n.strip()]
    if not noms:
        return redirect(url_for("home"))
    return render_template("pages/cagnottes/confirm_delete.html", noms=noms)


@app.route("/cagnotte/<nom>/delete", methods=["POST"])
def delete_cagnotte(nom: str):
    """Supprime une cagnotte et toutes ses dépenses, puis redirige vers l'accueil."""
    service.supprimer_cagnotte(nom)
    flash("Cagnotte supprimée.", "warning")
    return redirect(url_for("home"))


@app.route("/cagnottes/delete-multiple", methods=["POST"])
def delete_cagnottes_multiple():
    """Supprime plusieurs cagnottes en une seule action (soumission depuis confirm_delete).

    Les noms sont dans le champ caché `noms` (chaîne séparée par virgules).
    """
    raw = request.form.get("noms", "")
    noms = [n.strip() for n in raw.split(",") if n.strip()]
    for nom in noms:
        service.supprimer_cagnotte(nom)
    n = len(noms)
    if n == 1:
        flash("Cagnotte supprimée.", "warning")
    elif n > 1:
        flash(f"{n} cagnottes supprimées.", "warning")
    return redirect(url_for("home"))