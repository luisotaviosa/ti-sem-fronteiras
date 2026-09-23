# Coletor automático: TI Sem Fronteiras (esqueleto)

Coleta dados de fontes abertas, valida, registra a origem de cada dado e publica no Firestore.
O app Streamlit continua **só lendo** o Firestore.

```
API → coletor → validação → (variação > 30%? → revisão) → Firestore → app
                                                     └─ falhou? mantém o último conjunto válido
```

## O que já está pronto

| Fonte | Coleção | O que gera |
|---|---|---|
| Banco Mundial (API oficial, sem chave) | `indicadores_pais` | PIB per capita, inflação, nível de preços, câmbio e acesso à Internet dos 6 países do protótipo |
| Eurostat (API oficial, sem chave) | `indicadores_pais` | Nível de preços do consumo das famílias (EU27_2020=100), só Portugal/Alemanha/Irlanda/Espanha |
| Arbeitnow (API pública, sem chave) | `vagas` | Vagas de TI, com tecnologias extraídas do texto |
| (calculado das vagas) | `radar_tecnologias` | Índice 0–100 por tecnologia, com o método e o tamanho da amostra |

**Não coberto:** custo de vida como valor absoluto em USD/mês (Eurostat e Banco Mundial só dão índices relativos, não uma cifra pronta), salário médio em TI, vistos e trilhas (curadoria humana). Veja "Próximos passos".

## Como rodar (modo teste, sem Firebase)

Nesta pasta ainda não há ambiente virtual (o do app fica na pasta do app). Na primeira vez:

```bash
python3 -m venv .venv                          # se falhar: sudo apt install python3-venv python3-full
source .venv/bin/activate                      # o prompt passa a mostrar (.venv)
pip install -r requirements-coletor.txt
python -m unittest discover -s tests -v        # 72 testes offline (1 pode ficar "skipped" se faltar `firebase-admin` ou se o `seed_firestore.py` na pasta ainda for uma versão antiga sem `id_seguro`) (não usam a internet)
python -m coletor.executar --fonte todas       # consulta as APIs e grava JSON em saida/ (não toca no Firestore)
```

Nas vezes seguintes basta `source .venv/bin/activate`. Os testes rodam até sem instalar nada
(`python3 -m unittest discover -s tests`), pois só usam a biblioteca padrão do Python.

**Onde colocar o coletor:** para o agendamento no GitHub funcionar, `coletor/`, `tests/`,
`.github/` e `requirements-coletor.txt` precisam estar no **mesmo repositório do app**.
Copie-os para a pasta do app e use o `.venv` que já existe lá:

```bash
cd ~/IFS/SIRITEC/coletor_ti_sem_fronteiras
cp -r coletor tests .github requirements-coletor.txt README_COLETOR.md ~/IFS/SIRITEC/prototipo/ti_sem_fronteiras/
cd ~/IFS/SIRITEC/prototipo/ti_sem_fronteiras
source .venv/bin/activate
pip install -r requirements-coletor.txt
echo "saida/" >> .gitignore
```

(O `seed_firestore.py` corrigido deste pacote substitui o do app: faça uma cópia do original antes.)

Depois de conferir `saida/*.json`, para publicar de verdade (use **primeiro um projeto Firebase de teste**):

```bash
python -m coletor.executar --fonte todas --publicar    # lê serviceAccountKey.json ou FIREBASE_SERVICE_ACCOUNT
```

