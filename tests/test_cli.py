import argparse
import json
import logging
import os
import re
import sys
import time
from copy import deepcopy
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import pysubs2
import pytest
from ffmpeg import FFmpeg

from shuku.cli import (
    DEFAULT_MP3_VBR_QUALITY,
    PENALIZED_SUBTITLE_KEYWORDS,
    Context,
    FileProcessingError,
    convert_to_lrc,
    create_concat_file,
    create_condensed_subtitles,
    display_and_select_stream,
    extract_season_and_episode,
    extract_specific_subtitle,
    extract_speech_timing_from_subtitles,
    extract_subtitles,
    filter_chapters_in_place,
    filter_skip_patterns_in_place,
    find_matching_subtitle_file,
    find_subtitles,
    generate_output_path,
    get_all_stream_info,
    get_audio_extension,
    get_ffmpeg_audio_options,
    get_ffmpeg_video_options,
    get_input_files,
    get_skipped_chapter_intervals,
    merge_overlapping_segments,
    prepare_filename_for_display,
    prepare_filename_for_matching,
    process_file,
    safe_move,
    select_audio_stream,
    sort_subtitle_streams,
    strip_subtitle_styles,
    verify_ffmpeg_and_ffprobe_availability,
)
from shuku.config import DEFAULT_CONFIG
from shuku.utils import prompt_user_choice


@pytest.fixture
def base_context(tmp_path):
    input_path = str(tmp_path / "input.mkv")
    input_name = "input"
    return Context(
        file_path=input_path,
        config=deepcopy(DEFAULT_CONFIG),
        args=argparse.Namespace(
            sub_delay=0,
            output=None,
            sub_track_id=None,
            audio_track_id=None,
            subtitles=None,
        ),
        temp_dir=str(tmp_path),
        metadata={},
        stream_info={
            "audio": [
                {"index": 0, "tags": {"language": "eng"}},
                {"index": 1, "tags": {"language": "jpn"}},
                {"index": 2, "tags": {"language": "fra"}},
            ],
            "subtitle": [],
        },
        selected_audio_stream=None,
        original_subtitle_format="srt",
        input_name=input_name,
        basename=input_name,
        clean_name=input_name,
    )


@pytest.mark.parametrize("search_config", ["enabled", "disabled"])
def test_find_subtitles_search_configurations(base_context, tmp_path, search_config):
    base_context.args.subtitles = None
    base_context.config = {"external_subtitle_search": search_config}
    base_context.file_path = str(tmp_path / "video.mp4")
    with (
        patch("shuku.cli.find_matching_subtitle_file") as mock_find,
        patch("shuku.cli.extract_subtitles") as mock_extract,
    ):
        mock_find.return_value = (
            str(tmp_path / "found.srt") if search_config == "enabled" else None
        )
        mock_extract.return_value = str(tmp_path / "extracted.srt")
        result = find_subtitles(base_context)
    if search_config == "enabled":
        assert result == str(tmp_path / "found.srt")
        mock_find.assert_called_once()
        mock_extract.assert_not_called()
    else:
        assert result == str(tmp_path / "extracted.srt")
        mock_find.assert_not_called()
        mock_extract.assert_called_once()


def test_find_subtitles_with_file(base_context, tmp_path):
    subtitle_file = tmp_path / "test.srt"
    subtitle_file.touch()
    base_context.args.subtitles = str(subtitle_file)
    base_context.config = {"external_subtitle_search": "disabled"}
    result = find_subtitles(base_context)
    assert result == str(subtitle_file)


def test_find_subtitles_with_directory(base_context, tmp_path):
    base_context.args.subtitles = str(tmp_path)
    base_context.config = {"external_subtitle_search": "enabled"}
    base_context.file_path = str(tmp_path / "video.mp4")
    with patch("shuku.cli.find_matching_subtitle_file") as mock_find:
        mock_find.return_value = str(tmp_path / "found.srt")
        result = find_subtitles(base_context)
    assert result == str(tmp_path / "found.srt")
    mock_find.assert_called_once()


def test_find_subtitles_invalid_path(base_context):
    base_context.args.subtitles = "nonexistent_path"
    base_context.config = {"external_subtitle_search": "disabled"}
    with pytest.raises(ValueError, match="Invalid path provided for subtitles"):
        find_subtitles(base_context)


def test_find_subtitles_no_external_search(base_context, tmp_path):
    base_context.args.subtitles = None
    base_context.config = {"external_subtitle_search": "disabled"}
    base_context.file_path = str(tmp_path / "video.mp4")
    with patch("shuku.cli.extract_subtitles") as mock_extract:
        mock_extract.return_value = str(tmp_path / "extracted.srt")
        result = find_subtitles(base_context)
    assert result == str(tmp_path / "extracted.srt")
    mock_extract.assert_called_once()


def test_find_subtitles_external_search_no_match(base_context, tmp_path):
    base_context.args.subtitles = None
    sub_dir = tmp_path / "sub_dir"
    sub_dir.mkdir()
    base_context.config = {
        "external_subtitle_search": "enabled",
        "subtitle_directory": str(sub_dir),
    }
    base_context.file_path = str(tmp_path / "video.mp4")
    with (
        patch("shuku.cli.find_matching_subtitle_file", return_value=None),
        patch("shuku.cli.extract_subtitles") as mock_extract,
    ):
        mock_extract.return_value = str(tmp_path / "extracted.srt")
        result = find_subtitles(base_context)
    assert result == str(tmp_path / "extracted.srt")
    mock_extract.assert_called_once()


def test_find_subtitles_with_config_directory(base_context, tmp_path):
    base_context.args.subtitles = None
    base_context.config = {
        "external_subtitle_search": "enabled",
        "subtitle_directory": str(tmp_path),
    }
    base_context.file_path = str(tmp_path / "video.mp4")
    with patch("shuku.cli.find_matching_subtitle_file") as mock_find:
        mock_find.return_value = str(tmp_path / "found.srt")
        result = find_subtitles(base_context)
    assert result == str(tmp_path / "found.srt")
    mock_find.assert_called_once()


def test_find_subtitles_arg_priority_over_config(base_context, tmp_path):
    arg_dir = tmp_path / "arg_dir"
    arg_dir.mkdir()
    config_dir = tmp_path / "config_dir"
    config_dir.mkdir()
    # Update all relevant Context fields
    base_context.args.subtitles = str(arg_dir)
    base_context.config = {
        "external_subtitle_search": "enabled",
        "subtitle_directory": str(config_dir),
    }
    base_context.file_path = str(tmp_path / "video.mp4")
    base_context.basename = "video.mp4"
    base_context.input_name = "video"
    with patch("shuku.cli.find_matching_subtitle_file") as mock_find:
        mock_find.return_value = str(arg_dir / "found.srt")
        result = find_subtitles(base_context)
    assert result == str(arg_dir / "found.srt")
    mock_find.assert_called_once_with(base_context, str(arg_dir), "video")


def test_find_subtitles_fallback_to_video_directory(base_context, tmp_path):
    base_context.args.subtitles = None
    base_context.config = {
        "external_subtitle_search": "enabled",
        "subtitle_directory": None,
    }
    base_context.file_path = str(tmp_path / "video.mp4")
    base_context.basename = "video.mp4"
    base_context.input_name = "video"
    with patch("shuku.cli.find_matching_subtitle_file") as mock_find:
        mock_find.return_value = str(tmp_path / "found.srt")
        result = find_subtitles(base_context)
    assert result == str(tmp_path / "found.srt")
    mock_find.assert_called_once_with(base_context, str(tmp_path), "video")


def test_find_subtitles_no_subtitles_found(base_context, tmp_path):
    base_context.args.subtitles = None
    base_context.config = {"external_subtitle_search": "enabled"}
    base_context.file_path = str(tmp_path / "video.mp4")
    base_context.basename = "video.mp4"
    base_context.input_name = "video"
    with (
        patch("shuku.cli.find_matching_subtitle_file", return_value=None),
        patch("shuku.cli.extract_subtitles", return_value=None),
    ):
        result = find_subtitles(base_context)
    assert result is None


def test_find_subtitles_with_missing_external_file(base_context, caplog):
    base_context.file_path = "video.mp4"
    base_context.args.subtitles = "nonexistent_subtitles.srt"
    base_context.config["external_subtitle_search"] = "exact"
    with patch(
        "os.path.exists", side_effect=lambda path: path == base_context.file_path
    ):
        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                find_subtitles(base_context)


@pytest.fixture
def large_padding_subs():
    subtitle_content = """1
00:00:01,000 --> 00:00:03,000
First subtitle.

2
00:00:10,000 --> 00:00:12,000
Second subtitle after a large gap.
"""
    return pysubs2.SSAFile.from_string(subtitle_content)


def test_extract_speech_timing_from_subtitles_large_padding(
    base_context, large_padding_subs
):
    base_context.config["padding"] = 7
    base_context.config["line_skip_patterns"] = []
    base_context.file_path = "video.mp4"
    base_context.original_subtitle_format = "srt"
    result = extract_speech_timing_from_subtitles(base_context, large_padding_subs)
    assert len(result) == 1
    assert result == [(0.0, 19.0)]


@pytest.fixture
def mock_subtitle_file():
    return """1
00:00:01,000 --> 00:00:03,000
Hello, world!

2
00:00:04,000 --> 00:00:06,000
This is a test.

3
00:00:07,000 --> 00:00:09,000
♪ This is a song ♪

4
00:00:10,000 --> 00:00:12,000
Back to normal text.

5
00:00:13,000 --> 00:00:15,000
AB

6
00:00:16,000 --> 00:00:18,000
漢字

7
00:00:19,000 --> 00:00:21,000
A
"""


@pytest.fixture
def mock_subs(mock_subtitle_file):
    return pysubs2.SSAFile.from_string(mock_subtitle_file)


def test_filter_subtitles_skip_music(mock_subs):
    skip_patterns = [re.compile("^♪.*♪$")]
    filter_skip_patterns_in_place(mock_subs, skip_patterns)
    assert len(mock_subs) == 6
    expected_texts = [
        "Hello, world!",
        "This is a test.",
        "Back to normal text.",
        "AB",
        "漢字",
        "A",
    ]
    assert [sub.text for sub in mock_subs] == expected_texts
    expected_times = [
        (1000, 3000),
        (4000, 6000),
        (10000, 12000),
        (13000, 15000),
        (16000, 18000),
        (19000, 21000),
    ]
    assert [(sub.start, sub.end) for sub in mock_subs] == expected_times


def test_extract_speech_timing_from_subtitles(base_context, mock_subs):
    base_context.config["padding"] = 0.5
    base_context.original_subtitle_format = "srt"
    result = extract_speech_timing_from_subtitles(base_context, mock_subs)
    assert len(result) == 1
    assert result == [(0.5, 21.5)]


def test_extract_speech_timing_from_subtitles_no_skip_patterns(base_context, mock_subs):
    base_context.config["padding"] = 0.5
    base_context.config["line_skip_patterns"] = []
    base_context.original_subtitle_format = "srt"

    result = extract_speech_timing_from_subtitles(base_context, mock_subs)
    assert len(result) == 1
    assert result == [(0.5, 21.5)]


def test_skip_short_non_kanji_lines(mock_subs):
    skip_patterns = [
        re.compile(
            r"(?m)^[^\u4E00-\u9FFF]{1,3}$"
        ),  # Skips lines with 1-3 non-Kanji characters (e.g. "うん" or "OK").
    ]
    filter_skip_patterns_in_place(mock_subs, skip_patterns)
    assert len(mock_subs) == 5
    assert [sub.text for sub in mock_subs] == [
        "Hello, world!",
        "This is a test.",
        "♪ This is a song ♪",
        "Back to normal text.",
        "漢字",
    ]


