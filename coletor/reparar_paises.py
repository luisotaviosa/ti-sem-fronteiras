# -*- coding: utf-8 -*-
"""
Reparo pontual da coleção `paises` no Firestore.

POR QUE ISTO EXISTE: se a coleta automática (`--publicar`) rodar antes de
`seed_firestore.py` ter criado os documentos-base dos países, o patch de
`custo_vida_mensal_usd` (ver derivados.calcular_custo_vida_estimado) cria
documentos com SÓ esse campo — sem região, coordenadas, idioma, visto etc. O
app então quebra com `KeyError: 'regiao'` ao tentar montar os filtros do
MundoDev, porque NENHUM documento da coleção tem esse campo.

POR QUE NÃO BASTA RODAR `seed_firestore.py` DE NOVO: ele grava com `.set()`
SEM `merge=True` — ou seja, sobrescreve o documento INTEIRO. Rodá-lo agora
apagaria o `custo_vida_mensal_usd` já calculado (voltaria ao valor de
demonstração do data.py) e, pior, TAMBÉM resseeda as coleções `vagas` e
`radar_tecnologias` por inteiro, o que reverteria os dados reais já
coletados (vagas da Arbeitnow, radar calculado) para os dados de
demonstração.

O QUE ESTE SCRIPT FAZ, EM VEZ DISSO: mescla (merge=True) só os campos de base
de cada país — região, coordenadas, idioma, visto, dificuldade do visto,
demanda em TI e o texto de resumo — a partir de `data.py`. Ele NUNCA toca em
`custo_vida_mensal_usd` nem em `salario_medio_ti_usd` (de propósito: esses
podem já ter sido atualizados pelo coletor automático), e NUNCA toca nas
coleções `vagas`, `radar_tecnologias` ou `trilhas_qualificacao`.

Uso:
    python -m coletor.reparar_paises                 # modo teste: grava em saida/paises.json
    python -m coletor.reparar_paises --publicar       # grava no Firestore de verdade
"""
import argparse
import logging

from .modelos import id_documento
from .publicar import Publicador

log = logging.getLogger(__name__)

# De propósito SEM custo_vida_mensal_usd nem salario_medio_ti_usd.
CAMPOS_BASE = ("pais", "regiao", "lat", "lon", "idioma", "visto",
              "dificuldade_visto", "demanda_ti", "resumo")


def montar_patches(paises: list) -> list:
    """Um patch por país, só com os campos de CAMPOS_BASE que existirem em cada registro."""
    patches = []
    for p in paises:
        patch = {c: p[c] for c in CAMPOS_BASE if c in p}
        patch["id"] = id_documento(p["pais"])
        patches.append(patch)
    return patches


def main(argv=None, paises=None) -> int:
    ap = argparse.ArgumentParser(
        description="Repara os campos de base da coleção 'paises' (região, idioma, visto, "
                    "coordenadas, resumo) sem tocar em custo_vida_mensal_usd/salario_medio_ti_usd."
    )
    ap.add_argument("--publicar", action="store_true", help="grava no Firestore (padrão: modo teste)")
    ap.add_argument("--saida", default="saida")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if paises is None:
        import data   # data.py fica na raiz do repositório do app, não dentro do pacote coletor
        paises = data.PAISES

    pub = Publicador(dry_run=not args.publicar, saida=args.saida)
    patches = montar_patches(paises)
    pub.gravar("paises", patches)
    log.info("Reparo concluído: %d país(es) processado(s) — campos tocados: %s",
             len(patches), ", ".join(CAMPOS_BASE))
    log.info("custo_vida_mensal_usd e salario_medio_ti_usd NÃO foram tocados por este script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
