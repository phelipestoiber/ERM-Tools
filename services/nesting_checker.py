"""Verificador de Nestings Idênticos por Assinatura Geométrica.

Analisa todos os arquivos DXF de uma pasta (ou lista de arquivos),
compara suas geometrias e agrupa os idênticos.

Algoritmo:
    Para cada DXF, extrai os vértices (x, y, bulge) de todas as
    LWPOLYLINEs nas layers relevantes ("Parts", "Markings", "Gross
    Plates"), ordena a lista e gera uma tupla imutável como
    "impressão digital". Arquivos com tupla idêntica são nestings
    geometricamente iguais, independentemente do nome.

Eventos SSE emitidos:
    LOG  <mensagem>           — progresso informativo
    OK   <grupo>              — grupo de nestings idênticos encontrado
    FAIL <arquivo>: <erro>    — arquivo ilegível (processamento continua)
    DOWNLOAD <uuid.zip>       — ZIP com o relatório .txt disponível
    DONE                      — fim do stream
"""

from __future__ import annotations

import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# Layers cujas geometrias definem a identidade do nesting
_LAYERS_ALVO = ["Parts", "Markings", "Gross Plates"]

_OUTPUT_NAME = "relatorio_nesting.txt"


# =====================================================================
# ASSINATURA GEOMÉTRICA
# =====================================================================

def _gerar_assinatura_geometrica(filepath: Path):
    """Lê o DXF e retorna uma tupla imutável com os vértices das
    LWPOLYLINEs nas layers relevantes.

    Raises:
        RuntimeError: se o arquivo não puder ser lido.

    Returns:
        Tupla ordenada de vértices, ou tupla vazia se nenhuma
        geometria relevante for encontrada.
    """
    import ezdxf

    try:
        doc = ezdxf.readfile(str(filepath))
    except Exception as exc:
        raise RuntimeError(f"Falha ao ler DXF: {exc}") from exc

    assinatura: list = []

    for bloco in doc.blocks:
        # Ignora layouts de impressão (*Model_Space, *Paper_Space…)
        if bloco.name.startswith("*"):
            continue

        for layer in _LAYERS_ALVO:
            for poly in bloco.query(f'LWPOLYLINE[layer=="{layer}"]'):
                pontos = []
                for pt in poly:
                    x = round(pt[0], 2)
                    y = round(pt[1], 2)
                    # bulge ≠ 0 → segmento é um arco (scallop)
                    bulge = round(pt[4], 3) if len(pt) > 4 else 0.0
                    pontos.append((x, y, bulge))

                if pontos:
                    assinatura.append(tuple(pontos))

    assinatura.sort()
    return tuple(assinatura)


# =====================================================================
# FORMATAÇÃO E RELATÓRIO
# =====================================================================

def _formatar_nomes(nomes: list[str]) -> str:
    """Formata uma lista de nomes de arquivo para leitura natural."""
    limpos = [Path(n).stem for n in nomes]
    if len(limpos) == 1:
        return limpos[0]
    if len(limpos) == 2:
        return f"{limpos[0]} e {limpos[1]}"
    return ", ".join(limpos[:-1]) + f" e {limpos[-1]}"