def test_skip_music_and_short_non_kanji_lines(mock_subs):
    skip_patterns = [
        re.compile("^♪.*♪$"),
        re.compile(r"(?m)^[^\u4E00-\u9FFF]{1,3}$"),
    ]
    filter_skip_patterns_in_place(mock_subs, skip_patterns)
    assert len(mock_subs) == 4
    assert [sub.text for sub in mock_subs] == [
        "Hello, world!",
        "This is a test.",
        "Back to normal text.",
        "漢字",
    ]


def test_empty_subtitle_file():
    empty_subs = pysubs2.SSAFile()
    skip_patterns: list[re.Pattern] = []
    filter_skip_patterns_in_place(empty_subs, skip_patterns)
    assert len(empty_subs) == 0


def test_extract_speech_timing_from_subtitles_overlapping_segments(
    base_context, tmp_path
):
    subtitle_content = """1
00:00:01,000 --> 00:00:03,000
First subtitle.

2
00:00:02,500 --> 00:00:04,500
Overlapping subtitle.
"""
    subtitle_path = tmp_path / "test.srt"
    subtitle_path.write_text(subtitle_content)
    base_context.config["padding"] = 0.5
    base_context.config["line_skip_patterns"] = []
    base_context.temp_dir = str(tmp_path)
    subs = pysubs2.load(subtitle_path)
    result = extract_speech_timing_from_subtitles(base_context, subs)
    assert len(result) == 1
    assert result == [(0.5, 5.0)]


def test_create_concat_file():
    segment_files = ["segment1.ts", "segment2.ts", "segment3.ts"]
    temp_dir = "/tmp"
    expected_concat_file = "/tmp/concat.txt"
    expected_calls = [
        call("file 'segment1.ts'\n"),
        call("file 'segment2.ts'\n"),
        call("file 'segment3.ts'\n"),
    ]
    mock_open_file = mock_open()
    with (
        patch("shuku.cli.open", mock_open_file),
        patch("shuku.cli.os.path.join", return_value=expected_concat_file),
    ):
        result = create_concat_file(segment_files, temp_dir)
        assert result == expected_concat_file
        mock_open_file.assert_called_once_with(expected_concat_file, "w")
        file_handle = mock_open_file()
        file_handle.write.assert_has_calls(expected_calls)
        assert file_handle.write.call_count == len(segment_files)


def test_find_subtitles_external_subs(base_context):
    path_to_subtitles = "/path/to/subs.srt"
    base_context.args.subtitles = path_to_subtitles

    with (
        patch("shuku.cli.logging.info") as mock_log_info,
        patch("pathlib.Path.is_file", return_value=True),
    ):
        result = find_subtitles(base_context)
        assert result == path_to_subtitles
        mock_log_info.assert_called_once_with(
            f"Using provided subtitle file: {Path(path_to_subtitles)}"
        )


def test_find_subtitles_matching_file(base_context):
    base_context.file_path = "/path/to/video.mp4"
    base_context.input_name = "video"
    base_context.basename = "video.mp4"
    with (
        patch("shuku.cli.os.path.exists", side_effect=[True, True]),
        patch("shuku.cli.os.path.split", return_value=("/path/to", "video.mp4")),
        patch("shuku.cli.os.path.splitext", return_value=("video", ".mp4")),
        patch("shuku.cli.logging.debug") as mock_log_debug,
        patch("shuku.cli.extract_subtitles") as mock_extract,
    ):
        result = find_subtitles(base_context)
        assert result == "/path/to/video.srt"
        expected_log_messages = [
            "/path/to/video.srt",
        ]
        for message in expected_log_messages:
            assert any(message in call[0][0] for call in mock_log_debug.call_args_list)
        mock_extract.assert_not_called()


def test_find_subtitles_extract_from_video(base_context):
    with (
        patch("shuku.cli.os.path.exists", return_value=False),
        patch("shuku.cli.extract_subtitles") as mock_extract,
    ):
        expected_extracted_path = "/tmp/extracted_subs.srt"
        mock_extract.return_value = expected_extracted_path
        result = find_subtitles(base_context)
        assert result == expected_extracted_path
        mock_extract.assert_called_once_with(base_context)


def test_select_audio_stream_matching_language(base_context):
    base_context.config["audio_languages"] = ["jpn", "ja"]
    with patch("shuku.cli.logging.info") as mock_info:
        chosen_index = select_audio_stream(base_context)
    assert chosen_index == "1"
    mock_info.assert_called_with("Using audio stream: jpn")


def test_select_audio_stream_first_available(base_context):
    base_context.config = {}
    with patch(
        "shuku.cli.display_and_select_stream", return_value="0"
    ) as mock_display_and_select:
        chosen_index = select_audio_stream(base_context)
    assert chosen_index == "0"
    mock_display_and_select.assert_called_once_with(
        base_context.stream_info["audio"], "audio"
    )


def test_select_audio_stream_with_valid_audio_track_id(base_context):
    base_context.args.audio_track_id = 1
    chosen_index = select_audio_stream(base_context)
    assert chosen_index == "1"


def test_select_audio_stream_no_streams(base_context):
    base_context.stream_info["audio"] = []
    with pytest.raises(ValueError):
        select_audio_stream(base_context)


def test_get_all_stream_info_no_streams():
    file_path = "dummy_input.mp4"
    with patch.object(FFmpeg, "execute", return_value=json.dumps({"streams": []})):
        with pytest.raises(FileProcessingError) as exc_info:
            get_all_stream_info(file_path)
        assert "Error processing dummy_input.mp4" in str(exc_info.value)


def test_find_subtitles_prefer_external_false_extracted_subs(base_context):
    base_context.config["external_subtitle_search"] = "disabled"
    with patch("shuku.cli.extract_subtitles", return_value="/tmp/extracted_subs.srt"):
        result = find_subtitles(base_context)
        assert result == "/tmp/extracted_subs.srt"


def test_find_subtitles_external_search_disabled_no_extracted_subs_matching_external(
    base_context,
):
    base_context.config["external_subtitle_search"] = "disabled"
    with (
        patch("shuku.cli.extract_subtitles", return_value=None),
        patch(
            "shuku.cli.find_matching_subtitle_file",
            return_value="/path/to/matching_subs.srt",
        ),
    ):
        result = find_subtitles(base_context)
        assert result is None


def test_find_subtitles_prefer_external_false_no_extracted_subs_no_matching_external(
    base_context,
):
    base_context.config["external_subtitle_search"] = "disabled"
    with (
        patch("shuku.cli.extract_subtitles", return_value=None),
        patch("shuku.cli.find_matching_subtitle_file", return_value=None),
    ):
        result = find_subtitles(base_context)
        assert result is None


def test_find_subtitles_expands_user_directory(base_context, tmp_path):
    home_dir = tmp_path / "home" / "user"
    subs_dir = home_dir / "mysubs"
    subs_dir.mkdir(parents=True)
    sub_file = subs_dir / "input.srt"
    sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nTest subtitle\n")
    base_context.config["subtitle_directory"] = os.path.join("~", "mysubs")
    with patch("os.path.expanduser") as mock_expanduser:
        mock_expanduser.side_effect = lambda p: str(p).replace("~", str(home_dir))

        result = find_subtitles(base_context)
        assert str(sub_file) == result


def test_extract_subtitles_no_streams(base_context):
    base_context.stream_info["subtitle"] = []
    with pytest.raises(
        ValueError, match="No subtitle streams found in the input file."
    ):
        extract_subtitles(base_context)


def test_extract_subtitles_matching_language(base_context):
    base_context.config["subtitle_languages"] = ["eng", "jpn"]
    base_context.stream_info["subtitle"] = [
        {"index": 0, "tags": {"language": "eng"}, "codec_name": "subrip"},
        {"index": 1, "tags": {"language": "jpn"}, "codec_name": "subrip"},
    ]
    with (
        patch(
            "shuku.cli.extract_specific_subtitle",
            return_value="/tmp/extracted_subs.srt",
        ) as mock_extract,
        patch("shuku.cli.is_supported_subtitle_format", return_value=True),
    ):
        result = extract_subtitles(base_context)
        assert result == "/tmp/extracted_subs.srt"
        mock_extract.assert_called_with(base_context, 0)


def test_find_subtitles_expands_user_directory_cli_arg(base_context, tmp_path):
    """Test that tilde expansion works for CLI-provided subtitle path."""
    home_dir = tmp_path / "home" / "user"
    sub_file = home_dir / "input.srt"
    sub_file.parent.mkdir(parents=True)
    sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nTest subtitle\n")
    base_context.args.subtitles = os.path.join("~", "input.srt")
    with patch("os.path.expanduser") as mock_expanduser:
        mock_expanduser.side_effect = lambda p: str(p).replace("~", str(home_dir))
        result = find_subtitles(base_context)
        assert str(sub_file) == result


def test_find_subtitles_expands_user_directory_config_directory(base_context, tmp_path):
    home_dir = tmp_path / "home" / "user"
    subs_dir = home_dir / "mysubs"
    sub_file = subs_dir / "input.srt"
    sub_file.parent.mkdir(parents=True)
    sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nTest subtitle\n")
    base_context.config["subtitle_directory"] = os.path.join("~", "mysubs")
    with patch("os.path.expanduser") as mock_expanduser:
        mock_expanduser.side_effect = lambda p: str(p).replace("~", str(home_dir))
        result = find_subtitles(base_context)
        assert str(sub_file) == result


def test_extract_subtitles_no_matching_language(base_context):
    base_context.config["subtitle_languages"] = ["fra", "deu"]
    base_context.stream_info["subtitle"] = [
        {"index": 0, "tags": {"language": "eng"}, "codec_name": "subrip"},
        {"index": 1, "tags": {"language": "jpn"}, "codec_name": "subrip"},
    ]
    with (
        patch(
            "shuku.cli.extract_specific_subtitle",
            return_value="/tmp/extracted_subs.srt",
        ) as mock_extract,
        patch("shuku.cli.logging.warning") as mock_warning,
        patch(
            "shuku.cli.display_and_select_stream", return_value="0"
        ) as mock_display_and_select,
        patch("shuku.cli.is_supported_subtitle_format", return_value=True),
    ):
        result = extract_subtitles(base_context)
        assert result == "/tmp/extracted_subs.srt"
        mock_extract.assert_called_with(base_context, 0)
        mock_warning.assert_called_once_with(
            "No subtitles found for specified languages: fra, deu."
        )
        mock_display_and_select.assert_called_once_with(
            base_context.stream_info["subtitle"], "subtitle"
        )


def test_get_all_stream_info_subtitle_success():
    file_path = "dummy_input.mp4"
    expected_streams = [
        {"index": 0, "codec_type": "video", "tags": {"language": "eng"}},
        {"index": 1, "codec_type": "subtitle", "tags": {"language": "eng"}},
        {"index": 2, "codec_type": "subtitle", "tags": {"language": "jpn"}},
        {"index": 3, "codec_type": "audio", "tags": {"language": "eng"}},
    ]
    mock_data = {"streams": expected_streams}
    with patch.object(FFmpeg, "execute", return_value=json.dumps(mock_data)):
        result = get_all_stream_info(file_path)
        assert result["subtitle"] == [
            {"index": 1, "codec_type": "subtitle", "tags": {"language": "eng"}},
            {"index": 2, "codec_type": "subtitle", "tags": {"language": "jpn"}},
        ]
        assert "audio" in result
        assert "video" in result


def test_get_all_stream_info_no_subtitle_streams():
    file_path = "dummy_input.mp4"
    expected_streams = [
        {"index": 0, "codec_type": "video", "tags": {"language": "eng"}},
        {"index": 1, "codec_type": "audio", "tags": {"language": "eng"}},
    ]
    mock_data = {"streams": expected_streams}
    with patch.object(FFmpeg, "execute", return_value=json.dumps(mock_data)):
        result = get_all_stream_info(file_path)
        assert result["subtitle"] == []
        assert "audio" in result
        assert "video" in result


def test_merge_overlapping_segments_empty_input():
    segments: list[tuple[float, float]] = []
    expected_output: list[tuple[float, float]] = []
    assert merge_overlapping_segments(segments) == expected_output


