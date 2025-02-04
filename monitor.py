import redis
import json
from datetime import datetime
import time
import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv
from constants import (
    REDIS_PREFIX_TTL,
    get_data_key,
    get_user_id_from_ttl_key,
    get_ttl_key
)

# Força flush imediato dos prints
sys.stdout.reconfigure(line_buffering=True)

print("=== INICIANDO MONITOR ===", flush=True)
print("Python está rodando!", flush=True)

# Carrega variáveis do .env
load_dotenv()
print("Carregou dotenv!", flush=True)

# Conexão com Redis
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True
)

# URL do webhook do .env
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Constantes para retry e Redis
RETRY_INTERVALS = [30, 180, 300]  # 30s, 3min, 5min

# Cliente Redis do Upstash para logs
upstash_url = os.getenv('UPSTASH_REDIS_URL')
if upstash_url:
    # Parse da URL do Upstash
    url_parts = upstash_url.replace('redis://', '').split('@')
    auth = url_parts[0].split(':')
    host_port = url_parts[1].split(':')
    
    upstash_client = redis.Redis(
        host=host_port[0],
        port=int(host_port[1]),
        password=auth[1],
        ssl=True,
        decode_responses=True
    )
    print("✅ Conectado ao Upstash Redis", flush=True)
else:
    print("⚠️ UPSTASH_REDIS_URL não configurado!", flush=True)
    upstash_client = None

def save_error_log(error_type, source, error_message, details=None):
    """Salva log de erro no Upstash"""
    try:
        date = datetime.now().strftime('%Y-%m-%d')
        key = f"logs:{date}"
        
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "source": source,
            "error": error_message,
            "details": details or {}
        }
        
        # Pega logs existentes ou cria lista vazia
        current_logs = upstash_client.get(key)
        if current_logs:
            logs = json.loads(current_logs)
        else:
            logs = []
        
        # Adiciona novo log e salva
        logs.append(error_data)
        upstash_client.set(key, json.dumps(logs))
        
        # TTL de 30 dias
        upstash_client.expire(key, 60 * 60 * 24 * 30)
        
    except Exception as e:
        print(f"[META-ERROR] Erro ao salvar log: {str(e)}", flush=True)

def save_user_message(user_id: str, message: str, metadata: dict = None):
    """Salva mensagem do usuário no Redis"""
    try:
        ttl_key = get_ttl_key(user_id)
        data_key = get_data_key(user_id)
        ttl_value = metadata.get('ttl', 300) if metadata else 300
        
        if redis_client.exists(data_key):
            # Recupera dados existentes
            current_data = json.loads(redis_client.get(data_key))
            messages = current_data.get("messages", [])
            messages.append(message)
            
            # Nova estrutura com metadados novos e mensagens acumuladas
            current_data = {
                "messages": messages,
                "metadata": metadata,
                "retry_count": 0
            }
        else:
            # Cria nova estrutura
            current_data = {
                "messages": [message],
                "metadata": metadata,
                "retry_count": 0
            }
        
        # Salva no Redis
        redis_client.set(data_key, json.dumps(current_data))
        redis_client.set(ttl_key, "1")  # Valor dummy
        redis_client.expire(ttl_key, ttl_value)
        
    except Exception as e:
        error_msg = f"Erro ao salvar mensagem: {str(e)}"
        print(f"[ERROR] {error_msg}", flush=True)
        save_error_log("ERROR", "message", error_msg, {
            "user_id": user_id,
            "metadata": metadata
        })

def save_webhook_log(user_id: str, payload: dict, status: str, response: dict = None):
    """Salva log do webhook no Upstash
    
    Args:
        user_id: ID do usuário
        payload: Payload enviado
        status: Status do envio (sending, success, error)
        response: Resposta do webhook (opcional)
    """
    try:
        # Formato: 04-02-2025-13-21-45-123
        timestamp = datetime.now().strftime('%d-%m-%Y-%H-%M-%S-%f')[:-3]
        key = f"webhook:{user_id}:{timestamp}"
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "payload": payload,
            "status": status
        }
        
        if response:
            log_data["response"] = response
            
        upstash_client.set(key, json.dumps(log_data))
        # Expira em 30 dias
        upstash_client.expire(key, 60 * 60 * 24 * 30)
        
    except Exception as e:
        print(f"❌ Erro ao salvar log no Upstash: {str(e)}", flush=True)

