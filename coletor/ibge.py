# -*- coding: utf-8 -*-
"""
Brasil por dentro — IBGE/SIDRA, nível "Grandes Regiões" (N2): Norte, Nordeste,
Sudeste, Sul, Centro-Oeste.

STATUS: ETAPA DE DESCOBERTA. A API do IBGE (Agregados v3 / SIDRA) é oficial,
gratuita e sem chave — confirmada em 24/09/2026:
  https://servicodados.ibge.gov.br/api/v3/agregados/{id}/periodos/{periodo}/variaveis/{variavel}?localidades={nivel}[all]
Formato de resposta confirmado (fiel ao documentado, ex. de referência real):
    [{"id": "9324", "variavel": "...", "unidade": "...",
      "resultados": [{"series": [{"localidade": {"id": "3", "nome": "Sudeste"},
                                   "serie": {"2023": "45678.90"}}]}]}]

IMPORTANTE — o que NÃO existe: pesquisei antes de programar (24/09/2026) e
confirmei que o IBGE NÃO publica uma série oficial de "custo de vida
comparável entre regiões". IPCA/INPC medem VARIAÇÃO de preços no tempo em
cada região (índices temporais bilaterais), não NÍVEL de preços comparável
entre regiões — usá-los para comparar "quanto custa viver no Nordeste vs. no
Sudeste" seria um erro de método (o mesmo tipo de erro que o índice arquivado
do Banco Mundial nos ensinou a evitar). Um índice de custo de vida comparável
entre regiões existe só em pesquisa acadêmica (ex.: Menezes & Azzoni, método
CPD sobre microdados da POF), não como série oficial consultável por API. Por
isso este coletor NÃO tenta gerar um "custo de vida" para as regiões — só os
dois indicadores abaixo, que são genuinamente comparáveis entre regiões:

  - PIB per capita por Grande Região (Sistema de Contas Regionais do IBGE)
  - Rendimento médio real por Grande Região (PNAD Contínua)

Os IDs exatos dos agregados SIDRA (números arbitrários, não adivinháveis)
ainda precisam ser confirmados. Rode:
    python -m coletor.ibge --descobrir "PIB per capita"
    python -m coletor.ibge --descobrir "rendimento médio"
e me envie a saída — eu escolho os IDs certos e os parâmetros padrão de
`coletar()` a partir disso (mesmo processo que já demos com o Eurostat).

Escopo: só as 5 Grandes Regiões (nível N2), não os 27 estados — decisão
tomada com o usuário em 24/09/2026, para começar pelo recorte mais simples.
"""
import logging

from .modelos import agora_utc, id_documento, proveniencia
from .rede import ErroColeta, obter_json

log = logging.getLogger(__name__)

BASE = "https://servicodados.ibge.gov.br/api/v3"
FONTE = "IBGE (Sistema IBGE de Recuperação Automática — SIDRA)"
LICENCA = "Dados abertos do IBGE (uso livre, com citação da fonte)"
COLECAO = "brasil_regioes"   # coleção PRÓPRIA, separada de "paises" (ver justificativa no app.py)

# Códigos oficiais e estáveis das 5 Grandes Regiões (nível territorial N2 do IBGE) —
# não mudam; não é algo que precise de "descoberta" como um ID de agregado.
REGIOES = {"Norte": "1", "Nordeste": "2", "Sudeste": "3", "Sul": "4", "Centro-Oeste": "5"}

# --- Indicadores confirmados por descoberta (rodadas de 24/09/2026) -----------------
#
# PIB per capita por Grande Região: NÃO EXISTE pronto no SIDRA. A única tabela
# oficial de "PIB per capita" (agregado 6784, "Contas Nacionais Anuais") só tem
# nível nacional (N1) — sem quebra regional. Por isso é CALCULADO aqui, do
# mesmo jeito que o nível de preços do Banco Mundial (PA.NUS.PPPC.RF): dois
# componentes ativos, em vez de uma série pronta que não existe.
PIB_AGREGADO_ID, PIB_VARIAVEL_ID = "5938", "37"                 # PIB total, Mil Reais, por Grande Região
POPULACAO_AGREGADO_ID, POPULACAO_VARIAVEL_ID = "6579", "9324"   # População residente estimada, Pessoas

# Rendimento médio mensal real, trabalho principal, habitualmente recebido —
# agregado 5436, PNAD Contínua trimestral. Tem uma classificação cruzada por
# Sexo (id 2); "Total" = categoria 6794 (confirmado via --metadados 5436).
RENDIMENTO_AGREGADO_ID, RENDIMENTO_VARIAVEL_ID = "5436", "5932"
RENDIMENTO_CLASSIFICACAO = {"2": "6794"}   # Sexo = Total


