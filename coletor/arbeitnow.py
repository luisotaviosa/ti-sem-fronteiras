# -*- coding: utf-8 -*-
"""
Coletor da Arbeitnow (Job Board API) -> coleção `vagas`.

API pública, sem chave: https://www.arbeitnow.com/api/job-board-api
Campos observados na resposta real (verificado em set/2026):

    data[]: slug, company_name, title, description (HTML), remote (bool),
            url, tags (categorias amplas, NÃO tecnologias), job_types,
            location (cidade), created_at (Unix, segundos)

Decisões de projeto (por causa do que a API realmente entrega):

  * A API não informa país, e as vagas NÃO são só da Alemanha (nos dados reais há
    muitas de Londres, Paris etc.). O país é DEDUZIDO do texto de `location`
    (nome de país explícito ou cidade conhecida); se não der, `pais = "Não identificado"`.
  * As `tags` são categorias ("Software Development", "HR"...). As tecnologias
    (Python, Linux, Active Directory...) são extraídas do TEXTO da descrição
    por um dicionário de sinônimos.
  * A descrição NÃO é gravada: além de direitos autorais, ela costuma trazer
    nome e telefone de recrutadores (dado pessoal, LGPD). Guardamos só
    metadados, a lista de tecnologias e o link para a vaga original.
  * Salário não é informado pela API: `salario_faixa_usd = None`.
  * Senioridade e modalidade, quando deduzidas por regra, vêm marcadas como
    `*_inferida = True`.
"""
import argparse
import html
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from .modelos import agora_utc, id_documento, para_iso, proveniencia
from .rede import ErroColeta, obter_json

log = logging.getLogger(__name__)

ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"
FONTE = "Arbeitnow (Job Board API)"
LICENCA = "Termos do Arbeitnow: guardar só metadados e link, com atribuição"
COLECAO = "vagas"
NAO_IDENTIFICADO = "Não identificado"

# nome de país escrito na localização (ex.: "Berlin, Germany")
_PAISES_EXPLICITOS = {
    "Alemanha": r"germany|deutschland", "Reino Unido": r"united kingdom|\buk\b|england|scotland|wales",
    "França": r"france", "Países Baixos": r"netherlands|nederland", "Irlanda": r"ireland",
    "Espanha": r"spain|españa|espana", "Portugal": r"portugal", "Áustria": r"austria|österreich",
    "Suíça": r"switzerland|schweiz|suisse", "Polônia": r"poland|polska", "Suécia": r"sweden|sverige",
    "Dinamarca": r"denmark|danmark", "Bélgica": r"belgium|belgië|belgique", "Itália": r"italy|italia",
    "Canadá": r"canada", "Emirados Árabes Unidos": r"united arab emirates|\buae\b",
}
# cidades conhecidas (lista curta e conservadora: o que não estiver aqui vira "Não identificado")
_CIDADES = {
    "Alemanha": ["berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf",
                 "dusseldorf", "dresden", "leipzig", "hannover", "hanover", "nuremberg", "nürnberg", "bonn", "potsdam",
                 "kassel", "ulm", "starnberg", "münster", "muenster", "minden", "bremen", "essen", "dortmund",
                 "karlsruhe", "mannheim", "heidelberg", "freiburg", "aachen", "augsburg", "regensburg", "darmstadt",
                 # confirmadas em dados reais (inspecionar, 21–22/09/2026): cidades alemãs menores
                 "braunschweig", "grasbrunn", "landsberg am lech", "hürth", "huerth", "westerstede",
                 "gilching", "leverkusen", "pinneberg", "kempten", "wolfsburg",
                 "bochum", "eilsleben", "dinslaken", "tholey", "mainz"],
    "Reino Unido": ["london", "manchester", "edinburgh", "glasgow", "birmingham", "bristol", "leeds", "cambridge", "oxford",
                    "marlow", "cardiff"],  # Marlow (Buckinghamshire) e Cardiff (capital do País de Gales)
    "França": ["paris", "lyon", "marseille", "toulouse", "nantes", "bordeaux", "lille"],
    "Países Baixos": ["amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague", "den haag", "delft"],
    "Irlanda": ["dublin", "cork", "galway", "limerick"],
    "Espanha": ["madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "málaga", "bilbao"],
    "Portugal": ["lisbon", "lisboa", "porto", "braga", "coimbra"],
    "Áustria": ["vienna", "wien", "graz", "linz", "salzburg", "innsbruck"],
    "Suíça": ["zurich", "zürich", "geneva", "genève", "basel", "bern", "lausanne"],
    "Polônia": ["warsaw", "krakow", "kraków", "wroclaw", "wrocław", "gdansk", "gdańsk", "poznan", "poznań"],
    "Suécia": ["stockholm", "gothenburg", "göteborg", "malmö", "malmo"],
    "Dinamarca": ["copenhagen", "københavn", "aarhus"],
    "Noruega": ["oslo", "bergen"], "Finlândia": ["helsinki", "espoo", "tampere"],
    "Bélgica": ["brussels", "bruxelles", "antwerp", "ghent"],
    "Itália": ["milan", "milano", "rome", "roma", "turin", "torino"],
    "Tchéquia": ["prague", "praha", "brno"], "Hungria": ["budapest"], "Romênia": ["bucharest", "cluj"],
    "Estônia": ["tallinn"], "Lituânia": ["vilnius"], "Letônia": ["riga"],
    "Canadá": ["toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary"],
    "Emirados Árabes Unidos": ["dubai", "abu dhabi"],
}
_RE_PAIS = [(pais, re.compile(pad, re.I)) for pais, pad in _PAISES_EXPLICITOS.items()]
_RE_CIDADE = [(pais, re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(c) for c in cidades), re.I))
              for pais, cidades in _CIDADES.items()]


