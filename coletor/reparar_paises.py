# -*- coding: utf-8 -*-
"""
Reparo pontual da coleção `paises` no Firestore.

POR QUE ISTO EXISTE: se a coleta automática (`--publicar`) rodar antes de
`seed_firestore.py` ter criado os documentos-base dos países, o patch de
`custo_vida_mensal_usd` (ver derivados.calcular_custo_vida_estimado) cria
documentos com SÓ esse campo — sem região, coordenadas, idioma, visto etc. O
app então quebra com `KeyError: 'regiao'` ao tentar montar os filtros do
MundoDev, porque NENHUM documento da coleção tem esse campo.

INCIDENTE 2 (23/09/2026): a primeira versão deste script excluía
`custo_vida_mensal_usd` E `salario_medio_ti_usd` por completo, achando que os
dois já vinham de alguma coleta automática. Mas `salario_medio_ti_usd` nunca
teve fonte nenhuma (o Adzuna ainda está só em teste, não integrado) — excluí-lo
sempre deixou o campo ausente para sempre, e o app quebrou de novo, agora com
`KeyError: 'salario_medio_ti_usd'`. Corrigido: em vez de excluir os dois campos
por completo, o reparo agora lê o que já existe no Firestore e só preenche cada
um deles se ainda estiver faltando — nunca sobrescreve um valor que uma coleta
automática já publicou, mas também nunca deixa um campo ausente para sempre só
porque ele *poderia*, um dia, ter uma fonte automática.

POR QUE NÃO BASTA RODAR `seed_firestore.py` DE NOVO: ele grava com `.set()`
SEM `merge=True` — ou seja, sobrescreve o documento INTEIRO. Rodá-lo agora
apagaria o `custo_vida_mensal_usd` já calculado (voltaria ao valor de
demonstração do data.py) e, pior, TAMBÉM resseeda as coleções `vagas` e
`radar_tecnologias` por inteiro, o que reverteria os dados reais já
coletados (vagas da Arbeitnow, radar calculado) para os dados de
demonstração.

O QUE ESTE SCRIPT FAZ, EM VEZ DISSO: mescla (merge=True) os campos de base de
cada país (região, coordenadas, idioma, visto, dificuldade do visto, demanda em
TI e o texto de resumo) — esses sempre são atualizados a partir de `data.py`,
pois não têm outra fonte. `custo_vida_mensal_usd` e `salario_medio_ti_usd` só
são preenchidos se ainda estiverem ausentes no documento (ver
CAMPOS_SO_SE_AUSENTES) — nunca sobrescrevem um valor já calculado/coletado.
Este script NUNCA toca nas coleções `vagas`, `radar_tecnologias` ou
`trilhas_qualificacao`.

Uso:
    python -m coletor.reparar_paises                 # modo teste: grava em saida/paises.json
    python -m coletor.reparar_paises --publicar       # grava no Firestore de verdade
"""
import argparse
import logging

from .modelos import id_documento
from .publicar import Publicador

log = logging.getLogger(__name__)

# Campos que este reparo SEMPRE atualiza a partir do data.py: não têm nenhuma
# fonte automática (região, coordenadas, idioma, visto e o texto de resumo não
# mudam com a coleta), então sobrescrever com o valor do data.py é sempre seguro.
CAMPOS_BASE_SEMPRE = ("pais", "regiao", "lat", "lon", "idioma", "visto",
                     "dificuldade_visto", "demanda_ti", "resumo")

# Campos que este reparo só preenche se ainda estiverem AUSENTES no documento.
# custo_vida_mensal_usd já tem uma fonte automática melhor (Banco Mundial +
# Eurostat, calculado em derivados.py); salario_medio_ti_usd ainda não tem
# nenhuma (Adzuna está em teste, não integrado) — mas os DOIS seguem a mesma
# regra: nunca pisar num valor que uma coleta automática já publicou, só evitar
# que o app quebre quando o campo nunca existiu (foi exatamente isto que causou
# o incidente de 23/09/2026: excluir os dois campos por completo deixou
# salario_medio_ti_usd ausente para sempre, sem nenhuma fonte para preenchê-lo).
CAMPOS_SO_SE_AUSENTES = ("custo_vida_mensal_usd", "salario_medio_ti_usd")


def montar_patches(paises: list, existentes: dict = None) -> list:
    """
    Um patch por país. CAMPOS_BASE_SEMPRE entram sempre; os de
    CAMPOS_SO_SE_AUSENTES só entram se o documento em `existentes` (já
    publicado no Firestore) ainda não tiver esse campo.
    `existentes`: {id_do_pais: documento_atual} — normalmente vem de
    `Publicador.ler("paises")`. Passe {} (ou None) para tratar tudo como ausente
    (útil num Firestore/pasta de teste totalmente vazios).
    """
    existentes = existentes or {}
    patches = []
    for p in paises:
        pid = id_documento(p["pais"])
        doc_existente = existentes.get(pid, {})
        patch = {c: p[c] for c in CAMPOS_BASE_SEMPRE if c in p}
        for c in CAMPOS_SO_SE_AUSENTES:
            if c in p and c not in doc_existente:
                patch[c] = p[c]
        patch["id"] = pid
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
    existentes = pub.ler("paises")
    patches = montar_patches(paises, existentes)
    pub.gravar("paises", patches)
    log.info("Reparo concluído: %d país(es) processado(s).", len(patches))
    log.info("Sempre atualizados: %s", ", ".join(CAMPOS_BASE_SEMPRE))
    log.info("Preenchidos só onde faltavam (nunca sobrescritos se já existiam): %s",
             ", ".join(CAMPOS_SO_SE_AUSENTES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
