"""Processor for handling images in a folder."""

import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable

from .config import Config
from .ollama_client import describe_image as ollama_describe_image
from .openrouter_client import describe_image as openrouter_describe_image

logger = logging.getLogger(__name__)


def natural_sort_key(path: Path) -> list:
    """Generate a sort key for natural sorting.

    Splits the filename into text and number parts so that
    numbers are sorted numerically (1, 2, 10) instead of
    alphabetically (1, 10, 2).

    Args:
        path: Path to extract sort key from.

    Returns:
        List of strings and integers for sorting.
    """
    parts = re.split(r'(\d+)', path.stem)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def find_images(folder: Path, extensions: list[str]) -> list[Path]:
    """Find all images in a folder.

    Args:
        folder: Folder to scan.
        extensions: List of supported extensions.

    Returns:
        List of paths to found images, sorted in natural order.
    """
    images = set()
    for ext in extensions:
        images.update(folder.glob(f"*{ext}"))
        images.update(folder.glob(f"*{ext.upper()}"))
    return sorted(images, key=natural_sort_key)


def process_images(
    folder: Path,
    config: Config,
    overwrite: bool = False,
    verbose: bool = False,
    on_progress: Callable[[int, int, Path, str], None] | None = None,
) -> tuple[int, int]:
    """Process all images in a folder.

    Args:
        folder: Folder containing images.
        config: Application configuration.
        overwrite: If True, overwrite existing .txt files.
        verbose: If True, display detailed information.
        on_progress: Optional callback called after each image.
            Args: (current_index, total, image_path, description)

    Returns:
        Tuple (number of images processed, number of images skipped).
    """
    logger.info(f"Scanning folder: {folder}")
    images = find_images(folder, config.supported_extensions)
    processed = 0
    skipped = 0

    total = len(images)
    logger.info(f"Found {total} image(s) to process")
    if verbose:
        print(f"Found {total} image(s) to process.")

    batch_start = time.time()
    for i, image_path in enumerate(images, 1):
        txt_path = image_path.with_suffix(".txt")

        if txt_path.exists() and not overwrite:
            logger.debug(f"[{i}/{total}] Skipping (txt exists): {image_path.name}")
            if verbose:
                print(f"[{i}/{total}] Skipped (already exists): {image_path.name}")
            skipped += 1
            continue

        logger.info(f"[{i}/{total}] Starting processing: {image_path.name}")
        print(f"[{i}/{total}] Processing: {image_path.name}...")
        image_start = time.time()

        try:
            if config.provider == "openrouter":
                description = openrouter_describe_image(
                    image_path=image_path,
                    model=config.model,
                    system_prompt=config.system_prompt,
                    api_key=config.openrouter_api_key,
                    temperature=config.temperature,
                )
            else:
                description = ollama_describe_image(
                    image_path=image_path,
                    model=config.model,
                    system_prompt=config.system_prompt,
                    temperature=config.temperature,
                    num_ctx=config.num_ctx,
                    ollama_host=config.ollama_host,
                )

            image_time = time.time() - image_start
            logger.info(f"[{i}/{total}] Completed in {image_time:.2f}s: {image_path.name}")

            # Apply prefix and suffix with proper spacing
            if config.markdown_format:
                if config.description_prefix:
                    description = "# " + config.description_prefix + "\n" + description
                if config.description_suffix:
                    description = description + "\n\n# " + config.description_suffix
            else:
                if config.description_prefix:
                    description = config.description_prefix + " " + description
                if config.description_suffix:
                    description = description + " " + config.description_suffix

            txt_path.write_text(description, encoding="utf-8")
            logger.debug(f"Saved description to: {txt_path.name}")
            processed += 1

            if verbose:
                print(f"  -> Saved: {txt_path.name}")

            # Call progress callback if provided
            if on_progress:
                on_progress(i, total, image_path, description)

        except Exception as e:
            image_time = time.time() - image_start
            logger.error(f"[{i}/{total}] Error after {image_time:.2f}s on {image_path.name}: {e}")
            print(f"  Error: {e}")
            skipped += 1
            if on_progress:
                on_progress(i, total, image_path, f"Error: {e}")

    batch_time = time.time() - batch_start
    logger.info(f"Batch complete: {processed} processed, {skipped} skipped in {batch_time:.2f}s")
    return processed, skipped


def process_images_generator(
    folder: Path,
    config: Config,
    overwrite: bool = False,
    stop_event: threading.Event | None = None,
):
    """Process images as a generator for web interface.

    Yields progress updates after each image.

    Args:
        folder: Folder containing images.
        config: Application configuration.
        overwrite: If True, overwrite existing .txt files.
        stop_event: Optional threading event to signal stop request.

    Yields:
        Tuple (current_index, total, image_path, description, is_error)
    """
    images = find_images(folder, config.supported_extensions)
    total = len(images)

    for i, image_path in enumerate(images, 1):
        # Check for stop request before processing each image
        if stop_event and stop_event.is_set():
            return

        txt_path = image_path.with_suffix(".txt")

        if txt_path.exists() and not overwrite:
            yield (i, total, image_path, "Skipped (file exists)", True)
            continue

        try:
            if config.provider == "openrouter":
                description = openrouter_describe_image(
                    image_path=image_path,
                    model=config.model,
                    system_prompt=config.system_prompt,
                    api_key=config.openrouter_api_key,
                    temperature=config.temperature,
                )
            else:
                description = ollama_describe_image(
                    image_path=image_path,
                    model=config.model,
                    system_prompt=config.system_prompt,
                    temperature=config.temperature,
                    num_ctx=config.num_ctx,
                    ollama_host=config.ollama_host,
                )

            # Check again after API call (in case stop was requested during processing)
            if stop_event and stop_event.is_set():
                return

            # Apply prefix and suffix with proper spacing
            if config.markdown_format:
                if config.description_prefix:
                    description = "# " + config.description_prefix + "\n" + description
                if config.description_suffix:
                    description = description + "\n\n# " + config.description_suffix
            else:
                if config.description_prefix:
                    description = config.description_prefix + " " + description
                if config.description_suffix:
                    description = description + " " + config.description_suffix

            txt_path.write_text(description, encoding="utf-8")
            yield (i, total, image_path, description, False)

        except Exception as e:
            yield (i, total, image_path, f"Error: {e}", True)
