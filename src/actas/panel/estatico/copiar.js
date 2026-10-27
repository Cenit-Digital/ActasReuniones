// Botones «Copiar» del panel: copian el texto del elemento cuyo id dice `data-copiar` (enlaces de los socios y la contraseña ya
// mostrada, cuya vista anotó la base). Sin JavaScript los botones siguen ocultos y el texto se selecciona a mano.
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    if (!navigator.clipboard) return;
    document.querySelectorAll('button[data-copiar]').forEach(function (boton) {
      var origen = document.getElementById(boton.dataset.copiar);
      if (!origen) return;
      var etiqueta = boton.firstChild.nodeValue;
      boton.hidden = false;
      boton.addEventListener('click', function () {
        navigator.clipboard.writeText(origen.textContent.trim()).then(
          function () {
            boton.firstChild.nodeValue = 'Copiado';
          },
          function () {
            boton.firstChild.nodeValue = 'No se pudo copiar';
          }
        );
        setTimeout(function () {
          boton.firstChild.nodeValue = etiqueta;
        }, 2000);
      });
    });
  });
})();
