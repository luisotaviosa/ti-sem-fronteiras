# -*- coding: utf-8 -*-
"""
Resumo dos dados coletados (pasta `saida/`), para conferir a qualidade antes de publicar.

    python -m coletor.inspecionar            # lê saida/
    python -m coletor.inspecionar minha_pasta
"""
import json
import sys
from collections import Counter
from pathlib import Path

from .arbeitnow import NAO_IDENTIFICADO


def _carregar(pasta, nome):
    arq = Path(pasta) / f"{nome}.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []


def _top(contador, n=8, total=None):
    for chave, c in contador.most_common(n):
        pct = f" ({100 * c / total:.0f}%)" if total else ""
        print(f"    {c:4d}{pct}  {chave}")


def main(argv=None):
    pasta = (argv if argv is not None else sys.argv[1:] or ["saida"])[0]
    vagas, radar, ind = (_carregar(pasta, n) for n in ("vagas", "radar_tecnologias", "indicadores_pais"))

    print(f"=== VAGAS ({len(vagas)}) ===")
    if vagas:
        n = len(vagas)
        com = sum(1 for v in vagas if v.get("stack"))
        print(f"  com alguma tecnologia identificada: {com} ({100 * com / n:.0f}%)")
        print("  empresas mais frequentes (atenção a agências que dominam a amostra):")
        _top(Counter(v.get("empresa") for v in vagas), 8, n)
        print("  países (deduzidos da localização):")
        _top(Counter(v.get("pais") for v in vagas), 10, n)
        print("  modalidade:", dict(Counter(v.get("modalidade") for v in vagas)))
        print("  senioridade:", dict(Counter(v.get("senioridade") for v in vagas)))
        print("  cidades:")
        _top(Counter(v.get("localizacao") for v in vagas), 6, n)
        print("  categorias de origem (tags da Arbeitnow):")
        _top(Counter(t for v in vagas for t in v.get("categorias_fonte", [])), 10)
        print("  10 primeiras vagas:")
        for v in vagas[:10]:
            print(f"    - {v.get('titulo')} | {v.get('empresa')} | {', '.join(v.get('stack', [])) or '-'}")
        nao_id = Counter(v.get("localizacao") for v in vagas if v.get("pais") == NAO_IDENTIFICADO)
        if nao_id:
            print(f"\n  localizações NÃO identificadas ({sum(nao_id.values())} vaga(s); envie esta lista para eu ampliar o mapeamento):")
            for loc, c in nao_id.most_common():
                print(f"    {c:3d}  {loc!r}")

    print(f"\n=== RADAR ({len(radar)}) ===")
    for d in sorted(radar, key=lambda d: -d.get("demanda", 0)):
        print(f"  {d['tecnologia']:26s} demanda {d['demanda']:3d}   vagas {d['vagas_com_mencao']:4d}   ({d.get('categoria')})")
    if radar:
        r = radar[0]
        print(f"  amostra: {r.get('n_amostra')} vagas; {r.get('empresas_distintas')} empresas distintas; "
              f"a maior empresa responde por {100 * (r.get('concentracao_maior_empresa') or 0):.0f}% das vagas")

    print(f"\n=== INDICADORES DOS PAÍSES ({len(ind)}) ===")
    por = {}
    for d in ind:
        por.setdefault(d["pais"], {})[d["indicador"]] = f"{d['valor']:.4g} ({d['ano_referencia']})"
    for pais, vals in sorted(por.items()):
        print(f"  {pais}: " + "; ".join(f"{k}={v}" for k, v in vals.items()))
    if not (vagas or radar or ind):
        print(f"\n(nada encontrado em {pasta}/; rode antes: python -m coletor.executar --fonte todas)")


if __name__ == "__main__":
    main()
