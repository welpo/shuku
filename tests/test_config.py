import logging
import os
import tomllib
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from shuku.config import (
    CONFIG_FILENAME,
    CONFIG_OPTIONS,
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_HEADER,
    ConfigItem,
    ConfigValidationError,
    dump_default_config,
    generate_config_content,
    generate_item_content,
    get_default_config_path,
    load_config,
    resolve_aliases,
    validate_bitrate_or_scale,
    validate_config,
)
from shuku.utils import PROGRAM_NAME


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


def test_load_config_with_missing_file(caplog):
    missing_file_path = "nonexistent_config.toml"
    with patch("os.path.exists", return_value=False):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                load_config(missing_file_path)
    assert "file not found" in caplog.text.lower()
    assert missing_file_path in caplog.text


def test_all_condensing_options_disabled(caplog):
    config = {
        "condensed_audio.enabled": False,
        "condensed_subtitles.enabled": False,
        "condensed_video.enabled": False,
    }
    with pytest.raises(SystemExit) as exc_info:
        validate_config(config)
    assert exc_info.value.code == 1
    assert "All condensing options are disabled. Nothing to do." in caplog.text


def test_unknown_field(caplog):
    config = {"condensed_audio.enabled": True, "unknown_field": "value"}
    with pytest.raises(SystemExit) as exc_info:
        validate_config(config)
    assert exc_info.value.code == 1
    assert "Unknown configuration key" in caplog.text
    assert "unknown_field" in caplog.text


def test_nested_invalid_setting(caplog):
    config = {
        "condensed_audio.enabled": True,
        "condensed_subtitles.obama": "value",
    }
    with pytest.raises(SystemExit) as exc_info:
        validate_config(config)
    assert exc_info.value.code == 1
    assert "Unknown configuration key" in caplog.text
    assert "condensed_subtitles.obama" in caplog.text


def test_multiple_unknown_fields(caplog):
    config = {
        "condensed_audio.enabled": True,
        "unknown_field1": "value1",
        "unknown_field2": "value2",
    }
    with pytest.raises(SystemExit) as exc_info:
        validate_config(config)
    assert exc_info.value.code == 1
    assert "Unknown configuration key" in caplog.text
    assert "unknown_field1" in caplog.text
    assert "unknown_field2" in caplog.text


def test_load_config_no_file():
    with patch("logging.warning") as mock_warning:
        config = load_config("")
        assert mock_warning.called, "Warning was not logged"
        warning_message = mock_warning.call_args[0][0]
        assert "Using default configuration" in warning_message
    assert config == {key: item.default_value for key, item in CONFIG_OPTIONS.items()}


@pytest.mark.parametrize(
    "test_config, error_check",
    [
        (
            {
                "condensed_audio.enabled": False,
                "condensed_subtitles.enabled": False,
                "condensed_video.enabled": False,
            },
            lambda msg: "condensing options are disabled" in msg.lower(),
        ),
        (
            {"condensed_audio.enabled": True, "unknown_key": "value"},
            lambda msg: "unknown_key" in msg,
        ),
        (
            {
                "condensed_audio.enabled": True,
                "condensed_audio.audio_codec": "invalid_codec",
            },
            lambda msg: "condensed_audio.audio_codec" in msg
            and "Must be one of" in msg,
        ),
        (
            {"condensed_audio.enabled": True, "audio_languages": [1, 2, 3]},
            lambda msg: "audio_languages" in msg,
        ),
        (
            {"condensed_audio.enabled": True, "padding": "not_a_number"},
            lambda msg: "padding" in msg,
        ),
        (
            {"condensed_audio.enabled": True, "loglevel": "invalid_level"},
            lambda msg: "loglevel" in msg and "Must be one of" in msg,
        ),
    ],
)
def test_validate_config_failures(test_config, error_check, caplog):
    full_config = {key: item.default_value for key, item in CONFIG_OPTIONS.items()}
    full_config.update(test_config)
    with pytest.raises(SystemExit) as exc_info:
        with caplog.at_level(logging.ERROR):
            validate_config(full_config)
    assert exc_info.value.code == 1
    error_message = caplog.text
    assert error_check(error_message), f"Unexpected error message: {error_message}"


