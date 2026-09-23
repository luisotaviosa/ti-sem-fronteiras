# -*- coding: utf-8 -*-
"""
Radar de tecnologias CALCULADO a partir das vagas coletadas (coleção `radar_tecnologias`).

Método (documentado no próprio documento, campo `metodo`):
  participação = nº de vagas de TI que citam a tecnologia / total de vagas de TI
  demanda (0-100) = participação / maior participação entre as tecnologias × 100

O índice é RELATIVO (a tecnologia mais citada vale 100) e só é publicado com
amostra mínima, para não produzir um "radar" com 3 vagas.
"""
import logging
from collections import Counter

from .arbeitnow import TECNOLOGIAS
from .modelos import agora_iso, id_documento, proveniencia

log = logging.getLogger(__name__)

COLECAO = "radar_tecnologias"
MIN_AMOSTRA = 30

# --- custo de vida estimado (paises.custo_vida_mensal_usd) --------------------------
#
# Baseline: U.S. Bureau of Labor Statistics, Consumer Expenditure Surveys — 2024,
# gasto médio anual de "single consumer, one earner" (uma pessoa, com renda própria:
# o perfil mais parecido com quem está se mudando sozinho para trabalhar, e não a
# média de qualquer família). US$ 56.652/ano = US$ 4.721/mês.
# Fonte: news release USDL-25-1586 (19/12/2025), tabela por número de rendas da
# unidade de consumo: https://www.bls.gov/news.release/cesan.htm
# (dado verificado também via FRED, série CXUTOTALEXPLB0703M, que republica o
# número oficial do BLS: https://fred.stlouisfed.org/series/CXUTOTALEXPLB0703M)
BASELINE_USD_MENSAL = 4721
BASELINE_ANO_REFERENCIA = 2024
BASELINE_FONTE = ("U.S. Bureau of Labor Statistics, Consumer Expenditure Surveys — "
                  "gasto médio anual de pessoa solteira com renda própria, 2024: "
                  "US$ 56.652/ano (US$ 4.721/mês)")
BASELINE_URL = "https://www.bls.gov/news.release/cesan.htm"
CAMPO_INDICE_PADRAO = "PA.NUS.PPPC.RF"   # nível de preços do Banco Mundial (calculado), USA = 1,0
COLECAO_PAISES = "paises"


def calcular_custo_vida_estimado(indicadores: list, baseline_usd_mensal=BASELINE_USD_MENSAL,
                                 campo_indice=CAMPO_INDICE_PADRAO) -> list:
    """
    ESTIMA o custo de vida mensal (USD) de cada país como

        baseline dos EUA (BLS)  ×  nível de preços do país (Banco Mundial, USA = 1,0)

    Devolve uma lista de PATCHES para a coleção `paises` — cada um só com
    `custo_vida_mensal_usd` e os campos de proveniência ao lado, para ser mesclado
    (merge=True) no documento do país já existente (região, idioma, visto etc. não
    são tocados). O `id` de cada patch usa a MESMA regra do `seed_firestore.py`
    (nome do país normalizado), para cair no documento certo — ver
    tests/test_derivados.py, que confere essa igualdade diretamente contra
    `seed_firestore.id_seguro`.

    Isto é uma ESTIMATIVA, não uma pesquisa país a país: assume que a razão entre o
    consumo típico de um americano solteiro e o de alguém no país-alvo é a mesma
    razão medida para a economia inteira (nível de preços do PIB). Na prática, a
    cesta de um estrangeiro recém-chegado (aluguel, mercado, transporte) pode pesar
    diferente da média nacional — trate como ponto de partida, não como pesquisa de
    campo. Por isso todo documento carrega `custo_vida_mensal_usd_calculado: true` e
    o método por extenso, para a interface avisar que é estimado.
    """
    docs = []
    for ind in indicadores:
        if ind.get("indicador") != campo_indice or not isinstance(ind.get("valor"), (int, float)):
            continue
        estimativa = round(baseline_usd_mensal * ind["valor"])
        metodo = (f"baseline EUA (BLS {BASELINE_ANO_REFERENCIA}, pessoa solteira com renda "
                  f"própria: US$ {baseline_usd_mensal}/mês) × nível de preços do país "
                  f"({campo_indice} = {ind['valor']:.4g}, Banco Mundial, ano "
                  f"{ind.get('ano_referencia', '—')})")
        docs.append({
            "id": id_documento(ind["pais"]),
            "custo_vida_mensal_usd": estimativa,
            "custo_vida_mensal_usd_calculado": True,
            "custo_vida_mensal_usd_metodo": metodo,
            "custo_vida_mensal_usd_fonte": f"{BASELINE_FONTE}; {ind.get('fonte', '—')}",
            "custo_vida_mensal_usd_url_fonte": BASELINE_URL,
            "custo_vida_mensal_usd_coletado_em": ind.get("coletado_em"),
        })
    return docs

