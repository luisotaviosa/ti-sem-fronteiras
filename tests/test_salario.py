# -*- coding: utf-8 -*-
"""
Testes OFFLINE do coletor de salário (Adzuna). As respostas de exemplo seguem o
formato documentado oficialmente (developer.adzuna.com/docs/histogram, endpoint
irmão `history`): {"month": {"AAAA-MM": valor, ...}}. Nunca testado contra uma
resposta real (precisa de credencial paga... digo, gratuita, mas ainda assim uma
credencial que este ambiente não tem como obter).
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coletor import salario
from coletor.rede import ErroColeta

AGORA = datetime(2026, 9, 22, tzinfo=timezone.utc)


def http_ok(meses):
    def _http(url, params=None):
        return {"month": meses}
    return _http


def http_por_pais(respostas):
    """respostas: {codigo_pais_na_url: {"month": {...}} ou exceção a levantar}"""
    def _http(url, params=None):
        for codigo, resp in respostas.items():
            if f"/jobs/{codigo}/history" in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"URL não esperada no teste: {url}")
    return _http


class TestVerificarCobertura(unittest.TestCase):
    def test_pais_com_dado_e_ok_pais_sem_dado_nao_e(self):
        http = http_por_pais({
            "de": {"month": {"2026-08": 62000.0}},
            "pt": {"month": {}},        # aceito, mas sem nenhum dado
            "ca": ErroColeta("HTTP 400 em .../ca/history"),
            "es": {"month": {"2026-08": 41000.0}},
            "ie": {"month": {"2026-08": 58000.0}},
            "ae": ErroColeta("HTTP 400 em .../ae/history"),
        })
        r = salario.verificar_cobertura("id", "key", http=http)
        self.assertTrue(r["Alemanha"][0])
        self.assertTrue(r["Espanha"][0])
        self.assertTrue(r["Irlanda"][0])
        self.assertFalse(r["Portugal"][0])
        self.assertFalse(r["Canadá"][0])
        self.assertFalse(r["Emirados Árabes Unidos"][0])
        self.assertIn("62000", r["Alemanha"][1])

    def test_nunca_levanta_erro_mesmo_com_todos_os_paises_falhando(self):
        http = lambda url, params=None: (_ for _ in ()).throw(ErroColeta("sempre falha"))
        r = salario.verificar_cobertura("id", "key", http=http)
        self.assertTrue(all(not ok for ok, _ in r.values()))


class TestColetar(unittest.TestCase):
    def test_coleta_o_ultimo_mes_disponivel_por_pais(self):
        http = http_por_pais({
            "de": {"month": {"2026-06": 60000.0, "2026-08": 62000.0, "2026-07": 61000.0}},
            "es": {"month": {"2026-08": 41000.0}},
            "pt": {"month": {}}, "ca": {"month": {}}, "ie": {"month": {}}, "ae": {"month": {}},
        })
        docs, falhas = salario.coletar("id", "key", http=http, agora=AGORA)
        de = next(d for d in docs if d["pais"] == "Alemanha")
        self.assertEqual((de["valor"], de["mes_referencia"], de["ano_referencia"]), (62000.0, "2026-08", 2026))
        self.assertEqual(len(docs), 2)   # só Alemanha e Espanha tinham dado
        self.assertEqual(set(falhas), {"Portugal", "Canadá", "Irlanda", "Emirados Árabes Unidos"})

    def test_documento_marca_moeda_como_nao_confirmada(self):
        docs, _ = salario.coletar("id", "key", http=http_por_pais(
            {"de": {"month": {"2026-08": 62000.0}}, "es": {"month": {}},
             "pt": {"month": {}}, "ca": {"month": {}}, "ie": {"month": {}}, "ae": {"month": {}}}),
            agora=AGORA)
        self.assertIs(docs[0]["moeda_confirmada"], False)

    def test_indicador_e_proveniencia_completos(self):
        docs, _ = salario.coletar("id", "key", http=http_por_pais(
            {"de": {"month": {"2026-08": 62000.0}}, "es": {"month": {}},
             "pt": {"month": {}}, "ca": {"month": {}}, "ie": {"month": {}}, "ae": {"month": {}}}),
            agora=AGORA)
        d = docs[0]
        self.assertEqual(d["indicador"], "ADZUNA.SALARIO_TI_HISTORICO")
        for campo in ("fonte", "url_fonte", "coletado_em", "licenca"):
            self.assertTrue(d[campo])
        self.assertTrue(d["id"].startswith("adzuna_"))

    def test_erro_de_rede_num_pais_nao_impede_os_demais(self):
        docs, falhas = salario.coletar("id", "key", http=http_por_pais({
            "de": {"month": {"2026-08": 62000.0}},
            "es": ErroColeta("indisponível"),
            "pt": {"month": {}}, "ca": {"month": {}}, "ie": {"month": {}}, "ae": {"month": {}},
        }), agora=AGORA)
        self.assertEqual(len(docs), 1)
        self.assertIn("indisponível", falhas["Espanha"])


if __name__ == "__main__":
    unittest.main()
