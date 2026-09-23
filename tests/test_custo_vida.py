# -*- coding: utf-8 -*-
"""
Testes OFFLINE do módulo custo_vida.py.

O decodificador de JSON-stat 2.0 é testado contra exemplos construídos à mão, fiéis
à especificação aberta (https://json-stat.org/format/) — não uma resposta real do
Eurostat (sem acesso de rede nesta sessão para obter uma). Ver o aviso no topo de
custo_vida.py: rode `python -m coletor.custo_vida --descobrir` antes de usar em
produção, para confirmar os códigos reais de na_item/unit.
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coletor import custo_vida
from coletor.rede import ErroColeta

AGORA = datetime(2026, 9, 21, tzinfo=timezone.utc)

# --- exemplo JSON-stat 2.0 construído à mão, fiel à especificação (2 países x 2 anos) ---
FIXTURE_2D = {
    "version": "2.0", "class": "dataset",
    "id": ["geo", "time"],
    "size": [2, 2],
    "dimension": {
        "geo": {"label": "Geopolitical entity", "category": {
            "index": {"PT": 0, "DE": 1}, "label": {"PT": "Portugal", "DE": "Germany"}}},
        "time": {"label": "Time", "category": {
            "index": {"2024": 0, "2025": 1}, "label": {"2024": "2024", "2025": "2025"}}},
    },
    # ordem row-major (última dimensão varia mais rápido): PT/2024, PT/2025, DE/2024, DE/2025
    "value": {"0": 60.3, "1": 61.0, "2": 80.1, "3": 80.5},
}

# variante com "value" como LISTA (também previsto na especificação) e um buraco (null)
FIXTURE_LISTA_COM_BURACO = {
    "version": "2.0", "class": "dataset",
    "id": ["geo", "time"], "size": [2, 2],
    "dimension": FIXTURE_2D["dimension"],
    "value": [60.3, None, 80.1, 80.5],   # PT/2025 ausente
}

# 3 dimensões, com na_item e unit fixos em uma única categoria (sem "index", só "label")
FIXTURE_3D_NA_ITEM_FIXO = {
    "version": "2.0", "class": "dataset",
    "id": ["na_item", "geo", "time"], "size": [1, 2, 2],
    "dimension": {
        "na_item": {"label": "National accounts indicator", "category": {"label": {"PLI_AIC": "Price level index"}}},
        "geo": FIXTURE_2D["dimension"]["geo"],
        "time": FIXTURE_2D["dimension"]["time"],
    },
    "value": {"0": 60.3, "1": 61.0, "2": 80.1, "3": 80.5},
}


class TestDecodificadorJsonStat(unittest.TestCase):
    def test_2_dimensoes_value_como_dict(self):
        reg = custo_vida.decodificar_json_stat(FIXTURE_2D)
        esperado = [
            {"geo": "PT", "time": "2024", "value": 60.3},
            {"geo": "PT", "time": "2025", "value": 61.0},
            {"geo": "DE", "time": "2024", "value": 80.1},
            {"geo": "DE", "time": "2025", "value": 80.5},
        ]
        self.assertEqual(reg, esperado)

    def test_value_como_lista_com_buraco_null(self):
        reg = custo_vida.decodificar_json_stat(FIXTURE_LISTA_COM_BURACO)
        # a posição PT/2025 (flat=1) tem valor None e não deve aparecer na saída
        self.assertEqual(len(reg), 3)
        self.assertNotIn({"geo": "PT", "time": "2025", "value": None}, reg)
        self.assertIn({"geo": "DE", "time": "2024", "value": 80.1}, reg)

    def test_dimensao_de_categoria_unica_sem_index(self):
        reg = custo_vida.decodificar_json_stat(FIXTURE_3D_NA_ITEM_FIXO)
        self.assertEqual(len(reg), 4)
        self.assertTrue(all(r["na_item"] == "PLI_AIC" for r in reg))
        pt2025 = next(r for r in reg if r["geo"] == "PT" and r["time"] == "2025")
        self.assertEqual(pt2025["value"], 61.0)


# Resposta REAL obtida pelo usuário em 21/09/2026 (python -m coletor.custo_vida --descobrir):
# a dimensão "unit" não existe neste dataset; "na_item" tem 24 códigos reais.
NA_ITEM_REAL = {
    "PPP_EU27_2020": "Purchasing power parities (EU27_2020=1)",
    "PLI_EU27_2020": "Price level indices (EU27_2020=100)",
    "EXP_NAC": "Nominal expenditure in national currency",
    "EXP_PPS_EU27_2020_HAB": "Real expenditure per capita (in PPS_EU27_2020)",
    "VI_PPS_EU27_2020_HAB": "Volume indices of real expenditure per capita (in PPS_EU27_2020=100)",
}


class TestDescobrirDimensoes(unittest.TestCase):
    def test_lista_todas_as_dimensoes_sem_supor_nomes(self):
        def http(url, params=None):
            self.assertEqual(params.get("geo"), "PT")
            return {
                "id": ["na_item", "ppp_cat", "geo", "time"],
                "dimension": {
                    "na_item": {"label": "National accounts indicator",
                               "category": {"label": NA_ITEM_REAL}},
                    "ppp_cat": {"label": "PPP item categories",
                               "category": {"label": {"TOTAL": "Total", "AIC": "Actual individual consumption",
                                                       "FOOD": "Food and non-alcoholic beverages"}}},
                    "geo": {"category": {"label": {"PT": "Portugal"}}},
                    "time": {"category": {"label": {"2024": "2024"}}},
                }
            }
        r = custo_vida.descobrir_dimensoes(http=http)
        self.assertEqual(set(r), {"na_item", "ppp_cat", "geo", "time"})   # inclusive as que não eram esperadas
        self.assertIn("PLI_EU27_2020", r["na_item"]["categorias"])
        self.assertIn("AIC", r["ppp_cat"]["categorias"])
        self.assertEqual(r["ppp_cat"]["rotulo"], "PPP item categories")
        # a ordem de saída segue resp["id"], não uma lista fixa de nomes
        self.assertEqual(list(r), ["na_item", "ppp_cat", "geo", "time"])

    def test_com_a_resposta_real_do_usuario_sem_unit(self):
        def http(url, params=None):
            return {"id": ["na_item", "geo"],
                   "dimension": {"na_item": {"label": "x", "category": {"label": NA_ITEM_REAL}},
                                 "geo": {"category": {"label": {"PT": "Portugal"}}}}}
        r = custo_vida.descobrir_dimensoes(http=http)
        self.assertNotIn("unit", r)          # confirmado: esta dimensão não existe aqui
        self.assertEqual(len(r["na_item"]["categorias"]), 5)

    def test_resposta_sem_dimension_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            custo_vida.descobrir_dimensoes(http=lambda u, p=None: {"erro": "algo"})


class TestColetar(unittest.TestCase):
    def _http_dataset(self, na_item_labels=None):
        def http(url, params=None):
            doc = dict(FIXTURE_2D)
            if na_item_labels:
                doc = {**doc, "dimension": {**doc["dimension"],
                                            "na_item": {"category": {"label": na_item_labels}}}}
            return doc
        return http

    def test_valores_padrao_sao_os_confirmados_na_2a_rodada_de_descoberta(self):
        self.assertEqual(custo_vida.NA_ITEM_PADRAO, "PLI_EU27_2020")
        self.assertEqual(custo_vida.PPP_CAT_PADRAO, "E011")   # despesa das famílias, não AIC

    def test_coleta_com_os_padroes_usa_na_item_e_ppp_cat_corretos(self):
        vistos = {}

        def http(url, params=None):
            vistos.update(params or {})
            doc = dict(FIXTURE_2D)
            doc["dimension"] = {**doc["dimension"],
                               "na_item": {"category": {"label": {"PLI_EU27_2020": "Price level indices (EU27_2020=100)"}}},
                               "ppp_cat": {"category": {"label": {"E011": "Household final consumption expenditure"}}}}
            return doc

        docs = custo_vida.coletar(paises={"Portugal": "PT", "Alemanha": "DE"}, http=http, agora=AGORA)
        self.assertEqual(vistos.get("na_item"), "PLI_EU27_2020")
        self.assertEqual(vistos.get("ppp_cat"), "E011")
        pt = next(d for d in docs if d["pais"] == "Portugal")
        self.assertEqual((pt["valor"], pt["ano_referencia"]), (61.0, 2025))   # o ano mais recente, não o primeiro
        self.assertEqual(pt["indicador"], "EUROSTAT.PLI_EU27_2020")
        self.assertEqual(pt["descricao"], "Price level indices (EU27_2020=100) — Household final consumption expenditure")
        for campo in ("fonte", "url_fonte", "coletado_em", "licenca"):
            self.assertTrue(pt[campo])

    def test_filtros_extra_entram_na_consulta_e_no_url_fonte(self):
        vistos = {}

        def http(url, params=None):
            vistos.update(params or {})
            return FIXTURE_2D
        docs = custo_vida.coletar("PLI_EU27_2020", filtros_extra={"ppp_cat": "AIC"},
                                  paises={"Portugal": "PT", "Alemanha": "DE"}, http=http, agora=AGORA)
        self.assertEqual(vistos.get("ppp_cat"), "AIC")
        self.assertIn("ppp_cat=AIC", docs[0]["url_fonte"])

    def test_paises_fora_da_cobertura_sao_ignorados(self):
        # geo "CA" (Canadá) não existe no dataset de exemplo: não deve gerar documento nem quebrar
        docs = custo_vida.coletar("PLI_EU27_2020", paises={"Portugal": "PT", "Canadá": "CA"},
                                  http=self._http_dataset(), agora=AGORA)
        self.assertEqual([d["pais"] for d in docs], ["Portugal"])

    def test_resposta_sem_value_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            custo_vida.coletar("PLI_EU27_2020", http=lambda u, p=None: {"sem": "value"}, agora=AGORA)

    def test_ids_nunca_colidem_com_os_do_banco_mundial(self):
        docs = custo_vida.coletar("PLI_EU27_2020", paises={"Portugal": "PT"},
                                  http=self._http_dataset(), agora=AGORA)
        self.assertTrue(docs[0]["id"].startswith("eurostat_"))
        self.assertTrue(docs[0]["indicador"].startswith("EUROSTAT."))


class TestTestarCombinacao(unittest.TestCase):
    def test_combinacao_sem_dados_e_relatada_como_problema_sem_quebrar(self):
        # exatamente o que aconteceu na coleta real: resposta válida, "value" vazio
        def http(url, params=None):
            return {"id": ["na_item", "ppp_cat", "geo", "time"], "size": [1, 1, 1, 1],
                   "dimension": {"na_item": {"category": {"label": {"PLI_EU27_2020": "x"}}},
                                "ppp_cat": {"category": {"label": {"E011": "y"}}}},
                   "value": {}}
        d = custo_vida.testar_combinacao(http=http)
        self.assertEqual(d["value_tamanho"], 0)
        self.assertIn("problema", d)
        self.assertIn("não existe dado publicado", d["problema"])

    def test_combinacao_com_dados_mostra_amostra_decodificada(self):
        def http(url, params=None):
            doc = dict(FIXTURE_2D)
            doc["dimension"] = {**doc["dimension"],
                               "na_item": {"category": {"label": {"PLI_EU27_2020": "x"}}},
                               "ppp_cat": {"category": {"label": {"E011": "y"}}}}
            return doc
        d = custo_vida.testar_combinacao(geo_amostra="PT", http=http)
        self.assertNotIn("problema", d)
        self.assertEqual(d["value_tamanho"], 4)
        self.assertTrue(d["registros_decodificados"])

    def test_resposta_que_nao_e_dict_e_relatada(self):
        d = custo_vida.testar_combinacao(http=lambda u, p=None: "erro em texto puro")
        self.assertIn("problema", d)
        self.assertIsNone(d["chaves_da_resposta"])



if __name__ == "__main__":
    unittest.main()
