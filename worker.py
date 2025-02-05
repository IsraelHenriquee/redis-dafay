import redis
import json
import asyncio
import aiohttp
import time
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from constants import (
    REDIS_PREFIX_TTL,
    get_data_key,
    get_user_id_from_ttl_key,
    get_ttl_key
)

# Força flush imediato dos prints
sys.stdout.reconfigure(line_buffering=True)

class WebhookWorker:
    def __init__(self):
        self.max_slots = 15
        self.active_slots = 0
        self.processing = set()
        
        # Carrega configurações
        load_dotenv()
        
        # Conexão com Redis
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True
        )
        
        # Cliente Redis do Upstash para logs
        upstash_url = os.getenv('UPSTASH_REDIS_URL')
        print(f"\n=== CONFIGURANDO UPSTASH ===", flush=True)
        if upstash_url:
            try:
                print(f"URL Upstash: {upstash_url}", flush=True)
                url_parts = upstash_url.replace('redis://', '').split('@')
                auth = url_parts[0].split(':')
                host_port = url_parts[1].split(':')
                
                print(f"Host: {host_port[0]}", flush=True)
                print(f"Port: {host_port[1]}", flush=True)
                print(f"Username: {auth[0]}", flush=True)
                
                self.upstash_client = redis.Redis(
                    host=host_port[0],
                    port=int(host_port[1]),
                    username=auth[0],
                    password=auth[1],
                    decode_responses=True,
                    socket_timeout=5,  # Timeout de 5s
                    socket_connect_timeout=5,  # Timeout de conexão
                    retry_on_timeout=True  # Tenta reconectar se der timeout
                )
                
                # Testa conexão
                if self.upstash_client.ping():
                    print("✅ Conectado ao Upstash!", flush=True)
                else:
                    print("❌ Erro ao conectar no Upstash - ping falhou", flush=True)
            except Exception as e:
                print(f"❌ Erro ao configurar Upstash: {str(e)}", flush=True)
        else:
            print("⚠️ URL do Upstash não configurada", flush=True)
        
        self.webhook_url = os.getenv('WEBHOOK_URL', '').rstrip('/')
        
    def save_webhook_log(self, user_id: str, payload: dict, status: str, response: dict = None):
        """Salva log do webhook no Upstash"""
        try:
            # Se não tem Upstash configurado, só ignora
            if not hasattr(self, 'upstash_client'):
                print("⚠️ Cliente Upstash não configurado", flush=True)
                return
                
            # Tenta reconectar se perdeu conexão
            try:
                if not self.upstash_client.ping():
                    print("⚠️ Ping falhou, tentando reconectar...", flush=True)
                    raise ConnectionError("Ping falhou")
                    
                # Formato: 04-02-2025-20-47-45-123
                timestamp = datetime.now().strftime('%d-%m-%Y-%H-%M-%S-%f')[:-3]
                key = f"webhook:{user_id}:{timestamp}"
                
                print(f"\n=== SALVANDO LOG NO UPSTASH ===", flush=True)
                print(f"Key: {key}", flush=True)
                
                log_data = {
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                    "payload": payload,
                    "status": status
                }
                
                if response:
                    log_data["response"] = response
                    
                # Tenta salvar
                print("Salvando dados...", flush=True)
                result = self.upstash_client.set(key, json.dumps(log_data))
                print(f"Resultado set: {result}", flush=True)
                
                # Expira em 30 dias
                result = self.upstash_client.expire(key, 60 * 60 * 24 * 30)
                print(f"Resultado expire: {result}", flush=True)
                
                print("✅ Log salvo com sucesso!", flush=True)
                
            except redis.ConnectionError as e:
                print(f"❌ Erro de conexão com Upstash: {str(e)}", flush=True)
                raise
                
            except redis.RedisError as e:
                print(f"❌ Erro do Redis: {str(e)}", flush=True)
                raise
                
        except Exception as e:
            print(f"❌ Erro ao salvar log no Upstash: {str(e)}", flush=True)
            print(f"Tipo do erro: {type(e)}", flush=True)
            
    async def send_webhook(self, user_id: str, payload: dict):
        """Envia webhook com retry em caso de erro"""
        try:
            print(f"\n=== ENVIANDO WEBHOOK ===", flush=True)
            print(f"URL: {self.webhook_url}", flush=True)
            print(f"Payload: {json.dumps(payload, indent=2)}", flush=True)
            
            # Log de envio
            self.save_webhook_log(user_id, payload, "sending")
            
            # Timeout de 61s (margem pro servidor de 60s)
            timeout = aiohttp.ClientTimeout(total=61)
            
            async with aiohttp.ClientSession() as session:
                print("\nIniciando request...", flush=True)
                
                try:
                    async with session.post(
                        self.webhook_url,
                        json=payload,
                        ssl=False,
                        timeout=timeout,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'Redis-Worker/1.0'
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
                        
                        # Log de sucesso/erro baseado no status
                        if 200 <= status < 300:
                            self.save_webhook_log(user_id, payload, "success", response_data)
                            return True
                        else:
                            self.save_webhook_log(user_id, payload, "error", response_data)
                            return False
                            
                except asyncio.TimeoutError:
                    error_msg = "Timeout ao enviar webhook"
                    print(f"❌ {error_msg}", flush=True)
                    self.save_webhook_log(user_id, payload, "error", {
                        "error": error_msg,
                        "type": "timeout"
                    })
                    return False
                    
                except Exception as e:
                    error_msg = f"Erro ao enviar webhook: {str(e)}"
                    print(f"❌ {error_msg}", flush=True)
                    self.save_webhook_log(user_id, payload, "error", {
                        "error": error_msg,
                        "type": "request_error"
                    })
                    return False
                    
        except Exception as e:
            error_msg = f"Erro geral ao processar webhook: {str(e)}"
            print(f"❌ {error_msg}", flush=True)
            self.save_webhook_log(user_id, payload, "error", {
                "error": error_msg,
                "type": "general_error"
            })
            return False
            
    async def process_message(self, queue_key: str, message_data: dict):
        """Processa uma mensagem da fila"""
        user_id = queue_key.split(':')[2]  # chat:QUEUE:USER_ID
        
        try:
            self.active_slots += 1
            self.processing.add(user_id)
            
            # Tenta enviar
            success = await self.send_webhook(user_id, message_data)
            
            if not success:
                # Devolve pra fila em caso de erro
                self.redis_client.rpush(queue_key, json.dumps(message_data))
                # Marca pra retry em 30s
                self.redis_client.expire(queue_key, 30)
                
        except Exception as e:
            print(f"❌ Erro ao processar mensagem: {str(e)}", flush=True)
            # Devolve pra fila em caso de erro
            self.redis_client.rpush(queue_key, json.dumps(message_data))
            
        finally:
            self.active_slots -= 1
            self.processing.remove(user_id)
            
    async def run(self):
        """Loop principal do worker"""
        print("=== INICIANDO WORKER ===", flush=True)
        
        while True:
            try:
                # Se tem slots livres
                if self.active_slots < self.max_slots:
                    # Procura filas com mensagens
                    queues = self.redis_client.keys("chat:QUEUE:*")
                    
                    for queue in queues:
                        # Pega próxima mensagem
                        message = self.redis_client.lpop(queue)
                        if not message:
                            continue
                            
                        try:
                            message_data = json.loads(message)
                        except json.JSONDecodeError:
                            print(f"❌ Mensagem inválida: {message}", flush=True)
                            continue
                            
                        # Cria task pra processar
                        asyncio.create_task(self.process_message(queue, message_data))
                        
                        # Se lotou os slots, para
                        if self.active_slots >= self.max_slots:
                            break
                            
                # Pequeno delay antes de checar novamente
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Erro no loop principal: {str(e)}", flush=True)
                # Continua executando mesmo com erro
                await asyncio.sleep(1)
                
if __name__ == "__main__":
    # Inicia worker
    worker = WebhookWorker()
    asyncio.run(worker.run())