def _classificacao_para_query(classificacao: dict) -> str:
    """{'2': '6794'} -> 'classificacao=2[6794]' (formato oficial: id[cat1,cat2]|id2[cat3])."""
    return "|".join(f"{cid}[{cat}]" for cid, cat in classificacao.items())


def _serie_por_regiao(agregado_id: str, variavel_id: str, periodo: str = "-6",
                      classificacao: dict = None, regioes=REGIOES, http=obter_json) -> tuple:
    """
    Busca `variavel_id` do `agregado_id` para as 5 Grandes Regiões, nos últimos
    `periodo` períodos (padrão: 6, para dar folga a séries com defasagens
    diferentes). Devolve ({regiao: {ano: valor}}, descricao_da_variavel, unidade).
    """
    url = f"{BASE}/agregados/{agregado_id}/periodos/{periodo}/variaveis/{variavel_id}"
    params = {"localidades": "N2[all]"}
    if classificacao:
        params["classificacao"] = _classificacao_para_query(classificacao)
    resp = http(url, params)
    if not isinstance(resp, list) or not resp:
        raise ErroColeta(f"Resposta inesperada do IBGE (agregado {agregado_id}): {str(resp)[:200]}")

    bloco = resp[0]
    series = []
    for resultado in bloco.get("resultados", []):
        series.extend(resultado.get("series", []))

    por_regiao = {}
    for serie in series:
        nome_regiao = serie.get("localidade", {}).get("nome")
        if nome_regiao not in regioes:
            continue
        anos = {}
        for ano_txt, valor_bruto in (serie.get("serie") or {}).items():
            valor = _valor_numerico(valor_bruto)
            if valor is not None and ano_txt.isdigit():
                anos[int(ano_txt)] = valor
        if anos:
            por_regiao[nome_regiao] = anos
    return por_regiao, bloco.get("variavel", variavel_id), bloco.get("unidade", "")


def coletar_pib_per_capita(regioes=REGIOES, http=obter_json, agora=None) -> list:
    """
    PIB per capita por Grande Região = PIB total ÷ população residente
    estimada, no ANO MAIS RECENTE em que as DUAS séries têm dado para aquela
    região (elas têm defasagens de divulgação diferentes; nunca se divide
    anos diferentes sem isso ficar registrado no método).
    """
    agora = agora or agora_utc()
    pib_por_regiao, pib_desc, pib_unidade = _serie_por_regiao(
        PIB_AGREGADO_ID, PIB_VARIAVEL_ID, regioes=regioes, http=http)
    pop_por_regiao, pop_desc, pop_unidade = _serie_por_regiao(
        POPULACAO_AGREGADO_ID, POPULACAO_VARIAVEL_ID, regioes=regioes, http=http)

    coletado_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = []
    for regiao in regioes:
        anos_pib, anos_pop = pib_por_regiao.get(regiao, {}), pop_por_regiao.get(regiao, {})
        comuns = set(anos_pib) & set(anos_pop)
        if not comuns:
            log.warning("PIB per capita: sem ano em comum entre PIB e população para %s", regiao)
            continue
        ano = max(comuns)
        pib_mil_reais, populacao_pessoas = anos_pib[ano], anos_pop[ano]
        if not populacao_pessoas:
            continue
        valor = (pib_mil_reais * 1000) / populacao_pessoas   # Mil Reais -> Reais, ÷ pessoas
        doc = {
            "id": id_documento(regiao, "pib_per_capita"),
            "regiao": regiao,
            "indicador": "IBGE.CALC.PIB_PER_CAPITA",
            "descricao": "PIB per capita (calculado)",
            "unidade": "Reais",
            "valor": round(valor, 2),
            "ano_referencia": ano,
            "calculado": True,
            "metodo": (f"{pib_desc} (agregado {PIB_AGREGADO_ID}, variável {PIB_VARIAVEL_ID}, {pib_unidade}) "
                      f"÷ {pop_desc} (agregado {POPULACAO_AGREGADO_ID}, variável {POPULACAO_VARIAVEL_ID}, "
                      f"{pop_unidade}), ano {ano}. Não existe tabela oficial de PIB per capita por Grande "
                      f"Região no SIDRA — a única tabela per capita (agregado 6784) só tem nível nacional."),
        }
        doc.update(proveniencia(
            FONTE, f"{BASE}/agregados/{PIB_AGREGADO_ID}/periodos/{ano}/variaveis/{PIB_VARIAVEL_ID}",
            LICENCA, coletado_em=coletado_em,
        ))
        docs.append(doc)
    return docs