def test_merge_overlapping_segments_non_overlapping():
    segments: list[tuple[float, float]] = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    expected_output: list[tuple[float, float]] = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    assert merge_overlapping_segments(segments) == expected_output


def test_merge_overlapping_segments_overlapping():
    segments: list[tuple[float, float]] = [
        (1.0, 3.0),
        (2.0, 4.0),
        (5.0, 7.0),
        (6.0, 8.0),
    ]
    expected_output: list[tuple[float, float]] = [(1.0, 4.0), (5.0, 8.0)]
    assert merge_overlapping_segments(segments) == expected_output


def test_merge_overlapping_segments_multiple_overlapping():
    segments: list[tuple[float, float]] = [
        (1.0, 4.0),
        (2.0, 5.0),
        (3.0, 6.0),
        (7.0, 9.0),
        (8.0, 10.0),
    ]
    expected_output: list[tuple[float, float]] = [(1.0, 6.0), (7.0, 10.0)]
    assert merge_overlapping_segments(segments) == expected_output


def test_safe_move_prompts_user_when_file_exists(base_context, tmpdir, monkeypatch):
    source = tmpdir.join("source.txt")
    source.write("test content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.config["if_file_exists"] = "overwrite"
    base_context.temp_dir = str(tmpdir)
    # Mock user input to simulate 'o' for "Overwrite".
    monkeypatch.setattr("builtins.input", lambda _: "o")
    safe_move(base_context, str(source), str(destination))
    assert not source.exists()
    assert destination.exists()
    assert destination.read() == "test content"


def test_safe_move_overwrites_when_config_overwrite(base_context, tmpdir):
    source = tmpdir.join("source.txt")
    source.write("test content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.config["if_file_exists"] = "overwrite"
    base_context.temp_dir = str(tmpdir)
    safe_move(base_context, str(source), str(destination))
    assert not source.exists()
    assert destination.exists()
    assert destination.read() == "test content"


@patch("shuku.cli.logging.info")
def test_safe_move_logs_skip(mock_log, base_context, tmpdir):
    source = tmpdir.join("source.txt")
    source.write("new content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.config["if_file_exists"] = "skip"
    base_context.temp_dir = str(tmpdir)
    safe_move(base_context, str(source), str(destination))
    assert "Skipping existing file" in mock_log.call_args[0][0]
    assert str(destination) in mock_log.call_args[0][0]


@patch("shuku.cli.logging.info")
def test_safe_move_logs_renaming(mock_log, base_context, tmpdir):
    source = tmpdir.join("source.txt")
    source.write("new content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.config["if_file_exists"] = "rename"
    base_context.temp_dir = str(tmpdir)
    result = safe_move(base_context, str(source), str(destination))
    assert "Renaming file" in mock_log.call_args[0][0]
    assert result in mock_log.call_args[0][0]


@patch("builtins.input", side_effect=["x", "r"])
@patch("builtins.print")
def test_prompt_user_choice_invalid_selection(mock_print, mock_input):
    choices = ["rename", "overwrite", "skip"]
    default = "skip"
    result = prompt_user_choice("What do you want to do?", choices, default)
    assert mock_print.call_args_list[0][0][0].startswith("Invalid selection")
    assert result == "rename"


@patch("builtins.input", side_effect=[""])
def test_prompt_user_choice_return_default(mock_input):
    choices = ["rename", "overwrite", "skip"]
    default = "skip"
    result = prompt_user_choice("What do you want to do?", choices, default)
    assert result == "skip"


def test_safe_move_renaming_behavior(base_context, tmpdir, monkeypatch):
    source = tmpdir.join("source.txt")
    source.write("new content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.temp_dir = str(tmpdir)
    monkeypatch.setattr("builtins.input", lambda _: "r")  # Rename
    result1 = safe_move(base_context, str(source), str(destination))
    assert not source.exists()
    assert destination.exists()
    assert destination.read() == "old content"
    assert os.path.exists(result1)
    assert open(result1).read() == "new content"
    assert str(datetime.now().year) in result1
    assert result1.startswith(str(tmpdir.join("destination_")))
    assert result1.endswith(".txt")
    time.sleep(1)  # Ensure different timestamps.
    source = tmpdir.join("source2.txt")
    source.write("newer content")
    result2 = safe_move(base_context, str(source), str(destination))
    assert not source.exists()
    assert destination.exists()
    assert destination.read() == "old content"
    assert os.path.exists(result1)
    assert open(result1).read() == "new content"
    assert os.path.exists(result2)
    assert open(result2).read() == "newer content"
    assert str(datetime.now().year) in result2
    assert result2.startswith(str(tmpdir.join("destination_")))
    assert result2.endswith(".txt")
    assert result1 != result2


def test_safe_move_skip_behavior(base_context, tmpdir, monkeypatch):
    source = tmpdir.join("source.txt")
    source.write("new content")
    destination = tmpdir.join("destination.txt")
    destination.write("old content")
    base_context.temp_dir = str(tmpdir)
    monkeypatch.setattr("builtins.input", lambda _: "s")  # Skip
    result = safe_move(base_context, str(source), str(destination))
    assert source.exists()
    assert source.read() == "new content"
    assert destination.exists()
    assert destination.read() == "old content"
    assert result == ""


def test_safe_move_non_existent_destination(base_context, tmpdir):
    source = tmpdir.join("source.txt")
    source.write("content")
    destination = tmpdir.join("non_existent.txt")
    base_context.config["if_file_exists"] = "overwrite"
    base_context.temp_dir = str(tmpdir)
    result = safe_move(base_context, str(source), str(destination))
    assert not source.exists()
    assert destination.exists()
    assert destination.read() == "content"
    assert result == str(destination)


@pytest.mark.parametrize(
    "user_input,expected_output",
    [
        ("", "0"),  # First stream selected by default (0-based index).
        ("0", "0"),  # Explicitly select first stream.
        ("1", "1"),  # Select second stream.
        ("2", "2"),  # Select third stream.
        ("2\n", "2"),  # Select third stream with newline.
    ],
)
def test_display_and_select_stream(user_input: str, expected_output: str, caplog):
    caplog.set_level(logging.INFO)
    streams = [
        {
            "index": 0,
            "tags": {"language": "eng", "title": "English"},
            "codec_name": "aac",
        },
        {
            "index": 1,
            "tags": {"language": "spa", "title": "Spanish"},
            "codec_name": "aac",
        },
        {
            "index": 2,
            "tags": {"language": "fra", "title": "French"},
            "codec_name": "aac",
        },
    ]
    output = StringIO()
    input_mock = patch("builtins.input", return_value=user_input)
    with patch("sys.stdout", new=output), input_mock:
        result = display_and_select_stream(streams, "audio")
    assert result == expected_output
    output_str = output.getvalue()
    for stream in streams:
        assert (
            f"[{stream['index']}] Language: {stream['tags']['language']}" in output_str
        )
        assert f"Title: {stream['tags']['title']}" in output_str
        assert f"Codec: {stream['codec_name']}" in output_str
    assert "Available audio streams" in output_str
    selected_stream = next(s for s in streams if str(s["index"]) == expected_output)
    expected_log = f"Selected audio stream: [{selected_stream['index']}] Language: {selected_stream['tags']['language']} | Title: {selected_stream['tags']['title']} | Codec: {selected_stream['codec_name']}"
    assert expected_log in caplog.text


@pytest.fixture
def mock_file_structure(tmp_path):
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    dir2 = tmp_path / "dir2"
    dir2.mkdir()
    file1 = dir1 / "file1.txt"
    file1.write_text("content")
    file2 = dir2 / "file2.txt"
    file2.write_text("content")
    return tmp_path


def test_get_input_files_single_file(mock_file_structure):
    file_path = str(mock_file_structure / "dir1" / "file1.txt")
    result = get_input_files([file_path])
    assert result == [file_path]


def test_get_input_files_multiple_files(mock_file_structure):
    file1 = str(mock_file_structure / "dir1" / "file1.txt")
    file2 = str(mock_file_structure / "dir2" / "file2.txt")
    result = get_input_files([file1, file2])
    assert set(result) == {file1, file2}


def test_get_input_files_directory(mock_file_structure):
    dir_path = str(mock_file_structure / "dir1")
    result = get_input_files([dir_path])
    expected = [str(mock_file_structure / "dir1" / "file1.txt")]
    assert result == expected


def test_get_input_files_mixed_input(mock_file_structure):
    file_path = str(mock_file_structure / "dir1" / "file1.txt")
    dir_path = str(mock_file_structure / "dir2")
    result = get_input_files([file_path, dir_path])
    expected = [
        str(mock_file_structure / "dir1" / "file1.txt"),
        str(mock_file_structure / "dir2" / "file2.txt"),
    ]
    assert set(result) == set(expected)


def test_get_input_files_nonexistent_file(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit) as exc_info:
            get_input_files(["nonexistent.txt"])
    assert exc_info.value.code == 1
    assert "Invalid input" in caplog.text
    assert "nonexistent.txt" in caplog.text
    assert "No valid files found. Exiting." in caplog.text


def test_get_input_files_nonexistent_directory(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit) as exc_info:
            get_input_files(["nonexistent_dir"])
    assert exc_info.value.code == 1
    assert "Invalid input" in caplog.text
    assert "nonexistent_dir" in caplog.text
    assert "No valid files found. Exiting." in caplog.text


def test_get_input_files_empty_input():
    with pytest.raises(SystemExit) as exc_info:
        get_input_files([])
    assert exc_info.value.code == 1


def test_get_input_files_all_invalid_inputs(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit) as exc_info:
            get_input_files(["nonexistent1.txt", "nonexistent2.txt"])
    assert exc_info.value.code == 1
    assert "Invalid input" in caplog.text
    assert "Invalid input" in caplog.text
    assert "nonexistent1.txt" in caplog.text
    assert "nonexistent2.txt" in caplog.text
    assert "No valid files found. Exiting." in caplog.text


@pytest.mark.parametrize(
    "file_path",
    [
        "/dev/null" if sys.platform != "win32" else "NUL",
    ],
)
def test_get_input_files_special_files(file_path, caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit) as exc_info:
            get_input_files([file_path])
    assert exc_info.value.code == 1
    assert "Invalid input" in caplog.text
    assert file_path in caplog.text
    assert "No valid files found" in caplog.text


def test_get_input_files_symlink(tmp_path):
    real_file = tmp_path / "real_file.txt"
    real_file.write_text("content")
    symlink = tmp_path / "symlink.txt"
    os.symlink(str(real_file), str(symlink))
    result = get_input_files([str(symlink)])
    assert result == [str(symlink)]


def test_get_input_files_permission_denied(tmp_path, monkeypatch):
    file_path = tmp_path / "no_permission.txt"
    file_path.write_text("content")

    def mock_exists(path):
        return True

    def mock_isfile(path):
        return True

    monkeypatch.setattr(os.path, "exists", mock_exists)
    monkeypatch.setattr(os.path, "isfile", mock_isfile)

    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = PermissionError("Permission denied")
        result = get_input_files([str(file_path)])
    assert result == [str(file_path)]


def test_get_input_files_very_long_path(tmp_path):
    long_dir = tmp_path / ("a" * 200)
    long_dir.mkdir()
    long_file = long_dir / ("b" * 200)
    long_file.write_text("content")
    result = get_input_files([str(long_dir)])
    assert result == [str(long_file)]


def test_get_input_files_unicode_path(tmp_path):
    unicode_dir = tmp_path / "πΈπ₯°π"
    unicode_dir.mkdir()
    unicode_file = unicode_dir / "γγγ«γ'γ―.txt"
    unicode_file.write_text("content")
    result = get_input_files([str(unicode_dir)])
    assert result == [str(unicode_file)]


MOCK_AUDIO_STREAMS = [
    {"index": 0, "tags": {"language": "eng"}, "codec_name": "aac"},
    {"index": 1, "tags": {"language": "spa"}, "codec_name": "mp3"},
]

MOCK_SUBTITLE_STREAMS = [
    {"index": 0, "tags": {"language": "eng"}, "codec_name": "subrip"},
    {"index": 1, "tags": {"language": "spa"}, "codec_name": "ass"},
    {"index": 2, "tags": {"language": "fre"}, "codec_name": "dvd_subtitle"},
]


@pytest.mark.parametrize(
    "stream_type,streams,expected",
    [
        ("audio", MOCK_AUDIO_STREAMS, "0"),
        ("subtitle", MOCK_SUBTITLE_STREAMS, "0"),
    ],
)
def test_select_first_stream(stream_type, streams, expected):
    with patch("builtins.input", return_value=""):
        result = display_and_select_stream(streams, stream_type)
    assert result == expected


@pytest.mark.parametrize(
    "stream_type,streams,user_input,expected",
    [
        ("audio", MOCK_AUDIO_STREAMS, "1", "1"),
        ("subtitle", MOCK_SUBTITLE_STREAMS, "1", "1"),
    ],
)
def test_select_specific_stream(stream_type, streams, user_input, expected):
    with patch("builtins.input", return_value=user_input):
        result = display_and_select_stream(streams, stream_type)
    assert result == expected


def test_invalid_then_valid_selection():
    with patch("builtins.input", side_effect=["3", "0"]):
        result = display_and_select_stream(MOCK_AUDIO_STREAMS, "audio")
    assert result == "0"


def test_non_numeric_then_valid_selection():
    with patch("builtins.input", side_effect=["abc", "1"]):
        result = display_and_select_stream(MOCK_AUDIO_STREAMS, "audio")
    assert result == "1"


def test_unsupported_subtitle_format():
    unsupported_streams = MOCK_SUBTITLE_STREAMS + [
        {"index": 3, "tags": {"language": "ger"}, "codec_name": "unsupported_format"}
    ]
    with patch("builtins.input", return_value=""):
        result = display_and_select_stream(unsupported_streams, "subtitle")
    assert result == "0"  # Should select the first supported format


def test_extract_subtitles_no_supported_streams(base_context):
    base_context.args.sub_track_id = None
    base_context.stream_info["subtitle"] = [
        {"index": 0, "tags": {"language": "eng"}, "codec_name": "unsupported_codec"},
        {"index": 1, "tags": {"language": "jpn"}, "codec_name": "another_unsupported"},
    ]
    with (
        patch("shuku.cli.is_supported_subtitle_format", return_value=False),
        pytest.raises(ValueError, match="No supported subtitle streams found."),
    ):
        extract_subtitles(base_context)


@pytest.mark.parametrize(
    "stream_type,streams",
    [
        ("audio", MOCK_AUDIO_STREAMS),
        ("subtitle", MOCK_SUBTITLE_STREAMS),
    ],
)
def test_display_streams(stream_type, streams, capsys):
    with patch("builtins.input", return_value=""):
        display_and_select_stream(streams, stream_type)
    captured = capsys.readouterr()
    for stream in streams:
        assert str(stream["index"]) in captured.out
        assert stream["tags"]["language"] in captured.out
        assert stream["codec_name"] in captured.out


def test_select_first_supported_stream():
    supported_streams = [
        {"index": 1, "tags": {"language": "spa"}, "codec_name": "subrip"},
        {"index": 2, "tags": {"language": "fre"}, "codec_name": "ass"},
    ]
    with patch("builtins.input", return_value=""):
        result = display_and_select_stream(supported_streams, "subtitle")
    assert result == "1"


def test_display_only_supported_streams(capsys):
    supported_streams = [
        {"index": 1, "tags": {"language": "spa"}, "codec_name": "subrip"},
        {"index": 3, "tags": {"language": "ger"}, "codec_name": "ass"},
    ]
    with patch("builtins.input", return_value=""):
        display_and_select_stream(supported_streams, "subtitle")
    captured = capsys.readouterr()
    assert "Available subtitle streams:" in captured.out
    assert "spa" in captured.out and "subrip" in captured.out
    assert "ger" in captured.out and "ass" in captured.out
    assert "Unsupported subtitle streams:" not in captured.out


def test_ffmpeg_exception_handling(monkeypatch, caplog):
    mock_ffmpeg = MagicMock()
    mock_ffmpeg().option().execute.side_effect = Exception("Mocked exception")
    with patch("sys.exit") as mock_exit:
        with patch("shuku.cli.FFmpeg", mock_ffmpeg):
            with caplog.at_level(logging.ERROR):
                verify_ffmpeg_and_ffprobe_availability()
                assert "ffmpeg not found or not working properly" in caplog.text
                assert "ffprobe not found or not working properly" in caplog.text
                assert mock_exit.called
                mock_exit.assert_any_call(1)


def test_ffmpeg_and_ffprobe_available(caplog):
    mock_ffmpeg = MagicMock()
    mock_ffmpeg().option().execute.return_value = b"ffmpeg version 4.2.1"
    with patch("shuku.cli.FFmpeg", mock_ffmpeg):
        with caplog.at_level(logging.DEBUG):
            verify_ffmpeg_and_ffprobe_availability()
            assert "ffmpeg version: 4.2.1" in caplog.text
            assert "ffprobe version: 4.2.1" in caplog.text
            assert "not found or not working properly" not in caplog.text


def test_extract_speech_timing_discards_zero_length_segments(sample_subs, base_context):
    base_context.args.sub_delay = -300000
    base_context.config["padding"] = 0
    segments = extract_speech_timing_from_subtitles(base_context, sample_subs)
    assert segments == [], "Zero-duration segments should be discarded"


def test_create_condensed_subtitles_positive_delay(tmp_path, sample_subs, base_context):
    # Original subs: 1-2s, 3-4s.
    # With +1s delay: 2-3s, 4-5s (for segment extraction).
    # Expected condensed output: 0-1s, 1-2s (as if subs were originally correct).
    base_context.args.sub_delay = 1000
    base_context.config["padding"] = 0
    speech_segments = extract_speech_timing_from_subtitles(base_context, sample_subs)
    create_condensed_subtitles(base_context, sample_subs, speech_segments)
    output_path = tmp_path / "input (condensed).srt"
    assert output_path.exists(), "Output file was not created"
    output_subs = pysubs2.load(str(output_path))
    assert len(output_subs) == 2, "Expected 2 subtitle events"
    assert output_subs[0].start == 0, "First subtitle should start at beginning"
    assert output_subs[0].end == 1000, "First subtitle should be 1s long"
    assert (
        output_subs[1].start == 1000
    ), "Second subtitle should start right after first"
    assert output_subs[1].end == 2000, "Second subtitle should be 1s long"
    assert output_subs[0].text == "First subtitle"
    assert output_subs[1].text == "Second subtitle"


def test_extract_speech_timing_prevents_negative_times(base_context):
    subs = pysubs2.SSAFile.from_string("""
1
00:00:00.500 --> 00:00:01.000
First line

2
00:00:02.000 --> 00:00:02.500
Second line

3
00:00:04.000 --> 00:00:05.000
Later line""")
    base_context.args.sub_delay = -2000
    base_context.config["padding"] = 0
    segments = extract_speech_timing_from_subtitles(base_context, subs)
    # Original times after -2s delay:
    # - 0.5-1.0s becomes -1.5 to -1.0 -> clamps to 0,0
    # - 2.0-2.5s becomes 0.0 to 0.5
    # These merge because they're contiguous starting at 0
    # - 4.0-5.0s becomes 2.0-3.0
    expected_segments = [
        (0.0, 0.5),  # First two segments merged.
        (2.0, 3.0),  # Third segment fully positive after shift.
    ]
    assert (
        segments == expected_segments
    ), "Segments weren't correctly handled when delay caused negative times"


@pytest.fixture
def sample_subs():
    return pysubs2.SSAFile.from_string("""1
00:00:01,000 --> 00:00:02,000
First subtitle

2
00:00:03,000 --> 00:00:04,000
Second subtitle
""")


def test_create_condensed_subtitles_negative_delay(tmp_path, sample_subs, base_context):
    # Original subs: 1-2s, 3-4s.
    # With -0.5s delay: 0.5-1.5s, 2.5-3.5s (for segment extraction).
    base_context.args.sub_delay = -0.5
    base_context.config["padding"] = 0
    speech_segments = extract_speech_timing_from_subtitles(base_context, sample_subs)
    create_condensed_subtitles(base_context, sample_subs, speech_segments)
    output_path = tmp_path / "input (condensed).srt"
    assert output_path.exists(), "Output file was not created"
    output_subs = pysubs2.load(str(output_path))
    assert len(output_subs) == 2, "Expected 2 subtitle events"
    assert output_subs[0].start == 0, "First subtitle should start at beginning"
    assert output_subs[0].end == 1000, "First subtitle should be 1s long"
    assert (
        output_subs[1].start == 1000
    ), "Second subtitle should start right after first"
    assert output_subs[1].end == 2000, "Second subtitle should be 1s long"
    assert output_subs[0].text == "First subtitle"
    assert output_subs[1].text == "Second subtitle"


@pytest.fixture
def mock_stream_info():
    return {
        "subtitle": [
            {
                "index": 0,
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "eng"},
            }
        ]
    }


@patch("shuku.cli.extract_specific_subtitle")
@patch("shuku.cli.is_supported_subtitle_format")
@patch("shuku.cli.display_and_select_stream")
def test_extract_subtitles_single_unsupported_stream(
    mock_display_select,
    mock_is_supported,
    mock_extract_specific,
    base_context,
    mock_stream_info,
):
    base_context.stream_info = mock_stream_info
    mock_is_supported.return_value = False
    with pytest.raises(ValueError, match="No supported subtitle streams found"):
        extract_subtitles(base_context)
    mock_extract_specific.assert_not_called()
    mock_display_select.assert_not_called()


@patch("shuku.cli.extract_specific_subtitle")
@patch("shuku.cli.is_supported_subtitle_format")
def test_extract_subtitles_single_supported_stream(
    mock_is_supported, mock_extract_specific, base_context, mock_stream_info
):
    base_context.stream_info = mock_stream_info
    mock_is_supported.return_value = True
    mock_extract_specific.return_value = (
        f"{base_context.temp_dir}/extracted_subtitle.srt"
    )
    result = extract_subtitles(base_context)
    assert result == f"{base_context.temp_dir}/extracted_subtitle.srt"
    mock_extract_specific.assert_called_once_with(base_context, 0)


def test_extract_subtitles_user_specified_invalid_track(base_context):
    base_context.args.sub_track_id = 2
    base_context.stream_info["subtitle"] = [
        {"index": 0, "tags": {"language": "eng"}, "codec_name": "subrip"},
        {"index": 1, "tags": {"language": "jpn"}, "codec_name": "subrip"},
    ]
    with pytest.raises(ValueError, match="Specified subtitle stream 2 not found."):
        extract_subtitles(base_context)


def test_basic_lrc_conversion():
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=1000, end=2000, text="Test subtitle"))
    lrc_content = convert_to_lrc(subs, "test.srt")
    assert "[00:01.00]Test subtitle" in lrc_content


def test_lrc_ends_with_newline():
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=1000, end=2000, text="Test subtitle"))
    lrc_content = convert_to_lrc(subs, "test.srt")
    assert lrc_content.endswith("\n")


