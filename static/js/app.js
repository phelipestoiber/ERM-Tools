/**
 * CAD Tools — app.js  (v0.1.0)
 *
 * Responsabilidades:
 *  - Navegação entre abas (switchTab)
 *  - Helper SSE via fetch + ReadableStream (sseHelper)
 *  - Helper de browse-folder (browseFolder)
 *  - Verificação de dependências ao carregar (loadDeps)
 */

'use strict';

/* ── TAB NAVIGATION ───────────────────────────────────────── */

function switchTab(tabId) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

  const panel = document.getElementById('panel-' + tabId);
  const btn   = document.querySelector(`[data-tab="${tabId}"]`);

  if (panel) panel.classList.add('active');
  if (btn)   btn.classList.add('active');
}

/* ── LOG AREA ─────────────────────────────────────────────── */

/**
 * Adiciona uma linha ao log.
 * @param {string} text   Texto a exibir
 * @param {string} type   'log' | 'ok' | 'fail' | 'done'
 * @param {string} areaId ID do elemento de log (default: 'log-area')
 */
function logLine(text, type = 'log', areaId = 'log-area') {
  const area = document.getElementById(areaId);
  if (!area) return;

  const span = document.createElement('span');
  span.className = `entry entry-${type}`;
  span.textContent = text;
  area.appendChild(span);
  area.scrollTop = area.scrollHeight;
}

function clearLog(areaId = 'log-area') {
  const area = document.getElementById(areaId);
  if (area) area.innerHTML = '';
}

/* ── SSE HELPER ───────────────────────────────────────────── */

/**
 * Faz um POST com FormData e lê o stream SSE via fetch + ReadableStream.
 *
 * O servidor envia linhas no formato:  data: TIPO payload\n\n
 * Tipos tratados: LOG | OK | FAIL | DOWNLOAD | DONE
 *
 * @param {string}   url         Endpoint POST SSE
 * @param {FormData} formData    Dados do formulário
 * @param {object}   opts
 * @param {string}   [opts.logAreaId='log-area']
 * @param {string}   [opts.progressId]    ID do .progress-wrap
 * @param {string}   [opts.downloadWrapId='download-wrap']
 * @param {Function} [opts.onDone]        Callback ao receber DONE
 */
async function sseHelper(url, formData, opts = {}) {
  const logAreaId      = opts.logAreaId      || 'log-area';
  const progressId     = opts.progressId     || null;
  const downloadWrapId = opts.downloadWrapId || 'download-wrap';
  const onDone         = opts.onDone         || null;

  clearLog(logAreaId);

  const progress = progressId ? document.getElementById(progressId) : null;
  if (progress) progress.classList.add('running');

  const dlWrap = document.getElementById(downloadWrapId);
  if (dlWrap) dlWrap.classList.remove('visible');

  let response;
  try {
    response = await fetch(url, { method: 'POST', body: formData });
  } catch (err) {
    logLine('Erro de conexão: ' + err.message, 'fail', logAreaId);
    if (progress) progress.classList.remove('running');
    return;
  }

  if (!response.ok) {
    const text = await response.text();
    logLine(`Erro HTTP ${response.status}: ${text}`, 'fail', logAreaId);
    if (progress) progress.classList.remove('running');
    return;
  }

  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Cada evento SSE termina com \n\n
    const parts = buffer.split('\n\n');
    buffer = parts.pop(); // guarda fragmento incompleto

    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (!line.startsWith('data:')) continue;

        const raw     = line.slice(5).trimStart();
        const spaceAt = raw.indexOf(' ');
        const tipo    = spaceAt === -1 ? raw : raw.slice(0, spaceAt);
        const payload = spaceAt === -1 ? '' : raw.slice(spaceAt + 1);

        switch (tipo) {
          case 'LOG':
            logLine(payload, 'log', logAreaId);
            break;
          case 'OK':
            logLine(payload, 'ok', logAreaId);
            break;
          case 'FAIL':
            logLine(payload, 'fail', logAreaId);
            break;
          case 'DOWNLOAD':
            _showDownload(payload, downloadWrapId);
            break;
          case 'DONE':
            logLine('Processamento concluído.', 'done', logAreaId);
            if (progress) progress.classList.remove('running');
            if (onDone) onDone();
            break;
        }
      }
    }
  }

  if (progress) progress.classList.remove('running');
}

