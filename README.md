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
