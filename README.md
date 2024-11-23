<p align="center">
    <a href="CONTRIBUTING.md#pull-requests">
        <img src="https://img.shields.io/badge/PRs-welcome-0?style=flat-square&labelColor=202b2d&color=3b5669" alt="PRs welcome"></a>
    <a href="https://pypi.org/project/shuku/">
         <img src="https://img.shields.io/pypi/v/shuku?style=flat-square&labelColor=202b2d&color=3b5669" alt="PyPI version"></a>
    <a href="https://github.com/welpo/shuku/releases">
        <img src="https://img.shields.io/github/v/release/welpo/shuku?style=flat-square&labelColor=202b2d&color=3b5669" alt="Latest release"></a>
    <a href="https://codecov.io/gh/welpo/shuku">
        <img src="https://img.shields.io/codecov/c/gh/welpo/shuku?style=flat-square&labelColor=202b2d&color=3b5669" alt="Codecov"></a>
    <a href="https://github.com/welpo/shuku/actions/workflows/ci.yml">
        <img src="https://img.shields.io/github/actions/workflow/status/welpo/shuku/.github%2Fworkflows%2Fci.yml?label=CI&style=flat-square&labelColor=202b2d&color=3b5669" alt="Continuous Integration"></a>
    <a href="https://github.com/welpo/shuku/actions/workflows/cd.yml">
        <img src="https://img.shields.io/github/actions/workflow/status/welpo/shuku/.github%2Fworkflows%2Fcd.yml?label=CD&style=flat-square&labelColor=202b2d&color=3b5669" alt="Continuous Deployment"></a>
    <a href="https://pypi.org/project/shuku/">
        <img src="https://img.shields.io/pypi/pyversions/shuku?style=flat-square&labelColor=202b2d&color=3b5669" alt="Python versions"></a>
    <a href="https://github.com/psf/black">
        <img src="https://img.shields.io/badge/code_style-black-000000?style=flat-square&labelColor=202b2d&color=black" alt="Code style: black"></a>
    <a href="https://github.com/welpo/shuku/blob/main/COPYING">
        <img src="https://img.shields.io/github/license/welpo/shuku?style=flat-square&labelColor=202b2d&color=3b5669" alt="License"></a>
    <a href="https://github.com/welpo/git-sumi">
        <img src="https://img.shields.io/badge/clean_commits-git--sumi-0?style=flat-square&labelColor=202b2d&color=3b5669" alt="Clean commits"></a>
    <br><br>
    <img src="https://raw.githubusercontent.com/welpo/shuku/main/assets/shuku-logo.png" width="300" alt="shuku logo: stylised bonsai tree with speech bubble leaves in a circular frame, set against pastel hills">
</p>

<h1 align="center">shuku</h1>

<h3 align="center">Shrink media to keep only the dialogue.</h3>

<p align="center">
  <img src="https://raw.githubusercontent.com/welpo/shuku/main/assets/animation_demo/shuku_demo.gif" alt="shuku demo">
</p>

<p align="center">
   shuku — from <ruby><rb>縮</rb><rt>しゅく</rt></ruby><ruby><rb>小</rb><rt>しょう</rt></ruby>: "minification"
</p>

Designed for language learners, `shuku` creates dialogue-only versions of media (show episodes, films, or YouTube videos) using subtitles. Useful to revisit content efficiently and improve comprehension.

https://github.com/user-attachments/assets/ae06b259-7043-423a-8895-5e8a60a32e37

## Table of contents

