import logging
import numbers
import os
import platform
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from shuku.logging_setup import DEFAULT_LOG_LEVEL_NAME, LOG_LEVELS
from shuku.utils import (
    PROGRAM_NAME,
    REPOSITORY,
    exit_if_file_missing,
    prompt_user_choice,
)

AUDIO_CODEC_CHOICES = ["libmp3lame", "aac", "libopus", "flac", "pcm_s16le", "copy"]
AUDIO_CODEC_ALIASES = {
    "mp3": "libmp3lame",
    "wav": "pcm_s16le",
    "opus": "libopus",
    "ogg": "libopus",
}
CODEC_MAX_QUALITY = {"libmp3lame": 9, "aac": 10}
DEFAULT_MAX_QUALITY = 10
DEFAULT_AUDIO_QUALITY = "48k"
FILE_EXISTS_OPTIONS = ["ask", "overwrite", "rename", "skip"]

CONFIG_FILENAME = f"{PROGRAM_NAME}.toml"
DEFAULT_CONFIG_HEADER = (
    f"# {PROGRAM_NAME} ~ configuration file\n"
    f"# {REPOSITORY}\n"
    "\n"
    "# This file uses TOML format: https://toml.io/\n"
    "# Lines starting with '#' are comments and are ignored.\n"
    "# When adding keys, pay attention to which TOML section it belongs to.\n"
    "# A TOML section starts with a header like [condensed_audio] and ends at the next section/end of file.\n\n\n"
)


class ConfigValidationError(Exception):
    pass


@dataclass
class ConfigItem:
    description: str
    default_value: Any
    example_value: Optional[Any] = None
    choices: Optional[list[Any]] = None
    validators: list[Callable] = field(default_factory=list)
    aliases: dict[str, Any] = field(default_factory=dict)


