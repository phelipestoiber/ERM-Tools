# CAD Tools — Estrutura de Desenvolvimento

> Guia de referência para criação do projeto: quais arquivos criar, em qual ordem e em qual versão cada um entra.
>
> **Versão do documento: 1.2** — adiciona a **Fase 7 — Escalar e Cotar (v0.7.0)**, baseada nas regras de negócio e funções de `main.py` (cotagem automática de perfis/ninhos no padrão FORAN). A fase de build/empacotamento passa de Fase 6 para **Fase 8**, mantendo a tag final `v1.0.0`.

---

## Legenda de versões

| Badge | Versão | Fase | Entregável |
|-------|--------|------|------------|
| `v0.1.0` | Scaffold | Fase 0 | App abre no browser com 5 abas vazias |
| `v0.2.0` | DWG → DXF | Fase 1 | Conversão via ODA funcionando |
| `v0.3.0` | DXF Scale | Fase 2 | Escalonamento de entidades via ezdxf |
| `v0.4.0` | DXF → PDF | Fase 3 | Renderização matplotlib funcionando |
| `v0.5.0` | PDF Editor | Fase 4 | Merge de páginas via pypdf |
| `v0.6.0` | DWG → PDF | Fase 5 | Pipeline encadeado ODA + renderer |
| `v0.7.0` | **Escalar e Cotar** | **Fase 6** | **Cotagem automática (regra FORAN) + escala + explosão de blocos** |
| `v1.0.0` | Release | Fase 7 | CAD_Tools.exe gerado pelo PyInstaller |

> Nota: a numeração de fases foi renumerada em relação à v1.1 do documento (a antiga "Fase 6 — Build" agora é Fase 7) para acomodar o novo módulo antes do empacotamento final.

---

## Árvore completa do projeto

```
cad_tools/
├── app.py                          # v0.1.0  — Flask app factory + __main__
├── requirements.txt                # v0.1.0  — dependências Python
├── build.spec                      # v1.0.0  — PyInstaller spec
├── .gitignore                      # v0.1.0
└── README.md                       # v1.0.0

├── routes/
│   ├── __init__.py                 # v0.1.0
│   ├── system.py                   # v0.1.0  — browse-folder, deps, detect-oda, download, shutdown
│   ├── dwg_to_dxf.py               # v0.2.0  — POST /api/dwg-to-dxf → SSE
│   ├── dxf_scale.py                # v0.3.0  — POST /api/dxf-scale → SSE
│   ├── dxf_to_pdf.py               # v0.4.0  — POST /api/dxf-to-pdf → SSE (estendido em v0.6.0)
│   ├── pdf_merge.py                # v0.5.0  — POST /api/pdf-merge → JSON
│   └── dxf_escala_cotagem.py       # v0.7.0  — POST /api/dxf-escala-cotagem → SSE

├── services/
│   ├── __init__.py                 # v0.1.0
│   ├── oda_converter.py            # v0.2.0  — subprocess wrapper para ODAFileConverter.exe
│   ├── dxf_scaler.py               # v0.3.0  — escala entidades + dimstyles via ezdxf
│   ├── dxf_renderer.py             # v0.4.0  — DXF → PDF via ezdxf.addons.drawing + matplotlib
│   ├── pdf_editor.py               # v0.5.0  — merge de páginas via pypdf
│   ├── dxf_cotador_foran.py        # v0.7.0  — geometria + regras de negócio (cotagem de perfis/scallops)
│   └── dxf_escala_cotagem.py       # v0.7.0  — orquestrador: escalar_e_cotar() → generator SSE

├── utils/
│   ├── __init__.py                 # v0.1.0
│   ├── sse.py                      # v0.1.0  — sse_event(tipo, payload), sse_done()
│   ├── zip_utils.py                # v0.2.0  — create_zip(files, dest_dir, prefix) → zip_path
│   ├── paths.py                    # v0.1.0  — resolve_output(), get_resource_path()
│   └── deps.py                     # v0.1.0  — check_all_deps() → {ezdxf, pypdf, oda_path, ...}

├── templates/
│   └── index.html                  # v0.1.0  — single-page app (5 abas; estendido em v0.7.0 para 6 abas)

├── static/
│   ├── css/
│   │   └── app.css                 # v0.1.0  — estilos globais + área de logs SSE (campos avançados em v0.7.0)
│   └── js/
│       ├── app.js                  # v0.1.0  — navegação entre abas + SSE helper genérico
│       ├── dwg_to_dxf.js           # v0.2.0  — formulário + SSE da aba DWG→DXF
│       ├── dxf_scale.js            # v0.3.0  — formulário + SSE da aba Scale
│       ├── dxf_to_pdf.js           # v0.4.0  — formulário + SSE da aba PDF (estendido em v0.6.0)
│       ├── pdf_merge.js            # v0.5.0  — upload + reordenação + merge
│       └── dxf_escala_cotagem.js   # v0.7.0  — formulário + SSE da aba Escalar e Cotar

├── output/                         # gerado no boot — gitignore
└── dist/
    └── CAD_Tools.exe               # v1.0.0 — gerado pelo PyInstaller
```