def test_lrc_metadata():
    subs = pysubs2.SSAFile()
    lrc_content = convert_to_lrc(subs, "test.srt")
    assert "[ti:test.srt]" in lrc_content
    assert "[tool:" in lrc_content
    assert "[ve:" in lrc_content
    assert "[by:" in lrc_content


@pytest.mark.parametrize(
    "styled_text, expected_output",
    [
        ("{\\i1}Italic{\\i0}", "Italic"),
        ("{\\b1}Bold{\\b0}", "Bold"),
        ("{\\u1}Underline{\\u0}", "Underline"),
        ("{\\s1}Strikeout{\\s0}", "Strikeout"),
        ("{\\fn Arial}Font{\\fn}", "Font"),
        ("{\\fs20}Size{\\fs}", "Size"),
        ("{\\c&H0000FF&}Color{\\c}", "Color"),
        ("{\\i1\\b1}Multiple{\\b0\\i0}", "Multiple"),
        ("No styling", "No styling"),
        ("{\\an8}Alignment", "Alignment"),
    ],
)
def test_strip_subtitle_styles_parametrized(styled_text, expected_output):
    assert strip_subtitle_styles(styled_text) == expected_output


def test_strip_subtitle_styles_with_newlines():
    styled_text = "Line 1\\N{\\i1}Line 2{\\i0}\\NLine 3"
    expected_output = "Line 1 Line 2 Line 3"
    assert strip_subtitle_styles(styled_text) == expected_output


