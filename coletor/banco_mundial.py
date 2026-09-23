# -*- coding: utf-8 -*-
"""
Coletor do Banco Mundial (World Development Indicators) -> coleção `indicadores_pais`.

Fonte oficial, sem chave de API. Formato da resposta (v2, ?format=json):

    [ {page, pages, per_page, total, lastupdated}, [ {indicator, country,
      countryiso3code, date, value, unit, obs_status, decimal}, ... ] ]

ATENÇÃO: erros vêm com HTTP 200 e um array de UM só elemento
(`[{"message": [...]}]`). Por isso o código confere o formato antes de usar.

Observação importante: o Banco Mundial NÃO publica "custo de vida mensal" nem
"salário médio em TI". Estes indicadores ENRIQUECEM a ficha do país (PIB per
capita, inflação, nível de preços, câmbio, acesso à Internet); os campos
`custo_vida_mensal_usd` e `salario_medio_ti_usd` do app devem vir de outras
fontes (ver README_COLETOR.md).
"""
import logging

from .modelos import agora_utc, id_documento, proveniencia
from .rede import ErroColeta, montar_url, obter_json

log = logging.getLogger(__name__)

BASE = "https://api.worldbank.org/v2"
FONTE = "Banco Mundial (World Development Indicators)"
LICENCA = "CC BY 4.0 (confirmar em data.worldbank.org/summary-terms-of-use)"
COLECAO = "indicadores_pais"
MAX_PAGINAS = 5

# Mesmos nomes de país usados em data.py (chave de junção com a coleção `paises`)
PAISES = {
    "Portugal": "PT",
    "Alemanha": "DE",
    "Canadá": "CA",
    "Irlanda": "IE",
    "Espanha": "ES",
    "Emirados Árabes Unidos": "AE",
}

# código do indicador -> (descrição, unidade)
INDICADORES = {
    "NY.GDP.PCAP.CD": ("PIB per capita", "US$ correntes"),
    "FP.CPI.TOTL.ZG": ("Inflação, preços ao consumidor", "% ao ano"),
    "PA.NUS.PPP": ("Fator de conversão PPC do PIB", "moeda local por US$ internacional"),
    "PA.NUS.FCRF": ("Taxa de câmbio oficial (média do período)", "moeda local por US$"),
    "IT.NET.USER.ZS": ("Indivíduos usando a Internet", "% da população"),
}


def _interpretar(resposta, url):
    """Valida o envelope [meta, linhas] e devolve (meta, linhas)."""
    if not isinstance(resposta, list) or not resposta:
        raise ErroColeta(f"Resposta inesperada do Banco Mundial em {url}")
    if len(resposta) == 1:  # erro disfarçado de HTTP 200
        raise ErroColeta(f"Consulta recusada pelo Banco Mundial: {resposta[0]}")
    meta, linhas = resposta[0], resposta[1]
    if not isinstance(meta, dict):
        raise ErroColeta(f"Cabeçalho de paginação inválido em {url}")
    return meta, (linhas or [])


def _variantes(ano_atual):
    """Formas equivalentes de pedir o dado mais recente; a primeira que a fonte aceitar é usada."""
    return [
        ("mrnev=1", {"format": "json", "mrnev": 1, "per_page": 200}),
        ("mrv=5", {"format": "json", "mrv": 5, "per_page": 200}),
        ("intervalo de datas", {"format": "json", "date": f"{ano_atual - 10}:{ano_atual}", "per_page": 200}),
    ]


def _paginar(url, base_params, http):
    """Percorre as páginas de uma consulta. Levanta ErroColeta se a fonte recusar."""
    linhas, atualizado, pagina = [], None, 1
    while True:
        meta, parte = _interpretar(http(url, {**base_params, "page": pagina}), url)
        linhas += parte
        atualizado = meta.get("lastupdated", atualizado)
        if pagina >= int(meta.get("pages") or 1) or pagina >= MAX_PAGINAS:
            return linhas, atualizado
        pagina += 1


def _entrada_catalogo(codigo, http):
    """Linha do catálogo do indicador (nome, unidade, fonte de dados) ou None."""
    try:
        _, linhas = _interpretar(http(f"{BASE}/indicator/{codigo}", {"format": "json"}), codigo)
        return linhas[0] if linhas else None
    except ErroColeta:
        return None


