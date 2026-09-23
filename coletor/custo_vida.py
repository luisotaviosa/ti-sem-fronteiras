# -*- coding: utf-8 -*-
"""
Custo de vida — Eurostat (prc_ppp_ind: Purchasing power parities, price level indices).

STATUS: ETAPA 1 DE 2 (descoberta). O decodificador de JSON-stat 2.0 abaixo segue um
padrão aberto e estável (https://json-stat.org/format/) e foi testado com um exemplo
construído à mão, fiel à especificação (ver tests/test_custo_vida.py).

Rodada 1 de descoberta (21/09/2026, `python -m coletor.custo_vida --descobrir`) já
confirmou os 24 códigos reais de `na_item` deste dataset — nenhum chute, foi lido
direto da fonte. Ela também mostrou que a dimensão "unit" NÃO existe neste dataset
(a suposição inicial estava errada); o que falta é achar a dimensão que escolhe a
CATEGORIA de consumo (GDP total, alimentação, consumo das famílias etc.) — a própria
página do Eurostat menciona uma dimensão assim (talvez chamada `ppp_cat`), mas ela
não apareceu na primeira rodada porque a função só olhava para "na_item" e "unit".
Corrigido: `descobrir_dimensoes()` agora lista TODAS as dimensões que a fonte
devolver, sem supor nomes — rode de novo e envie a saída.

Rodada 2 (mesmo dia): o usuário rodou de novo e enviou a lista completa. Confirmado:
  - não existe dimensão "unit" neste dataset (correto na rodada 1: ela não existe mesmo);
  - a dimensão que faltava se chama `ppp_cat` (61 códigos: GDP, consumo das famílias,
    alimentação, moradia, transporte, etc. — uma árvore de categorias de despesa).

DECISÃO (ver constantes NA_ITEM_PADRAO / PPP_CAT_PADRAO abaixo):
  - na_item  = PLI_EU27_2020  (Price level indices, EU27_2020=100) — é o índice de
    nível de preços, não o fator de PPC bruto; comparável entre países.
  - ppp_cat  = E011 (Household final consumption expenditure) — despesa das famílias,
    e não A01 (Actual Individual Consumption). A diferença importa: AIC soma também
    serviços públicos consumidos individualmente (saúde e educação públicas, mesmo
    quando gratuitas no ponto de uso), o que infla o índice em países com forte
    provisão pública. Para alguém se mudando, o que pesa no orçamento é o que sai do
    próprio bolso — mais perto de E011. Categorias mais finas existem (moradia
    "A0104", alimentação "A0101", transporte "A0107") e podem virar um índice
    "essenciais" mais preciso depois, se fizer sentido.

Este valor é um ÍNDICE relativo (EU27_2020 = 100), não um valor em USD/mês — por
isso ele entra em `indicadores_pais` como mais um indicador complementar (como o
nível de preços do Banco Mundial), sem substituir `custo_vida_mensal_usd` da ficha
do país, que exigiria uma conversão para valor absoluto que este dataset não fornece
sozinho.

Cobertura: Eurostat publica para os 27 países da UE, mais Reino Unido, EFTA (Islândia,
Noruega, Suíça) e alguns países candidatos — não cobre TODO PAÍS do mundo. Dos 6 países
do protótipo, cobre Portugal, Alemanha, Irlanda e Espanha; Canadá e Emirados Árabes
Unidos ficam de fora. Para esses dois, o nível de preços já calculado em
`banco_mundial.py` (a partir de PA.NUS.PPP/PA.NUS.FCRF) continua sendo a única fonte.

Referências consultadas (21/09/2026):
  - endpoint e formato: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON
  - dataset prc_ppp_ind: https://ec.europa.eu/eurostat/databrowser/view/prc_ppp_ind/default/table
  - cobertura geográfica (27 UE + RU + EFTA + candidatos): https://ec.europa.eu/eurostat/cache/metadata/en/prc_ppp_ind_esms.htm
Não consegui buscar uma resposta AO VIVO do endpoint nesta sessão (sem acesso de rede
no ambiente de execução) — por isso a etapa de descoberta, em vez de um valor pronto.
"""
import logging

