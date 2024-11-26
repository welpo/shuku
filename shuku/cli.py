import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from functools import wraps
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import pysubs2
from ffmpeg import FFmpeg, FFmpegError
from pysubs2.formats import (
    FILE_EXTENSION_TO_FORMAT_IDENTIFIER,
    FORMAT_IDENTIFIER_TO_FORMAT_CLASS,
)
from pysubs2.formats.substation import parse_tags

from shuku.config import (
    CONFIG_FILENAME,
    dump_default_config,
    load_config,
)
from shuku.logging_setup import setup_initial_logging, update_logging_level
from shuku.utils import (
    PROGRAM_NAME,
    PROGRAM_TAGLINE,
    REPOSITORY,
    exit_if_file_missing,
    prompt_user_choice,
)

SUBTITLE_EXTENSIONS = list(FILE_EXTENSION_TO_FORMAT_IDENTIFIER.keys())
YEAR_PATTERN = r"\b(189[6-9]|19\d{2}|20\d{2}|21\d{2})\b"

INCLUDE_DEMO_UTILS = False  # Set to True to load utils for the demo video.
if INCLUDE_DEMO_UTILS:
    try:  # pragma: no cover
        from shuku.demo_utils import save_segments_as_json
    except ImportError:  # pragma: no cover
        print("Demo utilities not available.")

DEFAULT_MP3_VBR_QUALITY = "6"
SUPPORTED_SUBTITLE_FORMATS = frozenset(sorted(FORMAT_IDENTIFIER_TO_FORMAT_CLASS.keys()))
PENALIZED_SUBTITLE_KEYWORDS = [
    "sign",
    "song",
    "comment",
    "description",
    "sdh",
    "cc",
    "forced",
]

CODEC_TO_FORMAT_IDENTIFIER = {
    "ass": "ass",
    "dvb_subtitle": "dvb",
    "dvb_teletext": "ttxt",
    "dvd_subtitle": "sub",
    "hdmv_pgs_subtitle": "sup",
    "mov_text": "txt",
    "ssa": "ssa",
    "subrip": "srt",
    "webvtt": "vtt",
}

# Temporary workaround as I can't get Nuitka to get along with Poetry.
# See https://github.com/Nuitka/Nuitka/issues/2965
try:
    from importlib.metadata import version

    VERSION = version(PROGRAM_NAME)
except ImportError:  # pragma: no cover
    VERSION = "0.0.3"  # Managed by 'release' script.


class FileProcessingError(Exception):
    def __init__(self, file_path: str, message: str):
        self.file_path = file_path
        self.message = message
        super().__init__(f"Error processing {file_path}: {message}")


@dataclass
class Context:
    file_path: str
    config: dict[str, Any]
    args: argparse.Namespace
    temp_dir: str
    metadata: dict[str, str]
    input_name: str
    basename: str
    clean_name: str
    stream_info: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"audio": [], "subtitle": []}
    )
    selected_audio_stream: Optional[str] = None
    original_subtitle_format: Optional[str] = None

    @classmethod
    def create(
        cls,
        file_path: str,
        config: dict[str, Any],
        args: argparse.Namespace,
        temp_dir: str,
    ) -> "Context":
        basename = os.path.basename(file_path)
        input_name = os.path.splitext(basename)[0]
        clean_name = prepare_filename_for_display(basename)
        return cls(
            file_path=file_path,
            config=config,
            args=args,
            temp_dir=temp_dir,
            metadata={},
            input_name=input_name,
            basename=basename,
            clean_name=clean_name,
        )


