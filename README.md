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

O sistema é composto por 3 serviços. Configure na seguinte ordem:

### 1. redis-datafy (Redis)
- **Source**: GitHub
- **Repository**: IsraelHenriquee/redis-datafy
- **Branch**: main
- **Dockerfile**: `Dockerfile.redis`

### 2. redis-api (API)
- **Source**: GitHub
- **Repository**: IsraelHenriquee/redis-datafy
- **Branch**: main
- **Dockerfile**: `Dockerfile`

**Variáveis de Ambiente**:
```
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
```

**Porta**: 5000 (HTTP)

### 3. redis-monitor (Monitor)
- **Source**: GitHub
- **Repository**: IsraelHenriquee/redis-datafy
- **Branch**: main
- **Dockerfile**: `Dockerfile.monitor`

**Variáveis de Ambiente**:
```
REDIS_HOST=redis-datafy
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha_aqui
WEBHOOK_URL=https://painel.israelhenrique.com.br/webhook/process
```

### Importante
- Use a mesma senha do Redis em todos os serviços
- O nome do serviço Redis deve ser exatamente `redis-datafy`
- Configure na ordem: redis -> api -> monitor
- Depois de configurar, clique em Deploy em cada serviço

### Endpoints
> ⚠️ **IMPORTANTE**: Estes endpoints são fixos e não devem ser alterados!

1. **Entrada de Mensagens (API)**
```
URL: /message
Método: POST
Porta: 5000
```

2. **Saída de Mensagens (Monitor)**
```
URL: Configurado via WEBHOOK_URL
Método: POST
Quando: Ao expirar mensagem no Redis
```

## Configuração Rápida (Docker Compose)

Se preferir usar o campo "Dockerfile" no EasyPanel, cole o seguinte conteúdo:

```dockerfile
# Primeiro estágio: Clonar o repositório
FROM alpine/git as clone
WORKDIR /app
RUN git clone https://github.com/IsraelHenriquee/redis-datafy.git .

# Serviço Redis
FROM redis:7.2.3 as redis
COPY --from=clone /app/redis.conf /usr/local/etc/redis/
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]

# Serviço API
FROM python:3.9 as api
WORKDIR /app
COPY --from=clone /app/requirements.txt .
RUN pip install -r requirements.txt
COPY --from=clone /app .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "api:app"]

# Serviço Monitor
FROM python:3.9 as monitor
WORKDIR /app
COPY --from=clone /app/requirements.txt .
RUN pip install -r requirements.txt
COPY --from=clone /app .
CMD ["python3", "monitor.py"]
```

Este Dockerfile multi-estágio:
1. Clona o repositório do GitHub
2. Constrói todos os serviços
3. Copia apenas os arquivos necessários

Mas lembre-se: ainda precisa configurar as variáveis de ambiente e portas no EasyPanel!

## Dockerfiles para Copiar

### redis-datafy (Redis)
```dockerfile
FROM alpine/git as clone
WORKDIR /app
RUN git clone https://github.com/IsraelHenriquee/redis-datafy.git .

FROM redis:7.2.3
COPY --from=clone /app/redis.conf /usr/local/etc/redis/
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
```

### redis-api (API)
```dockerfile
FROM alpine/git as clone
WORKDIR /app
RUN git clone https://github.com/IsraelHenriquee/redis-datafy.git .

FROM python:3.9
WORKDIR /app
COPY --from=clone /app/requirements.txt .
RUN pip install -r requirements.txt
COPY --from=clone /app .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "api:app"]
```

### redis-monitor (Monitor)
```dockerfile
FROM alpine/git as clone
WORKDIR /app
RUN git clone https://github.com/IsraelHenriquee/redis-datafy.git .

FROM python:3.9
WORKDIR /app
COPY --from=clone /app/requirements.txt .
RUN pip install -r requirements.txt
COPY --from=clone /app .
CMD ["python3", "monitor.py"]
```

Se estiver usando o campo "Dockerfile" no EasyPanel, basta copiar e colar o conteúdo correspondente ao serviço que está configurando.

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

## Endpoints

> ⚠️ **IMPORTANTE**: Estes endpoints são fixos e não devem ser alterados!

1. **Entrada de Mensagens (API)**
```
URL: /message
Método: POST
Porta: 5000
Exemplo: http://seu-dominio:5000/message
```

2. **Saída de Mensagens (Monitor)**
```
URL: Configurado via variável WEBHOOK_URL
Método: POST
Quando: Ao expirar mensagem no Redis
```

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

```
