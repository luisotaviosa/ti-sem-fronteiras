# -*- coding: utf-8 -*-
"""
Converte o serviceAccountKey.json (chave do Firebase) no bloco TOML que o
Streamlit Community Cloud pede em Settings -> Secrets.

Uso:
    python gerar_secrets_toml.py serviceAccountKey.json
    python gerar_secrets_toml.py serviceAccountKey.json > secrets_para_colar.toml

Não precisa de nenhuma biblioteca além da padrão do Python.
"""
import json
import sys


def escapar_toml(valor: str) -> str:
    """Escapa uma string para caber numa string TOML de uma linha só (aspas duplas).
    O JSON, depois de lido, já troca a sequência de texto \\n por uma quebra de
    linha de verdade dentro da private_key -- e uma quebra de linha real dentro
    de uma string TOML de aspas simples é inválida. Por isso aqui a ordem importa:
    escapar as barras invertidas ANTES de introduzir \\n novos, senão elas dobram."""
    return (valor.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n")
                 .replace("\r", "\\r")
                 .replace("\t", "\\t"))


def gerar_toml(caminho_json: str) -> str:
    with open(caminho_json, encoding="utf-8") as f:
        dados = json.load(f)
    linhas = ["[firebase]"]
    for chave, valor in dados.items():
        if isinstance(valor, str):
            linhas.append(f'{chave} = "{escapar_toml(valor)}"')
        elif isinstance(valor, (int, float, bool)):
            linhas.append(f"{chave} = {json.dumps(valor)}")
        else:
            linhas.append(f"{chave} = {json.dumps(valor)}")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python gerar_secrets_toml.py serviceAccountKey.json")
    print(gerar_toml(sys.argv[1]))
