"""Orquestrador da Fase 6 (v0.7.0) — Escalar e Cotar (regra FORAN).

Combina a cotagem automática de perfis/ninhos (services/dxf_cotador_foran.py)
com a escala global e a explosão de blocos, produzindo um DXF final
"_cotado.dxf" por arquivo de entrada.

Uso:
    for chunk in escalar_e_cotar(files, params, dest_dir=...):
        yield chunk   # repassar como SSE ao Flask

Eventos SSE emitidos:
    LOG  <mensagem>            — progresso informativo (por etapa)
    OK   <arquivo_cotado.dxf>  — processamento bem-sucedido, com resumo
                                  "N perfis cotados / M furos referenciados"
                                  embutido no payload
    FAIL <arquivo>: <erro>     — falha individual (processamento continua)
    DOWNLOAD <uuid.zip>        — zip disponível para download
    DONE                       — fim do stream
"""

from __future__ import annotations

import shutil
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

from services.dxf_cotador_foran import (
    adicionar_textos_no_model_space,
    atualizar_estilo_cota_global,
    configurar_visualizacao_inicial,
    duplicar_e_deslocar_labels,
    excluir_layer_completa,
    garantir_layer,
    mover_vista_inferior_para_origem,
    processar_perfil_foran,
)

# Labels padrão inseridas quando o usuário não informa uma lista própria
_LABELS_PADRAO = [
    ("SEÇÃO\nA-A", 150.000, 255.222),
    ("SEÇÃO\nB-B", 150.000, 160.788),
]


# =====================================================================
# HELPER INTERNO
# =====================================================================

def _limpar_entidades_layer(doc, nome_layer: str) -> int:
    """Remove apenas as ENTIDADES de uma layer de todos os blocos, sem apagar
    a definição da layer (e portanto sem perder sua cor/linetype/etc.).

    Usar este helper em vez de excluir_layer_completa() para a layer de cotas
    garante idempotência SEM o efeito colateral de recriar a layer com cor
    padrão (7 = branco) quando o ezdxf adicionar entidades depois.

    Returns:
        Quantidade de entidades removidas.
    """
    count = 0
    for block in doc.blocks:
        for ent in list(block.query(f'*[layer=="{nome_layer}"]')):
            block.delete_entity(ent)
            count += 1
    return count


# =====================================================================
# TRANSFORMAÇÕES DE CAD (Escala e Explosão)
# =====================================================================

def escalar_modelo_completo(doc, fator_escala: float) -> int:
    """Aplica escala homogênea a todas as entidades do modelspace.

    Falhas em entidades individuais são ignoradas (continua para a
    próxima) — consistente com o comportamento de dxf_scaler.py.

    Returns:
        Quantidade de entidades escaladas com sucesso.
    """
    from ezdxf.math import Matrix44

    matriz = Matrix44.scale(fator_escala, fator_escala, fator_escala)
    count = 0
    for entidade in doc.modelspace():
        try:
            entidade.transform(matriz)
            count += 1
        except Exception:
            pass
    return count


def explodir_todos_os_blocos(doc) -> int:
    """Explode recursivamente todos os INSERTs do modelspace (suporta
    blocos aninhados — "matrioskas").

    Returns:
        Total de blocos explodidos.
    """
    msp = doc.modelspace()
    total_exploded = 0

    while True:
        inserts = msp.query("INSERT")
        if len(inserts) == 0:
            break

        count_this_pass = 0
        for block_ref in inserts:
            try:
                block_ref.explode()
                count_this_pass += 1
            except Exception:
                pass

        if count_this_pass == 0:
            break

        total_exploded += count_this_pass

    return total_exploded


# =====================================================================
# PROCESSAMENTO DE UM ARQUIVO
# =====================================================================

