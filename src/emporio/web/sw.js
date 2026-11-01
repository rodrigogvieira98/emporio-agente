// Service worker do site. Servido em /sw.js (escopo raiz). O servidor troca os marcadores abaixo ao entregar o arquivo.
//
// Regra de ouro: preço, estoque, pedido e resposta da Lia nunca saem de cache, porque fato velho é fato errado.
//   - estáticos (CSS, JS, fontes, SVG, ícones): cache-first, pré-cache na instalação;
//   - páginas HTML: network-first; sem rede, a página offline própria (nunca uma página antiga guardada);
//   - /chat, /rastreio, /saude e qualquer método que não seja GET: network-only, nunca em cache.
"use strict";

const VERSAO = "/*VERSAO*/";
const CACHE = "emporio-estaticos-" + VERSAO;
const PAGINA_OFFLINE = "/offline";
const ESTATICOS = /*ESTATICOS*/[];
const SO_REDE = ["/chat", "/rastreio", "/saude"];

function soRede(url) {
  return SO_REDE.some(function (p) { return url.pathname === p || url.pathname.startsWith(p + "/"); });
}
function ehEstatico(url) {
  return url.pathname.startsWith("/static/");
}

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(CACHE)
      .then(function (cache) { return cache.addAll(ESTATICOS.concat([PAGINA_OFFLINE])); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys()
      .then(function (nomes) {
        return Promise.all(nomes.filter(function (n) { return n.startsWith("emporio-") && n !== CACHE; })
          .map(function (n) { return caches.delete(n); }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (evento) {
  var pedido = evento.request;
  var url = new URL(pedido.url);
  if (pedido.method !== "GET" || url.origin !== self.location.origin) return;  // POST e terceiros: direto à rede

  if (pedido.mode === "navigate" || (pedido.headers.get("accept") || "").indexOf("text/html") !== -1) {
    // HTML, inclusive /rastreio: rede primeiro, sem guardar nada; sem rede, a página offline
    evento.respondWith(
      fetch(pedido).catch(function () { return caches.match(PAGINA_OFFLINE); })
    );
    return;
  }
  if (soRede(url)) return;  // /chat, /rastreio, /saude: nunca em cache, nem sob falha
  if (ehEstatico(url)) {
    evento.respondWith(
      caches.match(pedido).then(function (guardado) {
        if (guardado) return guardado;
        return fetch(pedido).then(function (resposta) {
          if (resposta.ok) {
            var copia = resposta.clone();
            caches.open(CACHE).then(function (cache) { cache.put(pedido, copia); });
          }
          return resposta;
        });
      })
    );
  }
});