---

## Fase 0 — Scaffold e infraestrutura `v0.1.0` (~1–2 dias)

**Objetivo:** app sobe, abre no Chrome no modo `--app`, exibe 5 abas vazias. SSE e browse-folder funcionam. Zero lógica de conversão.

### `app.py`
```
- Flask app factory com create_app()
- Registra Blueprints de routes/ dinamicamente
- MAX_CONTENT_LENGTH = 512 * 1024 * 1024  (512 MB)
- Cria output/ via os.makedirs(exist_ok=True)
- Bloco __main__: encontra porta livre, abre Chrome --app=, inicia Flask
```

### `routes/system.py`
```
GET  /api/browse-folder    → tkinter.filedialog.askdirectory → {"folder": "caminho"}
GET  /api/deps             → check_all_deps() → JSON com status de cada dep
GET  /api/detect-oda       → busca ODAFileConverter.exe em 3 caminhos padrão
GET  /api/detect-accore    → busca accoreconsole.exe do AutoCAD
GET  /api/download/<name>  → send_from_directory(output_dir, name, as_attachment=True)
GET  /api/shutdown         → os.kill(os.getpid(), signal.SIGTERM)
```

### `utils/sse.py`
```
- sse_event(tipo, payload="") → "data: TIPO payload\n\n"
- sse_done()                  → "data: DONE\n\n"
- Tipos válidos: LOG | OK | FAIL | DOWNLOAD | DONE
```

### `utils/paths.py`
```
- get_resource_path(rel)   → resolve sys._MEIPASS quando congelado pelo PyInstaller
- resolve_output(dest)     → valida dest ou retorna app_root/output/
```

### `utils/deps.py`
```
- check_all_deps() → dict com:
    ezdxf:    bool (tenta import)
    pypdf:    bool (tenta import)
    matplotlib: bool
    oda_path: str | None
    accore_path: str | None
```

### `templates/index.html`
```
- Single-page app com 5 abas: DWG→DXF | DXF Scale | DXF→PDF | DWG→PDF | PDF Editor
- Área de logs SSE compartilhada (<div id="log-area">)
- Botão de download do .zip (oculto até receber evento DOWNLOAD)
- Navegação por JS puro (sem framework)
```

### `static/css/app.css`
```
- Layout geral: header com abas, main content, área de logs
- Classes para tipos de log: .log-ok (verde), .log-fail (vermelho), .log-info (cinza)
- Barra de progresso indeterminada (spinner ou animated bar)
```