def create_sample_srt(tmp_path, content):
    input_path = tmp_path / "input.srt"
    input_path.write_text(content)
    return str(input_path)


@pytest.fixture
def mock_subtitle_context():
    return Context(
        file_path="/path/to/video.mkv",
        config={},
        args=MagicMock(),
        temp_dir="/tmp",
        metadata={},
        input_name="video",
        basename="video",
        clean_name="video",
        stream_info={
            "subtitle": [
                {"index": 0, "codec_name": "subrip"},
                {"index": 1, "codec_name": "ass"},
                {"index": 2, "codec_name": "hdmv_pgs_subtitle"},
            ]
        },
    )


@pytest.mark.parametrize(
    "stream_index,codec_name,expected_format",
    [
        (0, "subrip", "srt"),
        (1, "ass", "ass"),
        (2, "hdmv_pgs_subtitle", "sup"),
    ],
)
def test_extract_specific_subtitle_success(
    mock_subtitle_context, stream_index, codec_name, expected_format
):
    with patch("shuku.cli.FFmpeg") as mock_ffmpeg:
        mock_ffmpeg_instance = MagicMock()
        mock_ffmpeg.return_value.option.return_value.input.return_value.output.return_value = mock_ffmpeg_instance
        result = extract_specific_subtitle(mock_subtitle_context, stream_index)
        assert result == f"/tmp/subtitles_{stream_index}.{expected_format}"
        mock_ffmpeg_instance.execute.assert_called_once()


def test_extract_specific_subtitle_invalid_index(mock_subtitle_context):
    with pytest.raises(ValueError) as exc_info:
        extract_specific_subtitle(mock_subtitle_context, 3)
    assert str(exc_info.value) == "Stream with index 3 not found in stream_info."


def test_extract_specific_subtitle_unsupported_codec(mock_subtitle_context):
    unsupported_codec = "unsupported_codec"
    mock_subtitle_context.stream_info["subtitle"][0]["codec_name"] = unsupported_codec
    with patch("shuku.cli.FFmpeg") as mock_ffmpeg:
        mock_ffmpeg_instance = MagicMock()
        mock_ffmpeg.return_value.option.return_value.input.return_value.output.return_value = mock_ffmpeg_instance
        result = extract_specific_subtitle(mock_subtitle_context, 0)
        assert result == f"/tmp/subtitles_0.{unsupported_codec}"
        mock_ffmpeg_instance.execute.assert_called_once()


@pytest.fixture
def sample_streams():
    return [
        {
            "tags": {
                "language": "eng",
                "title": "English",
                "forced": "0",
                "default": "1",
            },
            "index": 0,
        },
        {
            "tags": {
                "language": "eng",
                "title": "English (SDH)",
                "forced": "0",
                "default": "0",
            },
            "index": 1,
        },
        {
            "tags": {
                "language": "spa",
                "title": "Español",
                "forced": "0",
                "default": "0",
            },
            "index": 2,
        },
        {
            "tags": {
                "language": "fre",
                "title": "Français (Forced)",
                "forced": "1",
                "default": "0",
            },
            "index": 3,
        },
        {
            "tags": {
                "language": "jpn",
                "title": "Japanese (Signs & Songs)",
                "forced": "0",
                "default": "0",
            },
            "index": 4,
        },
    ]


def test_sort_subtitle_streams_preferred_language():
    streams = [
        {"tags": {"language": "eng", "title": "English"}},
        {"tags": {"language": "spa", "title": "Español"}},
    ]
    preferred_languages = ["spa", "eng"]
    sorted_streams = sort_subtitle_streams(streams, preferred_languages)
    assert sorted_streams[0]["tags"]["language"] == "spa"
    assert sorted_streams[1]["tags"]["language"] == "eng"


def test_sort_subtitle_streams_forced_subtitles():
    streams = [
        {"tags": {"language": "eng", "title": "English", "forced": "0"}},
        {"tags": {"language": "eng", "title": "English (Forced)", "forced": "1"}},
    ]
    sorted_streams = sort_subtitle_streams(streams, ["eng"])
    assert sorted_streams[0]["tags"]["forced"] == "1"
    assert sorted_streams[1]["tags"]["forced"] == "0"


def test_sort_subtitle_streams_penalized_keywords(sample_streams):
    sorted_streams = sort_subtitle_streams(sample_streams, ["eng"])
    assert sorted_streams[0]["tags"]["title"] == "English"
    assert sorted_streams[1]["tags"]["title"] == "English (SDH)"
    assert sorted_streams[-1]["tags"]["title"] == "Japanese (Signs & Songs)"


def test_sort_subtitle_streams_multiple_criteria(sample_streams):
    preferred_languages = ["eng", "spa", "fre", "jpn"]
    sorted_streams = sort_subtitle_streams(sample_streams, preferred_languages)
    assert sorted_streams[0]["tags"]["title"] == "English"
    assert sorted_streams[1]["tags"]["title"] == "English (SDH)"
    assert sorted_streams[2]["tags"]["title"] == "Español"
    assert sorted_streams[3]["tags"]["title"] == "Français (Forced)"
    assert sorted_streams[4]["tags"]["title"] == "Japanese (Signs & Songs)"


def test_sort_subtitle_streams_no_preferred_languages(sample_streams):
    sorted_streams = sort_subtitle_streams(sample_streams, [])
    assert len(sorted_streams) == len(sample_streams)
    # Should sort even without language preference.
    assert sorted_streams != sample_streams


@pytest.mark.parametrize("keyword", PENALIZED_SUBTITLE_KEYWORDS)
def test_sort_subtitle_streams_individual_penalties(keyword):
    streams = [
        {"tags": {"language": "eng", "title": f"English with {keyword}"}},
        {"tags": {"language": "eng", "title": "English without penalty"}},
    ]
    sorted_streams = sort_subtitle_streams(streams, ["eng"])
    assert sorted_streams[0]["tags"]["title"] == "English without penalty"
    assert sorted_streams[1]["tags"]["title"] == f"English with {keyword}"


def test_extract_subtitles_logs_sorting(base_context, sample_streams, caplog):
    base_context.config["subtitle_languages"] = ["spa", "eng"]
    base_context.args.sub_track_id = None
    base_context.stream_info["subtitle"] = sample_streams
    with (
        patch("shuku.cli.is_supported_subtitle_format", return_value=True),
        patch("shuku.cli.extract_specific_subtitle", return_value="/tmp/subtitles.srt"),
        caplog.at_level(logging.DEBUG),
    ):
        extract_subtitles(base_context)
        assert "Streams have been sorted" in caplog.text


def test_extract_subtitles_with_specified_track(base_context, caplog):
    base_context.args.sub_track_id = 1
    base_context.stream_info["subtitle"] = [
        {"index": 0, "codec_name": "subrip"},
        {"index": 1, "codec_name": "ass"},
        {"index": 2, "codec_name": "hdmv_pgs_subtitle"},
    ]
    expected_subtitle_path = "/tmp/subtitles_1.ass"
    with (
        patch(
            "shuku.cli.extract_specific_subtitle", return_value=expected_subtitle_path
        ) as mock_extract,
        caplog.at_level(logging.INFO),
    ):
        result = extract_subtitles(base_context)
        assert (
            f"Using specified subtitle stream: {base_context.args.sub_track_id}"
            in caplog.text
        )
        mock_extract.assert_called_once_with(
            base_context, base_context.args.sub_track_id
        )
        assert result == expected_subtitle_path


def test_find_matching_subtitle_file_integration(base_context):
    base_context.config = {
        "external_subtitle_search": "fuzzy",
        "subtitle_match_threshold": 0.8,
    }
    with (
        patch("os.path.exists") as mock_exists,
        patch("os.listdir") as mock_listdir,
        patch("shuku.cli.clean_filename") as mock_clean,
        patch("shuku.cli.character_based_similarity") as mock_similarity,
    ):
        mock_exists.return_value = False
        mock_listdir.return_value = ["video_similar.srt", "unrelated.srt"]
        mock_clean.side_effect = lambda x: x.split(".")[0]
        mock_similarity.side_effect = [0.85, 0.3]
        result = find_matching_subtitle_file(base_context, "/path/to", "video")
        assert result == "/path/to/video_similar.srt"


def test_generate_output_path_with_clean_output_filename(tmp_path):
    messy_filename = "[OBEY-Me] Show S01E01 (BD 1920x1080 x264 FLAC).mkv"
    context = Context.create(
        file_path=str(tmp_path / messy_filename),
        config={"clean_output_filename": True, "output_suffix": "_condensed"},
        args=argparse.Namespace(output=None),
        temp_dir=str(tmp_path),
    )

    result = generate_output_path(context, "mp3")
    expected = str(tmp_path / "Show S01E01_condensed.mp3")
    assert result == expected


def test_generate_output_path_without_clean_output_filename(tmp_path):
    messy_filename = "[OBEY-Me] Show S01E01 (BD 1920x1080 x264 FLAC).mkv"
    context = Context.create(
        file_path=str(tmp_path / messy_filename),
        config={"clean_output_filename": False, "output_suffix": "_condensed"},
        args=argparse.Namespace(output=None),
        temp_dir=str(tmp_path),
    )
    result = generate_output_path(context, "mp3")
    expected = str(
        tmp_path / "[OBEY-Me] Show S01E01 (BD 1920x1080 x264 FLAC)_condensed.mp3"
    )
    assert result == expected


@pytest.mark.parametrize(
    "input_filename, expected_output",
    [
        (
            "1984.George.Orwell.Adaptation.2024.mkv",
            "george orwell adaptation 1984 2024",
        ),
        (
            "Movie.2020.1080p.BluRay.x264-GROUP.mkv",
            "movie bluray 2020",
        ),
        (
            "2019.Great.Movie.BluRay.1080p.x264.mkv",
            "great movie bluray 2019",
        ),
        (
            "Old_Movie_1950_Remastered_2023.mp4",
            "old movie remastered 1950 2023",
        ),
        (
            "Movie.Without.Year.1080p.BluRay.x264-GROUP.mkv",
            "movie without year bluray",
        ),
        (
            "Movie (2022) [1080p].mkv",
            "movie 2022",
        ),
        (
            "TV.Show.S01E01.2021.720p.WEB-DL.x264.mkv",
            "tv show s01e01 web-dl 2021",
        ),
        (
            "Documentary.3001.A.Space.Odyssey.2023.4K.mkv",
            "documentary 3001 a space odyssey 2023",
        ),
        (
            "电影.2022.1080p.BluRay.2k.x264-GRoUP.mkv",
            "电影 bluray 2022",
        ),
        (
            "फिल्म_2023_[1080p*].mkv",
            "फिल्म 2023",
        ),
    ],
)
def test_prepare_filename_for_matching(input_filename, expected_output):
    assert prepare_filename_for_matching(input_filename) == expected_output


