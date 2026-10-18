import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    admin_ids: frozenset[int]
    session: str
    data_dir: Path
    log_level: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "userbot.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


def load_config(require_bot: bool = True) -> Config:
    load_dotenv()

    def need(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise SystemExit(f"Не задана переменная окружения {name} (см. .env.example)")
        return value

    admin_ids = frozenset(
        int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
    )
    if require_bot and not admin_ids:
        raise SystemExit("Не задан ADMIN_IDS — без него в админку никто не войдёт")

    data_dir = Path(os.getenv("DATA_DIR", "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "media").mkdir(exist_ok=True)

    return Config(
        api_id=int(need("API_ID")),
        api_hash=need("API_HASH"),
        bot_token=need("BOT_TOKEN") if require_bot else os.getenv("BOT_TOKEN", ""),
        admin_ids=admin_ids,
        session=os.getenv("SESSION", "userbot").strip() or "userbot",
        data_dir=data_dir,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
