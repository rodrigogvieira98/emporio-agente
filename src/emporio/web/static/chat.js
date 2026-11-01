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

    function definir(aberto) {
      corpo.hidden = !aberto;
      botao.setAttribute("aria-expanded", aberto ? "true" : "false");
      gravar(CHAVE_ABERTO, aberto ? "1" : "0");
    }
    var guardado = ler(CHAVE_ABERTO);
    definir(guardado === null ? window.innerWidth > 700 : guardado === "1");
    botao.addEventListener("click", function () { definir(corpo.hidden); });

    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (e.target !== log) return;
      log.scrollTop = log.scrollHeight;
      gravar(CHAVE_LOG, log.innerHTML);
    });
    document.body.addEventListener("htmx:afterRequest", function (e) {
      if (e.target === form) { form.reset(); campo.focus(); }
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      // respostas 422 do chat também trazem um fragmento com o aviso
      if (e.detail.xhr && e.detail.xhr.status === 422 && e.detail.target === log) e.detail.shouldSwap = true;
    });
    document.addEventListener("click", function (e) {
      var alvo = e.target.closest && e.target.closest(".btn-compra");
      if (!alvo) return;
      definir(true);
      campo.value = alvo.getAttribute("data-mensagem") || "";
      htmx.trigger(form, "submit");
    });
  });
})();