CONFIG_OPTIONS = {
    # Top-level settings.
    "loglevel": ConfigItem(
        description="Logging level. Only messages of the selected level or higher will be displayed.",
        default_value=DEFAULT_LOG_LEVEL_NAME,
        choices=list(LOG_LEVELS.keys()),
    ),
    "clean_output_filename": ConfigItem(
        description="Whether to clean output filenames by removing release tags, quality indicators, etc. If 'false', the original filename is used.",
        default_value=True,
        validators=[lambda x: isinstance(x, bool)],
    ),
    "output_directory": ConfigItem(
        description="Directory to save output files. Defaults to the same directory as the input file.",
        default_value=None,
        example_value="~/Desktop/condensed",
        validators=[lambda x: isinstance(x, str) if x else True],
    ),
    "output_suffix": ConfigItem(
        description="Suffix to add to output filenames.",
        default_value=" (condensed)",
    ),
    "if_file_exists": ConfigItem(
        description=f"What to do when output file exists.",
        default_value="ask",
        choices=FILE_EXISTS_OPTIONS,
    ),
    "padding": ConfigItem(
        description="Padding in seconds to add before and after each subtitle.",
        default_value=0.5,
        validators=[lambda x: isinstance(x, numbers.Number)],
    ),
    "subtitle_directory": ConfigItem(
        description="Directory to search for external subtitle files. Overridden by the --subtitles argument.",
        default_value=None,
        example_value="~/Videos/Subtitles",
        validators=[lambda x: isinstance(x, str) if x else True],
    ),
    "audio_languages": ConfigItem(
        description="Automatically select audio tracks with these languages (in order of preference).",
        default_value=None,
        example_value=["jpn", "jp", "ja", "eng"],
        validators=[lambda x: all(isinstance(lang, str) for lang in x) if x else True],
    ),
    "subtitle_languages": ConfigItem(
        description="Automatically select subtitle tracks with these languages (in order of preference).",
        default_value=None,
        example_value=["jpn", "jp", "ja", "eng"],
        validators=[lambda x: all(isinstance(lang, str) for lang in x) if x else True],
    ),
    "external_subtitle_search": ConfigItem(
        description="Method for finding external subtitles. 'disabled' turns off external subtitle search. 'exact' requires a perfect match, while 'fuzzy' allows for inexact matches.",
        default_value="fuzzy",
        choices=["disabled", "exact", "fuzzy"],
    ),
    "subtitle_match_threshold": ConfigItem(
        description="Minimum similarity score (0 to 1) for matching subtitles. Lower values allow for more lenient matching, but risk false positives.",
        default_value=0.65,
        validators=[lambda x: isinstance(x, float) and 0 <= x <= 1],
    ),
    "skip_chapters": ConfigItem(
        description="List of chapter titles to skip (case-insensitive).",
        default_value=[
            "avant",
            "avante",
            "closing credits",
            "credits",
            "ed",
            "end credit",
            "end credits",
            "ending",
            "logos/opening credits",
            "next episode",
            "op",
            "1. opening credits",
            "opening titles",
            "opening",
            "preview",
            "start credit",
            "trailer",
        ],
        validators=[lambda x: all(isinstance(title, str) for title in x)],
    ),
    "line_skip_patterns": ConfigItem(
        description="Regex patterns for lines to skip in subtitles. Use single-quoted strings.",
        default_value=[
            # Skip music.
            "^(～|〜)?♪.*",
            "^♬(～|〜)$",
            "^♪?(～|〜)♪?$",
            # Skip lines containing only "・～"
            "^・(～|〜)$",
            # Skip lines entirely enclosed in various types of brackets.
            "^\\([^)]*\\)$",  # Parentheses ()
            "^（[^）]*）$",  # Full-width parentheses （）
            "^\\[.*\\]$",  # Square brackets []
            "^\\{[^\\}]*\\}$",  # Curly braces {}
            "^<[^>]*>$",  # Angle brackets <>
        ],
        validators=[lambda x: all(isinstance(pattern, str) for pattern in x)],
    ),
    # Condensed audio settings.
    "condensed_audio.enabled": ConfigItem(
        description="Create condensed audio.",
        default_value=True,
        validators=[lambda x: isinstance(x, bool)],
    ),
    "condensed_audio.audio_codec": ConfigItem(
        description="Condensed audio codec.",
        default_value="libopus",
        choices=AUDIO_CODEC_CHOICES,
        aliases=AUDIO_CODEC_ALIASES,
    ),
    "condensed_audio.audio_quality": ConfigItem(
        description=f"Audio quality for condensed audio. See {REPOSITORY}?tab=readme-ov-file#audio-quality-settings",
        default_value=DEFAULT_AUDIO_QUALITY,
    ),
    "condensed_audio.custom_ffmpeg_args": ConfigItem(
        description="Custom FFmpeg arguments for condensed audio.",
        default_value=None,
        example_value={
            # Normalisation values based on https://podcasters.apple.com/support/893-audio-requirements
            "af": "loudnorm=I=-16:TP=-1:LRA=13,acompressor=threshold=-14dB:ratio=1.8:attack=30:release=300"
        },
        validators=[lambda x: isinstance(x, dict) if x else True],
    ),
    # Condensed video settings.
    "condensed_video.enabled": ConfigItem(
        description="Create condensed video.",
        default_value=False,
        validators=[lambda x: isinstance(x, bool)],
    ),
    "condensed_video.audio_codec": ConfigItem(
        description="Audio codec for condensed video.",
        default_value="copy",
        choices=AUDIO_CODEC_CHOICES,
        aliases=AUDIO_CODEC_ALIASES,
    ),
    "condensed_video.audio_quality": ConfigItem(
        description=f"Audio quality for condensed video. See {REPOSITORY}?tab=readme-ov-file#audio-quality-settings",
        default_value=None,
        example_value=DEFAULT_AUDIO_QUALITY,
    ),
    "condensed_video.video_codec": ConfigItem(
        description="Video codec for condensed video.",
        default_value="copy",
    ),
    "condensed_video.video_quality": ConfigItem(
        description="Video quality for condensed video (for x264, lower is better quality; 'copy' ignores this).",
        default_value=None,
        example_value="23",
    ),
    "condensed_video.custom_ffmpeg_args": ConfigItem(
        description="Custom FFmpeg arguments for condensed video.",
        default_value=None,
        example_value={"preset": "faster", "crf": "23", "threads": "0", "tune": "film"},
        validators=[lambda x: isinstance(x, dict) if x else True],
    ),
    # Condensed subtitles settings.
    "condensed_subtitles.enabled": ConfigItem(
        description="Create condensed subtitles.",
        default_value=False,
        validators=[lambda x: isinstance(x, bool)],
    ),
    "condensed_subtitles.format": ConfigItem(
        description="Output format for subtitles. 'auto' matches the input format.",
        default_value="auto",
        choices=["auto", "srt", "ass", "lrc"],
    ),
}

