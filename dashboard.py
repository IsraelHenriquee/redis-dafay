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
    <script>
        function refreshPage() {
            location.reload();
        }
        // Auto refresh a cada 5 segundos
        setInterval(refreshPage, 5000);
    </script>
</head>
<body>
    <div class="container mt-4">
        <h1>Redis Dashboard</h1>
        <div class="row mt-4">
            <!-- Webhooks -->
            <div class="col-md-6 mb-4">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h5 class="card-title mb-0">📝 Logs de Webhook ({{ webhooks|length }})</h5>
                    </div>
                    <div class="card-body">
                        {% for webhook in webhooks %}
                        <div class="mb-3 p-2 border rounded">
                            <strong>Usuário:</strong> {{ webhook.user_id }}<br>
                            <strong>Tentativas:</strong> {{ webhook.total_attempts }}<br>
                            <strong>Última atualização:</strong> {{ webhook.updated_at }}<br>
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
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Chats -->
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <h5 class="card-title mb-0">💬 Chats ({{ chats|length }})</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                        {% for chat in chats %}
                        <div class="col-md-4 mb-3">
                            <div class="p-2 border rounded">
                                <strong>Chat:</strong> {{ chat.id }}<br>
                                <strong>Usuário:</strong> {{ chat.user_id }}<br>
                                <strong>Mensagens:</strong> {{ chat.messages }}<br>
                            </div>
                        </div>
                        {% endfor %}
                        </div>
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
        webhooks.append({
            'user_id': data['user_id'],
            'total_attempts': data.get('total_attempts', 0),
            'updated_at': data.get('updated_at', 'N/A')
        })
    
    # Filas
    queues = []
    for key in redis_client.keys("chat:QUEUE:*"):
        queues.append({
            'name': key,
            'size': redis_client.llen(key),
            'ttl': redis_client.ttl(key)
        })
    
    # Chats
    chats = []
    for key in redis_client.keys("chat:DATA:*"):
        data = json.loads(redis_client.get(key))
        chats.append({
            'id': key,
            'user_id': data.get('user_id', 'N/A'),
            'messages': len(data.get('messages', []))
        })
    
    return render_template_string(HTML, 
        webhooks=webhooks,
        queues=queues,
        chats=chats
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
