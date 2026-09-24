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

# Códigos SIDRA de valor ausente/não aplicável (documentados pelo IBGE) — nunca
# um número de verdade, então nunca devem virar `float(...)`.
CODIGOS_AUSENTE = {"..", "...", "-", "X", ""}


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


def descobrir_metadados(agregado_id: str, http=obter_json) -> dict:
    """
    `GET /agregados/{id}/metadados`: variáveis disponíveis, níveis territoriais
    e classificações do agregado escolhido. Rode depois de achar o ID certo
    com `descobrir_agregados`, para confirmar que ele tem o nível N2 e achar o
    `variavel_id` certo (ex.: "PIB per capita", não "PIB total").
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


def coletar(agregado_id: str, variavel_id: str, periodo: str = "-1",
           regioes=REGIOES, http=obter_json, agora=None) -> list:
    """
    Coleta `variavel_id` do agregado `agregado_id` para as 5 Grandes Regiões,
    no período pedido (`-1` = mais recente disponível, convenção do SIDRA).
    Documentos vão para a coleção `brasil_regioes` (própria — ver COLECAO),
    não para `paises`: uma região do Brasil não tem visto, nem vagas
    internacionais, então usa um esquema de campos diferente (ver app.py,
    seção "Brasil por dentro").
    """
    agora = agora or agora_utc()
    url = f"{BASE}/agregados/{agregado_id}/periodos/{periodo}/variaveis/{variavel_id}"
    resp = http(url, {"localidades": "N2[all]"})
    if not isinstance(resp, list) or not resp:
        raise ErroColeta(f"Resposta inesperada do IBGE: {str(resp)[:200]}")

    bloco = resp[0]
    descricao = bloco.get("variavel", variavel_id)
    unidade = bloco.get("unidade", "")
    series = []
    for resultado in bloco.get("resultados", []):
        series.extend(resultado.get("series", []))

    nome_para_regiao = {v: k for k, v in regioes.items()}   # não usado hoje (id vem em "id"), mantido p/ clareza
    coletado_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = []
    for serie in series:
        localidade = serie.get("localidade", {})
        nome_regiao = localidade.get("nome")
        if nome_regiao not in regioes:
            continue   # ex.: viria "Brasil" (nível N1) se a consulta incluísse; ignora, foco é N2
        pontos = serie.get("serie", {})
        if not pontos:
            continue
        ano_mais_recente = sorted(pontos)[-1]
        valor = _valor_numerico(pontos[ano_mais_recente])
        if valor is None:
            log.warning("Sem valor numérico para %s em %s (ano %s): %r",
                       nome_regiao, agregado_id, ano_mais_recente, pontos[ano_mais_recente])
            continue
        doc = {
            "id": id_documento(nome_regiao),
            "regiao": nome_regiao,
            "indicador": f"IBGE.{agregado_id}.{variavel_id}",
            "descricao": descricao,
            "unidade": unidade,
            "valor": valor,
            "ano_referencia": int(ano_mais_recente) if ano_mais_recente.isdigit() else None,
        }
        doc.update(proveniencia(
            FONTE, f"{url}?localidades=N2[{localidade.get('id')}]", LICENCA, coletado_em=coletado_em,
        ))
        docs.append(doc)
    return docs


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Descoberta do IBGE/SIDRA para as 5 Grandes Regiões")
    ap.add_argument("--descobrir", metavar="TERMO", help='ex.: --descobrir "PIB per capita"')
    ap.add_argument("--metadados", metavar="AGREGADO_ID", help="mostra variáveis/níveis de um agregado")
    args = ap.parse_args()
    if not (args.descobrir or args.metadados):
        ap.error("use --descobrir TERMO ou --metadados AGREGADO_ID")

    if args.descobrir:
        achados = descobrir_agregados(args.descobrir)
        print(f"\n== {len(achados)} agregado(s) com \"{args.descobrir}\" no nome ==")
        for a in achados[:40]:
            print(f"  id={a['agregado_id']:<8} {a['agregado_nome']}  [{a['pesquisa']}]")
        if len(achados) > 40:
            print(f"  ... e mais {len(achados) - 40} (refine o termo de busca)")
        print("\nEscolha o agregado_id certo e rode --metadados <id> para ver as variáveis.")

    if args.metadados:
        meta = descobrir_metadados(args.metadados)
        print(f"\n== Agregado {args.metadados}: {meta.get('nome')} ==")
        print("Níveis territoriais:", meta.get("nivelTerritorial"))
        print("Variáveis:")
        for v in meta.get("variaveis", []):
            print(f"  id={v.get('id'):<6} {v.get('nome')}  (unidade: {v.get('unidade')})")
        print("\nMe envie esta saída inteira (junto com a do --descobrir) para eu finalizar coletar().")
