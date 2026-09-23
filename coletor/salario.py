# -*- coding: utf-8 -*-
"""
Salário médio em TI — Adzuna (endpoint `history`, salário médio anunciado por mês).

STATUS: precisa de credencial (gratuita) e de uma etapa de verificação — ver abaixo.
Endpoint e formato confirmados na documentação oficial (21/09/2026):
  https://developer.adzuna.com/docs/histogram (irmão do `history`, mesmo formato)
  https://developer.adzuna.com/overview
Resposta real documentada para o endpoint `history`:
    {"month": {"2013-09": 20000.00, "2013-10": 20450.00, ...}}
(chave = mês ISO "AAAA-MM", valor = salário médio anunciado naquele mês, SEM
símbolo de moeda — ver a incerteza sobre moeda logo abaixo.)

DUAS COISAS PRECISAM SER CONFIRMADAS ANTES DE USAR EM PRODUÇÃO (não dá para
verificar sem uma chave de API e acesso de rede, que este ambiente não tem):

  1. CREDENCIAL: crie uma gratuita em https://developer.adzuna.com/signup
     (poucos minutos, sem cartão de crédito). Depois:
         export ADZUNA_APP_ID=...
         export ADZUNA_APP_KEY=...

  2. COBERTURA DE PAÍS: nem todo país do protótipo é necessariamente um mercado
     do Adzuna. Rode ANTES de coletar:
         python -m coletor.salario --verificar
     Isso testa os 6 países e diz quais respondem com dado de verdade.
     PAISES_CANDIDATOS abaixo é um PALPITE FUNDAMENTADO (com base em mercados que o
     Adzuna tradicionalmente cobre), não uma lista confirmada — trate os países
     marcados como "não confirmado" com desconfiança até o --verificar confirmar.

  3. MOEDA: a documentação não deixa explícito em qual moeda o valor volta — o mais
     provável é a moeda local de cada mercado (EUR na Alemanha/Espanha/Portugal/
     Irlanda, CAD no Canadá, AED nos Emirados), a julgar por como o Adzuna anuncia
     vagas localmente, mas isso também precisa ser CONFIRMADO (ver --verificar, que
     imprime o valor bruto para conferência manual — compare com o que uma vaga
     real no site do Adzuna daquele país mostra). Por isso `coletar()` não converte
     para USD sozinho: devolve o valor bruto e deixa marcado
     `moeda_confirmada: False` até alguém confirmar.
"""
import logging

from .modelos import agora_utc, id_documento, proveniencia
from .rede import ErroColeta, obter_json

log = logging.getLogger(__name__)

BASE = "https://api.adzuna.com/v1/api"
FONTE = "Adzuna (salário médio anunciado, endpoint history)"
LICENCA = "Termos do Adzuna (developer.adzuna.com) — confirmar limites de uso/redistribuição antes de publicar"
COLECAO = "indicadores_pais"

WHAT_TI_PADRAO = "software developer"   # termo de busca; pode ser refinado por país/vaga depois

# Palpite fundamentado, NÃO CONFIRMADO — rode --verificar antes de confiar nisto.
PAISES_CANDIDATOS = {
    "Alemanha": "de", "Canadá": "ca", "Espanha": "es",
    "Portugal": "pt", "Irlanda": "ie", "Emirados Árabes Unidos": "ae",
}


def _url_historia(codigo_pais: str) -> str:
    return f"{BASE}/jobs/{codigo_pais}/history"


