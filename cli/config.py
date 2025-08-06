import os
import json
from pathlib import Path
from typing import Any, Dict
from rich.console import Console

console = Console()

DEFAULT_CONFIG = {
    "api_keys": {},
    "base_url": "https://api.openai.com/v1",
    "default_agent": "default",
    "llm_provider": "openai",
    "model_name": "gpt-4",
    "scan_settings": {
        "include_dependencies": False,
        "severity_threshold": "medium",
        "output_format": "console"
    }
}

class ConfigManager:
    """
    Handles loading, writing, and updating config.json
    with priority: config.json > .env
    """
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Use user home directory for config
            home = Path.home()
            config_dir = home / ".spoon-audit"
            config_dir.mkdir(exist_ok=True)
            self.path = config_dir / "config.json"
        else:
            self.path = Path(config_path)

    def load(self) -> Dict[str, Any]:
        """Load configuration from file or environment variables"""
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError as e:
                console.print(f"[red]Error reading config file: {e}[/red]")
                return self._load_from_env()
        
        return self._load_from_env()

    def _load_from_env(self) -> Dict[str, Any]:
        """Build configuration from environment variables"""
        cfg = DEFAULT_CONFIG.copy()
        
        # Map environment variables
        if os.getenv("OPENAI_API_KEY"):
            cfg["api_keys"]["openai"] = os.getenv("OPENAI_API_KEY")
        if os.getenv("SPOON_API_KEY"):
            cfg["api_keys"]["spoonos"] = os.getenv("SPOON_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            cfg["api_keys"]["anthropic"] = os.getenv("ANTHROPIC_API_KEY")
        
        if os.getenv("SPOON_BASE_URL"):
            cfg["base_url"] = os.getenv("SPOON_BASE_URL")
        if os.getenv("SPOON_MODEL"):
            cfg["model_name"] = os.getenv("SPOON_MODEL")
        if os.getenv("LLM_PROVIDER"):
            cfg["llm_provider"] = os.getenv("LLM_PROVIDER")
            
        return cfg

    def write(self, data: Dict[str, Any]) -> None:
        """Write configuration to file"""
        try:
            # Ensure directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            console.print(f"[red]Error writing config file: {e}[/red]")
            raise

    def show(self) -> None:
        """Display current configuration"""
        cfg = self.load()
        
        # Mask sensitive information
        display_cfg = self._mask_sensitive_data(cfg)
        
        console.print("[blue]Current Configuration:[/blue]")
        console.print(json.dumps(display_cfg, indent=2))
        console.print(f"\n[dim]Config file location: {self.path}[/dim]")

    def _mask_sensitive_data(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Mask API keys and other sensitive information for display"""
        import copy
        masked_cfg = copy.deepcopy(cfg)
        
        if "api_keys" in masked_cfg:
            for key in masked_cfg["api_keys"]:
                value = masked_cfg["api_keys"][key]
                if value:
                    # Show first 8 characters and mask the rest
                    masked_cfg["api_keys"][key] = f"{value[:8]}..." if len(value) > 8 else "***"
        
        return masked_cfg

    def get_api_key(self, provider: str) -> str:
        """Get API key for a specific provider"""
        cfg = self.load()
        return cfg.get("api_keys", {}).get(provider, "")

    def set_api_key(self, provider: str, key: str) -> None:
        """Set API key for a specific provider"""
        cfg = self.load()
        if "api_keys" not in cfg:
            cfg["api_keys"] = {}
        cfg["api_keys"][provider] = key
        self.write(cfg)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a configuration setting using dot notation (e.g., 'scan_settings.severity_threshold')"""
        cfg = self.load()
        
        keys = key.split('.')
        value = cfg
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """Set a configuration setting using dot notation"""
        cfg = self.load()
        keys = key.split('.')
        
        # Navigate to the parent dict
        current = cfg
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # Set the final value
        current[keys[-1]] = value
        self.write(cfg)