def _consultar(codigo, iso2s, ano_atual, http, variantes=None):
    """
    Busca o indicador para os países. Tenta cada variante de consulta; se todas forem
    recusadas, consulta o catálogo e repete com `source=<fonte do indicador>`.
    Devolve (linhas, atualizado, url, rotulo_da_variante_que_funcionou).
    """
    url = f"{BASE}/country/{';'.join(iso2s)}/indicator/{codigo}"
    lista, motivos = variantes or _variantes(ano_atual), []

    def tentar(extra=None):
        for rotulo, base in lista:
            rot = rotulo + (f" + source={extra['source']}" if extra else "")
            try:
                linhas, atualizado = _paginar(url, {**base, **(extra or {})}, http)
                return linhas, atualizado, url, rot
            except ErroColeta as e:
                motivos.append(f"[{rot}] {e}")
        return None

    achou = tentar()
    if achou:
        return achou
    fonte_id = ((_entrada_catalogo(codigo, http) or {}).get("source") or {}).get("id")
    if fonte_id:
        achou = tentar({"source": fonte_id})
        if achou:
            return achou
    raise ErroColeta(f"indicador {codigo}: nenhuma forma de consulta funcionou. " + " | ".join(motivos[:2]) + " ...")


def _mais_recente_por_pais(linhas):
    """Para cada país, a observação mais recente com valor (ignora nulos)."""
    melhor = {}
    for linha in linhas:
        if linha.get("value") is None:
            continue
        iso2 = (linha.get("country") or {}).get("id")
        try:
            ano = int(linha.get("date"))
        except (TypeError, ValueError):
            continue
        if iso2 not in melhor or ano > melhor[iso2][0]:
            melhor[iso2] = (ano, linha)
    return {iso2: par[1] for iso2, par in melhor.items()}


