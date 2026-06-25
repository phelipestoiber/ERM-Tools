"""Editor/Organizador de PDF — mescla páginas de múltiplos PDFs via pypdf.

Fluxo em duas etapas:
    1. stage_files()  — salva os PDFs enviados na pasta de staging e lê os
                         metadados (nome, nº de páginas, tamanho) de cada um,
                         retornando um file_id por arquivo.
    2. merge_pdfs()   — recebe a sequência final de páginas (file_id +
                         page_index, na ordem desejada), monta o PDF
                         mesclado e limpa os arquivos de staging usados.

Isso evita reenviar os bytes do PDF duas vezes: o upload ocorre uma única
vez (etapa 1); a reordenação de páginas no frontend referencia apenas os
file_ids já salvos no servidor.
"""

import time
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

# Arquivos de staging mais antigos que isso são considerados abandonados
# (ex.: o usuário selecionou arquivos mas nunca completou o merge) e podem
# ser removidos na próxima limpeza.
_STAGING_MAX_AGE_SECONDS = 2 * 60 * 60  # 2 horas


def cleanup_stale_staging(staging_dir: str | Path) -> int:
    """Remove arquivos de staging abandonados há mais de 2h.

    Returns:
        Quantidade de arquivos removidos.
    """
    staging_dir = Path(staging_dir)
    if not staging_dir.is_dir():
        return 0

    now = time.time()
    removed = 0
    for f in staging_dir.glob("*.pdf"):
        try:
            if now - f.stat().st_mtime > _STAGING_MAX_AGE_SECONDS:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def stage_files(files: list, staging_dir: str | Path) -> dict:
    """Salva os PDFs enviados na pasta de staging e lê seus metadados.

    Args:
        files: lista de objetos de upload do Flask (werkzeug FileStorage).
        staging_dir: pasta onde os arquivos ficam até o merge.

    Returns:
        {"files": [{"file_id", "filename", "n_pages", "size_bytes"}, ...],
         "errors": [{"filename", "error"}, ...]}
    """
    staging_dir = Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    cleanup_stale_staging(staging_dir)

    result_files = []
    errors = []

    for f in files:
        if not f.filename:
            continue

        file_id = uuid4().hex[:12]
        dest = staging_dir / f"{file_id}.pdf"

        try:
            f.save(dest)
            reader = PdfReader(str(dest))
            n_pages = len(reader.pages)
            size_bytes = dest.stat().st_size

            result_files.append({
                "file_id": file_id,
                "filename": f.filename,
                "n_pages": n_pages,
                "size_bytes": size_bytes,
            })
        except (PdfReadError, Exception) as exc:
            dest.unlink(missing_ok=True)
            errors.append({"filename": f.filename, "error": str(exc)})

    return {"files": result_files, "errors": errors}


def merge_pdfs(
    sequence: list[dict],
    staging_dir: str | Path,
    out_dir: str | Path,
) -> dict:
    """Monta o PDF mesclado a partir da sequência de páginas fornecida.

    Args:
        sequence: lista de {"file_id": str, "page_index": int}, na ordem
            final desejada.
        staging_dir: pasta onde os PDFs de origem foram salvos (stage_files).
        out_dir: pasta de destino para o PDF mesclado.

    Returns:
        {"pdf": nome_do_arquivo, "n_pages": int, "size_bytes": int}

    Raises:
        ValueError: se algum file_id/page_index for inválido ou a sequência
            estiver vazia.
    """
    staging_dir = Path(staging_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not sequence:
        raise ValueError("Sequência de páginas vazia.")

    # Cache de leitores para não reabrir o mesmo PDF várias vezes
    readers: dict[str, PdfReader] = {}
    used_file_ids: set[str] = set()

    writer = PdfWriter()

    for i, item in enumerate(sequence):
        file_id = item.get("file_id")
        page_index = item.get("page_index")

        if not file_id or not isinstance(page_index, int):
            raise ValueError(f"Item {i} da sequência é inválido: {item}")

        if file_id not in readers:
            src_path = staging_dir / f"{file_id}.pdf"
            if not src_path.is_file():
                raise ValueError(f"Arquivo de origem não encontrado para file_id={file_id}")
            readers[file_id] = PdfReader(str(src_path))

        reader = readers[file_id]
        if not (0 <= page_index < len(reader.pages)):
            raise ValueError(
                f"page_index={page_index} fora do intervalo para file_id={file_id} "
                f"(arquivo tem {len(reader.pages)} página(s))"
            )

        writer.add_page(reader.pages[page_index])
        used_file_ids.add(file_id)

    out_name = f"PDF_Mesclado_{uuid4().hex[:6]}.pdf"
    out_path = out_dir / out_name

    with open(out_path, "wb") as fh:
        writer.write(fh)

    n_pages = len(writer.pages)
    size_bytes = out_path.stat().st_size

    # Limpa os arquivos de staging usados neste merge
    for file_id in used_file_ids:
        (staging_dir / f"{file_id}.pdf").unlink(missing_ok=True)

    return {"pdf": out_name, "n_pages": n_pages, "size_bytes": size_bytes}
