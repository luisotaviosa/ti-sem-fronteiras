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


class TestListarPesquisas(unittest.TestCase):
    def test_lista_nomes_unicos_e_ordenados(self):
        # Reproduz a hipótese real: a 1ª chave do catálogo pode ser um ASSUNTO amplo
        # ("Trabalho e Rendimento"), não o nome da pesquisa em si ("PNAD Contínua") --
        # foi por isso que --pesquisa "PNAD Contínua" deu 0 resultados.
        catalogo = [
            {"id": "1", "nome": "Trabalho e Rendimento", "agregados": [
                {"id": "6387", "nome": "Rendimento médio mensal real, PNAD Contínua"}]},
            {"id": "2", "nome": "Economia", "agregados": [
                {"id": "9321", "nome": "PIB per capita, Contas Regionais"}]},
            {"id": "3", "nome": "Economia", "agregados": [   # nome repetido -> não deve duplicar na lista
                {"id": "9322", "nome": "Outro agregado"}]},
        ]
        nomes = ibge.listar_pesquisas(http=lambda u, p=None: catalogo)
        self.assertEqual(nomes, ["Economia", "Trabalho e Rendimento"])   # únicos e ordenados

    def test_resposta_que_nao_e_lista_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            ibge.listar_pesquisas(http=lambda u, p=None: {"erro": "x"})
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


class TestDescobrirPorPesquisa(unittest.TestCase):
    def test_lista_todos_os_agregados_da_pesquisa_sem_filtrar_pelo_nome_do_indicador(self):
        # Reproduz o problema real: "PIB per capita" não bate no título, mas o
        # nome do LEVANTAMENTO ("Contas Regionais") sim -- e aí pega os 2 agregados.
        catalogo = [
            {"id": "49", "nome": "Contas Regionais", "agregados": [
                {"id": "9321", "nome": "Produto Interno Bruto a preços correntes, por Grande Região"},
                {"id": "9322", "nome": "Valor adicionado bruto a preços correntes"},
            ]},
            {"id": "37", "nome": "IPCA", "agregados": [
                {"id": "1705", "nome": "IPCA-15 - Variação mensal"},
            ]},
        ]
        r = ibge.descobrir_por_pesquisa("Contas Regionais", http=lambda u, p=None: catalogo)
        self.assertEqual({a["agregado_id"] for a in r}, {"9321", "9322"})

    def test_nao_filtra_por_nome_do_agregado(self):
        catalogo = [{"id": "1", "nome": "PNAD Contínua", "agregados": [
            {"id": "6387", "nome": "Rendimento médio mensal real, por Grande Região"}]}]
        # termo "rendimento" NÃO está no nome da pesquisa "PNAD Contínua" -> não acha nada
        r = ibge.descobrir_por_pesquisa("rendimento", http=lambda u, p=None: catalogo)
        self.assertEqual(r, [])
        # mas buscando pelo nome da pesquisa, acha (mesmo sem repetir "rendimento")
        r2 = ibge.descobrir_por_pesquisa("PNAD Contínua", http=lambda u, p=None: catalogo)
        self.assertEqual(len(r2), 1)


class TestDescobrirMetadados(unittest.TestCase):
    def test_devolve_variaveis_e_niveis(self):
        resp = {"nome": "PIB per capita", "nivelTerritorial": {"Administrativo": ["N2", "N3"]},
               "variaveis": [{"id": "9321", "nome": "PIB per capita", "unidade": "Reais"}]}
        r = ibge.descobrir_metadados("9321", http=lambda u, p=None: resp)
        self.assertEqual(r["variaveis"][0]["nome"], "PIB per capita")


def _resposta(agregado_id, variavel_desc, unidade, por_regiao_anos):
    """{"Sudeste": {"2022": "48000.0", "2023": "50000.0"}, ...} -> formato real do SIDRA."""
    series = [{"localidade": {"id": ibge.REGIOES[nome], "nome": nome}, "serie": dict(anos)}
              for nome, anos in por_regiao_anos.items()]
    return [{"id": agregado_id, "variavel": variavel_desc, "unidade": unidade,
            "resultados": [{"series": series}]}]


