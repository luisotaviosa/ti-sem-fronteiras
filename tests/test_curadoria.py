# -*- coding: utf-8 -*-
"""Testes OFFLINE da curadoria de vistos e trilhas (sem rede — não usa nenhuma API)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coletor import curadoria
from coletor.publicar import Publicador

VISTO_OK = {"pais": "Portugal", "visto": "D3", "dificuldade_visto": "Baixa",
           "verificado_por": "Ana", "verificado_em": "2026-09-22", "fonte": "Portal oficial"}
TRILHA_OK = {"area": "Suporte / Redes", "competencia": "Redes", "certificacoes": ["CCNA"],
            "verificado_por": "Ana", "verificado_em": "2026-09-22", "fonte": "Sites dos certificadores"}


class TestValidarVisto(unittest.TestCase):
    def test_visto_valido_passa(self):
        self.assertEqual(curadoria.validar_visto(curadoria.preparar_visto(VISTO_OK)), [])

    def test_falta_verificado_por(self):
        ruim = {**VISTO_OK, "verificado_por": "  "}
        self.assertTrue(any("verificado_por" in e for e in curadoria.validar_visto(curadoria.preparar_visto(ruim))))

    def test_data_invalida(self):
        ruim = {**VISTO_OK, "verificado_em": "22/09/2026"}
        self.assertTrue(any("data válida" in e for e in curadoria.validar_visto(curadoria.preparar_visto(ruim))))

    def test_dificuldade_fora_do_vocabulario_fixo(self):
        ruim = {**VISTO_OK, "dificuldade_visto": "Médio-baixa"}
        self.assertTrue(any("dificuldade_visto" in e for e in curadoria.validar_visto(curadoria.preparar_visto(ruim))))

    def test_id_e_o_nome_do_pais_normalizado_como_nos_outros_patches(self):
        self.assertEqual(curadoria.preparar_visto(VISTO_OK)["id"], "portugal")


class TestValidarTrilha(unittest.TestCase):
    def test_trilha_valida_passa(self):
        self.assertEqual(curadoria.validar_trilha(curadoria.preparar_trilha(TRILHA_OK)), [])

    def test_certificacoes_precisa_ser_lista(self):
        ruim = {**TRILHA_OK, "certificacoes": "CCNA"}
        self.assertTrue(any("lista" in e for e in curadoria.validar_trilha(curadoria.preparar_trilha(ruim))))


class TestProcessar(unittest.TestCase):
    def test_publica_validos_e_rejeita_o_resto_sem_derrubar_o_lote(self):
        entradas = [VISTO_OK, {**VISTO_OK, "pais": "Alemanha", "verificado_por": ""}]  # 2º é inválido
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            resumo = curadoria.processar("paises", entradas, pub)
            self.assertEqual(resumo, {"recebidos": 2, "publicados": 1, "rejeitados": 1})
            self.assertIn("portugal", pub.ler("paises"))

    def test_patch_de_visto_preserva_o_resto_do_documento_do_pais(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("paises", [{"id": "portugal", "pais": "Portugal", "regiao": "Europa Ocidental",
                                   "custo_vida_mensal_usd": 2850}])
            curadoria.processar("paises", [VISTO_OK], pub)
            portugal = pub.ler("paises")["portugal"]
            self.assertEqual(portugal["visto"], "D3")
            self.assertEqual(portugal["regiao"], "Europa Ocidental")          # preservado
            self.assertEqual(portugal["custo_vida_mensal_usd"], 2850)          # preservado

    def test_colecao_nao_suportada_levanta_erro_claro(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            with self.assertRaises(ValueError):
                curadoria.processar("vagas", [VISTO_OK], pub)

    def test_modelos_json_fornecidos_sao_validos(self):
        base = os.path.join(os.path.dirname(__file__), "..", "curadoria")
        if not os.path.isdir(base):
            self.skipTest("pasta curadoria/ não está nesta cópia")
        with open(os.path.join(base, "vistos_modelo.json"), encoding="utf-8") as f:
            vistos = json.load(f)
        with open(os.path.join(base, "trilhas_modelo.json"), encoding="utf-8") as f:
            trilhas = json.load(f)
        for v in vistos:
            v["verificado_por"] = "x"  # o modelo vem com um placeholder de propósito
            self.assertEqual(curadoria.validar_visto(curadoria.preparar_visto(v)), [])
        for t in trilhas:
            t["verificado_por"] = "x"
            self.assertEqual(curadoria.validar_trilha(curadoria.preparar_trilha(t)), [])


if __name__ == "__main__":
    unittest.main()