def verificar_cobertura(app_id: str, app_key: str, paises=PAISES_CANDIDATOS,
                        what=WHAT_TI_PADRAO, http=obter_json) -> dict:
    """
    Testa cada país candidato e diz se o Adzuna respondeu com dado de verdade.
    -> {pais: (ok, detalhe)}. NUNCA levanta erro: um país recusado vira (False, motivo).
    """
    resultado = {}
    for pais, codigo in paises.items():
        params = {"app_id": app_id, "app_key": app_key, "what": what,
                  "months": 1, "content-type": "application/json"}
        try:
            resp = http(_url_historia(codigo), params)
        except ErroColeta as e:
            resultado[pais] = (False, str(e)[:200])
            continue
        mes = (resp or {}).get("month") or {}
        if mes:
            (ultimo_mes, valor), = list(mes.items())[-1:]
            resultado[pais] = (True, f"{ultimo_mes} = {valor} (moeda não confirmada — ver docstring do módulo)")
        else:
            resultado[pais] = (False, "resposta sem nenhum mês de dado (país pode não ser mercado do Adzuna, "
                                      "ou não há vagas para essa busca)")
    return resultado


def coletar(app_id: str, app_key: str, paises=PAISES_CANDIDATOS, what=WHAT_TI_PADRAO,
           http=obter_json, agora=None) -> tuple:
    """
    Coleta o salário médio anunciado (último mês disponível) por país.
    Devolve (documentos, falhas) — um país sem dado vira entrada em `falhas`, os
    demais continuam (mesmo padrão do banco_mundial.coletar_com_relatorio).

    Cada documento traz `moeda_confirmada: False` e `valor_bruto_sem_conversao:
    True` até a moeda ser confirmada manualmente (ver docstring do módulo) — não
    finge ser USD sem essa confirmação.
    """
    agora = agora or agora_utc()
    coletado_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs, falhas = [], {}
    for pais, codigo in paises.items():
        params = {"app_id": app_id, "app_key": app_key, "what": what,
                  "months": 1, "content-type": "application/json"}
        url = _url_historia(codigo)
        try:
            resp = http(url, params)
        except ErroColeta as e:
            falhas[pais] = str(e)
            continue
        mes = (resp or {}).get("month") or {}
        if not mes:
            falhas[pais] = "sem dado (país pode não ser mercado do Adzuna, ou 0 vagas para essa busca)"
            continue
        ultimo_mes = sorted(mes)[-1]
        valor = mes[ultimo_mes]
        doc = {
            "id": id_documento("adzuna", pais),
            "pais": pais,
            "indicador": "ADZUNA.SALARIO_TI_HISTORICO",
            "descricao": f'Salário médio anunciado em vagas de TI (busca: "{what}")',
            "unidade": "moeda local do anúncio, por ano (NÃO confirmada — ver módulo)",
            "valor": float(valor),
            "ano_referencia": int(ultimo_mes[:4]),
            "mes_referencia": ultimo_mes,
            "moeda_confirmada": False,
        }
        doc.update(proveniencia(FONTE, f"{url}?what={what}&months=1", LICENCA, coletado_em=coletado_em))
        docs.append(doc)
    return docs, falhas


if __name__ == "__main__":
    import argparse
    import os as _os
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Verificação/coleta de salário em TI (Adzuna)")
    ap.add_argument("--verificar", action="store_true", help="testa a cobertura de país (não grava nada)")
    ap.add_argument("--what", default=WHAT_TI_PADRAO)
    args = ap.parse_args()
    app_id, app_key = _os.environ.get("ADZUNA_APP_ID"), _os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise SystemExit(
            "Defina ADZUNA_APP_ID e ADZUNA_APP_KEY (gratuito: https://developer.adzuna.com/signup)."
        )
    if not args.verificar:
        ap.error("por enquanto use --verificar (a coleta de verdade entra em executar.py depois de confirmar a cobertura)")
    print(f"== Verificando cobertura Adzuna (busca: \"{args.what}\") ==")
    for pais, (ok, detalhe) in verificar_cobertura(app_id, app_key, what=args.what).items():
        print(f"  {'OK ' if ok else 'FALTA'}  {pais:28s} {detalhe}")
    print("\nSó use no coletor os países marcados OK. Para os demais, sem outra fonte, o "
          "campo salario_medio_ti_usd continua com o valor de demonstração do data.py.")
