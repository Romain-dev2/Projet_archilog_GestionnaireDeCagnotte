/* ============================================================
   Archilog — home.js
   Chargé uniquement sur home.html.

   Contient :
     1. Sélection multiple de cagnottes (via selection.js)
     2. Soumission suppression multiple (redirige)
   ============================================================ */

const selection = window.makeSelectionController({
    itemCheckboxSelector: '.cag-check',
    tableRowsSelector: '#cagnottesTable tbody tr',
    checkAllId: 'checkAll',
    deleteBarId: 'deleteBar',
    deleteBarTextId: 'deleteBarText',
    getKey: (cb) => cb.getAttribute('data-nom'),
    getIdx: (cb) => cb.getAttribute('data-idx'),
    formatText: (n) => {
        if (n === 0) return '0 sélectionnée(s)';
        return n === 1 ? '1 cagnotte sélectionnée' : (n + ' cagnottes sélectionnées');
    },
});

document.addEventListener('DOMContentLoaded', function () {
    selection.bindCheckAll();
});

// Appelées depuis le HTML
window.onRowCheck = selection.onRowCheck;
window.clearSelection = selection.clearSelection;

function submitMultiDelete() {
  if (selection.selected.size === 0) return;

  const noms = Array.from(selection.selected).join(',');
  window.location.href = '/cagnottes/confirm-delete-multiple?noms=' + encodeURIComponent(noms);
}

window.submitMultiDelete = submitMultiDelete;