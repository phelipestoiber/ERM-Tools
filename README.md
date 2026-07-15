# CAD Tools · v0.8.2

Aplicação web interna para manipulação de arquivos CAD (DWG, DXF) e PDF, com interface no navegador e processamento local via Python + Flask.

---

## Índice

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Requisitos](#requisitos)
- [Instalação e execução](#instalação-e-execução)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Arquitetura técnica](#arquitetura-técnica)
- [Rotas da API](#rotas-da-api)
- [Empacotamento como .exe](#empacotamento-como-exe)
- [Dependências externas](#dependências-externas)
- [Solução de problemas](#solução-de-problemas)

---

## Visão geral

CAD Tools é uma aplicação Flask de uso interno que expõe ferramentas de processamento de arquivos CAD e PDF através de uma interface web single-page. O servidor roda localmente (`127.0.0.1`) e se abre automaticamente no Chrome em modo "app" (sem barra de endereços), simulando o comportamento de uma aplicação nativa de desktop.

O progresso de todas as operações é transmitido em tempo real via **Server-Sent Events (SSE)** — sem necessidade de polling ou websockets.

---

## Funcionalidades

### ⇄ DWG → DXF
Converte arquivos `.dwg` para `.dxf` usando o **ODA File Converter** como motor externo.

- Upload de múltiplos arquivos DWG
- Detecção automática do ODA File Converter nas pastas padrão de instalação
- Seleção da versão DXF de saída (ACAD2000 a ACAD2018)
- Opção de auditoria (`AUDIT`) integrada
- Download do resultado como ZIP

### ⊞ DXF Scale
Escala entidades de arquivos DXF por um fator numérico usando **ezdxf**.

- Suporte a todas as entidades do modelspace: linhas, polilinhas, círculos, arcos, textos, MTEXTs, inserções de bloco, cotas
- Ajuste proporcional de estilos de cota (`dimtxt`, `dimasz`, `dimtsz`, etc.)
- Correção automática de MTEXTs com `text_direction` degenerado (gerados pelo ODA)
- Atualização de textos de cota sobrescritos manualmente (se numéricos puros)
- Sufixo configurável para o nome do arquivo de saída

### ⎙ DXF / DWG → PDF
Renderiza arquivos DXF (ou DWG, via pipeline ODA→DXF) como PDF usando **ezdxf.addons.drawing** + **matplotlib**.

- Tamanhos de papel: A4, A3, A2, A1
- Orientação: paisagem ou retrato
- Modo de cor: cores originais ou preto e branco
- Zoom extents automático — o desenho ocupa toda a folha sem distorção
- Renderização em thread com timeout de 120 s por arquivo
- Pipeline automático DWG→DXF→PDF (requer ODA instalado)

### ⊕ PDF Editor
Mescla e reordena páginas de múltiplos PDFs usando **pypdf**.

- Upload de vários PDFs com pré-visualização de cada página (renderizada localmente pelo pdf.js)
- Grade de miniaturas arrastáveis (drag-and-drop via SortableJS) para reordenar páginas
- Rotação individual de páginas (90° por clique)
- Remoção de páginas individuais antes do merge
- Fluxo em duas etapas: staging (upload + leitura de metadados) → merge final
- Limpeza automática de arquivos de staging abandonados (> 2 horas)

### ⊟ Escalar e Cotar `FORAN`
Cotagem automática de perfis/ninhos no padrão **FORAN** para estaleiros.

- Detecta a vista superior (por posição Y) e cota o comprimento total da peça
- Extrai e cota arcos/scallops com deduplicação de furos cortados ao meio
- Lógica de ancoragem: cota cada scallop pelo lado mais próximo da borda
- Escala global aplicada após a cotagem
- Explosão opcional de blocos aninhados (`INSERT → entidades`)
- Labels de seção configuráveis com posição livre (padrão: SEÇÃO A-A / SEÇÃO B-B)
- Parâmetros avançados configuráveis: layer de cotas, nome do bloco mestre, limites, raios mínimos, tolerâncias

### 📊 Direcionamento `Excel`
Calcula o direcionamento e apontamento de peças segundo a **regra Navipeças**, a partir de uma planilha Excel.

- Lê colunas `DNA` e `Ip Type` da planilha de entrada
- Calcula rota de fabricação (`LOGISTICA→EDIFICACAO`, `PRE-FABRICACAO→PAINEL`, etc.)
- Herança de rota para peças internas (filhos herdam rota do pai na hierarquia DNA)
- Exporta planilha formatada com tabela Excel, largura automática de colunas, logo da empresa e layout de impressão A4 paisagem
- Coluna `N.` com fórmula `SUBTOTAL` (contagem correta mesmo com filtros ativos)

---

## Requisitos

### Python
- Python **3.10 ou superior**

### Bibliotecas Python
Instaladas automaticamente pelo `iniciar.bat` a partir do `requirements.txt`:

```
Flask          3.1+
ezdxf          1.4+
matplotlib     3.10+
pypdf          6.13+
pandas         2.3+
openpyxl       3.1+
xlsxwriter     3.2+
Pillow         12+
numpy          2.2+
```

### Ferramentas externas (opcionais, mas necessárias para certas funções)

| Ferramenta | Função | Download |
|---|---|---|
| **ODA File Converter** | Conversão DWG → DXF | [opendesign.com](https://www.opendesign.com/guestfiles/oda_file_converter) |

O ODA File Converter deve ser instalado no sistema. O app o detecta automaticamente nas seguintes pastas:

```
C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe
C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe
C:\Program Files\ODA File Converter\ODAFileConverter.exe
```

---

## Instalação e execução

### Modo desenvolvimento (recomendado)

Basta executar o script de inicialização na raiz do projeto:

```
iniciar.bat
```

O script faz automaticamente:
1. Verifica se Python 3.10+ está instalado e acessível no PATH
2. Cria um ambiente virtual `.venv` (se ainda não existir)
3. Atualiza o `pip`
4. Instala todos os pacotes do `requirements.txt`
5. Inicia o servidor Flask na porta `5123`
6. Abre o Chrome em modo app (`--app=http://127.0.0.1:5123`)

### Manual (sem o .bat)

```bash
# Criar e ativar o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Iniciar o servidor
python app.py
```

Acesse `http://127.0.0.1:5123` no navegador.

> **Atenção:** não use o Live Server do VS Code (porta 5500). O frontend depende das rotas do Flask para funcionar.

---

## Estrutura do projeto

```
cad-tools/
│
├── app.py                      # Fábrica Flask + ponto de entrada
├── iniciar.bat                 # Launcher Windows (venv + deps + servidor)
├── requirements.txt
│
├── routes/                     # Blueprints Flask (uma rota por módulo)
│   ├── system.py               # /, /api/deps, /api/browse-folder, /api/download, /api/shutdown
│   ├── dwg_to_dxf.py           # POST /api/dwg-to-dxf
│   ├── dxf_scale.py            # POST /api/dxf-scale
│   ├── dxf_to_pdf.py           # POST /api/dxf-to-pdf
│   ├── pdf_merge.py            # POST /api/pdf-stage  +  POST /api/pdf-merge
│   ├── dxf_escala_cotagem.py   # POST /api/dxf-escala-cotagem
│   └── direcionamento.py       # POST /api/direcionamento-excel
│
├── services/                   # Lógica de negócio (sem dependência do Flask)
│   ├── oda_converter.py        # Wrapper do ODA File Converter
│   ├── dxf_scaler.py           # Escala de entidades DXF
│   ├── dxf_renderer.py         # Renderização DXF → PDF (matplotlib)
│   ├── pdf_editor.py           # Staging + merge de PDFs (pypdf)
│   ├── dxf_escala_cotagem.py   # Orquestrador FORAN (escala + cotagem)
│   ├── dxf_cotador_foran.py    # Motor de cotagem FORAN (puro, sem Flask)
│   └── direcionamento_excel.py # Cálculo de rotas Navipeças
│
├── utils/
│   ├── sse.py                  # Helpers de eventos SSE
│   ├── zip_utils.py            # Criação de ZIPs de saída
│   ├── paths.py                # Resolução de caminhos (dev vs. .exe)
│   └── deps.py                 # Verificação de dependências em runtime
│
├── templates/
│   └── index.html              # SPA principal (única página HTML)
│
├── static/
│   ├── css/app.css             # Estilos (tema escuro)
│   ├── js/app.js               # Navegação, SSE helper, browseFolder, loadDeps
│   ├── js/dwg_to_dxf.js
│   ├── js/dxf_scale.js
│   ├── js/dxf_to_pdf.js
│   ├── js/pdf_merge.js
│   ├── js/dxf_escala_cotagem.js
│   ├── js/direcionamento.js
│   └── img/logo.png            # Logo para cabeçalho de impressão (Direcionamento)
│
├── output/                     # Pasta de saída padrão (criada automaticamente)
├── staging/                    # Arquivos temporários do PDF Editor (criada automaticamente)
└── .venv/                      # Ambiente virtual Python (criado pelo iniciar.bat)
```

---

## Arquitetura técnica

### Comunicação frontend → backend

Todas as operações de processamento usam o padrão **POST + SSE**:

1. O frontend envia os arquivos via `fetch` com `FormData` (multipart/form-data)
2. O backend responde com `Content-Type: text/event-stream` e vai enviando eventos conforme processa
3. O frontend lê os eventos com `ReadableStream` e atualiza a UI em tempo real

Formato dos eventos SSE:

```
data: LOG  mensagem de progresso
data: OK   nome_do_arquivo_gerado.dxf
data: FAIL nome_do_arquivo.dwg: descrição do erro
data: DOWNLOAD uuid_do_zip.zip
data: DONE
```

### Fluxo de arquivos

```
Upload (multipart)
    └─> tmp_dir/   (pasta temporária por requisição)
            └─> services/  (processamento)
                    └─> out_dir/ (temporário)
                            └─> output/ (ZIP final)
                                    └─> /api/download/<zip>  (download)
```

As pastas temporárias são sempre removidas no bloco `finally` de cada generator SSE, independentemente de sucesso ou falha.

### Resolução de caminhos (dev vs. .exe)

O módulo `utils/paths.py` usa `sys._MEIPASS` quando o app está congelado pelo PyInstaller, garantindo que templates e assets sejam encontrados corretamente dentro do executável.

---

## Rotas da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Página inicial (SPA) |
| `GET` | `/api/browse-folder` | Abre diálogo de pasta nativo (tkinter) |
| `GET` | `/api/deps` | Status de todas as dependências |
| `GET` | `/api/detect-oda` | Detecta ODA File Converter |
| `GET` | `/api/detect-accore` | Detecta accoreconsole.exe (AutoCAD) |
| `GET` | `/api/download/<filename>` | Download de arquivo da pasta `output/` |
| `GET` | `/api/shutdown` | Encerra o servidor Flask |
| `POST` | `/api/dwg-to-dxf` | Converte DWG → DXF — resposta SSE |
| `POST` | `/api/dxf-scale` | Escala arquivos DXF — resposta SSE |
| `POST` | `/api/dxf-to-pdf` | Converte DXF/DWG → PDF — resposta SSE |
| `POST` | `/api/pdf-stage` | Staging de PDFs (upload + metadados) — JSON |
| `POST` | `/api/pdf-merge` | Merge de páginas — JSON |
| `POST` | `/api/dxf-escala-cotagem` | Escala + cotagem FORAN — resposta SSE |
| `POST` | `/api/direcionamento-excel` | Direcionamento Navipeças — resposta SSE |

### Parâmetros das rotas SSE

**POST `/api/dwg-to-dxf`** — `multipart/form-data`

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `files[]` | arquivo(s) | — | Arquivos .dwg |
| `oda_path` | texto | auto-detectado | Caminho do ODAFileConverter.exe |
| `version` | texto | `ACAD2013` | Versão DXF de saída |
| `audit` | `0`/`1` | `0` | Executar auditoria |
| `dest_folder` | texto | `output/` | Pasta de destino |

**POST `/api/dxf-scale`** — `multipart/form-data`

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `files[]` | arquivo(s) | — | Arquivos .dxf |
| `factor` | número | — | Fator de escala (> 0) |
| `suffix` | texto | `_scaled` | Sufixo do arquivo de saída |
| `dest_folder` | texto | `output/` | Pasta de destino |

**POST `/api/dxf-to-pdf`** — `multipart/form-data`

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `files[]` | arquivo(s) | — | Arquivos .dxf e/ou .dwg |
| `paper` | `A4`/`A3`/`A2`/`A1` | `A4` | Tamanho do papel |
| `orientation` | `landscape`/`portrait` | `landscape` | Orientação |
| `color_mode` | `color`/`bw` | `color` | Modo de cor |
| `dest_folder` | texto | `output/` | Pasta de destino |

**POST `/api/dxf-escala-cotagem`** — `multipart/form-data`

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `files[]` | arquivo(s) | — | Arquivos .dxf |
| `escala` | número | — | Fator de escala (> 0) |
| `layer_cota` | texto | `Dimensions` | Layer para inserção de cotas |
| `layer_textos_antigos` | texto | `Free Texts` | Layer a limpar antes de recotar |
| `nome_bloco` | texto | `PartBlock` | Nome do bloco mestre |
| `limite_y` | número | `2000` | Limite Y para separar vistas |
| `raio_minimo` | número | `15.0` | Raio mínimo de scallop |
| `tolerancia` | número | `2.0` | Tolerância de deduplicação |
| `tolerancia_borda` | número | `5.0` | Tolerância de scallop de extremidade |
| `explodir_blocos` | `0`/`1` | `1` | Explodir blocos após escalar |
| `labels` | JSON | padrão FORAN | Lista de labels fixos `[{texto,x,y}]` |
| `dest_folder` | texto | `output/` | Pasta de destino |

---

## Empacotamento como .exe

Para gerar um único executável Windows com PyInstaller:

```bash
pip install pyinstaller

pyinstaller ^
  --onefile ^
  --windowed ^
  --name CAD_Tools ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --hidden-import=ezdxf ^
  --hidden-import=matplotlib ^
  --hidden-import=pypdf ^
  --hidden-import=pandas ^
  --hidden-import=openpyxl ^
  --hidden-import=xlsxwriter ^
  --hidden-import=PIL ^
  app.py
```

O executável será gerado em `dist/CAD_Tools.exe`.

**Comportamento do .exe:**

- Ao ser executado, procura uma porta TCP livre automaticamente (em vez de fixar 5123)
- Inicia o servidor Flask nessa porta
- Abre o Chrome em modo `--app=http://127.0.0.1:<porta>` após 1.2 segundos
- Se o Chrome não for encontrado, usa o navegador padrão do sistema

> O ODA File Converter **não** é embutido no executável — precisa estar instalado separadamente no sistema do usuário.

---

## Dependências externas

### ODA File Converter

Necessário para as funcionalidades DWG→DXF e DWG→PDF.

1. Baixe em: https://www.opendesign.com/guestfiles/oda_file_converter
2. Instale em `C:\Program Files\ODA\`
3. O CAD Tools detecta automaticamente na inicialização

Verifique o status na aba **Dependências** dentro do app.

---

## Solução de problemas

**O app não abre o Chrome automaticamente**

O app tenta encontrar o Chrome nos caminhos padrão de instalação. Se não encontrar, usa `webbrowser.open()` e abre o navegador padrão do sistema. Nesse caso, abra manualmente `http://127.0.0.1:5123`.

**"ODA não encontrado" na aba DWG → DXF**

Instale o ODA File Converter. Se ele estiver em um caminho não padrão, informe o caminho manualmente no campo "ODA File Converter" e clique em Converter.

**Erro ao escalar DXF: "Biblioteca não instalada"**

Execute no terminal (com o venv ativado):
```bash
pip install ezdxf
```

**Erro ao gerar PDF: renderização travou**

Arquivos DXF muito complexos podem exceder o timeout de 120 s por arquivo. Tente dividir o arquivo em partes menores antes de converter.

**Erro na planilha de Direcionamento: "colunas 'DNA' e 'Ip Type' não encontradas"**

A planilha de entrada precisa ter exatamente essas colunas (maiúsculas/minúsculas importam). Verifique os cabeçalhos e reenvie.

**O servidor Flask não inicia (porta em uso)**

Em modo desenvolvimento, a porta fixa é `5123`. Se estiver em uso, encerre o processo que a ocupa ou edite `DEV_PORT` em `app.py`. Em modo `.exe`, o app usa uma porta livre automaticamente.

**Pasta de destino inválida**

Se a pasta informada não existir ou não for acessível, o app salva os arquivos em `output/` na raiz do projeto automaticamente.