DEFAULT_CONFIG = {key: item.default_value for key, item in CONFIG_OPTIONS.items()}


def load_config(config_path: Optional[str] = None) -> dict:
    if config_path:
        if config_path.lower() == "none":
            logging.info("Config path set to 'none'. Using default configuration.")
            return DEFAULT_CONFIG.copy()
        else:
            exit_if_file_missing(config_path)
            return load_specific_config(config_path)
    default_path = get_default_config_path()
    if default_path.exists():
        config_path = str(default_path)
        logging.debug(f"Using config file: {config_path}")
        return load_specific_config(config_path)
    else:
        logging.warning("No config file found. Using default configuration.")
        return DEFAULT_CONFIG.copy()


def load_specific_config(config_path: str) -> dict:
    with open(config_path, "rb") as config_file:
        user_config = tomllib.load(config_file)
    flattened_user_config = flatten_dict(user_config)
    config = DEFAULT_CONFIG.copy()
    config.update(flattened_user_config)
    resolved_config = resolve_aliases(config)
    validate_config(resolved_config)
    return resolved_config


def get_default_config_path() -> Path:
    if platform.system() == "Windows":
        config_base = os.environ.get("APPDATA")
        if not config_base:
            raise EnvironmentError("APPDATA environment variable is not set")
    else:
        # Unix-like systems (GNU+Linux, macOS).
        config_base = os.environ.get("XDG_CONFIG_HOME")
        if not config_base:
            config_base = os.path.expanduser("~/.config")
    return Path(config_base) / PROGRAM_NAME / CONFIG_FILENAME


def flatten_dict(
    d: dict[str, Any], parent_key: str = "", sep: str = "."
) -> dict[str, Any]:
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict) and "custom_ffmpeg_args" not in new_key:
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def resolve_aliases(config: dict[str, Any]) -> dict[str, Any]:
    resolved_config = {}
    for key, value in config.items():
        if key in CONFIG_OPTIONS:
            item = CONFIG_OPTIONS[key]
            if isinstance(value, str) and value in item.aliases:
                resolved_config[key] = item.aliases[value]
            else:
                resolved_config[key] = value
        else:
            resolved_config[key] = value
    return resolved_config


def validate_config(config: dict[str, Any]) -> None:
    if not any(
        config.get(option)
        for option in [
            "condensed_audio.enabled",
            "condensed_subtitles.enabled",
            "condensed_video.enabled",
        ]
    ):
        logging.error("All condensing options are disabled. Nothing to do.")
        sys.exit(1)
    valid_keys = set(CONFIG_OPTIONS.keys())
    unknown_keys = set(config.keys()) - valid_keys
    if unknown_keys:
        logging.error(f"Unknown configuration keys: {', '.join(unknown_keys)}")
        logging.error(f"Expected one of: {', '.join(valid_keys)}")
        sys.exit(1)
    for key, value in config.items():
        schema_item = CONFIG_OPTIONS[key]
        if schema_item.choices:
            valid_values = set(schema_item.choices) | set(schema_item.aliases.keys())
            if value not in valid_values:
                logging.error(
                    f"Invalid value for {key}: '{value}'. Must be one of: {', '.join(map(str, valid_values))}"
                )
                sys.exit(1)
        for validator in schema_item.validators:
            if not validator(value):
                logging.error(f"Validation failed for {key} with value '{value}'")
                sys.exit(1)
        if key.endswith(".audio_codec"):
            validate_audio_quality(value, config.get(f"{key[:-12]}.audio_quality"))


def validate_audio_quality(codec: str, quality: Optional[Any]) -> None:
    if codec in ["pcm_s16le", "copy"]:
        return
    if quality is None:
        logging.info(f"No quality specified for codec '{codec}'.")
        return
    if codec in ["libmp3lame", "aac", "libopus"]:
        validate_bitrate_or_scale(codec, quality)
    elif codec == "flac":
        validate_flac_compression(quality)


