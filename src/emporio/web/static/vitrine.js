// Vitrine: o carrossel funciona sem JS (scroll-snap e setas do teclado com o trilho focado).
// Aqui só entram as setas visíveis, como realce progressivo.
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var trilho = document.querySelector("[data-trilho]");
    var setas = document.querySelector("[data-setas]");
    if (!trilho || !setas) return;
    var botoes = setas.querySelectorAll("[data-seta]");
    var calmo = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function passo() {
      var item = trilho.querySelector(".vitrine-item");
      if (!item) return trilho.clientWidth;
      var gap = parseFloat(getComputedStyle(item.parentElement).columnGap) || 0;
      return item.getBoundingClientRect().width + gap;
    }
    function atualizar() {
      var max = trilho.scrollWidth - trilho.clientWidth - 1;
      botoes[0].disabled = trilho.scrollLeft <= 0;
      botoes[1].disabled = trilho.scrollLeft >= max;
    }
    botoes.forEach(function (b) {
      b.addEventListener("click", function () {
        var dir = Number(b.getAttribute("data-seta"));
        trilho.scrollBy({ left: dir * passo(), behavior: calmo ? "auto" : "smooth" });
      });
    });
    trilho.addEventListener("scroll", atualizar, { passive: true });
    window.addEventListener("resize", atualizar);
    setas.hidden = false;
    atualizar();
  });
})();