class TestSeriePorRegiao(unittest.TestCase):
    def test_pega_todos_os_anos_por_regiao(self):
        resp = _resposta("6579", "População residente estimada", "Pessoas",
                         {"Sudeste": {"2022": "88000000", "2023": "89000000"}})
        por_regiao, desc, unidade = ibge._serie_por_regiao("6579", "9324", http=lambda u, p=None: resp)
        self.assertEqual(por_regiao["Sudeste"], {2022: 88000000.0, 2023: 89000000.0})
        self.assertEqual((desc, unidade), ("População residente estimada", "Pessoas"))

    def test_codigo_de_ausencia_do_sidra_e_ignorado_sem_quebrar(self):
        resp = _resposta("5938", "PIB", "Mil Reais", {"Norte": {"2023": ".."}})
        por_regiao, _, _ = ibge._serie_por_regiao("5938", "37", http=lambda u, p=None: resp)
        self.assertEqual(por_regiao, {})   # nenhum ano válido -> região nem aparece

    def test_regiao_fora_de_n2_e_ignorada(self):
        resp = _resposta("5938", "PIB", "Mil Reais", {"Sudeste": {"2023": "1000.0"}})
        resp[0]["resultados"][0]["series"].append(
            {"localidade": {"id": "1", "nome": "Brasil"}, "serie": {"2023": "5000.0"}})
        por_regiao, _, _ = ibge._serie_por_regiao("5938", "37", http=lambda u, p=None: resp)
        self.assertEqual(set(por_regiao), {"Sudeste"})

    def test_classificacao_vira_parametro_de_query_no_formato_oficial(self):
        vistos = {}
        def http(url, params=None):
            vistos.update(params or {})
            return _resposta("5436", "Rendimento", "Reais", {"Sudeste": {"2025": "3200.0"}})
        ibge._serie_por_regiao("5436", "5932", classificacao={"2": "6794"}, http=http)
        self.assertEqual(vistos.get("classificacao"), "2[6794]")


    def test_periodo_trimestral_de_6_digitos_vira_so_o_ano_4_digitos(self):
        # Bug real de produção (24/09/2026): a PNAD Contínua trimestral devolve o
        # período como "AAAAQQ" (ano + trimestre móvel, ex.: "202502"), não só o
        # ano. Sem tratar isso, "ano_referencia" virava 202502 e era rejeitado na
        # validação por estar fora de qualquer faixa plausível de ano.
        resp = _resposta("5436", "Rendimento", "Reais", {"Sudeste": {"202502": "3200.0"}})
        por_regiao, _, _ = ibge._serie_por_regiao("5436", "5932", http=lambda u, p=None: resp)
        self.assertEqual(por_regiao["Sudeste"], {2025: 3200.0})   # e não {202502: 3200.0}


class TestColetarPibPerCapita(unittest.TestCase):
    def _http(self, pib_por_regiao, pop_por_regiao):
        def http(url, params=None):
            if f"/{ibge.PIB_AGREGADO_ID}/" in url:
                return _resposta(ibge.PIB_AGREGADO_ID, "Produto Interno Bruto a preços correntes",
                                 "Mil Reais", pib_por_regiao)
            if f"/{ibge.POPULACAO_AGREGADO_ID}/" in url:
                return _resposta(ibge.POPULACAO_AGREGADO_ID, "População residente estimada",
                                 "Pessoas", pop_por_regiao)
            raise AssertionError(f"URL inesperada: {url}")
        return http

    def test_calculo_bate_com_a_conta_na_mao_e_unidade_mil_reais_vira_reais(self):
        # PIB = 500.000 Mil Reais = 500.000.000 Reais; população = 10.000.000 pessoas
        # -> per capita = 500.000.000 / 10.000.000 = 50,00 Reais... só pra facilitar a conta.
        http = self._http({"Sudeste": {"2023": "500000"}}, {"Sudeste": {"2023": "10000000"}})
        docs = ibge.coletar_pib_per_capita(http=http, agora=AGORA)
        sudeste = next(d for d in docs if d["regiao"] == "Sudeste")
        self.assertEqual(sudeste["valor"], 50.0)
        self.assertEqual(sudeste["ano_referencia"], 2023)
        self.assertIs(sudeste["calculado"], True)
        self.assertIn("Mil Reais", sudeste["metodo"])
        self.assertEqual(sudeste["unidade"], "Reais")

    def test_usa_o_ano_mais_recente_EM_COMUM_quando_as_series_tem_defasagens_diferentes(self):
        # PIB só tem até 2022 (defasagem maior); população já tem 2023 e 2024.
        # Não pode usar população de 2024 dividindo o PIB de outro ano -- tem
        # que cair no último ano em que as DUAS existem: 2022.
        http = self._http(
            {"Sudeste": {"2021": "480000", "2022": "500000"}},
            {"Sudeste": {"2022": "10000000", "2023": "10100000", "2024": "10200000"}},
        )
        docs = ibge.coletar_pib_per_capita(http=http, agora=AGORA)
        sudeste = next(d for d in docs if d["regiao"] == "Sudeste")
        self.assertEqual(sudeste["ano_referencia"], 2022)
        self.assertEqual(sudeste["valor"], (500000 * 1000) / 10000000)

    def test_sem_ano_em_comum_a_regiao_fica_de_fora_sem_quebrar(self):
        http = self._http({"Sudeste": {"2020": "500000"}}, {"Sudeste": {"2023": "10000000"}})
        docs = ibge.coletar_pib_per_capita(http=http, agora=AGORA)
        self.assertEqual(docs, [])

    def test_um_documento_por_regiao(self):
        pib = {r: {"2023": "500000"} for r in ibge.REGIOES}
        pop = {r: {"2023": "10000000"} for r in ibge.REGIOES}
        docs = ibge.coletar_pib_per_capita(http=self._http(pib, pop), agora=AGORA)
        self.assertEqual({d["regiao"] for d in docs}, set(ibge.REGIOES))
        for campo in ("fonte", "url_fonte", "coletado_em", "licenca"):
            self.assertTrue(docs[0][campo])


