import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class RuntimeConfig:
    data_dir: Path = field(default_factory=lambda: user_data_path("ClassFox", appauthor=False))
    api_token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    host: str = "127.0.0.1"
    port: int = 8765
    allowed_origins: tuple[str, ...] = (
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
    )
    upload_limit: int = 25 * 1024 * 1024

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        data_path = os.environ.get("CLASSFOX_DATA_DIR")
        return cls(
            data_dir=Path(data_path).expanduser().resolve() if data_path else user_data_path("ClassFox", appauthor=False),
            api_token=os.environ.get("CLASSFOX_API_TOKEN") or secrets.token_urlsafe(32),
            port=int(os.environ.get("CLASSFOX_PORT", os.environ.get("API_PORT", "8765"))),
        )

    def __post_init__(self) -> None:
        if not self.api_token or not 0 <= self.port <= 65535:
            raise ValueError("无效的服务启动配置")
