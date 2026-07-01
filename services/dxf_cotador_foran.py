"""Cotagem automática de perfis/ninhos no padrão FORAN.

Módulo puro — sem dependência do Flask e sem geração de eventos SSE.
Toda a lógica aqui é portada de ``main.py`` (script de teste original) e
reorganizada em funções reutilizáveis pelo orquestrador
(``services/dxf_escala_cotagem.py``).

Convenções assumidas no DXF de entrada:
    - Bloco mestre (default "PartBlock") contendo os INSERTs de cada vista.
    - Cada "ninho" é um bloco próprio com uma LWPOLYLINE na layer "Parts"
      representando o contorno da peça recortada.
    - Vista superior: min_y da polilinha >= limite_y.
    - Vista inferior: min_y da polilinha <  limite_y (não é cotada).
    - Labels de identificação ficam na layer "Labels".

Idempotência:
    Rodar o fluxo duas vezes sobre o mesmo arquivo não deve duplicar cotas.
    Isso é garantido pelo orquestrador chamando ``excluir_layer_completa``
    na layer de cotas (e na layer de textos antigos) ANTES de
    ``processar_perfil_foran`` ser executado para qualquer ninho.
"""

from __future__ import annotations

import math


# =====================================================================
# UTILITÁRIOS DE DOCUMENTO
# =====================================================================

def garantir_layer(doc, nome_layer: str, cor: int = 3) -> None:
    """Cria a layer se ela ainda não existir no documento."""
    if nome_layer not in doc.layers:
        doc.layers.add(nome_layer, color=cor)


def excluir_layer_completa(doc, nome_layer: str) -> int:
    """Remove todas as entidades de ``nome_layer`` em todos os blocos e
    remove a própria layer.

    Usado para limpar o resultado de uma execução anterior antes de
    recotar — é o que garante a idempotência do fluxo. Não falha se a
    layer não existir.

    Returns:
        Quantidade de entidades removidas.
    """
    count = 0
    for block in doc.blocks:
        for entidade in block.query(f'*[layer=="{nome_layer}"]'):
            block.delete_entity(entidade)
            count += 1
    try:
        doc.layers.remove(nome_layer)
    except Exception:
        pass
    return count


def configurar_visualizacao_inicial(doc) -> None:
    """Ajusta ORTHOMODE/SNAPMODE e centraliza a viewport (zoom extents)."""
    from ezdxf import bbox

    try:
        doc.header["$ORTHOMODE"] = 1
    except Exception:
        pass
    try:
        doc.header["$SNAPMODE"] = 0
    except Exception:
        pass

    msp = doc.modelspace()
    caixa_geral = bbox.extents(msp)
    if caixa_geral.has_data:
        centro_x = (caixa_geral.extmin.x + caixa_geral.extmax.x) / 2.0
        centro_y = (caixa_geral.extmin.y + caixa_geral.extmax.y) / 2.0
        altura_tela = (caixa_geral.extmax.y - caixa_geral.extmin.y) * 1.1
        doc.set_modelspace_vport(height=altura_tela, center=(centro_x, centro_y))


def atualizar_estilo_cota_global(doc, estilo_cota: dict) -> None:
    """Aplica os overrides de ``estilo_cota`` ao dimstyle 'Standard' e às
    variáveis $DIM* do header, para o estilo de cota acompanhar a escala.
    """
    try:
        dimstyle = doc.dimstyles.get("Standard")
        for key, value in estilo_cota.items():
            if hasattr(dimstyle.dxf, key):
                setattr(dimstyle.dxf, key, value)
    except Exception:
        pass

    try:
        for key, value in estilo_cota.items():
            doc.header[f"${key.upper()}"] = value
    except Exception:
        pass


# =====================================================================
# GEOMETRIA E EXTRAÇÃO
# =====================================================================

def obter_limites(entidade):
    """Retorna (xmin, xmax, ymin, ymax) da entidade, ou None se vazio."""
    from ezdxf import bbox

    caixa = bbox.extents([entidade])
    if not caixa.has_data:
        return None
    return caixa.extmin.x, caixa.extmax.x, caixa.extmin.y, caixa.extmax.y


def extrair_arcos_unicos(polilinha, raio_minimo: float = 15.0, tolerancia: float = 2.0):
    """Percorre os segmentos virtuais da polilinha e retorna os arcos
    (furos/scallops) únicos, deduplicando scallops cortados ao meio
    (centros a menos de ``tolerancia`` um do outro).
    """
    arcos_unicos = []
    centros_processados = []
    for v_ent in polilinha.virtual_entities():
        if v_ent.dxftype() == "ARC":
            centro, raio = v_ent.dxf.center, v_ent.dxf.radius
            if raio < raio_minimo:
                continue

            ja_cadastrado = any(
                math.hypot(centro.x - c.x, centro.y - c.y) < tolerancia
                for c in centros_processados
            )
            if not ja_cadastrado:
                centros_processados.append(centro)
                arcos_unicos.append({
                    "centro": centro,
                    "raio": raio,
                    "inicio": v_ent.dxf.start_angle,
                    "fim": v_ent.dxf.end_angle,
                })
    return arcos_unicos


