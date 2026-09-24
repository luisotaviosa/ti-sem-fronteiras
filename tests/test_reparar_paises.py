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
    def test_sem_existentes_preenche_tudo_incluindo_custo_e_salario(self):
        # Firestore vazio (ou pasta de teste vazia): tudo conta como ausente.
        patches = reparar_paises.montar_patches(PAISES_DEMO, existentes={})
        p = next(p for p in patches if p["id"] == "portugal")
        self.assertEqual(p["custo_vida_mensal_usd"], 1100)
        self.assertEqual(p["salario_medio_ti_usd"], 2800)

    def test_nao_sobrescreve_custo_de_vida_ja_calculado(self):
        existentes = {"portugal": {"custo_vida_mensal_usd": 2850, "custo_vida_mensal_usd_calculado": True}}
        p = next(p for p in reparar_paises.montar_patches(PAISES_DEMO, existentes) if p["id"] == "portugal")
        self.assertNotIn("custo_vida_mensal_usd", p)          # não pisa no valor calculado
        self.assertEqual(p["salario_medio_ti_usd"], 2800)      # mas preenche o que ainda falta

    def test_nao_sobrescreve_salario_se_ja_existir_no_futuro(self):
        # Simula o dia em que o Adzuna já estiver publicando salario_medio_ti_usd de verdade.
        existentes = {"portugal": {"salario_medio_ti_usd": 3200, "moeda_confirmada": True}}
        p = next(p for p in reparar_paises.montar_patches(PAISES_DEMO, existentes) if p["id"] == "portugal")
        self.assertNotIn("salario_medio_ti_usd", p)
        self.assertEqual(p["custo_vida_mensal_usd"], 1100)     # este ainda estava ausente

    def test_campos_de_base_entram_sempre_mesmo_ja_existindo(self):
        existentes = {"portugal": {"regiao": "outra coisa qualquer"}}
        p = next(p for p in reparar_paises.montar_patches(PAISES_DEMO, existentes) if p["id"] == "portugal")
        self.assertEqual(p["regiao"], "Europa Ocidental")   # sempre vem do data.py, sem checar existentes

    def test_existentes_none_equivale_a_vazio(self):
        self.assertEqual(reparar_paises.montar_patches(PAISES_DEMO, None),
                         reparar_paises.montar_patches(PAISES_DEMO, {}))


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
            # e o SEGUNDO incidente (salario_medio_ti_usd ausente) também sai corrigido
            self.assertEqual(depois["portugal"]["salario_medio_ti_usd"], 2800)
            self.assertEqual(depois["alemanha"]["salario_medio_ti_usd"], 4800)

    def test_reproduz_com_pandas_de_verdade_o_segundo_keyerror_salario(self):
        """Mesmo formato do incidente real: df_filtrado.sort_values('salario_medio_ti_usd')."""
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            # estado logo após o PRIMEIRO reparo: regiao já presente, mas salario ainda não
            pub.gravar("paises", [
                {"id": "portugal", "regiao": "Europa Ocidental",
                 "custo_vida_mensal_usd": 2850, "custo_vida_mensal_usd_calculado": True},
                {"id": "alemanha", "regiao": "Europa Ocidental",
                 "custo_vida_mensal_usd": 3788, "custo_vida_mensal_usd_calculado": True},
            ])
            df_antes = pd.DataFrame(list(pub.ler("paises").values()))
            with self.assertRaises(KeyError):
                df_antes.sort_values("salario_medio_ti_usd")

            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)

            df_depois = pd.DataFrame(list(pub.ler("paises").values()))
            df_depois.sort_values("salario_medio_ti_usd")   # não deve levantar mais
            # e o custo de vida calculado continua intacto
            self.assertEqual(df_depois.set_index("id").loc["portugal", "custo_vida_mensal_usd"], 2850)

    def test_e_seguro_rodar_de_novo_sobre_um_pais_ja_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("paises", [{"id": "portugal", "regiao": "Europa Ocidental", "idioma": "Português",
                                   "custo_vida_mensal_usd": 2850, "salario_medio_ti_usd": 3200,
                                   "moeda_confirmada": True}])
            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)
            portugal = pub.ler("paises")["portugal"]
            self.assertEqual(portugal["regiao"], "Europa Ocidental")
            self.assertEqual(portugal["custo_vida_mensal_usd"], 2850)   # continua intacto
            self.assertEqual(portugal["salario_medio_ti_usd"], 3200)    # idem — não volta pro valor demo (2800)

    def test_nao_grava_nada_em_vagas_radar_ou_trilhas(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            reparar_paises.main(["--saida", tmp], paises=PAISES_DEMO)
            import os as _os
            for colecao in ("vagas", "radar_tecnologias", "trilhas_qualificacao"):
                self.assertFalse(_os.path.exists(_os.path.join(tmp, f"{colecao}.json")))


if __name__ == "__main__":
    unittest.main()
