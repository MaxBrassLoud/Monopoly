import random
import string

CHARSET = string.ascii_letters + string.digits

def create_user_id():
    parts = []
    for _ in range(3):
        parts.append(''.join(random.choice(CHARSET) for _ in range(4)))
    parts.append(''.join(random.choice(CHARSET) for _ in range(4)))
    return "-".join(parts)