### `static/js/app.js`
```
- switchTab(id): mostra/esconde painéis, ativa aba
- sseHelper(url, formData, logAreaId, onDownload):
    - Abre EventSource via POST com fetch + ReadableStream (workaround SSE + POST)
    - Parseia event.data.split(' ', 1) → [tipo, payload]
    - Tipos LOG/OK/FAIL: append ao log
    - DOWNLOAD: exibe botão com link /api/download/<payload>
    - DONE: fecha stream
- browseFolder(inputId): GET /api/browse-folder → preenche input
```

### `requirements.txt`
```
flask>=3.0
ezdxf>=1.2
matplotlib>=3.8
pypdf>=4.0
pyinstaller>=6.0
```

### `.gitignore`
```
output/
dist/
build/
__pycache__/
*.pyc
uploads/
*.zip
```

---

## Fase 1 — DWG → DXF via ODA `v0.2.0` (~2 dias)

**Objetivo:** upload de .dwg → ODA converte → .zip com .dxf é disponibilizado para download.

### `services/oda_converter.py`
```
- run_oda(in_dir, out_dir, version, audit, oda_path) → generator SSE
- Valida existência do oda_path antes de chamar subprocess
- subprocess.run([oda_path, in_dir, out_dir, version, "DXF", "0", str(audit)],
                 timeout=300, capture_output=True)
- Parseia stdout/stderr para extrair nomes de arquivos convertidos
- Yield: LOG antes de cada arquivo, OK ou FAIL depois
- Yield: DOWNLOAD <uuid>.zip ao final
- Yield: DONE para encerrar o stream
- Limpeza de in_dir no bloco finally (shutil.rmtree)
```

### `routes/dwg_to_dxf.py`
```
Blueprint: dwg_to_dxf, url_prefix=/api

POST /api/dwg-to-dxf
  - Recebe: files[] (multipart), oda_path, version, audit, dest_folder
  - Salva arquivos em tempfile.mkdtemp()
  - Chama oda_converter.run_oda() e faz stream SSE via stream_with_context
  - Ao final, move zip para resolve_output(dest_folder)
  - Content-Type: text/event-stream
```

### `utils/zip_utils.py`
```
- create_zip(files: list[Path], dest_dir: Path, prefix="output") → str (nome do zip)
- Nome do zip: f"{prefix}_{uuid4().hex[:8]}.zip"
- zipfile.ZipFile em modo "w" com compressão ZIP_DEFLATED
- Retorna apenas o nome do arquivo (não o caminho completo)
```

### `static/js/dwg_to_dxf.js`
```
- Formulário: input[file multiple .dwg], select versão DXF, checkbox audit
- Campo dest_folder + botão "Selecionar pasta" → browseFolder()
- Campo oda_path + botão "Detectar ODA" → GET /api/detect-oda
- Submit: chama sseHelper() com FormData
- Exibe botão de download ao receber evento DOWNLOAD
```

---

## Fase 2 — Escalonamento de DXF `v0.3.0` (~2 dias)

**Objetivo:** upload de .dxf → escalonamento de todas as entidades → .zip com arquivos escalados.

### `services/dxf_scaler.py`
```
- scale_dxf(path, factor, suffix, out_dir) → generator SSE
- Valida: factor > 0, arquivo legível como DXF (ezdxf.readfile)
- Para cada entidade do modelspace:
    matrix = Matrix44.scale(factor, factor, factor)
    entity.transform(matrix)
    if entity.dxftype() == "DIMENSION": entity.render()
- Ajuste de dimstyles:
    multiplicar pelo fator: dimtxt, dimasz, dimtsz, dimcen, dimexe, dimexo
    dividir pelo fator: dimlfac (preserva medidas exibidas)
- try/except por entidade → WARN no log, continua
- doc.saveas(out_dir / f"{stem}{suffix}.dxf")
- Yield: LOG, OK ou FAIL por arquivo; DOWNLOAD e DONE ao final
```