class TestColetarRendimentoMedio(unittest.TestCase):
    def test_usa_a_classificacao_total_e_pega_o_ano_mais_recente(self):
        vistos = {}
        def http(url, params=None):
            vistos.update(params or {})
            return _resposta(ibge.RENDIMENTO_AGREGADO_ID,
                             "Rendimento médio mensal real ... habitualmente recebido no trabalho principal",
                             "Reais", {"Sudeste": {"202404": "2900.0", "202502": "3050.0"}})
        docs = ibge.coletar_rendimento_medio(http=http, agora=AGORA)
        self.assertEqual(vistos.get("classificacao"), "2[6794]")   # Sexo = Total
        sudeste = next(d for d in docs if d["regiao"] == "Sudeste")
        self.assertEqual((sudeste["valor"], sudeste["ano_referencia"]), (3050.0, 2025))
        self.assertEqual(sudeste["indicador"], "IBGE.5436.5932")
        self.assertNotIn("calculado", sudeste)   # este NÃO é calculado, veio pronto da fonte


class TestColetarCombinado(unittest.TestCase):
    def test_junta_pib_per_capita_e_rendimento(self):
        def http(url, params=None):
            if f"/{ibge.PIB_AGREGADO_ID}/" in url:
                return _resposta(ibge.PIB_AGREGADO_ID, "PIB", "Mil Reais", {"Sudeste": {"2023": "500000"}})
            if f"/{ibge.POPULACAO_AGREGADO_ID}/" in url:
                return _resposta(ibge.POPULACAO_AGREGADO_ID, "População", "Pessoas", {"Sudeste": {"2023": "10000000"}})
            if f"/{ibge.RENDIMENTO_AGREGADO_ID}/" in url:
                return _resposta(ibge.RENDIMENTO_AGREGADO_ID, "Rendimento", "Reais", {"Sudeste": {"2025": "3050.0"}})
            raise AssertionError(url)
        docs = ibge.coletar(http=http, agora=AGORA)
        indicadores = {d["indicador"] for d in docs}
        self.assertEqual(indicadores, {"IBGE.CALC.PIB_PER_CAPITA", "IBGE.5436.5932"})

    def test_ids_dos_dois_indicadores_da_mesma_regiao_nunca_colidem(self):
        # Bug real encontrado em 24/09/2026: os dois indicadores usavam o MESMO id
        # por região ("sudeste"), então gravar um sobrescrevia silenciosamente o
        # outro na mesma coleção (merge=True mescla campo a campo, e "valor",
        # "indicador" etc. têm o mesmo nome nos dois documentos).
        def http(url, params=None):
            if f"/{ibge.PIB_AGREGADO_ID}/" in url:
                return _resposta(ibge.PIB_AGREGADO_ID, "PIB", "Mil Reais", {"Sudeste": {"2023": "400000000"}})
            if f"/{ibge.POPULACAO_AGREGADO_ID}/" in url:
                return _resposta(ibge.POPULACAO_AGREGADO_ID, "População", "Pessoas", {"Sudeste": {"2023": "10000000"}})
            if f"/{ibge.RENDIMENTO_AGREGADO_ID}/" in url:
                return _resposta(ibge.RENDIMENTO_AGREGADO_ID, "Rendimento", "Reais", {"Sudeste": {"2025": "3050.0"}})
            raise AssertionError(url)
        docs = ibge.coletar(http=http, agora=AGORA)
        ids = [d["id"] for d in docs]
        self.assertEqual(len(ids), len(set(ids)), f"IDs colidindo: {ids}")


class TestColecaoPropriaEIndependente(unittest.TestCase):
    def test_colecao_e_diferente_de_paises(self):
        self.assertEqual(ibge.COLECAO, "brasil_regioes")
        self.assertNotEqual(ibge.COLECAO, "paises")


if __name__ == "__main__":
    unittest.main()
