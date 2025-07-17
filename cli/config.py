import os
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG = {
    "api_keys": {},
    "base_url": "",
    "default_agent": "default",
    "llm_provider": "openai",
    "model_name": None
}

class ConfigManager:
    """
    Handles loading, writing, and updating config.json
    with priority: config.json > .env
    """
    def __init__(self, config_path: str = "config.json"):
        self.path = Path(config_path)

    def load(self) -> Dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text())
        # Build from .env
        cfg = DEFAULT_CONFIG.copy()
        # Map env variables
        if os.getenv("OPENAI_API_KEY"):
            cfg["api_keys"]["openai"] = os.getenv("OPENAI_API_KEY")
        if os.getenv("SPOON_API_KEY"):
            cfg["api_keys"]["spoonos"] = os.getenv("SPOON_API_KEY")
        if os.getenv("SPOON_BASE_URL"):
            cfg["base_url"] = os.getenv("SPOON_BASE_URL")
        if os.getenv("SPOON_MODEL"):
            cfg["model_name"] = os.getenv("SPOON_MODEL")
        return cfg

    def write(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def show(self) -> None:
        cfg = self.load()
        print(json.dumps(cfg, indent=2))
