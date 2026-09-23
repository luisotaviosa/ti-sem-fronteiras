# -*- coding: utf-8 -*-
"""
Base de dados mockada (protótipo) para o projeto TI Sem Fronteiras.

Em uma versão futura, estes dicionários/listas seriam substituídos por
dados vindos de APIs reais (ex: Numbeo, World Bank, LinkedIn Jobs API,
RemoteOK, WeWorkRemotely, etc.) ou de raspagem de dados (scraping).
Por enquanto, servem para demonstrar a arquitetura e a navegação do app.
"""

# ---------------------------------------------------------------------------
# MÓDULO I - MundoDev (Inteligência Geográfica)
# ---------------------------------------------------------------------------
PAISES = [
    {
        "pais": "Portugal",
        "lat": 38.7223,
        "lon": -9.1393,
        "regiao": "Europa",
        "demanda_ti": "Alta",
        "custo_vida_mensal_usd": 1100,
        "salario_medio_ti_usd": 2800,
        "idioma": "Português",
        "visto": "D3 (Trabalho Altamente Qualificado) / Blue Card UE",
        "dificuldade_visto": "Baixa",
        "resumo": "Idioma nativo facilita a adaptação. Forte polo de startups em Lisboa e Porto, "
                   "com custo de vida menor que a média da Europa Ocidental.",
    },
    {
        "pais": "Alemanha",
        "lat": 52.52,
        "lon": 13.405,
        "regiao": "Europa",
        "demanda_ti": "Muito Alta",
        "custo_vida_mensal_usd": 1500,
        "salario_medio_ti_usd": 4800,
        "idioma": "Alemão / Inglês (setor de tech)",
        "visto": "Blue Card UE / Visto de Busca de Emprego",
        "dificuldade_visto": "Média",
        "resumo": "Maior mercado de TI da Europa. Muitas empresas aceitam inglês como língua de trabalho.",
    },
    {
        "pais": "Canadá",
        "lat": 45.4215,
        "lon": -75.6972,
        "regiao": "América do Norte",
        "demanda_ti": "Muito Alta",
        "custo_vida_mensal_usd": 1800,
        "salario_medio_ti_usd": 5200,
        "idioma": "Inglês / Francês",
        "visto": "Express Entry (Federal Skilled Worker)",
        "dificuldade_visto": "Média",
        "resumo": "Programa de imigração por pontos bem estruturado, favorável a profissionais de TI.",
    },
    {
        "pais": "Irlanda",
        "lat": 53.3498,
        "lon": -6.2603,
        "regiao": "Europa",
        "demanda_ti": "Alta",
        "custo_vida_mensal_usd": 1900,
        "salario_medio_ti_usd": 5000,
        "idioma": "Inglês",
        "visto": "Critical Skills Employment Permit",
        "dificuldade_visto": "Baixa",
        "resumo": "Sede europeia de muitas big techs (Google, Meta, Stripe). Custo de vida alto em Dublin.",
    },
    {
        "pais": "Espanha",
        "lat": 40.4168,
        "lon": -3.7038,
        "regiao": "Europa",
        "demanda_ti": "Média",
        "custo_vida_mensal_usd": 1200,
        "salario_medio_ti_usd": 2600,
        "idioma": "Espanhol",
        "visto": "Visto de Empreendedor / Trabalho Altamente Qualificado",
        "dificuldade_visto": "Baixa",
        "resumo": "Boa qualidade de vida e proximidade cultural com o Brasil, salários mais baixos que a média da UE.",
    },
    {
        "pais": "Emirados Árabes Unidos",
        "lat": 25.2048,
        "lon": 55.2708,
        "regiao": "Oriente Médio",
        "demanda_ti": "Alta",
        "custo_vida_mensal_usd": 2200,
        "salario_medio_ti_usd": 5500,
        "idioma": "Inglês",
        "visto": "Golden Visa / Visto de Trabalho patrocinado por empresa",
        "dificuldade_visto": "Baixa",
        "resumo": "Isenção de imposto de renda pessoal. Alta demanda por especialistas em cloud e segurança.",
    },
]

