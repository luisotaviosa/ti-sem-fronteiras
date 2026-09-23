# -*- coding: utf-8 -*-
"""
Utilitários comuns aos coletores do TI Sem Fronteiras.

Todo documento publicado no Firestore carrega os campos de PROVENIÊNCIA:

    fonte, url_fonte, coletado_em, verificado_em, licenca, n_amostra

Assim a interface pode mostrar "fonte e data" e qualquer número pode ser
auditado até a origem.
"""
import re
from datetime import datetime, timezone


def agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def para_iso(dt: datetime) -> str:
    """Datas sempre em ISO 8601 UTC com 'Z' (ordenam corretamente como texto)."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def agora_iso() -> str:
    return para_iso(agora_utc())


def id_documento(*partes) -> str:
    """
    ID estável e válido para o Firestore.

    O Firestore NÃO aceita "/" em IDs de documento (ele vira separador de
    caminho). Por isso "JavaScript / TypeScript" vira "javascript_-_typescript".
    Também evita IDs reservados ("." , ".." e "__algo__").
    """
    texto = "_".join(str(p) for p in partes if p is not None).strip().lower()
    texto = re.sub(r"\s+", "_", texto)
    texto = re.sub(r"[/\\?#\[\]]+", "-", texto)
    if re.fullmatch(r"\.+|__.*__", texto or "."):
        texto = "id_" + texto
    return texto[:1000] or "sem_id"


def proveniencia(fonte: str, url_fonte: str, licenca: str, *, coletado_em: str = None,
                 verificado_em: str = None, n_amostra: int = None) -> dict:
    return {
        "fonte": fonte,
        "url_fonte": url_fonte,
        "coletado_em": coletado_em or agora_iso(),
        "verificado_em": verificado_em,   # preenchido só quando um humano revisa (ex.: vistos)
        "licenca": licenca,
        "n_amostra": n_amostra,           # nº de observações por trás do valor (quando se aplica)
    }
