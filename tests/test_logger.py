import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shuku.cli import format_duration, log_execution_time, parse_arguments
from shuku.logging_setup import (
    DEFAULT_LOG_LEVEL,
    SUCCESS,
    addLoggingLevel,
    setup_initial_logging,
    update_logging_level,
)


def test_add_logging_level():
    assert hasattr(logging, "SUCCESS")
    assert logging.SUCCESS == SUCCESS  # type: ignore
    assert hasattr(logging.getLoggerClass(), "success")
    assert hasattr(logging, "success")


def test_add_logging_level_redefine():
    with pytest.raises(AttributeError) as excinfo:
        addLoggingLevel("SUCCESS", SUCCESS)
    assert "SUCCESS already defined in logging module" in str(excinfo.value)


def test_log_for_level_below_level():
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.WARNING)
    with patch("logging.StreamHandler.emit") as mock_emit:
        logger.success("This message should not appear")  # type: ignore
        assert mock_emit.call_count == 0


def test_log_for_level_success():
    logger = logging.getLogger("test_logger")
    logger.setLevel(SUCCESS)
    logger.propagate = False  # Disable propagation to prevent multiple emits.
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    with patch.object(handler, "emit") as mock_emit:
        logger.success("This is a success message")  # type: ignore
        assert mock_emit.call_count == 1
        assert "This is a success message" in mock_emit.call_args[0][0].getMessage()
    logger.removeHandler(handler)


def test_add_logging_level_methodname_already_defined():
    with pytest.raises(AttributeError) as excinfo:
        addLoggingLevel("NEWLEVEL", SUCCESS, methodName="info")
    assert "info already defined in logging module" in str(excinfo.value)


def test_add_logging_level_methodname_already_defined_in_custom_logger():
    class CustomLogger(logging.Logger):
        def custom_method(self, message, *args, **kwargs):
            pass

    logging.setLoggerClass(CustomLogger)
    with pytest.raises(AttributeError) as excinfo:
        addLoggingLevel("NEWLEVEL", 25, methodName="custom_method")
    assert "custom_method already defined in logger class" in str(excinfo.value)
    logging.setLoggerClass(logging.Logger)


@pytest.mark.parametrize(
    "loglevel, expected_level",
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("success", SUCCESS),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.CRITICAL),
    ],
)
def test_update_logging_level_valid(loglevel, expected_level):
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock_get_logger.return_value
        update_logging_level(loglevel)
        mock_logger.setLevel.assert_called_once_with(expected_level)


def test_update_logging_level_invalid():
    with pytest.raises(ValueError) as excinfo:
        update_logging_level("invalid")
    assert "Invalid loglevel level: 'invalid'" in str(excinfo.value)
    assert "Choose from debug, info, success, warning, error, critical" in str(
        excinfo.value
    )


@pytest.mark.parametrize(
    "args, expected_level, expected_log_file",
    [
        ([], DEFAULT_LOG_LEVEL, None),
        (["--loglevel", "debug"], logging.DEBUG, None),
        (["--loglevel", "info"], logging.INFO, None),
        (["--loglevel", "info", "--log-file", "test.log"], logging.INFO, "test.log"),
        (
            ["--loglevel", "success", "--log-file", "success.log"],
            SUCCESS,
            "success.log",
        ),
        (["--loglevel", "warning"], logging.WARNING, None),
        (["--loglevel", "error"], logging.ERROR, None),
        (["--loglevel", "critical"], logging.CRITICAL, None),
    ],
)
def test_loglevel_control(args, expected_level, expected_log_file):
    with patch("sys.argv", ["shuku"] + args + ["input.mp4"]):
        parsed_args = parse_arguments()
        with (
            patch("logging.getLogger") as mock_get_logger,
            patch("logging.StreamHandler") as mock_stream_handler,
            patch("logging.FileHandler") as mock_file_handler,
        ):
            mock_logger = mock_get_logger.return_value
            setup_initial_logging(parsed_args.loglevel, parsed_args.log_file)
            mock_logger.setLevel.assert_called_with(expected_level)
            assert mock_stream_handler.called
            if expected_log_file:
                mock_file_handler.assert_called_once_with(
                    expected_log_file, encoding="utf-8"
                )
            else:
                mock_file_handler.assert_not_called()


def test_invalid_loglevel_argument():
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["shuku", "--loglevel", "invalid", "input.mp4"]):
            parse_arguments()


def test_loglevel_from_config_and_cli():
    config = {"loglevel": "warning"}
    with patch("sys.argv", ["shuku", "--loglevel", "debug", "input.mp4"]):
        args = parse_arguments()

    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock_get_logger.return_value
        setup_initial_logging()
        update_logging_level(args.loglevel or config["loglevel"])

        mock_logger.setLevel.assert_called_with(
            logging.DEBUG
        )  # CLI should override config.

    # Test config-only scenario.
    with patch("sys.argv", ["shuku", "input.mp4"]):
        args = parse_arguments()
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock_get_logger.return_value
        setup_initial_logging()
        update_logging_level(args.loglevel or config["loglevel"])
        mock_logger.setLevel.assert_called_with(
            logging.WARNING
        )  # Should use config value.


