import redis

# Conexão com Upstash
r = redis.Redis(
    host='needed-lioness-11713.upstash.io',
    port=6379,
    password='AS3BAAIjcDExN2I2MTUzNTIwZWU0MmQxYjVjMzAyZTkzNmEzMGEzYXAxMA',
    ssl=True,
    decode_responses=True  # Para não precisar fazer decode manual
)

# Testa conexão
print("\n=== Testando Conexão Upstash ===")

# Ping
print("\n1. Testando PING:")
print(f"Ping: {r.ping()}")

# Set/Get
print("\n2. Testando SET/GET:")
r.set('teste', 'Redis DO funcionando! 🚀')
print(f"Valor: {r.get('teste')}")

# Info
print("\n3. Info do Servidor:")
info = r.info()
print(f"Redis Version: {info.get('redis_version')}")
print(f"Connected Clients: {info.get('connected_clients')}")

print("\n✅ Teste completo!")