function _showDownload(zipName, wrapId) {
  const wrap = document.getElementById(wrapId);
  if (!wrap) return;

  const url = `/api/download/${encodeURIComponent(zipName)}`;

  wrap.innerHTML = `
    <span class="msg">📦 ${zipName}</span>
    <a class="btn btn-primary btn-sm" href="${url}" download>Baixar ZIP</a>
  `;
  wrap.classList.add('visible');
}

/* ── BROWSE FOLDER ────────────────────────────────────────── */

/**
 * Chama /api/browse-folder e preenche o input com o caminho retornado.
 * @param {string} inputId   ID do campo de texto a preencher
 */
async function browseFolder(inputId) {
  try {
    const res  = await fetch('/api/browse-folder');
    const data = await res.json();
    if (data.ok && data.folder) {
      const input = document.getElementById(inputId);
      if (input) input.value = data.folder;
    } else if (data.msg) {
      console.warn('browse-folder:', data.msg);
    }
  } catch (err) {
    console.error('browse-folder error:', err);
  }
}

/* ── DEPS CHECK ───────────────────────────────────────────── */

async function loadDeps() {
  try {
    const res  = await fetch('/api/deps');
    const data = await res.json();
    _renderDepStatus(data);
    _renderDepsPanel(data);
  } catch (e) {
    console.warn('Falha ao carregar deps:', e);
  }
}

function _renderDepStatus(data) {
  const bar = document.getElementById('dep-status-bar');
  if (!bar) return;

  const items = [
    { key: 'ezdxf',      label: 'ezdxf'    },
    { key: 'pypdf',      label: 'pypdf'     },
    { key: 'matplotlib', label: 'mpl'       },
    { key: 'oda_found',  label: 'ODA'       },
  ];

  bar.innerHTML = items.map(({ key, label }) => {
    const ok = data[key];
    return `<span class="dep-dot ${ok ? 'ok' : 'fail'}" title="${label}: ${ok ? 'ok' : 'não encontrado'}"></span>
            <span style="font-size:11px;color:var(--text-dim)">${label}</span>`;
  }).join('');
}

function _renderDepsPanel(data) {
  const grid = document.getElementById('deps-grid');
  if (!grid) return;

  const items = [
    { name: 'ezdxf',      ok: data.ezdxf,      val: data.ezdxf      ? 'instalado'         : 'pip install ezdxf' },
    { name: 'pypdf',      ok: data.pypdf,      val: data.pypdf      ? 'instalado'         : 'pip install pypdf' },
    { name: 'matplotlib', ok: data.matplotlib, val: data.matplotlib ? 'instalado'         : 'pip install matplotlib' },
    { name: 'ODA',        ok: data.oda_found,  val: data.oda_path   || 'não encontrado'   },
    { name: 'accore',     ok: data.accore_found, val: data.accore_path || 'não encontrado' },
  ];

  grid.innerHTML = items.map(({ name, ok, val }) => `
    <div class="dep-card ${ok ? 'ok' : 'fail'}">
      <div class="dep-name">${name}</div>
      <div class="dep-val">${val}</div>
    </div>
  `).join('');
}

/* ── INIT ─────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  // Tab buttons
  document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Shutdown button
  const shutdownBtn = document.getElementById('btn-shutdown');
  if (shutdownBtn) {
    shutdownBtn.addEventListener('click', async () => {
      if (!confirm('Encerrar o servidor CAD Tools?')) return;
      await fetch('/api/shutdown');
      window.close();
    });
  }

  // Start on first tab
  switchTab('dwg-to-dxf');

  // Load dependency status
  loadDeps();
});
