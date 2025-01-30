# Redis Datafy

Sistema de processamento de mensagens com Redis e Webhooks.

## Configuração no EasyPanel

O sistema é composto por 3 serviços que devem ser configurados na seguinte ordem:

### 1. redis-datafy (Redis)

**Nome**: redis-datafy
**Source**: GitHub
**Repository**: IsraelHenriquee/redis-datafy
**Branch**: main
**Dockerfile**: Dockerfile.redis

**Variáveis**: Nenhuma necessária

### 2. redis-api (API)

**Nome**: redis-redis-api
**Source**: GitHub
**Repository**: IsraelHenriquee/redis-datafy
**Branch**: main
**Dockerfile**: Dockerfile

**Variáveis de Ambiente**:
```env
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
```

**Porta**: 5000 (HTTP)

### 3. redis-monitor (Monitor)

**Nome**: redis-monitor
**Source**: GitHub
**Repository**: IsraelHenriquee/redis-datafy
**Branch**: main
**Dockerfile**: Dockerfile.monitor

**Variáveis de Ambiente**:
```env
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
WEBHOOK_URL=https://painel.israelhenrique.com.br/webhook/process2
```

## Passo a Passo

1. **Redis**:
   - Crie serviço `redis-datafy`
   - Selecione GitHub como Source
   - Cole URL do repositório
   - Selecione `Dockerfile.redis`
   - Deploy

2. **API**:
   - Crie serviço `redis-redis-api`
   - Selecione GitHub como Source
   - Cole URL do repositório
   - Selecione `Dockerfile`
   - Configure variáveis de ambiente
   - Exponha porta 5000
   - Deploy

3. **Monitor**:
   - Crie serviço `redis-monitor`
   - Selecione GitHub como Source
   - Cole URL do repositório
   - Selecione `Dockerfile.monitor`
   - Configure variáveis de ambiente
   - Deploy

## Importante

- Use a mesma senha do Redis em todos os serviços
- O nome do serviço Redis deve ser exatamente `redis-datafy`
- Configure na ordem: redis -> api -> monitor
- Depois de configurar, clique em Deploy em cada serviço

## Endpoints

1. **Entrada de Mensagens (API)**
```
URL: /message
Método: POST
Porta: 5000
Exemplo no EasyPanel: https://redis-redis-api.pk0y8w.easypanel.host/message
```

Exemplo de payload:
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
    "message": "Olá!",
    "ttl": 30
}
```

2. **Saída de Mensagens (Monitor)**
```
URL: Configurado via WEBHOOK_URL
Método: POST
Quando: Ao expirar mensagem no Redis
```

## Arquivos de Configuração

### redis.conf
```conf
notify-keyspace-events Ex
appendonly yes
save 900 1
save 300 10
save 60 10000
requirepass sua_senha_aqui
```

### requirements.txt
```
redis==5.0.1
flask==3.0.0
gunicorn==21.2.0
python-dotenv==1.0.0
aiohttp==3.9.1
asyncio==3.4.3
```

## Fluxo de Funcionamento

1. Cliente -> API (envia mensagem)
2. API -> Redis (salva com TTL)
3. Redis -> Monitor (avisa quando expira)
4. Monitor -> Webhook (envia mensagem expirada)
