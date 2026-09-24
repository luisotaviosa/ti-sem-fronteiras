# -*- coding: utf-8 -*-
"""
Testes OFFLINE do coletor IBGE (Brasil por Grandes Regiões). O exemplo de
resposta é fiel ao formato documentado (ver ibge.py) — nunca testado contra o
IBGE ao vivo nesta sessão (sem acesso de rede aqui).
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coletor import ibge
from coletor.rede import ErroColeta

AGORA = datetime(2026, 9, 24, tzinfo=timezone.utc)


def _resposta_pib(por_regiao):
    """{"Norte": "12345.6", ...} -> formato real do SIDRA (data[0].resultados[0].series)."""
    series = [{"localidade": {"id": ibge.REGIOES[nome], "nome": nome}, "serie": {"2023": valor}}
              for nome, valor in por_regiao.items()]
    return [{"id": "9321", "variavel": "PIB per capita, a preços correntes",
            "unidade": "Reais", "resultados": [{"series": series}]}]


class TestDescobrirAgregados(unittest.TestCase):
    def test_filtra_por_termo_no_nome_da_pesquisa_ou_do_agregado(self):
        catalogo = [
            {"id": "49", "nome": "Contas Regionais", "agregados": [
                {"id": "9321", "nome": "PIB a preços correntes e PIB per capita, a preços correntes"},
                {"id": "9322", "nome": "Valor adicionado bruto a preços correntes"},
            ]},
            {"id": "37", "nome": "IPCA", "agregados": [
                {"id": "1705", "nome": "IPCA-15 - Variação mensal"},
            ]},
        ]
        r = ibge.descobrir_agregados("per capita", http=lambda u, p=None: catalogo)
        self.assertEqual([a["agregado_id"] for a in r], ["9321"])

    def test_resposta_que_nao_e_lista_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            ibge.descobrir_agregados("x", http=lambda u, p=None: {"erro": "não é uma lista"})


class TestDescobrirMetadados(unittest.TestCase):
    def test_devolve_variaveis_e_niveis(self):
        resp = {"nome": "PIB per capita", "nivelTerritorial": {"Administrativo": ["N2", "N3"]},
               "variaveis": [{"id": "9321", "nome": "PIB per capita", "unidade": "Reais"}]}
        r = ibge.descobrir_metadados("9321", http=lambda u, p=None: resp)
        self.assertEqual(r["variaveis"][0]["nome"], "PIB per capita")


class TestColetar(unittest.TestCase):
    def test_um_documento_por_regiao_com_o_ano_mais_recente(self):
        por_regiao = {"Norte": "22000.0", "Nordeste": "19000.0", "Sudeste": "48000.0",
                     "Sul": "42000.0", "Centro-Oeste": "45000.0"}
        docs = ibge.coletar("9321", "9321", http=lambda u, p=None: _resposta_pib(por_regiao), agora=AGORA)
        self.assertEqual(len(docs), 5)
        sudeste = next(d for d in docs if d["regiao"] == "Sudeste")
        self.assertEqual(sudeste["valor"], 48000.0)
        self.assertEqual(sudeste["ano_referencia"], 2023)
        self.assertEqual(sudeste["indicador"], "IBGE.9321.9321")
        for campo in ("fonte", "url_fonte", "coletado_em", "licenca"):
            self.assertTrue(sudeste[campo])

    def test_codigo_de_ausencia_do_sidra_nao_vira_documento_quebrado(self):
        # ".." é o código oficial do SIDRA para "não se aplica" -- nunca virar 0.0 ou explodir
        por_regiao = {"Norte": "..", "Nordeste": "19000.0", "Sudeste": "48000.0",
                     "Sul": "42000.0", "Centro-Oeste": "45000.0"}
        docs = ibge.coletar("9321", "9321", http=lambda u, p=None: _resposta_pib(por_regiao), agora=AGORA)
        self.assertEqual(len(docs), 4)   # Norte fica de fora, sem gerar documento com valor errado
        self.assertNotIn("Norte", [d["regiao"] for d in docs])

    def test_pega_o_ano_mais_recente_quando_ha_mais_de_um(self):
        def http(url, params=None):
            return [{"id": "9321", "variavel": "PIB per capita", "unidade": "Reais",
                    "resultados": [{"series": [
                        {"localidade": {"id": "3", "nome": "Sudeste"},
                         "serie": {"2021": "40000.0", "2023": "48000.0", "2022": "44000.0"}},
                    ]}]}]
        docs = ibge.coletar("9321", "9321", http=http, agora=AGORA)
        self.assertEqual((docs[0]["valor"], docs[0]["ano_referencia"]), (48000.0, 2023))

    def test_id_normalizado_e_nunca_colide_com_paises(self):
        docs = ibge.coletar("9321", "9321", http=lambda u, p=None: _resposta_pib({"Sudeste": "48000.0"}), agora=AGORA)
        self.assertEqual(docs[0]["id"], "sudeste")

    def test_resposta_vazia_ou_invalida_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            ibge.coletar("9321", "9321", http=lambda u, p=None: [], agora=AGORA)
        with self.assertRaises(ErroColeta):
            ibge.coletar("9321", "9321", http=lambda u, p=None: {"nao": "lista"}, agora=AGORA)

    def test_regiao_fora_de_n2_e_ignorada_sem_quebrar(self):
        # se a consulta trouxer também o total "Brasil" (N1) por engano, não deve virar documento
        def http(url, params=None):
            resp = _resposta_pib({"Sudeste": "48000.0"})
            resp[0]["resultados"][0]["series"].append(
                {"localidade": {"id": "1", "nome": "Brasil"}, "serie": {"2023": "35000.0"}})
            return resp
        docs = ibge.coletar("9321", "9321", http=http, agora=AGORA)
        self.assertEqual([d["regiao"] for d in docs], ["Sudeste"])


class TestColecaoPropriaEIndependente(unittest.TestCase):
    def test_colecao_e_diferente_de_paises(self):
        self.assertEqual(ibge.COLECAO, "brasil_regioes")
        self.assertNotEqual(ibge.COLECAO, "paises")


if __name__ == "__main__":
    unittest.main()
