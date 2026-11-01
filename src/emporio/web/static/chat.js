// Chat da Lia: guarda só o HTML já escapado das mensagens exibidas, para o painel sobreviver à troca de página.
// O estado da conversa fica no servidor; apagar isto só limpa a tela. O painel começa sempre fechado e nunca abre sozinho.
// Abrir, fechar, Esc e clique fora são do gerenciador único (sobreposicoes.js).
(function () {
  var CHAVE_LOG = "emporio_chat_log";
  function ler(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function gravar(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } }

  document.addEventListener("DOMContentLoaded", function () {
    var raiz = document.getElementById("lia");
    var painel = document.getElementById("chat");
    var botao = document.getElementById("chat-alternar");
    var fechar = document.getElementById("chat-fechar");
    var log = document.getElementById("chat-log");
    var form = document.getElementById("chat-form");
    var campo = document.getElementById("chat-mensagem");
    if (!raiz || !painel || !botao || !log || !form) return;

    var salvo = ler(CHAVE_LOG);
    if (salvo) log.innerHTML = salvo;

    var celular = window.matchMedia("(max-width: 767px)");
    var html = document.documentElement;
    function aberto() { return !painel.hidden; }
    function aplicar(abrir) {
      painel.hidden = !abrir;
      raiz.classList.toggle("lia-aberta", abrir);
      botao.setAttribute("aria-expanded", abrir ? "true" : "false");
      html.classList.toggle("chat-tela-cheia", abrir && celular.matches);  // abaixo de 768px a Lia ocupa a tela
      if (abrir) { log.scrollTop = log.scrollHeight; }
      ajustarAltura();
    }
    // Teclado virtual: o campo fica colado ao teclado seguindo a área visível (iOS não redimensiona o layout).
    var vv = window.visualViewport;
    function ajustarAltura() {
      if (vv && celular.matches && aberto()) {
        html.style.setProperty("--altura-visivel", vv.height + "px");
        html.style.setProperty("--topo-visivel", vv.offsetTop + "px");
      } else {
        html.style.removeProperty("--altura-visivel");
        html.style.removeProperty("--topo-visivel");
      }
    }
    if (vv) { vv.addEventListener("resize", ajustarAltura); vv.addEventListener("scroll", ajustarAltura); }
    celular.addEventListener("change", function () { aplicar(aberto()); });

    var gestor = Sobreposicoes.registrar({
      raiz: raiz, gatilho: botao,
      aberto: aberto,
      abrir: function () { aplicar(true); },
      fechar: function () { aplicar(false); }
    });
    function abrirChat() { Sobreposicoes.abrir(gestor); if (campo) campo.focus(); }
    botao.addEventListener("click", function () { if (aberto()) Sobreposicoes.fechar(gestor); else abrirChat(); });
    if (fechar) fechar.addEventListener("click", function () { Sobreposicoes.fechar(gestor); });

    function avisar(texto) {
      var p = document.createElement("p");
      p.className = "msg aviso-chat";
      p.textContent = texto;
      log.appendChild(p);
      log.scrollTop = log.scrollHeight;
    }
    var SEM_REDE = "Sem conexão. A Lia precisa de internet para responder. Seu texto foi mantido, envie de novo quando a conexão voltar.";

    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (e.target !== log) return;
      log.scrollTop = log.scrollHeight;
      gravar(CHAVE_LOG, log.innerHTML);
    });
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      if (e.target === form && navigator.onLine === false) { e.preventDefault(); avisar(SEM_REDE); }
    });
    document.body.addEventListener("htmx:sendError", function (e) {
      if (e.target === form) avisar(SEM_REDE);  // rede caiu no envio: a Lia não responde de cache nem finge resposta
    });
    document.body.addEventListener("htmx:afterRequest", function (e) {
      if (e.target !== form) return;
      var chegou = e.detail.xhr && e.detail.xhr.status !== 0;
      if (chegou && e.detail.xhr.status !== 503) form.reset();  // ocupada ou sem rede: o texto fica no campo para reenviar
      campo.focus();
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      // respostas 422 e 503 do chat também trazem um fragmento com o aviso
      if (e.detail.xhr && (e.detail.xhr.status === 422 || e.detail.xhr.status === 503) && e.detail.target === log) e.detail.shouldSwap = true;
    });
    function enviar(texto) {
      if (!aberto()) Sobreposicoes.abrir(gestor);
      campo.value = texto || "";
      campo.focus();
      htmx.trigger(form, "submit");
    }
    document.addEventListener("click", function (e) {
      var abrir = e.target.closest && e.target.closest("[data-abrir-chat]");
      if (abrir) { e.preventDefault(); abrirChat(); return; }
      var alvo = e.target.closest && e.target.closest("[data-pergunta], .btn-compra");
      if (!alvo) return;
      enviar(alvo.getAttribute("data-pergunta") || alvo.getAttribute("data-mensagem"));
    });
  });
})();
