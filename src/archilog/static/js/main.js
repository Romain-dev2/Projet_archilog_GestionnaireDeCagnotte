/* ============================================================
   Archilog — main.js
   Chargé sur TOUTES les pages via base.html (après le DOM).

   Contient :
     1. Thème clair / sombre      — toggle + persistance localStorage
     2. Combobox d'autocomplétion — champ participant avec suggestions
     3. Toggle remboursement      — AJAX sur la page Équilibre
     4. Toast / snackbar          — notifications non-intrusives

   Ce fichier doit rester auto-suffisant : aucune dépendance externe.
   Les scripts de page (home.js, depenses.js) peuvent appeler les
   fonctions exportées ici (ex : initCombobox, showToast).
   ============================================================ */


/* ── 1. Thème clair / sombre ──────────────────────────────────────────── */

/**
 * Bascule entre le thème clair et le thème sombre.
 * Lit l'état actuel depuis l'attribut data-theme de <html>,
 * l'inverse, le sauvegarde dans localStorage et met à jour l'icône.
 *
 * Le script anti-flash dans <head> de base.html applique le thème AVANT
 * le premier paint : cette fonction gère uniquement les basculements
 * déclenchés par l'utilisateur en cours de session.
 */
function toggleDark() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';

  html.setAttribute('data-theme', next);
  localStorage.setItem('archilog_theme', next);

  /* Met à jour l'icône (dans le bouton de bascule) */
  const iconEl = document.getElementById('darkIcon');
  if (iconEl) iconEl.textContent = isDark ? '🌙' : '☀️';
}

document.addEventListener('DOMContentLoaded', function () {
  /* Applique l'icône correspondant au thème déjà posé par le script <head>.
     Sans cela, l'icône par défaut (☀️ dans base.html) resterait affichée
     même en mode sombre au premier chargement. */
  const theme = localStorage.getItem('archilog_theme') || 'light';
  const icon = document.getElementById('darkIcon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';

  /* Attache le toggle — pas de onclick="" inline dans le HTML */
  const btn = document.getElementById('darkToggle');
  if (btn) btn.addEventListener('click', toggleDark);
});


/* ── 2. Combobox d'autocomplétion ─────────────────────────────────────── */

/**
 * Initialise une combobox sur un champ texte existant.
 * La liste de suggestions filtre dynamiquement au fil de la frappe
 * et se ferme quand l'utilisateur clique en dehors.
 *
 * Utilisée sur les champs "participant" des pages new_depense, edit_depense
 * et dans le modal d'édition (depenses.js).
 *
 * @param {string}   inputId    - id de l'<input> texte
 * @param {string}   dropdownId - id du <div> contenant les suggestions (.combo-dropdown)
 * @param {string[]} items      - tableau des suggestions possibles
 */
function initCombobox(inputId, dropdownId, items) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;

  /* Reconstruit la liste filtrée à chaque frappe */
  function render(query) {
    const q = query.trim().toLowerCase();
    const matches = q
      ? items.filter(function (p) { return p.toLowerCase().includes(q); })
      : items; /* Affiche toutes les suggestions si le champ est vide */

    if (matches.length === 0) {
      dropdown.style.display = 'none';
      return;
    }

    dropdown.innerHTML = matches.map(function (p) {
      /* On échappe les guillemets pour éviter de casser l'attribut data-val */
      const safe = p.replace(/"/g, '&quot;');
      return '<div class="combo-item" data-val="' + safe + '">' + p + '</div>';
    }).join('');
    dropdown.style.display = 'block';

    /* mousedown (et non click) évite que le blur de l'input ferme la liste
       avant que la sélection d'un item soit enregistrée. */
    dropdown.querySelectorAll('.combo-item').forEach(function (item) {
      item.addEventListener('mousedown', function (e) {
        e.preventDefault();
        input.value = this.getAttribute('data-val');
        dropdown.style.display = 'none';
      });
    });
  }

  input.addEventListener('input', function () { render(this.value); });
  /* Affiche les suggestions à la prise de focus (même si le champ est vide) */
  input.addEventListener('focus', function () { render(this.value); });
  input.addEventListener('blur', function () {
    /* Petit délai pour laisser le mousedown sur un item se produire avant
       que le dropdown soit masqué par la perte de focus. */
    setTimeout(function () { dropdown.style.display = 'none'; }, 150);
  });
}


/* ── 3. Toggle remboursement (page Équilibre) ─────────────────────────── */

/**
 * Réponse attendue du endpoint de toggle remboursement.
 * @typedef {{effectue: boolean, nb_effectues: number}} ToggleRemboursementResponse
 */

/**
 * Marque / démarque un remboursement comme effectué via AJAX.
 * Met à jour la ligne visuellement (classe done-row) sans recharger la page.
 *
 * L'URL du endpoint est injectée par equilibre.html dans window.TOGGLE_URL
 * via un bloc <script> inline — seule façon de passer une URL Flask vers JS.
 *
 * @param {HTMLElement} btn - bouton .done-toggle cliqué dans la ligne du tableau
 */
function toggleRemboursement(btn) {
  const sig = btn.getAttribute('data-sig');
  const idx = btn.getAttribute('data-idx');
  const row = document.getElementById('tr-' + idx);

  /* Bloque le bouton pendant l'appel réseau pour éviter le double-clic */
  btn.disabled = true;

  const fd = new FormData();
  fd.append('signature', sig);

  fetch(window.TOGGLE_URL, { method: 'POST', body: fd })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      /** @type {ToggleRemboursementResponse} */
      const res = data;

      /* Mise à jour visuelle de la ligne selon l'état retourné par le serveur */
      if (res.effectue) {
        if (row) row.classList.add('done-row');
        btn.classList.add('done-toggle--on');
        btn.title = 'Marquer comme non effectué';
      } else {
        if (row) row.classList.remove('done-row');
        btn.classList.remove('done-toggle--on');
        btn.title = 'Marquer comme effectué';
      }

      /* Mise à jour du compteur "Effectués" dans les chiffres clés */
      const cpt = document.getElementById('cptEffectues');
      if (cpt) {
        cpt.textContent = String(res.nb_effectues);
        /* La classe stat-nb-green applique une couleur verte accessible (WCAG AA) */
        cpt.classList.toggle('stat-nb-green', res.nb_effectues > 0);
      }

      btn.disabled = false;
    })
    .catch(function () {
      /* En cas d'erreur réseau, on réactive simplement le bouton.
         TODO: afficher un toast d'erreur pour informer l'utilisateur. */
      btn.disabled = false;
    });
}


