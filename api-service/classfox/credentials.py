import os
from pathlib import Path
from typing import Literal, Protocol

import keyring
from dotenv import dotenv_values
from keyring.errors import KeyringError, PasswordDeleteError

from classfox.settings import Preferences, SettingsStore

CredentialName = Literal["llm", "asr", "dashscope", "seed_app", "seed_access", "seed_api"]
CREDENTIAL_NAMES: tuple[CredentialName, ...] = ("llm", "asr", "dashscope", "seed_app", "seed_access", "seed_api")
LEGACY_NAMES: dict[str, CredentialName] = {
    "LLM_API_KEY": "llm",
    "ASR_API_KEY": "asr",
    "DASHSCOPE_API_KEY": "dashscope",
    "SEED_ASR_APP_KEY": "seed_app",
    "SEED_ASR_ACCESS_KEY": "seed_access",
}


class CredentialError(Exception):
    pass


class Credentials(Protocol):
    def get(self, name: CredentialName) -> str | None: ...

    def set(self, name: CredentialName, value: str | None) -> None: ...


class SystemCredentials:
    def get(self, name: CredentialName) -> str | None:
        injected = os.environ.get(f"CLASSFOX_{name.upper()}_KEY")
        if injected:
            return injected
        try:
            return keyring.get_password("ClassFox", name)
        except KeyringError as exc:
            raise CredentialError("无法访问系统凭据存储，请检查系统钥匙串权限") from exc

    def set(self, name: CredentialName, value: str | None) -> None:
        if os.environ.get(f"CLASSFOX_{name.upper()}_KEY"):
            raise CredentialError("此凭据由启动环境提供，请在启动配置中修改")
        try:
            if value is None:
                try:
                    keyring.delete_password("ClassFox", name)
                except PasswordDeleteError:
                    if keyring.get_password("ClassFox", name) is not None:
                        raise
            else:
                keyring.set_password("ClassFox", name, value)
        except KeyringError as exc:
            raise CredentialError("无法更新系统凭据存储，请检查系统钥匙串权限") from exc


def is_placeholder(value: str) -> bool:
    return not value.strip() or any(
        marker in value.casefold() for marker in ("your-key", "your_key", "your-api", "your_api", "sk-your", "placeholder", "changeme")
    )


def import_legacy_settings(source: Path, settings: SettingsStore, credentials: Credentials) -> dict[str, object]:
    if not source.is_file() or source.name.endswith(".example") or source.stat().st_size > 128 * 1024:
        raise ValueError("请选择有效的旧版 .env 配置文件，不能导入发布模板")
    values = dotenv_values(source, interpolate=False)
    preferences = settings.load()
    import_preferences = not settings.path.exists()
    if import_preferences:
        data = preferences.model_dump()
        for old_name, field in [("LLM_BASE_URL", "base_url"), ("LLM_MODEL", "model")]:
            if values.get(old_name):
                data["llm"][field] = values[old_name]
        if values.get("LLM_API_KEY") and not is_placeholder(values["LLM_API_KEY"] or ""):
            data["llm"]["mode"] = "byok"
        mode = values.get("ASR_MODE") or "offline"
        data["asr"]["mode"] = "google" if mode == "local" else mode
        preferences = Preferences.model_validate(data)
    imported: list[str] = []
    for legacy_name, name in LEGACY_NAMES.items():
        value = values.get(legacy_name) or ""
        if not is_placeholder(value) and credentials.get(name) is None:
            credentials.set(name, value)
            imported.append(name)
    if import_preferences:
        settings.save(preferences)
    return {"settings_imported": import_preferences, "credential_names": imported}
