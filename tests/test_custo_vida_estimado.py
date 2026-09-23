# -*- coding: utf-8 -*-
"""
Testes OFFLINE do custo de vida estimado (derivados.calcular_custo_vida_estimado).

Cobre, especialmente:
  - a fórmula (baseline BLS × nível de preços);
  - o INVARIANTE crítico: o `id` do patch tem que bater com o id que
    seed_firestore.py usa para o mesmo país, senão o patch cria um documento
    novo e órfão em vez de mesclar no país existente;
  - que gravar() em modo teste mescla CAMPO A CAMPO (não substitui o documento
    inteiro) — sem isso, publicar o custo de vida apagaria região/idioma/visto
    do país.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # para achar seed_firestore.py, se copiado junto

from coletor import derivados
from coletor.publicar import Publicador
from coletor.validacao import validar_custo_vida_estimado

IND_PORTUGAL = {"id": "bm_pt_pa.nus.pppc.rf", "pais": "Portugal", "indicador": "PA.NUS.PPPC.RF",
                "valor": 0.6037, "ano_referencia": 2025, "fonte": "Banco Mundial (calculado)",
                "coletado_em": "2026-09-21T19:57:33Z"}
IND_ALEMANHA = {**IND_PORTUGAL, "id": "bm_de_pa.nus.pppc.rf", "pais": "Alemanha", "valor": 0.8023}
IND_OUTRO_CAMPO = {"id": "x", "pais": "Portugal", "indicador": "NY.GDP.PCAP.CD", "valor": 32080.6,
                   "ano_referencia": 2025, "fonte": "Banco Mundial", "coletado_em": "2026-09-21T19:57:33Z"}


class TestFormula(unittest.TestCase):
    def test_baseline_e_o_valor_oficial_do_bls_2024(self):
        # US$ 56.652/ano (BLS, "single consumer, one earner", 2024) / 12 = US$ 4.721/mês
        self.assertEqual(derivados.BASELINE_USD_MENSAL, round(56652 / 12))

    def test_estimativa_e_baseline_vezes_nivel_de_precos(self):
        docs = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])
        self.assertEqual(docs[0]["custo_vida_mensal_usd"], round(derivados.BASELINE_USD_MENSAL * 0.6037))

    def test_ignora_indicadores_que_nao_sao_o_nivel_de_precos(self):
        docs = derivados.calcular_custo_vida_estimado([IND_OUTRO_CAMPO])
        self.assertEqual(docs, [])

    def test_um_documento_por_pais(self):
        docs = derivados.calcular_custo_vida_estimado([IND_PORTUGAL, IND_ALEMANHA])
        self.assertEqual({d["id"] for d in docs}, {"portugal", "alemanha"})

    def test_todo_documento_e_marcado_como_calculado_com_metodo_e_fonte(self):
        d = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])[0]
        self.assertIs(d["custo_vida_mensal_usd_calculado"], True)
        self.assertIn("BLS", d["custo_vida_mensal_usd_metodo"])
        self.assertIn("PA.NUS.PPPC.RF", d["custo_vida_mensal_usd_metodo"])
        self.assertIn("Bureau of Labor Statistics", d["custo_vida_mensal_usd_fonte"])
        self.assertIn("Banco Mundial", d["custo_vida_mensal_usd_fonte"])


class TestIdBateComOSeedFirestore(unittest.TestCase):
    """O invariante mais importante deste módulo: sem isso, o patch nunca
    encontra o documento certo do país para mesclar."""

    def test_id_e_so_o_nome_do_pais_normalizado(self):
        d = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])[0]
        self.assertEqual(d["id"], "portugal")

    def test_pais_com_espaco_e_acento(self):
        ind = {**IND_PORTUGAL, "pais": "Emirados Árabes Unidos"}
        d = derivados.calcular_custo_vida_estimado([ind])[0]
        self.assertEqual(d["id"], "emirados_árabes_unidos")

    def test_bate_literalmente_com_seed_firestore_id_seguro_se_disponivel(self):
        try:
            import seed_firestore
            funcao = seed_firestore.id_seguro
        except (ImportError, AttributeError):
            self.skipTest(
                "seed_firestore.py não está nesta pasta, ou é uma versão antiga sem "
                "id_seguro() — copie o seed_firestore.py mais recente do pacote do "
                "coletor para a pasta do app (ele corrige um bug: os IDs antigos "
                "podiam conter '/', que o Firestore não aceita)."
            )
        for pais in ("Portugal", "Alemanha", "Canadá", "Irlanda", "Espanha", "Emirados Árabes Unidos"):
            ind = {**IND_PORTUGAL, "pais": pais}
            d = derivados.calcular_custo_vida_estimado([ind])[0]
            self.assertEqual(d["id"], funcao(pais), pais)


class TestValidacao(unittest.TestCase):
    def test_documento_valido_passa(self):
        d = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])[0]
        self.assertEqual(validar_custo_vida_estimado(d), [])

    def test_valor_fora_da_faixa_e_rejeitado(self):
        d = derivados.calcular_custo_vida_estimado([{**IND_PORTUGAL, "valor": 500}])[0]  # país 500x mais caro que os EUA
        self.assertTrue(any("fora da faixa" in e for e in validar_custo_vida_estimado(d)))

    def test_campo_calculado_precisa_ser_true(self):
        d = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])[0]
        d["custo_vida_mensal_usd_calculado"] = False
        self.assertTrue(any("calculado" in e for e in validar_custo_vida_estimado(d)))


class TestMesclaCampoACampoNaoApagaOResto(unittest.TestCase):
    def test_gravar_paises_preserva_campos_que_nao_estao_no_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            # simula o país já existente (como o seed_firestore.py teria gravado)
            pub.gravar("paises", [{
                "id": "portugal", "pais": "Portugal", "regiao": "Europa Ocidental",
                "lat": 39.4, "lon": -8.2, "idioma": "Português", "visto": "D3",
                "custo_vida_mensal_usd": 1100,  # valor antigo, do data.py
            }])
            patch = derivados.calcular_custo_vida_estimado([IND_PORTUGAL])
            pub.gravar("paises", patch)

            paises = pub.ler("paises")
            portugal = paises["portugal"]
            # o valor foi atualizado...
            self.assertEqual(portugal["custo_vida_mensal_usd"], round(derivados.BASELINE_USD_MENSAL * 0.6037))
            self.assertTrue(portugal["custo_vida_mensal_usd_calculado"])
            # ...mas os campos que o patch não tocou continuam lá
            for campo, esperado in (("regiao", "Europa Ocidental"), ("lat", 39.4),
                                    ("idioma", "Português"), ("visto", "D3")):
                self.assertEqual(portugal[campo], esperado, campo)


if __name__ == "__main__":
    unittest.main()