@pytest.mark.parametrize(
    "input_filename, expected_output",
    [
        (
            "Generic Title (Alternate Title) (2020) [BD 1080p HI10P AAC][RELEASEGROUP].mkv",
            "Generic Title (2020)",
        ),
        (
            "Foreign.Title.2023.1080p.BluRay.DD+5.1.x264-GROUPXYZ.mkv",
            "Foreign Title (2023)",
        ),
        (
            "One Word [1985][BD 1080p 10bit FLAC].mkv",
            "One Word (1985)",
        ),
        (
            "Multi Word Title 2021 1080p BluRay DDP 5.1 x264 ABCDEF.mkv",
            "Multi Word Title (2021)",
        ),
        (
            "Hyphenated-Title (2019) [UHD BluRay 2160p TrueHD Atmos 7.1 HEVC]-RELEASEGROUP.mkv",
            "Hyphenated-Title (2019)",
        ),
        (
            "Title.With.Dots.2022.2160p.UHD.BluRay.DTS-HD.MA.5.1.DoVi.HDR10.x265-GROUP123.mkv",
            "Title With Dots (2022)",
        ),
        (
            "ALL_CAPS_TITLE_2018_[1080p,BluRay,x264]_-_ALLCAPSGROUP.mkv",
            "ALL CAPS TITLE (2018)",
        ),
        (
            "Mixed.Case.ReleaseGroup.2017.1080p.WEB-DL.DD5.1.H264-mIxEdGrOuP.mkv",
            "Mixed Case ReleaseGroup (2017)",
        ),
        (
            "[PleaseSubMe] Two Bits 1122 (1080p) [2251141D].mkv",
            "Two Bits 1122",  # 1122 shouldn't be detected as the year.
        ),
        (
            "The.ABC.Show.S01E13.What.a.Good.Title.1080p.SESO.WEBRip.AAC2.0.x264 monkee.mkv",
            "The ABC Show S01E13 What a Good Title",
        ),
        (
            "Single.Word.2002.1080p.BluRay.DD+5.1.x264-ZQ.mkv",
            "Single Word (2002)",
        ),
        (
            "Another.Word.DVDRip.x264.mkv",
            "Another Word",
        ),
        (
            "Dollar.$igns.2020.1080p.BluRay.x264.mkv",
            "Dollar $igns (2020)",
        ),
        (
            "Prefix.Long.Title.2022.2160p.UHD.BluRay.FLAC.2.0.DoVi.HDR10.x265-LongGroupName&Numbers123.mkv",
            "Prefix Long Title (2022)",
        ),
        (
            "Foreign.Title.1997.JPN.BluRay.Remux.1080p.AVC.DTS-HD.MA.5.1-ZQ.mkv",
            "Foreign Title (1997)",
        ),
        (
            "Dot.Separated.Title.2018.REPACK.1080p.BluRay.DTS.x264-Geek.mkv",
            "Dot Separated Title (2018)",
        ),
        (
            "Space Separated Title 2004 1080p BluRay DTS x264-iLoveHD.mkv",
            "Space Separated Title (2004)",
        ),
        (
            "Short.Title.2019.1080p.AMZN.WEB-DL.DDP2.0.H.264-SOMEGROUPNAME.mkv",
            "Short Title (2019)",
        ),
        (
            "Three.Word.Title.1968.1080p.BluRay.x264.FLAC.1.0-PTH.mkv",
            "Three Word Title (1968)",
        ),
        (
            "One Word 1989 1080p BluRay AAC2.0 x264-SomeGroup.mkv",
            "One Word (1989)",
        ),
        (
            "true.king.s02e25.1080p.web.h264 patheticmoss.mkv",
            "true king s02e25",
        ),
        (
            "Your.Normal.School.S17E21.Study.Without.a.Hassle.1080p.NF.WEB-DL.JPN.DDP2.0.H.264.YSubs-CartoonHub",
            "Your Normal School S17E21 Study Without a Hassle",
        ),
        (
            "Film's Title (2024) [2160p] [WEBRip] [x265] [10bit] [5.1] [ABC.FG].mkv",
            "Film's Title (2024)",
        ),
        (
            "Four.Word.Title.Here.1990.1080p.BluRay.FLAC.2.0.x264-BV.mkv",
            "Four Word Title Here (1990)",
        ),
        (
            "Very.Long.Title.With.Lots.Of.Words.1995.1080p.WEB-DL.DD+2.0.H.264-SbR.mkv",
            "Very Long Title With Lots Of Words (1995)",
        ),
        (
            "Simple.Title.1999.1080p.BluRay.x264.SomeExtra.mkv",
            "Simple Title (1999)",
        ),
        (
            "Compound.Title.Name.1996.4K.Remaster.1080p.BluRay.x264-GROUPNAME.mkv",
            "Compound Title Name (1996)",
        ),
        (
            "Another.Simple.Title.2000.1080p.AMZN.WEB-DL.DDP2.0.H.264-SOMEGROUPHERE.mkv",
            "Another Simple Title (2000)",
        ),
        (
            "Foreign Title Name 2002 1080p BluRay DTS x264-RR.mkv",
            "Foreign Title Name (2002)",
        ),
        (
            "Three.Word.Title.2003.1080p.Bluray.Remux.AVC.FLAC.2.0-SOMEGROUPNAME.mkv",
            "Three Word Title (2003)",
        ),
        (
            "The.Farmers.Tale.S04E01.Cows.1080p.REPACK.HULU.WEB-DL.DDP5.1.H.264-ABc.mkv",
            "The Farmers Tale S04E01 Cows",
        ),
        (
            "Four.Word.Title.Again.2005.1080p.WEB-DL.DD+2.0.H.264-GroupABC.mkv",
            "Four Word Title Again (2005)",
        ),
        (
            "Series - 03 - Episode.mkv",
            "Series - 03 - Episode",
        ),
        (
            "[Cool Show][01][JPN+ENG][BDRIP][1440P][H265_FLAC].mkv",
            "Cool Show 01",
        ),
        (
            "Show.S01E03.REPACK.1080p.BluRay.FLAC2.0.x264-Hi10P-SHiNYSTAR.mkv",
            "Show S01E03",
        ),
        (
            "[012345][オバマー] MASSIVE ATTACK -マクドナルド- 3rd Day.mkv",
            "MASSIVE ATTACK -マクドナルド- 3rd Day",
        ),
        (
            "[PrettySquare] What a Name - 02 (DVD 720x480 H264 AC3) [1234567F].mkv",
            "What a Name - 02",
        ),
        (
            "Blade.Runner.2049.2017.2160p.UHD.BluRay.x265.mkv",
            "Blade Runner 2049 (2017)",
        ),
        (
            "фильм.2004.1080p.WEBRip.DDP2.0.H.264-BELIEVEiNYOU.mkv",
            "фильм (2004)",
        ),
        (
            "Weird Year 2023 2023",
            "Weird Year 2023 (2023)",
        ),
        (
            "Historical Drama & You 1960 1970 1980 2020.mkv",
            "Historical Drama & You 1960 1970 1980 (2020)",
        ),
        (
            "映画.2022.1080p.BluRay.x264-GROUP.mkv",
            "映画 (2022)",
        ),
        (
            "หนัง.2049.DVDRip.avi",
            "หนัง (2049)",
        ),
        (
            "[OBEY-Me] Osusume EP32 (BD 1920x1080 x264 DualFLAC(2ch+5.1ch).mkv",
            "Osusume EP32",
        ),
    ],
)
def test_prepare_filename_for_display(input_filename, expected_output):
    assert prepare_filename_for_display(input_filename) == expected_output


