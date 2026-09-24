# -*- coding: utf-8 -*-
"""
Testes OFFLINE: nenhuma chamada de rede. As respostas de exemplo imitam os
formatos reais das APIs (Banco Mundial e Arbeitnow).

Rodar:  python -m unittest discover -s tests -v
"""
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coletor import arbeitnow, banco_mundial, custo_vida, derivados, executar, ibge
from coletor.modelos import id_documento
from coletor.publicar import Publicador
from coletor.rede import ErroColeta
from coletor.validacao import (checar_variacao, separar_validos,
                               validar_indicador, validar_vaga)

logging.disable(logging.CRITICAL)                     # testes sem ruído de logs

CRIADO = 1789750837                                   # Unix (set/2026), como na API real
AGORA = datetime.fromtimestamp(CRIADO, timezone.utc) + timedelta(days=1)


# ------------------------------------------------------------ Banco Mundial
def linha(iso2, iso3, nome, codigo, ano, valor):
    return {"indicator": {"id": codigo, "value": "x"}, "country": {"id": iso2, "value": nome},
            "countryiso3code": iso3, "date": str(ano), "value": valor, "unit": "", "obs_status": "", "decimal": 1}


VALORES = {"NY.GDP.PCAP.CD": 30000.0, "FP.CPI.TOTL.ZG": 3.1, "PA.NUS.PPP": 0.6,
           "PA.NUS.FCRF": 0.92, "IT.NET.USER.ZS": 90.0,
           "PA.NUS.PPPC.RF": 0.8}   # só para os testes que exercitam esse código como exemplo genérico
PAISES3 = {"PT": ("PRT", "Portugal"), "DE": ("DEU", "Germany"), "CA": ("CAN", "Canada"),
           "IE": ("IRL", "Ireland"), "ES": ("ESP", "Spain"), "AE": ("ARE", "United Arab Emirates")}


def http_bm(url, params=None):
    codigo = url.rsplit("/", 1)[-1]
    linhas = []
    for iso2, (iso3, nome) in PAISES3.items():
        linhas.append(linha(iso2, iso3, nome, codigo, 2025, None))            # ano recente sem dado
        linhas.append(linha(iso2, iso3, nome, codigo, 2024, VALORES[codigo]))  # o valor a ser escolhido
        linhas.append(linha(iso2, iso3, nome, codigo, 2020, VALORES[codigo] * 0.5))
    linhas.append(linha("EU", "EUU", "European Union", codigo, 2024, 1.0))    # agregado: deve ser ignorado
    meta = {"page": 1, "pages": 1, "per_page": 200, "total": len(linhas), "lastupdated": "2026-07-13"}
    return [meta, linhas]


class TestBancoMundial(unittest.TestCase):
    def test_pega_valor_mais_recente_nao_nulo(self):
        docs = banco_mundial.coletar(http=http_bm, agora=AGORA)
        pib_pt = next(d for d in docs if d["pais"] == "Portugal" and d["indicador"] == "NY.GDP.PCAP.CD")
        self.assertEqual(pib_pt["ano_referencia"], 2024)
        self.assertEqual(pib_pt["valor"], 30000.0)
        self.assertEqual(pib_pt["defasagem_anos"], AGORA.year - 2024)

    def test_ignora_agregados_e_cobre_todos_os_pares(self):
        docs = banco_mundial.coletar(http=http_bm, agora=AGORA)
        self.assertEqual(len(docs), 6 * 6)                     # 6 países x (5 buscados + 1 calculado)
        self.assertFalse(any(d["iso2"] == "EU" for d in docs))

    def test_nivel_de_precos_e_calculado_a_partir_de_ppp_e_fcrf(self):
        docs = banco_mundial.coletar(http=http_bm, agora=AGORA)
        d = next(d for d in docs if d["pais"] == "Portugal" and d["indicador"] == "PA.NUS.PPPC.RF")
        self.assertTrue(d["calculado"])
        self.assertAlmostEqual(d["valor"], 0.6 / 0.92, places=4)
        self.assertIn("arquivada", d["metodo"])
        self.assertIn("calculado", d["fonte"].lower())

    def test_proveniencia_completa(self):
        d = banco_mundial.coletar(http=http_bm, agora=AGORA)[0]
        for campo in ("fonte", "url_fonte", "coletado_em", "licenca"):
            self.assertTrue(d[campo], campo)
        self.assertIsNone(d["verificado_em"])
        self.assertTrue(d["url_fonte"].startswith("https://api.worldbank.org/v2/country/"))

    def test_erro_http200_com_array_de_um_elemento(self):
        erro = lambda url, params=None: [{"message": [{"id": "120", "key": "Invalid value"}]}]
        with self.assertRaises(ErroColeta):
            banco_mundial.coletar(http=erro, agora=AGORA)