from .modelos import agora_utc, id_documento, proveniencia
from .rede import ErroColeta, obter_json

log = logging.getLogger(__name__)

ENDPOINT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_ppp_ind"
FONTE = "Eurostat (Purchasing power parities and price level indices, prc_ppp_ind)"
LICENCA = "Reutilização livre com atribuição (política de dados abertos do Eurostat)"
COLECAO = "indicadores_pais"  # mesma coleção do Banco Mundial: é mais um indicador por país

# Só os países do protótipo que o Eurostat cobre (códigos geo do Eurostat = ISO2, exceto Grécia "EL")
PAISES_COBERTOS = {"Portugal": "PT", "Alemanha": "DE", "Irlanda": "IE", "Espanha": "ES"}

# Confirmados via `--descobrir` (21/09/2026) — ver a justificativa da escolha no cabeçalho do módulo.
NA_ITEM_PADRAO = "PLI_EU27_2020"     # Price level indices (EU27_2020=100)
PPP_CAT_PADRAO = "E011"              # Household final consumption expenditure


def decodificar_json_stat(doc: dict) -> list:
    """
    Decodifica um dataset em JSON-stat 2.0 (padrão aberto, não específico do Eurostat:
    https://json-stat.org/format/) em uma lista de registros
    [{dim_id: codigo_da_categoria, ..., "value": valor}, ...].

    Funciona para qualquer número de dimensões. Testado com um exemplo construído à
    mão (ver tests/test_custo_vida.py); nunca testado contra uma resposta real desta
    fonte nesta sessão.
    """
    ids = doc["id"]
    sizes = doc["size"]
    dims = doc["dimension"]

    codigos_por_dim = []
    for dim_id in ids:
        categoria = dims[dim_id]["category"]
        indice = categoria.get("index")
        if indice is None:                                   # dimensão de categoria única
            codigos = list(categoria.get("label", {}).keys()) or [dim_id]
        elif isinstance(indice, dict):                        # {codigo: posicao}
            codigos = [c for c, _ in sorted(indice.items(), key=lambda kv: kv[1])]
        else:                                                 # já é uma lista de códigos, em ordem
            codigos = list(indice)
        codigos_por_dim.append(codigos)

    # stride de cada dimensão (row-major: a última dimensão varia mais rápido)
    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    valores = doc["value"]
    if isinstance(valores, dict):
        obter_valor = lambda i: valores.get(str(i))
    else:
        obter_valor = lambda i: valores[i] if i < len(valores) else None

    total = 1
    for s in sizes:
        total *= s

    registros = []
    for flat in range(total):
        resto = flat
        combinacao = {}
        for dim_id, stride, codigos in zip(ids, strides, codigos_por_dim):
            pos = resto // stride
            resto %= stride
            if pos < len(codigos):
                combinacao[dim_id] = codigos[pos]
        v = obter_valor(flat)
        if v is not None:
            registros.append({**combinacao, "value": v})
    return registros


def descobrir_dimensoes(http=obter_json, geo_amostra="PT") -> dict:
    """
    Busca uma fatia mínima do dataset (um país) e lista TODAS as dimensões que a
    resposta trouxer, com seus códigos e rótulos — sem supor os nomes de antemão.

    (Primeira versão desta função só olhava "na_item" e "unit"; a resposta real
    mostrou que "unit" não existe neste dataset e que falta outra dimensão, a que
    escolhe a categoria de consumo — GDP, alimentação, consumo das famílias etc.
    Por isso agora ela devolve o que a fonte realmente tiver, dimensão por dimensão.)
    -> {dim_id: {"rotulo": rótulo da dimensão, "categorias": {codigo: rótulo}}}
    """
    resp = http(ENDPOINT, {"format": "JSON", "geo": geo_amostra, "lang": "en"})
    if not isinstance(resp, dict) or "dimension" not in resp:
        raise ErroColeta(f"Resposta inesperada do Eurostat: {str(resp)[:200]}")
    dims = resp["dimension"]
    ordem = resp.get("id") or list(dims.keys())
    return {
        dim_id: {
            "rotulo": dims[dim_id].get("label", dim_id),
            "categorias": dict((dims[dim_id].get("category") or {}).get("label", {})),
        }
        for dim_id in ordem if dim_id in dims
    }


