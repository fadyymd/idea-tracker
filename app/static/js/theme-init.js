/* Runs synchronously in <head> to apply the saved theme before first paint (no flash). */
(function () {
  try {
    var saved = localStorage.getItem('theme');
    if (!saved && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) saved = 'dark';
    if (saved) document.documentElement.setAttribute('data-bs-theme', saved);
  } catch (e) { /* storage blocked: keep default */ }
})();