@pytest.mark.parametrize(
    "filename, directory_name, expected",
    [
        (
            "Fantasy.Adventures.S01E10.1080p.NF.WEB-DL.DDP5.1.HDR.HEVC-ABc.mkv",
            "Fantasy.Adventures.S01.1080p.NF.WEB-DL.DDP5.1.HDR.HEVC-ABc",
            ("01", "10"),
        ),
        (
            "[MagicSubs] Magical Academy - 07v2 (1080p) [A1B2C3D4].mkv",
            "[MagicSubs] Magical Academy [1080p]",
            ("01", "07"),
        ),
        (
            "[BearSubs] Animal Cafe - 06 [1080p].mkv",
            "[BearSubs] Animal Cafe - [1080p]",
            ("01", "06"),
        ),
        (
            "[EpicReleases] Epic Battles - S04E29 v3 - The Final Chapters (Part 1) (WEB 1080p Hi10 EAC3 AAC) [E5F6G7H8].mkv",
            "[EpicReleases] Epic Battles - The Final Chapters (WEB 1080p Hi10 EAC3 AAC)",
            ("04", "29"),
        ),
        (
            "[LegendSubs] Legendary Warriors (The Final Season) - 84 (1080p) [I9J0K1L2].mkv",
            "[LegendSubs] Legendary Warriors (The Final Season) [1080p]",
            ("01", "84"),
        ),
        (
            "[DokiDoki] Heartstrings - 01 (1920x1080 Hi10P BD FLAC) [M3N4O5P6].mkv",
            "Heartstrings (DokiDoki BD 1080p) (Dual Audio)",
            ("01", "01"),
        ),
        (
            "[SpiritRaws] Spirit Walker EP03 (BD 1920x1080 x264 DualFLAC(2ch+5.1ch).mkv",
            "Spirit.Walker.S01.1080p.BluRay.x264.FLAC-SpiritRaws",
            ("01", "03"),
        ),
        (
            "[HorizonSubs] Post-Apocalyptic Journey - 12 [1080p].mkv",
            "Post-Apocalyptic Journey (HorizonSubs WEB 1080p)",
            ("01", "12"),
        ),
        (
            "Spirits - 12 - Shapeshifter.mkv",
            "Spirits(2007).S01.1080p.BluRay.x264",
            ("01", "12"),
        ),
        (
            "(G_P) Mystery 74(x264)(Q7R8S9T0).mkv",
            "Mystery.S01.DVDRip.AC3.x264-G_P",
            ("01", "74"),
        ),
        (
            "[CozySubs] Cozy Camping - 02 [1080p].mkv",
            "Cozy Camping (CozySubs WEB 1080p)",
            ("01", "02"),
        ),
        (
            "[MagicSubs] Secret Agents - 37 (1080p) [U1V2W3X4].mkv",
            "[MagicSubs] Secret Agents (2023) [1080p]",
            ("01", "37"),
        ),
        (
            "[MagicSubs] Secret Agents - 18v2 (1080p) [Y5Z6A7B8].mkv",
            "[MagicSubs] Secret Agents (2022) [1080p]",
            ("01", "18"),
        ),
        (
            "[AF-F&Y-F]_Beastmen_-_12_(1280x720)_(h264)_[C9D0E1F2].mkv",
            "Beastmen",
            ("01", "12"),
        ),
        (
            "Robotic.Beings.Ver1.1a.S01E12.flowers.for.mAchine.1080p.CR.WEB-DL.AAC2.0.H.264-Kitsune.mkv",
            "Robotic.Beings.Ver1.1a.S01.1080p.CR.WEB-DL.AAC2.0.H.264-Kitsune",
            ("01", "12"),
        ),
        (
            "[FutureSubs] Promised Land S2 - 09v2 (1080p) [G3H4I5J6].mkv",
            "[FutureSubs] Promised Land S2 (01-11) (1080p) [Batch]",
            ("02", "09"),
        ),
        (
            "[SCY] Escape Paradise - 11 (BD 1080p Hi10 FLAC) [K7L8M9N0].mkv",
            "[SCY] Escape Paradise (BD 1080p Hi10 FLAC) [Dual-Audio]",
            ("01", "11"),
        ),
        (
            "[FableGirls]_Supernatural_Tales_02_(1920x1080_Blu-ray_FLAC)_[O1P2Q3R4].mkv",
            "Supernatural Tales (FableGirls BD 1080p)",
            ("01", "02"),
        ),
        (
            "[UCCUSS] Time Loop Mystery 第04話 「#4 Déjà vu（ジャメヴ）」 (BD 1920x1080p AVC DTSHD).mkv",
            "[UCCUSS] Time Loop Mystery 全25話 (BD 1920x1080p AVC DTSHD)",
            ("01", "04"),
        ),
        (
            "[IrizaRaws] Immortal Journey - 03 (BDRip 1920x1080 x264 10bit FLAC).mkv",
            "[IrizaRaws] Immortal Journey (BDRip 1920x1080 x264 10bit FLAC)",
            ("01", "03"),
        ),
        (
            "[IrizaRaws] Immortal Journey Logo - 01 (BDRip 1920x1080 x264 10bit FLAC).mkv",
            "[IrizaRaws] Immortal Journey (BDRip 1920x1080 x264 10bit FLAC)/Bonus",
            ("01", "01"),
        ),
        (
            "[IrizaRaws] Immortal Journey Menu - 02 (BDRip 1920x1080 x264 10bit FLAC).mkv",
            "[IrizaRaws] Immortal Journey (BDRip 1920x1080 x264 10bit FLAC)/Bonus/Menu",
            ("01", "02"),
        ),
        (
            "TimeTravel.S01E06.Grim.Reaper.1080p.BluRay.FLAC2.0.x264-ABc.mkv",
            "TimeTravel.S01.1080p.BluRay.FLAC2.0.x264-ABc",
            ("01", "06"),
        ),
        (
            "[RH] Psychic Boy - 09 [S5T6U7V8].mp4",
            "[RH] Psychic Boy [English Dubbed] [1080p]",
            ("01", "09"),
        ),
        (
            "[MysterySubs] Mind Detectives - 10 [1080p].mkv",
            "[MysterySubs] Mind Detectives [1080p]",
            ("01", "10"),
        ),
        (
            "[FantasyReleases] Fantasy World Adventures - Director's Cut - 13 [1080p].mkv",
            "Fantasy World Adventures - Director's Cut (FantasyReleases WEB 1080p)",
            ("01", "13"),
        ),
        (
            "[MagicSubs] Psychic Boy S3 - 02v2 (1080p) [W9X0Y1Z2].mkv",
            "[MagicSubs] Psychic Boy III [1080p]",
            ("03", "02"),
        ),
        (
            "[Kametsu] Afterlife Games - 04 (BD 1080p Hi10 FLAC) [A3B4C5D6].mkv",
            "Afterlife Games (BD 1080p Hi10 FLAC) [Dual-Audio] [Kametsu]",
            ("01", "04"),
        ),
        (
            "Psychic.Boy.S02E05.1080p.FUNI.WEB-DL.AAC2.0.x264-KiyoshiStar.mkv",
            "Psychic.Boy.S02.1080p.FUNI.WEB-DL.AAC2.0.x264-KiyoshiStar",
            ("02", "05"),
        ),
        (
            "[MysterySubs] Urban Legends X2 - 15 [1080p].mkv",
            "Urban Legends X2 (MysterySubs Web 1080p)",
            ("01", "15"),
        ),
        (
            "[FableGirls]_Urban_Legends_01_(1920x1080_Blu-ray_FLAC)_[E7F8G9H0].mkv",
            "Urban Legends [Bluray Hi10P]",
            ("01", "01"),
        ),
        (
            "[Komorebi] Emotional Letters 04 (BD 1080p) [I1J2K3L4].mkv",
            "[Komorebi] Emotional Letters [BD 1080p x264-10bit FLAC]",
            ("01", "04"),
        ),
        (
            "[MagicSubs] Magical Combat - 05v2 (1080p) [M5N6O7P8].mkv",
            "[MagicSubs] Magical Combat (01-24) (1080p) [Batch]",
            ("01", "05"),
        ),
        (
            "Mind.Mysteries.S01E07.MHz.1080p.BluRay.DD.5.1.x264-Kitsune.mkv",
            "Mind.Mysteries.S01.REPACK.1080p.BluRay.DUAL.DD.5.1.x264-Kitsune",
            ("01", "07"),
        ),
        (
            "Gambling.School.S01E07.REPACK.1080p.BluRay.FLAC2.0.x264-Hi10P-KiyoshiStar.mkv",
            "Gambling.School.S01.REPACK.1080p.BluRay.FLAC2.0.x264-Hi10P-KiyoshiStar",
            ("01", "07"),
        ),
        (
            "[MysterySubs] Super Hero S2 - 12 [1080p].mkv",
            "Super Hero (2019) (MysterySubs WEB 1080p)",
            ("02", "12"),
        ),
        (
            "[HeroicReleases][08][JPN+ENG][BDRIP][1080P][H264_FLACx2].mkv",
            "Super.Hero.S01.1080p.BluRay.FLAC2.0.x264-HeroicReleases",
            ("01", "08"),
        ),
        (
            "[MagicSubs] Alien Invasion Comedy - 09 (1080p) [Q9R0S1T2].mkv",
            "[MagicSubs] Alien Invasion Comedy [1080p]",
            ("01", "09"),
        ),
    ],
)
def test_extract_season_and_episode(filename, directory_name, expected):
    assert extract_season_and_episode(filename, directory_name) == expected


@pytest.mark.parametrize(
    "external_subtitle_search,expected_result",
    [
        ("disabled", None),
        ("fuzzy", "{}/myvideo.srt"),
    ],
)
def test_find_matching_subtitle_file(
    tmp_path, base_context, external_subtitle_search, expected_result
):
    base_context.config["external_subtitle_search"] = external_subtitle_search
    input_dir = tmp_path / "test_dir"
    input_dir.mkdir()
    (input_dir / "myvideo.srt").touch()  # Should only match w/ fuzzy search.
    result = find_matching_subtitle_file(
        context=base_context, input_dir=str(input_dir), input_name="my_video"
    )
    expected = (
        expected_result.format(input_dir)
        if isinstance(expected_result, str)
        else expected_result
    )
    assert result == expected, f"Unexpected result with {external_subtitle_search} mode"


def test_generate_output_path_with_config_output_dir(base_context, tmp_path):
    output_dir = str(tmp_path / "configured_output")
    base_context.config["output_directory"] = output_dir
    base_context.config["output_suffix"] = ".condensed"
    result = generate_output_path(base_context, "mp3")
    expected = str(Path(output_dir) / "input.condensed.mp3")
    assert result == expected


def test_generate_output_path_expands_user_directory(base_context):
    base_context.config["output_directory"] = os.path.join("~", "outputs")
    base_context.config["output_suffix"] = ""
    result = generate_output_path(base_context, "mp3")
    expected = str(Path(os.path.expanduser("~/outputs")) / "input.mp3")
    assert result == expected


def test_generate_output_path_cli_overrides_config(base_context, tmp_path):
    cli_output = str(tmp_path / "cli_output")
    config_output = str(tmp_path / "config_output")
    base_context.args.output = cli_output
    base_context.config["output_directory"] = config_output
    base_context.config["output_suffix"] = ""
    result = generate_output_path(base_context, "mp3")
    # Should use CLI path.
    expected = str(Path(cli_output) / "input.mp3")
    assert result == expected


def test_generate_output_path_uses_input_directory(base_context):
    base_context.config.pop("output_directory", None)
    base_context.args.output = None
    base_context.config["output_suffix"] = ""
    result = generate_output_path(base_context, "mp3")
    expected = str(Path(base_context.file_path).parent / "input.mp3")
    assert result == expected


@pytest.mark.parametrize(
    "stream_index,codec,expected_ext",
    [
        ("1", "aac", "m4a"),  # First stream, known codec.
        ("2", "flac", "flac"),  # Second stream, known codec.
        # Third stream, known codec.
        (
            "3",
            "libmp3lame",
            "mp3",
        ),
    ],
)
def test_get_audio_extension_copy_with_valid_stream(
    base_context, stream_index, codec, expected_ext
):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = stream_index
    stream_idx = int(stream_index) - 1
    base_context.stream_info["audio"][stream_idx]["codec_name"] = codec
    result = get_audio_extension(base_context)
    assert result == expected_ext


def test_get_audio_extension_copy_with_unknown_codec(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = "1"
    base_context.stream_info["audio"][0]["codec_name"] = "unknown_codec"
    result = get_audio_extension(base_context)
    assert result == "mkv"


def test_get_audio_extension_copy_with_out_of_bounds_index(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = "99"
    result = get_audio_extension(base_context)
    assert result == "mkv"


def test_get_audio_extension_copy_with_missing_codec_name(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = "1"
    base_context.stream_info["audio"][0].pop("codec_name", None)
    result = get_audio_extension(base_context)
    assert result == "mkv"


def test_get_audio_extension_copy_with_invalid_stream_index(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = "not_a_number"
    result = get_audio_extension(base_context)
    assert result == "mkv"


def test_get_audio_extension_copy_with_no_selected_stream(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    base_context.selected_audio_stream = None
    result = get_audio_extension(base_context)
    assert result == "mkv"


@pytest.mark.parametrize(
    "codec,expected_ext",
    [
        ("aac", "m4a"),
        ("alac", "m4a"),
        ("flac", "flac"),
        ("libmp3lame", "mp3"),
        ("libopus", "ogg"),
        ("pcm_s16le", "wav"),
        ("unknown_codec", "mkv"),
    ],
)
def test_get_audio_extension_direct_codec(base_context, codec, expected_ext):
    base_context.config["condensed_audio.audio_codec"] = codec
    base_context.selected_audio_stream = None
    result = get_audio_extension(base_context)
    assert result == expected_ext


def test_extract_speech_timing_respects_subtitle_delay(base_context):
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=1000, end=2000, text="Line 1"))  # 1-2 seconds.
    subs.append(pysubs2.SSAEvent(start=3000, end=4000, text="Line 2"))  # 3-4 seconds.
    # Positive delay of 1 second.
    base_context.args.sub_delay = 1000
    base_context.config["padding"] = 0
    segments = extract_speech_timing_from_subtitles(base_context, subs)
    # Segments should be shifted forward by 1 second.
    expected_segments = [
        (2.0, 3.0),
        (4.0, 5.0),
    ]
    assert segments == expected_segments


def test_extract_speech_timing_respects_negative_subtitle_delay(base_context):
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=2000, end=3000, text="Line 1"))  # 2-3 seconds.
    subs.append(pysubs2.SSAEvent(start=4000, end=5000, text="Line 2"))  # 4-5 seconds.
    base_context.args.sub_delay = -1000
    base_context.config["padding"] = 0
    segments = extract_speech_timing_from_subtitles(base_context, subs)
    expected_segments = [
        (1.0, 2.0),
        (3.0, 4.0),
    ]
    assert segments == expected_segments


def test_select_audio_stream_with_missing_tags(base_context):
    base_context.stream_info["audio"] = [
        {"index": 0, "tags": {"language": "eng"}},
        {"index": 1},
        {"index": 2, "tags": {"language": "jpn"}},
    ]
    base_context.config["audio_languages"] = ["jpn"]
    result = select_audio_stream(base_context)
    assert result == "2"


def test_select_audio_stream_all_streams_without_tags(base_context, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    base_context.stream_info["audio"] = [
        {"index": 0},
        {"index": 1},
        {"index": 2},
    ]
    base_context.config["audio_languages"] = ["jpn"]
    result = select_audio_stream(base_context)
    assert result == "0"


def test_select_audio_stream_mixed_tag_formats(base_context):
    base_context.stream_info["audio"] = [
        {"index": 0, "tags": {}},
        {"index": 1},
        {"index": 2, "tags": {}},
        {"index": 3, "tags": {"language": "jpn"}},
    ]
    base_context.config["audio_languages"] = ["jpn"]
    result = select_audio_stream(base_context)
    assert result == "3"


@pytest.fixture
def chapter_subs():
    subtitle_content = """1
00:00:20,000 --> 00:00:22,000
Opening theme song.

2
00:00:50,000 --> 00:00:52,000
First real dialogue.

3
00:01:20,000 --> 00:01:22,000
More dialogue.

4
00:23:30,000 --> 00:23:32,000
Preview of next episode!
"""
    return pysubs2.SSAFile.from_string(subtitle_content)


def test_filter_chapters_in_place_basic(chapter_subs):
    skip_intervals = [(0.0, 30.0), (1380.0, 1440.0)]  # Opening and Preview intervals
    filter_chapters_in_place(chapter_subs, skip_intervals)
    assert len(chapter_subs) == 2
    expected_texts = [
        "First real dialogue.",
        "More dialogue.",
    ]
    assert [sub.text for sub in chapter_subs] == expected_texts


def test_filter_chapters_in_place_no_intervals(chapter_subs):
    skip_intervals: list[tuple[float, float]] = []
    original_subs = chapter_subs.events.copy()
    filter_chapters_in_place(chapter_subs, skip_intervals)
    assert chapter_subs.events == original_subs


def test_get_skipped_chapter_intervals(base_context):
    base_context.config["skip_chapters"] = ["opening", "preview"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening"}},
        {"start_time": "30.0", "end_time": "1380.0", "tags": {"title": "Main"}},
        {"start_time": "1380.0", "end_time": "1440.0", "tags": {"title": "Preview"}},
    ]
    expected = [(0.0, 30.0), (1380.0, 1440.0)]
    assert get_skipped_chapter_intervals(base_context) == expected


def test_get_skipped_chapter_intervals_case_insensitive(base_context):
    base_context.config["skip_chapters"] = ["opening"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "OPENING"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Opening Theme"}},
    ]
    expected = [(0.0, 30.0)]
    assert get_skipped_chapter_intervals(base_context) == expected


def test_get_skipped_chapter_intervals_logs_matched_chapters(base_context, caplog):
    base_context.config["skip_chapters"] = ["opening", "ending", "preview"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "OPENING"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Main Story"}},
        {"start_time": "60.0", "end_time": "90.0", "tags": {"title": "Ending"}},
    ]
    with caplog.at_level(logging.DEBUG):
        get_skipped_chapter_intervals(base_context)
        assert "Skipping 2 matched chapters" in caplog.text
        assert "Ending" in caplog.text
        assert "OPENING" in caplog.text


def test_get_skipped_chapter_intervals_no_partial_matches(base_context):
    base_context.config["skip_chapters"] = ["opening"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening Theme"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Opening"}},
    ]
    expected = [(30.0, 60.0)]
    assert get_skipped_chapter_intervals(base_context) == expected


