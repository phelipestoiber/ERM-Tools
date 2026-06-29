"""Wrapper para o ODA File Converter (ODAFileConverter.exe).

Uso:
    for chunk in run_oda(in_dir, out_dir, oda_path=..., version="ACAD2013", audit=0):
        yield chunk   # repassar como SSE ao Flask

Eventos SSE emitidos:
    LOG  <mensagem>           — progresso informativo
    OK   <arquivo.dxf>        — conversão bem-sucedida
    FAIL <arquivo>: <erro>    — falha individual (processamento continua)
    DOWNLOAD <uuid.zip>       — zip disponível para download
    DONE                      — fim do stream
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip


def run_oda(
    dwg_files: list[Path],
    dest_dir: str | Path,
    oda_path: str,
    version: str = "ACAD2013",
    audit: int = 0,
):
    """Generator SSE que converte DWG → DXF via ODAFileConverter.exe.

    Args:
        dwg_files: Lista de caminhos para os arquivos .dwg já salvos em disco.
        dest_dir:  Pasta de destino para o ZIP final.
        oda_path:  Caminho completo do ODAFileConverter.exe.
        version:   Versão DXF de saída (ex.: ACAD2013, ACAD2010).
        audit:     0 ou 1 — passa o parâmetro de auditoria ao ODA.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    dest_dir = Path(dest_dir)

    # Valida ODA
    if not oda_path or not os.path.isfile(oda_path):
        yield sse_fail("ODA", "ODAFileConverter.exe não encontrado. Informe o caminho correto.")
        yield sse_done()
        return

    in_dir  = Path(tempfile.mkdtemp(prefix="cad_in_"))
    out_dir = Path(tempfile.mkdtemp(prefix="cad_out_"))

    try:
        # Copia DWGs para a pasta de entrada temporária
        for dwg in dwg_files:
            shutil.copy2(dwg, in_dir / Path(dwg).name)

        yield sse_log(f"Iniciando conversão de {len(dwg_files)} arquivo(s) com ODA...")
        yield sse_log(f"Versão DXF de saída: {version}  |  Auditoria: {audit}")

        # Executa o ODA
        cmd = [
            oda_path,
            str(in_dir),
            str(out_dir),
            version,
            "DXF",
            "0",           # recurse (0 = não recursivo)
            str(audit),
        ]
        yield sse_log(f"Executando: {os.path.basename(oda_path)}")

        result = subprocess.run(
            cmd,
            timeout=300,
            capture_output=True,
            text=True,
        )

        # Coleta arquivos gerados
        generated = list(out_dir.glob("*.dxf"))

        if result.returncode != 0 and not generated:
            stderr = (result.stderr or "").strip()
            yield sse_fail("ODA", stderr or f"código de saída {result.returncode}")
            yield sse_done()
            return

        # Associa DWG de entrada → DXF gerado (pelo nome base)
        input_stems = {Path(f).stem.lower(): Path(f).name for f in dwg_files}

        ok_files: list[Path] = []
        for dxf in generated:
            yield sse_ok(dxf.name)
            ok_files.append(dxf)

        # Reporta entradas sem correspondência como FAIL
        generated_stems = {f.stem.lower() for f in generated}
        for stem, dwg_name in input_stems.items():
            if stem not in generated_stems:
                yield sse_fail(dwg_name, "conversão não produziu arquivo de saída")

        if not ok_files:
            yield sse_log("Nenhum arquivo convertido com sucesso.")
            yield sse_done()
            return

        # Empacota e move ZIP para destino
        zip_name = create_zip(ok_files, dest_dir, prefix="dwg_to_dxf")
        yield sse_log(f"ZIP gerado: {zip_name}")
        yield sse_download(zip_name)

    except subprocess.TimeoutExpired:
        yield sse_fail("ODA", "Timeout de 300 s excedido.")
    except Exception as exc:
        yield sse_fail("ODA", str(exc))
    finally:
        shutil.rmtree(in_dir,  ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        yield sse_done()

def convert_dwg_to_dxf_internal(dwg_files: list[Path], dest_dir: Path, oda_path: str, version: str = "ACAD2013", audit: int = 0) -> dict:
    """Converte DWG para DXF silenciosamente. Usado internamente pelo pipeline de PDF."""
    import subprocess
    import shutil
    import tempfile

    in_dir = Path(tempfile.mkdtemp(prefix="cad_pipe_in_"))
    result = {"ok": [], "fail": []}

    try:
        # Copia os arquivos para o diretório de entrada do ODA
        for dwg in dwg_files:
            shutil.copy2(dwg, in_dir / Path(dwg).name)

        cmd = [
            oda_path,
            str(in_dir),
            str(dest_dir),
            version,
            "DXF",
            "0",
            str(audit),
        ]
        
        proc = subprocess.run(cmd, timeout=300, capture_output=True, text=True)

        generated = list(dest_dir.glob("*.dxf"))
        generated_stems = {f.stem.lower(): f for f in generated}

        # Verifica arquivo por arquivo se o DXF correspondente foi criado
        for dwg in dwg_files:
            stem = Path(dwg).stem.lower()
            if stem in generated_stems:
                result["ok"].append(generated_stems[stem])
            else:
                err = (proc.stderr or "").strip() or f"Código de saída {proc.returncode}"
                result["fail"].append((Path(dwg).name, err))

    except Exception as exc:
        for dwg in dwg_files:
            result["fail"].append((Path(dwg).name, str(exc)))
    finally:
        shutil.rmtree(in_dir, ignore_errors=True)

    return result
