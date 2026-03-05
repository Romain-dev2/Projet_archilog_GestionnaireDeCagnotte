/* ============================================================
   Archilog — depenses.js
   Chargé uniquement sur depenses.html.

   Contient :
     1. Sélection multiple de dépenses (via selection.js)
     2. Filtrage en temps réel (barre de recherche)
     3. Tri des colonnes Montant et Date (clic + clavier)
     4. Modal d'édition : ouverture, fermeture, soumission AJAX
     5. Modal suppression : suppression unique + multiple
   ============================================================ */


/* ── Types (pour calmer PyCharm) ───────────────────────────── */

/**
 * Réponse attendue après update AJAX d'une dépense.
 * @typedef {Object} UpdateDepenseResponse
 * @property {boolean} ok
 * @property {string=} error
 * @property {string} participant
 * @property {number} montant
 * @property {string} date
 * @property {string} libelle
 */


/* ── 1. Sélection multiple (util commun) ───────────────────── */

const selection = window.makeSelectionController({
    itemCheckboxSelector: '.dep-check',
    tableRowsSelector: '#depensesTable tbody tr',
    checkAllId: 'checkAll',
    deleteBarId: 'deleteBar',
    deleteBarTextId: 'deleteBarText',
    // Ici on stocke l'idx car ton backend delete attend "indices"
    getKey: (cb) => cb.getAttribute('data-idx'),
    getIdx: (cb) => cb.getAttribute('data-idx'),
    formatText: (n) => {
        if (n === 0) return '0 sélectionnée(s)';
        return n === 1 ? '1 dépense sélectionnée' : (n + ' dépenses sélectionnées');
    },
});

// Expose pour les handlers inline du template
window.onRowCheck = selection.onRowCheck;
window.clearSelection = selection.clearSelection;


/* ── 2. Modal suppression ─────────────────────────────────── */

let _pendingDeleteAction = null;

function openDeleteModal(msg, onConfirm) {
    const msgEl = document.getElementById('deleteConfirmMsg');
    const modal = document.getElementById('deleteConfirmModal');

    if (msgEl) msgEl.textContent = msg;
    _pendingDeleteAction = onConfirm;

    if (modal) modal.classList.add('open');
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteConfirmModal');
    if (modal) modal.classList.remove('open');
    _pendingDeleteAction = null;
}

function submitMultiDelete() {
    if (selection.selected.size === 0) return;

    const n = selection.selected.size;
    const msg = n === 1
        ? 'Supprimer cette dépense ? Cette action est irréversible.'
        : 'Supprimer ' + n + ' dépenses ? Cette action est irréversible.';

    openDeleteModal(msg, function () {
        const hidden = document.getElementById('hiddenIndices');
        const form = document.getElementById('multiDeleteForm');
        if (hidden) hidden.value = Array.from(selection.selected).join(',');
        if (form) form.submit();
    });
}

window.submitMultiDelete = submitMultiDelete;


/* ── 3. Recherche en temps réel ───────────────────────────── */

function filterTable(query) {
    const q = (query || '').trim().toLowerCase();
    const rows = document.querySelectorAll('#depensesTable tbody tr');
    let shown = 0;

    for (let i = 0; i < rows.length; i++) {
        const hay = rows[i].getAttribute('data-search') || '';
        const match = !q || hay.includes(q);
        rows[i].style.display = match ? '' : 'none';
        if (match) shown++;
    }

    const noResults = document.getElementById('noResults');
    const clearBtn = document.getElementById('clearBtn');
    clearBtn.classList.toggle('hidden', !q);
    noResults.classList.toggle('hidden', !(shown === 0 && q));
}

function clearSearch() {
    const input = document.getElementById('searchInput');
    if (input) input.value = '';
    filterTable('');
}

window.filterTable = filterTable;
window.clearSearch = clearSearch;


/* ── 4. Tri des colonnes ──────────────────────────────────── */

const sortState = {col: null, asc: true};

function sortTable(col) {
    const tbody = document.getElementById('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));

    if (sortState.col === col) {
        sortState.asc = !sortState.asc;
    } else {
        sortState.col = col;
        sortState.asc = true;
    }

    const toDateNum = function (s) {
        const p = (s || '').split('/');
        if (p.length !== 3) return 0;
        return parseInt(p[2] + p[1].padStart(2, '0') + p[0].padStart(2, '0'), 10);
    };

    rows.sort(function (a, b) {
        const va = a.getAttribute('data-' + col) || '';
        const vb = b.getAttribute('data-' + col) || '';

        if (col === 'montant') {
            const na = parseFloat(va) || 0;
            const nb = parseFloat(vb) || 0;
            return sortState.asc ? (na - nb) : (nb - na);
        }

        if (col === 'date') {
            const da = toDateNum(va);
            const db = toDateNum(vb);
            return sortState.asc ? (da - db) : (db - da);
        }

        return sortState.asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });

    rows.forEach(function (r, i) {
        const numCell = r.querySelector('.row-num');
        if (numCell) numCell.textContent = String(i + 1);
    });

    rows.forEach(function (r) {
        tbody.appendChild(r);
    });

    ['montant', 'date'].forEach(function (c) {
        const el = document.getElementById('sort-' + c);
        if (!el) return;

        el.textContent = (c !== sortState.col) ? '⇅' : (sortState.asc ? '↑' : '↓');

        const th = el.closest('th');
        if (th) th.classList.toggle('th-sort--active', c === sortState.col);
    });
}

function bindSortableHeaders() {
    const headers = document.querySelectorAll('th.th-sort[data-col]');
    headers.forEach(function (th) {
        const col = th.getAttribute('data-col');
        if (!col) return;

        th.addEventListener('click', function () {
            sortTable(col);
        });

        th.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                sortTable(col);
            }
        });
    });
}