def validate_bitrate_or_scale(codec: str, quality: Any) -> None:
    def error(msg: str) -> None:
        raise ConfigValidationError(f"{msg} for codec '{codec}'.")

    def warn(msg: str) -> None:
        logging.warning(f"{msg} for codec '{codec}'.")

    try:
        if isinstance(quality, str):
            quality = quality.lower()
            if quality.endswith("k"):
                value = float(quality[:-1])
                if codec == "libopus" and not 6 <= value <= 510:
                    warn(f"Unusual bitrate '{quality}'")
                elif not 8 <= value <= 1000:
                    warn(f"Unusual bitrate '{quality}'")
                return
            elif quality.startswith("v"):
                value = int(quality[1:])
                if value < 0:
                    error(f"Negative VBR quality '{quality}' not allowed")
                if codec in ["aac", "libopus"]:
                    error(f"VBR quality '{quality}' not supported")
                if codec == "libmp3lame" and value > 9:
                    warn(f"VBR quality '{quality}' outside V0-V9 range")
            else:
                value = float(quality)
        else:
            value = float(quality)
        if value < 0:
            error(f"Negative quality value '{quality}' not allowed")
        if codec == "libopus":
            if not 6000 <= value <= 510000:
                warn(f"Unusual bitrate '{value}'")
        if value > CODEC_MAX_QUALITY.get(codec, DEFAULT_MAX_QUALITY):
            warn(f"Quality value '{quality}' unusually high")
    except ValueError:
        error(f"Invalid quality format '{quality}'")


def validate_flac_compression(quality: Any) -> None:
    try:
        quality = int(quality)
        if 0 <= quality <= 12:
            return
    except (ValueError, TypeError):
        pass
    raise ConfigValidationError(
        f"Invalid flac compression level '{quality}'. Must be an integer between 0 and 12."
    )


def dump_default_config() -> None:
    try:
        file_path = get_default_config_path()
        content = generate_config_content()
        if file_path.exists():
            choice = prompt_user_choice(
                f"{file_path} already exists.",
                ["overwrite", "cancel"],
                default="Cancel",
            )
            if choice == "cancel":
                logging.warning("Configuration creation cancelled.")
                sys.exit(0)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logging.success(f"Configuration file created: {file_path}")  # type: ignore
    except OSError as e:
        logging.error(f"Error creating configuration file: {e}")
        sys.exit(1)


def generate_config_content() -> str:
    config_content = DEFAULT_CONFIG_HEADER
    sections: dict[str, dict[str, ConfigItem]] = {}
    for key, item in CONFIG_OPTIONS.items():
        parts = key.split(".")
        if len(parts) == 1:
            config_content += generate_item_content(key, item)
        else:
            section, subkey = parts[0], ".".join(parts[1:])
            sections.setdefault(section, {})[subkey] = item
    for section, items in sections.items():
        config_content += f"\n[{section}]\n"
        for subkey, item in items.items():
            config_content += generate_item_content(subkey, item)
    return config_content.rstrip() + "\n"


def generate_item_content(key: str, item: ConfigItem) -> str:
    choices = list(map(str, item.choices or []))
    aliases = [
        f"{alias} (alias for {value})" for alias, value in (item.aliases or {}).items()
    ]
    choice_str = (
        f"# Choices: {', '.join(choices + aliases)}\n" if choices or aliases else ""
    )

    def format_dict_with_equals(d: dict) -> str:
        return "{ " + ", ".join(f'"{k}" = {repr(v)}' for k, v in d.items()) + " }"

    example_value = (
        (
            format_dict_with_equals(item.example_value)
            if isinstance(item.example_value, dict)
            else repr(item.example_value)
        )
        if getattr(item, "example_value", None)
        else "null"
    )
    if key == "line_skip_patterns":
        default_value_str = f"{key} = [\n"
        default_value_str += "".join(
            f"    {repr(pattern)},\n" for pattern in item.default_value
        )
        default_value_str += "]\n"
    elif item.default_value is None:
        default_value_str = f"# {key} = {example_value}\n"
    elif isinstance(item.default_value, bool):
        default_value_str = f"{key} = {str(item.default_value).lower()}\n"
    elif isinstance(item.default_value, dict):
        default_value_str = f"{key} = {format_dict_with_equals(item.default_value)}\n"
    else:
        default_value_str = f"{key} = {repr(item.default_value)}\n"
    return f"# {item.description}\n{choice_str}{default_value_str}\n"
