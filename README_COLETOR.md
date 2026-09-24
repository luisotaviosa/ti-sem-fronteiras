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
| (calculado do nível de preços) | `paises` (patch) | `custo_vida_mensal_usd` estimado (baseline BLS × nível de preços) |
| Arbeitnow (API pública, sem chave) | `vagas` | Vagas de TI, com tecnologias extraídas do texto |
| (calculado das vagas) | `radar_tecnologias` | Índice 0–100 por tecnologia, com o método e o tamanho da amostra |
| Adzuna (precisa de chave gratuita; cobertura a confirmar) | `indicadores_pais` | Salário médio anunciado em vagas de TI — ver seção própria, ainda não integrada a `executar.py` |
| Curadoria humana (`coletor/curadoria.py`) | `paises` (patch) / `trilhas_qualificacao` | Vistos e trilhas de qualificação, com validação e proveniência |

**Não coberto:** custo de vida como valor absoluto em USD/mês (Eurostat e Banco Mundial só dão índices relativos, não uma cifra pronta), salário médio em TI, vistos e trilhas (curadoria humana). Veja "Próximos passos".

## Como rodar (modo teste, sem Firebase)

Nesta pasta ainda não há ambiente virtual (o do app fica na pasta do app). Na primeira vez:

```bash
python3 -m venv .venv                          # se falhar: sudo apt install python3-venv python3-full
source .venv/bin/activate                      # o prompt passa a mostrar (.venv)
pip install -r requirements-coletor.txt
python -m unittest discover -s tests -v        # 118 testes offline, sem usar a internet
                                                # (1 pode ficar "skipped" se faltar `firebase-admin`,
                                                # ou se o seed_firestore.py na pasta for uma versão antiga sem id_seguro)
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

## Brasil por dentro (IBGE/SIDRA) — etapa de descoberta, 5 Grandes Regiões

`coletor/ibge.py` cobre Norte, Nordeste, Sudeste, Sul e Centro-Oeste (decisão
tomada com o usuário em 24/09/2026: começar pelas 5 regiões, não os 27
estados). Grava numa coleção PRÓPRIA, `brasil_regioes` — não em `paises` —
porque uma região do Brasil não tem visto nem vagas internacionais.

**Achado importante, antes de programar:** pesquisei se existe um índice
oficial do IBGE para comparar custo de vida ENTRE regiões, e a resposta é
não. IPCA/INPC medem variação de preços NO TEMPO em cada região (índices
temporais bilaterais) — não servem para comparar nível de preços ENTRE
regiões. Um índice assim existe só em pesquisa acadêmica (ex.: Menezes &
Azzoni, método CPD sobre dados da POF), não como série oficial via API. Por
isso este coletor automatiza dois indicadores genuinamente comparáveis —
PIB per capita (Contas Regionais) e rendimento médio real (PNAD Contínua) —
e a interface (`app.py`) avisa explicitamente que não há comparação oficial
de custo de vida entre regiões.

**Falta confirmar os IDs dos agregados SIDRA** (números arbitrários, não
adivináveis). Primeira tentativa (24/09/2026): `--descobrir "PIB per capita"`
só achou um indicador de TAXA DE CRESCIMENTO (não o valor absoluto — o
agregado certo de Contas Regionais provavelmente usa "Produto Interno Bruto
per capita" por extenso, sem a sigla); `--descobrir "rendimento médio"` trouxe
252 resultados, ruído de pesquisas sem relação (rendimento agrícola, Censo, e
a Pesquisa Mensal de Emprego, que já foi DESCONTINUADA e substituída pela
PNAD Contínua). Por isso agora também tem busca por nome do LEVANTAMENTO
(`--pesquisa`), que ignora o nome do indicador e lista tudo dentro de uma
pesquisa conhecida — bem mais limpo que buscar pelo nome do indicador
quando não se sabe o título exato. Rode:
```bash
python -m coletor.ibge --pesquisa "Contas Regionais"
python -m coletor.ibge --pesquisa "PNAD Contínua"
```
e me envie a saída de cada um; depois `--metadados <id>` do que parecer certo,
para eu confirmar o `variavel_id` e finalizar os padrões de `coletar()`
(mesmo processo que já demos com o Eurostat). O decodificador da resposta já
está pronto e testado com o formato documentado, incluindo os códigos de
ausência do SIDRA (`..`, `X`, `-`) — só falta o ID de verdade.

**Atualização (24/09/2026):** `--pesquisa "Contas Regionais"` e `--pesquisa
"PNAD Contínua"` deram os dois ZERO resultados — a suposição de que esses
nomes apareceriam literalmente na 1ª chave do catálogo estava errada
(provavelmente essa chave agrupa por ASSUNTO amplo, tipo "Economia" ou
"Trabalho e Rendimento", não pelo nome da pesquisa). Em vez de arriscar mais
um palpite, adicionei:
```bash
python -m coletor.ibge --listar-pesquisas
```
que mostra o vocabulário REAL dessa chave, sem filtrar nada — para achar o
termo certo olhando a lista de verdade, em vez de continuar chutando strings.

**Atualização (24/09/2026), rodada seguinte:** com `--pesquisa`, achamos o
agregado 5938 ("Produto Interno Bruto dos Municípios") — mas seus metadados
mostraram que ele só tem PIB TOTAL (Mil Reais) e participações percentuais,
NUNCA per capita. Usar o total direto seria um erro (o Sudeste "ganharia" só
por ter mais gente, não por ser mais rico por pessoa) — o mesmo tipo de erro
que já evitamos com o IPCA. Ainda precisamos achar a tabela de PIB per
capita de verdade; próxima tentativa: `--pesquisa "Contas Nacionais Anuais"`.

Também achamos um candidato para rendimento (agregado 5436, PNAD Contínua
trimestral), mas o nome dele tem "por sexo" — ou seja, tem uma
CLASSIFICAÇÃO cruzada (sexo: Total/Homens/Mulheres) que `--metadados` não
mostrava (só imprimia variáveis e nível territorial, não classificações).
Corrigido: `--metadados` agora também lista as classificações e marca a
categoria que parece ser "Total", para não vir uma consulta sem querer
quebrada por sexo.

## Brasil por dentro — CONCLUÍDO (24/09/2026)

Depois de várias rodadas de descoberta, os dois indicadores estão
confirmados e implementados:

- **Rendimento médio:** agregado `5436`, variável `5932` ("habitualmente
  recebido no trabalho principal"), classificação Sexo (id `2`) = Total
  (categoria `6794`). Vem pronto da fonte, sem cálculo.
- **PIB per capita:** NÃO existe pronto por Grande Região no SIDRA (a única
  tabela per capita, agregado `6784`, só tem nível nacional). Por isso é
  CALCULADO — PIB total (agregado `5938`, variável `37`, em Mil Reais) ÷
  população residente estimada (agregado `6579`, variável `9324`, em
  Pessoas) — no ANO MAIS RECENTE em que as duas séries têm dado para aquela
  região (elas têm defasagens de divulgação diferentes; nunca se divide
  anos diferentes sem isso ficar registrado no campo `metodo`).

`coletor.ibge.coletar()` já une os dois, `coletor.executar.executar_ibge()`
já está no orquestrador (`--fonte ibge`), com validação própria
(`validar_regiao_br`, em `validacao.py`) e faixas plausíveis para cada
indicador.

**Bug real encontrado pelos próprios testes, antes de entregar:** os dois
indicadores usavam o MESMO `id` por região (ex.: `"sudeste"` para os dois).
Como vão para a mesma coleção, gravar o segundo sobrescrevia
SILENCIOSAMENTE o primeiro (merge=True mescla campo a campo, e "valor",
"indicador" etc. têm o mesmo nome nos dois documentos) — a mesma classe de
erro que já tínhamos corrigido para o Banco Mundial. Corrigido: o `id`
agora inclui o indicador (`id_documento(regiao, "pib_per_capita")` /
`id_documento(regiao, "rendimento_medio")`), com um teste de regressão
dedicado para isso não voltar a acontecer se um terceiro indicador for
adicionado no futuro.

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

## Salário médio em TI — etapa 1 (Adzuna), precisa da sua confirmação

`coletor/salario.py` usa o endpoint `history` do Adzuna (salário médio anunciado
por mês, formato confirmado na documentação oficial). Diferente das fontes
anteriores, esta tem DUAS coisas que só você consegue confirmar, porque exigem uma
credencial que este ambiente não tem como obter:

1. **Credencial gratuita:** crie em https://developer.adzuna.com/signup (poucos
   minutos, sem cartão) e exporte:
   ```bash
   export ADZUNA_APP_ID=...
   export ADZUNA_APP_KEY=...
   ```
2. **Cobertura de país:** a lista `PAISES_CANDIDATOS` no módulo é um palpite
   fundamentado, não confirmado. Rode:
   ```bash
   python -m coletor.salario --verificar
   ```
   e me envie a saída — só entram no coletor de verdade os países que responderem
   com dado. Alemanha, Canadá e Espanha são bem prováveis; Portugal, Irlanda e
   Emirados Árabes Unidos, menos.
3. **Moeda:** a documentação não diz explicitamente em qual moeda o valor volta
   (o mais provável é a moeda local de cada mercado). Por isso todo documento sai
   com `moeda_confirmada: False` — nada é convertido para USD até isso ser
   confirmado (o valor bruto aparece no `--verificar` para você comparar com uma
   vaga real no site do Adzuna daquele país).

Ainda não está em `executar.py` — entra assim que você confirmar os três pontos
acima. O resto (coleta por país, tratamento de erro por país sem derrubar os
demais, proveniência) já está pronto e testado com o formato de resposta oficial.

## INCIDENTE REAL (23/09/2026): app quebrou com KeyError: 'regiao'

Isto já aconteceu em produção: a coleta automática (`--publicar`) rodou ANTES de
`seed_firestore.py` ter criado os documentos-base dos países. O patch de
`custo_vida_mensal_usd` criou documentos com SÓ esse campo, sem `regiao` — e como
NENHUM documento da coleção tinha esse campo, a coluna nem existia no DataFrame, e
`app.py` quebrava com `KeyError: 'regiao'` ao montar o filtro de região do MundoDev.

**NÃO conserte rodando `seed_firestore.py` de novo.** Ele grava com `.set()` SEM
`merge=True` — sobrescreve o documento INTEIRO. Rodá-lo agora apagaria o
`custo_vida_mensal_usd` já calculado (voltaria ao valor de demonstração) e, pior,
resseeda `vagas` e `radar_tecnologias` por inteiro, revertendo os dados reais já
coletados (vagas da Arbeitnow, radar calculado) para os dados de demonstração.

**Conserto certo:**
```bash
python -m coletor.reparar_paises --publicar
```
Isto mescla (merge=True) só os campos de base do país (região, coordenadas, idioma,
visto, dificuldade do visto, demanda em TI, resumo) a partir do `data.py` — sem
tocar em `custo_vida_mensal_usd`/`salario_medio_ti_usd` nem nas outras 3 coleções.
Testado ponta a ponta reproduzindo o `KeyError` real com pandas antes de corrigir
(ver `tests/test_reparar_paises.py`).

**Se `--publicar` (deste ou de qualquer outro comando) travar com
`DEADLINE_EXCEEDED` / `_InactiveRpcError`:** isso é erro de REDE, não do código —
o Firestore escreve por gRPC, e redes de campus/instituição costumas liberar HTTPS
comum (é por isso que `--verificar`/`--testar`/coleta em modo teste funcionam) mas
bloquear ou atrapalhar gRPC. A biblioteca oficial do Firestore para Python não tem
opção de trocar para REST (é gRPC-only, ao contrário de outras bibliotecas do
Google Cloud) — não adianta configurar isso.

Alternativa que já se provou funcionar: rodar pelo GitHub Actions, cuja rede não
tem essa restrição (foi assim que os documentos incompletos foram publicados em
primeiro lugar). O workflow já tem a opção `reparar_paises` no menu do
`workflow_dispatch` — aba **Actions** do repositório → **Coleta automática de
dados** → **Run workflow** → escolha `reparar_paises` no menu → **Run workflow**.

## INCIDENTE 2 (23/09/2026): mesmo padrão, campo diferente (salario_medio_ti_usd)

Depois do reparo do incidente 1, o app quebrou de novo — `KeyError:
'salario_medio_ti_usd'`, mesmo padrão, campo diferente. Causa: a primeira versão
de `reparar_paises.py` excluía `custo_vida_mensal_usd` E `salario_medio_ti_usd`
por completo (achando que os dois já vinham de coleta automática). Mas
`salario_medio_ti_usd` nunca teve fonte nenhuma publicada (Adzuna ainda está só
em teste — ver seção própria) — excluí-lo sempre deixava o campo ausente para
sempre.

**Corrigido de vez:** em vez de uma lista fixa de campos "nunca toca", o reparo
agora lê o que já existe no Firestore (`Publicador.ler("paises")`) e só preenche
`custo_vida_mensal_usd`/`salario_medio_ti_usd` se ainda estiverem AUSENTES —
nunca sobrescreve um valor que uma coleta automática já publicou (hoje, isso é
só o custo de vida; no dia em que o Adzuna entrar de vez, o salário também fica
protegido automaticamente, sem precisar mexer no script de novo). Os campos de
base (região, idioma, visto etc.) continuam sempre atualizados a partir do
`data.py`, como antes. Reproduzido e corrigido com pandas de verdade antes de
entregar — ver `tests/test_reparar_paises.py` (esse teste específico se auto-pula quando pandas não está instalado, como no GitHub Actions — pandas não é dependência do coletor, só do app; foi exatamente isso que quebrou o CI na primeira versão deste reparo, e ficou corrigido).

Se rodar `python -m coletor.reparar_paises --publicar` e a mensagem de log disse
"Reparo concluído" mas o app ainda quebrar com um `KeyError` em OUTRO campo, é o
mesmo padrão de novo: algum campo que `data.py` tem mas que nunca foi escrito no
Firestore. Me avise qual campo que eu ajusto.

## Publicar no Firestore de verdade — ORDEM IMPORTA

Com a chave do Firebase em mãos (veja `guia_firebase.md`), a ordem certa é:

```bash
python seed_firestore.py                        # 1º: cria os documentos-base (país, vaga, radar, trilha demo)
python -m coletor.executar --fonte todas --publicar   # 2º: atualiza com dados reais
```

**Por quê nessa ordem:** o coletor grava `custo_vida_mensal_usd` como um PATCH no
documento do país (só esse campo, mesclado com `merge=True`). Se o documento do
país ainda não existir (banco novo, sem `seed_firestore.py` rodado antes), o patch
cria um documento faltando região, idioma, visto etc. — a ficha do país ficaria
incompleta no app. Rodar o seed primeiro garante que a base já está lá para o
patch se juntar a ela.

Depois disso, `streamlit run app.py` deve mostrar "🔥 Conectado ao Firestore
(Firebase)" na barra lateral, e a ficha do país já com o selo "🧮 Custo de vida
estimado".

## Vistos e trilhas — curadoria humana, com validação (não é coleta automática)

`coletor/curadoria.py` não busca nada de fonte nenhuma — é para quando alguém da
equipe pesquisar manualmente (ex.: o portal de imigração de um país, ou o site de
um certificador) e quiser publicar isso com o mesmo rigor dos dados automáticos:
proveniência obrigatória (`fonte`, `verificado_em`, `verificado_por`) e validação
antes de gravar.

1. Copie `curadoria/vistos_modelo.json` ou `curadoria/trilhas_modelo.json`,
   preencha com as entradas reais (uma por país ou por trilha).
2. Rode em modo teste primeiro:
   ```bash
   python -m coletor.curadoria --colecao paises --arquivo meus_vistos.json
   python -m coletor.curadoria --colecao trilhas_qualificacao --arquivo minhas_trilhas.json
   ```
3. Confira `saida/paises.json` / `saida/trilhas_qualificacao.json`, e só então
   adicione `--publicar`.

Cada entrada de visto é um PATCH no documento do país (como o custo de vida
estimado) — só os campos de visto, o resto do país continua intacto. Uma entrada
sem `verificado_por` ou com `verificado_em` que não seja uma data real é
rejeitada, sem derrubar as demais entradas do lote.

## Próximos passos

1. ~~Custo de vida em valor absoluto (USD/mês)~~ — feito, ver seção abaixo.
2. **Salário em TI:** triangular Adzuna (histograma, se cobrir o país), Stack Overflow Survey (ODbL) e ILOSTAT/Eurostat.
3. **Mais países nas vagas:** Adzuna (confirmar países cobertos) e o endpoint do Reino Unido da Arbeitnow (`arbeitnow.co.uk`).
4. **Vistos e trilhas:** painel administrativo com `verificado_em` e revisão trimestral.
5. **Lacunas de conhecimento:** comparar `radar_tecnologias` com a matriz curricular dos cursos.
