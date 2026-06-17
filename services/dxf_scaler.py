"""Escalonamento de entidades DXF via ezdxf.

Uso:
    for chunk in scale_dxf(path, factor=2.0, suffix="_scaled", out_dir=...):
        yield chunk   # repassar como SSE ao Flask

Eventos SSE emitidos:
    LOG  <mensagem>             — progresso informativo
    OK   <arquivo_scaled.dxf>   — escalonamento bem-sucedido
    FAIL <arquivo>: <erro>      — falha individual (processamento continua)
    DOWNLOAD <uuid.zip>         — zip disponível para download
    DONE                        — fim do stream

Lógica de dimstyles:
    Multiplicar pelo fator (atributos visuais — tamanho do texto/setas):
        dimtxt, dimasz, dimtsz, dimcen, dimexe, dimexo
    Dividir pelo fator (mantém o valor numérico exibido na cota):
        dimlfac
"""

import shutil
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# Atributos de dimstyle multiplicados pelo fator de escala
_DIMSTYLE_SCALE_UP = ["dimtxt", "dimasz", "dimtsz", "dimcen", "dimexe", "dimexo"]
# Atributos de dimstyle divididos pelo fator (preserva a medida exibida)
_DIMSTYLE_SCALE_DOWN = ["dimlfac"]


def _scale_dimstyles(doc, factor: float) -> int:
    """Ajusta todos os dimstyles do documento. Retorna a quantidade ajustada."""
    count = 0
    for dimstyle in doc.dimstyles:
        try:
            for attr in _DIMSTYLE_SCALE_UP:
                current = dimstyle.dxf.get(attr, None)
                if current is not None:
                    dimstyle.dxf.set(attr, current * factor)

            for attr in _DIMSTYLE_SCALE_DOWN:
                current = dimstyle.dxf.get(attr, None)
                # dimlfac=0 é tratado como 1 pelo AutoCAD; evita divisão por zero
                base = current if current else 1.0
                dimstyle.dxf.set(attr, base / factor)

            count += 1
        except Exception:
            # Dimstyle individual com problema não deve interromper o processo
            continue
    return count


def _scale_single_file(
    path: Path,
    factor: float,
    suffix: str,
    out_dir: Path,
):
    """Escala um único arquivo DXF. Levanta exceção em caso de falha total."""
    import ezdxf
    from ezdxf.math import Matrix44

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    # IMPORTANTE: ajustar os dimstyles ANTES de transformar/renderizar as
    # entidades. O DIMENSION.render() usa o dimlfac vigente no momento da
    # chamada — se os dimstyles forem ajustados depois, a cota já terá
    # sido renderizada com o valor antigo e o texto exibido ficará errado.
    n_dimstyles = _scale_dimstyles(doc, factor)

    matrix = Matrix44.scale(factor, factor, factor)

    n_entities = 0
    n_warn = 0

    for entity in msp:
        try:
            entity.transform(matrix)

            # DIMENSION precisa recalcular sua geometria após a transformação
            if entity.dxftype() == "DIMENSION":
                entity.render()

            n_entities += 1
        except Exception:
            n_warn += 1
            continue

    out_name = f"{path.stem}{suffix}.dxf"
    out_path = out_dir / out_name
    doc.saveas(str(out_path))

    return out_path, n_entities, n_warn, n_dimstyles


def scale_dxf(
    files: list[Path],
    factor: float,
    suffix: str,
    dest_dir: str | Path,
):
    """Generator SSE que escala um ou mais arquivos DXF.

    Args:
        files:    Lista de caminhos para os arquivos .dxf já salvos em disco.
        factor:   Fator de escala (deve ser > 0).
        suffix:   Sufixo adicionado ao nome do arquivo de saída.
        dest_dir: Pasta de destino para o ZIP final.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    dest_dir = Path(dest_dir)

    # Validação do fator
    if factor is None or factor <= 0:
        yield sse_fail("validação", "Fator de escala deve ser maior que zero.")
        yield sse_done()
        return

    try:
        import ezdxf  # noqa: F401
    except ImportError:
        yield sse_fail("ezdxf", "Biblioteca não instalada. Execute: pip install ezdxf")
        yield sse_done()
        return

    out_dir = Path(__import__("tempfile").mkdtemp(prefix="cad_scale_out_"))

    try:
        yield sse_log(f"Iniciando escalonamento de {len(files)} arquivo(s)  —  fator: {factor}")

        ok_files: list[Path] = []

        for f in files:
            f = Path(f)
            try:
                yield sse_log(f"Processando {f.name}...")

                out_path, n_entities, n_warn, n_dimstyles = _scale_single_file(
                    f, factor, suffix, out_dir
                )

                detail = f"{n_entities} entidade(s) escalada(s)"
                if n_dimstyles:
                    detail += f", {n_dimstyles} dimstyle(s) ajustado(s)"
                if n_warn:
                    detail += f", {n_warn} ignorada(s) com erro"

                yield sse_log(detail)
                yield sse_ok(out_path.name)
                ok_files.append(out_path)

            except Exception as exc:
                yield sse_fail(f.name, str(exc))
                continue

        if not ok_files:
            yield sse_log("Nenhum arquivo escalado com sucesso.")
            return

        zip_name = create_zip(ok_files, dest_dir, prefix="dxf_scaled")
        yield sse_log(f"ZIP gerado: {zip_name}")
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail("dxf-scale", str(exc))
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        yield sse_done()
