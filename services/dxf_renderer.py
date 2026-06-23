"""Renderização de DXF para PDF via ezdxf.addons.drawing + matplotlib.

Uso:
    for chunk in render_to_pdf(files, paper="A4", orientation="landscape",
                                bw=False, dest_dir=...):
        yield chunk   # repassar como SSE ao Flask

Eventos SSE emitidos:
    LOG  <mensagem>           — progresso informativo
    OK   <arquivo.pdf>        — renderização bem-sucedida
    FAIL <arquivo>: <erro>    — falha individual (processamento continua)
    DOWNLOAD <uuid.zip>       — zip disponível para download
    DONE                      — fim do stream
"""

import shutil
import threading
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# Tamanhos de papel em milímetros (largura, altura) — orientação retrato
_PAPER_SIZES_MM = {
    "A4": (210, 297),
    "A3": (297, 420),
    "A2": (420, 594),
    "A1": (594, 841),
}

_MM_PER_INCH = 25.4
_RENDER_TIMEOUT_SECONDS = 120


def _paper_size_inches(paper: str, orientation: str) -> tuple[float, float]:
    """Retorna (largura, altura) em polegadas para o papel/orientação dados."""
    w_mm, h_mm = _PAPER_SIZES_MM.get(paper, _PAPER_SIZES_MM["A4"])
    if orientation == "landscape":
        w_mm, h_mm = h_mm, w_mm
    return w_mm / _MM_PER_INCH, h_mm / _MM_PER_INCH


def _render_single_file(
    path: Path,
    paper: str,
    orientation: str,
    bw: bool,
    out_dir: Path,
) -> Path:
    """Renderiza um único arquivo DXF para PDF. Levanta exceção em caso de falha.

    Executa em uma thread separada com timeout, pois a renderização pode
    travar/demorar indefinidamente em arquivos muito grandes ou complexos.
    """
    import ezdxf
    import matplotlib

    matplotlib.use("Agg")  # backend sem GUI — necessário em modo servidor
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    # Pequena margem de segurança (% da maior dimensão) para evitar que a
    # espessura das linhas/texto seja cortada exatamente na borda da folha.
    # IMPORTANTE: mesmo que o usuário queira "zero margem", uma margem de
    # segurança mínima é necessária. Quando o desenho tem geometria exatamente
    # na borda do recorte (ex.: um retângulo de moldura) E a margem é
    # matematicamente 0%, a linha cai exatamente sobre o limite de recorte do
    # PDF e pode ser invisível dependendo da precisão de arredondamento do
    # rasterizador. 0.2% é imperceptível visualmente (frações de milímetro
    # numa folha A4) mas evita esse problema de forma confiável.
    EXTENTS_PADDING_RATIO = 0.002

    result: dict = {}

    def _do_render():
        try:
            doc = ezdxf.readfile(str(path))
            msp = doc.modelspace()

            width_in, height_in = _paper_size_inches(paper, orientation)

            fig = plt.figure(figsize=(width_in, height_in))
            try:
                # Primeiro renderiza num eixo temporário cobrindo toda a
                # figura, apenas para o Frontend desenhar e podermos medir
                # o bounding box real do desenho (em coordenadas de dados).
                ax = fig.add_axes((0, 0, 1, 1))
                ax.set_axis_off()

                ctx = RenderContext(doc)

                if bw:
                    config = Configuration(
                        color_policy=ColorPolicy.BLACK,
                        background_policy=BackgroundPolicy.WHITE,
                    )
                else:
                    config = Configuration(
                        color_policy=ColorPolicy.COLOR,
                        background_policy=BackgroundPolicy.WHITE,
                    )

                backend = MatplotlibBackend(ax, adjust_figure=False)
                frontend = Frontend(ctx, backend, config=config)
                frontend.draw_layout(msp)

                # Calcula o bounding box do que foi REALMENTE desenhado e
                # reposiciona o eixo para que ocupe a folha inteira
                # (equivalente a "zoom extents" + "ajustar à folha" do
                # AutoCAD), preservando a proporção do desenho — sem
                # distorcer círculos/textos. A dimensão que melhor "encaixa"
                # na folha vai de ponta a ponta (0% de margem); a outra
                # fica centrada.
                #
                # IMPORTANTE: usamos ax.dataLim (calculado pelo matplotlib
                # durante o desenho) em vez de ezdxf.bbox.extents(msp).
                # O bbox do ezdxf considera TODAS as entidades do arquivo,
                # inclusive em camadas congeladas/desligadas (ex.: camada
                # "Defpoints" do AutoCAD, construções auxiliares ocultas —
                # comuns em arquivos DWG convertidos). Isso deixava o
                # cálculo da margem assimétrico: o centro do bbox ficava
                # deslocado por geometria invisível, enquanto o desenho
                # realmente renderizado (que respeita visibilidade de
                # camada) não. ax.dataLim reflete fielmente só o que foi
                # desenhado na tela, eliminando essa distorção.
                data_bounds = ax.dataLim
                if data_bounds.width > 0 or data_bounds.height > 0:
                    dx = data_bounds.x1 - data_bounds.x0
                    dy = data_bounds.y1 - data_bounds.y0
                    cx = (data_bounds.x1 + data_bounds.x0) / 2
                    cy = (data_bounds.y1 + data_bounds.y0) / 2

                    # Evita desenhos degenerados (uma única linha/ponto)
                    dx = dx if dx > 1e-9 else 1.0
                    dy = dy if dy > 1e-9 else 1.0

                    pad = 1.0 + EXTENTS_PADDING_RATIO
                    dx *= pad
                    dy *= pad

                    page_aspect = width_in / height_in
                    draw_aspect = dx / dy

                    if draw_aspect > page_aspect:
                        # Desenho proporcionalmente mais largo que a folha
                        # → a largura ocupa 100% da página.
                        axes_w_frac = 1.0
                        axes_h_frac = page_aspect / draw_aspect
                    else:
                        # Desenho proporcionalmente mais alto que a folha
                        # → a altura ocupa 100% da página.
                        axes_h_frac = 1.0
                        axes_w_frac = draw_aspect / page_aspect

                    left = (1.0 - axes_w_frac) / 2
                    bottom = (1.0 - axes_h_frac) / 2

                    # O backend do ezdxf provavelmente configura
                    # aspect='equal' no eixo durante draw_layout(). Como já
                    # calculamos manualmente um retângulo de eixo com a
                    # proporção exata do desenho, resetamos para 'auto'
                    # para que nosso set_position/xlim/ylim não sejam
                    # sobrescritos pelo mecanismo de aspecto do matplotlib.
                    ax.set_aspect("auto")
                    ax.set_position((left, bottom, axes_w_frac, axes_h_frac))
                    ax.set_xlim(cx - dx / 2, cx + dx / 2)
                    ax.set_ylim(cy - dy / 2, cy + dy / 2)

                out_path = out_dir / f"{path.stem}.pdf"
                fig.savefig(str(out_path), dpi=300)
                result["out_path"] = out_path
            finally:
                plt.close(fig)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_do_render, daemon=True)
    thread.start()
    thread.join(timeout=_RENDER_TIMEOUT_SECONDS)

    if thread.is_alive():
        # A renderização não terminou a tempo — não há como matar a thread
        # com segurança, mas reportamos o timeout e seguimos para o próximo
        # arquivo. A thread travada será descartada quando o processo Python
        # encerrar (é uma thread daemon).
        raise TimeoutError(f"Renderização excedeu {_RENDER_TIMEOUT_SECONDS}s")

    if "error" in result:
        raise result["error"]

    return result["out_path"]