### `routes/dxf_scale.py`
```
Blueprint: dxf_scale, url_prefix=/api

POST /api/dxf-scale
  - Recebe: files[] (multipart .dxf), factor (float), suffix (str), dest_folder
  - Valida factor > 0 (retorna 400 se inválido)
  - Salva em tempdir, chama dxf_scaler.scale_dxf() por arquivo
  - Stream SSE via stream_with_context
  - Zip com todos os arquivos gerados → resolve_output(dest_folder)
```

### `static/js/dxf_scale.js`
```
- Formulário: input[file multiple .dxf], input[number] fator, input[text] sufixo
- Campo dest_folder + botão "Selecionar pasta"
- Submit: chama sseHelper()
- Exibe link de download ao receber DOWNLOAD
```

---

## Fase 3 — DXF → PDF `v0.4.0` (~2 dias)

**Objetivo:** upload de .dxf → renderização com matplotlib → .zip com PDFs.

### `services/dxf_renderer.py`
```
- render_to_pdf(path, paper, orient, bw, out_dir) → generator SSE
- Mapa de tamanhos (mm): A4=(210,297), A3=(297,420), A2=(420,594), A1=(594,841)
- Aplica orientação: swap w/h se landscape
- fig = plt.figure(figsize=(w/25.4, h/25.4))
- ax = fig.add_axes([0, 0, 1, 1])
- ctx = RenderContext(doc)
- Se bw=True: override de todas as cores para preto no ctx
- Frontend(ctx, MatplotlibBackend(ax)).draw_layout(msp)
- plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
- plt.close(fig) — libera memória
- Timeout por arquivo via threading.Timer(120, thread_kill)
- Yield: LOG, OK ou FAIL; DOWNLOAD e DONE ao final
```

### `routes/dxf_to_pdf.py`
```
Blueprint: dxf_to_pdf, url_prefix=/api

POST /api/dxf-to-pdf
  - Recebe: files[] (multipart .dxf ou .dwg), paper, orientation, color_mode, dest_folder
  - Para .dxf: chama dxf_renderer.render_to_pdf() diretamente
  - Para .dwg: pipeline encadeado (implementado em v0.6.0)
  - Stream SSE
  - Zip de saída → resolve_output(dest_folder)

GET /api/detect-accore
  - Busca accoreconsole.exe em caminhos padrão do AutoCAD
  - → {"path": "...", "found": true/false}
```

### `static/js/dxf_to_pdf.js`
```
- Formulário: input[file multiple .dxf/.dwg], select paper, select orientation, radio color/bw
- Campo dest_folder + botão selecionar
- Submit: chama sseHelper()
- Exibe link de download ao receber DOWNLOAD
```

---

## Fase 4 — Editor de PDF (merge) `v0.5.0` (~2 dias)

**Objetivo:** upload de múltiplos PDFs → reordenação de páginas → PDF mesclado.

### `services/pdf_editor.py`
```
- merge_pdfs(files_map: dict[str, Path], sequence: list[dict]) → Path
  - files_map: {file_id: caminho_pdf}
  - sequence: [{file_id, page_index}, ...]
  - Valida cada file_id e page_index
  - PdfWriter().add_page(PdfReader(path).pages[page_index])
  - Salva em out_dir/PDF_Mesclado_{uuid[:6]}.pdf
  - Retorna caminho do arquivo gerado
```

### `routes/pdf_merge.py`
```
Blueprint: pdf_merge, url_prefix=/api

POST /api/pdf-merge
  - Recebe: files[] (multipart PDF), sequence (JSON string)
  - Salva arquivos com file_id gerado pelo frontend (ex.: campo "file_ids[]")
  - Chama pdf_editor.merge_pdfs()
  - Cria zip com o PDF gerado
  - Retorna JSON: {zip, pdf, n_pages, size_bytes}
  - Não usa SSE — retorno JSON direto (operação rápida)
```

