// Gerenciador único de elementos abertos sobre a página (menu de categorias, filtros recolhidos, painel da Lia).
// Regras para todos: abrir um fecha os outros; clique ou toque fora fecha; Esc fecha; o foco volta a quem abriu;
// clique dentro não fecha. Elementos <details data-sobreposicao> são descobertos sozinhos (gatilho = [data-gatilho],
// painel = [data-painel]); outros se registram com Sobreposicoes.registrar({raiz, gatilho, aberto, abrir, fechar}).
// Com data-so-celular, o elemento só se comporta como sobreposição abaixo de 900px (no desktop fica sempre aberto).
(function () {
  var lista = [];
  var largo = window.matchMedia("(min-width: 900px)");

  function ativo(o) { return !(o.raiz.hasAttribute("data-so-celular") && largo.matches); }
  function interativo(el) {
    return !!(el && el.closest && el.closest("a[href], button, input, select, textarea, summary, label, [tabindex]"));
  }
  function fechar(o, devolverFoco) {
    if (!o.aberto()) return;
    o.fechar();
    if (devolverFoco && o.gatilho) o.gatilho.focus();
  }
  function fecharOutros(mantem) {
    lista.forEach(function (o) { if (o !== mantem && ativo(o)) fechar(o, false); });
  }
  function registrar(o) {
    lista.push(o);
    return o;
  }
  function abrir(o) {
    fecharOutros(o);
    o.abrir();
  }

  function detalhes(raiz) {
    var gatilho = raiz.querySelector("[data-gatilho]");
    var o = registrar({
      raiz: raiz, gatilho: gatilho,
      aberto: function () { return raiz.open; },
      abrir: function () { raiz.open = true; },
      fechar: function () { raiz.open = false; }
    });
    raiz.addEventListener("toggle", function () { if (raiz.open && ativo(o)) fecharOutros(o); });
    function sincronizar() {  // desktop: filtros sempre visíveis; celular: recolhidos, abertos só se já há filtro aplicado
      if (!raiz.hasAttribute("data-so-celular")) return;
      raiz.open = largo.matches || raiz.hasAttribute("data-filtrado");
    }
    sincronizar();
    largo.addEventListener("change", sincronizar);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("details[data-sobreposicao]").forEach(detalhes);
  });

  document.addEventListener("click", function (e) {
    lista.forEach(function (o) {
      if (!ativo(o) || !o.aberto() || o.raiz.contains(e.target)) return;
      if (document.documentElement.classList.contains("chat-tela-cheia") && o.raiz.hasAttribute("data-lia")) return;
      fechar(o, !interativo(e.target));
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" && e.key !== "Esc") return;
    var fechou = false;
    lista.forEach(function (o) {
      if (ativo(o) && o.aberto()) { fechar(o, !fechou); fechou = true; }
    });
  });

  window.Sobreposicoes = { registrar: registrar, abrir: abrir, fechar: function (o) { fechar(o, true); } };
})();