window.sortTable = sortTable;


/* ── 5. Modal d'édition ───────────────────────────────────── */

let currentEditRow = null;

function bindEditButtons() {
    document.querySelectorAll('.edit-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            openEditModal(btn);
        });
    });
}

function openEditModal(btn) {
    const depenseId = btn.getAttribute('data-id');
    const row = btn.closest('tr');
    currentEditRow = row;

    const editId = document.getElementById('editId');
    const editParticipant = document.getElementById('editParticipant');
    const editMontant = document.getElementById('editMontant');
    const editLibelle = document.getElementById('editLibelle');
    const editDate = document.getElementById('editDate');

    if (editId) editId.value = depenseId || '';

    if (editParticipant) {
        editParticipant.value = row.querySelector('.cell-participant strong').textContent.trim();
    }

    if (editMontant) {
        editMontant.value = row.getAttribute('data-montant') || '';
    }

    if (editLibelle) {
        const libelle = row.querySelector('.cell-libelle').textContent.trim();
        editLibelle.value = (libelle === '—') ? '' : libelle;
    }

    if (editDate) {
        const rawDate = row.getAttribute('data-date') || '';
        const parts = rawDate.split('/');
        editDate.value = (parts.length === 3) ? (parts[2] + '-' + parts[1] + '-' + parts[0]) : '';
    }

    const errEl = document.getElementById('editError');
    if (errEl) errEl.style.display = 'none';

    const modal = document.getElementById('editModal');
    if (modal) modal.classList.add('open');

    if (editParticipant) editParticipant.focus();
}

function closeModal() {
    const modal = document.getElementById('editModal');
    if (modal) modal.classList.remove('open');
    currentEditRow = null;
}

function submitEdit(e) {
    e.preventDefault();

    const id = document.getElementById('editId')?.value || '';
    const participant = document.getElementById('editParticipant')?.value.trim() || '';
    const montant = document.getElementById('editMontant')?.value || '';
    const date = document.getElementById('editDate')?.value || '';
    const libelle = document.getElementById('editLibelle')?.value.trim() || '';

    const errEl = document.getElementById('editError');
    const submitBtn = document.getElementById('editSubmitBtn');

    if (errEl) errEl.style.display = 'none';
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Enregistrement…';
    }

    const fd = new FormData();
    fd.append('participant', participant);
    fd.append('montant', montant);
    fd.append('date', date);
    fd.append('libelle', libelle);

    const url = '/cagnotte/' + window.NOM + '/depense/' + id + '/update';

    fetch(url, {method: 'POST', body: fd})
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            /** @type {UpdateDepenseResponse} */
            const res = data;

            if (!res.ok) throw new Error(res.error || 'Erreur serveur');
            if (currentEditRow) {
                currentEditRow.querySelector('.cell-participant strong').textContent = res.participant;
                currentEditRow.querySelector('.cell-montant').textContent = String(res.montant) + '€';
                currentEditRow.querySelector('.cell-libelle').textContent = res.libelle || '—';
                currentEditRow.querySelector('.cell-date').textContent = res.date || '—';

                // Data-* pour tri + recherche
                currentEditRow.setAttribute('data-montant', String(res.montant));
                currentEditRow.setAttribute('data-date', res.date || '');
                currentEditRow.setAttribute(
                    'data-search',
                    res.participant.toLowerCase() + ' ' + (res.libelle || '').toLowerCase()
                );

                // petit feedback visuel
                const rowToMark = currentEditRow;
                rowToMark.classList.add('row-saved');
                setTimeout(function () {
                    rowToMark.classList.remove('row-saved');
                }, 1200);
            }

            // ✅ Toujours fermer le modal si la requête a réussi
            closeModal();
        })
        .catch(function (err) {
            if (errEl) {
                errEl.textContent = 'Erreur : ' + err.message;
                errEl.style.display = 'block';
            } else if (window.showToast) {
                window.showToast('Erreur : ' + err.message, 'error');
            }
        })
        .finally(function () {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Enregistrer les modifications';
            }
        });
}


/* ── Init / listeners globaux ─────────────────────────────── */

document.addEventListener('DOMContentLoaded', function () {
    // init sélection (checkAll)
    selection.bindCheckAll();
    selection.updateBar();

    // Tri (clic + clavier) sur headers
    bindSortableHeaders();

    // Edit + autocomplete
    bindEditButtons();
    if (window.PARTICIPANTS) {
        initCombobox('editParticipant', 'editParticipantDropdown', window.PARTICIPANTS);
    }

    const editForm = document.getElementById('editForm');
    if (editForm) editForm.addEventListener('submit', submitEdit);

    document.querySelectorAll('.single-delete-form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = form.getAttribute('data-confirm') || 'Confirmer la suppression ?';
            openDeleteModal(msg, function () {
                form.submit();
            });
        });
    });

    const deleteOverlay = document.getElementById('deleteConfirmModal');
    if (deleteOverlay) {
        deleteOverlay.addEventListener('click', function (e) {
            if (e.target === deleteOverlay) closeDeleteModal();
        });
    }

    const deleteBtn = document.getElementById('deleteConfirmBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function () {
            const action = _pendingDeleteAction;
            closeDeleteModal();
            if (action) action();
        });
    }

    const editOverlay = document.getElementById('editModal');
    if (editOverlay) {
        editOverlay.addEventListener('click', function (e) {
            if (e.target === editOverlay) closeModal();
        });
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeDeleteModal();
        closeModal();
    }
});