CATEGORIAS = {                       # mesmas categorias de data.py
    "Python": "Linguagem",
    "JavaScript / TypeScript": "Linguagem",
    "AWS": "Cloud",
    "Docker / Kubernetes": "DevOps",
    "Linux (Suporte/Admin)": "Infraestrutura",
    "SQL": "Dados",
    "Active Directory": "Infraestrutura",
    "Terraform": "DevOps",
}
METODO = ("participação = vagas de TI que citam a tecnologia / total de vagas de TI; "
          "demanda = participação / maior participação × 100")


def limitar_por_empresa(vagas: list, maximo: int) -> list:
    """Mantém no máximo `maximo` vagas por empresa (evita que uma agência com dezenas de
    anúncios parecidos domine o radar)."""
    contagem, mantidas = Counter(), []
    for v in vagas:
        chave = v.get("empresa") or "?"
        if contagem[chave] < maximo:
            contagem[chave] += 1
            mantidas.append(v)
    return mantidas


def calcular_radar(vagas: list, fonte="Arbeitnow (calculado das vagas coletadas; vagas na Europa)",
                   min_amostra=MIN_AMOSTRA, max_por_empresa=None) -> list:
    if max_por_empresa:
        vagas = limitar_por_empresa(vagas, max_por_empresa)
    n = len(vagas)
    if n < min_amostra:
        log.warning("Radar não publicado: amostra de %d vagas (mínimo %d)", n, min_amostra)
        return []
    empresas = Counter(v.get("empresa") or "?" for v in vagas)
    maior_empresa, n_maior = empresas.most_common(1)[0]
    concentracao = n_maior / n
    if concentracao > 0.30:
        log.warning("Radar concentrado: %.0f%% das vagas vêm de uma só empresa (%s). "
                    "Considere usar max_por_empresa.", 100 * concentracao, maior_empresa)
    contagem = {t: sum(1 for v in vagas if t in v.get("stack", [])) for t in TECNOLOGIAS}
    maior = max(contagem.values()) or 1
    datas = sorted(v["publicado_em"] for v in vagas if v.get("publicado_em"))
    coletado_em = agora_iso()
    docs = []
    for tec, c in contagem.items():
        doc = {
            "id": id_documento("radar", tec),
            "tecnologia": tec,
            "categoria": CATEGORIAS.get(tec, "Outra"),
            "demanda": round(100 * (c / n) / (maior / n)),
            "vagas_com_mencao": c,
            "participacao": round(c / n, 4),
            "empresas_distintas": len(empresas),
            "concentracao_maior_empresa": round(concentracao, 3),
            "max_por_empresa": max_por_empresa,
            "periodo": {"de": datas[0] if datas else None, "ate": datas[-1] if datas else None},
            "metodo": METODO,
        }
        doc.update(proveniencia(fonte, "coleção `vagas` do próprio Firestore", "derivado de dados coletados",
                                coletado_em=coletado_em, n_amostra=n))
        docs.append(doc)
    return docs