def test_valid_config():
    config = {
        "condensed_audio.enabled": True,
        "condensed_audio.audio_codec": "libmp3lame",
        "padding": 0.5,
    }
    validate_config(config)


def test_default_config_is_valid():
    validate_config(DEFAULT_CONFIG)


def test_resolve_aliases():
    test_config = {
        "condensed_audio.audio_codec": "mp3",
        "condensed_audio.enabled": True,
    }
    resolved_config = resolve_aliases(test_config)
    assert resolved_config["condensed_audio.audio_codec"] == "libmp3lame"
    assert resolved_config["condensed_audio.enabled"] == True


@pytest.mark.parametrize(
    "test_config, expected_value",
    [
        ({"condensed_audio.audio_codec": "mp3"}, "libmp3lame"),
        ({"condensed_audio.audio_codec": "wav"}, "pcm_s16le"),
        ({"condensed_audio.audio_codec": "opus"}, "libopus"),
        ({"condensed_audio.audio_codec": "aac"}, "aac"),
    ],
)
def test_condensed_audio_codec_aliases(test_config, expected_value):
    full_config = {key: item.default_value for key, item in CONFIG_OPTIONS.items()}
    full_config.update(test_config)
    resolved_config = resolve_aliases(full_config)
    assert resolved_config["condensed_audio.audio_codec"] == expected_value


def test_validate_config_with_invalid_alias(caplog):
    config = {key: item.default_value for key, item in CONFIG_OPTIONS.items()}
    config["condensed_audio.audio_codec"] = "invalid_alias"
    config["condensed_audio.enabled"] = True
    with pytest.raises(SystemExit) as exc_info:
        with caplog.at_level(logging.ERROR):
            validate_config(config)
    assert exc_info.value.code == 1
    assert "Invalid value for condensed_audio.audio_codec" in caplog.text
    assert "mp3" in caplog.text  # Aliases should appear as a valid value.
    assert "wav" in caplog.text
    assert "libmp3lame" in caplog.text