def coletar(na_item: str = NA_ITEM_PADRAO, filtros_extra: dict = None, paises=PAISES_COBERTOS,
           http=obter_json, agora=None) -> list:
    """
    Coleta o indicador `na_item` (padrão: nível de preços, EU27_2020=100) para os
    países cobertos, restrito à categoria de despesa em `filtros_extra` (padrão:
    consumo das famílias — ver a justificativa no cabeçalho do módulo). Documentos no
    mesmo formato de `banco_mundial.coletar()`, na mesma coleção (`indicadores_pais`),
    com `indicador` prefixado por "EUROSTAT." para não colidir com os códigos do
    Banco Mundial.
    """
    agora = agora or agora_utc()
    filtros_extra = {"ppp_cat": PPP_CAT_PADRAO} if filtros_extra is None else filtros_extra
    geos = list(paises.values())
    params = {"format": "JSON", "na_item": na_item, "geo": geos, "lang": "en"}
    params.update(filtros_extra or {})
    resp = http(ENDPOINT, params)
    if not isinstance(resp, dict) or "value" not in resp:
        raise ErroColeta(f"Resposta inesperada do Eurostat: {str(resp)[:200]}")

    registros = decodificar_json_stat(resp)
    geo_para_nome = {v: k for k, v in paises.items()}
    rotulo_na_item = ((resp.get("dimension", {}).get("na_item") or {})
                      .get("category", {}).get("label", {}).get(na_item, na_item))
    ppp_cat = (filtros_extra or {}).get("ppp_cat")
    rotulo_ppp_cat = ((resp.get("dimension", {}).get("ppp_cat") or {})
                     .get("category", {}).get("label", {}).get(ppp_cat)) if ppp_cat else None
    descricao = f"{rotulo_na_item} — {rotulo_ppp_cat}" if rotulo_ppp_cat else rotulo_na_item

    # para cada país, fica com o ano mais recente
    melhor = {}
    for r in registros:
        geo = r.get("geo")
        if geo not in geo_para_nome:
            continue
        try:
            ano = int(r.get("time"))
        except (TypeError, ValueError):
            continue
        if geo not in melhor or ano > melhor[geo][0]:
            melhor[geo] = (ano, r["value"])

    coletado_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    sufixo_id = "_".join([na_item] + [str(v) for v in (filtros_extra or {}).values()])
    docs = []
    for geo, (ano, valor) in melhor.items():
        doc = {
            "id": id_documento("eurostat", geo, sufixo_id),
            "pais": geo_para_nome[geo],
            "iso2": geo,
            "indicador": f"EUROSTAT.{na_item}",
            "descricao": descricao,
            "unidade": "índice" if na_item.startswith("PLI") else "razão",
            "valor": float(valor),
            "ano_referencia": ano,
            "defasagem_anos": agora.year - ano,
        }
        url_params = "&".join([f"na_item={na_item}"] + [f"{k}={v}" for k, v in (filtros_extra or {}).items()])
        doc.update(proveniencia(
            FONTE, f"{ENDPOINT}?format=JSON&{url_params}&geo={geo}",
            LICENCA, coletado_em=coletado_em,
        ))
        docs.append(doc)
    return docs


