# -*- coding: utf-8 -*-
"""
TI Sem Fronteiras - Protótipo (SIRITEC / IFS Campus Socorro)

Ecossistema modular para internacionalização de carreiras em TI:
  - Módulo I  -> MundoDev      (Inteligência Geográfica)
  - Módulo II -> GlobalIT Jobs (Inteligência de Mercado)

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

import firestore_data as fdb

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO GERAL
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TI Sem Fronteiras",
    page_icon="🌐",
    layout="wide",
)

CORES = {
    "primaria": "#2563EB",
    "secundaria": "#0F172A",
    "destaque": "#22C55E",
}

df_paises = pd.DataFrame(fdb.carregar_paises())
if not df_paises.empty and "pais" in df_paises.columns:
    # Descarta documentos sem um "pais" de verdade (ex.: um patch de custo de vida
    # que caiu num id errado e virou um documento órfão, sem nenhum dos campos de
    # base) -- sem isso, um documento assim pode ser escolhido como padrão no
    # seletor da ficha por país e quebrar a página com IndexError.
    _valido = df_paises["pais"].notna() & (df_paises["pais"].astype(str).str.strip() != "")
    df_paises = df_paises[_valido]
df_vagas = pd.DataFrame(fdb.carregar_vagas())
df_radar = pd.DataFrame(fdb.carregar_radar_tecnologias())
df_indicadores = pd.DataFrame(fdb.carregar_indicadores_pais())
df_brasil_regioes = pd.DataFrame(fdb.carregar_brasil_regioes())
TRILHAS_QUALIFICACAO = fdb.carregar_trilhas_qualificacao()


def _dado_mais_recente(*dfs, coluna="coletado_em"):
    """Maior valor de `coletado_em` entre os DataFrames informados, ou None se nenhum tiver a coluna."""
    valores = []
    for df in dfs:
        if coluna in df.columns:
            valores += [v for v in df[coluna].dropna().tolist() if v]
    return max(valores) if valores else None


def _campo(linha, nome):
    """Como `linha.get(nome)`, mas trata NaN do pandas como ausente.

    Quando um DataFrame é montado a partir de documentos que nem todos têm um dado
    campo (comum quando um documento mais antigo do Firestore foi gravado antes de o
    coletor passar a incluir esse campo), o pandas preenche as linhas que não têm
    esse campo com NaN — e NaN é "verdadeiro" em Python (bool(float('nan')) é True).
    Sem este tratamento, um simples `if campo:` mostraria dados como "USD nan/mês"
    ou marcaria como "calculado" um indicador que não é.
    """
    v = linha.get(nome)
    return None if isinstance(v, float) and v != v else v


# ---------------------------------------------------------------------------
# SIDEBAR - NAVEGAÇÃO
# ---------------------------------------------------------------------------
st.sidebar.title("🌐 TI Sem Fronteiras")
st.sidebar.caption("SIRITEC · IFS Campus Socorro")
pagina = st.sidebar.radio(
    "Navegação",
    ["🏠 Início", "🗺️ MundoDev", "💼 GlobalIT Jobs"],
)
st.sidebar.markdown("---")
modo = fdb.modo_dados()
if modo == "firestore":
    st.sidebar.success("🔥 Conectado ao Firestore (Firebase)")
else:
    st.sidebar.info("📦 Usando dados locais de demonstração (Firebase não conectado)")
st.sidebar.caption(
    "Protótipo acadêmico. Em versão futura, os dados virão de APIs reais e raspagem de dados."
)
_atualizado_em = _dado_mais_recente(df_vagas, df_indicadores)
if _atualizado_em:
    st.sidebar.caption(f"🕒 Dados coletados em: {str(_atualizado_em)[:16].replace('T', ' ')} UTC")


# ---------------------------------------------------------------------------
# PÁGINA: INÍCIO
# ---------------------------------------------------------------------------
def pagina_inicio():
    st.title("TI Sem Fronteiras")
    st.subheader("Ecossistema unificado para internacionalização de carreiras em TI")

    st.markdown(
        """
        O projeto **TI Sem Fronteiras** nasce para eliminar barreiras geográficas para o
        talento técnico do Instituto Federal de Sergipe, tratando a carreira internacional
        como um processo de duas etapas: **a escolha do destino** e **a conquista da vaga**.
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🗺️ Módulo I — MundoDev")
        st.markdown(
            "**Inteligência Geográfica.** Mapeamento de países, cultura, custo de vida "
            "e requisitos de imigração."
        )
        st.markdown(
            "- Mapeamento de países\n"
            "- Guia de sobrevivência (custo de vida, moradia, saúde)\n"
            "- Segurança jurídica (vistos e regularização)"
        )
    with col2:
        st.markdown("### 💼 Módulo II — GlobalIT Jobs")
        st.markdown(
            "**Inteligência de Mercado.** Oportunidades de trabalho, tecnologias "
            "demandadas e requisitos técnicos."
        )
        st.markdown(
            "- Monitoramento de vagas\n"
            "- Radar de tecnologias\n"
            "- Trilhas de qualificação"
        )

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Países mapeados", len(df_paises))
    c2.metric("Vagas monitoradas", len(df_vagas))
    c3.metric("Tecnologias no radar", len(df_radar))