### `static/js/pdf_merge.js`
```
- Upload múltiplo de PDFs
- Para cada arquivo: exibe nome e número de páginas
- Lista de páginas reordenável (botões ↑↓ ou drag-and-drop)
- Cada item da lista tem: nome_arquivo | página N | botão remover
- Submit: serializa lista como JSON em campo "sequence"
- Resposta JSON: exibe link de download direto
```

---

## Fase 5 — DWG → PDF (pipeline encadeado) `v0.6.0` (~1 dia)

**Objetivo:** estender `dxf_to_pdf.py` e `dxf_to_pdf.js` para aceitar .dwg, convertendo via ODA antes de renderizar.

### `routes/dxf_to_pdf.py` (extensão)
```
- Detectar extensão do arquivo enviado
- Se .dxf → render_to_pdf() diretamente (já existia em v0.4.0)
- Se .dwg:
    Etapa 1: oda_converter.run_oda() → gera DXF temporário
      Yield: "LOG Convertendo DWG para DXF: arquivo.dwg"
      Yield: "OK arquivo.dxf" (após ODA)
    Etapa 2: dxf_renderer.render_to_pdf() no DXF gerado
      Yield: "LOG Gerando PDF a partir do DXF..."
      Yield: "OK arquivo.pdf"
    finally: shutil.rmtree do tempdir com DXFs intermediários
- Se ODA não disponível e entrada é .dwg:
    Yield: "FAIL arquivo.dwg: ODA não encontrado. Instale o ODA File Converter."
```

### `static/js/dxf_to_pdf.js` (extensão)
```
- Alterar accept do input para ".dxf,.dwg"
- Exibir aviso na UI se ODA não detectado (GET /api/detect-oda ao carregar aba)
- Lógica de SSE permanece igual — server controla o fluxo
```

---

## Fase 6 — Escalar e Cotar (regra FORAN) `v0.7.0` (~3 dias)

**Objetivo:** adaptar as regras de negócio do script de teste `main.py` (cotagem automática de "ninhos" — peças aninhadas geradas pelo FORAN). Para cada DXF enviado: cota o comprimento total e os furos/scallops da vista superior, ajusta o layout (move a vista inferior, duplica labels), insere textos fixos, aplica a escala global e, opcionalmente, explode os blocos — tudo isso de forma idempotente (executar duas vezes no mesmo arquivo não duplica cotas).

> Diferença em relação à Fase 2 (`dxf_scale`): aquela é uma escala "genérica" (qualquer DXF). Esta fase é específica para o fluxo de nesting do FORAN — exige um bloco mestre (`PartBlock`) e camadas com nomes convencionados (`Parts`, `Labels`). Os dois módulos continuam independentes; nada aqui substitui a Fase 2.

### `services/dxf_cotador_foran.py`
```
- garantir_layer(doc, nome_layer, cor) → cria a layer de cotas se não existir
- excluir_layer_completa(doc, nome_layer) → remove entidades de uma execução anterior
  (usado para limpar a layer de cotas e a layer "Free Texts" antes de recotar — garante idempotência)
- configurar_visualizacao_inicial(doc) → ORTHOMODE=1 / SNAPMODE=0 + zoom extents
  via bbox.extents(msp) e doc.set_modelspace_vport()
- atualizar_estilo_cota_global(doc, estilo_cota) → aplica overrides ao dimstyle 'Standard'
  e às variáveis $DIM* do header, para o estilo de cota acompanhar a escala
- obter_limites(entidade) → bbox.extents([entidade]) → (xmin, xmax, ymin, ymax)
- extrair_arcos_unicos(polilinha, raio_minimo, tolerancia) → percorre virtual_entities()
  filtrando ARC; deduplica scallops cortados ao meio (centros a menos de `tolerancia` um do outro)
- cotar_horizontal(bloco, x1, x2, ref_y, base_y, estilo, layer) → add_linear_dim() + render()
- cotar_radial(bloco, centro, raio, a_inicio, a_fim, estilo, layer) → add_radius_dim() + render()
- processar_perfil_foran(bloco_alvo, polilinha, estilo_cota, layer_cota, limite_y) → REGRA DE NEGÓCIO:
    - ignora a polilinha se min_y < limite_y (não cota a vista inferior, só a superior)
    - cota o comprimento total 500u acima do topo da peça
    - para cada furo/scallop que não esteja a menos de `tolerancia_borda` de uma ponta:
        cota a distância até a borda mais próxima (esquerda ou direita, a que for menor)
    - sempre cota o raio de cada furo/scallop encontrado
    - retorna (sucesso: bool, qtd_scallops: int) para o orquestrador acumular totais
- mover_vista_inferior_para_origem(doc, nome_bloco, limite_y, deslocamento=-450)
    → desloca todos os INSERTs do bloco mestre cuja base esteja abaixo de limite_y,
      alinhando a base da vista inferior em Y = deslocamento
- duplicar_e_deslocar_labels(doc, layer_name, offset_principal=-10.0, offset_duplicado=-87.533)
    → desloca as labels originais e cria uma cópia deslocada (para acompanhar a vista duplicada)
- adicionar_textos_no_model_space(doc, config_labels, layer, altura_texto)
    → insere MTEXTs fixos (ex.: "SEÇÃO\nA-A" / "SEÇÃO\nB-B") nas coordenadas informadas
```

