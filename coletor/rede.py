# -*- coding: utf-8 -*-
"""
Acesso HTTP com boas práticas: tempo limite, novas tentativas com espera
crescente e identificação clara do projeto no User-Agent.

Os coletores recebem a função de rede por parâmetro (injeção de dependência),
o que permite testar tudo offline com respostas de exemplo.
"""
import os
import time
from urllib.parse import urlencode

USER_AGENT = os.environ.get(
    "COLETOR_USER_AGENT",
    "TI-Sem-Fronteiras/0.1 (projeto academico; IFS Campus Socorro)",
)


class ErroColeta(Exception):
    """Falha ao obter ou interpretar dados de uma fonte."""


def montar_url(url: str, params: dict = None) -> str:
    """
    URL final com os parâmetros. Mantém ":" ";" e "," literais: o `requests` os
    converteria em %3A %3B %2C, e APIs como a do Banco Mundial (intervalo
    "2016:2026") podem não decodificá-los.

    `doseq=True` é essencial quando um valor do dict é uma LISTA (ex.: vários
    países num só parâmetro `geo`): sem isso, o Python codifica a lista inteira
    como uma única string literal ("geo=['PT', 'DE']"), que a fonte não reconhece
    como nenhum código válido — a consulta não dá erro, só não bate com nada e
    volta vazia. Foi exatamente isso que aconteceu na consulta ao Eurostat com
    vários países de uma vez (confirmado em 22/09/2026: um país só funcionava,
    vários juntos voltavam 0 resultados sem nenhum erro).
    """
    if not params:
        return url
    return f"{url}?{urlencode(params, doseq=True, safe=':;,')}"


def obter_json(url: str, params: dict = None, tentativas: int = 3,
               espera: float = 2.0, timeout: int = 30):
    import requests  # importado aqui para os testes rodarem sem rede/dependência

    ultimo = None
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(
                montar_url(url, params), timeout=timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if r.status_code == 429 or r.status_code >= 500:
                raise ErroColeta(f"HTTP {r.status_code} em {url}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ErroColeta, ValueError) as e:
            ultimo = e
            if i < tentativas:
                time.sleep(espera * 2 ** (i - 1))
    raise ErroColeta(f"Falha após {tentativas} tentativas em {url}: {ultimo}")
