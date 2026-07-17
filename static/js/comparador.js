/**
 * comparador.js — v0.10.0
 * Formulário da aba "Comparador de Peças" + integração SSE.
 *
 * Dois modos:
 *   familias — peças de famílias diferentes com peso/área idênticos (main.py)
 *   copias   — cópias _C## divergentes do original (main2.py)
 *
 * O switch de modo mostra/oculta os campos de tolerância relevantes
 * no bloco avançado — o FormData sempre envia apenas os campos do modo ativo.
 */

'use strict';

(function () {

  /* ── SWITCH DE MODO ───────────────────────────────────────────────── */

  function setModo(modo) {
    document.querySelectorAll('.comp-modo-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.modo === modo);
    });

    // Mostra os campos de tolerância do modo selecionado
    document.querySelectorAll('.comp-tol-bloco').forEach(bloco => {
      bloco.style.display = bloco.dataset.modo === modo ? '' : 'none';
    });

    // Atualiza subtítulo dinâmico do painel
    const subtitulos = {
      familias: 'Detecta peças de <strong>famílias diferentes</strong> com peso e área idênticos dentro de uma tolerância.',
      copias:   'Detecta <strong>cópias (_C##)</strong> que divergem do original ou que se dividem em perfis distintos dentro da família.',
    };
    const el = document.getElementById('comp-subtitulo-dinamico');
    if (el) el.innerHTML = subtitulos[modo] || '';

    // Atualiza label do botão de execução
    const labels = {
      familias: '⊛ Comparar Famílias',
      copias:   '⊛ Comparar Cópias',
    };
    const btnRun = document.getElementById('btn-run-comparador');
    if (btnRun) btnRun.textContent = labels[modo] || '⊛ Comparar';

    // Guarda modo corrente no form (campo hidden)
    const hiddenModo = document.getElementById('comp-hidden-modo');
    if (hiddenModo) hiddenModo.value = modo;
  }

  /* ── SUBMIT ───────────────────────────────────────────────────────── */

  async function onSubmit(e) {
    e.preventDefault();

    const fileIn = document.getElementById('comparador-file');
    const btnRun = document.getElementById('btn-run-comparador');
    const modo   = document.getElementById('comp-hidden-modo')?.value || 'familias';

    if (!fileIn.files.length) {
      alert('Selecione um arquivo Excel (.xlsx ou .xls).');
      return;
    }

    const fd = new FormData();
    fd.append('file', fileIn.files[0]);
    fd.append('modo', modo);
    fd.append('dest_folder', document.getElementById('dest-folder-comparador').value || '');

    // Envia tolerâncias do modo ativo
    if (modo === 'familias') {
      fd.append('tol_peso', document.getElementById('comp-tol-peso').value || '');
      fd.append('tol_area', document.getElementById('comp-tol-area').value || '');
    } else {
      fd.append('tol_verdadeira', document.getElementById('comp-tol-verdadeira').value || '');
      fd.append('tol_grupo',      document.getElementById('comp-tol-grupo').value      || '');
    }

    const labelOriginal = btnRun.textContent;
    btnRun.disabled    = true;
    btnRun.textContent = 'processando...';

    await sseHelper('/api/comparar-pecas', fd, {
      logAreaId:      'log-comparador',
      progressId:     'progress-comparador',
      downloadWrapId: 'download-comparador',
      onDone: () => {
        btnRun.disabled    = false;
        btnRun.textContent = labelOriginal;
      },
    });

    btnRun.disabled    = false;
    btnRun.textContent = labelOriginal;
  }

  /* ── INIT ─────────────────────────────────────────────────────────── */

  function init() {
    const form = document.getElementById('form-comparador');
    if (!form) return;

    form.addEventListener('submit', onSubmit);

    // Botões de modo
    document.querySelectorAll('.comp-modo-btn').forEach(btn => {
      btn.addEventListener('click', () => setModo(btn.dataset.modo));
    });

    // Browse de pasta de destino
    document.getElementById('btn-browse-comparador')
      ?.addEventListener('click', () => browseFolder('dest-folder-comparador'));

    // Inicia no modo "familias"
    setModo('familias');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
