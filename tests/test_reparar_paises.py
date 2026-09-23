# -*- coding: utf-8 -*-
"""Testes OFFLINE do reparo de países (coletor/reparar_paises.py)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # para achar data.py, se copiado junto

from coletor import reparar_paises
from coletor.publicar import Publicador

PAISES_DEMO = [
    {"pais": "Portugal", "regiao": "Europa Ocidental", "lat": 39.4, "lon": -8.2,
     "idioma": "Português", "visto": "D3", "dificuldade_visto": "Baixa",
     "demanda_ti": "Alta", "resumo": "Bom custo de vida.",
     "custo_vida_mensal_usd": 1100, "salario_medio_ti_usd": 2800},
    {"pais": "Alemanha", "regiao": "Europa Ocidental", "lat": 51.2, "lon": 10.4,
     "idioma": "Alemão", "visto": "Blue Card UE", "dificuldade_visto": "Média",
     "demanda_ti": "Muito Alta", "resumo": "Forte mercado de TI.",
     "custo_vida_mensal_usd": 1500, "salario_medio_ti_usd": 4800},
]


class TestMontarPatches(unittest.TestCase):
    def test_nunca_inclui_custo_de_vida_ou_salario(self):
        patches = reparar_paises.montar_patches(PAISES_DEMO)
        for p in patches:
            self.assertNotIn("custo_vida_mensal_usd", p)
            self.assertNotIn("salario_medio_ti_usd", p)

    def test_inclui_os_campos_de_base(self):
        p = reparar_paises.montar_patches(PAISES_DEMO)[0]
        self.assertEqual(p["regiao"], "Europa Ocidental")
        self.assertEqual(p["idioma"], "Português")
        self.assertEqual(p["visto"], "D3")
        self.assertEqual(p["id"], "portugal")   # mesmo esquema de id dos outros patches


class TestReparoDoBugReal(unittest.TestCase):
    def test_reproduz_e_corrige_o_keyerror_de_producao(self):
        """
        Reproduz exatamente o incidente: a coleta automática rodou antes do
        seed_firestore.py, então 'paises' só tem o patch de custo de vida —
        SEM 'regiao' em nenhum documento (o que derruba a página no app real,
        porque a coluna nem existe no DataFrame). O reparo tem que preencher
        regiao/idioma/etc. em AMBOS os países, sem mexer no valor já calculado.
        """
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            # só o que a coleta automática já tinha gravado (sem seed_firestore.py rodado)
            pub.gravar("paises", [
                {"id": "portugal", "custo_vida_mensal_usd": 2850, "custo_vida_mensal_usd_calculado": True},
                {"id": "alemanha", "custo_vida_mensal_usd": 3788, "custo_vida_mensal_usd_calculado": True},
            ])
            antes = pub.ler("paises")
            self.assertNotIn("regiao", antes["portugal"])   # confirma que reproduzimos o bug

            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)

            depois = pub.ler("paises")
            # o app agora consegue montar sorted(df_paises["regiao"].unique()...) sem KeyError
            self.assertEqual(depois["portugal"]["regiao"], "Europa Ocidental")
            self.assertEqual(depois["alemanha"]["regiao"], "Europa Ocidental")
            self.assertEqual(depois["portugal"]["idioma"], "Português")
            # e o valor calculado sobrevive intacto
            self.assertEqual(depois["portugal"]["custo_vida_mensal_usd"], 2850)
            self.assertTrue(depois["portugal"]["custo_vida_mensal_usd_calculado"])
            self.assertEqual(depois["alemanha"]["custo_vida_mensal_usd"], 3788)

    def test_e_seguro_rodar_de_novo_sobre_um_pais_ja_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("paises", [{"id": "portugal", "regiao": "Europa Ocidental", "idioma": "Português",
                                   "custo_vida_mensal_usd": 2850}])
            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)
            portugal = pub.ler("paises")["portugal"]
            self.assertEqual(portugal["regiao"], "Europa Ocidental")
            self.assertEqual(portugal["custo_vida_mensal_usd"], 2850)   # continua intacto

    def test_nao_grava_nada_em_vagas_radar_ou_trilhas(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)
            import os as _os
            for colecao in ("vagas", "radar_tecnologias", "trilhas_qualificacao"):
                self.assertFalse(_os.path.exists(_os.path.join(tmp, f"{colecao}.json")))


if __name__ == "__main__":
    unittest.main()
