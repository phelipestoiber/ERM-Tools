/**
 * dxf_scale.js — v0.3.0
 * Formulário da aba "DXF Scale" + integração SSE.
 */

'use strict';

(function () {

  async function onSubmit(e) {
    e.preventDefault();

    const form   = document.getElementById('form-dxf-scale');
    const fileIn = document.getElementById('dxf-scale-files');
    const btnRun = document.getElementById('btn-run-scale');
    const factor = document.getElementById('scale-factor');

    if (!fileIn.files.length) {
      alert('Selecione ao menos um arquivo .dxf.');
      return;
    }

    const f = parseFloat(factor.value);
    if (!f || f <= 0) {
      alert('Informe um fator de escala maior que zero.');
      return;
    }

    const fd = new FormData(form);

    btnRun.disabled = true;
    btnRun.textContent = 'processando...';

    await sseHelper('/api/dxf-scale', fd, {
      logAreaId:      'log-scale',
      progressId:     'progress-scale',
      downloadWrapId: 'download-scale',
      onDone: () => {
        btnRun.disabled = false;
        btnRun.textContent = 'Escalar';
      },
    });

    btnRun.disabled = false;
    btnRun.textContent = 'Escalar';
  }

  function init() {
    const form = document.getElementById('form-dxf-scale');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-browse-scale')
      ?.addEventListener('click', () => browseFolder('dest-folder-scale'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
