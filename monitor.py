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

# Constantes para retry
RETRY_INTERVALS = [30, 180, 300]  # 30s, 3min, 5min

def acquire_lock(lock_key, expire_seconds=10):
    """Tenta adquirir um lock"""
    return redis_client.set(lock_key, '1', ex=expire_seconds, nx=True)

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

def save_user_message(user_id: str, message: str, metadata: dict = None):
    ttl_key = get_ttl_key(user_id)
    data_key = get_data_key(user_id)
    ttl_value = metadata.get('ttl', 300) if metadata else 300
    
    if redis_client.exists(ttl_key):
        # Recupera dados existentes
        current_data = json.loads(redis_client.get(data_key))
        messages = current_data.get("messages", [])
        messages.append(message)
        
        # Nova estrutura com metadados novos e mensagens acumuladas
        current_data = {
            "messages": messages,
            "metadata": metadata,  # Usa exatamente os metadados que chegaram
            "retry_count": 0  # Reseta contador de retry quando chega nova mensagem
        }
    else:
        # Cria nova estrutura
        current_data = {
            "messages": [message],
            "metadata": metadata,
            "retry_count": 0
        }
    
    # Salva no Redis e atualiza TTL
    redis_client.set(data_key, json.dumps(current_data))
    redis_client.expire(ttl_key, ttl_value)
    redis_client.expire(data_key, ttl_value)

async def process_expired_chat(ttl_key):
    try:
        user_id = get_user_id_from_ttl_key(ttl_key)
        data_key = get_data_key(user_id)
        
        # Recupera dados
        chat_data = json.loads(redis_client.get(data_key))
        if not chat_data:
            return
            
        retry_count = chat_data.get("retry_count", 0)
        
        # Monta payload
        payload = {
            **chat_data["metadata"],
            "listamessages": chat_data["messages"],
            "processed_at": datetime.now().isoformat()
        }
        
        # Tenta enviar
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    # Sucesso: apaga as chaves
                    print(f"[SUCCESS] Webhook enviado com sucesso após {retry_count} tentativas", flush=True)
                    redis_client.delete(data_key)
                    redis_client.delete(ttl_key)
                else:
                    if retry_count >= len(RETRY_INTERVALS):
                        # Máximo de tentativas atingido
                        print(f"[ERROR] Máximo de tentativas atingido. Apagando dados.", flush=True)
                        redis_client.delete(data_key)
                        redis_client.delete(ttl_key)
                        return
                    
                    # Pega próximo intervalo de retry
                    next_retry = RETRY_INTERVALS[retry_count]
                    print(f"[RETRY] Tentativa {retry_count + 1}. Próxima tentativa em {next_retry}s", flush=True)
                    
                    # Atualiza contador de retry
                    chat_data["retry_count"] = retry_count + 1
                    redis_client.set(data_key, json.dumps(chat_data))
                    
                    # Atualiza TTL
                    redis_client.expire(data_key, next_retry)
                    redis_client.expire(ttl_key, next_retry)
                    
    except Exception as e:
        print(f"[ERROR] Erro ao processar chat: {str(e)}", flush=True)
        # Trata erro como uma tentativa falha
        if retry_count >= len(RETRY_INTERVALS):
            redis_client.delete(data_key)
            redis_client.delete(ttl_key)
        else:
            next_retry = RETRY_INTERVALS[retry_count]
            chat_data["retry_count"] = retry_count + 1
            redis_client.set(data_key, json.dumps(chat_data))
            redis_client.expire(data_key, next_retry)
            redis_client.expire(ttl_key, next_retry)

async def monitor():
    """
    Monitora chaves que expiram no Redis
    """
    pubsub = redis_client.pubsub()
    pubsub.psubscribe('__keyevent@0__:expired')
    
    print("\nMonitorando chats que expiram...", flush=True)
    print(f"Webhook configurado para: {WEBHOOK_URL}", flush=True)
    
    # Debug: Lista todas as chaves no Redis
    print("\nChaves no Redis:", flush=True)
    for key in redis_client.keys('*'):
        ttl = redis_client.ttl(key)
        print(f"- {key} (TTL: {ttl}s)", flush=True)
    
    try:
        for message in pubsub.listen():
            print(f"\nRecebeu mensagem do Redis: {message}", flush=True)
            
            if message['type'] == 'pmessage':
                # Verifica se data já é string ou precisa decode
                expired_key = message['data']
                if isinstance(expired_key, bytes):
                    expired_key = expired_key.decode('utf-8')
                
                print(f"Chave expirada: {expired_key}", flush=True)
                    
                if expired_key.startswith(f"{REDIS_PREFIX_TTL}:"):  # Usa constante
                    print(f"✨ Processando chave: {expired_key}", flush=True)
                    await process_expired_chat(expired_key)
                else:
                    print(f"❌ Chave não é do chat: {expired_key}", flush=True)
    except Exception as e:
        print(f"Erro no monitor: {str(e)}", flush=True)
    finally:
        pubsub.close()

if __name__ == "__main__":
    load_dotenv()
    
    # Debug das variáveis
    print("\n=== Variáveis de Ambiente ===", flush=True)
    print(f"REDIS_HOST: {os.getenv('REDIS_HOST')}", flush=True)
    print(f"REDIS_PORT: {os.getenv('REDIS_PORT')}", flush=True)
    print(f"WEBHOOK_URL: {os.getenv('WEBHOOK_URL')}", flush=True)
    print("==========================", flush=True)
    
    try:
        redis_client.ping()
        print("\nConectado ao Redis com sucesso!", flush=True)
        print(f"Usando webhook: {WEBHOOK_URL}", flush=True)
        asyncio.run(monitor())
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.", flush=True)