/* ── 4. Toast / Snackbar ──────────────────────────────────────────────── */

let _toastQueue = [];
let _toastQueueRunning = false;

function showToastQueue(queue) {
  if (!Array.isArray(queue) || queue.length === 0) return;
  _toastQueue = _toastQueue.concat(queue);
  if (_toastQueueRunning) return;
  _toastQueueRunning = true;

  const toast = document.getElementById('toast');
  if (!toast) {
    _toastQueue = [];
    _toastQueueRunning = false;
    return;
  }

  function next() {
    if (_toastQueue.length === 0) {
      _toastQueueRunning = false;
      return;
    }

    const item = _toastQueue.shift();
    const onHidden = function () {
      toast.removeEventListener('archilog:toastHidden', onHidden);
      setTimeout(next, 150);
    };
    toast.addEventListener('archilog:toastHidden', onHidden);

    showToast(item.message, item.type);
  }

  next();
}

/**
 * Affiche une notification non-intrusive en bas de l'écran.
 * Remplace toute notification déjà visible.
 *
 * Appelée depuis :
 *   - toast.html  → pour les messages flash Flask (DOMContentLoaded)
 *   - depenses.js → pour les erreurs de soumission AJAX du modal
 *
 * @param {string} message  - Texte à afficher
 * @param {string} type     - "success" | "error" | "info" | "warning"
 */
function showToast(message, type) {
  const toast = document.getElementById('toast');
  const msgEl = document.getElementById('toastMsg');
  const iconEl = document.getElementById('toastIcon');
  const closeBtn = document.getElementById('toastClose');
  if (!toast || !msgEl || !iconEl || !closeBtn) return;

  /* Icônes SVG réutilisant le sprite déjà chargé dans base.html */
  const icons = {
    success: '<svg width="13" height="13"><use href="#icon-check"></use></svg>',
    error:   '<svg width="13" height="13"><use href="#icon-close"></use></svg>',
    info:    'ℹ',
    warning: '<svg width="13" height="13"><use href="#icon-trash-sm"></use></svg>',
  };

  /* Les erreurs restent affichées jusqu'à fermeture manuelle ;
     les autres types disparaissent automatiquement après 3 s. */
  const isError = (type === 'error');
  const delay = isError ? 0 : 3000;

  /* Annule un éventuel timer précédent avant de réafficher */
  if (toast._hideTimer) {
    clearTimeout(toast._hideTimer);
    toast._hideTimer = null;
  }

  /* Reset des classes + reflow pour relancer l'animation CSS si nécessaire.
     void offsetWidth force le navigateur à recalculer le layout avant
     de ré-ajouter les classes, évitant que la transition soit ignorée. */
  toast.classList.remove('toast--success', 'toast--error', 'toast--info', 'toast--visible', 'toast--warning');
  void toast.offsetWidth; // force reflow

  iconEl.innerHTML = icons[type] || icons.info;
  msgEl.textContent = message;
  toast.setAttribute('aria-hidden', 'false');
  toast.classList.add('toast--' + type, 'toast--visible');

  closeBtn.onclick = function () { hideToast(); };

  if (delay > 0) {
    toast._hideTimer = setTimeout(function () { hideToast(); }, delay);
  }
}

/**
 * Masque le toast avec une animation de sortie CSS.
 */
function hideToast() {
  const toast = document.getElementById('toast');
  if (!toast) return;

  if (toast._hideTimer) {
    clearTimeout(toast._hideTimer);
    toast._hideTimer = null;
  }

  toast.classList.remove('toast--visible');
  toast.setAttribute('aria-hidden', 'true');

  try {
    toast.dispatchEvent(new CustomEvent('archilog:toastHidden'));
  } catch (e) {}
}

/* Expose les fonctions utilitaires pour les scripts de page.
   Sans module ES, l'espace window est le seul moyen de partager
   des fonctions entre fichiers chargés séparément. */
window.initCombobox = initCombobox;
window.showToast = showToast;
window.showToastQueue = showToastQueue;
window.toggleRemboursement = toggleRemboursement;