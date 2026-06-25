/**
 * pdf_merge.js — v0.5.0
 * Editor de PDF: upload → staging (leitura de metadados) → reordenação de
 * páginas → merge final. Não usa SSE (operação rápida, resposta JSON).
 */

'use strict';

if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

(function () {

  // Lista de páginas atualmente montada: cada item é
  // { file_id, filename, page_index, n_pages_in_file, thumbnail }
  let pageList = [];

  /* ── MINIATURAS (pdf.js, renderizado localmente no navegador) ────── */

  const THUMB_WIDTH = 140; // px

  /**
   * Renderiza cada página do arquivo local como uma imagem (data URL),
   * usando pdf.js diretamente no navegador — não depende do servidor.
   */
  async function renderThumbnails(file) {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    const thumbnails = [];

    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const baseViewport = page.getViewport({ scale: 1 });
      const scale = THUMB_WIDTH / baseViewport.width;
      const viewport = page.getViewport({ scale });

      const canvas = document.createElement('canvas');
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
      thumbnails.push(canvas.toDataURL('image/png'));
    }

    return thumbnails;
  }

  /* ── STAGING (upload + leitura de metadados) ─────────────────────── */

  async function onFilesSelected(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    const status = document.getElementById('pdf-stage-status');
    status.textContent = 'Lendo arquivos e gerando pré-visualização...';
    status.style.color = 'var(--text-muted)';

    const fd = new FormData();
    for (const f of files) fd.append('files[]', f);

    try {
      // Em paralelo: (1) staging no servidor — obtém file_id/n_pages
      // confiáveis via pypdf; (2) renderização local das miniaturas via
      // pdf.js, direto a partir dos arquivos já selecionados (sem round-trip).
      const [stageRes, thumbsByFile] = await Promise.all([
        fetch('/api/pdf-stage', { method: 'POST', body: fd }).then(r => r.json()),
        Promise.all(files.map(f => renderThumbnails(f).catch(() => []))),
      ]);

      pageList = []; // substitui a seleção anterior

      (stageRes.files || []).forEach((fileInfo, fileIdx) => {
        const thumbs = thumbsByFile[fileIdx] || [];
        for (let p = 0; p < fileInfo.n_pages; p++) {
          pageList.push({
            file_id: fileInfo.file_id,
            filename: fileInfo.filename,
            page_index: p,
            n_pages_in_file: fileInfo.n_pages,
            thumbnail: thumbs[p] || null,
          });
        }
      });

      if (stageRes.errors && stageRes.errors.length) {
        const msgs = stageRes.errors.map(e => `${e.filename}: ${e.error}`).join(' | ');
        status.textContent = `Alguns arquivos falharam: ${msgs}`;
        status.style.color = 'var(--fail)';
      } else {
        status.textContent = `${stageRes.files.length} arquivo(s) carregado(s), ${pageList.length} página(s) no total.`;
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
      container.innerHTML = `<div class="placeholder" style="padding:24px 0;grid-column:1/-1;">
        <div class="sub">Nenhuma página carregada ainda</div>
      </div>`;
      updateMergeButton();
      return;
    }

    container.innerHTML = pageList.map((item, i) => `
      <div class="pdf-page-card" data-index="${i}">
        <button type="button" class="pdf-page-remove" data-action="remove" title="Remover">✕</button>
        <div class="pdf-page-thumb">
          ${item.thumbnail
            ? `<img src="${item.thumbnail}" alt="página ${item.page_index + 1}" />`
            : `<span class="pdf-page-thumb-fallback">PDF</span>`}
          <div class="pdf-page-badge">${i + 1}</div>
        </div>
        <div class="pdf-page-caption" title="${escapeHtml(item.filename)} — pág. ${item.page_index + 1}/${item.n_pages_in_file}">
          ${escapeHtml(item.filename)} · p.${item.page_index + 1}
        </div>
      </div>
    `).join('');

    container.querySelectorAll('[data-action="remove"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = e.target.closest('.pdf-page-card');
        removeItem(parseInt(card.dataset.index, 10));
      });
    });

    initSortable(container);
    updateMergeButton();
  }

  /**
   * Inicializa (ou reinicializa) o SortableJS no grid de páginas,
   * permitindo arrastar os cartões para reordenar — similar ao ilovepdf.
   */
  let sortableInstance = null;

  function initSortable(container) {
    if (!window.Sortable) return;

    if (sortableInstance) {
      sortableInstance.destroy();
      sortableInstance = null;
    }

    sortableInstance = new Sortable(container, {
      animation: 150,
      ghostClass: 'pdf-page-ghost',
      chosenClass: 'pdf-page-chosen',
      dragClass: 'pdf-page-drag',
      onEnd: function () {
        // Reconstrói pageList na nova ordem visual do DOM, depois
        // re-renderiza para atualizar os números de ordem (badges).
        const newOrder = [...container.children]
          .filter(el => el.dataset && el.dataset.index !== undefined)
          .map(el => parseInt(el.dataset.index, 10));
        pageList = newOrder.map(i => pageList[i]);
        renderPageList();
      },
    });
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
