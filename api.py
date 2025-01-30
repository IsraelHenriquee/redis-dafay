from flask import Flask, request, jsonify
import redis
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'  # Para HTTPS
app.config['SERVER_NAME'] = None  # Permite qualquer domínio

# Conexão com Redis
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True
)

@app.route('/message', methods=['POST'])
def save_message():
    """
    Endpoint para receber mensagens via POST
    
    Exemplo de curl:
    curl -X POST http://seu-ip:5000/message \
        -H "Content-Type: application/json" \
        -d '{
            "id_agente": 1,
            "numero_conectado": "+5511999999999",
            "foto": "https://example.com/photo.jpg",
            "phone": "+5511888888888",
            "sender_name": "João Silva",
            "user": "joao.silva",
            "chave": "chave123",
            "instance_id": "inst_123",
            "servidor": "srv1",
            "token": "token123",
            "token_seguranca": "sec_token123",
            "modo": "chat",
            "plataforma_ia": 1,
            "server_url": "https://api.example.com",
            "provider": 1,
            "id_instancia": 1,
            "message": "Olá!",
            "ttl": 30
        }'
    """
    try:
        # Pega o JSON do request
        payload = request.json
        
        # Validações básicas
        if not payload:
            return jsonify({"error": "Payload vazio"}), 400
            
        required_fields = ["user", "message"]
        for field in required_fields:
            if field not in payload:
                return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
        
        # Usa o campo user como identificador único do chat
        user_id = payload["user"]
        
        # Pega o TTL do payload ou usa 15 segundos como default
        ttl = payload.get("ttl", 15)
        
        # Chaves no Redis
        ttl_key = f"chat:TTL:{user_id}"
        data_key = f"chat:DATA:{user_id}"
        
        # Pega dados existentes ou cria novo
        current_data = redis_client.get(data_key)
        if current_data:
            data = json.loads(current_data)
            # Adiciona nova mensagem à lista existente
            data["messages"].append(payload["message"])
        else:
            # Se é primeira mensagem, cria estrutura inicial
            metadata = payload.copy()
            del metadata["message"]  # Remove a mensagem dos metadados
            if "ttl" in metadata:  # Remove TTL dos metadados
                del metadata["ttl"]
            
            data = {
                "metadata": metadata,
                "messages": [payload["message"]]
            }
        
        # Salva dados atualizados como string JSON
        redis_client.set(data_key, json.dumps(data))
        
        # Atualiza TTL
        redis_client.set(ttl_key, "", ex=ttl)
        
        return jsonify({
            "success": True,
            "message": f"Mensagem salva para usuário {user_id}, expira em {ttl} segundos"
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Erro ao processar mensagem: {str(e)}"
        }), 500

if __name__ == "__main__":
    try:
        redis_client.ping()
        print("Conectado ao Redis com sucesso!")
        app.run(host='0.0.0.0', port=5000)
    except redis.ConnectionError:
        print("Erro ao conectar ao Redis. Verifique se o servidor está rodando.")