# ---------------------------------------------------------------------------
# PÁGINA: MUNDODEV
# ---------------------------------------------------------------------------
def _normalizar(texto: str) -> str:
    """'São Paulo' -> 'sao paulo' — busca sem acento/maiúscula, só com a lib padrão."""
    import unicodedata
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def pagina_mundodev():
    st.title("🗺️ MundoDev")
    st.caption("Módulo I — Inteligência Geográfica")

    col_busca, col_regiao = st.columns([2, 1])
    with col_busca:
        busca = st.text_input(
            "🔎 Buscar por país, estado ou região",
            placeholder="ex.: Portugal, Bahia, Sudeste...",
        )
    with col_regiao:
        regioes = ["Todas"] + sorted(df_paises["regiao"].unique().tolist())
        regiao_sel = st.selectbox("Filtrar por região", regioes)

    df_filtrado = df_paises if regiao_sel == "Todas" else df_paises[df_paises["regiao"] == regiao_sel]

    if busca.strip():
        alvo = _normalizar(busca)
        # busca em país, região e (quando existir) país-pai, ex.: estados/regiões do Brasil
        campos_busca = ["pais", "regiao"] + (["pais_pai"] if "pais_pai" in df_filtrado.columns else [])
        mascara = df_filtrado[campos_busca].apply(
            lambda linha: any(alvo in _normalizar(v) for v in linha if v), axis=1
        )
        df_filtrado = df_filtrado[mascara]
        if df_filtrado.empty:
            st.info(f"Nenhum resultado para \"{busca}\". Tente outro termo ou limpe o campo de busca.")

    fig = px.bar(
        df_filtrado.sort_values("salario_medio_ti_usd"),
        x="salario_medio_ti_usd",
        y="pais",
        orientation="h",
        color="demanda_ti",
        title="Salário médio em TI por país (USD/mês, estimado)",
        labels={"salario_medio_ti_usd": "Salário médio (USD)", "pais": "País", "demanda_ti": "Demanda em TI"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 🌍 Mapa Global de Vagas")
    st.caption(
        "O tamanho e a cor de cada ponto/coluna representam a quantidade de vagas "
        "catalogadas no país."
    )

    vagas_por_pais = df_vagas.groupby("pais").size().reset_index(name="qtd_vagas")
    df_mapa = df_paises.merge(vagas_por_pais, on="pais", how="left")
    df_mapa["qtd_vagas"] = df_mapa["qtd_vagas"].fillna(0).astype(int)

    estilo_mapa = st.radio(
        "Estilo do mapa",
        ["🪐 Globo 3D", "🛰️ Satélite 3D (estilo Google Earth)"],
        horizontal=True,
    )

    if estilo_mapa == "🪐 Globo 3D":
        st.caption("Arraste para girar o globo e use a roda do mouse (ou pinça) para zoom.")

        fig_globo = go.Figure(
            go.Scattergeo(
                lon=df_mapa["lon"],
                lat=df_mapa["lat"],
                text=df_mapa.apply(
                    lambda r: (
                        f"<b>{r['pais']}</b><br>"
                        f"{r['qtd_vagas']} vaga(s) catalogada(s)<br>"
                        f"Demanda em TI: {r['demanda_ti']}<br>"
                        f"Salário médio: ${r['salario_medio_ti_usd']:,}/mês"
                    ),
                    axis=1,
                ),
                hoverinfo="text",
                mode="markers",
                marker=dict(
                    size=(df_mapa["qtd_vagas"] * 8 + 16),
                    sizemode="diameter",
                    color=df_mapa["qtd_vagas"],
                    colorscale="Blues",
                    cmin=0,
                    line=dict(width=1.5, color="white"),
                    opacity=0.9,
                ),
            )
        )
        fig_globo.update_geos(
            projection_type="orthographic",
            showland=True,
            landcolor="rgb(235, 240, 235)",
            showocean=True,
            oceancolor="rgb(200, 225, 245)",
            showcountries=True,
            countrycolor="rgb(190, 190, 190)",
            showcoastlines=True,
            coastlinecolor="rgb(170, 170, 170)",
            showlakes=False,
            bgcolor="rgba(0,0,0,0)",
        )
        fig_globo.update_layout(
            height=560,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_globo, use_container_width=True, config={"scrollZoom": True})

    else:
        st.caption(
            "Arraste para navegar, roda do mouse para zoom, e clique+arraste com o botão "
            "direito para inclinar (pitch) e girar (bearing) a câmera em 3D — igual ao "
            "Google Earth. Requer conexão com a internet para carregar as imagens de satélite."
        )

        tile_layer = pdk.Layer(
            "TileLayer",
            data="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            min_zoom=0,
            max_zoom=19,
            tile_size=256,
        )

        column_layer = pdk.Layer(
            "ColumnLayer",
            data=df_mapa,
            get_position=["lon", "lat"],
            get_elevation="qtd_vagas",
            elevation_scale=300000,
            radius=60000,
            get_fill_color=[37, 99, 235, 210],
            pickable=True,
            auto_highlight=True,
        )

        view_state = pdk.ViewState(latitude=30, longitude=10, zoom=1.3, pitch=45, bearing=0)

        deck = pdk.Deck(
            layers=[tile_layer, column_layer],
            initial_view_state=view_state,
            tooltip={
                "html": (
                    "<b>{pais}</b><br/>{qtd_vagas} vaga(s) catalogada(s)"
                    "<br/>Demanda em TI: {demanda_ti}"
                ),
                "style": {"backgroundColor": "#0F172A", "color": "white"},
            },
            map_provider=None,
        )
        st.pydeck_chart(deck, use_container_width=True)

    st.markdown("### Ficha por país")
    if df_filtrado.empty:
        st.warning(
            "Nenhum país para mostrar aqui. Se isto acontecer logo na primeira "
            "carga da página (sem busca nem filtro aplicados), o mais provável é "
            "que a coleção `paises` do Firestore ainda esteja vazia — rode o "
            "`seed_firestore.py` no projeto conectado."
        )
    else:
        pais_sel = st.selectbox("Escolha um país para ver detalhes", df_filtrado["pais"].tolist())
        dados = df_paises[df_paises["pais"] == pais_sel].iloc[0]

        col1, col2, col3 = st.columns(3)
        col1.metric("Custo de vida (USD/mês)", f"${dados['custo_vida_mensal_usd']:,}")
        col2.metric("Salário médio TI (USD/mês)", f"${dados['salario_medio_ti_usd']:,}")
        col3.metric("Demanda em TI", dados["demanda_ti"])
        if _campo(dados, "custo_vida_mensal_usd_calculado") is True:
            st.caption(
                "🧮 Custo de vida estimado — " + (_campo(dados, "custo_vida_mensal_usd_metodo") or "")
            )
            fonte_cv = _campo(dados, "custo_vida_mensal_usd_fonte")
            if fonte_cv:
                st.caption(f"Fonte: {fonte_cv}")

        st.markdown(f"**Idioma:** {dados['idioma']}")
        st.markdown(f"**Visto recomendado:** {dados['visto']} · *Dificuldade: {dados['dificuldade_visto']}*")
        st.markdown(f"**Resumo:** {dados['resumo']}")

        st.markdown("---")
        st.markdown("#### 🌐 Indicadores complementares (Banco Mundial)")
        st.caption(
            "Coletados automaticamente (ver `coletor/banco_mundial.py`). Complementam a ficha acima; "
            "não substituem custo de vida e salário médio em TI, que têm fonte própria."
        )
        ind_pais = df_indicadores[df_indicadores["pais"] == pais_sel] if not df_indicadores.empty else df_indicadores
        if ind_pais.empty:
            st.caption("Nenhum indicador complementar coletado para este país ainda.")
        else:
            cols_ind = st.columns(3)
            for i, (_, row) in enumerate(ind_pais.sort_values("indicador").iterrows()):
                with cols_ind[i % 3]:
                    st.metric(
                        _campo(row, "descricao") or row["indicador"],
                        f"{row['valor']:.4g}" + (f" {_campo(row, 'unidade')}" if _campo(row, "unidade") == "razão" else ""),
                        help=f"Ano de referência: {_campo(row, 'ano_referencia') or '—'}",
                    )
                    if _campo(row, "calculado") is True:
                        st.caption("🧮 calculado por nós (a série oficial está arquivada na fonte)")
                    fonte_txt = _campo(row, "fonte") or "—"
                    coletado_txt = str(_campo(row, "coletado_em") or "")[:10]
                    st.caption(f"Fonte: {fonte_txt}" + (f" · coletado em {coletado_txt}" if coletado_txt else ""))

    # -----------------------------------------------------------------
    # 🇧🇷 Brasil por dentro — layout PRÓPRIO, não reaproveita a ficha de país
    # acima: uma região do Brasil não tem visto nem vagas internacionais, e os
    # indicadores vêm de outra fonte (IBGE/SIDRA), com outro significado.
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🇧🇷 Brasil por dentro — as 5 Grandes Regiões")
    st.caption(
        "Indicadores oficiais do IBGE (Sistema de Contas Regionais e PNAD Contínua), "
        "por Grande Região. Aqui não há visto nem vagas internacionais — é o mercado "
        "de trabalho brasileiro visto por dentro."
    )
    if df_brasil_regioes.empty:
        st.info(
            "Ainda sem dados coletados para as regiões do Brasil. "
            "Ver `coletor/ibge.py` no repositório do coletor."
        )
    else:
        st.warning(
            "⚠️ Não existe, hoje, um índice oficial de custo de vida comparável entre "
            "regiões do Brasil (IPCA/INPC medem variação de preços no tempo, não nível "
            "de preços entre regiões — não são comparáveis entre si dessa forma). Os "
            "indicadores abaixo são os que realmente permitem comparar as regiões.",
            icon="ℹ️",
        )
        indicadores_disponiveis = sorted(df_brasil_regioes["descricao"].unique().tolist())
        indicador_sel = st.selectbox("Indicador", indicadores_disponiveis, key="indicador_brasil")
        df_ind = df_brasil_regioes[df_brasil_regioes["descricao"] == indicador_sel]

        fig_br = px.bar(
            df_ind.sort_values("valor"),
            x="valor", y="regiao", orientation="h",
            labels={"valor": _campo(df_ind.iloc[0], "unidade") or "valor", "regiao": "Região"},
            title=indicador_sel,
        )
        st.plotly_chart(fig_br, use_container_width=True)

        cols_br = st.columns(5)
        for i, (_, row) in enumerate(df_ind.sort_values("regiao").iterrows()):
            with cols_br[i % 5]:
                st.metric(row["regiao"], f"{row['valor']:,.0f}")
        r0 = df_ind.iloc[0]
        st.caption(
            f"Ano de referência: {_campo(r0, 'ano_referencia') or '—'} · "
            f"Fonte: {_campo(r0, 'fonte') or '—'} · "
            f"coletado em {str(_campo(r0, 'coletado_em') or '')[:10]}"
        )


# ---------------------------------------------------------------------------
# PÁGINA: GLOBALIT JOBS
# ---------------------------------------------------------------------------
def pagina_globalit_jobs():
    st.title("💼 GlobalIT Jobs")
    st.caption("Módulo II — Inteligência de Mercado")

    tab1, tab2, tab3 = st.tabs(["📋 Vagas", "📡 Radar de Tecnologias", "🎯 Trilhas de Qualificação"])

    # --- Vagas ---
    with tab1:
        col_f1, col_f2, col_f3 = st.columns(3)
        paises_opt = ["Todos"] + sorted(df_vagas["pais"].unique().tolist())
        senioridade_opt = ["Todas"] + sorted(df_vagas["senioridade"].unique().tolist())
        modalidade_opt = ["Todas"] + sorted(df_vagas["modalidade"].unique().tolist())

        pais_f = col_f1.selectbox("País", paises_opt)
        senioridade_f = col_f2.selectbox("Senioridade", senioridade_opt)
        modalidade_f = col_f3.selectbox("Modalidade", modalidade_opt)

        df_v = df_vagas.copy()
        if pais_f != "Todos":
            df_v = df_v[df_v["pais"] == pais_f]
        if senioridade_f != "Todas":
            df_v = df_v[df_v["senioridade"] == senioridade_f]
        if modalidade_f != "Todas":
            df_v = df_v[df_v["modalidade"] == modalidade_f]

        st.write(f"**{len(df_v)} vaga(s) encontrada(s)**")
        for _, vaga in df_v.iterrows():
            with st.container(border=True):
                st.markdown(f"#### {vaga['titulo']} — {vaga['empresa']}")

                pais_txt = vaga["pais"]
                if _campo(vaga, "pais_inferido") is True:
                    loc = _campo(vaga, "localizacao")
                    pais_txt += f" (inferido{f' de {loc}' if loc else ''})"

                modalidade_txt = vaga["modalidade"] + (" (inferida)" if _campo(vaga, "modalidade_inferida") is True else "")
                senioridade_txt = vaga["senioridade"] + (" (inferida)" if _campo(vaga, "senioridade_inferida") is True else "")

                salario_bruto = _campo(vaga, "salario_faixa_usd")
                salario_txt = f"USD {salario_bruto}/mês" if salario_bruto else "salário não informado"

                st.markdown(f"📍 {pais_txt} · 🏷️ {modalidade_txt} · 🎓 {senioridade_txt} · 💰 {salario_txt}")

                stack = _campo(vaga, "stack")
                st.markdown("**Stack:** " + (", ".join(stack) if stack else "não identificada"))

                fonte = _campo(vaga, "fonte")
                if fonte:
                    coletado_txt = str(_campo(vaga, "coletado_em") or "")[:10]
                    link = _campo(vaga, "url_fonte")
                    rodape = f"Fonte: {fonte}" + (f" · coletado em {coletado_txt}" if coletado_txt else "")
                    if link:
                        st.caption(rodape + f" · [ver vaga original]({link})")
                    else:
                        st.caption(rodape)

    # --- Radar de tecnologias ---
    with tab2:
        fig_radar = px.bar(
            df_radar.sort_values("demanda"),
            x="demanda",
            y="tecnologia",
            color="categoria",
            orientation="h",
            title="Radar de tecnologias mais demandadas no exterior",
            labels={"demanda": "Índice de demanda (0-100)", "tecnologia": "Tecnologia"},
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        tem_amostra = "n_amostra" in df_radar.columns and df_radar["n_amostra"].notna().any()
        if not tem_amostra:
            st.caption("Radar de demonstração (dados de exemplo; ainda sem coleta automática).")
        else:
            r0 = df_radar.iloc[0]
            partes = []
            if pd.notna(r0.get("n_amostra")):
                partes.append(f"amostra de {int(r0['n_amostra'])} vaga(s)")
            if pd.notna(r0.get("empresas_distintas")):
                partes.append(f"{int(r0['empresas_distintas'])} empresas distintas")
            conc = r0.get("concentracao_maior_empresa")
            if pd.notna(conc):
                partes.append(f"maior empresa concentra {conc * 100:.0f}%")
            st.caption("Calculado a partir das vagas coletadas — " + " · ".join(partes) + ".")
            if pd.notna(conc) and conc > 0.30:
                st.warning("⚠️ Uma empresa concentra mais de 30% da amostra: leia o índice com cautela.")
            periodo = r0.get("periodo")
            if isinstance(periodo, dict) and periodo.get("de"):
                st.caption(f"Período das vagas: {str(periodo['de'])[:10]} a {str(periodo.get('ate') or '')[:10]}")

    # --- Trilhas de qualificação ---
    with tab3:
        for trilha in TRILHAS_QUALIFICACAO:
            with st.expander(f"🎯 {trilha['area']} — {trilha['competencia']}"):
                for cert in trilha["certificacoes"]:
                    st.checkbox(cert, key=f"{trilha['area']}-{cert}")


# ---------------------------------------------------------------------------
# ROTEAMENTO
# ---------------------------------------------------------------------------
if pagina == "🏠 Início":
    pagina_inicio()
elif pagina == "🗺️ MundoDev":
    pagina_mundodev()
elif pagina == "💼 GlobalIT Jobs":
    pagina_globalit_jobs()
