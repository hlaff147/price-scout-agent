from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações globais da aplicação PromoRadar."""

    # Telegram
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    ALLOWED_TELEGRAM_CHAT_IDS: str | None = None

    # Banco de Dados
    DATABASE_PATH: str = "data/promoradar.db"

    # Scraping & Rede
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    # Aplicação
    LOG_LEVEL: str = "INFO"
    CHECK_INTERVAL_HOURS: int = 1
    DRY_RUN: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def has_telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    @property
    def allowed_chat_ids(self) -> set[str]:
        ids = set()
        if self.TELEGRAM_CHAT_ID:
            ids.add(str(self.TELEGRAM_CHAT_ID).strip())
        if self.ALLOWED_TELEGRAM_CHAT_IDS:
            for cid in self.ALLOWED_TELEGRAM_CHAT_IDS.split(","):
                cid_clean = cid.strip()
                if cid_clean:
                    ids.add(cid_clean)
        return ids

    @property
    def db_path(self) -> Path:
        path = Path(self.DATABASE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