def coletar_rendimento_medio(regioes=REGIOES, http=obter_json, agora=None) -> list:
    """Rendimento médio mensal real (trabalho principal, habitual), total (ambos os sexos), por Grande Região."""
    agora = agora or agora_utc()
    por_regiao, descricao, unidade = _serie_por_regiao(
        RENDIMENTO_AGREGADO_ID, RENDIMENTO_VARIAVEL_ID, periodo="-1",
        classificacao=RENDIMENTO_CLASSIFICACAO, regioes=regioes, http=http)
    coletado_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = []
    for regiao, anos in por_regiao.items():
        ano = max(anos)
        doc = {
            "id": id_documento(regiao, "rendimento_medio"),
            "regiao": regiao,
            "indicador": "IBGE.5436.5932",
            "descricao": descricao,
            "unidade": unidade,
            "valor": anos[ano],
            "ano_referencia": ano,
        }
        doc.update(proveniencia(
            FONTE, f"{BASE}/agregados/{RENDIMENTO_AGREGADO_ID}/periodos/{ano}/variaveis/{RENDIMENTO_VARIAVEL_ID}",
            LICENCA, coletado_em=coletado_em,
        ))
        docs.append(doc)
    return docs


def coletar(regioes=REGIOES, http=obter_json, agora=None) -> list:
    """Os dois indicadores confirmados: PIB per capita (calculado) + rendimento médio."""
    return (coletar_pib_per_capita(regioes, http=http, agora=agora)
           + coletar_rendimento_medio(regioes, http=http, agora=agora))

# Códigos SIDRA de valor ausente/não aplicável (documentados pelo IBGE) — nunca
# um número de verdade, então nunca devem virar `float(...)`.
CODIGOS_AUSENTE = {"..", "...", "-", "X", ""}


def listar_pesquisas(http=obter_json) -> list:
    """
    Lista os nomes ÚNICOS do nível mais alto de agrupamento do catálogo
    (`GET /agregados`) — sem filtrar por nada. Existe porque `--pesquisa` deu
    ZERO resultados para "Contas Regionais" e "PNAD Contínua" (24/09/2026): a
    suposição de que esses nomes apareceriam literalmente ali estava errada.
    Em vez de arriscar mais um palpite de string, isto mostra o vocabulário
    real que o IBGE usa nesse campo, para escolher o termo certo olhando a
    lista de verdade.
    """
    resp = http(f"{BASE}/agregados", {})
    if not isinstance(resp, list):
        raise ErroColeta(f"Resposta inesperada do catálogo de agregados: {str(resp)[:200]}")
    nomes = sorted({p.get("nome", "") for p in resp if p.get("nome")})
    return nomes


def descobrir_agregados(termo: str, http=obter_json) -> list:
    """
    Busca no catálogo INTEIRO de agregados do SIDRA (`GET /agregados`) por um
    termo no nome da pesquisa ou do agregado (client-side: a API não documenta
    busca textual server-side). Devolve uma lista de candidatos, cada um com o
    `agregado_id` (número arbitrário, é o que falta confirmar).
    """
    resp = http(f"{BASE}/agregados", {})
    if not isinstance(resp, list):
        raise ErroColeta(f"Resposta inesperada do catálogo de agregados: {str(resp)[:200]}")
    alvo = termo.lower()
    achados = []
    for pesquisa in resp:
        for ag in pesquisa.get("agregados", []):
            texto = f"{pesquisa.get('nome', '')} {ag.get('nome', '')}".lower()
            if alvo in texto:
                achados.append({"pesquisa": pesquisa.get("nome"), "agregado_id": ag.get("id"),
                                "agregado_nome": ag.get("nome")})
    return achados


def descobrir_por_pesquisa(termo: str, http=obter_json) -> list:
    """
    Lista TODOS os agregados de pesquisas cujo NOME DA PESQUISA contém `termo`
    (ignora o nome do agregado/indicador na comparação). Útil quando o nome do
    indicador que você procura não aparece do jeito esperado no título (ex.:
    "PIB per capita" às vezes só aparece por extenso, "Produto Interno Bruto
    per capita", ou junto de outra sigla) — mas o nome do LEVANTAMENTO é
    conhecido (ex.: "Contas Regionais", "PNAD Contínua"). A lista costuma ser
    bem mais curta e limpa que uma busca pelo nome do indicador.
    """
    resp = http(f"{BASE}/agregados", {})
    if not isinstance(resp, list):
        raise ErroColeta(f"Resposta inesperada do catálogo de agregados: {str(resp)[:200]}")
    alvo = termo.lower()
    achados = []
    for pesquisa in resp:
        if alvo in pesquisa.get("nome", "").lower():
            for ag in pesquisa.get("agregados", []):
                achados.append({"pesquisa": pesquisa.get("nome"), "agregado_id": ag.get("id"),
                                "agregado_nome": ag.get("nome")})
    return achados


