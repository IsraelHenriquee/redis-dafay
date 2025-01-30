# Redis Message Queue

Sistema de fila de mensagens usando Redis com TTL dinâmico.

## Estrutura

- `api.py`: API REST para receber mensagens
- `monitor.py`: Monitor que processa mensagens expiradas
- `requirements.txt`: Dependências do projeto

## Instalação

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

## Configuração

O sistema precisa de um arquivo `.env` com as seguintes variáveis:

```bash
# Host e porta do Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui

# URL do webhook para onde enviar as mensagens expiradas
WEBHOOK_URL=https://seu-dominio.com/webhook/process
```

## Configuração no EasyPanel

O sistema é composto por 3 serviços que precisam ser configurados no EasyPanel:

### 1. redis-datafy (Redis)
**Configuração Source:**
- Repository: `IsraelHenriquee/redis-datafy`
- Dockerfile: `Dockerfile.redis`

**Variáveis de Ambiente:**
- Não precisa de variáveis de ambiente
- Usa as configurações do arquivo `redis.conf`

**Portas:**
- Não precisa expor portas
- Comunicação apenas interna

### 2. redis-api (API)
**Configuração Source:**
- Repository: `IsraelHenriquee/redis-datafy`
- Dockerfile: `Dockerfile`

**Variáveis de Ambiente:**
```env
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
```

**Portas:**
- Porta: 5000
- Tipo: HTTP
- Necessário para receber mensagens via API

### 3. redis-monitor (Monitor)
**Configuração Source:**
- Repository: `IsraelHenriquee/redis-datafy`
- Dockerfile: `Dockerfile.monitor`

**Variáveis de Ambiente:**
```env
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
WEBHOOK_URL=https://seu-webhook.com/endpoint
```

**Portas:**
- Não precisa expor portas
- Apenas faz conexão de saída para o webhook

**Importante:**
- Use exatamente o mesmo `REDIS_PASSWORD` em todos os serviços
- O `REDIS_HOST` deve ser o nome do serviço Redis no EasyPanel
- O `WEBHOOK_URL` só é necessário no serviço monitor

### Papel de Cada Serviço

1. **redis-api** (API):
- Recebe mensagens via POST
- Salva no Redis com TTL
- Atualiza TTL se receber nova mensagem
- Roda com Gunicorn para alta performance

2. **redis-datafy** (Redis):
- Armazena as mensagens
- Controla o TTL (tempo de vida)
- Notifica quando mensagem expira
- Protegido com senha

3. **redis-monitor** (Monitor):
- Escuta eventos de expiração do Redis
- Envia mensagens expiradas para webhook
- Processa de forma assíncrona
- Aguenta várias mensagens simultâneas

### Fluxo de Funcionamento
1. Cliente -> API (envia mensagem)
2. API -> Redis (salva com TTL)
3. Redis -> Monitor (avisa quando expira)
4. Monitor -> Webhook (envia mensagem expirada)

## Uso no EasyPanel

1. Criar nova aplicação Python
2. Configurar variáveis de ambiente:
   - `REDIS_HOST`
   - `REDIS_PORT`
   - `REDIS_PASSWORD`
   - `WEBHOOK_URL`

3. A API estará disponível em:
```
https://$(PRIMARY_DOMAIN)/redis-api/api/message
```

## API

### POST /api/message

Enviar uma nova mensagem:

```json
{
    "id_agente": 1,
    "numero_conectado": "+5511999999999",
    "foto": "https://example.com/photo.jpg",
    "phone": "+5511888888888",
    "sender_name": "João Silva",
    "user": "joao.silva",
    "chave": "chave123",
    "instance_id": "inst_123",
    "servidor": "srv1",
    "token": "token123",
    "token_seguranca": "sec_token123",
    "modo": "chat",
    "plataforma_ia": 1,
    "server_url": "https://api.example.com",
    "provider": 1,
    "id_instancia": 1,
    "message": "Sua mensagem aqui",
    "ttl": 30
}
```

- `user`: Campo obrigatório, identificador único do chat
- `message`: Campo obrigatório, texto da mensagem
- `ttl`: Opcional, tempo em segundos até expirar (default: 15)

## Webhook

Quando o chat expira, todas as mensagens são enviadas para o webhook configurado com o seguinte formato:

```json
{
    "id_agente": 1,
    "numero_conectado": "...",
    "user": "joao.silva",
    "user_id": "joao.silva",
    "messages": [
        "Mensagem 1",
        "Mensagem 2",
        "Mensagem 3"
    ],
    "processed_at": "2025-01-30T01:19:45"
}
