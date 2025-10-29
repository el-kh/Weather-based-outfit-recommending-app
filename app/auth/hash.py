from argon2 import PasswordHasher

_ph = PasswordHasher()  # Argon2id by default

def hash_pw(plain: str) -> str:
    return _ph.hash(plain)

def verify_pw(hashed: str, plain: str) -> bool:
    try:
        _ph.verify(hashed, plain)
        return True
    except Exception:
        return False