# ---------------------------------------------------------------- Arbeitnow
def item(slug, titulo, desc, tags, remote=False, criado=CRIADO, loc="Munich"):
    return {"slug": slug, "company_name": "MY Humancapital GmbH", "title": titulo, "description": desc,
            "remote": remote, "url": f"https://www.arbeitnow.com/jobs/companies/x/{slug}",
            "tags": tags, "job_types": [], "location": loc, "created_at": criado}


CONTATO = "<p>Rückfragen: <strong>Simon Schneider</strong> unter <strong>089 954 287 111</strong></p>"
SYSADMIN = item("it-systemadministrator-dresden-379668", "IT-Systemadministrator (m/w/d) Dresden",
                "<p>Homeoffice-Möglichkeit</p><ul><li>Sie administrieren Windows- und Linux-Umgebungen "
                "sowie Active Directory</li></ul>" + CONTATO, ["System and Network Administration"], loc="Dresden")
ARCHITEKT = item("softwarearchitekt-embedded-dresden-16573", "Softwarearchitekt Embedded Systems (m/w/d)",
                 "<p>Sehr gute Kenntnisse in C/C++ und Python</p>" + CONTATO, ["Software Development"])
SENIOR = item("senior-backend-developer-berlin-1", "Senior Backend Developer (m/w/d)",
              "<p>Python, PostgreSQL, Docker und Kubernetes auf AWS</p>", ["Software Development"], remote=True, loc="Berlin")
HAUSMEISTER = item("hausmeister-potsdam-450645", "Hausmeister (m/w/d) Potsdam",
                   "<p>Wartung von Gebäuden</p>" + CONTATO, ["Building", "Supply"])
FEM = item("berechnungsingenieur-83819", "Berechnungsingenieur Strukturanalyse (m/w/d)",
           "<p>FEM, HyperMesh; Linux-Kenntnisse von Vorteil</p>", ["Engineering"])
ANTIGA = item("it-admin-antiga-9", "IT-Administrator (m/w/d)", "<p>Linux und Active Directory</p>",
              ["System and Network Administration"], criado=CRIADO - 90 * 86400)


def http_an(paginas):
    def _http(url, params=None):
        pag = (params or {}).get("page", 1)
        if pag <= len(paginas):
            resp = {"data": paginas[pag - 1], "links": {"next": "x" if pag < len(paginas) else None}}
            return resp
        return {"data": [], "links": {"next": None}}
    return _http


class TestArbeitnow(unittest.TestCase):
    def setUp(self):
        self.docs = arbeitnow.coletar(http=http_an([[SYSADMIN, ARCHITEKT, HAUSMEISTER], [SENIOR, FEM, ANTIGA, SYSADMIN]]),
                                      agora=AGORA)
        self.por_slug = {d["id"]: d for d in self.docs}

    def test_filtra_so_ti_e_remove_antigas_e_duplicadas(self):
        titulos = sorted(d["titulo"] for d in self.docs)
        self.assertEqual(len(self.docs), 3)                    # sysadmin, arquiteto, senior dev
        self.assertNotIn("Hausmeister (m/w/d) Potsdam", titulos)
        self.assertFalse(any("Berechnungsingenieur" in t for t in titulos))   # 1 menção a Linux não basta
        self.assertFalse(any("IT-Administrator" in t for t in titulos))        # vencida (> 30 dias)

    def test_extrai_tecnologias_do_texto(self):
        sysadm = self.por_slug["arbeitnow_it-systemadministrator-dresden-379668"]
        self.assertEqual(sorted(sysadm["stack"]), ["Active Directory", "Linux (Suporte/Admin)"])
        dev = self.por_slug["arbeitnow_senior-backend-developer-berlin-1"]
        self.assertEqual(sorted(dev["stack"]), ["AWS", "Docker / Kubernetes", "Python", "SQL"])

    def test_nao_armazena_descricao_nem_dados_pessoais(self):
        bruto = json.dumps(self.docs, ensure_ascii=False)
        self.assertNotIn("Simon Schneider", bruto)
        self.assertNotIn("089 954", bruto)
        self.assertFalse(any("description" in d for d in self.docs))

    def test_senioridade_e_modalidade_inferidas_sao_marcadas(self):
        dev = self.por_slug["arbeitnow_senior-backend-developer-berlin-1"]
        self.assertEqual((dev["senioridade"], dev["senioridade_inferida"]), ("Sênior", True))
        self.assertEqual((dev["modalidade"], dev["modalidade_inferida"]), ("Remoto", False))
        sysadm = self.por_slug["arbeitnow_it-systemadministrator-dresden-379668"]
        self.assertEqual((sysadm["modalidade"], sysadm["modalidade_inferida"]), ("Híbrido", True))
        self.assertEqual(sysadm["senioridade"], "Não informada")

    def test_pais_e_salario_e_proveniencia(self):
        d = self.docs[0]
        self.assertEqual((d["pais"], d["pais_inferido"]), ("Alemanha", True))
        self.assertIsNone(d["salario_faixa_usd"])
        self.assertTrue(d["url_fonte"].startswith("https://www.arbeitnow.com/jobs/"))
        self.assertTrue(d["expira_em"] > d["publicado_em"])

    def test_documentos_passam_na_validacao(self):
        validos, rejeitados = separar_validos(self.docs, validar_vaga)
        self.assertEqual((len(validos), len(rejeitados)), (3, 0))

    def test_resposta_sem_campo_data_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            arbeitnow.coletar(http=lambda u, p=None: {"erro": "x"}, agora=AGORA)


