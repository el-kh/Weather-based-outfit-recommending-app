import bcrypt

def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_pw(hashed: str, password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())
