# -*- coding: utf-8 -*-
"""
Orquestra a coleta: coletar -> validar -> checar variação -> publicar.

Uso:
    python -m coletor.executar --fonte todas                # TESTE: grava JSON em saida/
    python -m coletor.executar --fonte arbeitnow --publicar # grava no Firestore
    python -m coletor.executar --fonte banco_mundial --saida minha_pasta

Se uma fonte falhar, NADA é apagado: o app continua servindo o último conjunto
válido (e, na pior hipótese, o `data.py` de demonstração). O código de saída
diferente de zero faz o GitHub Actions marcar a execução como falha.
"""
import argparse
import logging
import sys

from . import arbeitnow, banco_mundial, custo_vida, derivados
from .modelos import agora_iso
from .publicar import Publicador
from .rede import ErroColeta, obter_json
from .validacao import (checar_variacao, separar_validos, validar_custo_vida_estimado,
                       validar_indicador, validar_vaga)

log = logging.getLogger("coletor")

# Limite de vagas por empresa no cálculo do radar (None = sem limite). Decida olhando
# `python -m coletor.inspecionar`: se uma agência domina a amostra, use por exemplo 5.
RADAR_MAX_POR_EMPRESA = None


def _relatorio_rejeicoes(nome, rejeitados):
    for doc, motivos in rejeitados:
        log.warning("%s rejeitado (%s): %s", nome, doc.get("id"), "; ".join(motivos))


def executar_banco_mundial(pub: Publicador, http=obter_json) -> dict:
    docs, falhas = banco_mundial.coletar_com_relatorio(http=http)
    if not docs:
        raise ErroColeta("Nenhum indicador obtido do Banco Mundial: " + "; ".join(falhas.values()))
    validos, rejeitados = separar_validos(docs, validar_indicador)
    _relatorio_rejeicoes("indicador", rejeitados)
    aprovados, pendentes = checar_variacao(validos, pub.ler(banco_mundial.COLECAO))
    for p in pendentes:
        log.warning("Variação > 30%% em %s (%s -> %s): pendente de revisão",
                    p["id"], p["valor_anterior"], p["valor"])
    pub.gravar(banco_mundial.COLECAO, aprovados)
    pub.gravar("_pendentes_revisao", pendentes)

    # custo de vida estimado (baseline BLS × nível de preços): ver derivados.py
    patches_custo_vida = derivados.calcular_custo_vida_estimado(aprovados)
    validos_cv, rejeitados_cv = separar_validos(patches_custo_vida, validar_custo_vida_estimado)
    _relatorio_rejeicoes("custo de vida estimado", rejeitados_cv)
    pub.gravar(derivados.COLECAO_PAISES, validos_cv)

    resumo = {"coletados": len(docs), "publicados": len(aprovados),
              "rejeitados": len(rejeitados), "pendentes": len(pendentes),
              "custo_vida_estimado_publicado": len(validos_cv)}
    if falhas:
        resumo["indicadores_falhos"] = falhas
    return resumo


def executar_custo_vida(pub: Publicador, http=obter_json) -> dict:
    """Eurostat: nível de preços (consumo das famílias), só Portugal/Alemanha/Irlanda/Espanha."""
    docs = custo_vida.coletar(http=http)
    validos, rejeitados = separar_validos(docs, validar_indicador)
    _relatorio_rejeicoes("indicador (Eurostat)", rejeitados)
    aprovados, pendentes = checar_variacao(validos, pub.ler(custo_vida.COLECAO))
    for p in pendentes:
        log.warning("Variação > 30%% em %s (%s -> %s): pendente de revisão",
                    p["id"], p["valor_anterior"], p["valor"])
    pub.gravar(custo_vida.COLECAO, aprovados)
    pub.gravar("_pendentes_revisao", pendentes)
    return {"coletados": len(docs), "publicados": len(aprovados),
            "rejeitados": len(rejeitados), "pendentes": len(pendentes)}


def executar_arbeitnow(pub: Publicador, http=obter_json) -> dict:
    docs = arbeitnow.coletar(http=http)
    validos, rejeitados = separar_validos(docs, validar_vaga)
    _relatorio_rejeicoes("vaga", rejeitados)
    pub.gravar(arbeitnow.COLECAO, validos)
    removidas = pub.expirar(arbeitnow.COLECAO)        # só depois de coleta bem-sucedida
    radar = derivados.calcular_radar(pub_lista(pub, arbeitnow.COLECAO, validos),
                                    max_por_empresa=RADAR_MAX_POR_EMPRESA)
    pub.gravar(derivados.COLECAO, radar)
    return {"coletados": len(docs), "publicados": len(validos), "rejeitados": len(rejeitados),
            "expiradas": removidas, "radar_publicado": bool(radar)}


def pub_lista(pub: Publicador, colecao: str, recentes: list) -> list:
    """Base do radar = vagas vigentes (coletadas agora + ainda válidas das coletas anteriores)."""
    vigentes = pub.ler(colecao)
    vigentes.update({d["id"]: d for d in recentes})
    return list(vigentes.values())


FONTES = {"banco_mundial": executar_banco_mundial, "custo_vida": executar_custo_vida,
         "arbeitnow": executar_arbeitnow}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Coleta automática do TI Sem Fronteiras")
    ap.add_argument("--fonte", choices=[*FONTES, "todas"], default="todas")
    ap.add_argument("--publicar", action="store_true", help="grava no Firestore (padrão: modo teste)")
    ap.add_argument("--saida", default="saida", help="pasta dos JSON do modo teste")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pub = Publicador(dry_run=not args.publicar, saida=args.saida)
    log.info("Modo: %s", "PUBLICAÇÃO NO FIRESTORE" if args.publicar else "teste (JSON local)")
    try:
        pub.verificar_credencial()
    except RuntimeError as e:
        log.error("%s", e)
        log.error("Para testar SEM Firebase, rode sem --publicar (grava JSON em %s/).", args.saida)
        return 2

    falhas = 0
    for nome in (FONTES if args.fonte == "todas" else [args.fonte]):
        try:
            resumo = FONTES[nome](pub)
            status = "parcial" if resumo.get("indicadores_falhos") else "ok"
            pub.registrar_execucao(nome, {"status": status, **resumo})
            log.info("%s concluída (%s): %s", nome, status, resumo)
        except (ErroColeta, RuntimeError) as e:
            falhas += 1
            log.error("%s FALHOU: %s (dados anteriores mantidos)", nome, e)
            try:
                pub.registrar_execucao(nome, {"status": "falha", "erro": str(e)})
            except Exception as e2:      # o registro é acessório: nunca esconde o erro original
                log.warning("Não foi possível registrar a falha: %s", e2)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
