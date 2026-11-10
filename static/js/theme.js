/* Menyelaraskan tema Bootstrap (dropdown, modal, dll.) dengan tema perangkat. CSS sendiri memakai prefers-color-scheme. */
(function () {
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  function apply() { document.documentElement.setAttribute('data-bs-theme', mq.matches ? 'dark' : 'light'); }
  apply();
  if (mq.addEventListener) mq.addEventListener('change', apply);
  else if (mq.addListener) mq.addListener(apply);
})();
