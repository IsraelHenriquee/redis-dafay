import redis
import requests
import json
from datetime import datetime
import time
import os
import sys
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

def process_expired_chat(ttl_key):
    """
    Quando um chat expira, envia todas as mensagens para o webhook
    """
    try:
        if not WEBHOOK_URL:
            print("WEBHOOK_URL não configurada no .env", flush=True)
            return
            
        # Pega o ID do usuário do ttl_key (formato: ttl:chat:user123)
        user_id = ttl_key.split(':')[2]
        
        # Tenta adquirir lock para este usuário
        lock_key = f"lock:chat:{user_id}"
        if not acquire_lock(lock_key):
            print(f"Outro processo já está tratando o chat do usuário {user_id}", flush=True)
            return
            
        # A chave dos dados está no formato data:chat:user123
        data_key = f"data:chat:{user_id}"
        
        print(f"\nProcessando chat expirado do usuário: {user_id}", flush=True)
        
        # Pega os dados do hash
        data = redis_client.hget(data_key, "data")
        
        if not data:
            print(f"Dados não encontrados para {data_key}", flush=True)
            return
            
        # Converte os dados do Redis para dicionário
        chat_data = json.loads(data)
        
        # Prepara o payload
        payload = {
            **chat_data["metadata"],  # Expande todos os campos de metadados
            "user_id": chat_data["metadata"]["user"],  # Adiciona user_id igual ao user
            "messages": chat_data["messages"],  # Lista simples com as mensagens
            "processed_at": datetime.now().isoformat()
        }
        
        print(f"Enviando payload para webhook: {json.dumps(payload, indent=2)}", flush=True)
        
        # Envia para o webhook
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"Resposta do webhook: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"Erro na resposta: {response.text}", flush=True)
            
        # Após enviar com sucesso, remove os dados
        redis_client.delete(data_key)
        
    except Exception as e:
        print(f"Erro ao processar chat expirado: {str(e)}", flush=True)

def monitor():
    """
    Monitora chaves que expiram no Redis
    """
    pubsub = redis_client.pubsub()
    
    # Inscreve no canal de eventos de expiração
    pubsub.psubscribe('__keyevent@0__:expired')
    
    print("Monitorando chats que expiram...", flush=True)
    print(f"Webhook configurado para: {WEBHOOK_URL}", flush=True)
    
    try:
        for message in pubsub.listen():
            if message['type'] == 'pmessage':
                key = message['data']
                if key.startswith('ttl:chat:'):
                    process_expired_chat(key)
    except KeyboardInterrupt:
        print("\nMonitoramento interrompido", flush=True)
    finally:
        pubsub.close()

if __name__ == "__main__":
    load_dotenv()
    
    # Debug das variáveis
    print("=== Variáveis de Ambiente ===", flush=True)
    print(f"REDIS_HOST: {os.getenv('REDIS_HOST')}", flush=True)
    print(f"REDIS_PORT: {os.getenv('REDIS_PORT')}", flush=True)
    print(f"WEBHOOK_URL: {os.getenv('WEBHOOK_URL')}", flush=True)
    print("==========================", flush=True)
    
    if not os.getenv('WEBHOOK_URL'):
        print("ERRO: WEBHOOK_URL não configurada!", flush=True)
        exit(1)
    
    try:
        redis_client.ping()
        print("Conectado ao Redis com sucesso!", flush=True)
        print(f"Usando webhook: {os.getenv('WEBHOOK_URL')}", flush=True)
        monitor()
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.", flush=True)
        exit(1)
