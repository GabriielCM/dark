/*
 * Painel local. A maquina pode estar sem rede: nada de CDN nem build.
 *
 * Na pagina da producao:
 * - as etapas sao uma lista que expande ao clicar; `?abrir=<etapa>` abre uma
 *   direto (e o link que o aviso do Windows usa);
 * - o estado das etapas se atualiza sozinho, sem redesenhar o que o revisor
 *   esta preenchendo;
 * - na grade de imagens, o que se digita num cartao e salvo sozinho.
 */
(function () {
  "use strict";

  var ESTADO_INTERVALO = 4000;
  var GRADE_INTERVALO = 5000;
  var SALVAR_ESPERA = 600;

  // -- utilidades ------------------------------------------------------------

  function json(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? "{}" : JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  }

  function hora() {
    var d = new Date();
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  function duracao(s) {
    if (!s) return "—";
    s = Number(s);
    if (s < 60) return Math.round(s) + "s";
    var m = Math.floor(s / 60), r = Math.floor(s % 60);
    if (m < 60) return m + "m " + ("0" + r).slice(-2) + "s";
    return Math.floor(m / 60) + "h " + ("0" + (m % 60)).slice(-2) + "m";
  }

  function selo(e) {
    var map = {
      done: ["ok", "concluída"], skipped: ["ok", "retomada"], running: ["info", "rodando"],
      failed: ["erro", "falhou"], pending: ["", "na fila"],
    };
    var par = map[e.estado] || ["", e.estado];
    if (e.estado === "blocked") par = e.com_o_claude ? ["info", "com o Claude"] : ["atencao", "precisa de você"];
    return '<span class="etiqueta ' + par[0] + '">' + par[1] + "</span>";
  }

  function progresso(e) {
    var p = e.progresso_etapa;
    if (!p || !p.total) return "";
    return '<span class="barra"><span style="width:' + (p.pct || 0) + '%"></span></span> ' +
      '<span class="mono">' + p.feitas + "/" + p.total + "</span>";
  }

  // Confirmacao para acoes destrutivas (tambem nos corpos carregados depois).
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (form.dataset && form.dataset.confirmar && !window.confirm(form.dataset.confirmar)) {
      ev.preventDefault();
    }
  });

  // -- pagina da producao ----------------------------------------------------

  var VIDEO = document.body.dataset.video;
  if (!VIDEO) return;

  var ultimoEstado = {};
  var salvando = 0;
  var esperas = {};

  function corpoDe(nome) {
    return document.querySelector('#etapa-' + nome + ' .etapa-corpo');
  }

  function ocupado(el) {
    if (!el) return false;
    if (salvando > 0 || Object.keys(esperas).length) return true;
    if (el.contains(document.activeElement) && document.activeElement !== document.body) return true;
    if (!document.querySelector("[data-lightbox]").hidden) return true;
    var videos = el.querySelectorAll("video");
    for (var i = 0; i < videos.length; i++) if (!videos[i].paused) return true;
    return false;
  }

  function carregarCorpo(nome, forcar) {
    var el = corpoDe(nome);
    if (!el) return Promise.resolve();
    if (el.dataset.carregado && !forcar) return Promise.resolve();
    return fetch(el.dataset.corpo)
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (html === null) return;
        el.innerHTML = html;
        el.dataset.carregado = "1";
        atualizarBarraGrade();
      })
      .catch(function () { /* offline: tenta de novo quando abrir */ });
  }

  document.querySelectorAll("details.etapa").forEach(function (det) {
    det.addEventListener("toggle", function () {
      if (!det.open) return;
      var nome = det.dataset.etapa;
      carregarCorpo(nome);
      var url = new URL(window.location.href);
      url.searchParams.set("abrir", nome);
      url.hash = "etapa-" + nome;
      history.replaceState(null, "", url.toString());
    });
  });

  // Link direto: abre e rola ate a etapa pedida.
  (function abrirInicial() {
    var alvo = document.body.dataset.aberta;
    if (!alvo) return;
    var el = document.getElementById(alvo === "perguntas" ? "perguntas" : "etapa-" + alvo);
    if (!el) return;
    if (el.tagName === "DETAILS") el.open = true;
    setTimeout(function () { el.scrollIntoView({ behavior: "smooth", block: "start" }); }, 60);
  })();

  function aplicarEstado(p) {
    var geral = document.querySelector('[data-campo="progresso-geral"]');
    if (geral) geral.textContent = p.progresso;
    var custo = document.querySelector('[data-campo="custo"]');
    if (custo && p.custo !== undefined) custo.textContent = "US$ " + Number(p.custo).toFixed(4);

    var chip = document.querySelector('[data-campo="precisa"]');
    if (chip) {
      var alvo = p.precisa_de_voce;
      chip.hidden = !alvo;
      if (alvo) {
        var etapa = p.etapas.filter(function (e) { return e.nome === alvo; })[0];
        var link = chip.querySelector('[data-campo="precisa-link"]');
        link.href = "?abrir=" + alvo + "#etapa-" + alvo;
        link.textContent = (etapa ? etapa.rotulo : alvo) + " →";
      }
    }

    p.etapas.forEach(function (e) {
      var det = document.getElementById("etapa-" + e.nome);
      var ponto = document.querySelector('[data-ponto="' + e.nome + '"]');
      if (ponto) ponto.dataset.estado = e.precisa_de_voce ? "precisa" : e.estado;
      if (!det) return;
      det.dataset.estado = e.estado;
      det.querySelector('[data-campo="selo"]').innerHTML = selo(e);
      det.querySelector('[data-campo="resumo"]').textContent = e.resumo || e.erro || "";
      det.querySelector('[data-campo="progresso"]').innerHTML = progresso(e);
      det.querySelector('[data-campo="tempo"]').textContent = duracao(e.duracao_s);

      var chave = e.estado + "|" + (e.resumo || "");
      var antes = ultimoEstado[e.nome];
      ultimoEstado[e.nome] = chave;
      if (antes !== undefined && antes !== chave && det.open) {
        var corpo = corpoDe(e.nome);
        if (corpo && corpo.dataset.carregado && !ocupado(corpo)) carregarCorpo(e.nome, true);
      }
    });
  }

  function cicloEstado() {
    if (document.hidden) { setTimeout(cicloEstado, ESTADO_INTERVALO); return; }
    fetch("/api/videos/" + encodeURIComponent(VIDEO) + "/estado")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (p) { if (p) aplicarEstado(p); })
      .catch(function () {})
      .finally(function () { setTimeout(cicloEstado, ESTADO_INTERVALO); });
  }
  setTimeout(cicloEstado, ESTADO_INTERVALO);

  // -- grade de imagens ------------------------------------------------------

  function grade() { return document.querySelector("[data-grade]"); }

  function cartaoDe(el) { return el.closest(".cartao-imagem"); }

  function campo(cartao, nome) { return cartao.querySelector('[data-campo="' + nome + '"]'); }

  function atualizarBarraGrade() {
    var g = grade();
    if (!g) return;
    var marcadas = g.querySelectorAll("[data-refazer]:checked:not(:disabled)").length;
    var barra = g.querySelector("[data-barra-grade]");
    barra.querySelector('[data-campo="marcadas"]').textContent = marcadas + " marcada(s)";
    var enviar = barra.querySelector('[data-acao="enviar"]');
    enviar.disabled = marcadas === 0;
    enviar.textContent = marcadas ? "Enviar pedidos (" + marcadas + ")" : "Enviar pedidos";
    var aprovar = barra.querySelector('[data-acao="aprovar"]');
    if (marcadas > 0) { aprovar.disabled = true; aprovar.title = "envie ou desmarque as imagens marcadas"; }
    g.querySelectorAll("details.secao").forEach(function (sec) {
      var n = sec.querySelectorAll("[data-refazer]:checked:not(:disabled)").length;
      var total = sec.querySelectorAll(".cartao-imagem").length;
      sec.querySelector("[data-secao-contagem]").textContent =
        total + " imagem(ns)" + (n ? " · " + n + " marcada(s)" : "");
    });
  }

  function salvar(cartao) {
    var chave = cartao.dataset.chave;
    delete esperas[chave];
    var marcado = cartao.querySelector("[data-refazer]").checked;
    var link = cartao.querySelector("[data-link]");
    var motivo = cartao.querySelector("[data-motivo]");
    salvando++;
    var url = "/api/videos/" + encodeURIComponent(VIDEO) + "/imagens/" + encodeURIComponent(chave) + "/rascunho";
    return json("PUT", url, {
      refazer: marcado,
      link: link ? link.value : null,
      motivo: motivo ? motivo.value : null,
    }).then(function (res) {
      campo(cartao, "erro").textContent = res.ok ? "" : (res.data.erro || "nao consegui salvar");
      campo(cartao, "salvo").textContent = res.ok ? (marcado ? "salvo às " + hora() : "") : "";
      cartao.dataset.estado = res.ok && marcado ? "rascunho" : cartao.dataset.estado === "rascunho" ? "ok" : cartao.dataset.estado;
    }).catch(function () {
      campo(cartao, "erro").textContent = "sem conexão com o painel";
    }).finally(function () { salvando--; atualizarBarraGrade(); });
  }

  function agendar(cartao) {
    var chave = cartao.dataset.chave;
    if (esperas[chave]) clearTimeout(esperas[chave]);
    campo(cartao, "salvo").textContent = "…";
    esperas[chave] = setTimeout(function () { salvar(cartao); }, SALVAR_ESPERA);
  }

  function salvarPendentes() {
    var chaves = Object.keys(esperas);
    return Promise.all(chaves.map(function (chave) {
      clearTimeout(esperas[chave]);
      var cartao = document.querySelector('.cartao-imagem[data-chave="' + chave + '"]');
      return cartao ? salvar(cartao) : null;
    })).then(function espera() {
      if (salvando > 0) return new Promise(function (ok) { setTimeout(ok, 100); }).then(espera);
    });
  }

  function mensagem(texto, erro) {
    var g = grade();
    if (!g) return;
    var el = g.querySelector('[data-campo="mensagem"]');
    el.textContent = texto || "";
    el.classList.toggle("erro-texto", !!erro);
  }

  document.addEventListener("change", function (ev) {
    var alvo = ev.target;
    if (!alvo.matches || !alvo.matches("[data-refazer]")) return;
    var cartao = cartaoDe(alvo);
    cartao.querySelector(".campos").hidden = !alvo.checked;
    if (alvo.checked) {
      var primeiro = cartao.querySelector("[data-link], [data-motivo]");
      if (primeiro) primeiro.focus();
    }
    salvar(cartao);
  });

  document.addEventListener("input", function (ev) {
    var alvo = ev.target;
    if (!alvo.matches || !alvo.matches("[data-link], [data-motivo]")) return;
    agendar(cartaoDe(alvo));
  });

  document.addEventListener("click", function (ev) {
    var alvo = ev.target.closest ? ev.target.closest("button") : null;
    if (!alvo) return;

    if (alvo.dataset.acao === "enviar") {
      alvo.disabled = true;
      mensagem("enviando…");
      salvarPendentes().then(function () {
        return json("POST", "/api/videos/" + encodeURIComponent(VIDEO) + "/imagens/enviar");
      }).then(function (res) {
        if (res.status === 422) {
          Object.keys(res.data.erros || {}).forEach(function (chave) {
            var cartao = document.querySelector('.cartao-imagem[data-chave="' + chave + '"]');
            if (cartao) campo(cartao, "erro").textContent = res.data.erros[chave];
          });
          mensagem("complete os cartões marcados em vermelho", true);
          atualizarBarraGrade();
          return;
        }
        if (!res.ok) { mensagem(res.data.erro || "não consegui enviar", true); atualizarBarraGrade(); return; }
        var partes = [];
        if (res.data.worker) partes.push(res.data.worker + " com link (o worker refaz)");
        if (res.data.claude) partes.push(res.data.claude + " com motivo (vão para o Claude)");
        mensagem("Enviado: " + partes.join(" · "));
        carregarCorpo("revisao_imagens", true);
      });
      return;
    }

    if (alvo.dataset.acao === "aprovar") {
      if (!window.confirm("Aprovar todas as imagens e seguir para a montagem?")) return;
      alvo.disabled = true;
      json("POST", "/api/videos/" + encodeURIComponent(VIDEO) + "/imagens/aprovar").then(function (res) {
        if (!res.ok) { mensagem(res.data.erro || "não consegui aprovar", true); alvo.disabled = false; return; }
        window.location.href = "/videos/" + encodeURIComponent(VIDEO);
      });
      return;
    }

    if (alvo.dataset.cancelar) {
      if (!window.confirm("Cancelar este pedido de refação?")) return;
      json("POST", "/api/videos/" + encodeURIComponent(VIDEO) + "/imagens/pedidos/" + alvo.dataset.cancelar + "/cancelar")
        .then(function () { carregarCorpo("revisao_imagens", true); });
      return;
    }

    if (alvo.dataset.filtro) {
      var g = grade();
      g.querySelectorAll(".filtro").forEach(function (b) { b.classList.toggle("ativo", b === alvo); });
      var filtro = alvo.dataset.filtro;
      g.querySelectorAll(".cartao-imagem").forEach(function (c) {
        var marcada = !!c.querySelector("[data-refazer]:checked") ||
          ["enviado", "aguardando_claude", "pronto_para_refazer", "refazendo"].indexOf(c.dataset.estado) >= 0;
        var mostrar = filtro === "todas" ||
          (filtro === "marcadas" && marcada) ||
          (filtro === "refeitas" && c.dataset.refeita) ||
          (filtro === "referencia" && c.dataset.referencia);
        c.hidden = !mostrar;
      });
      return;
    }

    if (alvo.dataset.secoes) {
      grade().querySelectorAll("details.secao").forEach(function (sec) { sec.open = alvo.dataset.secoes === "abrir"; });
      return;
    }

    if (alvo.classList.contains("miniatura") || alvo.dataset.antes) {
      abrirLightbox(alvo);
      return;
    }

    if (alvo.dataset.lightboxFechar !== undefined) fecharLightbox();
  });

  // -- lightbox --------------------------------------------------------------

  var atual = null;

  function abrirLightbox(botao) {
    var box = document.querySelector("[data-lightbox]");
    box.querySelector("img").src = botao.dataset.antes || botao.dataset.grande;
    box.querySelector(".legenda").textContent = botao.dataset.legenda || "";
    box.hidden = false;
    atual = botao.dataset.antes ? null : botao;
  }

  function fecharLightbox() {
    var box = document.querySelector("[data-lightbox]");
    box.hidden = true;
    box.querySelector("img").src = "";
    atual = null;
  }

  function vizinho(passo) {
    if (!atual) return;
    var todos = Array.prototype.filter.call(
      document.querySelectorAll(".cartao-imagem:not([hidden]) .miniatura"),
      function (b) { return b.offsetParent !== null; }
    );
    var i = todos.indexOf(atual);
    var proximo = todos[i + passo];
    if (proximo) abrirLightbox(proximo);
  }

  document.addEventListener("keydown", function (ev) {
    var box = document.querySelector("[data-lightbox]");
    if (box.hidden) return;
    if (ev.key === "Escape") fecharLightbox();
    else if (ev.key === "ArrowRight") vizinho(1);
    else if (ev.key === "ArrowLeft") vizinho(-1);
  });

  document.querySelector("[data-lightbox]").addEventListener("click", function (ev) {
    if (ev.target === ev.currentTarget) fecharLightbox();
  });

  // -- grade ao vivo ---------------------------------------------------------

  var assinaturaGrade = null;

  function cicloGrade() {
    var g = grade();
    var det = document.getElementById("etapa-revisao_imagens");
    if (!g || !det || !det.open || document.hidden) { setTimeout(cicloGrade, GRADE_INTERVALO); return; }
    fetch("/api/videos/" + encodeURIComponent(VIDEO) + "/imagens")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (res) {
        if (!res) return;
        var assinatura = res.cartoes.map(function (c) {
          return c.chave + ":" + c.estado + ":" + c.versao + ":" + (c.pedido ? c.pedido.estado : "");
        }).join("|");
        var aprovar = g.querySelector('[data-acao="aprovar"]');
        var marcadas = g.querySelectorAll("[data-refazer]:checked:not(:disabled)").length;
        aprovar.disabled = !res.pode_aprovar || marcadas > 0;
        aprovar.title = res.motivo_nao_aprova || "";
        if (assinaturaGrade !== null && assinatura !== assinaturaGrade && !ocupado(corpoDe("revisao_imagens"))) {
          carregarCorpo("revisao_imagens", true);
        }
        assinaturaGrade = assinatura;
      })
      .catch(function () {})
      .finally(function () { setTimeout(cicloGrade, GRADE_INTERVALO); });
  }
  setTimeout(cicloGrade, GRADE_INTERVALO);

  atualizarBarraGrade();
})();
