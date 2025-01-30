import requests

# URL do webhook
url = "https://painel.israelhenrique.com.br/webhook/process"

# Payload de teste
payload = {
    "id_agente": 1,
    "numero_conectado": "+5511999999999",
    "user": "TESTE",
    "messages": ["Mensagem de teste"],
    "processed_at": "2025-01-30T19:41:24.084578"
}

print(f"\nTestando webhook...")
print(f"URL: {url}")
print(f"Payload: {payload}")

# Tenta enviar
try:
    response = requests.post(
        url, 
        json=payload,
        verify=False,  # Desativa verificação SSL
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Redis-Monitor-Test/1.0'
        },
        timeout=30
    )
    
    print(f"\nResposta:")
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
    
except requests.exceptions.RequestException as e:
    print(f"\nERRO ao enviar:")
    print(f"Tipo: {type(e)}")
    print(f"Mensagem: {str(e)}")
