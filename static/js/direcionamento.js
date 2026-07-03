/**
 * direcionamento.js — v0.8.0
 * Formulário da aba "Direcionamento" (Navipeças) + integração SSE.
 * Aceita um único arquivo Excel (.xlsx/.xls) por envio.
 */

'use strict';

(function () {

  async function onSubmit(e) {
    e.preventDefault();

    const form   = document.getElementById('form-direcionamento');
    const fileIn = document.getElementById('direcionamento-file');
    const btnRun = document.getElementById('btn-run-direcionamento');

    if (!fileIn.files.length) {
      alert('Selecione um arquivo Excel (.xlsx ou .xls).');
      return;
    }

    const fd = new FormData();
    fd.append('file', fileIn.files[0]);
    fd.append('dest_folder', document.getElementById('dest-folder-direcionamento').value || '');

    btnRun.disabled = true;
    btnRun.textContent = 'processando...';

    await sseHelper('/api/direcionamento-excel', fd, {
      logAreaId:      'log-direcionamento',
      progressId:     'progress-direcionamento',
      downloadWrapId: 'download-direcionamento',
      onDone: () => {
        btnRun.disabled = false;
        btnRun.textContent = 'Processar Dados';
      },
    });

    btnRun.disabled = false;
    btnRun.textContent = 'Processar Dados';
  }

  function init() {
    const form = document.getElementById('form-direcionamento');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-browse-direcionamento')
      ?.addEventListener('click', () => browseFolder('dest-folder-direcionamento'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
