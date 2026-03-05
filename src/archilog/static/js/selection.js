/* ============================================================
   Archilog — selection.js
   Util commun : sélection multiple + barre d'action + checkAll.

   Exposé via window.makeSelectionController(opts) pour être
   consommé sans modules ES par home.js et depenses.js.

   Chaque page instancie son propre contrôleur avec ses sélecteurs
   spécifiques (cag-check / dep-check, table différente, etc.).
   ============================================================ */

(function () {
  /**
   * Crée un contrôleur de sélection multiple pour un tableau donné.
   *
   * @param {Object} opts
   * @param {string}   opts.itemCheckboxSelector  - Sélecteur CSS des checkboxes de ligne
   * @param {string}   opts.tableRowsSelector     - Sélecteur CSS des <tr> du tableau
   * @param {string}   opts.checkAllId            - id du checkbox "tout sélectionner"
   * @param {string}   opts.deleteBarId           - id de la barre d'action (delete bar)
   * @param {string}   opts.deleteBarTextId       - id du <span> de comptage dans la barre
   * @param {Function} opts.getKey                - (checkbox) → clé unique de la ligne (nom ou idx)
   * @param {Function} opts.getIdx                - (checkbox) → index visuel pour cibler #row-N
   * @param {Function} opts.formatText            - (n) → texte affiché dans la barre ("N sélectionnée(s)")
   *
   * @returns {{ selected: Set, updateBar, onRowCheck, clearSelection, bindCheckAll }}
   */
  function makeSelectionController(opts) {
    /* Ensemble des clés sélectionnées (nom de cagnotte ou idx de dépense).
       Utiliser un Set garantit l'unicité sans vérification manuelle. */
    const selected = new Set();

    /* ── Mise à jour de la barre et du checkbox "tout sélectionner" ── */
    function updateBar() {
      const n = selected.size;

      const bar = document.getElementById(opts.deleteBarId);
      const txt = document.getElementById(opts.deleteBarTextId);
      /* La barre est visible uniquement quand au moins un élément est sélectionné */
      if (bar) bar.classList.toggle('visible', n > 0);
      if (txt) txt.textContent = opts.formatText(n);

      /* Sync checkAll : coché seulement si TOUTES les lignes sont sélectionnées */
      const boxes = document.querySelectorAll(opts.itemCheckboxSelector);
      let all = boxes.length > 0;
      for (let i = 0; i < boxes.length; i++) {
        if (!boxes[i].checked) { all = false; break; }
      }
      const ca = document.getElementById(opts.checkAllId);
      if (ca) ca.checked = all;
    }

    /* ── Callback appelé par onchange de chaque checkbox de ligne ── */
    function onRowCheck(cb) {
      const key = opts.getKey(cb);
      const idx = opts.getIdx(cb);
      /* #row-N : convention de nommage partagée avec les templates Jinja */
      const row = (idx != null) ? document.getElementById('row-' + idx) : null;

      if (cb.checked) {
        selected.add(key);
        if (row) row.classList.add('selected-row');
      } else {
        selected.delete(key);
        if (row) row.classList.remove('selected-row');
      }

      updateBar();
    }

    /* ── Réinitialise toute la sélection (bouton "Annuler" de la barre) ── */
    function clearSelection() {
      selected.clear();

      /* Décoche toutes les checkboxes individuelles */
      const boxes = document.querySelectorAll(opts.itemCheckboxSelector);
      for (let i = 0; i < boxes.length; i++) boxes[i].checked = false;

      /* Décoche le checkbox "tout sélectionner" */
      const ca = document.getElementById(opts.checkAllId);
      if (ca) ca.checked = false;

      /* Retire la classe visuelle sur chaque ligne */
      const rows = document.querySelectorAll(opts.tableRowsSelector);
      for (let i = 0; i < rows.length; i++) rows[i].classList.remove('selected-row');

      updateBar();
    }

    /* ── Attache le listener sur le checkbox "tout sélectionner" ── */
    function bindCheckAll() {
      const ca = document.getElementById(opts.checkAllId);
      if (!ca) return;

      ca.addEventListener('change', function () {
        const checked = ca.checked;
        const boxes = document.querySelectorAll(opts.itemCheckboxSelector);

        for (let i = 0; i < boxes.length; i++) {
          boxes[i].checked = checked;

          const key = opts.getKey(boxes[i]);
          const idx = opts.getIdx(boxes[i]);
          const row = (idx != null) ? document.getElementById('row-' + idx) : null;

          if (checked) {
            selected.add(key);
            if (row) row.classList.add('selected-row');
          } else {
            selected.delete(key);
            if (row) row.classList.remove('selected-row');
          }
        }

        updateBar();
      });
    }

    return { selected, updateBar, onRowCheck, clearSelection, bindCheckAll };
  }

  /* Exposition globale : pas de module ES pour rester compatible avec le
     chargement synchrone via <script src="..."> dans base.html. */
  window.makeSelectionController = makeSelectionController;
})();