def _calcular_nivel_de_precos(recentes_por_codigo: dict, iso2_para_nome: dict, agora) -> list:
    """
    O indicador oficial PA.NUS.PPPC.RF (nível de preços) vem de uma base ARQUIVADA
    (source 57: "WDI Database Archives") e a API se recusa a servir seus dados,
    com ou sem `source=` — confirmado em 21/09/2026 via `--testar PA.NUS.PPPC.RF`.

    A própria definição do Banco Mundial para esse indicador é "razão entre o fator
    de conversão de PPC (PA.NUS.PPP) e a taxa de câmbio (PA.NUS.FCRF)", e esses dois
    componentes estão na base ativa (2: World Development Indicators). Por isso o
    valor é CALCULADO aqui a partir deles, em vez de buscado pronto.
    """
    numerador = recentes_por_codigo.get("PA.NUS.PPP")
    denominador = recentes_por_codigo.get("PA.NUS.FCRF")
    if not numerador or not denominador:
        return []
    docs = []
    for iso2 in sorted(set(numerador) & set(denominador)):
        if iso2 not in iso2_para_nome:
            continue
        n, d = numerador[iso2], denominador[iso2]
        try:
            valor_d = float(d["value"])
            if valor_d == 0:
                continue
            valor = float(n["value"]) / valor_d
        except (TypeError, ValueError):
            continue
        ano_n, ano_d = int(n["date"]), int(d["date"])
        ano_ref = min(ano_n, ano_d)
        doc = {
            "id": id_documento("bm", iso2, "PA.NUS.PPPC.RF"),
            "pais": iso2_para_nome[iso2],
            "iso2": iso2,
            "iso3": n.get("countryiso3code") or None,
            "indicador": "PA.NUS.PPPC.RF",
            "descricao": "Nível de preços (PPC do PIB ÷ câmbio oficial; 1,0 = nível dos EUA)",
            "unidade": "razão",
            "valor": round(valor, 4),
            "ano_referencia": ano_ref,
            "defasagem_anos": agora.year - ano_ref,
            "calculado": True,
            "metodo": (f"valor = PA.NUS.PPP (ano {ano_n}) / PA.NUS.FCRF (ano {ano_d}); "
                       "a série oficial deste indicador está arquivada (base 57) e não é mais servida pela API"),
        }
        doc.update(proveniencia(
            FONTE + " — calculado a partir de PA.NUS.PPP e PA.NUS.FCRF (a série oficial está arquivada)",
            montar_url(f"{BASE}/country/{iso2}/indicator/PA.NUS.PPP", {"format": "json", "date": str(ano_n)}),
            LICENCA,
            coletado_em=agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
        docs.append(doc)
    return docs


def coletar_com_relatorio(paises=PAISES, indicadores=INDICADORES, http=obter_json, agora=None):
    """
    Devolve (documentos, falhas). Um indicador que falhar (ex.: código inexistente ou
    arquivado pela fonte) é registrado em `falhas` e os demais continuam.
    """
    agora = agora or agora_utc()
    iso2_para_nome = {iso2: nome for nome, iso2 in paises.items()}
    docs, falhas, recentes_por_codigo = [], {}, {}
    variantes = _variantes(agora.year)
    for codigo, (descricao, unidade) in indicadores.items():
        try:
            linhas, atualizado, url, rotulo = _consultar(codigo, list(iso2_para_nome), agora.year, http, variantes)
            # a variante que funcionou passa a ser a primeira tentada nos próximos indicadores
            variantes.sort(key=lambda v: v[0] != rotulo)
            log.info("Indicador %s obtido (consulta: %s)", codigo, rotulo)
        except ErroColeta as e:
            falhas[codigo] = str(e)
            log.warning("Indicador %s ignorado: %s", codigo, e)
            continue
        recentes = _mais_recente_por_pais(linhas)
        recentes_por_codigo[codigo] = recentes
        for iso2, linha in recentes.items():
            if iso2 not in iso2_para_nome:   # ignora agregados/regiões
                continue
            ano = int(linha["date"])
            doc = {
                "id": id_documento("bm", iso2, codigo),
                "pais": iso2_para_nome[iso2],
                "iso2": iso2,
                "iso3": linha.get("countryiso3code") or None,
                "indicador": codigo,
                "descricao": descricao,
                "unidade": unidade,
                "valor": float(linha["value"]),
                "ano_referencia": ano,
                "defasagem_anos": agora.year - ano,
                "atualizado_na_fonte": atualizado,
            }
            doc.update(proveniencia(
                FONTE,
                montar_url(f"{BASE}/country/{iso2}/indicator/{codigo}",
                           {"format": "json", "date": f"{ano}"}),
                LICENCA,
                coletado_em=agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ))
            docs.append(doc)
        faltando = set(iso2_para_nome) - set(recentes)
        if faltando:
            log.warning("Sem valor recente para %s em %s", sorted(faltando), codigo)
    docs += _calcular_nivel_de_precos(recentes_por_codigo, iso2_para_nome, agora)
    return docs, falhas


def coletar(paises=PAISES, indicadores=INDICADORES, http=obter_json, agora=None):
    """Lista de documentos (um por país + indicador). Só levanta erro se NADA foi obtido."""
    docs, falhas = coletar_com_relatorio(paises, indicadores, http, agora)
    if not docs:
        raise ErroColeta("Nenhum indicador obtido do Banco Mundial: " + "; ".join(falhas.values()))
    return docs


def verificar_indicadores(indicadores=INDICADORES, http=obter_json):
    """Consulta o CATÁLOGO da fonte e diz se cada código de indicador existe. -> {codigo: (existe, texto)}"""
    resultado = {}
    for codigo in indicadores:
        try:
            _, linhas = _interpretar(http(f"{BASE}/indicator/{codigo}", {"format": "json"}), codigo)
            e = linhas[0] if linhas else {}
            fonte = e.get("source") or {}
            resultado[codigo] = (True, f"{e.get('name', '')}  [fonte {fonte.get('id')}: {fonte.get('value')}]")
        except ErroColeta as e:
            resultado[codigo] = (False, str(e))
    return resultado


def diagnosticar(http=obter_json, indicador="NY.GDP.PCAP.CD", ano=None):
    """
    Testa formas diferentes de consultar UM indicador e mostra o que a fonte respondeu.
    Serve para descobrir por que uma consulta é recusada. -> [(ok, rotulo, url, texto)]
    """
    ano = ano or agora_utc().year
    um = f"{BASE}/country/PT/indicator/{indicador}"
    seis = f"{BASE}/country/{';'.join(PAISES.values())}/indicator/{indicador}"
    testes = [
        ("catálogo do indicador", f"{BASE}/indicator/{indicador}", {"format": "json"}),
        ("1 país (PT), mrnev=1", um, {"format": "json", "mrnev": 1}),
        ("1 país (PT), mrv=5", um, {"format": "json", "mrv": 5}),
        ("1 país (PT), intervalo de datas", um, {"format": "json", "date": f"{ano - 10}:{ano}"}),
        ("1 país (PT), um único ano", um, {"format": "json", "date": str(ano - 2)}),
        ("1 país por ISO3 (PRT), mrnev=1", f"{BASE}/country/PRT/indicator/{indicador}", {"format": "json", "mrnev": 1}),
        ("6 países (;), mrnev=1", seis, {"format": "json", "mrnev": 1, "per_page": 200}),
        ("6 países (;), intervalo de datas", seis, {"format": "json", "date": f"{ano - 10}:{ano}", "per_page": 200}),
    ]
    saida = []
    for rotulo, url, params in testes:
        alvo = montar_url(url, params)
        try:
            _, linhas = _interpretar(http(url, params), url)
            exemplo = ""
            if linhas and isinstance(linhas[0], dict) and "country" in linhas[0]:
                l0 = linhas[0]
                exemplo = f"; ex.: {l0['country'].get('value')} {l0.get('date')} = {l0.get('value')}"
            saida.append((True, rotulo, alvo, f"{len(linhas)} linha(s){exemplo}"))
        except ErroColeta as e:
            saida.append((False, rotulo, alvo, str(e)[:220]))
    return saida


def testar_indicador(codigo, http=obter_json, pais="PT"):
    """Investiga UM indicador: existe no catálogo? de que base vem? a fonte serve os dados?"""
    entrada = _entrada_catalogo(codigo, http)
    fonte = (entrada or {}).get("source") or {}
    info = {"codigo": codigo, "no_catalogo": bool(entrada), "nome": (entrada or {}).get("name"),
            "fonte": f"{fonte.get('id')}: {fonte.get('value')}" if fonte else None, "testes": []}
    url = f"{BASE}/country/{pais}/indicator/{codigo}"
    formas = [("padrão (mrnev=1)", {"format": "json", "mrnev": 1})]
    if fonte.get("id"):
        formas.append((f"com source={fonte['id']}", {"format": "json", "mrnev": 1, "source": fonte["id"]}))
    for rotulo, params in formas:
        try:
            _, linhas = _interpretar(http(url, params), url)
            ex = f"{linhas[0]['country'].get('value')} {linhas[0].get('date')} = {linhas[0].get('value')}" if linhas else "sem linhas"
            info["testes"].append((True, rotulo, ex))
        except ErroColeta as e:
            info["testes"].append((False, rotulo, str(e)[:160]))
    return info


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Diagnóstico do Banco Mundial")
    ap.add_argument("--verificar", action="store_true", help="confere no catálogo se cada indicador existe")
    ap.add_argument("--diagnostico", action="store_true", help="testa formas de consulta e mostra as respostas")
    ap.add_argument("--testar", nargs="+", metavar="CODIGO", help="investiga indicadores (ex.: PA.NUS.PPP PA.NUS.PPPC.RF)")
    a = ap.parse_args()
    if not (a.verificar or a.diagnostico or a.testar):
        ap.error("use --verificar, --diagnostico e/ou --testar CODIGO...")
    for codigo in (a.testar or []):
        r = testar_indicador(codigo)
        print(f"== {codigo}: {'no catálogo' if r['no_catalogo'] else 'NÃO está no catálogo'} | {r['nome']} | base {r['fonte']}")
        for ok, rotulo, texto in r["testes"]:
            print(f"     {'OK  ' if ok else 'ERRO'} {rotulo}: {texto}")
    if a.verificar:
        print("== Catálogo: os indicadores existem? ==")
        for codigo, (ok, texto) in verificar_indicadores().items():
            print(f"  {'OK        ' if ok else 'NÃO EXISTE'}  {codigo:16s} {texto[:150]}")
    if a.diagnostico:
        print("== Formas de consulta (indicador NY.GDP.PCAP.CD) ==")
        for ok, rotulo, alvo, texto in diagnosticar():
            print(f"  {'OK ' if ok else 'ERRO'}  {rotulo}\n        {alvo}\n        -> {texto}")