async def send_webhook(payload, user_id):
    """Envia dados para o webhook de forma assíncrona"""
    # Remove barra final se existir
    webhook_url = WEBHOOK_URL.rstrip('/')
    
    try:
        print(f"\n=== ENVIANDO WEBHOOK ===", flush=True)
        print(f"URL: {webhook_url}", flush=True)
        print(f"Payload: {json.dumps(payload, indent=2)}", flush=True)
        
        # Salva log de envio
        save_webhook_log(user_id, payload, "sending")
        
        # Aumentado para 61 segundos para dar margem ao timeout do servidor (60s)
        timeout = aiohttp.ClientTimeout(total=61)
        
        async with aiohttp.ClientSession() as session:
            print("\nIniciando request...", flush=True)
            
            try:
                async with session.post(
                    webhook_url,
                    json=payload,
                    ssl=False,
                    timeout=timeout,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'Redis-Monitor/1.0'
                    }
                ) as response:
                    status = response.status
                    text = await response.text()
                    
                    print(f"\nResposta do webhook:", flush=True)
                    print(f"Status: {status}", flush=True)
                    print(f"Body: {text}", flush=True)
                    
                    response_data = {
                        "status_code": status,
                        "body": text
                    }
                    
                    if status == 200:
                        print("\n✅ Webhook enviado com sucesso!", flush=True)
                        save_webhook_log(user_id, payload, "success", response_data)
                    else:
                        print(f"\n❌ Erro na resposta do webhook:", flush=True)
                        print(f"Status: {status}", flush=True)
                        print(f"Body: {text}", flush=True)
                        save_webhook_log(user_id, payload, "error", response_data)
                    
                    return status == 200
            
            except asyncio.TimeoutError:
                print(f"\n❌ Timeout ao enviar webhook", flush=True)
                print(f"O servidor não respondeu em 61 segundos", flush=True)
                save_webhook_log(user_id, payload, "error", {
                    "error": "timeout",
                    "message": "O servidor não respondeu em 61 segundos"
                })
                # Força cancelamento da request
                await session.close()
                return False
                
    except aiohttp.ClientConnectorError as e:
        error_msg = f"Não conseguiu conectar ao servidor: {str(e)}"
        print(f"\n❌ {error_msg}", flush=True)
        save_webhook_log(user_id, payload, "error", {
            "error": "connection_error",
            "message": error_msg
        })
        return False
        
    except Exception as e:
        error_msg = f"ERRO GRAVE ao enviar webhook: {str(e)}"
        print(f"\n❌ {error_msg}", flush=True)
        print(f"Tipo: {type(e)}", flush=True)
        save_webhook_log(user_id, payload, "error", {
            "error": "unknown_error",
            "message": error_msg,
            "type": str(type(e))
        })
        return False

# Controle global de chats em processamento com timestamp
PROCESSING_CHATS = {}  # user_id -> (timestamp, retry_count)

async def process_expired_chat(ttl_key):
    """Processa chat expirado"""
    try:
        user_id = get_user_id_from_ttl_key(ttl_key)
        data_key = get_data_key(user_id)
        queue_key = f"chat:QUEUE:{user_id}"
        
        try:
            # Recupera dados
            chat_data = json.loads(redis_client.get(data_key))
            if not chat_data:
                save_error_log("WARNING", "process", "Dados não encontrados", {
                    "ttl_key": ttl_key,
                    "data_key": data_key
                })
                return
                
            # Monta payload
            payload = {
                **chat_data["metadata"],
                "listamessages": chat_data["messages"],
                "processed_at": datetime.now().isoformat()
            }
            
            # Adiciona na fila
            redis_client.rpush(queue_key, json.dumps(payload))
            print(f"✅ Mensagem adicionada na fila: {queue_key}", flush=True)
            
            # Limpa dados originais
            redis_client.delete(data_key)
            redis_client.delete(ttl_key)
                
        except Exception as e:
            error_msg = f"Erro ao processar chat: {str(e)}"
            print(f"❌ {error_msg}", flush=True)
            save_error_log("ERROR", "process", error_msg, {
                "user_id": user_id,
                "ttl_key": ttl_key
            })
            
    except Exception as e:
        error_msg = f"Erro ao processar chat: {str(e)}"
        print(f"❌ {error_msg}", flush=True)
        save_error_log("ERROR", "process", error_msg, {
            "ttl_key": ttl_key
        })

async def monitor():
    """Monitor principal"""
    while True:
        try:
            pubsub = redis_client.pubsub()
            pubsub.psubscribe('__keyevent@0__:expired')
            
            print("🚀 Monitor iniciado", flush=True)
            
            while True:
                message = pubsub.get_message()
                if message and message['type'] == 'pmessage':
                    # Verifica se data já é string ou precisa decode
                    key = message['data']
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    
                    print(f"\nRecebeu mensagem do Redis: {message}", flush=True)
                    print(f"Chave expirada: {key}", flush=True)
                    
                    if key.startswith(f"{REDIS_PREFIX_TTL}:"):
                        print(f"✅ Processando chat: {key}", flush=True)
                        await process_expired_chat(key)
                    else:
                        print(f"❌ Chave não é do chat: {key}", flush=True)
                        
                await asyncio.sleep(0.1)
                
        except Exception as e:
            error_msg = f"Erro crítico no monitor: {str(e)}"
            print(f"[CRITICAL] {error_msg}", flush=True)
            save_error_log("CRITICAL", "monitor", error_msg)
            
            # Espera 1 segundo e tenta reiniciar
            await asyncio.sleep(1)
            continue

if __name__ == "__main__":
    load_dotenv()
    
    # Debug das variáveis
    print("\n=== Variáveis de Ambiente ===", flush=True)
    print(f"REDIS_HOST: {os.getenv('REDIS_HOST')}", flush=True)
    print(f"REDIS_PORT: {os.getenv('REDIS_PORT')}", flush=True)
    print(f"WEBHOOK_URL: {os.getenv('WEBHOOK_URL')}", flush=True)
    print(f"UPSTASH_REDIS_URL: {os.getenv('UPSTASH_REDIS_URL')}", flush=True)
    print("==========================", flush=True)
    
    try:
        redis_client.ping()
        print("\nConectado ao Redis com sucesso!", flush=True)
        print(f"Usando webhook: {WEBHOOK_URL}", flush=True)
        asyncio.run(monitor())
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.", flush=True)
