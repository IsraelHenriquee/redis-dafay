import redis
import json
from datetime import datetime
import time
import os
import sys
import requests  # Trocando aiohttp por requests
from dotenv import load_dotenv

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

def send_webhook(payload):
    """Envia dados para o webhook de forma síncrona"""
    # Remove barra final se existir
    webhook_url = WEBHOOK_URL.rstrip('/')
    
    try:
        print(f"\n=== ENVIANDO WEBHOOK ===", flush=True)
        print(f"URL: {webhook_url}", flush=True)
        print(f"Payload: {json.dumps(payload, indent=2)}", flush=True)
        
        print("\nIniciando request...", flush=True)
        
        # Usa requests ao invés de aiohttp
        response = requests.post(
            webhook_url,
            json=payload,
            verify=False,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Redis-Monitor/1.0'
            },
            timeout=30
        )
        
        print(f"\nResposta do webhook:", flush=True)
        print(f"Status: {response.status_code}", flush=True)
        print(f"Body: {response.text}", flush=True)
        
        if response.status_code == 200:
            print("\n✅ Webhook enviado com sucesso!", flush=True)
        else:
            print(f"\n❌ Erro na resposta do webhook:", flush=True)
            print(f"Status: {response.status_code}", flush=True)
            print(f"Body: {response.text}", flush=True)
        
        return response.status_code == 200
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Não conseguiu conectar ao servidor:", flush=True)
        print(f"Erro: {str(e)}", flush=True)
        return False
        
    except requests.exceptions.Timeout:
        print(f"\n❌ Timeout ao enviar webhook", flush=True)
        print(f"O servidor não respondeu em 30 segundos", flush=True)
        return False
        
    except Exception as e:
        print(f"\n❌ ERRO GRAVE ao enviar webhook:", flush=True)
        print(f"Tipo: {type(e)}", flush=True)
        print(f"Mensagem: {str(e)}", flush=True)
        return False

def process_expired_chat(ttl_key):
    """
    Quando um chat expira, envia todas as mensagens para o webhook
    """
    try:
        # Extrai o user_id da chave TTL (formato: chat:TTL:{user_id})
        user_id = ttl_key.split(':')[-1]
        print(f"\nProcessando chat expirado do usuário: {user_id}", flush=True)
        
        # Chave dos dados
        data_key = f"chat:DATA:{user_id}"
        
        # Pega os dados do Redis
        chat_data = redis_client.get(data_key)
        if not chat_data:
            print(f"Dados não encontrados para {user_id}", flush=True)
            return
            
        # Converte de JSON
        chat_data = json.loads(chat_data)
        
        # Prepara o payload
        payload = {
            **chat_data["metadata"],  # Expanda todos os campos de metadados
            "user_id": chat_data["metadata"]["user"],  # Adiciona user_id igual ao user
            "messages": chat_data["messages"],  # Lista simples com as mensagens
            "processed_at": datetime.now().isoformat()
        }
        
        print(f"Enviando payload para webhook: {json.dumps(payload, indent=2)}", flush=True)
        
        # Envia para o webhook
        success = send_webhook(payload)
        
        if success:
            # Remove os dados do Redis
            redis_client.delete(data_key)
            print(f"Dados removidos do Redis para {user_id}", flush=True)
        else:
            print(f"Erro ao enviar webhook para {user_id}", flush=True)
            
    except Exception as e:
        print(f"Erro ao processar chat expirado: {str(e)}", flush=True)

def monitor():
    """
    Monitora chaves que expiram no Redis
    """
    pubsub = redis_client.pubsub()
    pubsub.psubscribe('__keyevent@0__:expired')
    
    print("\nMonitorando chats que expiram...", flush=True)
    print(f"Webhook configurado para: {WEBHOOK_URL}", flush=True)
    
    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            expired_key = message['data'].decode('utf-8')
            if expired_key.startswith('chat:TTL:'):
                # Processa em thread separada para não bloquear
                process_expired_chat(expired_key)

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
        monitor()
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.", flush=True)
