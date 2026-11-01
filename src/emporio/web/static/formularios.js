// Formulários POST do site (carrinho, checkout, rastreio, contato): sem rede, o navegador mostraria uma página de erro
// e o cliente perderia o que digitou. Aqui o envio é barrado de forma síncrona, o formulário fica como está e um aviso
// aparece na própria página, junto do botão. Com rede o envio segue o fluxo normal do navegador, sem atraso.
// O chat (htmx) tem tratamento próprio em chat.js.
(function () {
  var AVISO = "Sem conexão com a loja. Seus dados foram mantidos; envie de novo quando a conexão voltar.";

  function avisar(form, submitter) {
    var p = form.querySelector("[data-aviso-rede]");
    if (!p) {
      p = document.createElement("p");
      p.className = "aviso aviso-erro";
      p.setAttribute("role", "alert");
      p.setAttribute("data-aviso-rede", "");
      p.tabIndex = -1;
      var alvo = submitter || form.querySelector("[type=submit]");
      if (alvo && alvo.parentNode) alvo.parentNode.insertBefore(p, alvo); else form.appendChild(p);
    }
    p.textContent = AVISO;
    p.scrollIntoView({ block: "center" });
    p.focus({ preventScroll: true });
  }

  // Resultado do rastreio: a página já chega com a resposta; rola até ela e leva o foco (teclado e leitor de tela).
  document.addEventListener("DOMContentLoaded", function () {
    var r = document.querySelector("[data-resultado-rastreio]");
    if (!r) return;
    r.scrollIntoView({ block: "start" });
    r.focus({ preventScroll: true });
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches || !form.matches("form") || (form.method || "").toLowerCase() !== "post") return;
    if (form.hasAttribute("hx-post")) return;
    if (navigator.onLine === false) {
      e.preventDefault();
      avisar(form, e.submitter);
    } else {
      var p = form.querySelector("[data-aviso-rede]");
      if (p) p.remove();
    }
  });
})();
