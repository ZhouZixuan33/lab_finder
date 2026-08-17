# Lab Application Tracker

Lab Application Tracker is a private, local web application for exploring the research interests of UIUC ECE professors and keeping track of lab applications. It finds newly listed professors, researches their labs and publications with an LLM-assisted workflow, and stores everything on your computer in SQLite.

## Features

- Browse and search UIUC ECE professors in one table.
- Filter by broad research tag or application state.
- View research summaries, lab links, source links, and recent publications.
- Track `Interested → Applied → Accepted/Rejected`, an application date, and notes.
- Add newly listed professors without changing existing professor records.
- Review and approve differences from a single-professor update check.

## Requirements

- Windows PowerShell.
- Python 3.12 or newer.
- Node.js 20 or newer, including npm.
- An API key for an OpenAI-compatible chat model.
- Tavily and OpenAlex API keys.

## Quick Start

Run these commands in PowerShell:

```powershell
git clone git@github.com:ZhouZixuan33/lab_application_tracker.git
cd lab_application_tracker
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .\backend
npm --prefix frontend install
Copy-Item .env.example .env
notepad .env
npm --prefix frontend run build
.venv\Scripts\python.exe -m lab_tracker
```

Replace the placeholder API credentials before closing Notepad. When the backend is ready, open `http://127.0.0.1:8000`.

## Configuration

The generated `.env` file contains the settings you need:

```dotenv
DATABASE_PATH=./data/lab_tracker.db
LLM_BASE_URL=
LLM_API_KEY=replace-me
LLM_MODEL=replace-me
TAVILY_API_KEY=replace-me
OPENALEX_API_KEY=replace-me
TAVILY_MIN_INTERVAL_SECONDS=1.0
OPENALEX_MIN_INTERVAL_SECONDS=1.0
WEB_HOST_MIN_INTERVAL_SECONDS=1.0
```

Set the three API keys and the exact model name required by your LLM provider. Leave `LLM_BASE_URL` blank for the default OpenAI endpoint, or set it to the provider's OpenAI-compatible base URL. The remaining defaults are suitable for normal local use.

Never commit `.env` or share its contents.

## First Use

The professor list is empty when you start with a new database. Click **Find New Professors** once to discover the current UIUC ECE faculty and add professors that are not already stored.

Researching professors calls the configured LLM, Tavily, and OpenAlex services and may use provider quota. The operation can take several minutes; the page displays a compact running notice and a success, partial-success, or failure result when it finishes.

## Local Data

Your settings are stored in `.env`, and your professor and application data are stored in `data/lab_tracker.db` by default. Neither file is included when you clone the repository or committed to Git.

To move your data to another computer, stop the backend and copy the SQLite database separately into the same `data` location after cloning and installing the application.

If startup or research fails, check the `.env` values and the terminal running the backend for the error message.

## Developer Documentation

Architecture, development servers, tests, diagnostics, database details, and the complete REST API are documented in [DEVELOPMENT.md](DEVELOPMENT.md).
