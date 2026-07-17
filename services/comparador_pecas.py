"""Comparador de Peças — dois modos de análise via planilha Excel.

Modo A — Famílias Duplicadas (porta main.py):
    Identifica peças de famílias DIFERENTES que possuem peso e área
    geometricamente idênticos dentro de uma tolerância. Útil para detectar
    peças cadastradas na família errada.

    Colunas obrigatórias: Single Part Code, Unit. Weight, Area/Length, Block
    Saída: TXT + CSV → ZIP

Modo B — Cópias Divergentes (porta main2.py):
    Detecta cópias (_C01, _C02 …) que divergem do original ou que se
    dividem em mais de um perfil distinto dentro da mesma família.

    Colunas obrigatórias: Single Part Code, Unit. Weight, Area/Length
    Saída: TXT → ZIP

Eventos SSE emitidos (ambos os modos):
    LOG  <mensagem>           — progresso informativo
    OK   <resultado>          — ocorrência relevante encontrada
    FAIL <arquivo>: <erro>    — falha (interrompe — é 1 arquivo só)
    DOWNLOAD <uuid.zip>       — ZIP com relatório disponível
    DONE                      — fim do stream
"""

from __future__ import annotations

import csv
import re
import shutil
import tempfile
import time
from pathlib import Path

from utils.sse import sse_done, sse_download, sse_fail, sse_log, sse_ok
from utils.zip_utils import create_zip

# ── Sufixo FORAN que identifica cópias/simétricas (*X, *C1, *C2 …) ──────────
_PADRAO_FORAN = re.compile(r'\*.+$')

# ── Sufixo de cópia oficial (_C01, _C02 …) ───────────────────────────────────
_PADRAO_COPIA = re.compile(r'_C(\d+)$')


# =====================================================================
# HELPERS COMPARTILHADOS
# =====================================================================

def _parse_number(val) -> float:
    """Converte string com vírgula decimal para float."""
    if isinstance(val, str):
        return float(val.replace(',', '.'))
    return float(val)


def _extrair_familia(nome: str) -> str:
    """Remove sufixo _C## do nome, retornando a família base."""
    return _PADRAO_COPIA.sub('', nome)


def _validar_colunas(df, obrigatorias: list[str], nome_arquivo: str) -> None:
    """Levanta ValueError se alguma coluna obrigatória estiver ausente."""
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Coluna(s) ausente(s) em '{nome_arquivo}': {', '.join(faltando)}"
        )


