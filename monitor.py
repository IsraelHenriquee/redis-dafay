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

async def process_expired_chat(ttl_key):
    """Processa chat expirado"""
    try:
        user_id = get_user_id_from_ttl_key(ttl_key)
        data_key = get_data_key(user_id)
        
        # Pega dados do chat
        chat_data = redis_client.get(data_key)
        if not chat_data:
            print(f"❌ Dados não encontrados para {user_id}", flush=True)
            return
            
        chat_data = json.loads(chat_data)
        
        # Prepara payload
        payload = {
            "user": user_id,
            "id_agente": chat_data.get("id_agente"),
            "numero_conectado": chat_data.get("numero_conectado"),
            "foto": chat_data.get("foto"),
            "phone": chat_data.get("phone"),
            "sender_name": chat_data.get("sender_name"),
            "chave": chat_data.get("chave", ""),
            "instance_id": chat_data.get("instance_id"),
            "servidor": chat_data.get("servidor"),
            "token": chat_data.get("token"),
            "token_seguranca": chat_data.get("token_seguranca"),
            "modo": chat_data.get("modo"),
            "plataforma_ia": chat_data.get("plataforma_ia", 2),
            "server_url": chat_data.get("server_url", "-"),
            "provider": chat_data.get("provider", 1),
            "id_instancia": chat_data.get("id_instancia"),
            "listamessages": chat_data.get("messages", []),
            "processed_at": datetime.now().isoformat()
        }
        
        # Adiciona na fila
        queue_key = f"chat:QUEUE:{user_id}"
        redis_client.rpush(queue_key, json.dumps(payload))
        
        # Limpa dados do chat
        redis_client.delete(data_key)
        redis_client.delete(ttl_key)
        
    except Exception as e:
        print(f"❌ Erro ao processar chat expirado: {str(e)}", flush=True)
        save_error_log("process_error", "monitor", str(e), {
            "ttl_key": ttl_key,
            "user_id": user_id if 'user_id' in locals() else None
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
