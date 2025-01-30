import redis
import json
from datetime import datetime
import time
import os
import sys
import asyncio
import aiohttp
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
            try:
                # Usa exatamente a mesma configuração do teste
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
            **chat_data["metadata"],  # Expanda todos os campos de metadados
            "user_id": chat_data["metadata"]["user"],  # Adiciona user_id igual ao user
            "messages": chat_data["messages"],  # Lista simples com as mensagens
            "processed_at": datetime.now().isoformat()
        }
        
        print(f"Enviando payload para webhook: {json.dumps(payload, indent=2)}", flush=True)
        
        # Envia para o webhook de forma assíncrona
        asyncio.create_task(send_webhook(payload))
        
        # Remove os dados imediatamente
        redis_client.delete(data_key)
        
    except Exception as e:
        print(f"Erro ao processar chat expirado: {str(e)}", flush=True)

async def monitor():
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
                    # Processa de forma assíncrona
                    await process_expired_chat(key)
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
        
        # Roda o monitor de forma assíncrona
        asyncio.run(monitor())
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.", flush=True)
        exit(1)
