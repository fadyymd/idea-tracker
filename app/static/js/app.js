(function () {
  'use strict';

  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  /* ---------------- theme toggle ---------------- */
  var themeBtn = document.getElementById('theme-toggle');
  function syncThemeIcon() {
    if (!themeBtn) return;
    var dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    themeBtn.innerHTML = dark ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
    themeBtn.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  }
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-bs-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      syncThemeIcon();
      document.dispatchEvent(new CustomEvent('themechange'));
    });
    syncThemeIcon();
  }

  /* ---------------- flash messages as toasts ---------------- */
  document.querySelectorAll('.toast').forEach(function (el) {
    var delay = el.classList.contains('toast-danger') ? 9000 : 5000;
    new bootstrap.Toast(el, { delay: delay }).show();
  });

  /* ---------------- toast helper for JS-originated messages ---------------- */
  function notify(text, kind) {
    var stack = document.getElementById('toast-stack');
    if (!stack) return;
    var el = document.createElement('div');
    el.className = 'toast toast-' + (kind || 'warning');
    el.setAttribute('role', 'alert');
    el.innerHTML = '<div class="d-flex align-items-center gap-2 p-3"><i class="bi bi-exclamation-circle-fill toast-icon"></i>' +
      '<div class="flex-grow-1"></div><button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button></div>';
    el.querySelector('.flex-grow-1').textContent = text;
    stack.appendChild(el);
    var t = new bootstrap.Toast(el, { delay: 4500 });
    el.addEventListener('hidden.bs.toast', function () { el.remove(); });
    t.show();
  }

  /* ---------------- confirm + loading state on forms ---------------- */
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    var msg = form.getAttribute && form.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) { ev.preventDefault(); return; }
    var btn = ev.submitter || form.querySelector('button[type="submit"]');
    if (btn && form.hasAttribute('data-loading') && !btn.classList.contains('is-loading')) {
      // let the browser serialise the form first, then lock the button to prevent double submits
      setTimeout(function () {
        btn.classList.add('is-loading');
        btn.setAttribute('aria-busy', 'true');
        btn.insertAdjacentHTML('afterbegin', '<span class="spinner-border me-2" aria-hidden="true"></span>');
      }, 0);
    }
  });

  /* ---------------- auto-submit filter selects ---------------- */
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form.submit(); });
  });

  /* ---------------- AJAX voting ---------------- */
  function applyVote(box, data) {
    var scoreEl = box.querySelector('.vote-score');
    if (scoreEl) scoreEl.textContent = data.score;
    box.querySelector('.vote-up').classList.toggle('active', data.my_vote === 1);
    box.querySelector('.vote-down').classList.toggle('active', data.my_vote === -1);
    box.classList.remove('bump'); void box.offsetWidth; box.classList.add('bump');

    var up = document.querySelector('[data-up]');
    var down = document.querySelector('[data-down]');
    var side = document.getElementById('side-score');
    var bar = document.getElementById('ratio-up');
    if (up) up.textContent = data.upvotes;
    if (down) down.textContent = data.downvotes;
    if (side) side.textContent = data.score;
    if (bar) {
      var total = data.upvotes + data.downvotes;
      bar.style.width = (total ? Math.round(100 * data.upvotes / total) : 0) + '%';
      var down_bar = document.getElementById('ratio-down');
      if (down_bar) down_bar.style.width = (total ? 100 - Math.round(100 * data.upvotes / total) : 0) + '%';
    }
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.vote-btn');
    if (!btn || btn.disabled) return;
    var box = btn.closest('.vote-box');
    if (!box || box.classList.contains('pending')) return;
    box.classList.add('pending');

    fetch(box.dataset.voteUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrf,
        'X-Requested-With': 'fetch',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      credentials: 'same-origin',
      body: new URLSearchParams({ value: btn.dataset.value }).toString()
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; });
    }).then(function (r) {
      if (r.res.status === 401 && r.data.login) {
        window.location.href = r.data.login + '?next=' + encodeURIComponent(window.location.pathname);
      } else if (!r.res.ok) {
        notify(r.data.error || 'Could not register your vote.', 'warning');
      } else {
        applyVote(box, r.data);
      }
    }).catch(function () {
      notify('Network error. Please try again.', 'danger');
    }).then(function () {
      box.classList.remove('pending');
    });
  });

  /* ---------------- threaded replies + counters ---------------- */
  var form = document.getElementById('comment-form');
  if (form) {
    var parentInput = form.querySelector('input[name="parent_id"]');
    var banner = document.getElementById('reply-banner');
    var author = document.getElementById('reply-author');
    var textarea = form.querySelector('textarea');

    function setReply(id, name) {
      parentInput.value = id || '';
      var on = !!id;
      banner.classList.toggle('d-none', !on);
      banner.classList.toggle('d-flex', on);
      if (on) author.textContent = name;
    }
    document.addEventListener('click', function (ev) {
      var reply = ev.target.closest('.reply-btn');
      if (reply) {
        setReply(reply.dataset.parent, reply.dataset.author);
        form.scrollIntoView({ behavior: 'smooth', block: 'center' });
        textarea.focus();
      }
      if (ev.target.closest('#cancel-reply')) setReply('', '');
    });
  }
  document.querySelectorAll('[data-counter]').forEach(function (input) {
    var target = document.getElementById(input.getAttribute('data-counter'));
    if (!target) return;
    var update = function () { target.textContent = input.value.length; };
    input.addEventListener('input', update);
    update();
  });

  /* ---------------- copy link ---------------- */
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-copy') || window.location.href;
      var done = function () { notify('Link copied to clipboard.', 'success'); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url).then(done, function () { window.prompt('Copy this link:', url); });
      } else {
        window.prompt('Copy this link:', url);
      }
    });
  });

  /* ---------------- back-to-top ---------------- */
  var toTop = document.getElementById('to-top');
  if (toTop) {
    window.addEventListener('scroll', function () { toTop.classList.toggle('show', window.scrollY > 600); }, { passive: true });
    toTop.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
  }

  /* ---------------- admin charts (theme-aware) ---------------- */
  var dataEl = document.getElementById('chart-data');
  if (dataEl && window.Chart) {
    var payload = JSON.parse(dataEl.textContent);
    var charts = [];
    var css = function (name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); };

    var build = function () {
      charts.forEach(function (c) { c.destroy(); });
      charts = [];
      var text = css('--text-muted'), grid = css('--line');
      Chart.defaults.color = text;
      Chart.defaults.font.family = css('--bs-body-font-family') || 'sans-serif';

      var statusCanvas = document.getElementById('statusChart');
      if (statusCanvas) {
        charts.push(new Chart(statusCanvas, {
          type: 'doughnut',
          data: {
            labels: payload.status.map(function (s) { return s.label; }),
            datasets: [{
              data: payload.status.map(function (s) { return s.count; }),
              backgroundColor: ['--st-pending', '--st-under_review', '--st-approved', '--st-rejected', '--st-implemented'].map(css),
              borderColor: css('--surface'), borderWidth: 3
            }]
          },
          options: { cutout: '68%', plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } } }
        }));
      }
      var catCanvas = document.getElementById('categoryChart');
      if (catCanvas) {
        charts.push(new Chart(catCanvas, {
          type: 'bar',
          data: {
            labels: payload.categories.map(function (c) { return c.label; }),
            datasets: [{ label: 'Ideas', data: payload.categories.map(function (c) { return c.count; }), backgroundColor: css('--brand'), borderRadius: 8, maxBarThickness: 36 }]
          },
          options: {
            plugins: { legend: { display: false } },
            scales: {
              y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: grid } },
              x: { grid: { display: false } }
            }
          }
        }));
      }
    };
    build();
    document.addEventListener('themechange', build);
  }
})();