def _gerar_txt(grupos: dict, falhas: list[tuple], tmp_dir: Path, nome_pasta: str) -> Path:
    """Escreve o relatório completo em disco e retorna o caminho."""
    agrupados = [(sig, arqs) for sig, arqs in grupos.items() if len(arqs) > 1]
    unicos    = [(sig, arqs) for sig, arqs in grupos.items() if len(arqs) == 1]

    linhas: list[str] = []

    linhas += [
        "=" * 64,
        "  RELATÓRIO DE NESTINGS IDÊNTICOS",
        f"  Pasta: {nome_pasta}",
        "=" * 64,
        "",
    ]

    if agrupados:
        linhas.append("── GRUPOS IDÊNTICOS " + "─" * 44)
        for _, arquivos in sorted(agrupados, key=lambda x: len(x[1]), reverse=True):
            linhas.append(f"  [AGRUPADO] {_formatar_nomes(arquivos)}")
            linhas.append(f"             → {len(arquivos)} nestings idênticos")
            linhas.append("")

    if unicos:
        linhas.append("── ÚNICOS " + "─" * 54)
        for _, arquivos in unicos:
            linhas.append(f"  [ÚNICO]    {Path(arquivos[0]).stem}")
        linhas.append("")

    if falhas:
        linhas.append("── FALHAS " + "─" * 54)
        for nome, motivo in falhas:
            linhas.append(f"  [FALHA]    {nome}: {motivo}")
        linhas.append("")

    linhas += [
        "=" * 64,
        f"  Grupos idênticos : {len(agrupados)}",
        f"  Nestings únicos  : {len(unicos)}",
        f"  Falhas           : {len(falhas)}",
        "=" * 64,
    ]

    out_path = tmp_dir / _OUTPUT_NAME
    out_path.write_text("\n".join(linhas), encoding="utf-8")
    return out_path


# =====================================================================
# GENERATOR SSE
# =====================================================================

def verificar_nestings(arquivos: list[Path], dest_dir: str | Path, nome_pasta: str = ""):
    """Generator SSE que analisa uma lista de DXFs e agrupa os idênticos.

    Args:
        arquivos:   Lista de caminhos para os .dxf já salvos em disco.
        dest_dir:   Pasta de destino para o ZIP com o relatório.
        nome_pasta: Nome da pasta original (aparece no relatório).

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    dest_dir = Path(dest_dir)

    try:
        import ezdxf  # noqa: F401
    except ImportError:
        yield sse_fail("ezdxf", "Biblioteca não instalada. Execute: pip install ezdxf")
        yield sse_done()
        return

    if not arquivos:
        yield sse_fail("validação", "Nenhum arquivo DXF encontrado.")
        yield sse_done()
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_nesting_out_"))

    try:
        yield sse_log(f"Iniciando escaneamento de {len(arquivos)} arquivo(s) DXF...")
        yield sse_log("")

        grupos: dict = defaultdict(list)
        falhas: list[tuple] = []

        # ── Fase 1: gerar assinaturas ──────────────────────────────────
        for idx, arquivo in enumerate(arquivos, 1):
            nome = arquivo.name
            yield sse_log(f"[{idx}/{len(arquivos)}] Analisando: {nome}")

            try:
                sig = _gerar_assinatura_geometrica(arquivo)
                if not sig:
                    yield sse_log(f"  ⚠ {nome}: sem geometria nas layers alvo — ignorado")
                else:
                    grupos[sig].append(nome)
            except Exception as exc:
                yield sse_fail(nome, str(exc))
                falhas.append((nome, str(exc)))

        # ── Fase 2: relatório no log ───────────────────────────────────
        yield sse_log("")
        yield sse_log("=" * 60)
        yield sse_log(" RELATÓRIO DE NESTINGS IDÊNTICOS")
        yield sse_log("=" * 60)
        yield sse_log("")

        agrupados_count = 0
        unicos_count    = 0

        for sig, arqs in sorted(grupos.items(), key=lambda x: len(x[1]), reverse=True):
            qtd = len(arqs)
            nomes_fmt = _formatar_nomes(arqs)
            if qtd > 1:
                yield sse_ok(f"{nomes_fmt} → {qtd} idênticos")
                agrupados_count += 1
            else:
                yield sse_log(f"[ÚNICO]    {Path(arqs[0]).stem}")
                unicos_count += 1

        yield sse_log("")
        yield sse_log(
            f"Grupos idênticos: {agrupados_count}  |  "
            f"Únicos: {unicos_count}  |  "
            f"Falhas: {len(falhas)}"
        )
        yield sse_log("")

        # ── Fase 3: gera .txt e empacota ──────────────────────────────
        txt_path = _gerar_txt(dict(grupos), falhas, tmp_dir, nome_pasta or dest_dir.name)
        zip_name = create_zip([txt_path], dest_dir, prefix="nesting_relatorio")
        yield sse_log(f"Relatório gerado: {zip_name}")
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail("nesting-checker", str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        yield sse_done()
