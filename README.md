# AFK Labs ToonVault

AFK Labs ToonVault is a desktop app for downloading and organizing Webtoon chapters for offline reading.

Built with Python and pywebview, it features a modern terminal-inspired interface and supports multiple export formats.

## Features

- Add multiple Webtoon series links at once
- Choose start and end chapters
- Export chapters as PDF, CBZ, separate images, or one long image
- Organize downloads by series and chapter folders
- Clean dark interface inspired by terminal tools
- Windows desktop build support with PyInstaller

## Link Format

Use Webtoon series list links, not individual chapter links.

Works:

```text
https://www.webtoons.com/en/action/hero-killer/list?title_no=2745
```

Does not work:

```text
https://www.webtoons.com/en/action/hero-killer/episode-1/viewer?title_no=2745&episode_no=1
```

## Run From Source

```bash
pip install -r requirements.txt
python app.py
```

On Windows, you can also use:

```text
Abrir AFK Labs ToonVault.bat
```

## Build

```bash
python -m PyInstaller --noconfirm --windowed --name "AFK Labs ToonVault" --add-data "web;web" app.py
```

The generated executable will be created under:

```text
dist/AFK Labs ToonVault/AFK Labs ToonVault.exe
```

## Tech Stack

- Python
- pywebview
- HTML/CSS/JavaScript
- BeautifulSoup
- Requests
- Pillow
- PyInstaller
