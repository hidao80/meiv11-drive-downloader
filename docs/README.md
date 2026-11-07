# misskey-drive-downloader

[![test](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/test.yml/badge.svg)](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/test.yml)
[![lint](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/lint.yml/badge.svg)](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/lint.yml)
[![audit](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/audit.yml/badge.svg)](https://github.com/hidao80/meiv11-drive-downloader/actions/workflows/audit.yml)

Download every file in your [Misskey](https://misskey-hub.net/) drive, keeping the folder structure.

> [!IMPORTANT]
> This tool targets Misskey instances running **meiV11** or an equivalent version.
> Newer versions of upstream Misskey are **not supported**.

- Uses only the Python standard library — no third-party packages needed at runtime
- Resumable: files that are already saved are skipped on the next run
- Retries automatically on rate limits (HTTP 429), server errors, and network failures
- Converts file names so they are valid on Windows

## Requirements

- Python 3.8 or later
- [uv](https://docs.astral.sh/uv/) (recommended, optional)
- An access token for your Misskey account with the **View your Drive** (`read:drive`) permission

## Getting an access token

1. Open your Misskey instance in a browser and go to **Settings → API**.
2. Click **Generate access token**.
3. Enable only the **View your Drive** (`read:drive`) permission and create the token.
4. Copy the token. Treat it like a password — never commit it to a repository.

## Installation

```bash
git clone https://github.com/hidao80/meiv11-drive-downloader.git
cd meiv11-drive-downloader
uv sync
```

Without uv, no installation is needed — run the script directly with `python`.

## Usage

Set the token in the `MISSKEY_TOKEN` environment variable, then run the script.

bash / zsh:

```bash
export MISSKEY_TOKEN=your-access-token
uv run misskey_drive_download.py
```

PowerShell:

```powershell
$env:MISSKEY_TOKEN = "your-access-token"
uv run misskey_drive_download.py
```

Files are saved to `./misskey-drive` by default.

### Examples

```bash
# Save to a different directory
uv run misskey_drive_download.py -o D:/backup

# Use a different instance
uv run misskey_drive_download.py --host misskey.io

# List what would be downloaded without saving anything
uv run misskey_drive_download.py --dry-run

# Run without uv
python misskey_drive_download.py
```

### Options

| Option | Description | Default |
|---|---|---|
| `--host HOST` | Host name of the Misskey instance | `misskey.dev` |
| `-o`, `--output DIR` | Output directory | `./misskey-drive` |
| `--dry-run` | Print the files that would be downloaded, without downloading | off |
| `-h`, `--help` | Show help | |

### Environment variables

| Variable | Description |
|---|---|
| `MISSKEY_TOKEN` | Access token (required) |
| `MISSKEY_HOST` | Default host name. Overridden by `--host` |

## How it works

- **Folder structure** — Starting from the root of the drive, folders are traversed recursively and recreated under the output directory.
- **Resuming** — Each file is first written as `<name>.part` and renamed when complete. Any file that already exists is treated as complete and skipped, so an interrupted run can simply be restarted.
- **File names** — Characters that are invalid on Windows (`<>:"/\|?*` and control characters) are replaced with `_`. Trailing dots and spaces are removed, and reserved names such as `CON` or `NUL` are prefixed with `_`.
- **Duplicate names** — When two items in the same folder end up with the same name (compared case-insensitively), the file ID is appended, e.g. `photo_9abc123.png`.
- **Retries** — API calls are retried up to 5 times with exponential backoff on HTTP 429 and 5xx. Downloads are also retried on network errors, but fail immediately on 4xx errors other than 429. There is a 0.5 second pause between API calls.
- **Errors** — A failed file does not stop the run. Failures are listed at the end.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All files were saved or skipped |
| `1` | At least one file failed, or the token is missing or rejected |

## Notes

- Only files are downloaded. Metadata such as comments, sensitive flags, and attached notes is not saved.
- A file that already exists locally is never re-downloaded, even if it has changed on the server. Delete the local copy to fetch it again.
- If you run this inside a Git repository, keep the output directory out of version control. `misskey-drive/` is already listed in `.gitignore`; add any other directory you pass to `-o`.

## Development

```bash
uv sync           # installs pytest and ruff as dev dependencies
uv run pytest     # runs the tests (no network access)
uv run ruff check .                                          # lint
uv audit --no-dev --preview-features audit-command           # check runtime dependencies for known vulnerabilities
```
