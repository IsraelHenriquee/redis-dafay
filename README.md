# Redis Datafy

Sistema de processamento de chats com Redis e webhooks.

## Estrutura

```
redis-datafy/
  ├─ monitor/      # Monitora expiração de chats
  ├─ worker/       # Processa webhooks
  └─ dashboard/    # Interface web
```

## Configuração

### Redis (Upstash)

O projeto usa dois bancos Redis do Upstash:

1. **Redis Principal**:
   - Armazenamento de dados
   - Filas de mensagens
   - Notificações de expiração
   - Configurado via `REDIS_URL`

2. **Redis de Logs**:
   - Logs do sistema
   - Monitoramento
   - Configurado via `UPSTASH_REDIS_URL`

#### Limites (Free Tier)
- 256MB por banco
- 10,000 comandos/dia por banco
- Baixa latência (us-west-1)

### Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

```bash
# Redis Principal (dados, filas, expiração)
REDIS_URL=redis://default:senha@host.upstash.io:6379

# Redis de Logs
UPSTASH_REDIS_URL=redis://default:senha@host.upstash.io:6379

# URL do webhook
WEBHOOK_URL=https://seu-dominio.com/webhook/process
```

## Deploy (Digital Ocean)

1. Criar novo app
2. Adicionar serviços:
   - `monitor/`
   - `worker/`
   - `dashboard/`
3. Configurar variáveis de ambiente
4. Deploy! 🚀

## Desenvolvimento Local

```bash
# Monitor
cd monitor && python monitor.py

# Worker
cd worker && python worker.py

# Dashboard
cd dashboard && python dashboard.py
