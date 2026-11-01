// Carrossel de destaques. Sem JS, a lista é uma grade rolável (CSS). Com JS, vira um palco: cartão central em
// destaque, vizinhos menores e translúcidos atrás (escala 1, 0,87, 0,74; opacidade 1, 0,55, 0,18), em laço, com
// transição de 0,45 s (zerada em prefers-reduced-motion). Controlado só pela pessoa: nunca avança sozinho.
// Setas, pontos, teclado (setas na região), arrasto ou toque (mais de 40 px) e clique no vizinho para centralizar.
(function () {
  var ESCALAS = [1, 0.87, 0.74], OPACIDADES = [1, 0.55, 0.18], LIMITE_ARRASTO = 40;

  function iniciar(raiz) {
    var itens = Array.prototype.slice.call(raiz.querySelectorAll(".carrossel-item"));
    var controles = raiz.querySelector("[data-controles]");
    var anuncio = raiz.querySelector("[data-anuncio]");
    var lista = raiz.querySelector(".carrossel-lista");
    var total = itens.length;
    if (total < 2 || !lista) return;
    var botoes = controles.querySelectorAll("[data-seta]");
    var pontos = controles.querySelectorAll("[data-ponto]");
    var ativo = 0, inicioX = null, arrastou = false;

    function deslocamento(i) {
      var off = i - ativo;
      if (off > total / 2) off -= total;
      if (off < -total / 2) off += total;
      return off;
    }
    function passoLateral() {
      var largura = itens[0].offsetWidth;
      return Math.min(largura * 0.95, (raiz.clientWidth - largura) / 2 + largura * 0.3);
    }
    function medirAltura() {
      var maior = 0;
      itens.forEach(function (it) { maior = Math.max(maior, it.offsetHeight); });
      lista.style.height = (maior + 8) + "px";
    }
    function desenhar() {
      var passo = passoLateral();
      itens.forEach(function (it, i) {
        var off = deslocamento(i), abs = Math.abs(off), centro = off === 0, visivel = abs <= 2;
        it.style.transform = "translateX(calc(-50% + " + (off * passo) + "px)) scale(" + (ESCALAS[Math.min(abs, 2)]) + ")";
        it.style.opacity = visivel ? OPACIDADES[Math.min(abs, 2)] : 0;
        it.style.zIndex = String(30 - abs * 10);
        it.style.pointerEvents = visivel ? "auto" : "none";
        it.setAttribute("aria-hidden", centro ? "false" : "true");
        it.classList.toggle("e-centro", centro);
        it.querySelectorAll("a, button").forEach(function (a) { a.tabIndex = centro ? 0 : -1; });
      });
      pontos.forEach(function (p, i) {
        if (i === ativo) p.setAttribute("aria-current", "true"); else p.removeAttribute("aria-current");
      });
      if (anuncio) anuncio.textContent = (raiz.getAttribute("data-rotulo-anuncio") || "Em destaque") + ": " + itens[ativo].getAttribute("data-nome") + ", " + (ativo + 1) + " de " + total;
    }
    function ir(i) { ativo = ((i % total) + total) % total; desenhar(); }

    raiz.classList.add("carrossel-ativo");
    controles.hidden = false;
    medirAltura();
    desenhar();
    window.addEventListener("resize", function () { medirAltura(); desenhar(); });
    window.addEventListener("load", function () { medirAltura(); desenhar(); });

    botoes.forEach(function (b) { b.addEventListener("click", function () { ir(ativo + Number(b.getAttribute("data-seta"))); }); });
    pontos.forEach(function (p) { p.addEventListener("click", function () { ir(Number(p.getAttribute("data-ponto"))); }); });

    raiz.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      raiz.focus();  // o foco volta à região antes de trocar, para nunca ficar num cartão que saiu de vista
      ir(ativo + (e.key === "ArrowRight" ? 1 : -1));
    });
    itens.forEach(function (it, i) {
      it.addEventListener("click", function (e) {
        if (arrastou) { arrastou = false; e.preventDefault(); e.stopPropagation(); return; }
        if (i !== ativo) { e.preventDefault(); e.stopPropagation(); ir(i); }  // vizinho: centraliza em vez de abrir
      }, true);
    });
    lista.addEventListener("pointerdown", function (e) { if (e.isPrimary) { inicioX = e.clientX; arrastou = false; } });
    lista.addEventListener("pointerup", function (e) {
      if (!e.isPrimary || inicioX === null) return;
      var dx = e.clientX - inicioX;
      inicioX = null;
      if (Math.abs(dx) <= LIMITE_ARRASTO) return;
      arrastou = true;
      window.setTimeout(function () { arrastou = false; }, 250);  // sem click residual engolindo o próximo toque
      ir(ativo + (dx < 0 ? 1 : -1));
    });
    lista.addEventListener("pointercancel", function () { inicioX = null; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-carrossel]").forEach(iniciar);
  });
})();
