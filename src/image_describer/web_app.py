"""Web interface using Gradio."""

import base64
import os
import threading
import time
from collections import deque
from pathlib import Path

import gradio as gr

from .config import (
    Config,
    UserPreferences,
    get_openrouter_api_key,
    list_ollama_models,
    load_presets,
    load_user_preferences,
    save_user_preferences,
)
from .openrouter_client import OPENROUTER_VISION_MODELS
from .processor import find_images, process_images_generator


# Global stop event for cancellation
_stop_event = threading.Event()


def get_ollama_host() -> str:
    """Get the Ollama API host from environment or default."""
    host = os.getenv("OLLAMA_HOST", "")
    if not host:
        return "http://localhost:11434"
    # Replace 0.0.0.0 with localhost for better compatibility
    host = host.replace("0.0.0.0", "localhost")
    # Add http:// if missing
    if not host.startswith("http"):
        host = f"http://{host}"
    # Add default port if missing
    if host.count(":") == 1:  # Only has http:// but no port
        host = f"{host}:11434"
    return host


def create_app() -> gr.Blocks:
    """Create the Gradio web application."""

    presets = load_presets()
    preset_choices = [(p.name, p.key) for p in presets]
    preset_prompts = {p.key: p.prompt for p in presets}
    preset_markdown_format = {p.key: p.markdown_format for p in presets}

    # Load saved user preferences
    user_prefs = load_user_preferences()

    # Determine default preset
    default_preset = user_prefs.preset_key if user_prefs.preset_key else (preset_choices[0][1] if preset_choices else None)

    # Get logo as base64
    logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
    with open(logo_path, "rb") as f:
        logo_base64 = base64.b64encode(f.read()).decode("utf-8")

    with gr.Blocks(title="AutoDescribe Images") as app:
        gr.HTML(
            f'<div style="display: flex; justify-content: center;"><img src="data:image/png;base64,{logo_base64}"></div>'
        )
        gr.Markdown("Generate image descriptions using Ollama Vision models or OpenRouter API.")

        # Provider Selection
        provider_radio = gr.Radio(
            choices=[("Ollama (Local)", "ollama"), ("OpenRouter (Cloud)", "openrouter")],
            value=user_prefs.provider,
            label="Provider",
            info="Choose between local Ollama or cloud-based OpenRouter",
        )

        # Ollama Settings Group
        with gr.Group(visible=(user_prefs.provider == "ollama")) as ollama_group:
            connection_status = gr.HTML(
                value="<span style='color: gray;'>[Disconnected]</span>",
            )
            ollama_host_input = gr.Textbox(
                label="Ollama API",
                value=get_ollama_host(),
                placeholder="http://localhost:11434",
                info="Ollama server URL",
            )
            connect_btn = gr.Button("🔄 Test Connection", size="sm")

            model_dropdown = gr.Dropdown(
                label="Ollama Model",
                choices=[],
                value=None,
                allow_custom_value=True,
            )
            refresh_models_btn = gr.Button("🔄 Refresh Models", size="sm")
            gr.HTML(
                '<p style="font-size: 0.85em; color: #888; margin: 4px 0 8px 0; text-align: center;">'
                'Requires a vision model (llava, qwen3-vl, etc.) – '
                '<a href="https://ollama.com/search?c=vision" target="_blank" '
                'style="color: #58a6ff; text-decoration: none;">Browse vision models ↗</a>'
                '</p>'
            )

        # OpenRouter Settings Group
        with gr.Group(visible=(user_prefs.provider == "openrouter")) as openrouter_group:
            openrouter_api_key = gr.Textbox(
                label="OpenRouter API Key",
                value=get_openrouter_api_key(),
                placeholder="sk-or-v1-...",
                info="Set OPENROUTER_API_KEY in .env or enter here for this session",
                type="password",
            )
            openrouter_model = gr.Dropdown(
                label="OpenRouter Model",
                choices=OPENROUTER_VISION_MODELS,
                value=user_prefs.openrouter_model if user_prefs.openrouter_model else "openai/gpt-4o-mini",
                allow_custom_value=True,
                info="Select a vision-capable model",
            )
            gr.HTML(
                '<p style="font-size: 0.85em; color: #888; margin: 4px 0 8px 0; text-align: center;">'
                '<a href="https://openrouter.ai/models?supported_parameters=vision" target="_blank" '
                'style="color: #58a6ff; text-decoration: none;">Browse all vision models on OpenRouter ↗</a>'
                '</p>'
            )

        folder_input = gr.Textbox(
            label="Image Folder",
            value=user_prefs.image_folder,
            placeholder="Enter path to folder containing images...",
            info="Path to the folder with images to process",
            lines=2,
        )

        preset_dropdown = gr.Dropdown(
            label="Prompt Preset",
            choices=preset_choices,
            value=default_preset,
            info="Select a prompt preset for your use case. You can add or edit presets in config.yaml",
        )

        custom_prompt_input = gr.Textbox(
            label="Custom Prompt (Appended)",
            value=user_prefs.custom_prompt if hasattr(user_prefs, 'custom_prompt') else "",
            placeholder="Add custom instructions here... These will be appended to the preset prompt.",
            info="Additional instructions appended to the selected preset prompt",
            lines=4,
        )

        temperature_slider = gr.Slider(
            label="Temperature",
            minimum=0.0,
            maximum=1.0,
            value=user_prefs.temperature,
            step=0.1,
            info="Higher = more creative, Lower = more deterministic",
        )

        with gr.Row():
            prefix_input = gr.Textbox(
                label="Prefix",
                value=user_prefs.prefix,
                placeholder="Text added before description...",
                info="Added at the start of each description",
                lines=2,
            )
            suffix_input = gr.Textbox(
                label="Suffix",
                value=user_prefs.suffix,
                placeholder="Text added after description...",
                info="Added at the end of each description",
                lines=2,
            )

        overwrite_checkbox = gr.Checkbox(
            label="Overwrite existing files",
            value=user_prefs.overwrite,
            info="If unchecked, skip images that already have .txt files",
        )

        # State to track if processing is running
        is_processing = gr.State(False)

        with gr.Row():
            process_btn = gr.Button("Start Processing", variant="primary", size="lg", scale=3)
            stop_btn = gr.Button("Stop", variant="stop", size="lg", scale=1, interactive=False)

        status_text = gr.Textbox(
            label="Processing Status",
            value="Ready",
            interactive=False,
        )

        # Provider toggle handler
        def on_provider_change(provider):
            return (
                gr.update(visible=(provider == "ollama")),
                gr.update(visible=(provider == "openrouter")),
            )

        provider_radio.change(
            fn=on_provider_change,
            inputs=[provider_radio],
            outputs=[ollama_group, openrouter_group],
        )

        def check_connection(host: str):
            """Check connection to Ollama and refresh models list."""
            if not host:
                return "<span style='color: red;'>[Disconnected]</span>", gr.update(choices=[], value=None)
            try:
                models = list_ollama_models(host)
                if models and models != ["qwen3-vl:4b", "llava", "llama3.2-vision"]:
                    # Use saved model if available and valid
                    saved_model = user_prefs.ollama_model
                    default_model = saved_model if saved_model in models else (models[0] if models else None)
                    return f"<span style='color: #00ff00;'>[Connected]</span> ({len(models)} models)", gr.update(choices=models, value=default_model)
                else:
                    return "<span style='color: red;'>[Disconnected]</span>", gr.update(choices=models, value=models[0] if models else None)
            except Exception as e:
                return f"<span style='color: red;'>[Error]</span> {str(e)[:20]}", gr.update(choices=[], value=None)

        def refresh_models(host: str):
            """Refresh models list from current host."""
            models = list_ollama_models(host)
            return gr.update(choices=models, value=models[0] if models else None)

        def format_time(seconds: float) -> str:
            """Format seconds into human readable time."""
            if seconds < 60:
                return f"{seconds:.0f}s"
            elif seconds < 3600:
                minutes = int(seconds // 60)
                secs = int(seconds % 60)
                return f"{minutes}m {secs}s"
            else:
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                return f"{hours}h {minutes}m"

        def stop_processing():
            """Stop the current processing immediately."""
            _stop_event.set()
            return (
                "Stopping... (will stop after current image)",
                gr.update(interactive=True),  # Re-enable start button
                gr.update(interactive=False, value="Stopping..."),  # Disable stop button
                False,
            )

        def process_folder(
            provider: str,
            folder_path: str,
            ollama_host: str,
            ollama_model: str,
            or_api_key: str,
            or_model: str,
            preset_key: str,
            custom_prompt: str,
            temperature: float,
            prefix: str,
            suffix: str,
            overwrite: bool,
            processing: bool,
            progress=gr.Progress(),
        ):
            # Clear any previous stop signal
            _stop_event.clear()

            if not folder_path:
                yield (
                    "Error: Please enter a folder path",
                    gr.update(interactive=True),  # process_btn
                    gr.update(interactive=False, value="Stop"),  # stop_btn
                    False,
                )
                return

            folder = Path(folder_path)
            if not folder.exists():
                yield (
                    f"Error: Folder not found: {folder_path}",
                    gr.update(interactive=True),
                    gr.update(interactive=False, value="Stop"),
                    False,
                )
                return

            if not folder.is_dir():
                yield (
                    f"Error: Path is not a folder: {folder_path}",
                    gr.update(interactive=True),
                    gr.update(interactive=False, value="Stop"),
                    False,
                )
                return

            # Validate OpenRouter settings
            if provider == "openrouter" and not or_api_key:
                yield (
                    "Error: OpenRouter API key is required",
                    gr.update(interactive=True),
                    gr.update(interactive=False, value="Stop"),
                    False,
                )
                return

            system_prompt = preset_prompts.get(preset_key, "Describe this image.")
            markdown_format = preset_markdown_format.get(preset_key, False)
            
            # Append custom prompt if provided
            if custom_prompt and custom_prompt.strip():
                system_prompt = system_prompt + "\n\n" + custom_prompt.strip()

            # Determine which model to use based on provider
            model = or_model if provider == "openrouter" else ollama_model

            # Save user preferences for next session (API key not saved for security)
            save_user_preferences(UserPreferences(
                image_folder=folder_path,
                ollama_model=ollama_model or "",
                preset_key=preset_key or "",
                prefix=prefix or "",
                suffix=suffix or "",
                temperature=temperature,
                overwrite=overwrite,
                provider=provider,
                openrouter_model=or_model or "",
                custom_prompt=custom_prompt or "",
            ))

            config = Config(
                ollama_host=ollama_host or get_ollama_host(),
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                description_prefix=prefix,
                description_suffix=suffix,
                markdown_format=markdown_format,
                provider=provider,
                openrouter_api_key=or_api_key or "",
            )

            images = find_images(folder, config.supported_extensions)
            if not images:
                yield (
                    "No images found in folder",
                    gr.update(interactive=True),
                    gr.update(interactive=False, value="Stop"),
                    False,
                )
                return

            provider_name = "OpenRouter" if provider == "openrouter" else "Ollama"
            # Yield initial state: disable start, enable stop
            yield (
                f"Starting with {provider_name}... Found {len(images)} images",
                gr.update(interactive=False),  # Disable start button
                gr.update(interactive=True, value="Stop"),  # Enable stop button
                True,
            )

            processed_count = 0
            skipped_count = 0

            # Sliding window for time estimation (last 5 images)
            time_window: deque[float] = deque(maxlen=5)
            last_time = time.time()

            # Use tqdm-style progress bar
            generator = process_images_generator(folder, config, overwrite, _stop_event)

            for current, total, image_path, description, is_error in progress.tqdm(
                generator, total=len(images), desc="Processing"
            ):
                # Check if stop was requested
                if _stop_event.is_set():
                    yield (
                        f"Stopped! {processed_count} processed, {skipped_count} skipped",
                        gr.update(interactive=True),  # Re-enable start
                        gr.update(interactive=False, value="Stop"),  # Disable stop
                        False,
                    )
                    return

                # Calculate time for this image
                current_time = time.time()
                elapsed = current_time - last_time
                last_time = current_time

                if not is_error:
                    time_window.append(elapsed)
                    processed_count += 1
                else:
                    skipped_count += 1

                # Calculate ETA
                remaining = total - current
                if time_window and remaining > 0:
                    avg_time = sum(time_window) / len(time_window)
                    eta = avg_time * remaining
                    eta_str = f" - ETA: {format_time(eta)}"
                else:
                    eta_str = ""

                status = f"Processing: {current}/{total} ({image_path.name}){eta_str}"
                yield (
                    status,
                    gr.update(interactive=False),  # Keep start disabled
                    gr.update(interactive=True, value="Stop"),  # Keep stop enabled
                    True,
                )

            yield (
                f"Done! {processed_count} processed, {skipped_count} skipped",
                gr.update(interactive=True),  # Re-enable start
                gr.update(interactive=False, value="Stop"),  # Disable stop
                False,
            )

        connect_btn.click(
            fn=check_connection,
            inputs=[ollama_host_input],
            outputs=[connection_status, model_dropdown],
        )

        refresh_models_btn.click(
            fn=refresh_models,
            inputs=[ollama_host_input],
            outputs=[model_dropdown],
        )

        # Auto-connect on load
        app.load(
            fn=check_connection,
            inputs=[ollama_host_input],
            outputs=[connection_status, model_dropdown],
        )

        process_btn.click(
            fn=process_folder,
            inputs=[
                provider_radio,
                folder_input,
                ollama_host_input,
                model_dropdown,
                openrouter_api_key,
                openrouter_model,
                preset_dropdown,
                custom_prompt_input,
                temperature_slider,
                prefix_input,
                suffix_input,
                overwrite_checkbox,
                is_processing,
            ],
            outputs=[status_text, process_btn, stop_btn, is_processing],
        )

        stop_btn.click(
            fn=stop_processing,
            inputs=[],
            outputs=[status_text, process_btn, stop_btn, is_processing],
        )

        gr.HTML(
            """
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #444; text-align: center; color: #888; font-size: 0.9em;">
                <p>
                    <a href="https://github.com/hydropix/ollama-image-describer" target="_blank" style="color: #58a6ff; text-decoration: none;">
                        GitHub Project
                    </a>
                </p>
                <p style="margin-top: 8px;">
                    Found a bug? Have a suggestion?
                    <a href="https://github.com/hydropix/ollama-image-describer/issues" target="_blank" style="color: #58a6ff; text-decoration: none;">
                        Open an issue
                    </a>
                    or give a star to support the project!
                </p>
            </div>
            """
        )

    return app


def launch_web_app():
    """Launch the Gradio web application."""
    app = create_app()
    port = int(os.getenv("GRADIO_SERVER_PORT", "7861"))
    app.launch(
        server_name="127.0.0.1",
        server_port=port,
        share=False,
        inbrowser=True,
        allowed_paths=["/", "C:\\", "D:\\", "E:\\", "Z:\\", "Q:\\"],
    )


if __name__ == "__main__":
    launch_web_app()
