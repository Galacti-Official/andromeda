from argon2 import PasswordHasher


ph_key = PasswordHasher(
    time_cost=3,
    memory_cost=65536, # 64 MB
    parallelism=2
)


ph_password = PasswordHasher(
    time_cost=4,
    memory_cost=131072,  # 128MB
    parallelism=2
)


def hash_secret(unhashed_secret: str) -> str:
    if len(unhashed_secret) != 43:
        raise ValueError(f"unhashed secret must be 43 characters, got {len(unhashed_secret)}")
    
    return ph_key.hash(unhashed_secret)


def verify_secret(hashed_secret: str, unhashed_secret: str) -> bool:
    try:
        return ph_key.verify(hashed_secret, unhashed_secret)
    except Exception:
        return False


def hash_password(unhashed_password: str) -> str:
    return ph_password.hash(unhashed_password)


def verify_password(hashed_password: str, unhashed_password: str) -> bool:
    try:
        return ph_password.verify(hashed_password, unhashed_password)
    except Exception:
        return False
