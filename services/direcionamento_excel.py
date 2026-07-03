"""Direcionamento de peças a partir de planilha Excel (regra Navipeças).

Adaptado do script standalone `main.py` (Tkinter) para o padrão de serviço
SSE do CAD Tools. A lógica de negócio (cálculo de rota, herança de
apontamento, layout de exportação) foi mantida idêntica ao original —
apenas a camada de interface (tkinter) foi substituída por eventos SSE.

Uso:
    for chunk in processar_direcionamento(path, out_dir):
        yield chunk   # repassar como SSE ao Flask

Eventos SSE emitidos:
    LOG  <mensagem>            — progresso informativo
    OK   <resultado.xlsx>      — planilha gerada com sucesso
    FAIL <arquivo>: <erro>     — falha (interrompe o processamento — é 1 arquivo só)
    DOWNLOAD <uuid.zip>        — zip disponível para download
    DONE                       — fim do stream
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from utils.paths import get_resource_path
from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# Nome do arquivo de saída gerado
_OUTPUT_NAME = "resultado_direcionamento.xlsx"

# Caminho da logo empacotada — resolvido via get_resource_path para
# funcionar tanto em dev quanto congelado pelo PyInstaller (sys._MEIPASS)
_LOGO_RESOURCE = "static/img/logo.png"

# ── REGRAS DE NEGÓCIO (idênticas ao main.py original) ──────────────────

_REGRAS_ORIGEM = {
    "Cortado": "LOGISTICA",
    "Calandrado": "PRE-FABRICACAO",
    "Soldado": "PRE-FABRICACAO",
    "Dobrados": "CONFORMACAO",
    "Painel": "FABRICACAO",
    "Pre-Edificacao": "GALPAO",
    "Submontagem": "EDIFICACAO",
}

_REGRAS_DESTINO = {
    "Bloco": "EDIFICACAO",
    "Painel": "PAINEL",
    "Pre-Edificacao": "PRE-EDIFICACAO",
    "Cortado": "EDIFICACAO",
    "Submontagem": "EDIFICACAO",
}

_TIPOS_INTERNOS = [
    "Internal part", "Internal profile", "Internal flat bar", "Collar plate",
    "Internal bracket plate", "Internal macro plate", "Shell plate",
    "Internal standard plate", "Frame",
]

_COLUNAS_RENOMEADAS = {
    "Scantling/Thickness": "Espessura",
    "Node Name": "Peça",
    "Node Description": "Descrição Peça",
    "Parent Node": "Destino",
    "Parent Node Description": "Descrição Destino",
    "Block": "Bloco",
}

_COLUNAS_PRINCIPAIS = [
    "N.", "Bloco", "Peça", "Descrição Peça", "Descrição Destino",
    "Espessura", "Apontamento", "Direcionamento",
]


def _calcular_rota_principal(row, tipos_internos):
    import numpy as np
    import pandas as pd

    ip_type = row["Ip Type"]
    if pd.isna(ip_type):
        return "0"
    if ip_type in ["IP", "Bloco"] or ip_type in tipos_internos:
        return np.nan
    if ip_type in _REGRAS_ORIGEM:
        origem = _REGRAS_ORIGEM[ip_type]
        tipo_pai = row["Ip_Type_Pai"]
        destino = _REGRAS_DESTINO.get(tipo_pai, "EDIFICACAO")
        return f"{origem}->{destino}"
    return "0"


def _herdar_rota(row, mapa_rotas, tipos_internos):
    import pandas as pd

    if pd.notna(row["Rota_Calculada"]):
        return row["Rota_Calculada"]
    if row["Ip Type"] in tipos_internos:
        return mapa_rotas.get(row["DNA_Pai"], "0")
    return "0"


def _definir_apontamento(row, tipos_internos):
    import numpy as np
    import pandas as pd

    if pd.isna(row["Ip Type"]):
        return np.nan
    if row["Ip Type"] in tipos_internos:
        return row["Ip_Type_Pai"]
    return row["Ip Type"]


def _processar_dataframe(df):
    """Aplica toda a lógica de cálculo de rota/apontamento. Retorna o df pronto para export."""
    df["DNA_Str"] = df["DNA"].astype(str)
    df["DNA_Pai"] = df["DNA_Str"].apply(lambda x: x.rsplit("/", 1)[0] if "/" in x else x)

    mapa_ip_type = dict(zip(df["DNA_Str"], df["Ip Type"]))
    df["Ip_Type_Pai"] = df["DNA_Pai"].map(mapa_ip_type)

    df["Rota_Calculada"] = df.apply(
        lambda row: _calcular_rota_principal(row, _TIPOS_INTERNOS), axis=1
    )
    mapa_rotas = dict(zip(df["DNA_Str"], df["Rota_Calculada"]))

    df["Direcionamento"] = df.apply(
        lambda row: _herdar_rota(row, mapa_rotas, _TIPOS_INTERNOS), axis=1
    )
    df["Apontamento"] = df.apply(
        lambda row: _definir_apontamento(row, _TIPOS_INTERNOS), axis=1
    )

    df = df.drop(columns=["DNA_Str", "DNA_Pai", "Ip_Type_Pai", "Rota_Calculada"])

    # Renomeia colunas conhecidas
    renomear = {k: v for k, v in _COLUNAS_RENOMEADAS.items() if k in df.columns}
    if renomear:
        df = df.rename(columns=renomear)

    df = df.sort_values(by="DNA", ascending=True).reset_index(drop=True)

    # Coluna N. — fórmula SUBTOTAL, preservada do original (permite
    # contagem correta de linhas visíveis quando o usuário filtra a tabela)
    formulas_subtotal = [f"=SUBTOTAL(3, $C$2:C{i})" for i in range(2, len(df) + 2)]
    df.insert(0, "N.", formulas_subtotal)

    import numpy as np
    for col in _COLUNAS_PRINCIPAIS:
        if col not in df.columns:
            df[col] = np.nan

    resto = [c for c in df.columns if c not in _COLUNAS_PRINCIPAIS]
    df = df[_COLUNAS_PRINCIPAIS + resto]

    return df


def _exportar_xlsx(df, caminho_saida: Path, nome_arquivo_original: str, tmp_dir: Path):
    """Exporta o df para xlsx formatado (tabela, largura, logo, rodapé) via xlsxwriter."""
    import pandas as pd

    with pd.ExcelWriter(str(caminho_saida), engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Planilha1", header=False, startrow=1)

        workbook = writer.book
        worksheet = writer.sheets["Planilha1"]

        max_row = len(df)
        max_col = len(df.columns) - 1

        # Largura das colunas
        for i, col_name in enumerate(df.columns):
            if i == 0:
                worksheet.set_column(i, i, 8)  # coluna N. fixa
            else:
                tamanho_titulo = len(str(col_name))
                tamanho_dados = (
                    df[col_name].astype(str).map(len).max() if not df[col_name].empty else 0
                )
                max_length = max(tamanho_titulo, tamanho_dados) + 2
                worksheet.set_column(i, i, max_length)

        # Tabela oficial do Excel (listrada)
        col_settings = [{"header": str(col)} for col in df.columns]
        worksheet.add_table(
            0, 0, max_row, max_col,
            {"columns": col_settings, "style": "Table Style Medium 16"},
        )

        # Configurações de impressão
        worksheet.print_area(0, 0, max_row, 7)
        worksheet.repeat_rows(0)
        worksheet.set_landscape()
        worksheet.set_paper(9)
        worksheet.fit_to_pages(1, 0)
        worksheet.set_margins(left=0.7, right=0.7, top=0.75, bottom=0.75)

        # Cabeçalho com logo redimensionada
        caminho_logo = get_resource_path(_LOGO_RESOURCE)
        nome_arquivo_curto = os.path.basename(nome_arquivo_original)

        if os.path.exists(caminho_logo):
            try:
                from PIL import Image

                altura_desejada_pixels = 45
                caminho_logo_ajustada = tmp_dir / "logo_print_temp.png"

                with Image.open(caminho_logo) as img:
                    largura_proporcional = int(
                        (altura_desejada_pixels / float(img.height)) * img.width
                    )
                    filtro_qualidade = getattr(Image, "Resampling", Image).LANCZOS
                    img_redimensionada = img.resize(
                        (largura_proporcional, altura_desejada_pixels), filtro_qualidade
                    )
                    img_redimensionada.save(caminho_logo_ajustada)

                worksheet.set_header("&L&G", {"image_left": str(caminho_logo_ajustada)})
            except ImportError:
                # Pillow ausente — usa a logo original sem redimensionar
                worksheet.set_header("&L&G", {"image_left": caminho_logo})

        worksheet.set_footer(f"&L{nome_arquivo_curto}&C&P de &N&R&D")


def processar_direcionamento(arquivo_entrada: Path, dest_dir: str | Path):
    """Generator SSE que processa uma planilha Excel e gera o direcionamento.

    Args:
        arquivo_entrada: Caminho do .xlsx/.xls já salvo em disco.
        dest_dir:         Pasta de destino para o ZIP final.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    arquivo_entrada = Path(arquivo_entrada)
    dest_dir = Path(dest_dir)

    try:
        import pandas as pd  # noqa: F401
        import numpy as np  # noqa: F401
        import xlsxwriter  # noqa: F401
    except ImportError as exc:
        yield sse_fail(
            "dependências",
            f"Biblioteca não instalada: {exc}. "
            "Execute: pip install pandas numpy openpyxl xlsxwriter",
        )
        yield sse_done()
        return

    if not arquivo_entrada.exists():
        yield sse_fail(arquivo_entrada.name, "Arquivo de entrada não encontrado.")
        yield sse_done()
        return

    if arquivo_entrada.suffix.lower() not in (".xlsx", ".xls"):
        yield sse_fail(arquivo_entrada.name, "Formato inválido — envie um .xlsx ou .xls.")
        yield sse_done()
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_direcionamento_"))
    inicio = time.time()

    try:
        yield sse_log(f"Lendo planilha: {arquivo_entrada.name}...")

        import pandas as pd

        try:
            df = pd.read_excel(arquivo_entrada)
        except Exception as exc:
            yield sse_fail(arquivo_entrada.name, f"Falha ao ler o Excel: {exc}")
            return

        if "DNA" not in df.columns or "Ip Type" not in df.columns:
            yield sse_fail(
                arquivo_entrada.name,
                "O arquivo Excel precisa ter as colunas exatas 'DNA' e 'Ip Type'.",
            )
            return

        yield sse_log(f"{len(df)} linha(s) carregada(s). Calculando direcionamento...")

        try:
            df = _processar_dataframe(df)
        except Exception as exc:
            yield sse_fail(arquivo_entrada.name, f"Falha no cálculo de rotas: {exc}")
            return

        yield sse_log("Exportando planilha formatada (tabela, logo, layout de impressão)...")

        out_path = tmp_dir / _OUTPUT_NAME
        try:
            _exportar_xlsx(df, out_path, arquivo_entrada.name, tmp_dir)
        except Exception as exc:
            yield sse_fail(arquivo_entrada.name, f"Falha ao exportar Excel: {exc}")
            return
        finally:
            # Limpeza da logo temporária, se sobrou
            logo_temp = tmp_dir / "logo_print_temp.png"
            if logo_temp.exists():
                logo_temp.unlink(missing_ok=True)

        tempo = time.time() - inicio
        yield sse_log(f"Concluído em {tempo:.2f}s.")
        yield sse_ok(_OUTPUT_NAME)

        zip_name = create_zip([out_path], dest_dir, prefix="direcionamento")
        yield sse_log(f"ZIP gerado: {zip_name}")
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail(arquivo_entrada.name, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        yield sse_done()
