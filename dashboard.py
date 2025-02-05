from flask import Flask, render_template_string
import redis
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# HTML template
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Redis Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        pre {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            max-height: 200px;
            overflow-y: auto;
        }
        .card {
            margin-bottom: 20px;
        }
        .attempt {
            border-left: 4px solid #6c757d;
            padding-left: 10px;
            margin-bottom: 10px;
        }
        .attempt.success {
            border-left-color: #198754;
        }
        .attempt.error {
            border-left-color: #dc3545;
        }
    </style>
    <script>
        function refreshPage() {
            location.reload();
        }
        setInterval(refreshPage, 5000);
        
        function togglePayload(id) {
            const el = document.getElementById(id);
            if (el.style.display === 'none') {
                el.style.display = 'block';
            } else {
                el.style.display = 'none';
            }
        }
    </script>
</head>
<body>
    <div class="container mt-4">
        <h1>Redis Dashboard</h1>
        <div class="row mt-4">
            <!-- Webhooks -->
            <div class="col-md-12 mb-4">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h5 class="card-title mb-0">📝 Logs de Webhook ({{ webhooks|length }})</h5>
                    </div>
                    <div class="card-body">
                        {% for webhook in webhooks %}
                        <div class="mb-4 p-3 border rounded">
                            <h6>Usuário: {{ webhook.user_id }}</h6>
                            <div class="text-muted small">
                                Criado em: {{ webhook.created_at }}<br>
                                Total tentativas: {{ webhook.total_attempts }}<br>
                                Última atualização: {{ webhook.updated_at }}
                            </div>
                            
                            <div class="mt-3">
                                <h6>Tentativas:</h6>
                                {% for attempt in webhook.attempts %}
                                <div class="attempt {{ attempt.status }}">
                                    <div class="d-flex justify-content-between align-items-start">
                                        <div>
                                            <strong>Status:</strong> 
                                            {% if attempt.status == 'success' %}
                                                <span class="text-success">✅ Sucesso</span>
                                            {% elif attempt.status == 'error' %}
                                                <span class="text-danger">❌ Erro</span>
                                            {% else %}
                                                <span class="text-warning">⚠️ {{ attempt.status }}</span>
                                            {% endif %}
                                            <br>
                                            <small class="text-muted">{{ attempt.timestamp }}</small>
                                        </div>
                                        <button class="btn btn-sm btn-outline-secondary" 
                                                onclick="togglePayload('payload-{{ loop.index }}-{{ webhook.user_id }}')">
                                            Ver Payload
                                        </button>
                                    </div>
                                    <div id="payload-{{ loop.index }}-{{ webhook.user_id }}" style="display: none;" class="mt-2">
                                        <pre><code>{{ attempt.payload|tojson(indent=2) }}</code></pre>
                                        {% if attempt.response %}
                                        <strong>Resposta:</strong>
                                        <pre><code>{{ attempt.response|tojson(indent=2) }}</code></pre>
                                        {% endif %}
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Filas -->
            <div class="col-md-6 mb-4">
                <div class="card">
                    <div class="card-header bg-success text-white">
                        <h5 class="card-title mb-0">📥 Filas ({{ queues|length }})</h5>
                    </div>
                    <div class="card-body">
                        {% for queue in queues %}
                        <div class="mb-3 p-2 border rounded">
                            <strong>Fila:</strong> {{ queue.name }}<br>
                            <strong>Mensagens:</strong> {{ queue.size }}<br>
                            <strong>TTL:</strong> {{ queue.ttl }}s<br>
                            {% if queue.messages %}
                            <div class="mt-2">
                                <button class="btn btn-sm btn-outline-secondary" 
                                        onclick="togglePayload('queue-{{ loop.index }}')">
                                    Ver Mensagens
                                </button>
                                <div id="queue-{{ loop.index }}" style="display: none;" class="mt-2">
                                    <pre><code>{{ queue.messages|tojson(indent=2) }}</code></pre>
                                </div>
                            </div>
                            {% endif %}
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Chats -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <h5 class="card-title mb-0">💬 Chats ({{ chats|length }})</h5>
                    </div>
                    <div class="card-body">
                        {% for chat in chats %}
                        <div class="mb-3 p-2 border rounded">
                            <strong>Chat:</strong> {{ chat.id }}<br>
                            <strong>Usuário:</strong> {{ chat.user_id }}<br>
                            <strong>Mensagens:</strong> {{ chat.messages }}<br>
                            <div class="mt-2">
                                <button class="btn btn-sm btn-outline-secondary" 
                                        onclick="togglePayload('chat-{{ loop.index }}')">
                                    Ver Dados
                                </button>
                                <div id="chat-{{ loop.index }}" style="display: none;" class="mt-2">
                                    <pre><code>{{ chat.data|tojson(indent=2) }}</code></pre>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

def connect_redis():
    return redis.Redis(
        host=os.getenv('REDIS_HOST'),
        port=int(os.getenv('REDIS_PORT')),
        password=os.getenv('REDIS_PASSWORD'),
        decode_responses=True
    )

@app.route('/')
def dashboard():
    redis_client = connect_redis()
    
    # Webhooks
    webhooks = []
    for key in redis_client.keys("webhook:user:*"):
        data = json.loads(redis_client.get(key))
        webhooks.append(data)  # Agora pegamos todos os dados
    
    # Filas
    queues = []
    for key in redis_client.keys("chat:QUEUE:*"):
        messages = []
        # Pega até 5 mensagens da fila sem remover
        for i in range(min(5, redis_client.llen(key))):
            msg = redis_client.lindex(key, i)
            if msg:
                messages.append(json.loads(msg))
                
        queues.append({
            'name': key,
            'size': redis_client.llen(key),
            'ttl': redis_client.ttl(key),
            'messages': messages
        })
    
    # Chats
    chats = []
    for key in redis_client.keys("chat:DATA:*"):
        data = json.loads(redis_client.get(key))
        chats.append({
            'id': key,
            'user_id': data.get('user_id', 'N/A'),
            'messages': len(data.get('messages', [])),
            'data': data
        })
    
    return render_template_string(HTML, 
        webhooks=webhooks,
        queues=queues,
        chats=chats
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
