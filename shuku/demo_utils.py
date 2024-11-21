import json
import logging
import os
import sys
from typing import Any

from shuku.cli import Context

JSON_OUTPUT_FOLDER = os.path.expanduser("~/Desktop/JSON_timings")


# Function to save segments as JSON for the demo video.
def save_segments_as_json(
    context: Context,
    segments: list[tuple[float, float]],
) -> None:
    os.makedirs(JSON_OUTPUT_FOLDER, exist_ok=True)
    original_filename = os.path.basename(context.file_path)
    json_filename = f"{os.path.splitext(original_filename)[0]} segments.json"
    json_path = os.path.join(JSON_OUTPUT_FOLDER, json_filename)
    duration = get_video_duration(context.stream_info)
    data = {
        "totalDuration": duration,
        "segments": [
            {"start": start, "duration": end - start} for start, end in segments
        ],
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    logging.info(f"Speech segments JSON saved to: {json_path}")


def get_video_duration(stream_info: dict[str, Any]) -> float:
    video_stream = stream_info["video"][0]
    duration_str = video_stream["tags"].get("DURATION", "00:00:00.000000000")
    hours, minutes, seconds = map(float, duration_str.split(":"))
    return hours * 3600 + minutes * 60 + seconds