# ---------------------------------------------------------------- validação
class TestValidacao(unittest.TestCase):
    def test_indicador_fora_da_faixa_e_rejeitado(self):
        doc = banco_mundial.coletar(http=http_bm, agora=AGORA)[0]
        self.assertEqual(validar_indicador(doc), [])
        ruim = {**doc, "indicador": "FP.CPI.TOTL.ZG", "valor": 900.0}
        self.assertTrue(any("fora da faixa" in e for e in validar_indicador(ruim)))

    def test_vaga_com_descricao_e_rejeitada(self):
        d = arbeitnow.coletar(http=http_an([[SYSADMIN]]), agora=AGORA)[0]
        self.assertTrue(any("descrição" in e for e in validar_vaga({**d, "description": "<p>..</p>"})))

    def test_variacao_grande_vai_para_revisao(self):
        novos = [{"id": "a", "valor": 100.0}, {"id": "b", "valor": 10.0}, {"id": "c", "valor": 5.0}]
        antes = {"a": {"valor": 95.0}, "b": {"valor": 20.0}}          # b caiu 50%; c é novo
        aprovados, pendentes = checar_variacao(novos, antes, limite=0.30)
        self.assertEqual([d["id"] for d in aprovados], ["a", "c"])
        self.assertEqual([d["id"] for d in pendentes], ["b"])
        self.assertEqual(pendentes[0]["valor_anterior"], 20.0)


# -------------------------------------------------------------------- radar
def vaga_com(stack):
    return {"stack": stack, "publicado_em": "2026-09-01T00:00:00Z"}


class TestRadar(unittest.TestCase):
    def test_amostra_pequena_nao_publica(self):
        self.assertEqual(derivados.calcular_radar([vaga_com(["Python"])] * 5), [])

    def test_indice_relativo_com_maximo_100(self):
        vagas = [vaga_com(["Python", "SQL"])] * 20 + [vaga_com(["Linux (Suporte/Admin)"])] * 10 + [vaga_com([])] * 10
        radar = {d["tecnologia"]: d for d in derivados.calcular_radar(vagas)}
        self.assertEqual(radar["Python"]["demanda"], 100)
        self.assertEqual(radar["Linux (Suporte/Admin)"]["demanda"], 50)
        self.assertEqual(radar["Terraform"]["demanda"], 0)
        self.assertEqual(radar["Python"]["n_amostra"], 40)
        self.assertEqual(len(radar), 8)                        # as 8 tecnologias de data.py
        self.assertNotIn("/", radar["Python"]["id"])


# ----------------------------------------------------------------- utilitários
class TestIds(unittest.TestCase):
    def test_id_nunca_tem_barra(self):
        # o seed_firestore.py original geraria "javascript_/_typescript" (inválido no Firestore)
        self.assertEqual(id_documento("JavaScript / TypeScript"), "javascript_-_typescript")
        self.assertEqual(id_documento("Suporte / Redes"), "suporte_-_redes")
        self.assertEqual(id_documento("Linux (Suporte/Admin)"), "linux_(suporte-admin)")
        self.assertNotIn("/", id_documento("a/b/c"))


