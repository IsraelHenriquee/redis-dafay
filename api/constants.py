"""
Constantes compartilhadas entre API e Monitor
"""

# Prefixos das chaves no Redis
REDIS_PREFIX_TTL = "chat:TTL"    # Chave de TTL: chat:TTL:{user_id}
REDIS_PREFIX_DATA = "chat:DATA"   # Chave de dados: chat:DATA:{user_id}

def get_ttl_key(user_id: str) -> str:
    """Retorna a chave TTL para um usuário"""
    return f"{REDIS_PREFIX_TTL}:{user_id}"

def get_data_key(user_id: str) -> str:
    """Retorna a chave de dados para um usuário"""
    return f"{REDIS_PREFIX_DATA}:{user_id}"

def get_user_id_from_ttl_key(ttl_key: str) -> str:
    """Extrai o user_id de uma chave TTL"""
    return ttl_key.split(":")[-1]

# Estrutura padrão dos dados
DEFAULT_DATA_STRUCTURE = {
    "metadata": {},      # Todos os campos do payload exceto message e ttl
    "messages": []       # Lista de mensagens
}

# Campos obrigatórios no payload
REQUIRED_FIELDS = ["user", "message"]

# Tempo padrão de expiração (segundos)
DEFAULT_TTL = 15
