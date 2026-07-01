/**
 * dxf_escala_cotagem.js — v0.7.0
 * Formulário da aba "Escalar e Cotar" (regra FORAN) + integração SSE.
 */

'use strict';

(function () {

  // Lista de labels fixos: cada item é { texto, x, y }
  let labelList = [];

  /* ── LISTA DINÂMICA DE LABELS ────────────────────────────────────── */

  function renderLabelList() {
    const container = document.getElementById('cotagem-labels-list');
    if (!container) return;

    if (!labelList.length) {
      container.innerHTML = `<div class="sub" style="padding:8px 0;color:var(--text-dim);">
        Nenhum label fixo — serão usados os padrões (SEÇÃO A-A / SEÇÃO B-B).
      </div>`;
      return;
    }

    container.innerHTML = labelList.map((item, i) => `
      <div class="label-row" data-index="${i}">
        <input type="text" class="label-texto" placeholder="Texto (use \\n p/ quebra de linha)" value="${escapeAttr(item.texto)}" />
        <input type="number" class="label-x" placeholder="X" step="any" value="${item.x}" />
        <input type="number" class="label-y" placeholder="Y" step="any" value="${item.y}" />
        <button type="button" class="btn btn-secondary btn-sm label-remove" title="Remover">✕</button>
      </div>
    `).join('');

    container.querySelectorAll('.label-row').forEach(row => {
      const idx = parseInt(row.dataset.index, 10);

      row.querySelector('.label-texto').addEventListener('input', (e) => {
        labelList[idx].texto = e.target.value;
      });
      row.querySelector('.label-x').addEventListener('input', (e) => {
        labelList[idx].x = e.target.value;
      });
      row.querySelector('.label-y').addEventListener('input', (e) => {
        labelList[idx].y = e.target.value;
      });
      row.querySelector('.label-remove').addEventListener('click', () => {
        labelList.splice(idx, 1);
        renderLabelList();
      });
    });
  }

  function escapeAttr(s) {
    const div = document.createElement('div');
    div.textContent = s ?? '';
    return div.innerHTML.replace(/"/g, '&quot;');
  }

  function addLabelRow() {
    labelList.push({ texto: '', x: 0, y: 0 });
    renderLabelList();
  }

  /* ── SUBMIT ───────────────────────────────────────────────────────── */

  async function onSubmit(e) {
    e.preventDefault();

    const form    = document.getElementById('form-dxf-cotagem');
    const fileIn  = document.getElementById('cotagem-files');
    const btnRun  = document.getElementById('btn-run-cotagem');
    const escala  = document.getElementById('cotagem-escala');

    if (!fileIn.files.length) {
      alert('Selecione ao menos um arquivo .dxf.');
      return;
    }

    const e_val = parseFloat(escala.value);
    if (!e_val || e_val <= 0) {
      alert('Informe uma escala maior que zero.');
      return;
    }

    const fd = new FormData(form);

    // Só envia "labels" se o usuário montou ao menos uma linha válida
    const validLabels = labelList
      .filter(l => l.texto.trim() !== '')
      .map(l => ({ texto: l.texto, x: parseFloat(l.x) || 0, y: parseFloat(l.y) || 0 }));
    if (validLabels.length) {
      fd.set('labels', JSON.stringify(validLabels));
    } else {
      fd.delete('labels');
    }

    btnRun.disabled = true;
    btnRun.textContent = 'processando...';

    await sseHelper('/api/dxf-escala-cotagem', fd, {
      logAreaId:      'log-cotagem',
      progressId:     'progress-cotagem',
      downloadWrapId: 'download-cotagem',
      onDone: () => {
        btnRun.disabled = false;
        btnRun.textContent = '⊟ Escalar e Cotar';
      },
    });

    btnRun.disabled = false;
    btnRun.textContent = '⊟ Escalar e Cotar';
  }

  /* ── INIT ─────────────────────────────────────────────────────────── */

  function init() {
    const form = document.getElementById('form-dxf-cotagem');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    document.getElementById('btn-browse-cotagem')
      ?.addEventListener('click', () => browseFolder('dest-folder-cotagem'));

    document.getElementById('btn-add-label')
      ?.addEventListener('click', addLabelRow);

    renderLabelList();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