def testar_combinacao(na_item: str = NA_ITEM_PADRAO, ppp_cat: str = PPP_CAT_PADRAO,
                      geo_amostra="PT", http=obter_json) -> dict:
    """
    Busca a MESMA combinação que `coletar()` usa, para um só país, e mostra a
    resposta crua: quantos valores vieram, e por quê (a combinação na_item×ppp_cat
    pode simplesmente não ter dado publicado — nem toda combinação das 24×61
    existe). Use quando `coletar()` devolver 0 documentos sem erro.
    """
    params = {"format": "JSON", "na_item": na_item, "ppp_cat": ppp_cat, "geo": geo_amostra, "lang": "en"}
    resp = http(ENDPOINT, params)
    diagnostico = {"params_enviados": params, "chaves_da_resposta": list(resp.keys()) if isinstance(resp, dict) else None}
    if not isinstance(resp, dict):
        diagnostico["problema"] = f"resposta não é um objeto JSON (tipo: {type(resp).__name__})"
        return diagnostico
    diagnostico["id_dimensoes"] = resp.get("id")
    diagnostico["size"] = resp.get("size")
    valor = resp.get("value")
    diagnostico["value_tipo"] = type(valor).__name__ if valor is not None else None
    diagnostico["value_tamanho"] = len(valor) if valor else 0
    if isinstance(valor, dict):
        diagnostico["value_amostra"] = dict(list(valor.items())[:5])
    if not valor:
        diagnostico["problema"] = (
            "a resposta veio sem nenhum valor: o Eurostat entendeu a consulta (não deu erro), "
            "mas não existe dado publicado para esta combinação de na_item + ppp_cat + geo. "
            "Tente outra combinação de ppp_cat (ver --descobrir) ou confirme geo/lang."
        )
    else:
        diagnostico["registros_decodificados"] = decodificar_json_stat(resp)[:5]
    return diagnostico


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Descoberta e diagnóstico do dataset de custo de vida (Eurostat)")
    ap.add_argument("--descobrir", action="store_true", help="lista TODAS as dimensões, códigos e rótulos")
    ap.add_argument("--testar", action="store_true",
                    help=f"testa a combinação padrão (na_item={NA_ITEM_PADRAO}, ppp_cat={PPP_CAT_PADRAO}) para 1 país")
    ap.add_argument("--na-item", default=NA_ITEM_PADRAO)
    ap.add_argument("--ppp-cat", default=PPP_CAT_PADRAO)
    ap.add_argument("--geo", default="PT")
    args = ap.parse_args()
    if not (args.descobrir or args.testar):
        ap.error("use --descobrir e/ou --testar")

    if args.descobrir:
        dimensoes = descobrir_dimensoes()
        for dim_id, info in dimensoes.items():
            cats = info["categorias"]
            print(f"\n== {dim_id}: {info['rotulo']} ({len(cats)} código(s)) ==")
            for codigo, rotulo in list(cats.items())[:60]:
                print(f"  {codigo:20s} {rotulo}")
            if len(cats) > 60:
                print(f"  ... e mais {len(cats) - 60}")
        print("\nProcure a dimensão que escolhe a CATEGORIA de consumo (GDP, alimentação, "
              "consumo das famílias etc. — pode se chamar 'ppp_cat' ou outro nome) e me "
              "envie esta saída inteira junto com o na_item que parecer mais próximo de "
              "'custo de vida' (ex.: os que começam com PLI_).")

    if args.testar:
        print(f"\n== Testando na_item={args.na_item} · ppp_cat={args.ppp_cat} · geo={args.geo} ==")
        d = testar_combinacao(args.na_item, args.ppp_cat, args.geo)
        for chave, valor in d.items():
            print(f"  {chave}: {valor}")
        if d.get("problema"):
            print("\n>>> Envie esta saída inteira para eu ajustar o na_item/ppp_cat. <<<")
        else:
            print(f"\nOK: {d['value_tamanho']} valor(es) encontrado(s).")