def test_get_skipped_chapter_intervals_empty_config(base_context):
    base_context.config["skip_chapters"] = []
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Preview"}},
    ]
    assert get_skipped_chapter_intervals(base_context) == []


def test_get_skipped_chapter_intervals_no_chapters(base_context):
    base_context.config["skip_chapters"] = ["opening", "preview"]
    base_context.stream_info["chapters"] = []
    assert get_skipped_chapter_intervals(base_context) == []


def test_get_skipped_chapter_intervals_no_matching_chapters(base_context):
    base_context.config["skip_chapters"] = ["opening", "preview"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Part A"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Part B"}},
    ]
    assert get_skipped_chapter_intervals(base_context) == []


def test_get_skipped_chapter_intervals_config_not_set(base_context):
    base_context.config = {}  # No skip_chapters key
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening"}},
    ]
    assert get_skipped_chapter_intervals(base_context) == []


@pytest.mark.parametrize(
    "chapter_title",
    [
        "opening theme",
        "PREVIEW NEXT",
        "Opening Song",
        "Preview of Next Episode",
        "OPENING CREDITS",
    ],
)
def test_get_skipped_chapter_intervals_exact_match(base_context, chapter_title):
    base_context.config["skip_chapters"] = ["opening", "preview"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": chapter_title}},
    ]
    # Should not match partial words/phrases.
    assert get_skipped_chapter_intervals(base_context) == []


def test_main_processing_with_chapter_filtering(base_context):
    base_context.config["skip_chapters"] = ["opening"]
    base_context.stream_info["chapters"] = [
        {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening"}},
        {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Main"}},
    ]
    base_context.config["line_skip_patterns"] = ["^♪.*♪$"]
    subs = pysubs2.SSAFile()
    test_lines = [
        (1000, 2000, "This is in opening"),  # Should be filtered (in Opening)
        (5000, 6000, "♪ This is a song ♪"),  # Should be filtered (pattern)
        (40000, 42000, "This should remain"),  # Should stay
        (50000, 52000, "Also should remain"),  # Should stay
    ]
    for start, end, text in test_lines:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
    skip_patterns = [
        re.compile(pattern) for pattern in base_context.config["line_skip_patterns"]
    ]
    filter_skip_patterns_in_place(subs, skip_patterns)
    skip_intervals = get_skipped_chapter_intervals(base_context)
    filter_chapters_in_place(subs, skip_intervals)
    expected_texts = [
        "This should remain",
        "Also should remain",
    ]
    assert [sub.text for sub in subs] == expected_texts


def test_process_file_with_chapter_filtering(tmp_path):
    video_path = str(tmp_path / "test.mkv")
    Path(video_path).touch()
    sub_path = str(tmp_path / "test.srt")
    with open(sub_path, "w") as f:
        f.write("""1
00:00:01,000 --> 00:00:02,000
Line in opening

2
00:00:35,000 --> 00:00:36,000
Line in main content""")
    config = deepcopy(DEFAULT_CONFIG)
    config["skip_chapters"] = ["opening"]
    config["condensed_audio.enabled"] = False
    config["condensed_video.enabled"] = False
    config["condensed_subtitles.enabled"] = True
    with (
        patch("shuku.cli.FFmpeg") as mock_ffmpeg,
        patch("shuku.cli.get_all_stream_info") as mock_stream_info,
        patch("shuku.cli.find_subtitles", return_value=sub_path),
    ):
        mock_stream_info.return_value = {
            "video": [],
            "audio": [],
            "subtitle": [],
            "chapters": [
                {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Opening"}},
                {"start_time": "30.0", "end_time": "60.0", "tags": {"title": "Main"}},
            ],
        }
        args = argparse.Namespace(
            subtitles=None,
            output=None,
            sub_track_id=None,
            audio_track_id=None,
            sub_delay=0,
        )
        process_file(video_path, config, args)
        output_path = str(tmp_path / "test (condensed).srt")
        assert os.path.exists(output_path)
        output_subs = pysubs2.load(output_path)
        assert len(output_subs) == 1
        assert "Line in main content" in [sub.text for sub in output_subs]
        assert "Line in opening" not in [sub.text for sub in output_subs]


def test_audio_copy_codec(base_context):
    base_context.config["condensed_audio.audio_codec"] = "copy"
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "copy"}


def test_pcm_codec(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "pcm_s16le",
            "condensed_audio.audio_quality": None,
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "pcm_s16le", "ac": 2, "f": "wav"}


def test_pcm_codec_with_quality(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "pcm_s16le",
            "condensed_audio.audio_quality": "48k",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "pcm_s16le", "ac": 2, "f": "wav", "b:a": "48k"}


def test_flac_codec(base_context):
    base_context.config.update(
        {"condensed_audio.audio_codec": "flac", "condensed_audio.audio_quality": 5}
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "flac", "ac": 2, "compression_level": 5}


def test_aac_codec_quality(base_context):
    base_context.config.update(
        {"condensed_audio.audio_codec": "aac", "condensed_audio.audio_quality": "5"}
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "aac", "ac": 2, "q:a": "5"}


def test_aac_codec_bitrate(base_context):
    base_context.config.update(
        {"condensed_audio.audio_codec": "aac", "condensed_audio.audio_quality": "128k"}
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "aac", "ac": 2, "b:a": "128k"}


def test_opus_codec_numeric(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libopus",
            "condensed_audio.audio_quality": "64",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libopus", "ac": 2, "b:a": "64b", "application": "voip"}


def test_opus_codec_bitrate(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libopus",
            "condensed_audio.audio_quality": "128k",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libopus", "ac": 2, "b:a": "128k", "application": "voip"}


def test_mp3_vbr_quality(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libmp3lame",
            "condensed_audio.audio_quality": "V2",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libmp3lame", "ac": 2, "q:a": "2"}


def test_mp3_numeric_quality(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libmp3lame",
            "condensed_audio.audio_quality": 2,
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libmp3lame", "ac": 2, "q:a": 2}


def test_mp3_bitrate(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libmp3lame",
            "condensed_audio.audio_quality": "320k",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libmp3lame", "ac": 2, "b:a": "320k"}


def test_mp3_invalid_quality(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libmp3lame",
            "condensed_audio.audio_quality": "invalid",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "libmp3lame", "ac": 2, "q:a": DEFAULT_MP3_VBR_QUALITY}


def test_other_codec(base_context):
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "other_codec",
            "condensed_audio.audio_quality": "256k",
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "other_codec", "ac": 2, "b:a": "256k"}


def test_no_audio_quality(base_context):
    base_context.config.update(
        {"condensed_audio.audio_codec": "aac", "condensed_audio.audio_quality": None}
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result == {"c:a": "aac", "ac": 2}


def test_video_media_type(base_context):
    base_context.config.update(
        {"condensed_video.audio_codec": "aac", "condensed_video.audio_quality": "128k"}
    )
    result = get_ffmpeg_audio_options(base_context, media_type="video")
    assert result == {"c:a": "aac", "ac": 2, "b:a": "128k"}


@pytest.mark.parametrize(
    "audio_quality",
    [
        "V0",
        "v0",
        "V9",
        "v9",
        "0",
        "9",
        "128k",
        "320k",
    ],
)
def test_mp3_valid_quality_formats(base_context, audio_quality):
    """Test MP3 codec with various valid quality formats"""
    base_context.config.update(
        {
            "condensed_audio.audio_codec": "libmp3lame",
            "condensed_audio.audio_quality": audio_quality,
        }
    )
    result = get_ffmpeg_audio_options(base_context)
    assert result["c:a"] == "libmp3lame"
    assert result["ac"] == 2
    assert ("q:a" in result) or ("b:a" in result)


def test_video_copy_codec(base_context):
    base_context.config["condensed_video.video_codec"] = "copy"
    base_context.config["condensed_video.video_quality"] = "23"  # Should be ignored
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": "copy"}


@pytest.mark.parametrize("codec", ["libx264", "libx265", "libvpx-vp9", "vp9"])
def test_crf_codecs(base_context, codec):
    base_context.config.update(
        {"condensed_video.video_codec": codec, "condensed_video.video_quality": "23"}
    )
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": codec, "crf": "23"}


def test_other_codec_bitrate(base_context):
    base_context.config.update(
        {
            "condensed_video.video_codec": "other_codec",
            "condensed_video.video_quality": "2M",
        }
    )
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": "other_codec", "b:v": "2M"}


@pytest.mark.parametrize(
    "quality",
    [
        "0",  # Minimum value
        "23",  # Common default
        "51",  # Maximum value for x264/x265
        "2M",  # Bitrate format
        "500k",  # Another bitrate format
    ],
)
def test_various_quality_values(base_context, quality):
    base_context.config.update(
        {
            "condensed_video.video_codec": "libx264",
            "condensed_video.video_quality": quality,
        }
    )
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": "libx264", "crf": quality}


@pytest.mark.parametrize(
    "codec,quality,expected_option",
    [
        ("libx264", "23", "crf"),
        ("libx265", "28", "crf"),
        ("libvpx-vp9", "31", "crf"),
        ("vp9", "31", "crf"),
        ("mpeg4", "1500k", "b:v"),
        ("libsvtav1", "2M", "b:v"),
    ],
)
def test_codec_quality_mapping(base_context, codec, quality, expected_option):
    base_context.config.update(
        {"condensed_video.video_codec": codec, "condensed_video.video_quality": quality}
    )
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": codec, expected_option: quality}


def test_none_quality(base_context):
    base_context.config.update(
        {
            "condensed_video.video_codec": "libx264",
            "condensed_video.video_quality": None,
        }
    )
    result = get_ffmpeg_video_options(base_context)
    assert result == {"c:v": "libx264", "crf": None}
