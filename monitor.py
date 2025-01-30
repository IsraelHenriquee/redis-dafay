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
    get_user_id_from_ttl_key
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

async def process_expired_chat(ttl_key):
    """
    Quando um chat expira, envia todas as mensagens para o webhook
    """
    try:
        # Extrai o user_id da chave TTL usando função auxiliar
        user_id = get_user_id_from_ttl_key(ttl_key)
        print(f"\nProcessando chat expirado do usuário: {user_id}", flush=True)
        
        # Chave dos dados usando função auxiliar
        data_key = get_data_key(user_id)
        
        # Pega os dados do Redis
        chat_data = redis_client.get(data_key)
        if not chat_data:
            print(f"Dados não encontrados para {user_id}", flush=True)
            return
            
        # Converte de JSON
        chat_data = json.loads(chat_data)
        
        # Monta o payload
        payload = {
            **chat_data["metadata"],  # Expanda todos os campos de metadados
            "user_id": chat_data["metadata"]["user"],  # Adiciona user_id igual ao user
            "listamessages": chat_data["messages"],  # Alterado aqui
            "processed_at": datetime.now().isoformat()
        }
        
        print(f"Enviando payload para webhook: {json.dumps(payload, indent=2)}", flush=True)
        
        # Envia para o webhook de forma assíncrona
        success = await send_webhook(payload)
        
        if success:
            # Remove os dados do Redis
            redis_client.delete(data_key)
            print(f"Dados removidos do Redis para {user_id}", flush=True)
        else:
            print(f"Erro ao enviar webhook para {user_id}", flush=True)
            
    except Exception as e:
        print(f"Erro ao processar chat expirado: {str(e)}", flush=True)

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
