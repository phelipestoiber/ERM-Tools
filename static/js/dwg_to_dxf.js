/**
 * dwg_to_dxf.js — v0.2.0
 * Formulário da aba "DWG → DXF" + integração SSE.
 */

'use strict';

(function () {

  /* ── DETECT ODA ───────────────────────────────────────── */

  async function detectOda() {
    const btn   = document.getElementById('btn-detect-oda');
    const input = document.getElementById('oda-path');
    if (!btn || !input) return;

    btn.disabled = true;
    btn.textContent = 'buscando...';

    try {
      const res  = await fetch('/api/detect-oda');
      const data = await res.json();

      if (data.found) {
        input.value = data.path;
        input.style.borderColor = 'var(--ok)';
      } else {
        input.value = '';
        input.style.borderColor = 'var(--fail)';
        input.placeholder = 'ODA não encontrado — informe o caminho manualmente';
      }
    } catch (e) {
      console.error('detect-oda:', e);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Detectar';
    }
  }

  /* ── SUBMIT ───────────────────────────────────────────── */

  async function onSubmit(e) {
    e.preventDefault();

    const form    = document.getElementById('form-dwg-to-dxf');
    const fileIn  = document.getElementById('dwg-files');
    const btnRun  = document.getElementById('btn-run-dwg');

    if (!fileIn.files.length) {
      alert('Selecione ao menos um arquivo .dwg.');
      return;
    }

    // FormData direto do form — input já tem name="files[]"
    const fd = new FormData(form);

    btnRun.disabled = true;
    btnRun.textContent = 'processando...';

    await sseHelper('/api/dwg-to-dxf', fd, {
      logAreaId:      'log-dwg',
      progressId:     'progress-dwg',
      downloadWrapId: 'download-dwg',
      onDone: () => {
        btnRun.disabled = false;
        btnRun.textContent = 'Converter';
      },
    });

    btnRun.disabled = false;
    btnRun.textContent = 'Converter';
  }

  /* ── INIT ─────────────────────────────────────────────── */

  function init() {
    const form = document.getElementById('form-dwg-to-dxf');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-detect-oda')
      ?.addEventListener('click', detectOda);

    document.getElementById('btn-browse-dwg')
      ?.addEventListener('click', () => browseFolder('dest-folder-dwg'));

    // Auto-detecta ODA ao montar a aba
    detectOda();
  }

  // Aguarda o DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
