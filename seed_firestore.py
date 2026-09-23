# -*- coding: utf-8 -*-
"""
Script para popular o Firestore com os dados iniciais do projeto.

Rode este script UMA VEZ, depois de colocar o arquivo serviceAccountKey.json
na mesma pasta:

    python3 seed_firestore.py

Ele cria as coleções: paises, vagas, radar_tecnologias, trilhas_qualificacao.
"""

import os
import re
import sys

import firebase_admin
from firebase_admin import credentials, firestore

import data

CHAVE = "serviceAccountKey.json"


def id_seguro(valor) -> str:
    """ID válido no Firestore: o "/" é separador de caminho e não pode aparecer no ID."""
    texto = re.sub(r"\s+", "_", str(valor).strip().lower())
    return re.sub(r"[/\\?#\[\]]+", "-", texto)


def main():
    if not os.path.exists(CHAVE):
        print(f"❌ Não encontrei '{CHAVE}' nesta pasta.")
        print("   Baixe a chave em: Firebase Console > Configurações do projeto")
        print("   > Contas de serviço > Gerar nova chave privada.")
        sys.exit(1)

    cred = credentials.Certificate(CHAVE)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    colecoes = {
        "paises": ("pais", data.PAISES),
        "vagas": ("titulo", data.VAGAS),
        "radar_tecnologias": ("tecnologia", data.RADAR_TECNOLOGIAS),
        "trilhas_qualificacao": ("area", data.TRILHAS_QUALIFICACAO),
    }

    for nome_colecao, (campo_id, registros) in colecoes.items():
        for registro in registros:
            doc_id = id_seguro(registro[campo_id])
            db.collection(nome_colecao).document(doc_id).set(registro)
        print(f"✅ Coleção '{nome_colecao}': {len(registros)} documento(s) enviado(s).")

    print("\n🎉 Firestore populado com sucesso! Agora rode: streamlit run app.py")


if __name__ == "__main__":
    main()
