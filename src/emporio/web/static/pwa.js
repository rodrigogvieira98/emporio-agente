// Registra o service worker. Sem suporte, ou fora de HTTPS e localhost, o site segue funcionando normalmente.
(function () {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () { /* sem SW o site funciona igual */ });
  });
})();