### `services/dxf_escala_cotagem.py`
```
- escalar_modelo_completo(doc, fator) → Matrix44.scale(fator,fator,fator) aplicado a cada
  entidade do modelspace via entity.transform(); try/except por entidade (ignora, continua)
- explodir_todos_os_blocos(doc) → loop sobre msp.query('INSERT') até não restar nenhum,
  explodindo recursivamente (suporta blocos aninhados — "matrioskas")
- escalar_e_cotar(path, params, out_dir) → generator SSE
    params recebidos da rota:
      escala (float, obrigatório, >0)
      layer_cota (default "Dimensions")
      layer_textos_antigos (default "Free Texts", opcional — pode ser "" para pular limpeza)
      nome_bloco (default "PartBlock")
      limite_y (default 2000)
      raio_minimo (default 15.0) / tolerancia (default 2.0) / tolerancia_borda (default 5.0)
      explodir_blocos (bool, default true)
      labels (lista opcional de {texto, x, y}; default replica os 2 labels de SEÇÃO A-A/B-B)
    fluxo:
      1. doc = ezdxf.readfile(path)              → FAIL se não for DXF válido
      2. garantir_layer(layer_cota); excluir_layer_completa(layer_cota) e (layer_textos_antigos)
      3. monta estilo_cota_global a partir de `escala` (dimtxt, dimasz, dimexe, dimexo
         multiplicados pela escala; dimdec=0) → atualizar_estilo_cota_global()
      4. localiza o bloco mestre `nome_bloco`     → FAIL "bloco mestre não encontrado" se ausente
      5. para cada bloco != mestre (ninhos): query LWPOLYLINE[layer=="Parts"]
         → processar_perfil_foran() por polilinha, acumulando totais
      6. mover_vista_inferior_para_origem(); duplicar_e_deslocar_labels()
      7. adicionar_textos_no_model_space() com `labels`
      8. escalar_modelo_completo(doc, escala)
      9. se explodir_blocos: explodir_todos_os_blocos(doc)
      10. configurar_visualizacao_inicial(doc)
      11. doc.saveas(out_dir / f"{stem}_cotado.dxf")
    Yield: LOG por etapa relevante; ao final do arquivo, OK <nome>_cotado.dxf com o resumo
      "N perfis cotados / M furos referenciados" embutido no payload
    try/except envolvendo o arquivo inteiro → FAIL <nome>.dxf: <erro> e continua para o próximo
    Yield: DOWNLOAD <uuid>.zip e DONE ao final do lote
```