def descobrir_metadados(agregado_id: str, http=obter_json) -> dict:
    """
    `GET /agregados/{id}/metadados`: variáveis, níveis territoriais e
    CLASSIFICAÇÕES (dimensões cruzadas, tipo "sexo" ou "cor ou raça" — cada
    uma com suas categorias, entre elas geralmente um código "Total"). Rode
    depois de achar o ID certo com `descobrir_agregados`/`descobrir_por_pesquisa`,
    para achar o `variavel_id` certo e, se houver classificações, o código de
    "Total" (senão a consulta pode vir dividida por sexo/idade/etc. sem você
    pedir, ou a API pode até recusar por faltar escolher uma categoria).
    """
    resp = http(f"{BASE}/agregados/{agregado_id}/metadados", {})
    if not isinstance(resp, dict):
        raise ErroColeta(f"Resposta inesperada dos metadados do agregado {agregado_id}: {str(resp)[:200]}")
    return resp


def _valor_numerico(bruto):
    """Converte um valor do SIDRA para float, ou None se for um código de ausência."""
    texto = str(bruto).strip()
    if texto in CODIGOS_AUSENTE:
        return None
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Descoberta do IBGE/SIDRA para as 5 Grandes Regiões")
    ap.add_argument("--listar-pesquisas", action="store_true",
                    help="lista o vocabulário real da 1ª chave do catálogo (use se --pesquisa der 0 resultados)")
    ap.add_argument("--descobrir", metavar="TERMO", help='busca pelo nome do indicador, ex.: --descobrir "PIB per capita"')
    ap.add_argument("--pesquisa", metavar="TERMO", help='busca por nome do LEVANTAMENTO, ex.: --pesquisa "Contas Regionais"')
    ap.add_argument("--metadados", metavar="AGREGADO_ID", help="mostra variáveis/níveis de um agregado")
    args = ap.parse_args()
    if not (args.descobrir or args.pesquisa or args.metadados or args.listar_pesquisas):
        ap.error("use --listar-pesquisas, --descobrir TERMO, --pesquisa TERMO ou --metadados AGREGADO_ID")

    if args.listar_pesquisas:
        nomes = listar_pesquisas()
        print(f"\n== {len(nomes)} categoria(s) únicas no catálogo ==")
        for n in nomes:
            print(f"  {n}")
        print("\nProcure aqui o nome que parecer certo (ex.: algo com 'Regionais', 'PNAD', "
              "'Rendimento', 'Trabalho') e rode --pesquisa com esse texto exato.")

    if args.descobrir:
        achados = descobrir_agregados(args.descobrir)
        print(f"\n== {len(achados)} agregado(s) com \"{args.descobrir}\" no nome ==")
        for a in achados[:40]:
            print(f"  id={a['agregado_id']:<8} {a['agregado_nome']}  [{a['pesquisa']}]")
        if len(achados) > 40:
            print(f"  ... e mais {len(achados) - 40} (refine o termo, ou tente --pesquisa "
                  "com o nome do levantamento, ex.: \"Contas Regionais\", \"PNAD Contínua\")")
        print("\nEscolha o agregado_id certo e rode --metadados <id> para ver as variáveis.")

    if args.pesquisa:
        achados = descobrir_por_pesquisa(args.pesquisa)
        print(f"\n== {len(achados)} agregado(s) em pesquisas com \"{args.pesquisa}\" no nome ==")
        for a in achados[:60]:
            print(f"  id={a['agregado_id']:<8} {a['agregado_nome']}  [{a['pesquisa']}]")
        if len(achados) > 60:
            print(f"  ... e mais {len(achados) - 60}")
        print("\nEscolha o agregado_id certo e rode --metadados <id> para ver as variáveis.")

    if args.metadados:
        meta = descobrir_metadados(args.metadados)
        print(f"\n== Agregado {args.metadados}: {meta.get('nome')} ==")
        print("Níveis territoriais:", meta.get("nivelTerritorial"))
        print("\nVariáveis:")
        for v in meta.get("variaveis", []):
            print(f"  id={v.get('id'):<6} {v.get('nome')}  (unidade: {v.get('unidade')})")
        classificacoes = meta.get("classificacoes") or []
        if classificacoes:
            print(f"\n⚠️  Este agregado tem {len(classificacoes)} classificação(ões) — dimensões "
                  "cruzadas que talvez seja preciso fixar num valor (ex.: 'Total') na consulta:")
            for c in classificacoes:
                print(f"\n  Classificação id={c.get('id')}: {c.get('nome')}")
                for cat in c.get("categorias", []):
                    marca = "  <-- provável 'Total'" if "total" in str(cat.get("nome", "")).lower() else ""
                    print(f"    categoria id={cat.get('id'):<8} {cat.get('nome')}{marca}")
        else:
            print("\n(sem classificações cruzadas — a consulta não precisa fixar nenhuma categoria extra)")
        print("\nMe envie esta saída inteira (junto com a do --descobrir/--pesquisa) para eu finalizar coletar().")
