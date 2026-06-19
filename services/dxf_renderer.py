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

    result: dict = {}

    def _do_render():
        try:
            doc = ezdxf.readfile(str(path))
            msp = doc.modelspace()

            width_in, height_in = _paper_size_inches(paper, orientation)

            fig = plt.figure(figsize=(width_in, height_in))
            try:
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

                backend = MatplotlibBackend(ax)
                frontend = Frontend(ctx, backend, config=config)
                frontend.draw_layout(msp)

                out_path = out_dir / f"{path.stem}.pdf"
                fig.savefig(str(out_path), dpi=300, bbox_inches="tight")
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
