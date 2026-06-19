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

Lógica de dimstyles e texto de cotas:
    O objetivo é que, após escalonar o desenho, a cota mostre a distância
    REAL e correta na nova escala (ex.: 25 → 250 ao escalar por 10).

    - dimtxt, dimasz, dimtsz, dimcen, dimexe, dimexo:
        Multiplicados pelo fator — mantêm o tamanho visual (texto, setas)
        proporcional ao novo desenho.
    - dimlfac:
        NÃO é alterado. Ao deixar dimlfac inalterado, a medida exibida
        para cotas automáticas (sem texto sobrescrito) é recalculada a
        partir da nova geometria e reflete corretamente o valor real.
    - Texto sobrescrito manualmente (dim.dxf.text):
        Cotas com texto digitado manualmente (sem o placeholder "<>") não
        são recalculadas pelo ezdxf, pois o texto é uma string fixa. Para
        esses casos, se o conteúdo for puramente numérico, multiplicamos
        o valor pelo fator e atualizamos o texto. Caso contrário (texto
        com prefixo/sufixo não numérico), o valor é mantido e um aviso é
        registrado no log para revisão manual.
"""

import re
import shutil
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# Atributos de dimstyle multiplicados pelo fator de escala (tamanho visual)
_DIMSTYLE_SCALE_UP = ["dimtxt", "dimasz", "dimtsz", "dimcen", "dimexe", "dimexo"]

# Reconhece um texto de cota puramente numérico, ex.: "25", "25.4", "25,4"
_NUM_RE = re.compile(r"^[-+]?\d+([.,]\d+)?$")


def _scale_dimstyles(doc, factor: float) -> int:
    """Ajusta o tamanho visual (texto/setas) de todos os dimstyles.

    dimlfac é deliberadamente NÃO alterado — veja docstring do módulo.
    """
    count = 0
    for dimstyle in doc.dimstyles:
        try:
            for attr in _DIMSTYLE_SCALE_UP:
                current = dimstyle.dxf.get(attr, None)
                if current is not None:
                    dimstyle.dxf.set(attr, current * factor)
            count += 1
        except Exception:
            # Dimstyle individual com problema não deve interromper o processo
            continue
    return count


def _scale_override_text(text: str, factor: float) -> tuple[str, bool]:
    """Tenta multiplicar pelo fator o valor numérico de um texto de cota
    sobrescrito manualmente.

    Returns:
        (novo_texto, alterado) — alterado=False se o texto não pôde ser
        interpretado como um número puro (nesse caso o texto original é
        retornado sem modificação).
    """
    if not text or "<>" in text:
        # Vazio ou com placeholder automático — ezdxf recalcula sozinho.
        return text, False

    stripped = text.strip()
    if not _NUM_RE.match(stripped):
        return text, False

    has_comma = "," in stripped
    normalized = stripped.replace(",", ".")

    try:
        value = float(normalized)
    except ValueError:
        return text, False

    new_value = value * factor

    if "." in normalized:
        decimals = len(normalized.split(".")[-1])
        new_text = f"{new_value:.{decimals}f}"
    else:
        new_text = f"{round(new_value):g}"

    if has_comma:
        new_text = new_text.replace(".", ",")

    return new_text, True


def _scale_single_file(
    path: Path,
    factor: float,
    suffix: str,
    out_dir: Path,
):
    """Escala um único arquivo DXF. Levanta exceção em caso de falha total.

    Returns:
        (out_path, n_entities, n_warn, n_dimstyles, n_overrides,
         n_fixed_mtext, n_local_overrides, fail_details)
    """
    import ezdxf
    from ezdxf.math import Matrix44, Vec3

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    n_dimstyles = _scale_dimstyles(doc, factor)

    matrix = Matrix44.scale(factor, factor, factor)

    n_entities = 0
    n_warn = 0
    n_overrides = 0
    n_fixed_mtext = 0
    n_local_overrides = 0
    fail_details: list[str] = []

    # Cotas processadas com sucesso na 1ª passagem, para o ajuste de altura
    # isolado na 2ª passagem (ver comentário abaixo).
    dimensions_to_resize: list = []

    # ── PASSAGEM 1 ──────────────────────────────────────────────────────
    # Transforma a geometria de todas as entidades e recalcula o valor/texto
    # exibido nas cotas (medida real + texto sobrescrito numérico). Esta
    # passagem é isolada de qualquer ajuste de altura visual (dimtxt) para
    # garantir que o cálculo do VALOR da cota nunca seja influenciado pela
    # manipulação do override de DIMSTYLE da entidade.
    for entity in msp:
        dxftype = entity.dxftype()
        try:
            if dxftype == "MTEXT":
                # Alguns conversores de terceiros (ex.: ODA File Converter)
                # gravam text_direction=(0,0,0), um vetor degenerado que faz
                # o transform() do ezdxf calcular 0/0 internamente e travar
                # com ZeroDivisionError. Descartamos o atributo para que o
                # ezdxf recalcule text_direction corretamente a partir de
                # 'rotation' antes de transformar a entidade.
                if entity.dxf.hasattr("text_direction"):
                    direction = Vec3(entity.dxf.text_direction)
                    if direction.magnitude < 1e-9:
                        entity.dxf.discard("text_direction")
                        n_fixed_mtext += 1

            entity.transform(matrix)

            if dxftype == "DIMENSION":
                dimensions_to_resize.append(entity)
                current_text = entity.dxf.get("text", "")
                new_text, changed = _scale_override_text(current_text, factor)
                if changed:
                    entity.dxf.text = new_text
                    n_overrides += 1
                elif current_text and "<>" not in current_text:
                    # Texto manual não numérico — não foi possível atualizar
                    fail_details.append(
                        f"DIMENSION (handle={entity.dxf.handle}): "
                        f"texto sobrescrito \"{current_text}\" não é numérico puro — não atualizado"
                    )

                # Remove o override de dimlfac que o ezdxf injeta no transform()
                ov = entity.override()
                if "dimlfac" in ov.dimstyle_attribs:
                    del ov.dimstyle_attribs["dimlfac"]
                    ov.commit()

                # Recalcula a geometria/texto renderizado da cota
                entity.render()

            n_entities += 1
        except Exception as exc:
            n_warn += 1
            fail_details.append(f"{dxftype} (handle={entity.dxf.handle}): {exc}")
            continue

    # ── PASSAGEM 2 ──────────────────────────────────────────────────────
    # Com o valor/texto das cotas já corretamente calculado e estável (1ª
    # passagem), ajustamos agora SOMENTE o tamanho visual (dimtxt, dimasz,
    # etc.) de cotas com override próprio na XDATA, e renderizamos de novo.
    # Como os pontos de definição (defpoints) não são tocados aqui, o valor
    # numérico exibido permanece exatamente o já calculado na passagem 1 —
    # apenas o tamanho do texto/setas muda.
    for entity in dimensions_to_resize:
        try:
            ov = entity.override()
            local_changed = False
            for attr in _DIMSTYLE_SCALE_UP:
                if attr in ov.dimstyle_attribs:
                    ov.dimstyle_attribs[attr] = ov.dimstyle_attribs[attr] * factor
                    local_changed = True
            if local_changed:
                ov.commit()
                n_local_overrides += 1
                entity.render()
        except Exception as exc:
            fail_details.append(
                f"DIMENSION (handle={entity.dxf.handle}): "
                f"falha ao ajustar altura do override — {exc}"
            )

    out_name = f"{path.stem}{suffix}.dxf"
    out_path = out_dir / out_name
    doc.saveas(str(out_path))

    return (out_path, n_entities, n_warn, n_dimstyles, n_overrides,
            n_fixed_mtext, n_local_overrides, fail_details)


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

                (out_path, n_entities, n_warn, n_dimstyles, n_overrides,
                 n_fixed_mtext, n_local_overrides, fail_details) = _scale_single_file(
                    f, factor, suffix, out_dir
                )

                detail = f"{n_entities} entidade(s) escalada(s)"
                if n_dimstyles:
                    detail += f", {n_dimstyles} dimstyle(s) ajustado(s)"
                if n_local_overrides:
                    detail += f", {n_local_overrides} override(s) de cota ajustado(s)"
                if n_overrides:
                    detail += f", {n_overrides} texto(s) de cota atualizado(s)"
                if n_fixed_mtext:
                    detail += f", {n_fixed_mtext} MTEXT corrigido(s) (direção degenerada)"
                if n_warn:
                    detail += f", {n_warn} entidade(s) com erro"

                yield sse_log(detail)

                # Mostra detalhe de cada falha para diagnóstico (limitado a 15 linhas)
                for line in fail_details[:15]:
                    yield sse_log(f"  ⚠ {line}")
                if len(fail_details) > 15:
                    yield sse_log(f"  ⚠ ... e mais {len(fail_details) - 15} ocorrência(s)")

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
