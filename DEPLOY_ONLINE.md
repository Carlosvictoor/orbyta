# Colocar Orbyta online

## 1) Checklist rápido

Antes de subir, confirme:

- `SECRET_KEY` forte no `.env`
- `FLASK_DEBUG=0`
- `SESSION_COOKIE_SECURE=1`
- `PREFERRED_URL_SCHEME=https`
- `TRUST_PROXY=1`
- `APP_BASE_URL=https://seu-dominio.com`
- `MP_ACCESS_TOKEN` e `MP_PUBLIC_KEY` preenchidos
- `WHATSAPP_PROVIDER` configurado (`twilio` ou `webhook`)

## 2) Instalação

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3) Rodar em produção

```powershell
.\.venv\Scripts\python.exe serve.py
```

## 4) Mercado Pago

No painel do Mercado Pago, configure o webhook para:

```text
https://seu-dominio.com/webhook/mercadopago
```

Fluxos disponíveis no sistema:

- assinatura recorrente no cartão
- pagamento por Pix
- conferência manual em `/assinatura/status`

## 5) WhatsApp

No painel do dono:

- salve o `WhatsApp do estabelecimento`
- personalize a mensagem automática
- use o botão `Enviar teste`

Se usar `WHATSAPP_PROVIDER=webhook`, o sistema já envia o número do estabelecimento no payload (`from`, `sender`, `business_phone`).

## 6) Hospedagem

Você pode subir em:

- **Render**
- **Railway**
- **VPS com Nginx + Windows/Linux**

Arquivos já preparados no projeto:

- `render.yaml` → deploy no Render
- `Procfile` → deploy no Railway
- `runtime.txt` → versão do Python

Comando de start:

```text
python serve.py
```

## 7) Persistência

Defina `ORBYTA_DATA_DIR` apontando para o volume persistente da plataforma.

A pasta `data/` precisa ser persistida para não perder:

- usuários
- negócios
- agendamentos
- financeiro
- ranking

## 8) Checklist por plataforma

### Render
- conecte o repositório
- confirme `render.yaml`
- preencha as variáveis sensíveis (`SECRET_KEY`, `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY`, etc.)
- mantenha o disco persistente ativo

### Railway
- suba o projeto
- Railway vai usar o `Procfile`
- crie um volume e defina `ORBYTA_DATA_DIR`
- configure as mesmas variáveis do `.env`

Variáveis principais no Railway:

```env
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
PREFERRED_URL_SCHEME=https
TRUST_PROXY=1
APP_BASE_URL=https://SEU-APP.up.railway.app
ORBYTA_DATA_DIR=/data/orbyta
MP_ACCESS_TOKEN=...
MP_PUBLIC_KEY=...
WHATSAPP_PROVIDER=webhook
WHATSAPP_WEBHOOK_URL=...
WHATSAPP_WEBHOOK_TOKEN=...
```

## 9) Conferência final

Depois de subir, teste:

- `/health`
- login do dono
- criação de agendamento
- pagamento Mercado Pago
- webhook do Mercado Pago
- lembrete/teste do WhatsApp