# ---------------------------------------------------------------------------
# MÓDULO II - GlobalIT Jobs (Inteligência de Mercado)
# ---------------------------------------------------------------------------
VAGAS = [
    {"titulo": "Backend Developer (Node.js)", "empresa": "TechNordic", "pais": "Portugal",
     "modalidade": "Remoto", "senioridade": "Pleno", "stack": ["Node.js", "TypeScript", "AWS"],
     "salario_faixa_usd": "2800-3600"},
    {"titulo": "Suporte de Infraestrutura TI", "empresa": "BlueCloud GmbH", "pais": "Alemanha",
     "modalidade": "Híbrido", "senioridade": "Júnior", "stack": ["Linux", "Redes", "ITIL"],
     "salario_faixa_usd": "3200-4000"},
    {"titulo": "DevOps Engineer", "empresa": "MapleStack", "pais": "Canadá",
     "modalidade": "Remoto", "senioridade": "Sênior", "stack": ["Kubernetes", "Terraform", "AWS"],
     "salario_faixa_usd": "6000-8000"},
    {"titulo": "Suporte Técnico N2", "empresa": "GreenIsle IT", "pais": "Irlanda",
     "modalidade": "Presencial", "senioridade": "Júnior", "stack": ["Windows Server", "Active Directory"],
     "salario_faixa_usd": "3400-4200"},
    {"titulo": "QA Automation Engineer", "empresa": "IberiaSoft", "pais": "Espanha",
     "modalidade": "Remoto", "senioridade": "Pleno", "stack": ["Python", "Selenium", "CI/CD"],
     "salario_faixa_usd": "2400-3200"},
    {"titulo": "Cloud Security Analyst", "empresa": "DesertSec", "pais": "Emirados Árabes Unidos",
     "modalidade": "Presencial", "senioridade": "Sênior", "stack": ["Azure", "SIEM", "ISO 27001"],
     "salario_faixa_usd": "5500-7000"},
]

RADAR_TECNOLOGIAS = [
    {"tecnologia": "Python", "categoria": "Linguagem", "demanda": 92},
    {"tecnologia": "JavaScript / TypeScript", "categoria": "Linguagem", "demanda": 88},
    {"tecnologia": "AWS", "categoria": "Cloud", "demanda": 85},
    {"tecnologia": "Docker / Kubernetes", "categoria": "DevOps", "demanda": 80},
    {"tecnologia": "Linux (Suporte/Admin)", "categoria": "Infraestrutura", "demanda": 78},
    {"tecnologia": "SQL", "categoria": "Dados", "demanda": 75},
    {"tecnologia": "Active Directory", "categoria": "Infraestrutura", "demanda": 60},
    {"tecnologia": "Terraform", "categoria": "DevOps", "demanda": 55},
]

TRILHAS_QUALIFICACAO = [
    {"area": "Suporte / Redes", "competencia": "Redes e Infraestrutura",
     "certificacoes": ["CompTIA Network+", "CCNA", "ITIL Foundation"]},
    {"area": "Cloud", "competencia": "Computação em Nuvem",
     "certificacoes": ["AWS Cloud Practitioner", "AWS Solutions Architect Associate", "Azure Fundamentals (AZ-900)"]},
    {"area": "Segurança", "competencia": "Cibersegurança",
     "certificacoes": ["CompTIA Security+", "ISO 27001 Foundation"]},
    {"area": "Desenvolvimento", "competencia": "Programação Backend",
     "certificacoes": ["Python Institute PCEP", "freeCodeCamp Backend", "Node.js Certification"]},
    {"area": "DevOps", "competencia": "Automação e Deploy",
     "certificacoes": ["Docker Certified Associate", "Certified Kubernetes Administrator (CKA)"]},
]
