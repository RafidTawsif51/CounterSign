from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read .env from backend/ or the repo root; ignore frontend-only vars like VITE_API_URL.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Mock flags: true = mock adapter, false = real API.
    mock_nessie: bool = True
    mock_crs: bool = True
    mock_apify: bool = True
    mock_twilio: bool = True
    mock_cartesia: bool = True
    mock_claude: bool = True  # extraction only
    mock_injection: bool = False  # the real scanner needs no external service: layer 1 is local, the Claude classifier follows mock_claude
    mock_risk: bool = False  # the real assessor needs no external service; its Claude classifier follows mock_claude

    anthropic_api_key: str = ""
    claude_model_main: str = "claude-sonnet-5-5"
    claude_model_fast: str = "claude-haiku-5-5"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # Webhook authentication. REQUIRE_CALL_TOKEN: each verification call has its own secret in its webhook URLs. Blank means on
    # whenever MOCK_TWILIO is false. VALIDATE_SIGNATURES: strict mode, a valid X-Twilio-Signature is also required (off by
    # default because trial accounts fetch TwiML without one).
    twilio_require_call_token: Optional[bool] = None
    twilio_validate_signatures: bool = False
    public_base_url: str = ""

    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""
    stt_api_key: str = ""

    nessie_api_key: str = ""
    apify_token: str = ""
    crs_api_key: str = ""

    database_url: str = "sqlite:///./countersign.db"

    demo_vendor_phone: str = ""
    # Comma separated. Kept as a string because pydantic-settings parses list env vars as JSON.
    allowed_call_numbers: str = ""

    bounty_webhook_secret: str = ""

    # Where uploaded invoice PDFs are saved (generated filenames only).
    upload_dir: str = "./uploads"

    # Extraction results keyed by SHA-256 of the document. Survives demo resets; rebuild with
    # `python -m scripts.warm_cache` after a fresh deploy.
    extract_cache_dir: str = "./.cache/extractions"

    # Injection classifier verdicts keyed by content hash.
    injection_cache_dir: str = "./.cache/injection"

    # Urgency / secrecy / authority classifier verdicts keyed by content hash.
    risk_cache_dir: str = "./.cache/risk"

    frontend_url: str = ""

    @field_validator("twilio_require_call_token", mode="before")
    @classmethod
    def _blank_is_default(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def call_token_required(self) -> bool:
        """Per-call webhook secret: the setting if given, otherwise on whenever Twilio is real."""
        return (not self.mock_twilio) if self.twilio_require_call_token is None else self.twilio_require_call_token

    @property
    def allowed_call_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.allowed_call_numbers.split(",") if n.strip()]

    @property
    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:5173"]
        if self.frontend_url:
            origins.append(self.frontend_url.rstrip("/"))
        return origins

    @property
    def mock_flags(self) -> dict[str, bool]:
        return {
            "nessie": self.mock_nessie,
            "crs": self.mock_crs,
            "apify": self.mock_apify,
            "twilio": self.mock_twilio,
            "cartesia": self.mock_cartesia,
            "claude": self.mock_claude,
            "injection": self.mock_injection,
            "risk": self.mock_risk,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