- [Features](#features)
- [Comparison with similar tools](#comparison-with-similar-tools)
- [Installation](#installation)
- [Usage](#quick-start)
- [Configuration](#configuration)
  - [General options](#general-options)
  - [Condensed audio options](#condensed-audio-options)
  - [Condensed video options](#condensed-video-options)
  - [Condensed subtitles options](#condensed-subtitles-options)
  - [Audio quality settings](#audio-quality-settings)
- [Command line options](#command-line-options)
- [Examples](#examples)
- [Support](#support)
- [Contributing](#contributing)
- [License](#license)

## Features

- Create condensed audio, video, and subtitle files based on dialogue
- Multiplatform support: GNU+Linux, macOS, and Windows
- Extensive configuration options, including codec, quality, and custom FFmpeg arguments
- Smart audio/subtitle track selection
- Fuzzy matching for external subtitles
- Pad subtitle timings for context and smoother transitions
- Shift subtitle timing without extra tools
- Skip unwanted subtitle lines (e.g., lyrics or sound effects)
- Skip chapters (e.g., openings, previews, credits)
- Smart metadata extraction (season, episode, title)
- Logging and progress tracking
- Generate LRC files from subtitles to use with music players
- Batch processing of multiple files and directories

## Comparison with similar tools

| Feature | [shuku](#comparison-with-other-tools) | [impd](https://github.com/Ajatt-Tools/impd) | [Condenser](https://github.com/ercanserteli/condenser) |
|---------|:-------:|:------:|:-----------:|
| **Platform support** |
| GNU+Linux | ✅ | ✅ | ❌ |
| macOS | ✅ | ❌ | ❌ |
| Windows | ✅ | ❌ | ✅ |
| **Output** |
| Condensed audio | ✅ | ✅ | ✅ |
| Condensed subtitles | ✅ | ❌ | ✅ |
| Condensed video | ✅ | ❌ | ❌ |
| **Subtitle handling** |
| Support internal and external subs | ✅ | ✅ | ✅ |
| [Fuzzy subtitle search](#external_subtitle_search) | ✅ | ❌ | ❌ |
| [Language preference settings](#subtitle_languages) | ✅ | ✅ | ❌ |
| [Subtitle timing padding](#padding) | ✅ | ✅ | ✅ |
| [Shift subtitle timing](#--sub-delay-ms) | ✅ | ❌ | ❌ |
| [Skip chapters (credits, opening…)](#skip_chapters) | ✅ | ❌ | ❌ |
| [Skip subtitle lines based on patterns](#line_skip_patterns) | Unlimited patterns | One pattern | Filters content in parentheses & list of characters |
| **File management** |
| [Clean filenames](#clean_output_filename) | ✅ | ❌ | ❌ |
| [Custom filename suffix](#output_suffix) | ✅ | ❌ | ✅ |
| YouTube video processing | ❌ | ✅ | ❌ |
| Playlist management | ❌ | ✅ | ❌ |
| Automatic archiving of old files | ❌ | ✅ | ❌ |
| **User interface** |
| Graphical user interface | ❌ | ❌ | For user prompts |
| Command line interface | ✅ | ✅ | ✅ |
| **Configuration** |
| [Custom codec](#audio_codec) | ✅ | ❌ | ✅ |
| [Custom quality](#audio-quality-settings) | ✅ | ❌ | ❌ |
| [Custom ffmpeg arguments](#custom_ffmpeg_args) | ✅ | ✅ | ❌ |
| [Can extract without reencoding](#copy) | ✅ | ❌ | ❌ |
| Configuration format | TOML | Key-value | JSON |
| **Metadata** |
| Automatic metadata generation | ✅ | ✅ | ❌ |
| Episode number | ✅ | ✅ | ❌ |
| Season number | ✅ | ❌ | ❌ |
| Clean media title | ✅ | ❌ | ❌ |
| **Repository metrics** |
| License | [![License](https://img.shields.io/github/license/welpo/shuku?style=flat-square)](https://github.com/welpo/shuku/blob/main/COPYING) | [![License](https://img.shields.io/github/license/Ajatt-Tools/impd?style=flat-square)](https://github.com/Ajatt-Tools/impd/blob/master/LICENSE) | [![License](https://img.shields.io/github/license/ercanserteli/condenser?style=flat-square)](https://github.com/ercanserteli/condenser/blob/master/LICENSE) |
| Stars | [![Stars](https://img.shields.io/github/stars/welpo/shuku?style=flat-square)](https://github.com/welpo/shuku/stargazers) | [![Stars](https://img.shields.io/github/stars/Ajatt-Tools/impd?style=flat-square)](https://github.com/Ajatt-Tools/impd/stargazers) | [![Stars](https://img.shields.io/github/stars/ercanserteli/condenser?style=flat-square)](https://github.com/ercanserteli/condenser/stargazers) |
| Contributors | [![Contributors](https://img.shields.io/github/contributors/welpo/shuku?style=flat-square)](https://github.com/welpo/shuku/graphs/contributors) | [![Contributors](https://img.shields.io/github/contributors/Ajatt-Tools/impd?style=flat-square)](https://github.com/Ajatt-Tools/impd/graphs/contributors) | [![Contributors](https://img.shields.io/github/contributors/ercanserteli/condenser?style=flat-square)](https://github.com/ercanserteli/condenser/graphs/contributors) |
| Last Commit | [![Last Commit](https://img.shields.io/github/last-commit/welpo/shuku?style=flat-square)](https://github.com/welpo/shuku/commits) | [![Last Commit](https://img.shields.io/github/last-commit/Ajatt-Tools/impd?style=flat-square)](https://github.com/Ajatt-Tools/impd/commits) | [![Last Commit](https://img.shields.io/github/last-commit/ercanserteli/condenser?style=flat-square)](https://github.com/ercanserteli/condenser/commits) |
| Language | [![Top Language](https://img.shields.io/github/languages/top/welpo/shuku?style=flat-square)](https://github.com/welpo/shuku/search?l=python) | [![Top Language](https://img.shields.io/github/languages/top/Ajatt-Tools/impd?style=flat-square)](https://github.com/Ajatt-Tools/impd/search?l=shell) | [![Top Language](https://img.shields.io/github/languages/top/ercanserteli/condenser?style=flat-square)](https://github.com/ercanserteli/condenser/search?l=python) |
| Code Coverage | [![Code Coverage](https://img.shields.io/codecov/c/gh/welpo/shuku?style=flat-square)](https://codecov.io/gh/welpo/shuku) | ![Code Coverage](https://img.shields.io/codecov/c/gh/Ajatt-Tools/impd?style=flat-square) | [![Code Coverage](https://img.shields.io/codecov/c/gh/ercanserteli/condenser?style=flat-square)](https://codecov.io/gh/ercanserteli/condenser) |

> [!IMPORTANT]
> If you feel the comparisons are incomplete or unfair, please [file an issue](https://github.com/welpo/shuku/issues/new?&labels=bug&template=2_bug_report.yml) so this page can be improved. Even better, submit a pull request!

## Installation

1. Make sure FFmpeg is installed on your system. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html) or install it using your package manager:

   ```bash
   # Debian, Linux Mint, Ubuntu…
   sudo apt install ffmpeg

   # Arch Linux, Manjaro…
   sudo pacman -S ffmpeg

   # macOS with brew (https://brew.sh/)
   brew install ffmpeg
   ```

For Windows, here's [a good guide](https://phoenixnap.com/kb/ffmpeg-windows).

2. Install shuku with [pipx](https://github.com/pypa/pipx) (recommended) or pip:

   ```bash
   pipx install shuku
   # or
   pip install shuku
   ```

Alternatively, download a [pre-built binary](https://github.com/welpo/shuku/releases).

## Quick start

If you run:

```bash
shuku video.mkv
```

`shuku` will create `video (condensed).ogg` containing only the dialog from the video, next to the original file.

For this to work, `video.mp4` must either have internal subtitles, or a matching subtitle file in the same directory.

## Configuration

To dump the default configuration, run:

```bash
shuku --init
```

This will create a `shuku.toml` file in your system's default configuration directory:

- On Windows: `%APPDATA%\shuku\shuku.toml`
- On Unix-like systems (GNU+Linux, macOS):
  - By default: `~/.config/shuku/shuku.toml`
  - If `XDG_CONFIG_HOME` is set: `$XDG_CONFIG_HOME/shuku/shuku.toml`

The configuration file is self-documented and should be easy to understand.

The options are split into four categories: general options, condensed audio options, condensed video options, and condensed subtitles options.

### General options

#### `loglevel`

Sets the verbosity of log messages. Only messages of the selected level or higher will be displayed.

Default: `'info'`
Choices: `debug`, `info`, `success`, `warning`, `error`, `critical`

#### `clean_output_filename`

If `true`, removes quality indicators, release group tags, and other technical information from output filenames. For example, `[GROUP] Show.S01E01.1080p.x264-GROUP.mkv` becomes `Show S01E01.ext` (where `.ext` is `.ogg`, `.srt`, etc.).

Default: `true`.

#### `output_directory`

Specifies the directory where output files will be saved. If not set, outputs to the same directory as the input file.

#### `output_suffix`

The suffix added to output files.

Default: `' (condensed)'`

#### `if_file_exists`

What to do when output file exists. Can be:

- `'ask'`: Prompt user to overwrite, rename, or skip
- `'overwrite'`: Overwrite without prompting
- `'rename'`: Automatically rename with timestamp
- `'skip'`: Skip without prompting

Default: `'ask'`

#### `padding`

The number of seconds to add before and after each subtitle timing.

Default: `0.5`

#### `subtitle_directory`

Specifies a directory to search for external subtitle files. Overridden by the `--subtitles` command-line argument.

#### `audio_languages`

Specifies preferred languages for audio tracks, in order of preference.

Example: `['jpn', 'jp', 'ja', 'eng']`

#### `subtitle_languages`

Specifies preferred languages for subtitle tracks, in order of preference.

Example: `['jpn', 'jp', 'ja', 'eng']`

#### `external_subtitle_search`

Determines how external subtitles are matched to video files. `disabled` turns off external subtitle search, `exact` requires perfect filename matches, and `fuzzy` allows for inexact matches.

Default: `'fuzzy'`

#### `subtitle_match_threshold`

When using fuzzy matching, this sets the minimum similarity score for subtitle files. Lower values allow more lenient matching but risk false positives.

Default: `0.6`

#### `skip_chapters`

A list of chapter titles to skip when processing. Case-insensitive. Useful for skipping openings, previews, credits…

Default:

```toml
skip_chapters = ['avant', '1. opening credits', 'logos/opening credits', 'opening titles', 'opening', 'op', 'ending', 'ed', 'start credit', 'credits', 'end credits', 'end credit', 'closing credits', 'next episode', 'preview', 'avante', 'trailer']
```

#### `line_skip_patterns`

Regular expression patterns for subtitle lines to skip. Useful for removing song lyrics, sound effects, etc. Use single quotes to enclose patterns.

Default:

```toml
line_skip_patterns = [
  # Skip music.
  '^(～|〜)?♪.*',
  '^♬(～|〜)$',
  '^♪?(～|〜)♪?$',
  # Skip lines containing only '・～'
  '^・(～|〜)$',
  # Skip lines entirely enclosed in various types of brackets.
  '^\\([^)]*\\)$',  # Parentheses ()
  '^（[^）]*）$',  # Full-width parentheses （）
  '^\\[.*\\]$',  # Square brackets []
  '^\\{[^\\}]*\\}$',  # Curly braces {}
  '^<[^>]*>$',  # Angle brackets <>
]
```

### Condensed audio options

#### `enabled`

Whether to create condensed audio files.

Default: `true`

#### `audio_codec`

Audio codec for the condensed audio.

Default: `'libopus'`
Choices: `libmp3lame`, `aac`, `libopus`, `flac`, `pcm_s16le`, `copy`, `mp3`, `wav`, `opus`, `ogg`

#### `audio_quality`

See [Audio quality settings](#audio-quality-settings) for details.

Default: `'48k'`

#### `custom_ffmpeg_args`

Extra FFmpeg arguments to use when creating the final audio.

Example:

```toml
custom_ffmpeg_args = {
  "af" = 'loudnorm=I=-16:LRA=6:TP=-1,acompressor=threshold=-12dB:ratio=3:attack=200:release=1000'
}
```

### Condensed video options

#### `enabled`

Whether to create condensed video files.

Default: `false`

#### `audio_codec`

Audio codec for the condensed video.

Default: `'copy'`
Choices: `libmp3lame`, `aac`, `libopus`, `flac`, `pcm_s16le`, `copy`, `mp3`, `wav`, `opus`, `ogg`

#### `audio_quality`

See [Audio quality settings](#audio-quality-settings) for details.

Example: `'128k'`

#### `video_codec`

Video codec to use. `'copy'` copies the video stream without re-encoding.

Default: `'copy'`

#### `video_quality`

Video quality.

### Video quality settings

The `video_quality` setting depends on the chosen video codec:

#### `libx264` / `libx265` (H.264 / H.265)

Modern video codecs that offer excellent compression. H.265 generally achieves better compression than H.264 but may take longer to encode.

- **How to set quality**: Uses Constant Rate Factor (CRF). Specify a number between 0-51. Lower values = better quality & larger files. A change of ±6 roughly doubles/halves the file size.

- **Examples**:
  - `'23'`: Default, good quality
  - `'18'`: Very high quality, visually lossless
  - `'28'`: Acceptable quality, smaller files

#### `libvpx-vp9` (VP9)

An open video codec developed by Google, offering quality comparable to H.265.

- **How to set quality**: Uses CRF like H.264/H.265. Specify a number between 0-63. Lower values = better quality & larger files.

- **Examples**:
  - `'31'`: Default balanced quality
  - `'24'`: High quality
  - `'35'`: More compression, smaller files

#### Other codecs

For other video codecs, quality is set using bitrate.

- **How to set quality**: Specify the bitrate in bits per second with optional 'k' or 'M' suffix
  - `'1000k'` or `'1M'` = 1 Mbps
  - Lower values = lower quality & smaller files

- **Examples**:
  - `'1M'` or `'1000k'`: Medium quality
  - `'2M'` or `'2000k'`: High quality
  - `'500k'`: Lower quality, smaller file

#### `copy`

Copies the video stream without re-encoding. Use this to maintain original quality and for fastest processing.

- **Quality Setting**: `video_quality` is ignored when using `copy`

#### `custom_ffmpeg_args`

Custom FFmpeg arguments for processing the final video.

Example:

```toml
custom_ffmpeg_args = { "preset" = 'faster', "crf" = '23', "threads" = '0', "tune" = 'film' }
```

### Condensed subtitles options

#### `enabled`

Whether to create condensed subtitle files.

Default: `false`

#### `format`

Output format for condensed subtitles. `'auto'` matches the input format.

Default: `'auto'`
Choices: `auto`, `srt`, `ass`, `lrc`

### Audio quality settings

The `audio_quality` setting depends on the chosen audio codec:

#### `libopus` (`ogg`, `opus`) (Default)

A modern audio codec known for high quality and efficiency at low bitrates. The best size/quality ratio. If your media player supports it, don't even think about it.

- **How to set quality**: Specify the desired bitrate either as a number representing bits per second (e.g., `48000` for 48 kbps) or using the 'k' suffix (e.g., `'48k'`, `'128k'`)."

- **Examples**:
  - `'48k'` or `48000`: Good quality with small file size (default).
  - `'128k'` or `128000`: Higher quality, larger file size.

#### `libmp3lame` (`mp3`)

A widely supported format compatible with most devices.

- **How to set quality**:
  - **Variable Bitrate (VBR)**: Use `'V'` followed by a number from `0` to `9` (e.g., `'V0'`, `'V5'`). Lower numbers mean better quality.
  - **Constant Bitrate (CBR)**: Specify the bitrate in kilobits per second with `'k'` (e.g., `'128k'`, `'320k'`).

- **Examples**:
  - `'V3'`: Good balance between quality and file size.
  - `'192k'`: High-quality CBR MP3.

#### `aac`

Offers better sound quality than MP3 at similar bitrates.

- **How to set quality**:
  - **Variable Bitrate (VBR)**: Use a single digit from `1` to `5` (e.g., `'2'`, `'5'`). Higher numbers mean better quality.
  - **Bitrate**: Specify the bitrate in kilobits per second with `'k'` (e.g., `'128k'`).

- **Examples**:
  - `'2'`: Good quality with reasonable file size.
  - `'128k'`: Standard quality.

#### `flac`

A lossless codec that preserves original audio quality but results in larger files.

- **How to set quality**: Specify the compression level from `0` to `12`. Higher numbers provide better compression but take longer to encode.

- **Examples**:
  - `5`: Default compression level, good balance.
  - `12`: Maximum compression, slower encoding.

#### `pcm_s16le` (`wav`)

An uncompressed audio format resulting in very large files. The only reason you might want to use it over FLAC is software compatibility.

- **Quality Setting**: `audio_quality` is ignored.

#### `copy`

Copies the audio stream without any re-encoding. Use this if you want to keep the original audio as-is.

- **Quality Setting**: `audio_quality` is ignored.

## Command line options

### `--init`

Create a default configuration file in the following locations depending on your operating system:

- **Windows**: `C:\Users\<YourUsername>\AppData\Roaming\shuku\shuku.toml`
- **Unix-like systems (GNU+Linux, macOS)**: `~/.config/shuku/shuku.toml`

### `-c <path>, --config <path>`

Path to a configuration file, or "none" to use the default configuration.

Default: `shuku.toml` in the user config directory (e.g., `~/.config/shuku/shuku.toml`).

### `-s <path>, --subtitles <path>`

Path to subtitle file or directory containing subtitle files to match to input videos.

### `-o <path>, --output <path>`

Path to the output directory. If not specified, the input file's directory will be used.

### `--audio-track-id <id>`

ID of the audio track to use. You can use `ffprobe {file}` to list available tracks.

### `--sub-track-id <id>`

ID of the subtitle track to use.

### `--sub-delay <ms>`

Delay subtitles by `<ms>` milliseconds. Can be negative.

### `-v {level}, --loglevel {level}`

Set the logging level. Choices: `debug`, `info`, `success`, `warning`, `error`, `critical`.

### `--log-file <path>`

Logs will be written to this file in addition to the terminal.

### `-h, --help`

Show the help message and exit.

### `-V, --version`

Print the version number and exit.

## Examples

1. Process a single video file:

   ```bash
   shuku video.mkv
   ```

2. Process multiple files:

   ```bash
   shuku video1.mp4 path/to/directory_with_videos/
   ```

3. Use a specific subtitle file:

   ```bash
   shuku video.mp4 -s subtitles.srt
   ```

4. Set output directory and logging level:

   ```bash
   shuku video.mkv -o ~/condensed -v debug
   ```

5. Use a specific audio track and apply subtitle delay:

   ```bash
   shuku video.mp4 --audio-track-id 2 --sub-delay 500
   ```

6. Use the default configuration, show all logs and save them to a file:

   ```bash
   shuku file.mkv -c none -v debug --log-file shuku.log
   ```

## Support

Something not working? Have an idea? Let us know!

- Questions? → [Start a discussion](https://github.com/welpo/shuku/discussions)
- Found a bug? → [Report it here](https://github.com/welpo/shuku/issues/new?&labels=bug&template=2_bug_report.yml)
- Feature request? → [Tell us more!](https://github.com/welpo/shuku/issues/new?&labels=feature&template=3_feature_request.yml)

## Contributing

Please do! We appreciate bug reports, feature or documentation improvements (however minor), feature requests…

Take a look at the [Contributing Guidelines](/CONTRIBUTING.md) to learn more.

## License

`shuku` is free software: you can redistribute it and/or modify it under the terms of the [GNU General Public License as published by the Free Software Foundation](./COPYING), either version 3 of the License, or (at your option) any later version.