def inferir_pais(localizacao: str) -> str:
    """País deduzido do texto de `location` (nome de país explícito, depois cidade conhecida)."""
    texto = localizacao or ""
    for pais, rx in _RE_PAIS:
        if rx.search(texto):
            return pais
    for pais, rx in _RE_CIDADE:
        if rx.search(texto):
            return pais
    return NAO_IDENTIFICADO
DIAS_VALIDADE = 30

# --- tecnologias do radar (mesmos nomes de data.py) -------------------------
TECNOLOGIAS = {
    "Python": [r"\bpython\b"],
    "JavaScript / TypeScript": [r"\bjavascript\b", r"\btypescript\b", r"\bnode\.?js\b"],
    "AWS": [r"\baws\b", r"\bamazon web services\b"],
    "SQL": [r"\bsql\b", r"\bpostgres(?:ql)?\b", r"\bmysql\b"],
    "Docker / Kubernetes": [r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b"],
    "Linux (Suporte/Admin)": [r"\blinux\b"],
    "Active Directory": [r"\bactive directory\b"],
    "Terraform": [r"\bterraform\b"],
}
_TEC_RE = {nome: [re.compile(p, re.I) for p in pads] for nome, pads in TECNOLOGIAS.items()}

# --- o que conta como vaga de TI -------------------------------------------
# Ajuste depois de rodar `python -m coletor.arbeitnow --tags` (mostra as tags reais).
TAGS_TI = {
    "Software Development", "System and Network Administration",
    "Information Systems", "Data", "Data Science", "Web Development", "DevOps",
    "IT", "Technology", "AI", "Platform Development", "Machine Learning", "Cloud",
}   # "Engineering" fica de fora de propósito: inclui engenharia mecânica, civil etc.
_TITULO_TI = re.compile(
    r"\b(software\w*|entwickler\w*|developer|devops|systemadministrator\w*|"
    r"netzwerk\w*|network\w*|cloud|daten\w*|security|informatik\w*|fachinformatiker\w*)\b", re.I)
_TITULO_IT_SIGLA = re.compile(r"\bIT\b")          # "IT-Systemadministrator" (só maiúsculas)

# --- senioridade e modalidade ----------------------------------------------
_SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head of|chief|teamleiter\w*|leiter\w*)\b", re.I)
_PLENO = re.compile(r"\b(mid[- ]?level|intermediate|medior)\b", re.I)
_JUNIOR = re.compile(r"\b(junior|jr\.?|trainee|werkstudent\w*|praktik\w*|ausbildung|entry[- ]level)\b", re.I)
# Sinais ESPECÍFICOS de trabalho híbrido. Menção solta a "remote" no texto NÃO conta
# (aparece em "remote-first culture", "remote friendly", etc. e inflava o híbrido).
_HOMEOFFICE = re.compile(
    r"\bhybrid\w*|hybrides?\s+arbeit\w*|home[\s-]?office|mobiles?\s+arbeit\w*|"
    r"\d\s*(?:days?|tage?)\s*(?:per|a|pro|in the|im)\s*(?:week|woche|office|büro)", re.I)


def limpar_html(texto: str) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).strip()