def render_to_pdf(
    files: list[Path],
    paper: str,
    orientation: str,
    color_mode: str,
    dest_dir: str | Path,
):
    """Generator SSE que renderiza um ou mais arquivos DXF para PDF.

    Args:
        files:       Lista de caminhos para os arquivos .dxf já salvos em disco.
        paper:       Tamanho do papel — A4 | A3 | A2 | A1.
        orientation: "portrait" | "landscape".
        color_mode:  "color" | "bw".
        dest_dir:    Pasta de destino para o ZIP final.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    dest_dir = Path(dest_dir)
    bw = color_mode == "bw"

    try:
        import ezdxf  # noqa: F401
        import matplotlib  # noqa: F401
    except ImportError as exc:
        yield sse_fail("dependências", f"Biblioteca não instalada: {exc}")
        yield sse_done()
        return

    out_dir = Path(__import__("tempfile").mkdtemp(prefix="cad_pdf_out_"))

    try:
        yield sse_log(
            f"Iniciando renderização de {len(files)} arquivo(s)  —  "
            f"papel: {paper} ({orientation}), cor: {color_mode}"
        )

        ok_files: list[Path] = []

        for f in files:
            f = Path(f)
            try:
                yield sse_log(f"Renderizando {f.name}...")

                out_path = _render_single_file(f, paper, orientation, bw, out_dir)

                yield sse_ok(out_path.name)
                ok_files.append(out_path)

            except TimeoutError as exc:
                yield sse_fail(f.name, str(exc))
                continue
            except Exception as exc:
                yield sse_fail(f.name, str(exc))
                continue

        if not ok_files:
            yield sse_log("Nenhum arquivo renderizado com sucesso.")
            return

        zip_name = create_zip(ok_files, dest_dir, prefix="dxf_to_pdf")
        yield sse_log(f"ZIP gerado: {zip_name}")
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail("dxf-to-pdf", str(exc))
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        yield sse_done()