def _escalar_e_cotar_single_file(path: Path, params: dict, out_dir: Path, log):
    """Processa um único DXF. Levanta exceção em caso de falha total.

    ``log`` é uma função callback(str) usada para emitir mensagens LOG
    intermediárias enquanto o arquivo é processado.

    Returns:
        (out_path, t_perfis, t_scallops)
    """
    import ezdxf
    from ezdxf import bbox as _bx

    escala              = params["escala"]
    layer_cota          = params["layer_cota"]
    layer_textos_antigos = params["layer_textos_antigos"]
    nome_bloco          = params["nome_bloco"]
    limite_y            = params["limite_y"]
    raio_minimo         = params["raio_minimo"]
    tolerancia          = params["tolerancia"]
    tolerancia_borda    = params["tolerancia_borda"]
    explodir_blocos     = params["explodir_blocos"]
    labels              = params["labels"]
    debug_blocos        = params.get("debug_blocos", False)

    doc = ezdxf.readfile(str(path))

    # ── FIX: cor da layer de cotas ─────────────────────────────────────────
    # NAO usar excluir_layer_completa() para a layer de cotas.
    #
    # excluir_layer_completa() chama doc.layers.remove() → apaga a DEFINIÇÃO
    # da layer. Quando o ezdxf adiciona entidades de cota em seguida, recria
    # a layer com cor padrão (7 = branco). A cor=3 (verde) era perdida.
    #
    # Solução: _limpar_entidades_layer() remove só as entidades (idempotência)
    # SEM apagar a definição. Depois garantir_layer() cria a layer se ela
    # ainda não existe OU força cor=3 se já existe.
    _limpar_entidades_layer(doc, layer_cota)
    garantir_layer(doc, layer_cota, cor=3)

    # "Free Texts" pode ser excluída completamente (idêntico ao main.py)
    if layer_textos_antigos:
        excluir_layer_completa(doc, layer_textos_antigos)

    # Estilo de cota — idêntico ao main.py
    # (dimtxt × 2.5, dimasz × 1.5, dimexe × 1.0, dimexo × 0.25, dimdec = 0)
    estilo_cota_global = {
        "dimtxt": 2.5 * escala,
        "dimasz": 1.5 * escala,
        "dimexe": 1.0 * escala,
        "dimexo": 0.25 * escala,
        "dimdec": 0,
    }
    atualizar_estilo_cota_global(doc, estilo_cota_global)

    # 1. Localiza o bloco mestre
    try:
        part_block = doc.blocks.get(nome_bloco)
    except Exception:
        raise ValueError(f"bloco mestre '{nome_bloco}' não encontrado")

    # 2. Cota cada ninho (bloco != mestre) cuja LWPOLYLINE esteja na layer "Parts"
    t_perfis, t_scallops = 0, 0
    log(f"Cotando perfis/scallops de {path.name}...")
    for bloco in list(doc.blocks):
        if bloco.name.startswith("*") or bloco.name == nome_bloco:
            continue

        for poly in bloco.query('LWPOLYLINE[layer=="Parts"]'):
            sucesso, qtd = processar_perfil_foran(
                part_block, poly, estilo_cota_global, layer_cota,
                limite_y=limite_y, raio_minimo=raio_minimo,
                tolerancia=tolerancia, tolerancia_borda=tolerancia_borda,
            )
            if sucesso:
                t_perfis += 1
                t_scallops += qtd

    # 3. Ajusta a vista inferior
    mover_vista_inferior_para_origem(doc, nome_bloco=nome_bloco, limite_y=limite_y)

    # 4. Duplica/desloca labels (idêntico ao main.py)
    duplicar_e_deslocar_labels(doc)

    # 5. Adiciona os textos fixos
    if labels:
        log("Inserindo textos fixos...")
        adicionar_textos_no_model_space(
            doc, labels, layer_textos_antigos or "Free Texts", 4.0
        )

    # 6. Escala o desenho inteiro
    log(f"Aplicando escala global de {escala:.4f}x...")
    escalar_modelo_completo(doc, escala)

    # 7. Explode blocos (opcional)
    if explodir_blocos:
        log("Explodindo blocos...")
        explodir_todos_os_blocos(doc)

    # 8. Centraliza a câmera
    configurar_visualizacao_inicial(doc)

    out_path = out_dir / f"{path.stem}_cotado.dxf"
    doc.saveas(str(out_path))

    return out_path, t_perfis, t_scallops


