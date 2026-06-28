from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env") # type: ignore
    
    database_url: str
    redis_url: str
    jwt_private_key: str
    jwt_public_key: str
    user_jwt_iss: str
    user_jwt_aud: str
    production: bool
    build: str
    debug: bool = False
    version: str = "0.1.0-beta1"
    version_family: str = "v0"
    dummy_password_hash: str = "$argon2id$v=19$m=131072,t=4,p=2$oyquekmTfion1k21h1TYEA$MWrdV1jMYPLZtZCl4/Df76VHbrYnInV4Etc89d/XWsY"
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    rate_limit_trusted_proxy_ips: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = ""
    frontend_url: str

settings = Settings()  # type: ignore
