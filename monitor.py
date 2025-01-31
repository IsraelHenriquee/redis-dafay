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
        
        # Adiciona erro à lista do dia
        upstash_client.rpush(key, json.dumps(error_data))
        
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

async def send_webhook(payload):
    """Envia dados para o webhook de forma assíncrona"""
    # Remove barra final se existir
    webhook_url = WEBHOOK_URL.rstrip('/')
    
    try:
        print(f"\n=== ENVIANDO WEBHOOK ===", flush=True)
        print(f"URL: {webhook_url}", flush=True)
        print(f"Payload: {json.dumps(payload, indent=2)}", flush=True)
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("\nIniciando request...", flush=True)
            
            async with session.post(
                webhook_url,
                json=payload,
                ssl=False,
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
                
                if status == 200:
                    print("\n✅ Webhook enviado com sucesso!", flush=True)
                else:
                    print(f"\n❌ Erro na resposta do webhook:", flush=True)
                    print(f"Status: {status}", flush=True)
                    print(f"Body: {text}", flush=True)
                
                return status == 200
                
    except aiohttp.ClientConnectorError as e:
        print(f"\n❌ Não conseguiu conectar ao servidor:", flush=True)
        print(f"Erro: {str(e)}", flush=True)
        return False
        
    except asyncio.TimeoutError:
        print(f"\n❌ Timeout ao enviar webhook", flush=True)
        print(f"O servidor não respondeu em 30 segundos", flush=True)
        return False
        
    except Exception as e:
        print(f"\n❌ ERRO GRAVE ao enviar webhook:", flush=True)
        print(f"Tipo: {type(e)}", flush=True)
        print(f"Mensagem: {str(e)}", flush=True)
        return False

async def process_expired_chat(ttl_key):
    """Processa chat expirado"""
    retry_count = 0
    
    try:
        user_id = get_user_id_from_ttl_key(ttl_key)
        data_key = get_data_key(user_id)
        
        # Recupera dados
        chat_data = json.loads(redis_client.get(data_key))
        if not chat_data:
            save_error_log("WARNING", "process", "Dados não encontrados", {
                "ttl_key": ttl_key,
                "data_key": data_key
            })
            return
            
        retry_count = chat_data.get("retry_count", 0)
        
        # Monta payload
        payload = {
            **chat_data["metadata"],
            "listamessages": chat_data["messages"],
            "processed_at": datetime.now().isoformat()
        }
        
        # Tenta enviar
        if await send_webhook(payload):
            # Sucesso: apaga as chaves
            print(f"[SUCCESS] Webhook enviado com sucesso após {retry_count} tentativas", flush=True)
            redis_client.delete(data_key)
            redis_client.delete(ttl_key)
        else:
            if retry_count >= len(RETRY_INTERVALS):
                error_msg = "Máximo de tentativas atingido"
                print(f"[ERROR] {error_msg}", flush=True)
                save_error_log("ERROR", "webhook", error_msg, {
                    "user_id": user_id,
                    "retry_count": retry_count,
                    "status": 500
                })
                redis_client.delete(data_key)
                redis_client.delete(ttl_key)
                return
            
            # Pega próximo intervalo de retry
            next_retry = RETRY_INTERVALS[retry_count]
            print(f"[RETRY] Tentativa {retry_count + 1}. Próxima tentativa em {next_retry}s", flush=True)
            
            # Atualiza contador de retry
            chat_data["retry_count"] = retry_count + 1
            redis_client.set(data_key, json.dumps(chat_data))
            
            # Atualiza TTL apenas da chave de controle
            redis_client.expire(ttl_key, next_retry)
            
    except Exception as e:
        error_msg = f"Erro ao processar chat: {str(e)}"
        print(f"[ERROR] {error_msg}", flush=True)
        save_error_log("ERROR", "process", error_msg, {
            "user_id": user_id if 'user_id' in locals() else None,
            "retry_count": retry_count,
            "ttl_key": ttl_key
        })
        
        # Trata erro como uma tentativa falha
        if retry_count >= len(RETRY_INTERVALS):
            redis_client.delete(data_key)
            redis_client.delete(ttl_key)
        else:
            next_retry = RETRY_INTERVALS[retry_count]
            chat_data["retry_count"] = retry_count + 1
            redis_client.set(data_key, json.dumps(chat_data))
            redis_client.expire(ttl_key, next_retry)

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
                    key = message['data'].decode('utf-8')
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