**Diagnóstico do Banco Mundial:** `python -m coletor.banco_mundial --verificar` consulta o catálogo da fonte e
diz, para cada código de indicador, se ele existe. Se um indicador for recusado (ex.: "The indicator was not
found. It may have been deleted or archived"), a coleta **continua com os demais** e a execução fica com status
`parcial`, listando o(s) indicador(es) falho(s) em `saida/_coleta_banco_mundial.json`. Para trocar um indicador,
edite o dicionário `INDICADORES` em `coletor/banco_mundial.py` (e a faixa plausível em `validacao.py`).

**Consulta do Banco Mundial:** o coletor tenta formas equivalentes de pedir o dado mais recente
(`mrnev=1`, depois `mrv=5`, depois intervalo de datas) e usa a primeira que a fonte aceitar. Se a fonte recusar
a consulta (erro 175, "indicator not found"), rode `python -m coletor.banco_mundial --verificar --diagnostico`:
ele mostra, para cada forma de consulta, a URL testada e a resposta recebida.

**Nível de preços (`PA.NUS.PPPC.RF`): calculado, não buscado pronto.** A série oficial vem de uma base *arquivada* (source 57: "WDI Database Archives") e a API recusa os dados mesmo com `source=`, confirmado em 21/09/2026. A própria definição do indicador é "PPC do PIB (`PA.NUS.PPP`) ÷ câmbio oficial (`PA.NUS.FCRF`)", e os dois componentes estão na base ativa — por isso o valor é calculado a partir deles. O documento carrega `calculado: true` e `metodo` explicando a conta.

**Investigar um indicador específico:** `python -m coletor.banco_mundial --testar PA.NUS.PPPC.RF PA.NUS.PPP` mostra, para cada código, se está no catálogo, de qual base vem e se a fonte serve os dados (com e sem `source=`). Se o catálogo diz que existe mas a fonte não serve os dados, troque o indicador em `INDICADORES`.

**Conferir a qualidade dos dados:** `python -m coletor.inspecionar` resume o que está em `saida/` (empresas que
dominam a amostra, cobertura de tecnologias, radar, indicadores). Se uma agência de recrutamento concentrar as
vagas, defina `RADAR_MAX_POR_EMPRESA = 5` em `coletor/executar.py`.

**`--publicar` exige credencial do Firebase** (`serviceAccountKey.json` ou `FIREBASE_SERVICE_ACCOUNT`). Sem ela,
o coletor avisa logo no início (código de saída 2). Para testar sem Firebase, rode **sem** `--publicar`.

**Atualização de 22/09/2026, 3ª rodada:** adicionadas Bochum, Eilsleben, Dinslaken, Tholey e Mainz (cidades alemãs, confirmadas). O custo de vida via Eurostat também já está funcionando (ver seção própria abaixo) — o problema era um bug de rede (lista de países mal codificada na URL), não os códigos do indicador.

**Atualização de 21/09/2026, 2ª rodada:** adicionada Cardiff (capital do País de Gales, Reino Unido). "Roku" apareceu com 12% das vagas nesta coleta — abaixo do limite de 30% que dispara o aviso de concentração, mas vale acompanhar se crescer.

**Atualização de 21/09/2026 (rodada de dados reais):** confirmadas e adicionadas 10 cidades alemãs menores (Braunschweig, Grasbrunn, Landsberg am Lech, Hürth, Westerstede, Gilching, Leverkusen, Pinneberg, Kempten, Wolfsburg) e Marlow (Reino Unido — confirmado por busca, não é cidade alemã apesar do nome curto). "Remote job" e localização em branco continuam, corretamente, como "Não identificado": não há indício de país nesses casos.

**Localizações que não viraram país** ("Remote", "Anywhere", cidade fora da lista) aparecem em uma seção própria do `python -m coletor.inspecionar`, com a contagem de cada uma. Se aparecer alguma, envie essa lista de volta: é assim que a lista de cidades (`_CIDADES` em `arbeitnow.py`) cresce com dados reais, em vez de suposição.

Para descobrir as tags reais da Arbeitnow (e ajustar `TAGS_TI` em `arbeitnow.py`):
`python -m coletor.arbeitnow --tags`

## Formato dos documentos

Todo documento carrega a **proveniência**: `fonte`, `url_fonte`, `coletado_em`, `verificado_em`, `licenca`, `n_amostra`.

```json
{ "id": "bm_pt_ny.gdp.pcap.cd", "pais": "Portugal", "iso2": "PT", "indicador": "NY.GDP.PCAP.CD",
  "descricao": "PIB per capita", "unidade": "US$ correntes", "valor": 27000.5,
  "ano_referencia": 2024, "defasagem_anos": 2,
  "fonte": "Banco Mundial (World Development Indicators)", "url_fonte": "https://api.worldbank.org/v2/country/PT/indicator/NY.GDP.PCAP.CD?...",
  "coletado_em": "2026-09-18T12:00:00Z", "verificado_em": null, "licenca": "CC BY 4.0 (confirmar ...)", "n_amostra": null }
```

```json
{ "id": "arbeitnow_it-systemadministrator-dresden-379668", "titulo": "IT-Systemadministrator (m/w/d) Dresden",
  "empresa": "…", "pais": "Alemanha", "pais_inferido": true, "localizacao": "Dresden",
  "modalidade": "Híbrido", "modalidade_inferida": true, "senioridade": "Não informada", "senioridade_inferida": false,
  "stack": ["Linux (Suporte/Admin)", "Active Directory"], "salario_faixa_usd": null,
  "publicado_em": "…", "expira_em": "…",
  "fonte": "Arbeitnow (Job Board API)", "url_fonte": "https://www.arbeitnow.com/jobs/…",
  "coletado_em": "…", "verificado_em": null, "licenca": "…", "n_amostra": null }
```

Campos terminados em `_inferido/_inferida` foram **deduzidos por regra**, não informados pela fonte.

## Decisões que vieram da resposta real da Arbeitnow

* **Modalidade "Sênior" também cobre "Head of", "Staff" e "Chief"** (cargos de liderança técnica), além de "Senior" e "Lead".
* **Sem campo de país, e as vagas não são só da Alemanha** (nos dados reais há muitas de Londres e Paris): o país é deduzido do texto de `location` (nome de país ou cidade de uma lista curta). Sem correspondência, fica "Não identificado". Para cobrir mais cidades, edite `_CIDADES` em `arbeitnow.py`.
* **`tags` são categorias amplas** ("Software Development", "HR"), não tecnologias: as tecnologias saem de um dicionário aplicado ao texto.
* **A descrição traz nome e telefone de recrutadores:** por isso ela **não é armazenada** (LGPD e direitos autorais). Só ficam os metadados, as tecnologias e o link.
* **Sem salário:** `salario_faixa_usd = null`.
* **Modalidade "Híbrido" é deduzida** só por sinais específicos ("hybrid", "home office", "2 dias por semana no escritório"); a menção solta a "remote" no texto não conta. `Remoto` vem do campo `remote` da API.
* **Muitas vagas não são de TI:** o filtro usa tag de TI, palavra de TI no título ou 2+ tecnologias no texto. Prefere-se precisão a cobertura (vagas como "1st-Level-Support" com tag "Customer Service" podem ficar de fora).

## Ajustes necessários no app — já feitos

As três pendências abaixo (registradas quando este README foi escrito, antes do
`app.py` ser atualizado) já foram implementadas e entregues:

1. ~~`app.py` mostra `USD {salario_faixa_usd}/mês`; com `null` aparece "None".~~
   Corrigido: mostra "salário não informado".
2. ~~Vagas passam a ter `senioridade`/`modalidade` = "Não informada"~~ — já é uma
   opção normal nos filtros.
3. ~~Exibir `fonte` e `coletado_em`~~ — aparece na ficha do país e nos cartões de
   vaga, junto com o link para a vaga original e os selos "(inferido)"/"(inferida)".

## Correção importante no seed

O `seed_firestore.py` original gera IDs com "/" (`javascript_/_typescript`, `docker_/_kubernetes`, `linux_(suporte/admin)`, `suporte_/_redes`), que o Firestore **não aceita**: a carga inicial falharia no radar. Use o `seed_firestore.py` deste pacote (mesma lógica, com `id_seguro`).

## Agendamento e segurança

* `.github/workflows/coleta.yml`: toda segunda, 06:00 UTC, e sob demanda. Segredo: `FIREBASE_SERVICE_ACCOUNT`. Em repositório **público**, o GitHub desativa agendamentos após 60 dias sem atividade.
* **Regras do Firestore:** troque o "modo teste" por leitura pública e **escrita negada** ao cliente; só a conta de serviço (esta rotina) escreve.
* Nunca suba `serviceAccountKey.json` (já está no `.gitignore`); adicione também `saida/` e `.venv/`.

## O que NÃO foi testado

* A gravação real no Firestore (`Publicador` com `dry_run=False`) e o workflow no GitHub: valide em um projeto de teste.
* Chamadas de rede reais: os testes usam respostas de exemplo com os formatos verificados. A paginação da Arbeitnow (`links.next`, parâmetro `page`) segue o padrão da API, mas confirme na primeira execução.

## Custo de vida — concluído (Eurostat), com uma limitação conhecida

`coletor/custo_vida.py` já está integrado em `executar.py` (`--fonte custo_vida`),
gravando na mesma coleção `indicadores_pais` do Banco Mundial. Duas rodadas de
descoberta confirmaram os códigos reais:

- `na_item = PLI_EU27_2020` — nível de preços, índice EU27_2020=100.
- `ppp_cat = E011` — despesa das famílias (Household final consumption expenditure),
  e não `A01` (Actual Individual Consumption). A diferença importa: AIC soma também
  serviços públicos consumidos individualmente (saúde e educação públicas, mesmo
  quando gratuitas no ponto de uso), o que infla o índice em países com forte
  provisão pública. Para quem está se mudando, o que pesa no orçamento é o que sai
  do próprio bolso — mais perto de E011.

**Limitação que continua valendo:** é um ÍNDICE relativo (EU27_2020=100), não um
valor em USD/mês. Por isso ele entra como mais um indicador complementar na ficha do
país, sem substituir `custo_vida_mensal_usd` — transformar um índice relativo em
valor absoluto exigiria uma referência de baseline que este dataset não fornece
sozinho (ver "Próximos passos").

**Cobertura:** só Portugal, Alemanha, Irlanda e Espanha — o Eurostat não publica
para Canadá nem Emirados Árabes Unidos, que continuam com o nível de preços já
calculado do Banco Mundial (`PA.NUS.PPPC.RF`) como única referência.

## Custo de vida (Eurostat): bug real encontrado e corrigido — não era o código do indicador

A coleta real de 22/09/2026 devolveu 0 documentos. O diagnóstico (`--testar`) provou
que `na_item=PLI_EU27_2020` + `ppp_cat=E011` estavam CORRETOS desde o início: com 1
só país, a consulta devolve 30 anos de dados normalmente. O problema era outro,
mais sério: `coletar()` pede vários países de uma vez (`geo` como uma LISTA), e
`rede.montar_url()` usava `urlencode()` sem `doseq=True`. Sem isso, uma lista vira
uma única string com a *repr* do Python (`geo=['PT', 'DE', 'IE', 'ES']`,
percent-encoded), que a fonte não reconhece como nenhum código de país — a consulta
não dá erro, só não bate com nada e volta vazia.

Isso passou despercebido nos testes porque `coletar()` sempre foi testado com uma
função `http` de mentira (um stub Python), que nunca passa pelo `montar_url()` real
— só a chamada `--testar` (que usa o `obter_json` de verdade) expôs o problema.
Corrigido (`doseq=True`) e coberto por dois testes novos: um direto em
`montar_url()` e outro que passa pelo caminho inteiro (`obter_json` → `requests.get`
com `requests.get` simulado), para não depender só de stubs que mascaram esse tipo
de bug de novo.

Este bug só afetava o Eurostat (`custo_vida.py`) — o Banco Mundial nunca usou lista
em parâmetro de query (ele junta os países com `;` direto na URL), por isso nunca
teve esse problema.

## Custo de vida em USD/mês — concluído (baseline e fórmula)

Depois de coletar o nível de preços (Banco Mundial, `PA.NUS.PPPC.RF`, USA=1,0), o
coletor agora TAMBÉM publica uma estimativa em USD/mês, direto no campo
`custo_vida_mensal_usd` da coleção `paises` (o mesmo campo que a ficha do país já
mostrava, antes com o valor fixo do `data.py`).

**Fórmula:** `custo_vida_mensal_usd = baseline_EUA × nível_de_preços(país)`

**Baseline:** U.S. Bureau of Labor Statistics, Consumer Expenditure Surveys — gasto
médio anual de "single consumer, one earner" (uma pessoa, com renda própria: o
perfil mais parecido com quem está se mudando sozinho para trabalhar, não a média
de uma família). 2024: US$ 56.652/ano = **US$ 4.721/mês**. Fonte: news release
USDL-25-1586 (19/12/2025), https://www.bls.gov/news.release/cesan.htm — conferido
também via FRED (série CXUTOTALEXPLB0703M).

Por que essa série e não "todas as unidades de consumo" (US$ 78.535/ano, a manchete
mais citada do BLS): aquela é a média de um domicílio de ~2,4 pessoas, o que
superestimaria o custo para alguém se mudando sozinho.

**Limitação, documentada em cada valor (campo `custo_vida_mensal_usd_metodo`):** é
uma ESTIMATIVA, não uma pesquisa país a país. Assume que a razão entre o consumo
típico de um americano solteiro e o de alguém no país-alvo é a mesma razão medida
para a economia inteira (nível de preços do PIB). A cesta de um estrangeiro
recém-chegado (aluguel, mercado, transporte) pode pesar diferente da média
nacional — é um ponto de partida, não pesquisa de campo.

Cada valor carrega proveniência própria: `custo_vida_mensal_usd_calculado` (sempre
`true`), `_metodo` (a conta por extenso), `_fonte` (BLS + Banco Mundial) e
`_coletado_em`. A ficha do país (`app.py`) já mostra um aviso "🧮 Custo de vida
estimado" com o método, sempre que esse campo vier marcado.

**Correção importante que isso revelou:** o modo de teste (`dry_run`) do
`Publicador.gravar()` substituía o documento INTEIRO ao gravar, em vez de mesclar
campo a campo como o Firestore real faz com `merge=True`. Isso nunca dava problema
porque, até agora, cada coletor sempre escrevia documentos completos. Agora que
gravamos um PATCH (só `custo_vida_mensal_usd` e mais nada) num documento de país
que já tem região/idioma/visto, a mesclagem rasa apagaria esses campos no modo de
teste. Corrigido — `tests/test_coletores.py` tem um teste dedicado para isso.

**Verificação de segurança:** o `id` do patch usa a mesma normalização de nome de
país que o `seed_firestore.py` já usa para os documentos da coleção `paises` — sem
isso, o patch cairia num documento novo e órfão em vez de mesclar no país certo.
`tests/test_custo_vida_estimado.py` testa essa igualdade diretamente contra
`seed_firestore.id_seguro` (roda de verdade quando `firebase-admin` está instalado,
como na sua máquina; aqui no ambiente de teste sem essa dependência, esse teste
específico é pulado, com aviso — os demais continuam rodando).

## Próximos passos

1. ~~Custo de vida em valor absoluto (USD/mês)~~ — feito, ver seção abaixo.
2. **Salário em TI:** triangular Adzuna (histograma, se cobrir o país), Stack Overflow Survey (ODbL) e ILOSTAT/Eurostat.
3. **Mais países nas vagas:** Adzuna (confirmar países cobertos) e o endpoint do Reino Unido da Arbeitnow (`arbeitnow.co.uk`).
4. **Vistos e trilhas:** painel administrativo com `verificado_em` e revisão trimestral.
5. **Lacunas de conhecimento:** comparar `radar_tecnologias` com a matriz curricular dos cursos.
