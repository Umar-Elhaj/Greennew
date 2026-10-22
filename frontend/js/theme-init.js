/* GREEN — theme applied before the first paint (loaded synchronously in <head>
   on every page): saved choice, otherwise the operating system preference.
   Same rule as ThemeManager.init() in utils.js. */
(function () {
  var saved = null;
  try { saved = localStorage.getItem('green_theme'); } catch (_) { /* storage blocked */ }
  var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.setAttribute('data-theme', saved || (dark ? 'dark' : 'light'));
})();
