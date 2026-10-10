"""Backend configuration. Credentials never come from browser widgets."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = PROJECT_ROOT / ".local" / "runtime.json"


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "preview"
    database_url: str = field(default="", repr=False)
    household_id: str = ""
    access_mode: str = "local"
    local_editor_subject: str = "local-editor"

    @classmethod
    def load(cls):
        requested = os.environ.get("MENUAGENT_MODE", "auto")
        if requested == "preview":
            return cls()
        if requested not in ("auto", "postgres"):
            raise ValueError("MENUAGENT_MODE must be preview, postgres or auto.")
        path = Path(os.environ.get("MENUAGENT_RUNTIME_FILE", str(LOCAL_CONFIG)))
        saved = json.loads(path.read_text()) if path.is_file() else {}
        database_url = os.environ.get("MENUAGENT_DATABASE_URL", saved.get("database_url", ""))
        if not database_url:
            if requested == "postgres":
                raise ValueError("Configure the MenuAgent database before using PostgreSQL mode.")
            return cls()
        household_id = os.environ.get("MENUAGENT_HOUSEHOLD_ID", saved.get("household_id", ""))
        try:
            household_id = str(UUID(household_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Configure a valid MenuAgent household ID.") from None
        access_mode = os.environ.get("MENUAGENT_ACCESS_MODE", saved.get("access_mode", "local"))
        if access_mode not in ("local", "oidc"):
            raise ValueError("MENUAGENT_ACCESS_MODE must be local or oidc.")
        subject = os.environ.get("MENUAGENT_LOCAL_EDITOR_SUBJECT", saved.get("local_editor_subject", "local-editor"))
        if access_mode == "local" and not subject.strip():
            raise ValueError("Configure a local editor identity.")
        return cls("postgres", database_url, household_id, access_mode, subject)