def extrair_tecnologias(texto: str) -> list:
    return [nome for nome, padroes in _TEC_RE.items() if any(p.search(texto) for p in padroes)]


def eh_vaga_ti(titulo: str, tags, tecnologias) -> bool:
    """TI se: tag de TI, OU palavra de TI no título, OU 2+ tecnologias no texto.
    (Uma única menção, ex.: "Linux von Vorteil" numa vaga de engenharia mecânica,
    não basta; prefere-se precisão a cobertura.)"""
    return bool(
        (set(tags or []) & TAGS_TI)
        or _TITULO_TI.search(titulo or "")
        or _TITULO_IT_SIGLA.search(titulo or "")
        or len(tecnologias or []) >= 2
    )


def inferir_senioridade(titulo: str) -> str:
    if _SENIOR.search(titulo or ""):
        return "Sênior"
    if _PLENO.search(titulo or ""):
        return "Pleno"
    if _JUNIOR.search(titulo or ""):
        return "Júnior"
    return "Não informada"


def inferir_modalidade(remoto: bool, texto: str):
    """Devolve (modalidade, foi_inferida)."""
    if remoto:
        return "Remoto", False
    if _HOMEOFFICE.search(texto or ""):
        return "Híbrido", True
    return "Não informada", False


def normalizar(item: dict, coletado_em: str, agora: datetime, dias_validade=DIAS_VALIDADE, so_ti=True):
    """Converte um item da API em documento; devolve None se não for aproveitável."""
    slug, titulo = item.get("slug"), item.get("title")
    if not slug or not titulo:
        return None
    try:
        publicado = datetime.fromtimestamp(int(item["created_at"]), timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    expira = publicado + timedelta(days=dias_validade)
    if expira < agora:
        return None                                   # vaga antiga demais

    texto = limpar_html(item.get("description"))      # usado só em memória
    tecnologias = extrair_tecnologias(f"{titulo} {texto}")
    tags = item.get("tags") or []
    if so_ti and not eh_vaga_ti(titulo, tags, tecnologias):
        return None

    pais = inferir_pais(item.get("location"))
    modalidade, mod_inf = inferir_modalidade(bool(item.get("remote")), texto)
    senioridade = inferir_senioridade(titulo)
    doc = {
        "id": id_documento("arbeitnow", slug),
        "titulo": titulo.strip(),
        "empresa": (item.get("company_name") or "").strip(),   # pode ser agência de recrutamento
        "pais": pais,
        "pais_inferido": pais != NAO_IDENTIFICADO,
        "localizacao": item.get("location"),
        "modalidade": modalidade,
        "modalidade_inferida": mod_inf,
        "senioridade": senioridade,
        "senioridade_inferida": senioridade != "Não informada",
        "stack": tecnologias,
        "salario_faixa_usd": None,
        "categorias_fonte": tags,
        "publicado_em": para_iso(publicado),
        "expira_em": para_iso(expira),
    }
    doc.update(proveniencia(FONTE, item.get("url") or ENDPOINT, LICENCA, coletado_em=coletado_em))
    return doc


def coletar(max_paginas=3, so_ti=True, http=obter_json, agora=None, dias_validade=DIAS_VALIDADE):
    """Percorre as páginas da API e devolve os documentos de vagas de TI."""
    agora = agora or agora_utc()
    coletado_em = para_iso(agora)
    docs, vistos = [], set()
    for pagina in range(1, max_paginas + 1):
        resposta = http(ENDPOINT, {"page": pagina})
        if not isinstance(resposta, dict) or "data" not in resposta:
            raise ErroColeta("Resposta inesperada da Arbeitnow (campo 'data' ausente)")
        itens = resposta["data"]
        if not itens:
            break
        for item in itens:
            doc = normalizar(item, coletado_em, agora, dias_validade, so_ti)
            if doc and doc["id"] not in vistos:
                vistos.add(doc["id"])
                docs.append(doc)
        if not (resposta.get("links") or {}).get("next"):   # sem próxima página
            break
    log.info("Arbeitnow: %d vagas de TI aproveitadas", len(docs))
    return docs


if __name__ == "__main__":          # utilitário: lista as tags reais de uma página
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Mostra a frequência das tags da Arbeitnow")
    ap.add_argument("--tags", action="store_true", required=True)
    ap.parse_args()
    dados = obter_json(ENDPOINT, {"page": 1})["data"]
    for tag, n in Counter(t for i in dados for t in i.get("tags", [])).most_common():
        print(f"{n:4d}  {tag}")
