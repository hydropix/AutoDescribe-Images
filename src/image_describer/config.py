"""Configuration loading module."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv
from ollama import Client

load_dotenv()

# User preferences file location (in config directory)
USER_PREFS_FILE = Path(__file__).parent.parent.parent / "config" / "user_preferences.json"


@dataclass
class UserPreferences:
    """User preferences that persist between sessions."""

    image_folder: str = ""
    ollama_model: str = ""
    preset_key: str = ""
    prefix: str = ""
    suffix: str = ""
    temperature: float = 0.7
    overwrite: bool = True
    # OpenRouter settings (API key loaded from environment, not persisted here)
    provider: str = "ollama"  # "ollama" or "openrouter"
    openrouter_model: str = "openai/gpt-4o-mini"
    custom_prompt: str = ""  # Additional text appended to the preset prompt


def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from environment variable.

    Returns:
        The API key from OPENROUTER_API_KEY env var, or empty string if not set.
    """
    return os.getenv("OPENROUTER_API_KEY", "")


def load_user_preferences() -> UserPreferences:
    """Load user preferences from JSON file.

    Returns:
        UserPreferences object with saved values or defaults.
    """
    if USER_PREFS_FILE.exists():
        try:
            with open(USER_PREFS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return UserPreferences(
                image_folder=data.get("image_folder", ""),
                ollama_model=data.get("ollama_model", ""),
                preset_key=data.get("preset_key", ""),
                prefix=data.get("prefix", ""),
                suffix=data.get("suffix", ""),
                temperature=data.get("temperature", 0.7),
                overwrite=data.get("overwrite", True),
                provider=data.get("provider", "ollama"),
                openrouter_model=data.get("openrouter_model", "openai/gpt-4o-mini"),
                custom_prompt=data.get("custom_prompt", ""),
            )
        except (json.JSONDecodeError, KeyError):
            pass
    return UserPreferences()


def save_user_preferences(prefs: UserPreferences) -> None:
    """Save user preferences to JSON file.

    Args:
        prefs: UserPreferences object to save.
    """
    data = {
        "image_folder": prefs.image_folder,
        "ollama_model": prefs.ollama_model,
        "preset_key": prefs.preset_key,
        "prefix": prefs.prefix,
        "suffix": prefs.suffix,
        "temperature": prefs.temperature,
        "overwrite": prefs.overwrite,
        "provider": prefs.provider,
        "openrouter_model": prefs.openrouter_model,
        "custom_prompt": prefs.custom_prompt,
    }
    with open(USER_PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@dataclass
class PromptPreset:
    """A prompt preset configuration."""

    key: str
    name: str
    prompt: str
    markdown_format: bool = False


@dataclass
class Config:
    """Application configuration."""

    ollama_host: str = "http://localhost:11434"
    model: str = "qwen3-vl:4b"
    system_prompt: str = "Describe this image in detail."
    temperature: float = 0.7
    num_ctx: int = 8192  # Context window size (important for vision models with large images)
    supported_extensions: list[str] = field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp", ".gif"]
    )
    description_suffix: str = ""
    description_prefix: str = ""
    markdown_format: bool = False
    # OpenRouter settings
    provider: str = "ollama"  # "ollama" or "openrouter"
    openrouter_api_key: str = ""


def load_presets(config_path: Path | None = None) -> list[PromptPreset]:
    """Load prompt presets from YAML configuration.

    Args:
        config_path: Path to YAML configuration file.

    Returns:
        List of PromptPreset objects.
    """
    if config_path is None:
        config_path = Path("config/config.yaml")

    presets = []

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        prompts_data = data.get("prompts", {})
        for key, preset_data in prompts_data.items():
            presets.append(
                PromptPreset(
                    key=key,
                    name=preset_data.get("name", key),
                    prompt=preset_data.get("prompt", "Describe this image."),
                    markdown_format=preset_data.get("markdownFormat", False),
                )
            )

    if not presets:
        presets.append(
            PromptPreset(
                key="default",
                name="Default",
                prompt="Describe this image in detail.",
            )
        )

    return presets


def list_ollama_models(ollama_host: str | None = None) -> list[str]:
    """List available Ollama models.

    Args:
        ollama_host: Ollama server host URL.

    Returns:
        List of model names.
    """
    host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

    try:
        client = Client(host=host)
        response = client.list()
        models = [model.model for model in response.models]
        return sorted(models)
    except Exception:
        return ["qwen3-vl:4b", "llava", "llama3.2-vision"]


def load_config(
    config_path: Path | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    preset_key: str | None = None,
) -> Config:
    """Load configuration from .env and optional YAML file.

    Priority (highest to lowest):
        1. CLI arguments (suffix, prefix, preset_key)
        2. Environment variables (.env)
        3. YAML config file
        4. Default values

    Args:
        config_path: Path to YAML configuration file.
        suffix: Suffix to append to descriptions (from CLI).
        prefix: Prefix to prepend to descriptions (from CLI).
        preset_key: Key of the preset to use.

    Returns:
        Config: The loaded configuration object.
    """
    # Start with defaults
    ollama_host = Config.ollama_host
    model = Config.model
    system_prompt = Config.system_prompt
    temperature = Config.temperature
    num_ctx = Config.num_ctx
    supported_extensions = Config().supported_extensions
    description_suffix = Config.description_suffix
    description_prefix = Config.description_prefix
    markdown_format = Config.markdown_format

    # Load from YAML if exists
    if config_path is None:
        config_path = Path("config/config.yaml")

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Load defaults from YAML
        defaults = data.get("defaults", {})
        temperature = defaults.get("temperature", temperature)
        model = defaults.get("model", model)
        num_ctx = defaults.get("num_ctx", num_ctx)
        supported_extensions = data.get("supported_extensions", supported_extensions)

        # Load prompt from preset if specified
        if preset_key:
            prompts_data = data.get("prompts", {})
            if preset_key in prompts_data:
                system_prompt = prompts_data[preset_key].get("prompt", system_prompt)
                markdown_format = prompts_data[preset_key].get("markdownFormat", False)
        else:
            # Fallback to old system_prompt format or first preset
            if "system_prompt" in data:
                system_prompt = data["system_prompt"]
            else:
                prompts_data = data.get("prompts", {})
                if prompts_data:
                    first_key = next(iter(prompts_data))
                    system_prompt = prompts_data[first_key].get("prompt", system_prompt)
                    markdown_format = prompts_data[first_key].get("markdownFormat", False)

    # Override with environment variables
    ollama_host = os.getenv("OLLAMA_HOST", ollama_host)
    model = os.getenv("OLLAMA_MODEL", model)

    # Override with CLI arguments if provided
    if suffix is not None:
        description_suffix = suffix
    if prefix is not None:
        description_prefix = prefix

    return Config(
        ollama_host=ollama_host,
        model=model,
        system_prompt=system_prompt,
        temperature=temperature,
        num_ctx=num_ctx,
        supported_extensions=supported_extensions,
        description_suffix=description_suffix,
        description_prefix=description_prefix,
        markdown_format=markdown_format,
    )
