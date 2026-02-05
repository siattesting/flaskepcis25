import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration."""
    
    # Core Flask Security
    SECRET_KEY = os.getenv("SECRET_KEY", "insecure-dev-key-change-in-prod")
    
    # Database
    # Default to localhost Postgres if not set
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/epcis_db"
    )

    # --- CHANGED: New Engine Configuration ---
    # flask-sqlalchemy-lite expects a dict mapping alias names to connection strings.
    # 'default' is required.
    SQLALCHEMY_ENGINES = {
        "default": os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:postgres@db:5432/epcis_db"
        )
    }
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Critical for handling DB connection drops
        "pool_size": 10,
        "max_overflow": 20,
    }

    # JWT Configuration (for Human Operators)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "insecure-jwt-key-change-in-prod")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 hour
    
    # EPCIS / GS1 Settings
    COMPANY_PREFIX = os.getenv("COMPANY_PREFIX", "0000000")  # GCP
    # URN prefix for constructing IDs (e.g., urn:epc:id:sgtin:...)
    EPCIS_URN_PREFIX = f"urn:epc:id:sgtin:{COMPANY_PREFIX}"

class DevelopmentConfig(Config):
    """Local development config."""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production config for African factory deployment."""
    DEBUG = False
    TESTING = False
    
    # Enforce stricter security in production
    @property
    def JWT_COOKIE_SECURE(self):
        return os.getenv("Use_HTTPS", "False").lower() == "true"

class TestingConfig(Config):
    """Testing config."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

# Dictionary to map environment names to classes
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig
}