def _union_find_init(n: int):
    """Retorna (find, union, parent) para um Union-Find de tamanho n."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    return find, union, parent


# =====================================================================
# MODO A — FAMÍLIAS DUPLICADAS
# =====================================================================

def _processar_familias_duplicadas(df, tol_peso: float, tol_area: float) -> list[dict]:
    """Aplica Union-Find cross-família e retorna lista de grupos suspeitos."""
    # Filtra sufixos FORAN antes de qualquer processamento
    df = df[~df['Single Part Code'].astype(str).str.contains(
        _PADRAO_FORAN.pattern, regex=True, na=False
    )].copy()

    # Extrai (familia, peso, area, bloco)
    pecas_brutas = []
    for _, row in df.iterrows():
        try:
            nome_full = str(row['Single Part Code']).strip()
            peso = _parse_number(row['Unit. Weight'])
            area = _parse_number(row['Area/Length'])
            bloco = str(row.get('Block', '') or '').strip()
        except (ValueError, TypeError):
            continue
        familia = _extrair_familia(nome_full)
        pecas_brutas.append((familia, peso, area, bloco))

    # Dedup: uma entrada por (familia + geometria), acumulando blocos
    representantes: dict = {}
    for familia, peso, area, bloco in pecas_brutas:
        chave = (familia, round(peso, 3), round(area, 3))
        if chave not in representantes:
            representantes[chave] = [peso, area, {bloco}]
        else:
            representantes[chave][2].add(bloco)

    pecas = [
        (familia, peso, area, ', '.join(sorted(blocos)), idx)
        for idx, ((familia, _, _), (peso, area, blocos)) in enumerate(representantes.items())
    ]

    n = len(pecas)
    if n == 0:
        return []

    find, union, _ = _union_find_init(n)

    for i in range(n):
        fam_i, peso_i, area_i, _, _ = pecas[i]
        for j in range(i + 1, n):
            fam_j, peso_j, area_j, _, _ = pecas[j]
            if fam_i == fam_j:
                continue
            if abs(area_i - area_j) > tol_area:
                continue
            if abs(peso_i - peso_j) > tol_peso:
                continue
            union(i, j)

    grupos: dict = {}
    for i in range(n):
        grupos.setdefault(find(i), []).append(pecas[i])

    suspeitos = []
    for lista in grupos.values():
        fam_dict = {fam: blocos for fam, _, _, blocos, _ in lista}
        if len(fam_dict) > 1:
            suspeitos.append({
                'familias': fam_dict,
                'peso': lista[0][1],
                'area': lista[0][2],
            })

    return suspeitos


def _gerar_txt_familias(suspeitos: list[dict], tol_peso: float, tol_area: float,
                         nome_arquivo: str, tmp_dir: Path) -> Path:
    linhas = [
        '=' * 70,
        '  RELATÓRIO — PEÇAS COM PESO/ÁREA IDÊNTICOS MAS FAMÍLIAS DIFERENTES',
        f'  Arquivo     : {nome_arquivo}',
        f'  Tolerâncias : peso ±{tol_peso}  |  área ±{tol_area}',
        '=' * 70,
        '',
    ]

    if not suspeitos:
        linhas.append('Nenhuma divergência encontrada.')
    else:
        for idx, grupo in enumerate(suspeitos, 1):
            linhas.append(f'Grupo {idx}:')
            linhas.append(f'  Peso médio : {grupo["peso"]:.6f}')
            linhas.append(f'  Área média : {grupo["area"]:.6f}')
            linhas.append(f'  Famílias ({len(grupo["familias"])}):')
            for fam in sorted(grupo['familias']):
                linhas.append(f'    - {grupo["familias"][fam]} - {fam}')
            linhas.append('-' * 40)
            linhas.append('')

    linhas.append(f'Total de grupos suspeitos: {len(suspeitos)}')
    linhas.append('Fim do relatório.')

    out = tmp_dir / 'relatorio_familias_duplicadas.txt'
    out.write_text('\n'.join(linhas), encoding='utf-8')
    return out


def _gerar_csv_familias(suspeitos: list[dict], tmp_dir: Path) -> Path:
    out = tmp_dir / 'relatorio_familias_duplicadas.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Grupo', 'Peso', 'Area', 'Bloco', 'Familia'])
        for idx, grupo in enumerate(suspeitos, 1):
            for fam in sorted(grupo['familias']):
                w.writerow([idx, grupo['peso'], grupo['area'],
                             grupo['familias'][fam], fam])
    return out


def verificar_familias_duplicadas(arquivo: Path, params: dict, dest_dir: Path):
    """Generator SSE — Modo A: detecta famílias com geometria duplicada.

    Args:
        arquivo:  Caminho do Excel já salvo em disco.
        params:   dict com tol_peso (default 0.009) e tol_area (default 0.009).
        dest_dir: Pasta de destino para o ZIP com o relatório.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    tol_peso = float(params.get('tol_peso', 0.009))
    tol_area = float(params.get('tol_area', 0.009))
    tmp_dir  = Path(tempfile.mkdtemp(prefix='cad_comp_a_'))
    inicio   = time.time()

    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        yield sse_fail('dependências', 'pandas não instalado. Execute: pip install pandas openpyxl')
        yield sse_done()
        return

    try:
        yield sse_log(f'Lendo planilha: {arquivo.name}...')

        import pandas as pd

        try:
            df = pd.read_excel(arquivo, dtype=str)
        except Exception as exc:
            yield sse_fail(arquivo.name, f'Falha ao ler Excel: {exc}')
            return

        colunas_obr = ['Single Part Code', 'Unit. Weight', 'Area/Length']
        try:
            _validar_colunas(df, colunas_obr, arquivo.name)
        except ValueError as exc:
            yield sse_fail(arquivo.name, str(exc))
            return

        yield sse_log(f'{len(df)} linha(s) carregada(s).')
        yield sse_log(f'Tolerâncias: peso ±{tol_peso}  |  área ±{tol_area}')
        yield sse_log('Aplicando Union-Find cross-família...')

        try:
            suspeitos = _processar_familias_duplicadas(df, tol_peso, tol_area)
        except Exception as exc:
            yield sse_fail(arquivo.name, f'Falha no processamento: {exc}')
            return

        yield sse_log('')
        yield sse_log('=' * 60)
        yield sse_log(' GRUPOS COM FAMÍLIAS DUPLICADAS')
        yield sse_log('=' * 60)
        yield sse_log('')

        if not suspeitos:
            yield sse_log('Nenhuma peça de famílias diferentes com peso/área idênticos encontrada.')
        else:
            for idx, grupo in enumerate(suspeitos, 1):
                familias_fmt = ' | '.join(sorted(grupo['familias']))
                yield sse_ok(
                    f'Grupo {idx}: {familias_fmt} '
                    f'(peso={grupo["peso"]:.4f}, área={grupo["area"]:.4f})'
                )

        yield sse_log('')
        yield sse_log(f'Grupos suspeitos encontrados: {len(suspeitos)}')
        yield sse_log(f'Concluído em {time.time() - inicio:.2f}s.')

        txt_path = _gerar_txt_familias(suspeitos, tol_peso, tol_area, arquivo.name, tmp_dir)
        csv_path = _gerar_csv_familias(suspeitos, tmp_dir)

        zip_name = create_zip([txt_path, csv_path], dest_dir, prefix='comp_familias')
        yield sse_log(f'ZIP gerado: {zip_name}')
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail(arquivo.name, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        yield sse_done()


# =====================================================================
# MODO B — CÓPIAS DIVERGENTES
# =====================================================================

def _agrupar_copias(copias: list, tol_grupo: float) -> list[list]:
    """Union-Find intra-família: agrupa cópias com Δpeso/Δarea ≤ tol_grupo."""
    n = len(copias)
    find, union, _ = _union_find_init(n)

    for i in range(n):
        for j in range(i + 1, n):
            if (abs(copias[i][1] - copias[j][1]) <= tol_grupo and
                    abs(copias[i][2] - copias[j][2]) <= tol_grupo):
                union(i, j)

    grupos: dict = {}
    for i in range(n):
        grupos.setdefault(find(i), []).append(copias[i])
    return list(grupos.values())


def _processar_copias_divergentes(df, tol_verdadeira: float,
                                   tol_grupo: float) -> list[dict]:
    """Separa originais de cópias _C##, agrupa as cópias e compara com o original."""
    originais: dict = {}   # nome -> (peso, area)
    familias: dict  = {}   # familia -> [(nome, peso, area)]

    for _, row in df.iterrows():
        try:
            nome = str(row['Single Part Code']).strip()
            peso = _parse_number(row['Unit. Weight'])
            area = _parse_number(row['Area/Length'])
        except (ValueError, TypeError, KeyError):
            continue

        m = _PADRAO_COPIA.search(nome)
        if m:
            familia = nome[:m.start()]
            familias.setdefault(familia, []).append((nome, peso, area))
        else:
            originais[nome] = (peso, area)

    familias_com_problema = []

    for familia, lista_copias in familias.items():
        original = originais.get(familia)
        grupos   = _agrupar_copias(lista_copias, tol_grupo)

        grupos_info = []
        for grupo in grupos:
            peso_medio = sum(c[1] for c in grupo) / len(grupo)
            area_media = sum(c[2] for c in grupo) / len(grupo)

            if original:
                ok       = (abs(peso_medio - original[0]) <= tol_verdadeira and
                            abs(area_media - original[1]) <= tol_verdadeira)
                dif_peso = peso_medio - original[0]
                dif_area = area_media - original[1]
            else:
                ok = None
                dif_peso = dif_area = None

            grupos_info.append({
                'pecas':      sorted(c[0] for c in grupo),
                'peso_medio': peso_medio,
                'area_media': area_media,
                'ok':         ok,
                'dif_peso':   dif_peso,
                'dif_area':   dif_area,
            })

        tem_divergencia = original and any(not g['ok'] for g in grupos_info)
        tem_split       = len(grupos_info) > 1

        if tem_divergencia or tem_split:
            familias_com_problema.append({
                'familia':  familia,
                'original': original,
                'grupos':   grupos_info,
            })

    return familias_com_problema


def _gerar_txt_copias(problemas: list[dict], tol_verdadeira: float,
                       tol_grupo: float, nome_arquivo: str, tmp_dir: Path) -> Path:
    todas_divergentes = [
        p
        for fam in problemas
        for g in fam['grupos']
        if fam['original'] and not g['ok']
        for p in g['pecas']
    ]

    linhas = [
        '=' * 70,
        '  RELATÓRIO — CÓPIAS DIVERGENTES DO ORIGINAL',
        f'  Arquivo               : {nome_arquivo}',
        f'  Tol. cópia verdadeira : ±{tol_verdadeira}',
        f'  Tol. agrupamento      : ±{tol_grupo}',
        '=' * 70,
        '',
    ]

    if todas_divergentes:
        linhas.append('PEÇAS DIVERGENTES DO ORIGINAL:')
        linhas.append(f'  {", ".join(todas_divergentes)}')
        linhas.append('')
        linhas.append('=' * 70)
        linhas.append('')

    if not problemas:
        linhas.append('Nenhuma divergência encontrada.')
    else:
        for fam_data in problemas:
            familia  = fam_data['familia']
            original = fam_data['original']
            grupos   = fam_data['grupos']

            linhas.append(f'FAMÍLIA: {familia}')
            if original:
                linhas.append(f'  Original : peso={original[0]:.6f}  área={original[1]:.6f}')
            else:
                linhas.append('  Original : NÃO ENCONTRADO NA PLANILHA')

            num_grupos = len(grupos)
            linhas.append(f'  Grupos de cópias: {num_grupos}')
            if num_grupos > 1:
                linhas.append(
                    f'  *** ATENÇÃO: cópias desta família se dividem em '
                    f'{num_grupos} perfis distintos ***'
                )

            for idx, g in enumerate(grupos, 1):
                if original is not None:
                    status = 'OK — igual ao original' if g['ok'] else 'DIVERGE do original'
                else:
                    status = '(sem original para comparar)'

                linhas.append(f'\n  Grupo {idx} [{status}]')
                linhas.append(f'    Peso médio : {g["peso_medio"]:.6f}')
                linhas.append(f'    Área média : {g["area_media"]:.6f}')
                if g['dif_peso'] is not None and not g['ok']:
                    linhas.append(
                        f'    dif. peso={g["dif_peso"]:+.6f}  '
                        f'dif. área={g["dif_area"]:+.6f}'
                    )
                linhas.append(f'    Peças ({len(g["pecas"])}): {", ".join(g["pecas"])}')

            linhas.append('\n' + '-' * 70)
            linhas.append('')

    linhas.append(f'Total de famílias com problema: {len(problemas)}')
    linhas.append('Fim do relatório.')

    out = tmp_dir / 'relatorio_copias_divergentes.txt'
    out.write_text('\n'.join(linhas), encoding='utf-8')
    return out


def verificar_copias_divergentes(arquivo: Path, params: dict, dest_dir: Path):
    """Generator SSE — Modo B: detecta cópias (_C##) divergentes do original.

    Args:
        arquivo:  Caminho do Excel já salvo em disco.
        params:   dict com tol_verdadeira (default 0.001) e tol_grupo (default 0.010).
        dest_dir: Pasta de destino para o ZIP com o relatório.

    Yields:
        Strings no formato SSE (data: TIPO payload\\n\\n).
    """
    tol_verdadeira = float(params.get('tol_verdadeira', 0.001))
    tol_grupo      = float(params.get('tol_grupo',      0.010))
    tmp_dir        = Path(tempfile.mkdtemp(prefix='cad_comp_b_'))
    inicio         = time.time()

    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        yield sse_fail('dependências', 'pandas não instalado. Execute: pip install pandas openpyxl')
        yield sse_done()
        return

    try:
        yield sse_log(f'Lendo planilha: {arquivo.name}...')

        import pandas as pd

        try:
            df = pd.read_excel(arquivo, dtype=str)
        except Exception as exc:
            yield sse_fail(arquivo.name, f'Falha ao ler Excel: {exc}')
            return

        colunas_obr = ['Single Part Code', 'Unit. Weight', 'Area/Length']
        try:
            _validar_colunas(df, colunas_obr, arquivo.name)
        except ValueError as exc:
            yield sse_fail(arquivo.name, str(exc))
            return

        yield sse_log(f'{len(df)} linha(s) carregada(s).')
        yield sse_log(f'Tol. verdadeira: ±{tol_verdadeira}  |  tol. agrupamento: ±{tol_grupo}')
        yield sse_log('Separando originais e cópias _C##...')

        try:
            problemas = _processar_copias_divergentes(df, tol_verdadeira, tol_grupo)
        except Exception as exc:
            yield sse_fail(arquivo.name, f'Falha no processamento: {exc}')
            return

        yield sse_log('')
        yield sse_log('=' * 60)
        yield sse_log(' FAMÍLIAS COM CÓPIAS DIVERGENTES')
        yield sse_log('=' * 60)
        yield sse_log('')

        if not problemas:
            yield sse_log('Nenhuma divergência encontrada — todas as cópias são válidas.')
        else:
            for fam_data in problemas:
                familia   = fam_data['familia']
                grupos    = fam_data['grupos']
                divergentes = sum(
                    1 for g in grupos if fam_data['original'] and not g['ok']
                )
                num_grupos  = len(grupos)

                partes = []
                if divergentes:
                    partes.append(f'{divergentes} grupo(s) divergente(s)')
                if num_grupos > 1:
                    partes.append(f'{num_grupos} perfis distintos')
                if not partes:
                    partes.append('sem original para comparar')

                yield sse_ok(f'{familia} — {" / ".join(partes)}')

        yield sse_log('')
        yield sse_log(f'Famílias com problema: {len(problemas)}')
        yield sse_log(f'Concluído em {time.time() - inicio:.2f}s.')

        txt_path = _gerar_txt_copias(
            problemas, tol_verdadeira, tol_grupo, arquivo.name, tmp_dir
        )
        zip_name = create_zip([txt_path], dest_dir, prefix='comp_copias')
        yield sse_log(f'ZIP gerado: {zip_name}')
        yield sse_download(zip_name)

    except Exception as exc:
        yield sse_fail(arquivo.name, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        yield sse_done()
