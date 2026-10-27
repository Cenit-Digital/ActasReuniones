// Tema del panel: el del sistema (prefers-color-scheme), salvo que se elija otro con el botón; se recuerda en este navegador.
// Se carga en <head> para aplicar el tema guardado antes de pintar. Con copiar.js, el único JavaScript del panel (CSP
// script-src 'self').
(function () {
  'use strict';
  var raiz = document.documentElement;
  var CLAVE = 'actas-tema';
  try {
    var guardado = localStorage.getItem(CLAVE);
    if (guardado === 'claro' || guardado === 'oscuro') raiz.dataset.tema = guardado;
  } catch (e) {
    // Sin almacenamiento (navegación privada o bloqueado): vale el tema del sistema.
  }
  function actual() {
    return raiz.dataset.tema || (matchMedia('(prefers-color-scheme: light)').matches ? 'claro' : 'oscuro');
  }
  document.addEventListener('DOMContentLoaded', function () {
    var boton = document.getElementById('tema');
    if (!boton) return;
    function pintar() {
      boton.setAttribute('aria-pressed', String(actual() === 'claro'));
    }
    pintar();
    boton.hidden = false;
    boton.addEventListener('click', function () {
      raiz.dataset.tema = actual() === 'claro' ? 'oscuro' : 'claro';
      try {
        localStorage.setItem(CLAVE, raiz.dataset.tema);
      } catch (e) {
        // Sin almacenamiento: el tema dura lo que la página.
      }
      pintar();
    });
  });
})();
