# TI Sem Fronteiras — Protótipo (SIRITEC / IFS Campus Socorro)

App em Python (Streamlit) com backend em **Firebase Firestore** e fallback
automático para dados de demonstração quando o Firebase não está configurado
(ideal para testar o app antes mesmo de criar o projeto no Firebase).

- **Módulo I — MundoDev**: países, custo de vida, salário médio em TI, vistos.
- **Módulo II — GlobalIT Jobs**: vagas, radar de tecnologias, trilhas de qualificação.

---

## Passo a passo — criar o Firebase do zero

### 1. Criar o projeto
1. Acesse **https://console.firebase.google.com**
2. Clique em **"Adicionar projeto"** → dê um nome (ex: `ti-sem-fronteiras`) → siga o assistente
   (pode desativar o Google Analytics, não é necessário para este protótipo).

### 2. Ativar o Firestore
1. No menu lateral do projeto, vá em **Build → Firestore Database**.
2. Clique em **"Criar banco de dados"**.
3. Escolha o modo **"Teste" (test mode)** — libera leitura/escrita por 30 dias,
   suficiente para o protótipo do SIRITEC. Escolha a região `southamerica-east1` (São Paulo).

### 3. Gerar a chave de acesso (credencial)
1. Clique na engrenagem (⚙️) → **"Configurações do projeto"**.
2. Aba **"Contas de serviço"** → **"Gerar nova chave privada"**.
3. Um arquivo `.json` será baixado. Renomeie para **`serviceAccountKey.json`**
   e coloque na raiz da pasta do projeto (mesma pasta do `app.py`).
   ⚠️ **Nunca suba esse arquivo pro GitHub** — o `.gitignore` já está configurado para ignorá-lo.

---

## Testar localmente (no seu computador)

```bash
pip install -r requirements.txt

# 1) Popular o Firestore com os dados iniciais (roda uma vez só)
python3 seed_firestore.py

# 2) Rodar o app
streamlit run app.py
```

Abrirá automaticamente em `http://localhost:8501`. Na barra lateral, o app mostra
se está **🟢 conectado ao Firestore** ou **🟡 em modo offline** (dados mock) —
útil para debugar se a chave está correta.

> Se você ainda não gerou a `serviceAccountKey.json`, o app roda normalmente mesmo assim,
> só que usando os dados de exemplo do `data.py` em vez do Firestore.

---

## Publicar um link online (Streamlit Community Cloud — grátis)

1. Suba o projeto para um repositório no **GitHub** (público ou privado).
   ⚠️ Confirme que `serviceAccountKey.json` **não** foi enviado (cheque com `git status`).
2. Acesse **https://share.streamlit.io** e faça login com sua conta GitHub.
3. Clique em **"New app"**, selecione o repositório, branch e o arquivo `app.py`.
4. Antes de rodar, vá em **"Advanced settings" → "Secrets"** e cole o conteúdo do seu
   `serviceAccountKey.json` no formato TOML abaixo (é assim que o Streamlit Cloud
   injeta a credencial sem precisar do arquivo físico):

   ```toml
   [firebase]
   type = "service_account"
   project_id = "seu-projeto-id"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\nCOLE_AQUI\n-----END PRIVATE KEY-----\n"
   client_email = "...@seu-projeto-id.iam.gserviceaccount.com"
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "..."
   ```

   Todos esses campos existem dentro do `serviceAccountKey.json` que você baixou — é só copiar cada valor.

5. Clique em **"Deploy"**. Em ~1-2 minutos você recebe um link público tipo
   `https://ti-sem-fronteiras.streamlit.app` para compartilhar no SIRITEC.

---

## Estrutura dos arquivos

- `app.py` — interface do app (páginas, gráficos, navegação).
- `firestore_data.py` — camada de dados: tenta ler do Firestore, cai para `data.py` se não configurado.
- `data.py` — dados de demonstração (fallback offline).
- `seed_firestore.py` — script para popular o Firestore com os dados iniciais.
- `requirements.txt` — dependências do projeto.
- `.gitignore` — protege a chave secreta de ir pro GitHub por engano.

## Próximos passos

- Regras de segurança do Firestore: trocar o modo "Teste" (aberto) por regras reais antes de
  usar dados de usuários de verdade — hoje qualquer pessoa com o link pode ler/escrever.
- Painel admin simples (formulário Streamlit) para cadastrar vagas/países sem editar código.
- Migrar as buscas de vagas para uma fonte real via API ou scraping agendado.
