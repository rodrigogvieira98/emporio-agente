// Chat da Lia: guarda só o HTML já escapado das mensagens exibidas, para o painel sobreviver à troca de página.
// O estado da conversa fica no servidor; apagar isto só limpa a tela.
(function () {
  var CHAVE_LOG = "emporio_chat_log", CHAVE_ABERTO = "emporio_chat_aberto";
  function ler(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function gravar(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } }

  document.addEventListener("DOMContentLoaded", function () {
    var log = document.getElementById("chat-log");
    var corpo = document.getElementById("chat-corpo");
    var botao = document.getElementById("chat-alternar");
    var form = document.getElementById("chat-form");
    var campo = document.getElementById("chat-mensagem");
    if (!log || !corpo || !botao || !form) return;

    var salvo = ler(CHAVE_LOG);
    if (salvo) log.innerHTML = salvo;
    log.scrollTop = log.scrollHeight;

    var celular = window.matchMedia("(max-width: 767px)");
    var raiz = document.documentElement;
    function definir(aberto) {
      corpo.hidden = !aberto;
      botao.setAttribute("aria-expanded", aberto ? "true" : "false");
      raiz.classList.toggle("chat-tela-cheia", aberto && celular.matches);  // abaixo de 768px a Lia ocupa a tela
      gravar(CHAVE_ABERTO, aberto ? "1" : "0");
    }
    celular.addEventListener("change", function () { definir(!corpo.hidden); });

    // Teclado virtual: o campo fica colado ao teclado seguindo a área visível (iOS não redimensiona o layout).
    var vv = window.visualViewport;
    function ajustarAltura() {
      if (vv && celular.matches && !corpo.hidden) {
        raiz.style.setProperty("--altura-visivel", vv.height + "px");
        raiz.style.setProperty("--topo-visivel", vv.offsetTop + "px");
      } else {
        raiz.style.removeProperty("--altura-visivel");
        raiz.style.removeProperty("--topo-visivel");
      }
    }
    if (vv) { vv.addEventListener("resize", ajustarAltura); vv.addEventListener("scroll", ajustarAltura); }
    new MutationObserver(ajustarAltura).observe(corpo, { attributes: true, attributeFilter: ["hidden"] });

    function avisar(texto) {
      var p = document.createElement("p");
      p.className = "msg aviso-chat";
      p.textContent = texto;
      log.appendChild(p);
      log.scrollTop = log.scrollHeight;
    }
    var SEM_REDE = "Sem conexão. A Lia precisa de internet para responder. Seu texto foi mantido, envie de novo quando a conexão voltar.";
    var guardado = ler(CHAVE_ABERTO);
    // a homepage abre com o chat fechado, para a vitrine aparecer inteira; nas demais páginas, aberto no desktop
    var padrao = window.innerWidth >= 768 && !document.body.hasAttribute("data-home");
    definir(guardado === null ? padrao : guardado === "1");
    botao.addEventListener("click", function () { definir(corpo.hidden); });

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
      if (chegou) form.reset();  // sem resposta, o texto digitado fica para reenviar
      campo.focus();
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      // respostas 422 do chat também trazem um fragmento com o aviso
      if (e.detail.xhr && e.detail.xhr.status === 422 && e.detail.target === log) e.detail.shouldSwap = true;
    });
    document.addEventListener("click", function (e) {
      var abrir = e.target.closest && e.target.closest("[data-abrir-chat]");
      if (abrir) { e.preventDefault(); definir(true); campo.focus(); return; }
      var pergunta = e.target.closest && e.target.closest("[data-pergunta]");
      if (pergunta) {  // abre o chat já preenchido; quem decide enviar é o cliente
        definir(true);
        campo.value = pergunta.getAttribute("data-pergunta") || "";
        campo.focus();
        return;
      }
      var alvo = e.target.closest && e.target.closest(".btn-compra");
      if (!alvo) return;
      definir(true);
      campo.value = alvo.getAttribute("data-mensagem") || "";
      htmx.trigger(form, "submit");
    });
  });
})();