def test_invalid_loglevel_in_config():
    config = {"loglevel": "invalid"}
    with patch("sys.argv", ["shuku", "input.mp4"]):
        args = parse_arguments()
    with pytest.raises(ValueError) as excinfo:
        update_logging_level(args.loglevel or config["loglevel"])
    assert "Invalid loglevel level: 'invalid'" in str(excinfo.value)


def test_log_execution_time_default():
    @log_execution_time()
    def dummy_function():
        time.sleep(0.1)

    with patch("logging.debug") as mock_debug:
        dummy_function()
        mock_debug.assert_called_once()
        assert "dummy_function executed in" in mock_debug.call_args[0][0]
        assert "sec" in mock_debug.call_args[0][0]


def test_log_execution_time_custom_level():
    @log_execution_time(log_level="info")
    def dummy_function():
        time.sleep(0.1)

    with patch("logging.info") as mock_info:
        dummy_function()
        mock_info.assert_called_once()
        assert "dummy_function executed in" in mock_info.call_args[0][0]


def test_log_execution_time_custom_message():
    @log_execution_time(message_template="Custom: {} took {}")
    def dummy_function():
        time.sleep(0.1)

    with patch("logging.debug") as mock_debug:
        dummy_function()
        mock_debug.assert_called_once()
        assert "Custom: dummy_function took" in mock_debug.call_args[0][0]


def test_log_execution_time_return_value():
    @log_execution_time()
    def dummy_function():
        return "test"

    with patch("logging.debug"):
        result = dummy_function()
        assert result == "test"


def test_log_execution_time_exception():
    @log_execution_time()
    def dummy_function():
        raise ValueError("Test exception")

    with patch("logging.debug") as mock_debug:
        with pytest.raises(ValueError):
            dummy_function()
        mock_debug.assert_called_once()
        assert "dummy_function executed in" in mock_debug.call_args[0][0]


@pytest.mark.parametrize("level", ["debug", "info", "warning", "error", "critical"])
def test_log_execution_time_all_levels(level):
    @log_execution_time(log_level=level)
    def dummy_function():
        pass

    with patch(f"logging.{level}") as mock_log:
        dummy_function()
        mock_log.assert_called_once()


def test_setup_initial_logging():
    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("logging.StreamHandler") as mock_stream_handler,
        patch("logging.FileHandler") as mock_file_handler,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        setup_initial_logging()
        mock_logger.setLevel.assert_called_once_with(DEFAULT_LOG_LEVEL)
        assert mock_stream_handler.called
        mock_logger.addHandler.assert_called()
        mock_file_handler.assert_not_called()


def test_setup_initial_logging_with_file():
    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("logging.StreamHandler") as mock_stream_handler,
        patch("logging.FileHandler") as mock_file_handler,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        setup_initial_logging(log_file="test.log")
        mock_logger.setLevel.assert_called_once_with(DEFAULT_LOG_LEVEL)
        assert mock_stream_handler.called
        mock_file_handler.assert_called_once_with("test.log", encoding="utf-8")
        assert mock_logger.addHandler.call_count == 2


@pytest.mark.parametrize(
    "loglevel, expected_level",
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.CRITICAL),
    ],
)
def test_setup_initial_logging_with_loglevel(loglevel, expected_level):
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        setup_initial_logging(loglevel)
        mock_logger.setLevel.assert_called_once_with(expected_level)


def test_setup_initial_logging_valid_level():
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        setup_initial_logging("debug")
        mock_get_logger.assert_called_once()
        mock_logger.setLevel.assert_called_once_with(logging.DEBUG)


def test_log_file_argument():
    with patch("sys.argv", ["shuku", "--log-file", "test.log", "input.mp4"]):
        parsed_args = parse_arguments()
        assert parsed_args.log_file == "test.log"
    with patch("sys.argv", ["shuku", "input.mp4"]):
        parsed_args = parse_arguments()
        assert parsed_args.log_file is None


def test_setup_initial_logging_file_exception():
    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("logging.StreamHandler") as mock_stream_handler,
        patch("logging.FileHandler") as mock_file_handler,
        patch("logging.error") as mock_error,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_file_handler.side_effect = Exception("Mock exception")
        setup_initial_logging(log_file="test.log")
        assert mock_stream_handler.called
        mock_logger.addHandler.assert_called()
        mock_error.assert_called_once_with(
            "Failed to set up file logging to test.log: Mock exception"
        )


@pytest.mark.parametrize(
    "input_seconds, expected_output",
    [
        (0, "0 sec"),
        (1, "1 sec"),
        (59, "59 sec"),
        (60, "1 min"),
        (61, "1 min, 1 sec"),
        (119, "1 min, 59 sec"),
        (120, "2 min"),
        (3599, "59 min, 59 sec"),
        (3600, "1 h"),
        (3601, "1 h, 1 sec"),
        (3661, "1 h, 1 min, 1 sec"),
        (7199, "1 h, 59 min, 59 sec"),
        (7200, "2 h"),
        (7325, "2 h, 2 min, 5 sec"),
        (86400, "24 h"),
        (86401, "24 h, 1 sec"),
    ],
)
def test_format_duration(input_seconds, expected_output):
    assert format_duration(input_seconds) == expected_output
