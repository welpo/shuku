import logging
import os
import sys
from typing import Optional

PROGRAM_NAME = "shuku"
PROGRAM_TAGLINE = "Shrink media to keep only the dialogue."
REPOSITORY = f"https://github.com/welpo/{PROGRAM_NAME}"

MAX_PROMPT_LENGTH = 50


def exit_if_file_missing(file_path: str) -> None:
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        sys.exit(1)


def prompt_user_choice(prompt: str, choices: list[str], default: str) -> str:
    options = format_choices(choices)
    default_choice = find_default_choice(choices, default)
    separator = "\n" if len(prompt) > MAX_PROMPT_LENGTH else " "
    full_prompt = f"{prompt}{separator}{options}? (default: {default_choice}): "
    while True:
        user_input = input(full_prompt).strip().lower()
        if user_input == "":
            return default.lower()
        if is_valid_choice(user_input, choices):
            return next(
                choice.lower()
                for choice in choices
                if choice.lower().startswith(user_input)
            )
        print(
            f"Invalid selection. Please choose from: {', '.join(choice[0].lower() for choice in choices)}, "
            f"or press Enter for default ({default_choice})."
        )


def format_choices(choices: list[str]) -> str:
    formatted = [f"[{choice[0].upper()}]{choice[1:]}" for choice in choices]
    return (
        ", ".join(formatted[:-1]) + f" or {formatted[-1]}"
        if len(choices) > 1
        else formatted[0]
    )


def find_default_choice(choices: list[str], default: str) -> Optional[str]:
    return next(
        (choice for choice in choices if choice.lower() == default.lower()), None
    )


def is_valid_choice(user_input: str, choices: list[str]) -> bool:
    return any(user_input == choice[0].lower() for choice in choices)
