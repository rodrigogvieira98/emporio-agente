// Banner da home: cinco fotos de instrumentos com troca automática suave a cada 6 s (WCAG 2.2.2).
// Sem JS fica só a primeira foto. A pessoa pode pausar e retomar pelo botão; o mouse ou o foco sobre o banner pausam
// por um instante; com prefers-reduced-motion nada troca sozinho; aba oculta para o relógio. Sem região viva: a troca
// automática nunca é anunciada ao leitor de tela. As demais fotos só carregam pouco antes de aparecerem.
(function () {
  var INTERVALO = 6000;

  function iniciar(raiz) {
    var slides = Array.prototype.slice.call(raiz.querySelectorAll("[data-slide]"));
    var botao = raiz.querySelector("[data-pausa]");
    var total = slides.length;
    if (total < 2) return;
    var ativo = 0, relogio = null, pausadoPelaPessoa = false, pausadoTemporario = false;
    var reduzido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function carregar(i) {
      var img = slides[((i % total) + total) % total].querySelector("img[data-src]");
      if (img) { img.src = img.getAttribute("data-src"); img.removeAttribute("data-src"); }
    }
    function mostrar(i) {
      ativo = ((i % total) + total) % total;
      carregar(ativo);
      slides.forEach(function (s, k) {
        s.classList.toggle("e-ativo", k === ativo);
        if (k === ativo) s.removeAttribute("aria-hidden"); else s.setAttribute("aria-hidden", "true");
      });
      carregar(ativo + 1);
    }
    function parar() { if (relogio !== null) { window.clearInterval(relogio); relogio = null; } }
    function atualizar() {
      parar();
      if (reduzido || pausadoPelaPessoa || pausadoTemporario || document.hidden) return;
      relogio = window.setInterval(function () { mostrar(ativo + 1); }, INTERVALO);
    }

    if (botao) {
      botao.hidden = reduzido;  // sem troca automática não há o que pausar
      botao.addEventListener("click", function () {
        pausadoPelaPessoa = !pausadoPelaPessoa;
        botao.setAttribute("aria-pressed", pausadoPelaPessoa ? "true" : "false");
        botao.setAttribute("aria-label", pausadoPelaPessoa ? "Retomar a troca de fotos" : "Pausar a troca de fotos");
        atualizar();
      });
    }
    // só mouse e caneta: um toque no celular não deve deixar o banner preso em pausa
    raiz.addEventListener("pointerenter", function (e) { if (e.pointerType !== "touch") { pausadoTemporario = true; atualizar(); } });
    raiz.addEventListener("pointerleave", function (e) { if (e.pointerType !== "touch") { pausadoTemporario = false; atualizar(); } });
    raiz.addEventListener("focusin", function () { pausadoTemporario = true; atualizar(); });
    raiz.addEventListener("focusout", function () { pausadoTemporario = false; atualizar(); });
    document.addEventListener("visibilitychange", atualizar);

    carregar(1);
    atualizar();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-banner]").forEach(iniciar);
  });
})();
