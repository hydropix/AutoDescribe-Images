# ollama-image-describer

CLI tool to automatically generate text descriptions for images using Ollama vision models (LLaVA, Qwen3-VL, Llama Vision).

## Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** - Python package manager
- **[Ollama](https://ollama.com/)** - Must be installed separately and running

### Installing Ollama

Download and install Ollama from [ollama.com](https://ollama.com/), then pull a vision model:

```bash
ollama pull qwen3-vl:8b
```

## Installation

```bash
# Clone the repository
git clone https://github.com/hydropix/ollama-image-describer.git
cd ollama-image-describer

# Install Python dependencies with uv
uv sync
```

> **Note:** `uv sync` installs the Python dependencies (including the `ollama` Python client library). The Ollama server itself must be installed separately as described above.

## Configuration

### Environment Variables (.env)

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Configure your Ollama server:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3-vl:8b
```

### Prompt Configuration (config.yaml)

The `config.yaml` file contains:
- `system_prompt`: Instructions for the vision model
- `temperature`: Generation temperature (0.0-1.0)
- `supported_extensions`: List of image formats to process

## Usage

```bash
uv run python -m image_describer <image_folder> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Path to YAML config file |
| `--suffix` | `-s` | Text appended to each description (e.g., ", By Artist") |
| `--overwrite/--no-overwrite` | | Overwrite existing .txt files (default: overwrite) |
| `--verbose` | `-v` | Verbose mode |

### Examples

```bash
# Basic usage
uv run python -m image_describer ./my_images

# With custom suffix
uv run python -m image_describer ./my_images --suffix ", By Kristof"

# Verbose mode with custom config
uv run python -m image_describer ./my_images -v -c custom_config.yaml
```

## Supported Models

- **Qwen3-VL** (recommended): `qwen3-vl:8b`
- **LLaVA**: `llava`, `llava:13b`
- **Llama Vision**: `llama3.2-vision`

## License

MIT
