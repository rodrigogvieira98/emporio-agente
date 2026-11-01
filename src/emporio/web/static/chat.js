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
    var log = document.getElementById("chat-log");
    var form = document.getElementById("chat-form");
    var campo = document.getElementById("chat-mensagem");
    if (!raiz || !painel || !botao || !log || !form) return;

    var salvo = ler(CHAVE_LOG);
    if (salvo) log.innerHTML = salvo;
    log.querySelectorAll(".escrevendo").forEach(function (n) { n.remove(); });  // nunca restaura uma bolha de escrevendo

    var celular = window.matchMedia("(max-width: 767px), (max-height: 520px) and (pointer: coarse)");  // celular em pé ou deitado
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
      if (vv && aberto()) {  // qualquer orientação: o painel nunca passa da área visível
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
    // Sugestões saem de cena com o campo em foco (o teclado ocupa a tela) e depois da primeira mensagem do cliente.
    var corpo = document.getElementById("chat-corpo");
    function marcarConversa() {
      var conversou = !!log.querySelector(".msg.voce");
      if (corpo) corpo.classList.toggle("ja-conversou", conversou);
    }
    marcarConversa();
    if (campo && corpo) {
      campo.addEventListener("focus", function () { if (celular.matches) corpo.classList.add("campo-em-foco"); });
      campo.addEventListener("blur", function () { corpo.classList.remove("campo-em-foco"); });
    }
    // Foco contido na Lia aberta em tela cheia: Tab e Shift+Tab circulam só pelo painel.
    painel.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || !aberto() || !html.classList.contains("chat-tela-cheia")) return;
      var itens = Array.prototype.filter.call(painel.querySelectorAll("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])"),
        function (n) { return !n.disabled && n.offsetParent !== null; });
      if (!itens.length) return;
      var primeiro = itens[0], ultimo = itens[itens.length - 1];
      if (e.shiftKey && (document.activeElement === primeiro || document.activeElement === painel)) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
    });
    var camada = document.getElementById("lia-camada");
    if (camada) camada.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); Sobreposicoes.fechar(gestor); });

    // no celular o campo não ganha foco ao abrir: o teclado não cobre a conversa nem as sugestões antes da hora
    function abrirChat() {
      Sobreposicoes.abrir(gestor);
      if (!campo) return;
      if (!celular.matches) { campo.focus(); return; }
      painel.setAttribute("tabindex", "-1");  // o foco entra no painel (sem teclado) e o Tab circula só dentro dele
      painel.focus({ preventScroll: true });
    }
    botao.addEventListener("click", function () { if (aberto()) Sobreposicoes.fechar(gestor); else abrirChat(); });
    // Celular: o toque na faixa da página acima do painel só fecha a Lia; não aciona o que está por baixo.
    document.addEventListener("click", function (e) {
      if (!aberto() || !html.classList.contains("chat-tela-cheia") || raiz.contains(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      Sobreposicoes.fechar(gestor);
    }, true);

    function avisar(texto) {
      var p = document.createElement("p");
      p.className = "msg aviso-chat";
      p.textContent = texto;
      log.appendChild(p);
      log.scrollTop = log.scrollHeight;
    }
    var SEM_REDE = "Sem conexão. A Lia precisa de internet para responder. Seu texto foi mantido, envie de novo quando a conexão voltar.";

    // Ritmo da conversa: depois da bolha do cliente aparece "Lia está escrevendo"; a resposta chega do servidor, mas só
    // entra no lugar dessa bolha depois de min(700 + 15 ms por caractere, 2200 ms) contados desde o envio. Só no navegador.
    var TEMPO_BASE = 700, TEMPO_CHAR = 15, TEMPO_MAX = 2200;
    var escrevendo = null, envioEm = 0, esperando = false, temporizador = null;
    function salvar() {  // o histórico guardado nunca leva a bolha de escrevendo
      var c = log.cloneNode(true);
      c.querySelectorAll(".escrevendo").forEach(function (n) { n.remove(); });
      gravar(CHAVE_LOG, c.innerHTML);
    }
    function mostrarEscrevendo() {
      var p = document.createElement("p");
      p.className = "msg lia escrevendo";
      p.innerHTML = '<span class="so-leitor">Lia está escrevendo</span><span class="pontos" aria-hidden="true"><i></i><i></i><i></i></span>';
      log.appendChild(p);
      log.scrollTop = log.scrollHeight;
      escrevendo = p; envioEm = Date.now(); esperando = true;
    }
    function tirarEscrevendo() {
      if (temporizador) { clearTimeout(temporizador); temporizador = null; }
      if (escrevendo && escrevendo.parentNode) escrevendo.parentNode.removeChild(escrevendo);
      escrevendo = null; esperando = false;
    }
    function entregar(html, espera) {
      temporizador = setTimeout(function () {
        temporizador = null;
        if (escrevendo && escrevendo.parentNode) escrevendo.parentNode.removeChild(escrevendo);
        escrevendo = null; esperando = false;
        log.insertAdjacentHTML("beforeend", html);
        if (window.htmx) window.htmx.process(log);
        log.scrollTop = log.scrollHeight;
        salvar();
      }, Math.max(0, espera));
    }

    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (e.target !== log) return;
      log.scrollTop = log.scrollHeight;
      salvar();
    });
    // Bolha otimista: a mensagem aparece no log ao enviar e o campo é limpo; falha desfaz as duas coisas.
    var pendente = null;
    function desfazerPendente() {
      if (!pendente) return;
      if (pendente.bolha.parentNode) pendente.bolha.parentNode.removeChild(pendente.bolha);
      marcarConversa();
      campo.value = pendente.texto;
      pendente = null;
    }
    function semBolhaDoUsuario(html) {  // o servidor devolve a bolha do usuário para clientes sem JS; aqui ela já existe
      var t = document.createElement("template");
      t.innerHTML = html;
      t.content.querySelectorAll(".msg.voce").forEach(function (n) { n.remove(); });
      return t.innerHTML;
    }
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      if (e.target !== form) return;
      if (esperando) { e.preventDefault(); return; }  // a Lia ainda está "escrevendo" a resposta anterior
      if (navigator.onLine === false) { e.preventDefault(); avisar(SEM_REDE); return; }
      var texto = campo.value;
      if (!texto.trim()) return;
      var bolha = document.createElement("p");
      bolha.className = "msg voce";
      bolha.textContent = texto;
      log.appendChild(bolha);
      log.scrollTop = log.scrollHeight;
      pendente = { bolha: bolha, texto: texto };
      mostrarEscrevendo();
      if (corpo) corpo.classList.add("ja-conversou");
      campo.value = "";
    });
    document.body.addEventListener("htmx:sendError", function (e) {
      if (e.target !== form) return;
      tirarEscrevendo();
      avisar(SEM_REDE);  // rede caiu no envio: a Lia não responde de cache nem finge resposta
    });
    document.body.addEventListener("htmx:afterRequest", function (e) {
      if (e.target !== form) return;
      if (pendente) tirarEscrevendo();
      desfazerPendente();  // sem resposta aproveitada (sem rede, ocupada, inválida): a bolha sai e o texto volta ao campo
      campo.focus();
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      // respostas 422 e 503 do chat também trazem um fragmento com o aviso
      if (e.detail.target !== log || !e.detail.xhr) return;
      var status = e.detail.xhr.status;
      if (status === 422 || status === 503) {
        e.detail.shouldSwap = true;
        tirarEscrevendo();
        desfazerPendente();
        e.detail.serverResponse = semBolhaDoUsuario(e.detail.serverResponse);
      } else if (status >= 200 && status < 300 && pendente) {
        var corrigido = semBolhaDoUsuario(e.detail.serverResponse);
        pendente = null;  // a bolha otimista fica como a mensagem do cliente
        var t = document.createElement("template");
        t.innerHTML = corrigido;
        var minimo = Math.min(TEMPO_BASE + TEMPO_CHAR * t.content.textContent.trim().length, TEMPO_MAX);
        e.detail.shouldSwap = false;  // a troca é feita por nós, quando o tempo mínimo de "escrevendo" passar
        entregar(corrigido, minimo - (Date.now() - envioEm));
      }
    });
    // Sugestão e "Quero comprar" só preparam a conversa: abrem o painel, preenchem o campo e põem o foco nele.
    // A mensagem sai quando o cliente envia (Enter ou botão Enviar), e o texto pode ser editado antes.
    function preencher(texto) {
      if (!aberto()) Sobreposicoes.abrir(gestor);
      campo.value = texto || "";
      campo.focus();
      campo.setSelectionRange(campo.value.length, campo.value.length);
    }
    document.addEventListener("click", function (e) {
      var abrir = e.target.closest && e.target.closest("[data-abrir-chat]");
      if (abrir) { e.preventDefault(); abrirChat(); return; }
      var alvo = e.target.closest && e.target.closest("[data-pergunta], .btn-compra");
      if (!alvo) return;
      preencher(alvo.getAttribute("data-pergunta") || alvo.getAttribute("data-mensagem"));
    });
  });
})();