# ------------------------------------------------------- publicador + executor
class TestPublicadorEExecutor(unittest.TestCase):
    def test_expirar_remove_vencidas_no_modo_teste(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("vagas", [{"id": "velha", "expira_em": "2026-01-01T00:00:00Z"},
                                 {"id": "nova", "expira_em": "2026-12-01T00:00:00Z"}])
            self.assertEqual(pub.expirar("vagas", agora="2026-09-18T00:00:00Z"), 1)
            self.assertEqual(sorted(pub.ler("vagas")), ["nova"])

    def test_gravar_mescla_com_o_que_ja_existe(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("c", [{"id": "1", "v": 1}])
            pub.gravar("c", [{"id": "2", "v": 2}, {"id": "1", "v": 10}])
            self.assertEqual({k: d["v"] for k, d in pub.ler("c").items()}, {"1": 10, "2": 2})

    def test_gravar_mescla_campo_a_campo_sem_apagar_o_resto_do_documento(self):
        # Igual ao merge=True real do Firestore: um patch com só ALGUNS campos
        # não pode apagar os campos que já estavam no documento.
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            pub.gravar("paises", [{"id": "portugal", "pais": "Portugal", "regiao": "Europa",
                                   "idioma": "Português", "custo_vida_mensal_usd": 1100}])
            pub.gravar("paises", [{"id": "portugal", "custo_vida_mensal_usd": 2850}])  # só este campo
            portugal = pub.ler("paises")["portugal"]
            self.assertEqual(portugal["custo_vida_mensal_usd"], 2850)   # atualizado
            self.assertEqual(portugal["regiao"], "Europa")               # preservado
            self.assertEqual(portugal["idioma"], "Português")            # preservado

    def test_execucao_completa_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            r1 = executar.executar_banco_mundial(pub, http=http_bm)
            r2 = executar.executar_arbeitnow(pub, http=http_an([[SYSADMIN, ARCHITEKT, SENIOR, HAUSMEISTER]]))
            self.assertEqual(r1, {"coletados": 36, "publicados": 36, "rejeitados": 0, "pendentes": 0,
                                 "custo_vida_estimado_publicado": 6})
            self.assertEqual((r2["publicados"], r2["radar_publicado"]), (3, False))   # amostra < 30
            self.assertTrue(os.path.exists(os.path.join(tmp, "indicadores_pais.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "vagas.json")))
            # 2ª execução: valores iguais -> nenhuma pendência de revisão
            r3 = executar.executar_banco_mundial(pub, http=http_bm)
            self.assertEqual(r3["pendentes"], 0)

    def test_falha_de_fonte_devolve_codigo_de_saida_1_e_nao_apaga_dados(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            executar.executar_banco_mundial(pub, http=http_bm)
            antes = pub.ler("indicadores_pais")
            original = executar.FONTES["banco_mundial"]
            executar.FONTES["banco_mundial"] = lambda p: banco_mundial.coletar(
                http=lambda u, params=None: [{"message": "erro"}])
            try:
                codigo = executar.main(["--fonte", "banco_mundial", "--saida", tmp])
            finally:
                executar.FONTES["banco_mundial"] = original
            self.assertEqual(codigo, 1)
            self.assertEqual(pub.ler("indicadores_pais"), antes)      # dados anteriores intactos


# ------------------------------------------- falhas reais observadas em campo
ERRO_175 = [{"message": [{"id": "175", "key": "Invalid format",
                          "value": "The indicator was not found. It may have been deleted or archived."}]}]


def http_bm_com_um_indicador_invalido(invalido):
    def _http(url, params=None):
        if url.rstrip("/").endswith(invalido) or f"/indicator/{invalido}" in url:
            return ERRO_175
        return http_bm(url, params)
    return _http


class TestIndicadorInvalido(unittest.TestCase):
    def test_um_indicador_invalido_nao_derruba_os_outros(self):
        docs, falhas = banco_mundial.coletar_com_relatorio(
            http=http_bm_com_um_indicador_invalido("IT.NET.USER.ZS"), agora=AGORA)
        # 4 dos 5 indicadores buscados (24) + o calculado PA.NUS.PPPC.RF (6), que não depende de IT.NET.USER.ZS
        self.assertEqual(len(docs), 6 * 4 + 6)
        self.assertEqual(list(falhas), ["IT.NET.USER.ZS"])
        self.assertIn("IT.NET.USER.ZS", falhas["IT.NET.USER.ZS"])       # a mensagem diz QUAL falhou

    def test_se_todos_falharem_levanta_erro(self):
        with self.assertRaises(ErroColeta):
            banco_mundial.coletar(http=lambda u, p=None: ERRO_175, agora=AGORA)

    def test_execucao_fica_parcial_e_registra_o_indicador_falho(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            r = executar.executar_banco_mundial(pub, http=http_bm_com_um_indicador_invalido("IT.NET.USER.ZS"))
            self.assertEqual(r["publicados"], 6 * 4 + 6)
            self.assertIn("IT.NET.USER.ZS", r["indicadores_falhos"])

    def test_verificacao_do_catalogo_aponta_o_codigo_inexistente(self):
        def catalogo(url, params=None):
            if url.endswith("/FANTASIA.001"):
                return ERRO_175
            codigo = url.rsplit("/", 1)[-1]
            return [{"page": 1, "pages": 1}, [{"id": codigo, "name": f"Indicador {codigo}"}]]
        indicadores = {"FANTASIA.001": ("x", "x"), "NY.GDP.PCAP.CD": ("x", "x")}
        r = banco_mundial.verificar_indicadores(indicadores=indicadores, http=catalogo)
        self.assertFalse(r["FANTASIA.001"][0])
        self.assertTrue(r["NY.GDP.PCAP.CD"][0])


class TestPublicarSemCredencial(unittest.TestCase):
    def test_publicar_sem_credencial_falha_cedo_com_codigo_2_e_sem_traceback(self):
        antigo_cwd = os.getcwd()
        antigo_env = os.environ.pop("FIREBASE_SERVICE_ACCOUNT", None)
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)                                   # pasta sem serviceAccountKey.json
            try:
                self.assertEqual(executar.main(["--fonte", "todas", "--publicar", "--saida", tmp]), 2)
            finally:
                os.chdir(antigo_cwd)
                if antigo_env is not None:
                    os.environ["FIREBASE_SERVICE_ACCOUNT"] = antigo_env


# ------------------------------------------------ consulta ao Banco Mundial (campo)
class TestConsultaBancoMundial(unittest.TestCase):
    def test_montar_url_mantem_dois_pontos_e_ponto_e_virgula_literais(self):
        from coletor.rede import montar_url
        u = montar_url("https://x/country/PT;DE/indicator/A", {"format": "json", "date": "2016:2026"})
        self.assertIn("date=2016:2026", u)
        self.assertNotIn("%3A", u)
        self.assertIn("PT;DE", u)

    def test_montar_url_expande_lista_em_parametros_repetidos(self):
        # BUG REAL encontrado em 22/09/2026: sem doseq=True, uma lista virava um
        # único parâmetro com a repr do Python ("geo=['PT', 'DE']"), que a fonte
        # não reconhece como código nenhum — a consulta ao Eurostat com vários
        # países de uma vez voltava 0 resultados, sem erro.
        from coletor.rede import montar_url
        u = montar_url("https://x", {"geo": ["PT", "DE", "IE", "ES"], "na_item": "PLI_EU27_2020"})
        self.assertEqual(u.count("geo=PT") + u.count("geo=DE") + u.count("geo=IE") + u.count("geo=ES"), 4)
        self.assertNotIn("[", u)
        self.assertNotIn("%5B", u)   # "[" codificado — sinal do bug antigo

    def test_obter_json_manda_a_lista_como_parametros_repetidos_de_verdade(self):
        # Testa o caminho REAL (obter_json -> montar_url -> requests.get), não um
        # `http` de mentira — é exatamente o que os testes de coletar() com stub
        # nunca cobriram, e por isso o bug passou despercebido nos testes offline.
        import unittest.mock as mock
        from coletor.rede import obter_json

        resposta = mock.Mock(status_code=200)
        resposta.json.return_value = {"ok": True}
        resposta.raise_for_status = lambda: None
        with mock.patch("requests.get", return_value=resposta) as get_mock:
            obter_json("https://x", {"geo": ["PT", "DE"], "na_item": "PLI_EU27_2020"})
        url_chamada = get_mock.call_args[0][0]
        self.assertIn("geo=PT", url_chamada)
        self.assertIn("geo=DE", url_chamada)
        self.assertNotIn("[", url_chamada)

    def test_se_uma_forma_de_consulta_for_recusada_tenta_a_proxima(self):
        chamadas = []

        def http(url, params=None):
            chamadas.append(dict(params or {}))
            if "mrnev" in (params or {}):                 # a fonte recusa a 1ª forma
                return ERRO_175
            return http_bm(url, params)

        docs, falhas = banco_mundial.coletar_com_relatorio(http=http, agora=AGORA)
        self.assertEqual((len(docs), falhas), (36, {}))
        # depois de descobrir a forma que funciona (mrv=5), ela vira a primeira tentativa
        usadas = [("mrnev" in c, "mrv" in c) for c in chamadas]
        self.assertEqual(usadas[0], (True, False))        # 1º indicador: testa mrnev, falha
        self.assertEqual(usadas[1], (False, True))        # ... e cai em mrv
        self.assertEqual(usadas[2], (False, True))        # 2º indicador já começa por mrv

    def test_diagnostico_mostra_resposta_de_cada_forma_de_consulta(self):
        def http(url, params=None):
            if "date" in (params or {}):
                return ERRO_175                            # simula: só o intervalo de datas é recusado
            return http_bm(url, params)
        res = banco_mundial.diagnosticar(http=http, ano=2026)
        por_rotulo = {r: ok for ok, r, _, _ in res}
        self.assertFalse(por_rotulo["1 país (PT), intervalo de datas"])
        self.assertTrue(por_rotulo["1 país (PT), mrnev=1"])
        self.assertTrue(any("date=2016:2026" in alvo for _, _, alvo, _ in res))


class TestRadarViesEInspecao(unittest.TestCase):
    def test_radar_expoe_concentracao_por_empresa_e_aceita_limite(self):
        vagas = [{"stack": ["Python"], "empresa": "Agencia", "publicado_em": "2026-09-01T00:00:00Z"}] * 40 + \
                [{"stack": ["SQL"], "empresa": f"Emp{i}", "publicado_em": "2026-09-01T00:00:00Z"} for i in range(20)]
        radar = {d["tecnologia"]: d for d in derivados.calcular_radar(vagas)}
        self.assertEqual(radar["Python"]["empresas_distintas"], 21)
        self.assertAlmostEqual(radar["Python"]["concentracao_maior_empresa"], 40 / 60, places=3)
        self.assertEqual(radar["Python"]["demanda"], 100)
        limitado = {d["tecnologia"]: d for d in derivados.calcular_radar(vagas, min_amostra=10, max_por_empresa=5)}
        self.assertEqual(limitado["Python"]["vagas_com_mencao"], 5)          # agência limitada a 5
        self.assertEqual(limitado["SQL"]["vagas_com_mencao"], 20)
        self.assertEqual(limitado["SQL"]["demanda"], 100)                    # agora SQL lidera

    def test_inspecionar_imprime_resumo(self):
        import contextlib, io
        from coletor import inspecionar
        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            executar.executar_banco_mundial(pub, http=http_bm)
            executar.executar_arbeitnow(pub, http=http_an([[SYSADMIN, ARCHITEKT, SENIOR]]))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                inspecionar.main([tmp])
            txt = buf.getvalue()
        for trecho in ("=== VAGAS (3) ===", "empresas mais frequentes", "=== INDICADORES DOS PAÍSES (36) ===", "Portugal:"):
            self.assertIn(trecho, txt)


# ------------------------------- correções vindas dos dados reais (set/2026)
def _vaga(titulo="Backend Developer", desc="", tags=("Software Development",), loc="Berlin", remote=False):
    return arbeitnow.normalizar(item("x-" + titulo[:8].replace(" ", ""), titulo, desc, list(tags), remote=remote, loc=loc),
                                "2026-09-19T00:00:00Z", AGORA)


class TestCorrecoesDadosReais(unittest.TestCase):
    def test_pais_deduzido_da_localizacao(self):
        casos = {"London": "Reino Unido", "London Office": "Reino Unido", "Paris": "França", "Munich": "Alemanha",
                 "Berlin, Germany": "Alemanha", "Dublin": "Irlanda", "Lisbon": "Portugal", "Zürich": "Suíça",
                 "Remote": arbeitnow.NAO_IDENTIFICADO, "": arbeitnow.NAO_IDENTIFICADO, None: arbeitnow.NAO_IDENTIFICADO}
        for loc, esperado in casos.items():
            self.assertEqual(arbeitnow.inferir_pais(loc), esperado, loc)

    def test_pais_deduzido_de_cidades_menores_vistas_em_dados_reais(self):
        # confirmadas via python -m coletor.inspecionar em 21-22/09/2026 (antes ficavam "Não identificado")
        alemas = ["Braunschweig", "Grasbrunn", "Landsberg am Lech", "Hürth", "Westerstede",
                  "Gilching", "Leverkusen", "Pinneberg", "Kempten", "Wolfsburg",
                  "Bochum", "Eilsleben", "Dinslaken", "Tholey", "Mainz"]
        for cidade in alemas:
            self.assertEqual(arbeitnow.inferir_pais(cidade), "Alemanha", cidade)
        self.assertEqual(arbeitnow.inferir_pais("Marlow"), "Reino Unido")   # Marlow, Buckinghamshire
        self.assertEqual(arbeitnow.inferir_pais("Cardiff"), "Reino Unido")  # capital do País de Gales
        # sem indício de país: continuam não identificadas (não é um erro do mapeamento)
        self.assertEqual(arbeitnow.inferir_pais("Remote job"), arbeitnow.NAO_IDENTIFICADO)
        self.assertEqual(arbeitnow.inferir_pais(""), arbeitnow.NAO_IDENTIFICADO)

    def test_vaga_de_londres_nao_e_alemanha(self):
        d = _vaga(loc="London")
        self.assertEqual((d["pais"], d["pais_inferido"]), ("Reino Unido", True))
        d2 = _vaga(loc="Somewhere Unknown")
        self.assertEqual((d2["pais"], d2["pais_inferido"]), (arbeitnow.NAO_IDENTIFICADO, False))

    def test_mencao_solta_a_remote_nao_vira_hibrido(self):
        self.assertEqual(_vaga(desc="<p>We are a remote-first company with great culture</p>")["modalidade"], "Não informada")
        self.assertEqual(_vaga(desc="<p>Our hybrid work model</p>")["modalidade"], "Híbrido")
        self.assertEqual(_vaga(desc="<p>2 days per week in the office</p>")["modalidade"], "Híbrido")
        self.assertEqual(_vaga(desc="<p>Homeoffice-Möglichkeit</p>")["modalidade"], "Híbrido")
        self.assertEqual(_vaga(remote=True)["modalidade"], "Remoto")

    def test_tags_reais_de_ti_e_engenharia_generica(self):
        self.assertIsNotNone(_vaga(titulo="Platform Specialist", tags=("IT",)))
        self.assertIsNotNone(_vaga(titulo="Platform Specialist", tags=("Technology",)))
        self.assertIsNone(_vaga(titulo="Maschinenbauingenieur", tags=("Engineering",)))   # "Engineering" sozinho não basta

    def test_pleno_e_junior(self):
        self.assertEqual(arbeitnow.inferir_senioridade("Mid-Level Data Engineer"), "Pleno")
        self.assertEqual(arbeitnow.inferir_senioridade("Junior Data Analyst"), "Júnior")
        self.assertEqual(arbeitnow.inferir_senioridade("Data Analyst"), "Não informada")


class TestBancoMundialFonteDoCatalogo(unittest.TestCase):
    def test_se_a_consulta_padrao_falha_tenta_com_source_do_catalogo(self):
        def http(url, params=None):
            if "/country/" not in url:                                # catálogo
                return [{"page": 1, "pages": 1}, [{"id": "PA.NUS.PPPC.RF", "name": "Price level ratio",
                                                   "source": {"id": "2", "value": "World Development Indicators"}}]]
            if "source" not in (params or {}):
                return ERRO_175                                       # sem source: recusado
            return http_bm(url, params)
        docs, falhas = banco_mundial.coletar_com_relatorio(
            http=http, indicadores={"PA.NUS.PPPC.RF": ("Nível de preços", "razão")}, agora=AGORA)
        self.assertEqual((len(docs), falhas), (6, {}))

    def test_testar_indicador_relata_catalogo_e_dados(self):
        def http(url, params=None):
            if "/indicator/" in url and "/country/" not in url:
                return [{"page": 1}, [{"name": "Price level ratio", "source": {"id": "2", "value": "WDI"}}]]
            return ERRO_175 if "source" not in (params or {}) else http_bm(url, params)
        r = banco_mundial.testar_indicador("PA.NUS.PPPC.RF", http=http)
        self.assertTrue(r["no_catalogo"])
        self.assertEqual([ok for ok, _, _ in r["testes"]], [False, True])


class TestExecutarCustoVida(unittest.TestCase):
    def test_custo_vida_esta_no_orquestrador_e_grava_na_mesma_colecao_do_banco_mundial(self):
        self.assertIn("custo_vida", executar.FONTES)
        self.assertEqual(custo_vida.COLECAO, banco_mundial.COLECAO)   # "indicadores_pais", mesma coleção


class TestExecutarIbge(unittest.TestCase):
    def test_ibge_esta_no_orquestrador_e_usa_colecao_propria(self):
        self.assertIn("ibge", executar.FONTES)
        self.assertNotEqual(ibge.COLECAO, banco_mundial.COLECAO)
        self.assertEqual(ibge.COLECAO, "brasil_regioes")

    def test_execucao_completa_offline(self):
        def http(url, params=None):
            if f"/{ibge.PIB_AGREGADO_ID}/" in url:
                return [{
                    "id": ibge.PIB_AGREGADO_ID, "variavel": "PIB", "unidade": "Mil Reais",
                    "resultados": [{"series": [
                        # 400.000.000 Mil Reais ÷ 10.000.000 pessoas = R$ 40.000/ano per capita (realista)
                        {"localidade": {"id": v, "nome": k}, "serie": {"2023": "400000000"}}
                        for k, v in ibge.REGIOES.items()]}]}]
            if f"/{ibge.POPULACAO_AGREGADO_ID}/" in url:
                return [{
                    "id": ibge.POPULACAO_AGREGADO_ID, "variavel": "População", "unidade": "Pessoas",
                    "resultados": [{"series": [
                        {"localidade": {"id": v, "nome": k}, "serie": {"2023": "10000000"}}
                        for k, v in ibge.REGIOES.items()]}]}]
            if f"/{ibge.RENDIMENTO_AGREGADO_ID}/" in url:
                return [{
                    "id": ibge.RENDIMENTO_AGREGADO_ID, "variavel": "Rendimento", "unidade": "Reais",
                    "resultados": [{"series": [
                        {"localidade": {"id": v, "nome": k}, "serie": {"2025": "3000.0"}}
                        for k, v in ibge.REGIOES.items()]}]}]
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            resumo = executar.executar_ibge(pub, http=http)
            self.assertEqual(resumo, {"coletados": 10, "publicados": 10, "rejeitados": 0})   # 5 regiões x 2 indicadores
            gravados = pub.ler("brasil_regioes")
            self.assertEqual(len(gravados), 10)
            self.assertTrue(any(d["indicador"] == "IBGE.CALC.PIB_PER_CAPITA" for d in gravados.values()))
            self.assertTrue(any(d["indicador"] == "IBGE.5436.5932" for d in gravados.values()))

    def test_execucao_completa_das_3_fontes_offline(self):
        def http_eurostat(url, params=None):
            doc = dict({"version": "2.0", "class": "dataset", "id": ["geo", "time"], "size": [4, 1]})
            doc["dimension"] = {
                "na_item": {"category": {"label": {"PLI_EU27_2020": "Price level indices"}}},
                "ppp_cat": {"category": {"label": {"E011": "Household final consumption expenditure"}}},
                "geo": {"category": {"index": {"PT": 0, "DE": 1, "IE": 2, "ES": 3}}},
                "time": {"category": {"index": {"2025": 0}}},
            }
            doc["value"] = {"0": 65.0, "1": 98.0, "2": 87.0, "3": 74.0}
            return doc

        with tempfile.TemporaryDirectory() as tmp:
            pub = Publicador(dry_run=True, saida=tmp)
            r_bm = executar.executar_banco_mundial(pub, http=http_bm)
            r_cv = executar.executar_custo_vida(pub, http=http_eurostat)
            r_an = executar.executar_arbeitnow(pub, http=http_an([[SYSADMIN, ARCHITEKT, SENIOR]]))
            self.assertEqual(r_cv["publicados"], 4)   # PT, DE, IE, ES
            self.assertEqual((r_bm["publicados"], r_an["publicados"]), (36, 3))
            # os dois indicadores (Banco Mundial + Eurostat) convivem na mesma coleção
            todos = pub.ler("indicadores_pais")
            self.assertEqual(len(todos), 36 + 4)
            self.assertTrue(any(d["indicador"] == "EUROSTAT.PLI_EU27_2020" for d in todos.values()))

if __name__ == "__main__":
    unittest.main()
