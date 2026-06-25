/**
 * pdf_merge.js — v0.5.0
 * Editor de PDF: upload → staging (leitura de metadados) → reordenação de
 * páginas → merge final. Não usa SSE (operação rápida, resposta JSON).
 */

'use strict';

(function () {

  // Lista de páginas atualmente montada: cada item é
  // { file_id, filename, page_index, n_pages_in_file }
  let pageList = [];

  /* ── STAGING (upload + leitura de metadados) ─────────────────────── */

  async function onFilesSelected(e) {
    const files = e.target.files;
    if (!files || !files.length) return;

    const status = document.getElementById('pdf-stage-status');
    status.textContent = 'Lendo arquivos...';

    const fd = new FormData();
    for (const f of files) fd.append('files[]', f);

    try {
      const res = await fetch('/api/pdf-stage', { method: 'POST', body: fd });
      const data = await res.json();

      pageList = []; // substitui a seleção anterior

      for (const fileInfo of data.files || []) {
        for (let p = 0; p < fileInfo.n_pages; p++) {
          pageList.push({
            file_id: fileInfo.file_id,
            filename: fileInfo.filename,
            page_index: p,
            n_pages_in_file: fileInfo.n_pages,
          });
        }
      }

      if (data.errors && data.errors.length) {
        const msgs = data.errors.map(e => `${e.filename}: ${e.error}`).join(' | ');
        status.textContent = `Alguns arquivos falharam: ${msgs}`;
        status.style.color = 'var(--fail)';
      } else {
        status.textContent = `${data.files.length} arquivo(s) carregado(s), ${pageList.length} página(s) no total.`;
        status.style.color = 'var(--text-muted)';
      }

      renderPageList();
    } catch (err) {
      status.textContent = 'Erro ao processar arquivos: ' + err.message;
      status.style.color = 'var(--fail)';
    }
  }

  /* ── LISTA DE PÁGINAS REORDENÁVEL ────────────────────────────────── */

  function renderPageList() {
    const container = document.getElementById('pdf-page-list');
    if (!container) return;

    if (!pageList.length) {
      container.innerHTML = `<div class="placeholder" style="padding:24px 0;">
        <div class="sub">Nenhuma página carregada ainda</div>
      </div>`;
      updateMergeButton();
      return;
    }

    container.innerHTML = pageList.map((item, i) => `
      <div class="pdf-page-item" data-index="${i}">
        <span class="pdf-page-num">${i + 1}</span>
        <span class="pdf-page-name">${escapeHtml(item.filename)}</span>
        <span class="pdf-page-sub">página ${item.page_index + 1} de ${item.n_pages_in_file}</span>
        <span class="pdf-page-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-action="up" ${i === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="down" ${i === pageList.length - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="btn btn-danger btn-sm" data-action="remove">✕</button>
        </span>
      </div>
    `).join('');

    container.querySelectorAll('.pdf-page-item').forEach(el => {
      const i = parseInt(el.dataset.index, 10);
      el.querySelector('[data-action="up"]')?.addEventListener('click', () => moveItem(i, -1));
      el.querySelector('[data-action="down"]')?.addEventListener('click', () => moveItem(i, 1));
      el.querySelector('[data-action="remove"]')?.addEventListener('click', () => removeItem(i));
    });

    updateMergeButton();
  }

  function moveItem(index, delta) {
    const newIndex = index + delta;
    if (newIndex < 0 || newIndex >= pageList.length) return;
    [pageList[index], pageList[newIndex]] = [pageList[newIndex], pageList[index]];
    renderPageList();
  }

  function removeItem(index) {
    pageList.splice(index, 1);
    renderPageList();
  }

  function updateMergeButton() {
    const btn = document.getElementById('btn-run-merge');
    if (btn) btn.disabled = pageList.length === 0;
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  /* ── MERGE FINAL ──────────────────────────────────────────────────── */

  async function onMergeSubmit(e) {
    e.preventDefault();
    if (!pageList.length) return;

    const btn = document.getElementById('btn-run-merge');
    const status = document.getElementById('pdf-merge-status');
    const destFolder = document.getElementById('dest-folder-merge').value;
    const dlWrap = document.getElementById('download-merge');

    btn.disabled = true;
    btn.textContent = 'mesclando...';
    status.textContent = '';
    dlWrap.classList.remove('visible');

    const sequence = pageList.map(({ file_id, page_index }) => ({ file_id, page_index }));

    try {
      const res = await fetch('/api/pdf-merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          sequence: JSON.stringify(sequence),
          dest_folder: destFolder,
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        status.textContent = 'Erro: ' + (data.error || 'falha desconhecida');
        status.style.color = 'var(--fail)';
      } else {
        status.textContent = `PDF mesclado: ${data.pdf} (${data.n_pages} página(s), ${(data.size_bytes / 1024).toFixed(1)} KB)`;
        status.style.color = 'var(--ok)';

        dlWrap.innerHTML = `
          <span class="msg">📦 ${data.zip}</span>
          <a class="btn btn-primary btn-sm" href="/api/download/${encodeURIComponent(data.zip)}" download>Baixar ZIP</a>
        `;
        dlWrap.classList.add('visible');

        // Os file_ids usados já foram limpos no servidor — esvazia a lista
        pageList = [];
        renderPageList();
      }
    } catch (err) {
      status.textContent = 'Erro de conexão: ' + err.message;
      status.style.color = 'var(--fail)';
    } finally {
      btn.disabled = pageList.length === 0;
      btn.textContent = '⊕ Mesclar PDFs';
    }
  }

  /* ── INIT ─────────────────────────────────────────────────────────── */

  function init() {
    const fileInput = document.getElementById('pdf-merge-files');
    const form = document.getElementById('form-pdf-merge');
    if (!fileInput || !form) return;

    fileInput.addEventListener('change', onFilesSelected);
    form.addEventListener('submit', onMergeSubmit);

    document.getElementById('btn-browse-merge')
      ?.addEventListener('click', () => browseFolder('dest-folder-merge'));

    renderPageList();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
