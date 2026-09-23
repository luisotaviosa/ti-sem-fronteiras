# -*- coding: utf-8 -*-
"""
Curadoria humana: vistos e trilhas de qualificação.

Estes dois assuntos NÃO têm coleta automática (ver README_COLETOR.md — não existe
fonte confiável para "requisitos de visto" que dê para consultar por API). Em vez
disso, alguém da equipe preenche um arquivo JSON (ver os modelos em
`curadoria/vistos_modelo.json` e `curadoria/trilhas_modelo.json`) e este módulo
valida e publica, do mesmo jeito que os coletores automáticos — com proveniência,
sem pular o portão de qualidade.

Uso:
    python -m coletor.curadoria --colecao paises --arquivo meus_vistos.json
    python -m coletor.curadoria --colecao trilhas_qualificacao --arquivo minhas_trilhas.json --publicar

Cada entrada de VISTO é um PATCH no documento do país (mesmo mecanismo do
`derivados.calcular_custo_vida_estimado`): só os campos de visto, sem tocar em
região/idioma/custo de vida. Cada entrada de TRILHA é um documento completo da
coleção `trilhas_qualificacao`.
"""
import json
import logging
from datetime import date

from .modelos import id_documento
from .publicar import Publicador
from .validacao import _faltando

log = logging.getLogger(__name__)

COLECAO_PAISES = "paises"
COLECAO_TRILHAS = "trilhas_qualificacao"

CAMPOS_VISTO = ("pais", "visto", "dificuldade_visto", "verificado_por", "verificado_em", "fonte")
CAMPOS_TRILHA = ("area", "competencia", "certificacoes", "verificado_por", "verificado_em", "fonte")
DIFICULDADES_VALIDAS = {"Baixa", "Média", "Alta"}


def _validar_comum(doc: dict, campos: tuple) -> list:
    erros = [f"campo ausente: {c}" for c in _faltando(doc, campos)]
    if erros:
        return erros
    try:
        date.fromisoformat(str(doc["verificado_em"])[:10])
    except ValueError:
        erros.append(f"verificado_em não é uma data válida (AAAA-MM-DD): {doc['verificado_em']!r}")
    if not str(doc.get("verificado_por", "")).strip():
        erros.append("verificado_por vazio — diga quem checou a informação")
    return erros


def validar_visto(doc: dict) -> list:
    erros = _validar_comum(doc, CAMPOS_VISTO)
    if not erros and doc.get("dificuldade_visto") not in DIFICULDADES_VALIDAS:
        erros.append(f"dificuldade_visto deve ser uma de {DIFICULDADES_VALIDAS}, veio {doc.get('dificuldade_visto')!r}")
    return erros


def validar_trilha(doc: dict) -> list:
    erros = _validar_comum(doc, CAMPOS_TRILHA)
    if not erros and not isinstance(doc.get("certificacoes"), list):
        erros.append("certificacoes deve ser uma lista")
    return erros


def preparar_visto(entrada: dict) -> dict:
    """Adiciona proveniência e monta o patch (id = país, como os demais patches em `paises`)."""
    return {
        "id": id_documento(entrada["pais"]),
        "pais": entrada["pais"],
        "visto": entrada["visto"],
        "dificuldade_visto": entrada["dificuldade_visto"],
        "fonte": entrada.get("fonte", "Curadoria da equipe"),
        "url_fonte": entrada.get("url_fonte", ""),
        "verificado_em": entrada["verificado_em"],
        "verificado_por": entrada["verificado_por"],
    }


def preparar_trilha(entrada: dict) -> dict:
    return {
        "id": id_documento(entrada["area"]),
        "area": entrada["area"],
        "competencia": entrada["competencia"],
        "certificacoes": entrada["certificacoes"],
        "fonte": entrada.get("fonte", "Curadoria da equipe"),
        "url_fonte": entrada.get("url_fonte", ""),
        "verificado_em": entrada["verificado_em"],
        "verificado_por": entrada["verificado_por"],
    }


def processar(colecao: str, entradas: list, pub: Publicador) -> dict:
    """Valida e publica; devolve um resumo (o mesmo formato dos outros `executar_*`)."""
    if colecao == COLECAO_PAISES:
        preparar, validar = preparar_visto, validar_visto
    elif colecao == COLECAO_TRILHAS:
        preparar, validar = preparar_trilha, validar_trilha
    else:
        raise ValueError(f"coleção não suportada pela curadoria: {colecao!r} (use {COLECAO_PAISES} ou {COLECAO_TRILHAS})")

    validos, rejeitados = [], []
    for entrada in entradas:
        doc = preparar(entrada)
        erros = validar(doc)
        (rejeitados if erros else validos).append((doc, erros) if erros else doc)
    for doc, erros in rejeitados:
        log.warning("Entrada de curadoria rejeitada (%s): %s", doc.get("id"), "; ".join(erros))
    pub.gravar(colecao, validos)
    return {"recebidos": len(entradas), "publicados": len(validos), "rejeitados": len(rejeitados)}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Publica curadoria humana (vistos ou trilhas)")
    ap.add_argument("--colecao", required=True, choices=[COLECAO_PAISES, COLECAO_TRILHAS])
    ap.add_argument("--arquivo", required=True, help="JSON com uma lista de entradas (ver curadoria/*_modelo.json)")
    ap.add_argument("--publicar", action="store_true", help="grava no Firestore (padrão: modo teste)")
    ap.add_argument("--saida", default="saida")
    args = ap.parse_args()

    entradas = json.loads(open(args.arquivo, encoding="utf-8").read())
    pub = Publicador(dry_run=not args.publicar, saida=args.saida)
    resumo = processar(args.colecao, entradas, pub)
    log.info("Curadoria (%s): %s", args.colecao, resumo)