def test_config_loading_with_aliases(tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.toml"
    config_content = """
    [condensed_audio]
    audio_codec = "mp3"
    enabled = true
    """
    config_file.write_text(config_content)
    loaded_config = load_config(str(config_file))
    assert loaded_config["condensed_audio.audio_codec"] == "libmp3lame"
    assert loaded_config["condensed_audio.enabled"] == True
    assert "condensed_subtitles.enabled" in loaded_config


def test_resolve_aliases_with_unknown_key():
    test_config = {"condensed_audio.audio_codec": "mp3", "unknown_key": "some_value"}
    resolved_config = resolve_aliases(test_config)
    assert resolved_config["condensed_audio.audio_codec"] == "libmp3lame"
    assert resolved_config["unknown_key"] == "some_value"
    assert "unknown_key" in resolved_config


@pytest.mark.parametrize(
    "system, env_vars, expected_path",
    [
        (
            "Windows",
            {"APPDATA": r"C:\Users\TestUser\AppData\Roaming"},
            Path(r"C:\Users\TestUser\AppData\Roaming") / PROGRAM_NAME / CONFIG_FILENAME,
        ),
        (
            "Linux",
            {"XDG_CONFIG_HOME": "/opt/custom_config"},
            Path("/opt/custom_config") / PROGRAM_NAME / CONFIG_FILENAME,
        ),
        (
            "Linux",
            {},  # Unset XDG_CONFIG_HOME.
            Path.home() / ".config" / PROGRAM_NAME / CONFIG_FILENAME,
        ),
        (
            "Darwin",  # macOS.
            {"XDG_CONFIG_HOME": "/Users/testuser/.config"},
            Path("/Users/testuser/.config") / PROGRAM_NAME / CONFIG_FILENAME,
        ),
    ],
)
def test_get_default_config_path(system, env_vars, expected_path):
    with patch.dict(os.environ, env_vars, clear=True):
        with patch("platform.system", return_value=system):
            result = get_default_config_path()
            assert result == expected_path


def test_get_default_config_path_windows_no_appdata():
    with patch.dict(os.environ, {}, clear=True):
        with patch("platform.system", return_value="Windows"):
            with pytest.raises(
                EnvironmentError, match="APPDATA environment variable is not set"
            ):
                get_default_config_path()


def test_generate_config_content():
    content = generate_config_content()
    assert content.startswith(DEFAULT_CONFIG_HEADER.rstrip("\n"))
    # Check all CONFIG_OPTIONS are present.
    for key, item in CONFIG_OPTIONS.items():
        parts = key.split(".")
        if len(parts) > 1:
            # Nested option.
            section = parts[0]
            subkey = ".".join(parts[1:])
            assert f"[{section}]" in content
            assert subkey in content
        else:
            # Top-level option.
            assert key in content
        assert item.description in content
        # Check choices are listed.
        if item.choices or item.aliases:
            choices = list(map(str, item.choices or []))
            for alias, value in (item.aliases or {}).items():
                choices.append(f"{alias} (alias for {value})")
            choices_line = f"# Choices: {', '.join(choices)}"
            assert choices_line in content
        # Check default values.
        if item.default_value is None:
            assert "None" not in content
        elif isinstance(item.default_value, bool):
            assert f"{parts[-1]} = {str(item.default_value).lower()}" in content
        elif key == "line_skip_patterns":
            assert f"{parts[-1]} = [" in content
            for pattern in item.default_value:
                assert repr(pattern) in content
            assert "]" in content
        else:
            assert f"{parts[-1]} = {repr(item.default_value)}" in content
    # Check the file ends with a single newline.
    assert content.endswith("\n")
    assert not content.endswith("\n\n")


@pytest.fixture
def mock_default_config_path(tmp_path):
    return tmp_path / "config" / CONFIG_FILENAME


@pytest.fixture
def mock_generate_content():
    return "Mock config content"


def test_dump_default_config_io_error(
    capsys, mock_default_config_path, mock_generate_content
):
    with (
        patch(
            "shuku.config.get_default_config_path",
            return_value=mock_default_config_path,
        ),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.mkdir", side_effect=IOError("Permission denied")),
        patch("logging.error") as mock_error,
        pytest.raises(SystemExit) as exc_info,
    ):
        dump_default_config()
    assert exc_info.value.code == 1
    mock_error.assert_called_once_with(
        "Error creating configuration file: Permission denied"
    )


def test_dump_default_config_long_path(mock_default_config_path, mock_generate_content):
    long_path = Path("a" * 555) / CONFIG_FILENAME
    with (
        patch("shuku.config.get_default_config_path", return_value=long_path),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.exists", side_effect=OSError("File name too long")),
        patch("logging.error") as mock_error,
        pytest.raises(SystemExit) as exc_info,
    ):
        dump_default_config()
    assert exc_info.value.code == 1
    error_message = mock_error.call_args[0][0]
    assert "Error creating configuration file" in error_message
    assert "File name too long" in error_message


def test_dump_default_config_unicode_path(
    mock_default_config_path, mock_generate_content
):
    unicode_path = Path("测试路径") / CONFIG_FILENAME
    with (
        patch("shuku.config.get_default_config_path", return_value=unicode_path),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.mkdir"),
        patch("builtins.open", mock_open()) as mock_file,
    ):
        dump_default_config()
    mock_file.assert_called_once_with(unicode_path, "w", encoding="utf-8")


def test_dump_default_config_disk_full_error(
    mock_default_config_path, mock_generate_content
):
    with (
        patch(
            "shuku.config.get_default_config_path",
            return_value=mock_default_config_path,
        ),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.mkdir"),
        patch("builtins.open", mock_open()) as mock_file,
    ):
        mock_file.return_value.write.side_effect = IOError("No space left on device")
        with (
            patch("logging.error") as mock_error,
            pytest.raises(SystemExit) as exc_info,
        ):
            dump_default_config()
    assert exc_info.value.code == 1
    mock_error.assert_called_once_with(
        "Error creating configuration file: No space left on device"
    )


def test_dump_default_config_parent_directory_creation(
    mock_default_config_path, mock_generate_content
):
    with patch(
        "shuku.config.get_default_config_path", return_value=mock_default_config_path
    ):
        with patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                with patch("builtins.open", mock_open()):
                    dump_default_config()

                    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_dump_default_config_existing_file_overwrite(
    mock_default_config_path, mock_generate_content
):
    mock_prompt = Mock(return_value="overwrite")
    with (
        patch(
            "shuku.config.get_default_config_path",
            return_value=mock_default_config_path,
        ),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.exists", return_value=True),
        patch("shuku.config.prompt_user_choice", mock_prompt),
        patch("builtins.open", mock_open()) as mock_file,
    ):
        dump_default_config()
        mock_prompt.assert_called_once_with(
            f"{mock_default_config_path} already exists.",
            ["overwrite", "cancel"],
            default="Cancel",
        )
        mock_file.assert_called_once_with(
            mock_default_config_path, "w", encoding="utf-8"
        )
        mock_file().write.assert_called_once_with(mock_generate_content)


def test_dump_default_config_existing_file_cancel(
    mock_default_config_path, mock_generate_content
):
    mock_prompt = Mock(return_value="cancel")
    with (
        patch(
            "shuku.config.get_default_config_path",
            return_value=mock_default_config_path,
        ),
        patch(
            "shuku.config.generate_config_content", return_value=mock_generate_content
        ),
        patch("pathlib.Path.exists", return_value=True),
        patch("shuku.config.prompt_user_choice", mock_prompt),
        patch("builtins.open", mock_open()) as mock_file,
        patch("logging.warning") as mock_warning,
    ):
        with pytest.raises(SystemExit) as excinfo:
            dump_default_config()
        assert excinfo.value.code == 0
        mock_prompt.assert_called_once_with(
            f"{mock_default_config_path} already exists.",
            ["overwrite", "cancel"],
            default="Cancel",
        )
        mock_file.assert_not_called()
        mock_warning.assert_called_once()
        assert "cancelled" in mock_warning.call_args[0][0].lower()


@pytest.fixture
def config_file(tmp_path):
    def _create_file(content, permissions):
        file_path = tmp_path / "test_config.toml"
        with open(file_path, "w") as f:
            f.write(content)
        os.chmod(file_path, permissions)
        return file_path

    return _create_file


def test_read_config_file_with_restricted_permissions(config_file):
    content = """
    condensed_audio.enabled = true
    condensed_audio.audio_codec = "libmp3lame"
    """
    file_path = config_file(content, 0o444)
    result = load_config(str(file_path))
    assert result["condensed_audio.enabled"] is True
    assert result["condensed_audio.audio_codec"] == "libmp3lame"


def test_empty_config_file_loads_defaults(tmp_path):
    config_file = tmp_path / "empty_config.toml"
    config_file.touch()
    result = load_config(str(config_file))
    assert result == DEFAULT_CONFIG


def test_load_config_uses_default_path(tmp_path, caplog):
    default_config_path = tmp_path / "default_config.toml"
    with open(default_config_path, "w") as f:
        f.write("condensed_audio.enabled = true\n")
    with patch(
        "shuku.config.get_default_config_path", return_value=default_config_path
    ):
        with caplog.at_level(logging.DEBUG):
            result = load_config()
    assert result["condensed_audio.enabled"] is True
    assert f"Using config file: {default_config_path}" in caplog.text


@pytest.mark.parametrize("config_path", [None, "none", "NONE"])
def test_load_config_no_config_file(config_path, caplog):
    with patch(
        "shuku.config.get_default_config_path", return_value=Path("/non_existent_path")
    ):
        with caplog.at_level(logging.INFO):
            result = load_config(config_path)
    assert result == DEFAULT_CONFIG
    if config_path and config_path.lower() == "none":
        assert "Config path set to 'none'. Using default configuration." in caplog.text
    else:
        assert "No config file found. Using default configuration." in caplog.text


@pytest.mark.parametrize("config_type", ["audio", "video"])
@pytest.mark.parametrize(
    "codec,quality,should_pass",
    [
        # mp3.
        ("libmp3lame", "128k", True),
        ("libmp3lame", "0", True),
        ("libmp3lame", "V0", True),
        ("libmp3lame", "9", True),
        ("libmp3lame", 9, True),
        ("libmp3lame", "V9", True),
        ("libmp3lame", "v9", True),
        ("libmp3lame", "w9", False),
        ("libmp3lame", "invalid", False),
        ("libmp3lame", "10", True),  # Logs a warning.
        ("libmp3lame", "V10", True),
        # aac.
        ("aac", "128k", True),
        ("aac", "1", True),
        ("aac", 1, True),
        ("aac", "5", True),
        ("aac", "invalid", False),
        ("aac", 6, True),
        ("aac", "6", True),
        ("aac", "V6", False),
        # libopus.
        ("libopus", "64k", True),
        ("libopus", "0", True),
        ("libopus", "10", True),
        ("libopus", "invalid", False),
        ("libopus", "128k", True),
        ("libopus", "1228k", True),
        ("libopus", "300k", True),
        ("libopus", "11", True),
        ("libopus", "V0", False),
        ("libopus", "V-1", False),
        ("libopus", "-1", False),
        # flac.
        ("flac", "0", True),
        ("flac", 8, True),
        ("flac", "invalid", False),
        ("flac", "9", True),
        ("flac", 10, True),
        ("flac", "-2", False),
        ("flac", "V2", False),
        # wav.
        ("pcm_s16le", None, True),
        ("pcm_s16le", "any_value", True),  # quality is ignored.
        ("pcm_s16le", "V0", True),
        # copy.
        ("copy", None, True),
        ("copy", "any_value", True),
        ("copy", "V0", True),  # quality is ignored.
    ],
)
def test_audio_codec_quality(config_type, codec, quality, should_pass):
    config = {
        f"condensed_{config_type}.enabled": True,
        f"condensed_{config_type}.audio_codec": codec,
        f"condensed_{config_type}.audio_quality": quality,
    }
    if should_pass:
        validate_config(config)
    else:
        with pytest.raises(ConfigValidationError):
            validate_config(config)


@pytest.mark.parametrize(
    "codec,quality,expected_warning",
    [
        ("libmp3lame", "7k", "Unusual bitrate"),
        ("libmp3lame", "1001k", "Unusual bitrate"),
        ("aac", "5k", "Unusual bitrate"),
        ("aac", "2000k", "Unusual bitrate"),
        ("libopus", "3k", "Unusual bitrate"),
        ("libopus", "1500k", "Unusual bitrate"),
        ("libmp3lame", "10", "unusually high"),
        ("libmp3lame", 10, "unusually high"),
        ("aac", "11", "unusually high"),
        ("aac", 11, "unusually high"),
        ("libopus", "11", "unusually high"),
        ("libopus", 11, "unusually high"),
        ("libmp3lame", "V10", "unusually high"),
        ("libmp3lame", "v11", "unusually high"),
        ("libmp3lame", "128k", None),
        ("libmp3lame", "320k", None),
    ],
)
def test_warnings(codec, quality, expected_warning, caplog):
    caplog.set_level(logging.WARNING)
    validate_bitrate_or_scale(codec, quality)
    if expected_warning is None:
        assert len(caplog.records) == 0, f"Unexpected warning(s) found: {caplog.text}"
    else:
        assert any(
            expected_warning in record.message for record in caplog.records
        ), f"Expected warning '{expected_warning}' not found in log messages"


@pytest.mark.parametrize(
    "codec,quality,expected_error",
    [
        ("libmp3lame", "-1", "Negative quality value"),
        ("aac", "V0", "not supported"),
        ("libopus", "invalid", "Invalid quality"),
    ],
)
def test_validation_errors(codec, quality, expected_error):
    with pytest.raises(ConfigValidationError) as exc_info:
        validate_bitrate_or_scale(codec, quality)
    assert expected_error in str(exc_info.value)


def test_generate_item_content_with_dict_default_value():
    key = "my_key"
    item = ConfigItem(
        description="My description",
        default_value={"key1": "value1", "key2": 42},
        example_value={"example_key": "example_value"},
    )
    result = generate_item_content(key, item)
    expected_output = """# My description
my_key = { "key1" = 'value1', "key2" = 42 }

"""
    assert result == expected_output
