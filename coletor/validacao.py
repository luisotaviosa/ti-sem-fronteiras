# -*- coding: utf-8 -*-
"""
Portões de qualidade: nada vai para o Firestore sem passar por aqui.

  1. validar_*        -> esquema e faixas plausíveis (rejeita e explica o motivo)
  2. checar_variacao  -> salto grande em relação à coleta anterior fica PENDENTE
                         de revisão humana em vez de ser publicado.
"""
from datetime import datetime, timezone

MODALIDADES = {"Remoto", "Híbrido", "Presencial", "Não informada"}
SENIORIDADES = {"Júnior", "Pleno", "Sênior", "Não informada"}
PROVENIENCIA = ("fonte", "url_fonte", "coletado_em", "licenca")

# faixa plausível por indicador do Banco Mundial (mín, máx)
FAIXAS_INDICADOR = {
    "NY.GDP.PCAP.CD": (100, 300_000),
    "FP.CPI.TOTL.ZG": (-20, 200),
    "PA.NUS.PPPC.RF": (0.05, 5),   # calculado por nós (a série oficial está arquivada)
    "PA.NUS.PPP": (1e-4, 1e6),      # moeda local por US$ int'l: varia muito entre países
    "PA.NUS.FCRF": (1e-4, 1e6),
    "IT.NET.USER.ZS": (0, 100),
    "EUROSTAT.PLI_EU27_2020": (20, 300),  # índice EU27_2020=100; folga ampla para casos extremos
}


def _faltando(doc, campos):
    return [c for c in campos if doc.get(c) in (None, "")]


def validar_indicador(doc: dict) -> list:
    erros = [f"campo ausente: {c}" for c in _faltando(doc, ("id", "pais", "indicador", "valor", "ano_referencia") + PROVENIENCIA)]
    if erros:
        return erros
    if not isinstance(doc["valor"], (int, float)):
        erros.append("valor não numérico")
    else:
        faixa = FAIXAS_INDICADOR.get(doc["indicador"])
        if faixa and not (faixa[0] <= doc["valor"] <= faixa[1]):
            erros.append(f"valor {doc['valor']} fora da faixa plausível {faixa}")
    if not (1990 <= int(doc["ano_referencia"]) <= datetime.now(timezone.utc).year):
        erros.append("ano de referência fora do intervalo esperado")
    return erros


REGIOES_BR = {"Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"}
FAIXAS_INDICADOR_BR = {
    "IBGE.CALC.PIB_PER_CAPITA": (1_000, 500_000),   # Reais/ano; folga ampla entre regiões
    "IBGE.5436.5932": (100, 50_000),                # Reais/mês
}


def validar_regiao_br(doc: dict) -> list:
    """Para a coleção `brasil_regioes` — mesma ideia de validar_indicador, mas com
    `regiao` (uma das 5 Grandes Regiões) em vez de `pais`."""
    erros = [f"campo ausente: {c}" for c in _faltando(doc, ("id", "regiao", "indicador", "valor", "ano_referencia") + PROVENIENCIA)]
    if erros:
        return erros
    if doc["regiao"] not in REGIOES_BR:
        erros.append(f"regiao inválida: {doc['regiao']!r} (esperado uma de {REGIOES_BR})")
    if not isinstance(doc["valor"], (int, float)):
        erros.append("valor não numérico")
    else:
        faixa = FAIXAS_INDICADOR_BR.get(doc["indicador"])
        if faixa and not (faixa[0] <= doc["valor"] <= faixa[1]):
            erros.append(f"valor {doc['valor']} fora da faixa plausível {faixa}")
    if not (1990 <= int(doc["ano_referencia"]) <= datetime.now(timezone.utc).year):
        erros.append("ano de referência fora do intervalo esperado")
    return erros


def validar_custo_vida_estimado(doc: dict) -> list:
    campos = ("id", "custo_vida_mensal_usd", "custo_vida_mensal_usd_calculado",
             "custo_vida_mensal_usd_metodo", "custo_vida_mensal_usd_fonte")
    erros = [f"campo ausente: {c}" for c in _faltando(doc, campos)]
    if erros:
        return erros
    v = doc["custo_vida_mensal_usd"]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        erros.append("custo_vida_mensal_usd não numérico")
    elif not (100 <= v <= 20_000):
        erros.append(f"custo_vida_mensal_usd fora da faixa plausível: {v}")
    if doc["custo_vida_mensal_usd_calculado"] is not True:
        erros.append("custo_vida_mensal_usd_calculado deveria ser True")
    return erros


def validar_vaga(doc: dict) -> list:
    erros = [f"campo ausente: {c}" for c in _faltando(doc, ("id", "titulo", "empresa", "pais", "publicado_em", "expira_em") + PROVENIENCIA)]
    if doc.get("modalidade") not in MODALIDADES:
        erros.append(f"modalidade inválida: {doc.get('modalidade')!r}")
    if doc.get("senioridade") not in SENIORIDADES:
        erros.append(f"senioridade inválida: {doc.get('senioridade')!r}")
    if not isinstance(doc.get("stack"), list):
        erros.append("stack deve ser lista")
    if "description" in doc or "descricao_completa" in doc:
        erros.append("descrição completa não deve ser armazenada (direitos autorais/LGPD)")
    return erros


def separar_validos(docs, validador):
    """Devolve (validos, rejeitados) com rejeitados = [(doc, [motivos])]."""
    validos, rejeitados = [], []
    for d in docs:
        erros = validador(d)
        (rejeitados if erros else validos).append((d, erros) if erros else d)
    return validos, rejeitados


def checar_variacao(novos, anteriores: dict, campo="valor", limite=0.30):
    """
    Compara com a coleta anterior (dict id -> doc). Devolve (aprovados, pendentes):
    documentos cujo `campo` variou mais que `limite` (30%) vão para revisão.
    """
    aprovados, pendentes = [], []
    for d in novos:
        antigo = anteriores.get(d["id"])
        v_ant, v_novo = (antigo or {}).get(campo), d.get(campo)
        if isinstance(v_ant, (int, float)) and isinstance(v_novo, (int, float)) and v_ant:
            if abs(v_novo - v_ant) / abs(v_ant) > limite:
                pendentes.append({**d, "valor_anterior": v_ant})
                continue
        aprovados.append(d)
    return aprovados, pendentes
