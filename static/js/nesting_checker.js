/**
 * nesting_checker.js — v0.9.1
 * Formulário da aba "Verificador de Nestings" + integração SSE.
 * Input: upload de arquivos DXF diretamente.
 */

'use strict';

(function () {

  async function onSubmit(e) {
    e.preventDefault();

    const btnRun    = document.getElementById('btn-run-nesting');
    const filesInput = document.getElementById('nesting-files');
    const destInput  = document.getElementById('dest-folder-nesting');

    if (!filesInput.files || filesInput.files.length === 0) {
      alert('Selecione ao menos um arquivo .dxf.');
      return;
    }

    const fd = new FormData();
    for (const f of filesInput.files) {
      fd.append('files[]', f);
    }
    fd.append('dest_folder', destInput.value.trim());

    btnRun.disabled    = true;
    btnRun.textContent = 'analisando...';

    await sseHelper('/api/nesting-check', fd, {
      logAreaId:      'log-nesting',
      progressId:     'progress-nesting',
      downloadWrapId: 'download-nesting',
      onDone: () => {
        btnRun.disabled    = false;
        btnRun.textContent = '⊜ Verificar Nestings';
      },
    });

    btnRun.disabled    = false;
    btnRun.textContent = '⊜ Verificar Nestings';
  }

  function init() {
    const form = document.getElementById('form-nesting');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-browse-dest-nesting')
      ?.addEventListener('click', () => browseFolder('dest-folder-nesting'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();