def log_execution_time(
    log_level: str = "debug", message_template: Optional[str] = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
            finally:
                end_time = time.time()
                duration = end_time - start_time
                formatted_duration = format_duration(duration)
                if message_template:
                    log_message = message_template.format(
                        func.__name__, formatted_duration
                    )
                else:
                    log_message = f"{func.__name__} executed in {formatted_duration}"
                logging_function = getattr(logging, log_level.lower())
                logging_function(log_message)
            return result

        return wrapper

    return decorator


def format_duration(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_components = []
    if hours:
        time_components.append(f"{hours} h")
    if minutes:
        time_components.append(f"{minutes} min")
    if seconds or not time_components:
        time_components.append(f"{seconds} sec")
    return ", ".join(time_components)


@log_execution_time(log_level="info", message_template="Total execution time: {1}")
def main() -> None:
    args = parse_arguments()
    setup_initial_logging(args.loglevel, args.log_file)
    logging.debug(f"Running {PROGRAM_NAME} version {VERSION}")
    if args.init:
        dump_default_config()
        sys.exit(0)
    verify_ffmpeg_and_ffprobe_availability()
    try:
        config = load_config(args.config)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        sys.exit(1)
    loglevel = args.loglevel or config.get("loglevel", "info")
    update_logging_level(loglevel)
    logging.debug(
        "Loaded config:"
        + "\n"
        + "\n".join(f"  {key}: {value}" for key, value in config.items())
    )
    input_files = get_input_files(args.input)
    total_files = len(input_files)
    successful_files = 0
    for input_file in input_files:
        try:
            process_file(input_file, config, args)
            successful_files += 1
        except FFmpegError as e:
            logging.error(f"FFmpeg error processing file {input_file}: {e.message}")
            logging.debug(f"FFmpeg command: {' '.join(e.arguments)}")
        except FileProcessingError as e:
            logging.error(str(e))
        except Exception as e:
            logging.error(f"Error processing file {input_file}: {str(e)}")
    failed_files = total_files - successful_files
    emoji = " ✨" if successful_files and not failed_files else ""
    logging.info(f"Done!{emoji}")
    if successful_files:
        file_word = pluralize(successful_files, "file")
        logging.success(f"Successfully condensed {successful_files} {file_word}.")  # type: ignore
    if failed_files:
        file_word = pluralize(failed_files, "file")
        logging.warning(f"{failed_files} {file_word} failed to process.")
        sys.exit(2 if successful_files == 0 else 1)


@log_execution_time(log_level="debug", message_template="File processed in {1}")
def process_file(
    file_path: str, config: dict[str, Any], args: argparse.Namespace
) -> None:
    logging.info(f"Processing {file_path}")
    exit_if_file_missing(file_path)
    with tempfile.TemporaryDirectory() as temp_dir:
        context = Context.create(file_path, config, args, temp_dir)
        context.stream_info = get_all_stream_info(file_path)
        # Extracting subs can be slow; we get all user input before processing.
        if config["condensed_audio.enabled"] or config["condensed_video.enabled"]:
            context.selected_audio_stream = select_audio_stream(context)
            context.metadata = create_metadata(context)
        # Raises an error if no subtitles found.
        subtitle_path = find_subtitles(context)
        if context.config["condensed_subtitles.enabled"]:
            context.original_subtitle_format = get_subtitle_extension(context)
        subtitles = pysubs2.load(subtitle_path)
        line_skip_patterns = context.config["line_skip_patterns"]
        skip_patterns = [re.compile(pattern) for pattern in line_skip_patterns]
        if skip_patterns:
            filter_skip_patterns_in_place(subtitles, skip_patterns)
        skip_intervals = get_skipped_chapter_intervals(context)
        if skip_intervals:
            filter_chapters_in_place(subtitles, skip_intervals)
        speech_segments = extract_speech_timing_from_subtitles(context, subtitles)
        if not speech_segments:
            raise FileProcessingError(file_path, "No valid segments found")
        if config["condensed_subtitles.enabled"]:
            create_condensed_subtitles(context, subtitles, speech_segments)
        if context.selected_audio_stream:
            segment_files = extract_segments(context, speech_segments)
            if config["condensed_audio.enabled"]:
                create_condensed_audio(context, segment_files)
            if config["condensed_video.enabled"]:
                create_condensed_video(context, segment_files)


def verify_ffmpeg_and_ffprobe_availability() -> None:
    version_pattern = re.compile(r"version\s+([\d.]+)")
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            version_info = FFmpeg(executable=tool).option("version").execute()
            match = version_pattern.search(version_info.decode())
            version = match.group(1) if match else "Unknown"
            logging.debug(f"{tool} version: {version}")
        except Exception as e:
            logging.error(f"{tool} not found or not working properly. Error: {str(e)}")
            sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{PROGRAM_NAME}: {PROGRAM_TAGLINE}",
        epilog=f"Visit {REPOSITORY} to learn more~",
        add_help=False,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Print version and exit.",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="<path>",
        help=f'Path to a configuration file, or "none" to use the default configuration. Default: {CONFIG_FILENAME} in the user config directory (e.g. ~/.config/{PROGRAM_NAME}/{CONFIG_FILENAME}).',
    )
    parser.add_argument(
        "input",
        nargs="*",
        help="Path to the video files or directories to condense.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="<path>",
        help="Path to the output directory. If not specified, the input file's directory will be used.",
    )
    parser.add_argument(
        "--audio-track-id",
        type=int,
        metavar="<id>",
        help="ID of the audio track to use.",
    )
    parser.add_argument(
        "--sub-track-id",
        type=int,
        metavar="<id>",
        help="ID of the subtitle track to use.",
    )
    parser.add_argument(
        "-s",
        "--subtitles",
        metavar="<path>",
        help="Path to subtitle file or directory containing subtitle files.",
    )
    parser.add_argument(
        "--sub-delay",
        type=int,
        default=0,
        metavar="<ms>",
        help="Delay subtitles by <ms> milliseconds. Can be negative.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create a default configuration file in the user config directory.",
    )
    parser.add_argument(
        "-v",
        "--loglevel",
        choices=["debug", "info", "success", "warning", "error", "critical"],
        default=None,
        help="Set the logging level.",
    )
    parser.add_argument(
        "--log-file",
        metavar="<path>",
        help="Logs will be written to <path> in addition to the console.",
    )
    return parser.parse_args()


def get_input_files(file_paths: list[str]) -> list[str]:
    input_files = []
    for file_path in file_paths:
        path = Path(file_path)
        if path.is_file():
            input_files.append(str(path))
        elif path.is_dir():
            input_files.extend(str(f) for f in path.rglob("*") if f.is_file())
        else:
            logging.warning(f'Invalid input or not found, skipping: "{path}"')
    if not input_files:
        logging.error("No valid files found. Exiting.")
        sys.exit(1)
    return input_files


def get_all_stream_info(file_path: str) -> dict[str, Any]:
    logging.debug("Getting stream info with ffprobe…")
    info = (
        FFmpeg(executable="ffprobe")
        .input(file_path, show_streams=None, show_chapters=None, of="json")
        .execute()
    )
    parsed = json.loads(info)
    streams = parsed.get("streams", [])
    if not streams:
        raise FileProcessingError(file_path, "No streams found")
    return {
        "video": [s for s in streams if s["codec_type"] == "video"],
        "audio": [s for s in streams if s["codec_type"] == "audio"],
        "subtitle": [s for s in streams if s["codec_type"] == "subtitle"],
        "chapters": parsed.get("chapters", []),
    }


def select_audio_stream(context: Context) -> str:
    audio_languages = context.config.get("audio_languages")
    streams = context.stream_info["audio"]
    if not streams:
        raise ValueError("No audio streams found in the input file.")
    if context.args.audio_track_id is not None:
        if any(stream["index"] == context.args.audio_track_id for stream in streams):
            logging.info(f"Using specified audio stream: {context.args.audio_track_id}")
            return str(context.args.audio_track_id)
        else:
            raise ValueError(
                f"Specified audio stream {context.args.audio_track_id} not found."
            )
    if audio_languages:
        for lang in audio_languages:
            for stream in streams:
                tags = stream.get("tags", {})
                if tags.get("language", "").lower().startswith(lang.lower()):
                    logging.info(f"Using audio stream: {lang}")
                    return str(stream["index"])
    if len(streams) == 1:
        logging.info("Using the only available audio stream.")
        return str(streams[0]["index"])
    return display_and_select_stream(streams, "audio")


def display_and_select_stream(streams: list[dict[str, Any]], stream_type: str) -> str:
    display_streams(streams, stream_type)
    selected_index = get_user_selection(streams, stream_type)
    selected_stream = next(s for s in streams if str(s["index"]) == selected_index)
    logging.info(
        f"Selected {stream_type} stream: {format_stream_info(selected_stream, stream_type)}"
    )
    return selected_index


def display_streams(streams: list[dict[str, Any]], stream_type: str) -> None:
    print(f"\nAvailable {stream_type} streams:")
    for stream in streams:
        print(f"  {format_stream_info(stream, stream_type)}")


def format_stream_info(stream: dict[str, Any], stream_type: str) -> str:
    index = stream["index"]
    tags = stream.get("tags", {})
    lang = tags.get("language", "Unknown language")
    title = tags.get("title", "No title")
    codec = stream.get("codec_name", "Unknown codec")
    if stream_type == "audio":
        return f"[{index}] Language: {lang} | Title: {title} | Codec: {codec}"
    support_marker = "" if is_supported_subtitle_format(codec) else " (*)"
    return (
        f"[{index}] Language: {lang} | Title: {title} | Format: {codec}{support_marker}"
    )


def is_supported_subtitle_format(codec: str) -> bool:
    format_identifier = CODEC_TO_FORMAT_IDENTIFIER.get(codec.lower(), codec.lower())
    return format_identifier in SUPPORTED_SUBTITLE_FORMATS


def get_user_selection(
    supported_streams: list[dict[str, Any]], stream_type: str
) -> str:
    while True:
        selection = input(
            f"\nEnter the {stream_type} index to use (press Enter for first supported stream): "
        ).strip()
        if selection == "":
            return str(supported_streams[0]["index"])
        try:
            index = int(selection)
            if any(s["index"] == index for s in supported_streams):
                return str(index)
            print(
                f"Invalid selection. Choose a supported {stream_type} stream from the list."
            )
        except ValueError:
            print(
                "Invalid input. Enter a number or press Enter for the first supported stream."
            )


def create_metadata(context: Context) -> dict[str, str]:
    logging.debug("Preparing metadata…")
    input_dirname = os.path.basename(os.path.dirname(context.file_path))
    clean_name = context.clean_name
    season, episode = extract_season_and_episode(context.basename, input_dirname)
    metadata = {
        "title": clean_name,
        "artist": PROGRAM_NAME,
        "genre": f"Condensed Media",
        "track": episode,
        "disc": season,
        "album": f"Condensed with {PROGRAM_NAME}",
        "date": str(time.gmtime().tm_year),
        "encoded_by": f"{PROGRAM_NAME} v{VERSION}",
        "comment": f"{context.basename} condensed with {PROGRAM_NAME} — {REPOSITORY}",
    }
    # See https://github.com/jonghwanhyeon/python-ffmpeg/issues/65.
    indexed_metadata = {
        f"metadata:g:{i}": f"{k}={v}" for i, (k, v) in enumerate(metadata.items())
    }
    return indexed_metadata


def find_subtitles(context: Context) -> str:
    file_path = Path(context.file_path).resolve()
    subtitle_path = context.args.subtitles or context.config.get("subtitle_directory")
    search_locations = []
    if subtitle_path:
        subtitles_path = Path(os.path.expanduser(subtitle_path))
        if subtitles_path.is_file():
            logging.info(f"Using provided subtitle file: {subtitles_path}")
            return str(subtitles_path)
        elif subtitles_path.is_dir():
            search_locations.append(("provided directory", subtitles_path))
        else:
            raise ValueError(f"Invalid path provided for subtitles: {subtitles_path}")
    if context.config["external_subtitle_search"] != "disabled":
        search_locations.append(("input file directory", file_path.parent))
    for location_name, directory in search_locations:
        matched_sub = find_matching_subtitle_file(
            context, str(directory), context.input_name
        )
        if matched_sub:
            return matched_sub
        logging.debug(f"No suitable subtitles found in {location_name}.")
    logging.info("No external subtitles found, attempting extraction from video file…")
    return extract_subtitles(context)


def find_matching_subtitle_file(
    context: Context,
    input_dir: str,
    input_name: str,
) -> Optional[str]:
    logging.debug(
        f"Looking for external subtitles with extensions: {', '.join(SUBTITLE_EXTENSIONS)}"
    )
    external_subtitle_search = context.config["external_subtitle_search"]
    for ext in SUBTITLE_EXTENSIONS:
        exact_sub_match = os.path.join(input_dir, f"{input_name}{ext.lower()}")
        if os.path.exists(exact_sub_match):
            logging.debug(f"Exact subtitle match found: {exact_sub_match}")
            return exact_sub_match
    if external_subtitle_search == "fuzzy":
        return find_fuzzy_subtitle_match(context, input_dir, input_name)
    return None


def find_fuzzy_subtitle_match(
    context: Context,
    directory: str,
    input_name: str,
) -> Optional[str]:
    logging.debug("No exact match found. Trying fuzzy matching.")
    # Find all subtitle files in the directory.
    all_subs = [
        f
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in SUBTITLE_EXTENSIONS
    ]
    if not all_subs:
        logging.debug("No subtitle files found in the directory.")
        return None
    cleaned_input_name = prepare_filename_for_matching(input_name)
    similarity_scores = []
    logging.debug(f"Finding best match amongst {len(all_subs)} subtitle files…")
    for sub_file in all_subs:
        cleaned_sub_name = prepare_filename_for_matching(os.path.splitext(sub_file)[0])
        similarity = character_based_similarity(cleaned_input_name, cleaned_sub_name)
        similarity_scores.append((sub_file, similarity))
    similarity_scores.sort(key=lambda x: x[1], reverse=True)
    threshold = context.config["subtitle_match_threshold"]
    if similarity_scores and similarity_scores[0][1] >= threshold:
        best_match = os.path.join(directory, similarity_scores[0][0])
        logging.info(
            f"Fuzzy match found: {best_match} (similarity: {similarity_scores[0][1]:.2f})"
        )
        return best_match
    logging.debug(f"No fuzzy match found with threshold {threshold}.")
    logging.debug(
        f"Best match: {similarity_scores[0][0]} ({similarity_scores[0][1]:.2f})"
    )
    return None


def prepare_filename_for_matching(filename: str) -> str:
    filename = clean_filename(filename)
    # Extract all years.
    years = re.findall(YEAR_PATTERN, filename)
    # Convert to lowercase.
    words = filename.lower().split()
    # Remove years from the cleaned words.
    words = [word for word in words if word not in years]
    # Add all extracted years back at the end.
    words.extend(years)
    return " ".join(words).strip()


def clean_filename(filename: str) -> str:
    # Remove file extension.
    filename = re.sub(r"\.[^.]+$", "", filename)
    # Audio format.
    filename = re.sub(
        r"\b(?:DTS(?:-HD)?|MA|DD?P?(?:\+?(?:Atmos|[1-9](?:\.[1-9])?))?|AC-?3?|AAC|FLAC|TrueHD|Atmos)(?:[-\s.]?(?:\d+\.?)+(?:ch)?)?\b",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    # Remove content within brackets and parentheses, except years.
    filename_sans_brackets = re.sub(
        rf"\((?!{YEAR_PATTERN}\))[^)]*\)|\[(?!{YEAR_PATTERN}\])[^\]]*\]", "", filename
    )
    # In case everything was enclosed in brackets/paren.
    if filename_sans_brackets:
        filename = filename_sans_brackets
    # Encoding.
    filename = re.sub(
        r"\b([xh]\.*\d{3}.*|HEVC|AVC|U?HDRip|REPACK|(?:HYBRID[-\s]?)?REMUX|HYBRID)\b",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    # Resolution.
    filename = re.sub(
        r"\b\d{3,5}x\d{3,4}p?\b|\b\d{3,4}p\b", "", filename, flags=re.IGNORECASE
    )
    # Video quality.
    filename = re.sub(
        r"\b(U?HD|[248]K|[SH]DR1?0?)\b", "", filename, flags=re.IGNORECASE
    )
    # Replace non-alphanumeric characters with spaces, except apostrophes, colons, dash and +.
    filename = re.sub(r"[_\[\]{}<>|`~!@#\.%^*()=+]", " ", filename)
    # Replace multiple spaces with a single space
    filename = re.sub(r"\s+", " ", filename)
    # Remove extra spaces and trim.
    return " ".join(filename.split()).strip()


def character_based_similarity(str1: str, str2: str) -> float:
    return SequenceMatcher(None, str1, str2).ratio()


def extract_subtitles(context: Context) -> str:
    streams = context.stream_info["subtitle"]
    if not streams:
        raise ValueError("No subtitle streams found in the input file.")
    if context.args.sub_track_id is not None:
        if any(stream["index"] == context.args.sub_track_id for stream in streams):
            logging.info(
                f"Using specified subtitle stream: {context.args.sub_track_id}"
            )
            return extract_specific_subtitle(context, context.args.sub_track_id)
        else:
            raise ValueError(
                f"Specified subtitle stream {context.args.sub_track_id} not found."
            )
    supported_streams = [
        s for s in streams if is_supported_subtitle_format(s.get("codec_name", ""))
    ]
    unsupported_streams = [s for s in streams if s not in supported_streams]
    if unsupported_streams:
        logging.debug("Dropping unsupported subtitle streams:")
        for stream in unsupported_streams:
            logging.debug(f"  {format_stream_info(stream, 'subtitle')}")
    if not supported_streams:
        raise ValueError("No supported subtitle streams found.")
    subtitle_languages = context.config.get("subtitle_languages", [])
    sorted_streams = sort_subtitle_streams(supported_streams, subtitle_languages)
    if sorted_streams != supported_streams:
        logging.debug("Streams have been sorted.")
    if subtitle_languages:
        best_stream = sorted_streams[0]
        if best_stream["tags"].get("language", "").lower() in [
            lang.lower() for lang in subtitle_languages
        ]:
            logging.info(
                f"Using subtitle stream: {best_stream['tags'].get('language')}"
            )
            return extract_specific_subtitle(context, best_stream["index"])
        else:
            logging.warning(
                f"No subtitles found for specified languages: {', '.join(subtitle_languages)}."
            )
    if len(sorted_streams) == 1:
        logging.info("Using only available supported subtitle stream.")
        return extract_specific_subtitle(context, sorted_streams[0]["index"])
    selected_stream = display_and_select_stream(sorted_streams, "subtitle")
    return extract_specific_subtitle(context, int(selected_stream))


def sort_subtitle_streams(
    streams: list[dict[str, Any]], preferred_languages: list[str] = []
) -> list[dict[str, Any]]:
    def stream_sort_key(stream: dict[str, Any]) -> tuple[int, int, int, int, str]:
        tags = stream.get("tags", {})
        language = tags.get("language", "").lower()
        title = tags.get("title", "").lower()
        lang_priority = (
            (
                preferred_languages.index(language)
                if language in preferred_languages
                else len(preferred_languages)
            )
            if preferred_languages
            else 0
        )
        is_forced = int(tags.get("forced", "0") != "1")
        is_default = int(stream.get("disposition", {}).get("default", 0) != 1)
        title_penalty = sum(1 for word in PENALIZED_SUBTITLE_KEYWORDS if word in title)
        return (lang_priority, is_forced, is_default, title_penalty, title)

    return sorted(streams, key=stream_sort_key)


def extract_specific_subtitle(context: Context, stream_index: int) -> str:
    stream_info = context.stream_info["subtitle"]
    matching_stream = next(
        (stream for stream in stream_info if stream["index"] == stream_index), None
    )
    if matching_stream is None:
        raise ValueError(f"Stream with index {stream_index} not found in stream_info.")
    codec_name = matching_stream["codec_name"]
    format_identifier = CODEC_TO_FORMAT_IDENTIFIER.get(codec_name, codec_name.lower())
    output_path = os.path.join(
        context.temp_dir, f"subtitles_{stream_index}.{format_identifier}"
    )
    logging.info(f"Extracting subtitles to {format_identifier} format…")
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input(context.file_path)
        .output(output_path, map=f"0:{stream_index}")
    )
    ffmpeg.execute()
    return output_path


def filter_skip_patterns_in_place(
    subs: pysubs2.SSAFile, skip_patterns: list[re.Pattern]
) -> None:
    logging.debug("Filtering subtitles based on skip patterns…")
    subs.events = [
        line
        for line in subs
        if not any(pattern.match(line.plaintext) for pattern in skip_patterns)
    ]


def get_skipped_chapter_intervals(context: Context) -> list[tuple[float, float]]:
    skip_titles = context.config.get("skip_chapters", [])
    matched_chapters = [
        chapter
        for chapter in context.stream_info["chapters"]
        if chapter["tags"]["title"].lower() in skip_titles
    ]
    if matched_chapters:
        logging.debug(
            f"Skipping {len(matched_chapters)} matched chapters: "
            f"{', '.join(ch['tags']['title'] for ch in matched_chapters)}"
        )
    return [(float(ch["start_time"]), float(ch["end_time"])) for ch in matched_chapters]


def filter_chapters_in_place(
    subs: pysubs2.SSAFile,
    skip_intervals: list[tuple[float, float]],
) -> None:
    logging.debug("Filtering subtitles based on chapters…")

    def segments_overlap(
        sub_start: float, sub_end: float, skip: tuple[float, float]
    ) -> bool:
        return not (sub_end < skip[0] or sub_start > skip[1])

    subs.events = [
        line
        for line in subs
        if not any(
            segments_overlap(line.start / 1000, line.end / 1000, skip)
            for skip in skip_intervals
        )
    ]


def extract_speech_timing_from_subtitles(
    context: Context, subtitles: pysubs2.SSAFile
) -> list[tuple[float, float]]:
    delay = context.args.sub_delay
    if delay != 0:
        logging.debug(f"Applying subtitle offset of {delay:.3f} milliseconds.")
        subtitles.shift(ms=delay)
    padding = context.config["padding"]
    segments = []
    for line in subtitles:
        start = line.start / 1000 - padding
        end = line.end / 1000 + padding
        start = max(0, start)
        end = max(0, end)
        if end > start:  # Only add segments with positive duration.
            segments.append((start, end))
    merged_segments = merge_overlapping_segments(segments)
    if INCLUDE_DEMO_UTILS:
        save_segments_as_json(context, merged_segments)  # type: ignore  # pragma: no cover
        sys.exit(0)  # pragma: no cover
    return merged_segments


def merge_overlapping_segments(
    segments: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not segments:
        return []
    segments.sort(key=lambda x: x[0])  # Sort by start time.
    merged = [segments[0]]
    for current in segments[1:]:
        previous = merged[-1]
        if current[0] <= previous[1]:
            # Merge overlapping segments.
            merged[-1] = (previous[0], max(previous[1], current[1]))
        else:
            merged.append(current)
    return merged


def generate_output_path(context: Context, extension: str) -> str:
    if context.config.get("clean_output_filename"):
        filename = context.clean_name
    else:
        filename = context.input_name
    file_path = context.file_path
    suffix = context.config.get("output_suffix")
    filename = f"{filename}{suffix}.{extension}"
    if context.args.output:
        output_dir = Path(os.path.expanduser(context.args.output))
    elif context.config.get("output_directory"):
        output_dir = Path(os.path.expanduser(context.config["output_directory"]))
    else:
        output_dir = Path(file_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / filename)


def get_audio_extension(context: Context) -> str:
    logging.debug("Getting audio extension…")
    audio_codec = context.config["condensed_audio.audio_codec"]
    if audio_codec == "copy" and context.selected_audio_stream is not None:
        try:
            # ffmpeg uses 1-based indexing for streams.
            stream_index = int(context.selected_audio_stream) - 1
            original_codec = (
                context.stream_info["audio"][stream_index].get("codec_name", "").lower()
            )
            logging.debug(f"The original codec is: {original_codec}")
            return get_extension_for_codec(original_codec)
        except (IndexError, ValueError) as e:
            logging.error(f"Error accessing audio stream info: {e}")
            return get_extension_for_codec(audio_codec)
    return get_extension_for_codec(audio_codec)


def get_subtitle_extension(context: Context) -> str:
    if context.config["condensed_subtitles.format"] != "auto":
        format = context.config["condensed_subtitles.format"]
        logging.debug(f"Using user-specified format: {format}")
        return str(format)
    if hasattr(context, "original_subtitle_format"):
        extension = context.original_subtitle_format
        if f".{extension}" in FILE_EXTENSION_TO_FORMAT_IDENTIFIER:
            logging.debug(f"Using input subtitle format: {extension}")
            return str(extension)
    logging.debug(f"No valid subtitle format found, using 'srt'")
    return "srt"


def get_extension_for_codec(codec: str) -> str:
    return {
        "aac": "m4a",
        "alac": "m4a",
        "flac": "flac",
        "libmp3lame": "mp3",
        "libopus": "ogg",
        "pcm_s16le": "wav",
    }.get(codec.lower(), "mkv")


def create_condensed_audio(
    context: Context,
    segment_files: list[str],
) -> None:
    audio_extension = get_audio_extension(context)
    logging.debug(f"Using audio extension: {audio_extension}")
    temp_path = os.path.join(context.temp_dir, f"temp.{audio_extension}")
    logging.debug("Creating concat file…")
    concat_file = create_concat_file(segment_files, context.temp_dir)
    encode_final_audio(context, concat_file, temp_path)
    suggested_path = generate_output_path(context, audio_extension)
    final_path = safe_move(context, temp_path, suggested_path)
    if final_path:
        logging.success(f"Condensed audio created successfully: '{final_path}'")  # type: ignore


def extract_segments(
    context: Context,
    segments: list[tuple[float, float]],
) -> list[str]:
    logging.info(f"Extracting {len(segments)} segments…")
    file_path = context.file_path
    video_stream_index = None
    if context.config["condensed_video.enabled"]:
        video_stream = next((s for s in context.stream_info["video"]), None)
        if not video_stream:
            raise FileProcessingError(file_path, "No video stream found")
        video_stream_index = video_stream["index"]
    segment_files: list[str] = []
    progress_bar = custom_progress_bar(len(segments))
    for i, (start, end) in enumerate(segments):
        segment_file = Path(context.temp_dir) / f"segment_{i}.mkv"
        segment_files.append(str(segment_file))
        extract_segment(
            file_path,
            str(segment_file),
            start,
            end,
            str(context.selected_audio_stream),
            video_stream_index,
        )
        if progress_bar:
            progress_bar.update(1)
    if progress_bar:
        progress_bar.close()
    return segment_files


def extract_segment(
    file_path: str,
    output_path: str,
    start: float,
    end: float,
    selected_audio_stream: str,
    video_stream_index: Optional[int],
) -> None:
    ffmpeg_options: dict = {
        "ss": start,
        "to": end,
        "avoid_negative_ts": "make_zero",
        "map": [f"0:{selected_audio_stream}"],
        "c:a": "copy",
    }
    if video_stream_index is not None:
        ffmpeg_options["map"] = ffmpeg_options["map"] + [f"0:{video_stream_index}"]
        ffmpeg_options["c:v"] = "copy"
    ffmpeg = (
        FFmpeg().option("y").input(file_path).output(url=output_path, **ffmpeg_options)
    )
    ffmpeg.execute()


def create_concat_file(segment_files: list[str], temp_dir: str) -> str:
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for segment_file in segment_files:
            f.write(f"file '{segment_file}'\n")
    return concat_file


def encode_final_audio(context: Context, concat_file: str, output_path: str) -> None:
    ffmpeg_audio_options = get_ffmpeg_audio_options(context, media_type="audio")
    custom_args = context.config.get("condensed_audio.custom_ffmpeg_args") or {}
    ffmpeg_options = ffmpeg_audio_options | custom_args | context.metadata
    logging.debug(f"ffmpeg options: {ffmpeg_options}")
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input(concat_file, f="concat", safe=0)
        .output(
            url=output_path,
            map="0:a",
            **ffmpeg_options,
        )
    )
    logging.info("Creating condensed audio…")
    ffmpeg.execute()


def get_ffmpeg_audio_options(
    context: Context,
    media_type: Literal["audio", "video"] = "audio",
) -> dict[str, Any]:
    logging.debug("Getting audio options…")
    audio_quality = context.config.get(f"condensed_{media_type}.audio_quality")
    audio_codec = context.config[f"condensed_{media_type}.audio_codec"]
    if audio_codec == "copy":
        return {"c:a": "copy"}
    options = {
        "c:a": audio_codec,
        "ac": 2,  # Force stereo.
    }
    if audio_codec == "pcm_s16le":
        options["f"] = "wav"
    if audio_quality is None:
        return options
    if audio_codec == "flac":
        options["compression_level"] = audio_quality
    elif audio_codec == "aac":
        key = "q:a" if str(audio_quality).isdigit() else "b:a"
        options[key] = audio_quality
    elif audio_codec == "libopus":
        if isinstance(audio_quality, str) and audio_quality.lower().endswith("k"):
            options["b:a"] = audio_quality
        elif str(audio_quality).isdigit():
            options["b:a"] = f"{int(audio_quality)}b"
        options["application"] = "voip"
    elif audio_codec == "libmp3lame":
        if isinstance(audio_quality, str):
            if audio_quality.lower().startswith("v"):
                audio_quality = audio_quality[1:]
            if audio_quality.isdigit() and 0 <= int(audio_quality) <= 9:
                options["q:a"] = audio_quality
            elif audio_quality.lower().endswith("k") and audio_quality[:-1].isdigit():
                options["b:a"] = audio_quality
            else:
                options["q:a"] = DEFAULT_MP3_VBR_QUALITY
        else:
            options["q:a"] = audio_quality
    else:
        options["b:a"] = audio_quality
    return options


def prepare_filename_for_display(filename: str) -> str:
    # Clean stuff that might be helpful for matching subs to files, but irrelevant for display.
    # Source.
    filename = re.sub(
        r"\b(DV|Blu(-| )?Ray|NF|REMASTERED|HMAX|AMZN|DSNP|SESO|ATVP|HULU|WEB(-| )?(DL|RIP)?|DVDRip|BDRip)\b",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    # 🦜🏴‍☠️
    filename = re.sub(
        r"[-.](?=[^.]*\.(?:[a-zA-Z]{2,4})$)(?:[A-Z0-9]{2,}|(?:(?=[a-z]*[A-Z][a-z]*[A-Z])|(?=[A-Z]*[a-z][A-Z]*))(?=.*[A-Z])(?=.*[a-z])[A-Za-z0-9-]{2,}|[A-Za-z0-9]{2,5})(?=[.-]?\w+$)",
        "",
        filename,
    )
    filename = re.sub(r"([A-Z]+|(?=.*[A-Z]){2,4})(?=\.[a-zA-Z]{2,4}$)", "", filename)
    # Other stuff.
    filename = re.sub(
        r"\b(_-_|DoVi|E\.N\.D|DVD|PAL|CR|FUNI|U-NEXT|Dual[\. ]Audio|PROPER|JPN\+?ENG|JAP|GBR|ENG|JAPANESE|JPN|SUBBED|DUAL|Remaster|MA\.5\.1)\b",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    filename = clean_filename(filename)
    # Wrap the year in parentheses, if present.
    END_YEAR_PATTERN = YEAR_PATTERN + r"\s*$"
    filename = re.sub(END_YEAR_PATTERN, r"(\1)", filename)
    return filename


def extract_season_and_episode(filename: str, directory_name: str) -> tuple[str, str]:
    logging.debug("Extracting season and episode numbers…")
    season_patterns = [
        r"\bS(\d+)(?=E\d+\b)",  # SxxExx.
        r"\bS(\d+)\b",  # Sxx.
        r"Season\s*(\d+)",  # "Season x".
        r"_S(\d+)_",  # _Sxx_.
        r"第(\d+)季",  # Japanese season format.
    ]
    episode_patterns = [
        r"\bE(\d+)\b",  # Standard (E01).
        r"Ep?\.?\s*(\d+)\b",  # Ep01, Ep.01, E.01.
        r"[_\s]-\s*(\d+)(?:v\d+)?",  # " - 01" or " - 01v2" format. Allows underscore before hyphen.
        r"[_\s](\d+)(?:v\d+)?(?=[_\s]|$|\(|\[)",  # Standalone number, possibly followed by version (v2, v3, etc.), allowing underscore.
        r"\[(\d+)(?:v\d+)?\]",  # [01] or [01v2].
        r"第(\d+)[話话]",  # Japanese episode format.
        r"#(\d+)",  # #01 format.
    ]
    logging.debug(f"Filename: {filename}")
    logging.debug(f"Directory name: {directory_name}")
    season = (
        find_match(season_patterns, filename)
        or find_match(season_patterns, directory_name)
        or "01"
    )
    episode = (
        find_match(episode_patterns, filename)
        or find_match(episode_patterns, directory_name)
        or "01"
    )
    logging.debug(f"Season: {season}, Episode: {episode}")
    return season, episode


def find_match(patterns: list[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result = match.group(1).zfill(2)
            logging.debug(f"Match found: {result} (pattern: {pattern})")
            return result
    return None


def get_destination_path(context: Context, final_path: str) -> Optional[str]:
    if not os.path.exists(final_path):
        return final_path
    if_file_exists = context.config["if_file_exists"]
    if if_file_exists == "skip":
        logging.info(f"Skipping existing file: '{final_path}'")
        return None
    if if_file_exists == "ask":
        user_choice = prompt_user_choice(
            prompt=f"⚠️ File already exists: '{final_path}'",
            choices=["Overwrite", "Rename", "Skip"],
            default="Rename",
        )
        if user_choice == "skip":
            logging.info(f"Skipping existing file: '{final_path}'")
            return None
        if_file_exists = user_choice
    if if_file_exists == "rename":
        base, ext = os.path.splitext(final_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = f"{base}_{timestamp}{ext}"
        logging.info(f"Renaming file to: '{final_path}'")
    else:  # overwrite.
        logging.info(f"Overwriting existing file: '{final_path}'")
    return final_path


def safe_move(context: Context, temp_path: str, final_path: str) -> str:
    destination = get_destination_path(context, final_path)
    if destination is None:
        return ""
    shutil.move(temp_path, destination)
    return destination


def create_condensed_subtitles(
    context: Context,
    subs: pysubs2.SSAFile,
    speech_segments: list[tuple[float, float]],
) -> None:
    logging.info("Creating condensed subtitles…")
    subs.sort()  # Sort by start time.
    condensed_subs = pysubs2.SSAFile()
    cumulative_duration = 0
    progress_bar = custom_progress_bar(len(speech_segments))
    # Pre-calculate subtitle start times in milliseconds.
    sub_starts = [sub.start for sub in subs]
    condensed_subs_batch = []
    for segment_start, segment_end in speech_segments:
        segment_start = int(segment_start * 1000)
        segment_end_ms = int(segment_end * 1000)
        segment_duration = segment_end_ms - segment_start
        # Find the index of the first subtitle that starts within this segment.
        start_index = bisect_left(sub_starts, segment_start)
        for sub in subs[start_index:]:
            if sub.start >= segment_end_ms:
                break
            new_sub = pysubs2.SSAEvent()
            new_sub.start = sub.start - segment_start + cumulative_duration
            new_sub.end = min(
                sub.end - segment_start + cumulative_duration,
                segment_duration + cumulative_duration,
            )
            new_sub.text = sub.text
            condensed_subs_batch.append(new_sub)
        cumulative_duration += segment_duration
        if progress_bar:
            progress_bar.update(1)
    if progress_bar:
        progress_bar.close()
    condensed_subs.events.extend(condensed_subs_batch)
    subtitle_extension = get_subtitle_extension(context)
    temp_path = os.path.join(context.temp_dir, f"temp.{subtitle_extension}")
    if subtitle_extension == "lrc":
        lrc_content = convert_to_lrc(condensed_subs, context.clean_name)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
    else:
        condensed_subs.save(temp_path)
    suggested_path = generate_output_path(context, subtitle_extension)
    final_path = safe_move(context, temp_path, suggested_path)
    if final_path:
        logging.success(f"Condensed subtitles created successfully: '{final_path}'")  # type: ignore


def convert_to_lrc(subs: pysubs2.SSAFile, clean_name: str) -> str:
    # Start the LRC file with metadata.
    lrc_lines = [
        f"[ti:{clean_name}]",
        f"[tool:{PROGRAM_NAME}]",
        f"[ve:{VERSION}]",
        f"[by:{REPOSITORY}]",
        "",
    ]
    for sub in subs:
        sub.text = strip_subtitle_styles(sub.text)
        start_time = sub.start / 1000  # Milliseconds to seconds.
        minutes, seconds = divmod(start_time, 60)
        # The LRC format does not support hours.
        lrc_time = f"[{int(minutes):02d}:{seconds:05.2f}]"
        lrc_lines.append(f"{lrc_time}{sub.text}")
    return "\n".join(lrc_lines) + "\n"


def strip_subtitle_styles(text: str) -> str:
    stripped_text = "".join(fragment for fragment, _ in parse_tags(text))
    # Replace line breaks with a space.
    stripped_text = stripped_text.replace("\\N", " ")
    # Ensure there's no double spaces.
    stripped_text = " ".join(stripped_text.split())
    return stripped_text


def create_condensed_video(
    context: Context,
    segment_files: list[str],
) -> None:
    logging.debug("Preparing to create condensed video…")
    video_extension = get_video_extension(context)
    temp_output_path = os.path.join(context.temp_dir, f"temp.{video_extension}")
    concat_file = create_concat_file(segment_files, context.temp_dir)
    video_options = get_ffmpeg_video_options(context)
    audio_options = get_ffmpeg_audio_options(context, media_type="video")
    custom_args = context.config.get("condensed_video.custom_ffmpeg_args") or {}
    ffmpeg_options = video_options | audio_options | custom_args | context.metadata
    logging.debug(f"ffmpeg options: {ffmpeg_options}")
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input(concat_file, f="concat", safe=0)
        .output(
            url=temp_output_path,
            map=["0:v", "0:a"],
            **ffmpeg_options,
        )
    )
    logging.info("Creating condensed video…")
    ffmpeg.execute()
    suggested_path = generate_output_path(context, video_extension)
    final_path = safe_move(context, temp_output_path, suggested_path)
    if final_path:
        logging.success(f"Condensed video created successfully: '{final_path}'")  # type: ignore


def get_video_extension(context: Context) -> str:
    video_codec = context.config["condensed_video.video_codec"]
    codec_to_extension = {
        "libx264": "mp4",
        "h264": "mp4",
        "libx265": "mp4",
        "hevc": "mp4",
        "libvpx": "webm",
        "vp8": "webm",
        "libvpx-vp9": "webm",
        "vp9": "webm",
        "libaom-av1": "mp4",
        "av1": "mp4",
        "mpeg4": "mp4",
        "libxvid": "avi",
        "msmpeg4": "avi",
        "flv": "flv",
        "wmv2": "wmv",
        "mjpeg": "avi",
        # Original extension for copy.
        "copy": os.path.splitext(context.file_path)[1][1:],
    }
    extension = codec_to_extension.get(video_codec, "mkv")
    logging.debug(f"Selected video codec: {video_codec}, using extension: {extension}")
    return extension


def get_ffmpeg_video_options(context: Context) -> dict[str, Any]:
    logging.debug("Getting video options…")
    video_codec = context.config["condensed_video.video_codec"]
    video_quality = context.config["condensed_video.video_quality"]
    options = {"c:v": video_codec}
    if video_codec == "copy":
        return options
    quality_option = (
        "crf" if video_codec in ["libx264", "libx265", "libvpx-vp9", "vp9"] else "b:v"
    )
    options[quality_option] = video_quality
    return options


class ProgressBar:
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.max_width = 100
        self.min_bar_length = 10

    def _get_progress_bar(self) -> str:
        available_width = min(
            shutil.get_terminal_size((80, 20)).columns, self.max_width
        )
        count_display = f"{self.current}/{self.total}"
        percentage = f"{(self.current/self.total*100):3.0f}%"

        # Bar space = total - static elements (percentage, count, borders, spaces).
        bar_length = max(
            available_width - len(percentage) - len(count_display) - 5,
            self.min_bar_length,
        )
        filled = int(bar_length * self.current / self.total)

        return f"\r{percentage} |{'█' * filled}{' ' * (bar_length - filled)}| {count_display}"

    def update(self, n: int = 1) -> None:
        self.current += n
        print(self._get_progress_bar(), end="", flush=True)

    def close(self) -> None:
        print(self._get_progress_bar() + "\n", end="", flush=True)


def custom_progress_bar(total: int) -> Optional[ProgressBar]:
    if not logging.getLogger().getEffectiveLevel() <= logging.INFO:
        return None
    return ProgressBar(total)


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    if plural is None:
        plural = singular + "s"
    return singular if count == 1 else plural


if __name__ == "__main__":
    main()  # pragma: no cover