# =====================================================================
# GENERATOR SSE
# =====================================================================

def escalar_e_cotar(files: list, params: dict, dest_dir):
    """Generator SSE — cota, escala e (opcionalmente) explode um lote de
    arquivos DXF no padrão FORAN.

    Args:
        files: lista de caminhos para os arquivos .dxf já salvos em disco.
        params: dict com as chaves
            escala (float, obrigatório, >0)
            layer_cota (default "Dimensions")
            layer_textos_antigos (default "Free Texts")
            nome_bloco (default "PartBlock")
            limite_y (default 2000)
            raio_minimo (default 15.0)
            tolerancia (default 2.0)
            tolerancia_borda (default 5.0)
            explodir_blocos (bool, default True)
            labels (lista de {texto, x, y}; default replica SEÇÃO A-A / B-B)
        dest_dir: pasta de destino para o ZIP final.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    dest_dir = Path(dest_dir)

    escala = params.get("escala")
    if escala is None or escala <= 0:
        yield sse_fail("validação", "Escala deve ser maior que zero.")
        yield sse_done()
        return

    try:
        import ezdxf  # noqa: F401
    except ImportError:
        yield sse_fail("ezdxf", "Biblioteca não instalada. Execute: pip install ezdxf")
        yield sse_done()
        return

    norm_params = {
        "escala":               float(escala),
        "layer_cota":           params.get("layer_cota") or "Dimensions",
        "layer_textos_antigos": params.get("layer_textos_antigos", "Free Texts"),
        "nome_bloco":           params.get("nome_bloco") or "PartBlock",
        "limite_y":             float(params.get("limite_y", 2000)),
        "raio_minimo":          float(params.get("raio_minimo", 15.0)),
        "tolerancia":           float(params.get("tolerancia", 2.0)),
        "tolerancia_borda":     float(params.get("tolerancia_borda", 5.0)),
        "explodir_blocos":      bool(params.get("explodir_blocos", True)),
        "labels":               params.get("labels") or _LABELS_PADRAO,
    }

    out_dir = Path(__import__("tempfile").mkdtemp(prefix="cad_cotagem_out_"))

    try:
        yield sse_log(
            f"Iniciando cotagem + escala de {len(files)} arquivo(s)  —  "
            f"escala: {norm_params['escala']}, bloco mestre: {norm_params['nome_bloco']}"
        )

        ok_files: list[Path] = []

        for f in files:
            f = Path(f)
            try:
                yield sse_log(f"Processando {f.name}...")

                # Mensagens LOG intermediárias coletadas durante o
                # processamento são acumuladas e emitidas em sequência —
                # o generator não pode ser "yield"ado de dentro de uma
                # função auxiliar comum, então usamos uma lista como buffer.
                pending_logs: list[str] = []
                out_path, t_perfis, t_scallops = _escalar_e_cotar_single_file(
                    f, norm_params, out_dir, log=pending_logs.append
                )
                for msg in pending_logs:
                    yield sse_log(msg)

                resumo = f"{t_perfis} perfis cotados / {t_scallops} furos referenciados"
                yield sse_ok(f"{out_path.name}: {resumo}")
                ok_files.append(out_path)

            except Exception as exc:
                yield sse_fail(f.name, str(exc))
                continue

        if not ok_files:
            yield sse_log("Nenhum arquivo processado com sucesso.")
            return

        zip_name = create_zip(ok_files, dest_dir, prefix="dxf_cotado")
        yield sse_log(f"ZIP gerado: {zip_name}")
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail("dxf-escala-cotagem", str(exc))
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        yield sse_done()
