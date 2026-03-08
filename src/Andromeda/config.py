from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env") # type: ignore
    
    database_url: str
    jwt_private_key: str
    jwt_public_key: str
    user_jwt_iss: str
    user_jwt_aud: str
    production: str
    debug: bool = False
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    rate_limit_trusted_proxy_ips: str = ""

settings = Settings()  # type: ignore
