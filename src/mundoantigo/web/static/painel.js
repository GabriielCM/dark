/*
 * O painel e local e a maquina pode estar sem rede — nada de CDN.
 * Isto e o unico JavaScript do projeto: recarrega um fragmento em intervalo.
 */
(function () {
  "use strict";

  function atualizar(el) {
    var url = el.dataset.recarregar;
    var intervalo = parseInt(el.dataset.intervalo || "4000", 10);

    function ciclo() {
      fetch(url, { headers: { "X-Fragmento": "1" } })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html === null) return;
          // Nao substitui enquanto o usuario tem algo aberto dentro do bloco:
          // recarregar por baixo de um <details> aberto e irritante.
          if (el.querySelector("details[open]")) return;
          el.innerHTML = html;
        })
        .catch(function () { /* offline: tenta de novo no proximo ciclo */ })
        .finally(function () { setTimeout(ciclo, intervalo); });
    }
    setTimeout(ciclo, intervalo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-recarregar]").forEach(atualizar);

    // Confirmacao para acoes destrutivas (refazer com apagar, rejeitar).
    document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (!window.confirm(form.dataset.confirmar)) e.preventDefault();
      });
    });
  });
})();
