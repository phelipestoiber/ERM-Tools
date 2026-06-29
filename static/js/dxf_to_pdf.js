/**
 * dxf_to_pdf.js — v0.4.0 · pipeline DWG→PDF na v0.6.0
 * Formulário da aba "DXF / DWG → PDF" + integração SSE.
 */

'use strict';

(function () {

  /* ── AVISO DE ODA AUSENTE ─────────────────────────────────────────── */

  async function checkOdaAvailability() {
    const warn = document.getElementById('oda-warning-pdf');
    if (!warn) return;

    try {
      const res = await fetch('/api/detect-oda');
      const data = await res.json();
      warn.style.display = data.found ? 'none' : 'block';
    } catch (e) {
      // Em caso de erro na verificação, não bloqueia o uso da aba
      warn.style.display = 'none';
    }
  }

  async function onSubmit(e) {
    e.preventDefault();

    const form   = document.getElementById('form-dxf-to-pdf');
    const fileIn = document.getElementById('pdf-files');
    const btnRun = document.getElementById('btn-run-pdf');

    if (!fileIn.files.length) {
      alert('Selecione ao menos um arquivo .dxf ou .dwg.');
      return;
    }

    const fd = new FormData(form);

    btnRun.disabled = true;
    btnRun.textContent = 'renderizando...';

    await sseHelper('/api/dxf-to-pdf', fd, {
      logAreaId:      'log-pdf',
      progressId:     'progress-pdf',
      downloadWrapId: 'download-pdf',
      onDone: () => {
        btnRun.disabled = false;
        btnRun.textContent = 'Gerar PDF';
      },
    });

    btnRun.disabled = false;
    btnRun.textContent = 'Gerar PDF';
  }

  function init() {
    const form = document.getElementById('form-dxf-to-pdf');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-browse-pdf')
      ?.addEventListener('click', () => browseFolder('dest-folder-pdf'));

    checkOdaAvailability();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