### `routes/dxf_escala_cotagem.py`
```
Blueprint: dxf_escala_cotagem, url_prefix=/api

POST /api/dxf-escala-cotagem
  - Recebe: files[] (multipart .dxf), escala (float),
            layer_cota, layer_textos_antigos, nome_bloco, limite_y,
            raio_minimo, tolerancia, tolerancia_borda,
            explodir_blocos (0|1), labels (JSON string opcional), dest_folder
  - Valida escala > 0 (retorna 400 se inválido)
  - Salva em tempdir, chama dxf_escala_cotagem.escalar_e_cotar() por arquivo
  - Stream SSE via stream_with_context
  - Zip com todos os *_cotado.dxf → resolve_output(dest_folder)
```

### `static/js/dxf_escala_cotagem.js`
```
- Formulário: input[file multiple .dxf], input[number] escala
- Bloco "Avançado" (recolhível, com defaults já preenchidos):
    layer_cota, nome_bloco, limite_y, raio_minimo, tolerancia, tolerancia_borda
- Checkbox "Explodir blocos após escalar" (marcado por padrão)
- Lista dinâmica opcional de labels fixos (texto + x + y), botão "+ adicionar label"
- Campo dest_folder + botão "Selecionar pasta"
- Submit: serializa labels como JSON, chama sseHelper()
- Exibe o resumo (perfis cotados / furos) extraído do payload do evento OK,
  e o link de download ao receber DOWNLOAD
```

### `templates/index.html` (extensão)
```
- Adiciona a 6ª aba "Escalar e Cotar"
- Reaproveita a área de logs SSE compartilhada (mesmo padrão das outras abas)
```

### `static/css/app.css` (extensão)
```
- Estilo para o bloco "Avançado" recolhível (<details>/<summary> ou toggle)
- Estilo para a lista dinâmica de labels (linha: texto + x + y + botão remover)
```

---

## Fase 7 — Build, polish e empacotamento `v1.0.0` (~2 dias)

**Objetivo:** gerar `CAD_Tools.exe` funcional e documentar o projeto.

### `build.spec`
```python
# PyInstaller spec gerado e editado manualmente
a = Analysis(
    ['app.py'],
    datas=[('templates', 'templates'), ('static', 'static')],
    hiddenimports=['ezdxf', 'matplotlib', 'pypdf', 'ezdxf.addons.drawing'],
)
exe = EXE(a.pure, a.scripts, name='CAD_Tools', console=False, onefile=True)
```

### `app.py` (complemento v1.0.0)
```python
# Porta livre automática
import socket
s = socket.socket(); s.bind(('', 0)); port = s.getsockname()[1]; s.close()

# Abrir Chrome no modo app
import subprocess
subprocess.Popen([chrome_path, f"--app=http://localhost:{port}"])

# Resolver caminhos quando congelado
import sys, os
base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
template_dir = os.path.join(base, 'templates')
static_dir   = os.path.join(base, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
```

### `README.md`
```
## Requisitos
- Python 3.10+ (modo desenvolvimento)
- ODA File Converter (instalação separada — link de download)
- Google Chrome (recomendado para modo app)

## Instalação (desenvolvimento)
pip install flask ezdxf matplotlib pypdf

## Executar
python app.py

## Build do executável
pip install pyinstaller
pyinstaller build.spec
# Saída: dist/CAD_Tools.exe

## Uso do executável
Basta executar CAD_Tools.exe. O app abre automaticamente no Chrome.
```

---

## Ordem de criação recomendada