def cotar_horizontal(bloco, x1, x2, ref_y, base_y, estilo, layer) -> None:
    dim = bloco.add_linear_dim(
        base=((x1 + x2) / 2, base_y), p1=(x1, ref_y), p2=(x2, ref_y),
        angle=0, dimstyle="Standard", override=estilo, dxfattribs={"layer": layer},
    )
    dim.render()


def cotar_radial(bloco, centro, raio, a_inicio, a_fim, estilo, layer) -> None:
    if a_fim < a_inicio:
        a_fim += 360
    estilo_raio = estilo.copy()
    estilo_raio.update({"dimtoh": 1, "dimtix": 0, "dimtad": 1})
    dim = bloco.add_radius_dim(
        center=centro, radius=raio, angle=-(a_inicio + a_fim) / 2.0,
        dimstyle="Standard", override=estilo_raio, dxfattribs={"layer": layer},
    )
    dim.render()


# =====================================================================
# REGRAS DE NEGÓCIO (Específico Estaleiro/FORAN)
# =====================================================================

def processar_perfil_foran(
    bloco_alvo,
    polilinha,
    estilo_cota: dict,
    layer_cota: str,
    limite_y: float = 2000,
    raio_minimo: float = 15.0,
    tolerancia: float = 2.0,
    tolerancia_borda: float = 5.0,
):
    """Cota o comprimento total e os furos/scallops de uma vista superior.

    Regra: só cota a vista superior (min_y da polilinha >= limite_y).

    Returns:
        (sucesso: bool, qtd_scallops: int)
    """
    limites = obter_limites(polilinha)
    if not limites:
        return False, 0
    min_x, max_x, min_y, max_y = limites

    # REGRA: Cota apenas na vista superior
    if min_y < limite_y:
        return False, 0

    # 1. Cota Comprimento Total (500 unidades acima do topo)
    cotar_horizontal(bloco_alvo, min_x, max_x, max_y, max_y + 500, estilo_cota, layer_cota)

    # 2. Processa Scallops
    arcos = extrair_arcos_unicos(polilinha, raio_minimo=raio_minimo, tolerancia=tolerancia)

    for arco in arcos:
        centro = arco["centro"]
        dist_esq = abs(centro.x - min_x)
        dist_dir = abs(max_x - centro.x)

        # Avalia se NÃO é furo de extremidade
        if dist_esq > tolerancia_borda and dist_dir > tolerancia_borda:
            # LÓGICA DE ANCORAGEM: Ancorar a cota no lado mais próximo
            ponto_ancora = min_x if dist_esq <= dist_dir else max_x

            cotar_horizontal(
                bloco_alvo, ponto_ancora, centro.x, max_y,
                max_y + 300, estilo_cota, layer_cota,
            )

        # Cota de Raio sempre é gerada
        cotar_radial(bloco_alvo, centro, arco["raio"], arco["inicio"], arco["fim"], estilo_cota, layer_cota)

    return True, len(arcos)


def mover_vista_inferior_para_origem(
    doc, nome_bloco: str = "PartBlock", limite_y: float = 2000, deslocamento: float = -450
) -> None:
    """Desloca todos os INSERTs do bloco mestre cuja base esteja abaixo de
    ``limite_y``, alinhando a base da vista inferior em Y = ``deslocamento``.
    """
    from ezdxf import bbox

    try:
        part_block = doc.blocks.get(nome_bloco)
    except Exception:
        return

    inserts_inferiores = []
    min_y_global = float("inf")
    for entidade in part_block:
        if entidade.dxftype() == "INSERT":
            caixa = bbox.extents([entidade])
            if caixa.has_data and caixa.extmin.y < limite_y:
                inserts_inferiores.append(entidade)
                min_y_global = min(min_y_global, caixa.extmin.y)

    if not inserts_inferiores:
        return

    for insert in inserts_inferiores:
        p = insert.dxf.insert
        insert.dxf.insert = (p.x, p.y - min_y_global + deslocamento, p.z)


def duplicar_e_deslocar_labels(
    doc,
    layer_name: str = "Labels",
    offset_principal: float = -10.0,
    offset_duplicado: float = -87.533,
) -> int:
    """Desloca as labels originais e cria uma cópia deslocada (para
    acompanhar a vista duplicada).

    Returns:
        Quantidade de labels duplicadas.
    """
    msp = doc.modelspace()
    entidades = msp.query(f'*[layer=="{layer_name}"]')
    count = 0
    for ent in entidades:
        try:
            ent.translate(0, offset_principal, 0)
            nova_ent = ent.copy()
            nova_ent.translate(0, offset_duplicado, 0)
            msp.add_entity(nova_ent)
            count += 1
        except AttributeError:
            pass
    return count


def adicionar_textos_no_model_space(doc, config_labels, layer: str, altura_texto: float) -> int:
    """Insere MTEXTs fixos (ex.: "SEÇÃO\\nA-A") nas coordenadas informadas.

    Args:
        config_labels: lista de (texto, x, y).

    Returns:
        Quantidade de textos inseridos.
    """
    msp = doc.modelspace()
    count = 0
    for texto, x, y in config_labels:
        mtext = msp.add_mtext(texto, dxfattribs={"layer": layer})
        mtext.dxf.insert = (x, y)
        mtext.dxf.char_height = altura_texto
        mtext.dxf.attachment_point = 5  # Centraliza o texto no meio
        count += 1
    return count
