import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pysubs2
import pytest
from ffmpeg import FFmpeg

from shuku.config import generate_config_content, get_default_config_path
from shuku.utils import REPOSITORY


# Ensure that the tests run in an isolated environment.
# Avoids reading from the user's actual configuration files.
@pytest.fixture(autouse=True)
def isolate_config_environment(monkeypatch, tmp_path):
    # Set XDG_CONFIG_HOME to a temporary directory.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Ensure APPDATA is not set (for Windows).
    monkeypatch.delenv("APPDATA", raising=False)
    # Set HOME to a non-existent path to avoid reading from ~/.config.
    monkeypatch.setenv("HOME", str(tmp_path / "nonexistent"))


def run_shuku(
    input_file: str,
    output_dir: str,
    config: str = "",
    run_dir: str = ".",
    args: list[str] = [],
) -> subprocess.CompletedProcess:
    cmd = ["shuku", input_file, "-o", output_dir]
    if config:
        cmd.extend(["-c", config])
    cmd.extend(args)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=run_dir, env=env)
    return result


def compute_file_hash(file_path: str) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_file_duration(file_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return float(result.stdout)


def get_audio_metadata(file_path: str) -> dict[str, Any]:
    probe = (
        FFmpeg(executable="ffprobe")
        .option("v", "quiet")
        .option("print_format", "json")
        .option("show_format")
        .option("show_streams")
        .input(file_path)
        .execute()
    )
    probe_data = json.loads(probe)
    # Try to get metadata from 'format' section (works with MP3).
    metadata = probe_data.get("format", {}).get("tags", {})
    # If metadata is empty, try to get it from the first audio stream (for ogg).
    if not metadata:
        streams = probe_data.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if audio_streams:
            metadata = audio_streams[0].get("tags", {})
    result = {
        "artist": metadata.get("artist", ""),
        "genre": metadata.get("genre", ""),
        "encoded_by": metadata.get("encoded_by", ""),
        "album": metadata.get("album", ""),
        "date": metadata.get("date", ""),
    }
    return result


@pytest.mark.parametrize(
    "audio_codec,audio_quality,expected_extension",
    [
        ("aac", "128k", "m4a"),
        ("libopus", "128k", "ogg"),
    ],
)
def test_audio_codec_and_quality(
    tmp_path, audio_codec, audio_quality, expected_extension
):
    input_file = (
        "tests/test_files/input/ディスコで超ノリノリのげんげん [ISyLeiYnPx8].mp4"
    )
    input_filename = Path(input_file).stem
    config_content = f"""
    clean_output_filename = false
    [condensed_audio]
    enabled = true
    audio_codec = "{audio_codec}"
    audio_quality = "{audio_quality}"
    """
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    result = run_shuku(input_file, str(tmp_path), str(config_file))
    assert result.returncode == 0, f"shuku failed with {audio_codec} {audio_quality}"
    output_audio = tmp_path / f"{input_filename} (condensed).{expected_extension}"
    assert (
        output_audio.exists()
    ), f"Audio file was not created with {audio_codec} {audio_quality}"
    assert (
        output_audio.stat().st_size > 0
    ), f"Audio file is empty with {audio_codec} {audio_quality}"
    if audio_codec == "aac":
        # ffmpeg can't write metadata to m4a files.
        return
    metadata = get_audio_metadata(str(output_audio))
    assert metadata is not None, "Failed to get audio metadata"
    assert metadata["artist"] == "shuku", "Artist metadata is incorrect"
    assert metadata["genre"] == "Condensed Media", "Genre metadata is incorrect"
    assert metadata["encoded_by"].startswith(
        "shuku v"
    ), "Encoded_by metadata is incorrect"
    assert metadata["date"] == str(time.gmtime().tm_year), "Date metadata is incorrect"


@pytest.mark.parametrize(
    "config_file",
    [
        # Nested and flat TOML formats.
        "tests/test_files/config/mp3v9nopaddingsrt_sections.toml",
        "tests/test_files/config/mp3v9nopaddingsrt_dotnotation.toml",
    ],
)
def test_toml_formats(tmp_path, config_file):
    input_file = "tests/test_files/input/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM].mp4"
    expected_mp3 = "tests/test_files/output/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).mp3"
    expected_srt = "tests/test_files/output/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).srt"
    expected_vid = "tests/test_files/output/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).mp4"
    result = run_shuku(input_file, str(tmp_path), config_file)
    assert result.returncode == 0, f"shuku failed with config {config_file}"
    output_mp3 = tmp_path / "T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).mp3"
    output_srt = tmp_path / "T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).srt"
    output_vid = tmp_path / "T×T 週末版時報cm(イマミル) [t2zOxG4BzTM] (condensed).mp4"
    assert output_mp3.exists(), f"MP3 file was not created with config {config_file}"
    assert output_srt.exists(), f"SRT file was not created with config {config_file}"
    assert output_vid.exists(), f"Video file was not created with config {config_file}"
    expected_mp3_size = Path(expected_mp3).stat().st_size
    actual_mp3_size = output_mp3.stat().st_size
    assert actual_mp3_size > 0, f"MP3 file is empty with config {config_file}"
    assert (
        abs(actual_mp3_size - expected_mp3_size) / expected_mp3_size < 0.05
    ), f"MP3 file size differs significantly with config {config_file}"
    expected_duration = get_file_duration(expected_mp3)
    actual_duration = get_file_duration(str(output_mp3))
    assert (
        abs(actual_duration - expected_duration) < 0.1
    ), f"MP3 duration differs significantly with config {config_file}"
    assert compute_file_hash(output_srt) == compute_file_hash(
        expected_srt
    ), f"SRT file content differs with config {config_file}"
    expected_vid_size = Path(expected_vid).stat().st_size
    actual_vid_size = output_vid.stat().st_size
    assert actual_vid_size > 0, f"Video file is empty with config {config_file}"
    assert (
        abs(actual_vid_size - expected_vid_size) / expected_vid_size < 0.05
    ), f"Video file size differs significantly with config {config_file}"
    expected_vid_duration = get_file_duration(expected_vid)
    actual_vid_duration = get_file_duration(str(output_vid))
    assert (
        abs(actual_vid_duration - expected_vid_duration) < 0.5
    ), f"Video duration differs significantly with config {config_file}"


def test_no_audio(tmp_path):
    input_file = "tests/test_files/input/Silent Love [KuuEs0oVVS8].mp4"
    output_mp3 = tmp_path / "Silent Love [KuuEs0oVVS8] (condensed).mp3"
    result = run_shuku(input_file, str(tmp_path))
    assert result.returncode != 0
    assert not output_mp3.exists()
    assert "No audio streams " in result.stderr


def test_no_video(tmp_path):
    config = "tests/test_files/config/condense_all.toml"
    input_file = (
        # Only contains audio and sub streams.
        "tests/test_files/input/ディスコで超ノリノリのげんげん [ISyLeiYnPx8].mkv"
    )
    output_mp3 = tmp_path / "ディスコで超ノリノリのげんげん [ISyLeiYnPx8]_TLDR.ogg"
    result = run_shuku(input_file, str(tmp_path), config)
    assert result.returncode != 0
    assert not output_mp3.exists()
    assert "No video stream" in result.stderr


def test_no_subtitles(tmp_path):
    input_file = "tests/test_files/input/ZHIYlXDiBIc.mp4"
    output_mp3 = tmp_path / "Silent Love [KuuEs0oVVS8] (condensed).mp3"
    result = run_shuku(input_file, str(tmp_path))
    assert result.returncode != 0
    assert not output_mp3.exists()
    assert "No subtitle streams found" in result.stderr


def test_run_without_config_file_loads_default_config(tmp_path):
    input_file = "tests/test_files/input/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM].mp4"
    result = run_shuku(input_file, str(tmp_path), config="")
    assert result.returncode == 0
    assert "File not found" not in result.stderr
    assert "Using default configuration" in result.stderr
    output_files = list(tmp_path.glob("*"))
    assert len(output_files) == 1


def test_condense_unsorted_subs_lrc(tmp_path):
    input_file = "tests/test_files/input/unsorted_subs.srt"
    config = tmp_path / "config.toml"
    config.write_text("""
    clean_output_filename = false
    condensed_subtitles.enabled = true
    condensed_subtitles.format = "lrc"
    condensed_audio.enabled = false
    condensed_video.enabled = false""")
    expected_output = "tests/test_files/output/unsorted_subs (condensed).lrc"
    result = run_shuku(input_file, str(tmp_path), str(config))
    assert result.returncode == 0, "shuku failed with config"
    output = tmp_path / "unsorted_subs (condensed).lrc"
    assert output.exists(), "LRC file was not created with config"
    assert compute_file_hash(output) == compute_file_hash(
        expected_output
    ), "Condensed file content differs from expected output"
    with open(output, "r") as f:
        content = f.read()
    assert "[ti:unsorted" in content, "Metadata not found in condensed LRC"
    assert "  " not in content, "Extra spaces found in condensed LRC"
    assert "[00:00.00]" in content, "First line should be at 00:00:00,000"


def test_empty_file(tmp_path):
    input_file = "tests/test_files/input/empty_file.mkv"
    result = run_shuku(input_file, str(tmp_path))
    assert result.returncode != 0, "shuku should fail with an empty file"
    assert "Invalid data" in result.stderr
    output_files = list(tmp_path.glob("*"))
    assert len(output_files) == 0
    assert "Successfully condensed" not in result.stderr
    assert "1 file failed to process" in result.stderr


def test_invalid_config(tmp_path):
    input_file = "tests/test_files/input/T×T 週末版時報cm(イマミル) [t2zOxG4BzTM].mp4"
    invalid_config = tmp_path / "invalid_config.toml"
    invalid_config.write_text("""condensed_video = true
condensed_video = false""")
    result = run_shuku(input_file, str(tmp_path), str(invalid_config))
    assert result.returncode != 0, "shuku should fail with an invalid config"
    assert "Error loading config" in result.stderr
    assert "Cannot overwrite a value" in result.stderr
    output_files = [f for f in tmp_path.glob("*") if f != invalid_config]
    assert (
        len(output_files) == 0
    ), "No output files should be created with invalid config"
    assert "Successfully condensed" not in result.stderr
    assert "file failed to process" not in result.stderr


def test_add_internal_subs_custom_suffix(tmp_path):
    input_file = "tests/test_files/input/祝成人！新成人インタビュー [ufQzl-dyA4s].mkv"
    config = "tests/test_files/config/condense_all.toml"
    result = run_shuku(input_file, str(tmp_path), config)
    assert result.returncode == 0, "shuku failed with internal subtitles"
    output_video = tmp_path / "祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.mkv"
    output_audio = tmp_path / "祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.ogg"
    output_subs = tmp_path / "祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.srt"
    expected_video = (
        "tests/test_files/output/祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.mkv"
    )
    expected_audio = (
        "tests/test_files/output/祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.ogg"
    )
    expected_subs = (
        "tests/test_files/output/祝成人！新成人インタビュー [ufQzl-dyA4s]_TLDR.srt"
    )
    for output_file, expected_file in [
        (output_video, expected_video),
        (output_audio, expected_audio),
        (output_subs, expected_subs),
    ]:
        assert output_file.exists(), f"{output_file} was not created"
        assert output_file.stat().st_size > 0, f"{output_file} is empty"
        expected_size = Path(expected_file).stat().st_size
        actual_size = output_file.stat().st_size
        assert (
            abs(actual_size - expected_size) / expected_size < 0.05
        ), f"{output_file} size differs significantly from expected"
        if output_file != output_subs:
            expected_duration = get_file_duration(expected_file)
            actual_duration = get_file_duration(str(output_file))
            assert (
                abs(actual_duration - expected_duration) < 0.5
            ), f"{output_file} duration differs significantly from expected"
    assert compute_file_hash(output_subs) == compute_file_hash(
        expected_subs
    ), "Subtitle content differs from expected output"
    assert "Successfully condensed" in result.stderr
    assert "file failed to process" not in result.stderr
    assert "Using only available supported subtitle stream" in result.stderr


def test_invalid_audio_track_id(tmp_path):
    input_file = (
        "tests/test_files/input/ディスコで超ノリノリのげんげん [ISyLeiYnPx8].mp4"
    )
    result = run_shuku(input_file, str(tmp_path), args=["--audio-track-id", "333"])
    assert result.returncode != 0, "Should fail with non-zero exit code"
    assert "Error processing file" in result.stderr
    assert "Specified audio stream 333 not found" in result.stderr


def run_shuku_init(tmp_path: Path) -> subprocess.CompletedProcess:
    cmd = ["shuku", "--init"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    env["XDG_CONFIG_HOME"] = str(tmp_path)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def test_init_creates_new_config(tmp_path):
    result = run_shuku_init(tmp_path)
    config_path = get_default_config_path()
    assert result.returncode == 0
    assert f"Configuration file created: {config_path}" in result.stderr
    assert config_path.parent.exists(), "Config directory should be created"
    assert config_path.parent.is_dir(), "Created path should be a directory"
    assert config_path.exists(), "Config file should exist in the created directory"
    with open(config_path) as f:
        actual_content = f.read()
        assert "{REPOSITORY}" not in actual_content
        assert REPOSITORY in actual_content
    expected_content = generate_config_content()
    assert actual_content == expected_content


def test_init_aborts_if_config_exists(tmp_path):
    config_dir = tmp_path / ".config" / "shuku"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "shuku.toml"
    original_content = "original content"
    with open(config_path, "w") as f:
        f.write(original_content)
    run_shuku_init(tmp_path)
    with open(config_path) as f:
        current_content = f.read()
        assert current_content == original_content, "File was overwritten"


def test_subtitle_delay_with_precise_timing(tmp_path):
    """Test that subtitle delay correctly synchronizes shifted subtitles with audio.

    Uses a test file with 'bruh' sounds at precise timestamps and two sets of subtitles:
    1. Original subtitles matching the audio
    2. Subtitles shifted forward by 10 seconds

    Both should produce identical condensed output when the shifted subs are corrected
    with --sub-delay -10000.
    """
    input_file = "tests/test_files/input/bruh.opus"
    original_subs = "tests/test_files/input/bruh.srt"
    shifted_subs = "tests/test_files/input/bruh_delayed_10_sec.srt"
    expected_audio = "tests/test_files/output/bruh (condensed).flac"
    expected_subs = "tests/test_files/output/bruh (condensed).srt"
    config_content = """
    clean_output_filename = false
    padding = 0

    [condensed_audio]
    enabled = true
    audio_codec = "flac"  # For consistent hashes.
    audio_quality = "0"

    [condensed_subtitles]
    enabled = true
    format = "srt"
    """
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    # Method A: Use original subtitles.
    result_original = run_shuku(
        input_file,
        str(tmp_path / "original"),
        str(config_file),
        args=["--subtitles", original_subs],
    )
    assert result_original.returncode == 0, "shuku failed with original subtitles"
    # Method B: Use shifted subtitles with delay correction.
    result_shifted = run_shuku(
        input_file,
        str(tmp_path / "shifted"),
        str(config_file),
        args=["--subtitles", shifted_subs, "--sub-delay", "-10000"],
    )
    assert result_shifted.returncode == 0, "shuku failed with shifted subtitles"
    output_audio_original = tmp_path / "original" / "bruh (condensed).flac"
    output_audio_shifted = tmp_path / "shifted" / "bruh (condensed).flac"
    output_subs_original = tmp_path / "original" / "bruh (condensed).srt"
    output_subs_shifted = tmp_path / "shifted" / "bruh (condensed).srt"
    # Check files.
    assert output_audio_original.exists(), "Original audio not created"
    assert output_audio_shifted.exists(), "Shifted audio not created"
    assert output_subs_original.exists(), "Original subtitles not created"
    assert output_subs_shifted.exists(), "Shifted subtitles not created"
    # Compare original and shifted outputs (should be identical).
    assert compute_file_hash(str(output_audio_original)) == compute_file_hash(
        str(output_audio_shifted)
    ), "Original and shifted audio outputs differ"
    assert compute_file_hash(str(output_subs_original)) == compute_file_hash(
        str(output_subs_shifted)
    ), "Original and shifted subtitle outputs differ"
    assert compute_file_hash(str(output_subs_original)) == compute_file_hash(
        expected_subs
    ), "Subtitle content differs from expected output"
    # Compare with expected output using size and duration:
    expected_size = Path(expected_audio).stat().st_size
    actual_size = output_audio_original.stat().st_size
    assert (
        abs(actual_size - expected_size) / expected_size < 0.05
    ), "Audio file size differs significantly from expected"
    expected_duration = get_file_duration(expected_audio)
    actual_duration = get_file_duration(str(output_audio_original))
    assert (
        abs(actual_duration - expected_duration) < 0.1
    ), "Audio duration differs significantly from expected"
    # Compare subtitle timings.
    subs1 = pysubs2.load(str(output_subs_original))
    subs2 = pysubs2.load(str(output_subs_shifted))
    for i, (sub1, sub2) in enumerate(zip(subs1, subs2)):
        print(f"\nBruh {i+1}:")
        print(f"Original: {sub1.start/1000:.3f}s - {sub1.end/1000:.3f}s")
        print(f"Shifted:  {sub2.start/1000:.3f}s - {sub2.end/1000:.3f}s")


def test_negative_subtitle_delay(tmp_path):
    """Test that negative subtitle delay clamps timestamps to zero for both start and end times."""
    input_file = (
        "tests/test_files/input/ディスコで超ノリノリのげんげん [ISyLeiYnPx8].mp4"
    )
    input_filename = Path(input_file).stem
    config_content = """
    clean_output_filename = false
    padding = 0
    [condensed_subtitles]
    enabled = true
    format = "srt"
    [condensed_audio]
    enabled = false
    """
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    result = run_shuku(input_file, str(tmp_path), str(config_file))
    assert result.returncode == 0, "shuku failed with original subtitles."
    result_negative = run_shuku(
        input_file,
        str(tmp_path / "negative"),
        str(config_file),
        args=["--sub-delay", "-3000"],
    )
    assert result_negative.returncode == 0, "shuku failed with negative delay."
    negative_subs = pysubs2.load(
        str(tmp_path / "negative" / f"{input_filename} (condensed).srt")
    )
    for sub in negative_subs:
        assert sub.start >= 0, f"Found negative timestamp: {sub.start}"
        assert sub.end >= 0, f"Found negative timestamp: {sub.end}"


def test_process_file_no_segments_after_delay(tmp_path):
    input_file = (
        "tests/test_files/input/ディスコで超ノリノリのげんげん [ISyLeiYnPx8].mp4"
    )
    result = run_shuku(
        input_file=input_file,
        output_dir=str(tmp_path),
        config="",
        args=["--sub-delay", "-300000"],  # Should discard all segments.
    )
    assert result.returncode != 0
    assert "No valid segments found" in result.stderr
    output_base = tmp_path / "ディスコで超ノリノリのげんげん [ISyLeiYnPx8]_condensed"
    assert not output_base.with_suffix(".srt").exists()
    assert not output_base.with_suffix(".flac").exists()