```
1.  app.py                    ← ponto de entrada, cria tudo
2.  utils/sse.py              ← base de toda comunicação SSE
3.  utils/paths.py            ← resolve caminhos desde o início
4.  utils/deps.py             ← checa dependências ao subir
5.  routes/system.py          ← endpoints utilitários (browse, deps, download)
6.  templates/index.html      ← estrutura HTML das abas
7.  static/css/app.css        ← estilos básicos
8.  static/js/app.js          ← navegação + sseHelper()
    ── v0.1.0 completo ──
9.  services/oda_converter.py
10. utils/zip_utils.py
11. routes/dwg_to_dxf.py
12. static/js/dwg_to_dxf.js
    ── v0.2.0 completo ──
13. services/dxf_scaler.py
14. routes/dxf_scale.py
15. static/js/dxf_scale.js
    ── v0.3.0 completo ──
16. services/dxf_renderer.py
17. routes/dxf_to_pdf.py
18. static/js/dxf_to_pdf.js
    ── v0.4.0 completo ──
19. services/pdf_editor.py
20. routes/pdf_merge.py
21. static/js/pdf_merge.js
    ── v0.5.0 completo ──
22. routes/dxf_to_pdf.py      ← extensão para aceitar .dwg
23. static/js/dxf_to_pdf.js   ← extensão para detectar ODA
    ── v0.6.0 completo ──
24. services/dxf_cotador_foran.py   ← geometria + regras de negócio (sem Flask)
25. services/dxf_escala_cotagem.py  ← orquestrador SSE (escalar_e_cotar)
26. routes/dxf_escala_cotagem.py
27. static/js/dxf_escala_cotagem.js
28. templates/index.html      ← extensão para 6ª aba
29. static/css/app.css        ← extensão (bloco avançado + lista de labels)
    ── v0.7.0 completo ──
30. build.spec
31. README.md
    ── v1.0.0 / release ──
```

---

## Convenção de commits

```
feat(scaffold): add Flask app factory with blueprint registration       # v0.1.0
feat(scaffold): add SSE helper and paths utils                          # v0.1.0
feat(scaffold): add index.html single-page with 5 tabs                  # v0.1.0
feat(oda): add ODAFileConverter subprocess wrapper                      # v0.2.0
feat(oda): add dwg-to-dxf route and frontend form                       # v0.2.0
feat(scale): implement DXF entity scaling with dimstyle adjustment      # v0.3.0
feat(render): add matplotlib PDF export with paper size support         # v0.4.0
feat(merge): implement PDF page merge via pypdf sequence JSON           # v0.5.0
feat(pipeline): chain ODA + renderer for DWG → PDF conversion          # v0.6.0
feat(cotagem): add FORAN profile/scallop auto-dimensioning rules        # v0.7.0
feat(cotagem): add escalar-e-cotar orchestrator with SSE and route      # v0.7.0
fix(sse): handle EventSource disconnect gracefully on client close      # qualquer fase
chore(build): add PyInstaller spec with template and static data        # v1.0.0
docs: add README with installation, build and usage instructions        # v1.0.0
```

---

## Endpoints — resumo final

| Método | Rota | Fase | Arquivo |
|--------|------|------|---------|
| `GET` | `/` | v0.1.0 | `routes/system.py` |
| `GET` | `/api/browse-folder` | v0.1.0 | `routes/system.py` |
| `GET` | `/api/deps` | v0.1.0 | `routes/system.py` |
| `GET` | `/api/detect-oda` | v0.1.0 | `routes/system.py` |
| `GET` | `/api/download/<filename>` | v0.1.0 | `routes/system.py` |
| `GET` | `/api/shutdown` | v0.1.0 | `routes/system.py` |
| `POST` | `/api/dwg-to-dxf` | v0.2.0 | `routes/dwg_to_dxf.py` |
| `POST` | `/api/dxf-scale` | v0.3.0 | `routes/dxf_scale.py` |
| `POST` | `/api/dxf-to-pdf` | v0.4.0 + v0.6.0 | `routes/dxf_to_pdf.py` |
| `GET` | `/api/detect-accore` | v0.4.0 | `routes/dxf_to_pdf.py` |
| `POST` | `/api/pdf-merge` | v0.5.0 | `routes/pdf_merge.py` |
| `POST` | `/api/dxf-escala-cotagem` | v0.7.0 | `routes/dxf_escala_cotagem.py` |
