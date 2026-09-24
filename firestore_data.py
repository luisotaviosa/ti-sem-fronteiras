# -*- coding: utf-8 -*-
"""
Camada de acesso a dados do TI Sem Fronteiras.

Tenta ler do Firestore (Firebase). Se não houver credencial configurada
(ainda não conectou o Firebase, ou está rodando localmente sem o arquivo
de chave), cai automaticamente para os dados mockados de data.py — assim
o app NUNCA quebra, mesmo antes da configuração do Firebase estar pronta.

Ordem de busca da credencial:
  1. st.secrets["firebase"]   -> usado no Streamlit Community Cloud (deploy online)
  2. ./serviceAccountKey.json -> usado no seu computador (teste local)
  3. Nenhuma encontrada       -> usa data.py (modo demonstração offline)
"""

import json
import os

import streamlit as st

import data  # fallback local

_db = None
_modo_atual = None  # "firestore" ou "local" — usado para mostrar na sidebar


def _secrets_firebase():
    """Lê a credencial de st.secrets["firebase"], se existir.

    Nas versões recentes do Streamlit, consultar st.secrets SEM haver um arquivo
    .streamlit/secrets.toml levanta uma exceção (em vez de responder "não existe").
    Aqui essa situação é tratada como "sem credencial nos secrets", para que o
    fluxo siga para a próxima opção (serviceAccountKey.json) ou para o modo local.
    """
    try:
        if "firebase" in st.secrets:
            return dict(st.secrets["firebase"])
    except Exception:
        pass
    return None


def _tentar_conectar():
    """Inicializa o Firebase Admin SDK uma única vez. Retorna o client ou None."""
    global _db, _modo_atual

    if _db is not None:
        return _db
    if _modo_atual == "local":
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        _modo_atual = "local"
        return None

    try:
        if not firebase_admin._apps:
            cred = None

            # 1) Credencial via secrets (deploy no Streamlit Community Cloud)
            cred_info = _secrets_firebase()
            if cred_info:
                cred = credentials.Certificate(cred_info)

            # 2) Credencial via arquivo local (teste na sua máquina)
            elif os.path.exists("serviceAccountKey.json"):
                cred = credentials.Certificate("serviceAccountKey.json")

            if cred is None:
                _modo_atual = "local"
                return None

            firebase_admin.initialize_app(cred)

        _db = firestore.client()
        _modo_atual = "firestore"
        return _db

    except Exception as e:
        st.sidebar.warning(f"Não foi possível conectar ao Firebase: {e}")
        _modo_atual = "local"
        return None


def modo_dados() -> str:
    """Retorna 'firestore' ou 'local', para exibir na interface."""
    _tentar_conectar()
    return _modo_atual or "local"


def _carregar_colecao(nome_colecao: str, fallback: list) -> list:
    db = _tentar_conectar()
    if db is None:
        return fallback
    try:
        docs = db.collection(nome_colecao).stream()
        registros = [doc.to_dict() for doc in docs]
        return registros if registros else fallback
    except Exception as e:
        st.sidebar.warning(f"Erro ao ler '{nome_colecao}' do Firestore: {e}")
        return fallback


def carregar_paises() -> list:
    return _carregar_colecao("paises", data.PAISES)


def carregar_vagas() -> list:
    return _carregar_colecao("vagas", data.VAGAS)


def carregar_radar_tecnologias() -> list:
    return _carregar_colecao("radar_tecnologias", data.RADAR_TECNOLOGIAS)


def carregar_trilhas_qualificacao() -> list:
    return _carregar_colecao("trilhas_qualificacao", data.TRILHAS_QUALIFICACAO)


def carregar_indicadores_pais() -> list:
    """Indicadores do Banco Mundial (coletor/banco_mundial.py): PIB per capita, inflação,
    câmbio, acesso à Internet e o nível de preços (este último calculado por nós, já que
    a série oficial do indicador está arquivada — ver coletor/banco_mundial.py).

    Sem fallback local: data.py não tem esses dados, então em modo demonstração esta
    coleção volta vazia e a interface deve tratar isso como "ainda não coletado",
    não como erro.
    """
    return _carregar_colecao("indicadores_pais", [])


def carregar_brasil_regioes() -> list:
    """PIB per capita e renda média por Grande Região do Brasil (coletor/ibge.py, IBGE/SIDRA).

    Coleção PRÓPRIA, separada de `paises`: uma região do Brasil não tem visto, nem
    vagas internacionais, então tem um conjunto de campos diferente (ver app.py,
    seção "Brasil por dentro"). Sem fallback local — volta vazia em modo demonstração.
    """
    return _carregar_colecao("brasil_regioes", [])
