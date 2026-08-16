# Lab Application Tracker

A local, single-user application for researching UIUC ECE professors and tracking lab applications.

The implementation is in progress. The approved design and implementation plan are available in `docs/superpowers`.

## Development prerequisites

- Python 3.12+
- Node.js 20+
- A Tavily API key
- An OpenAlex API key
- An API key for the configured LangChain chat model

Copy `.env.example` to `.env` before running the backend. Never commit `.env` or the SQLite database.

## Brand asset

The header uses the official orange-and-blue Block I published by the
[University of Illinois Brand Guidelines](https://brand.illinois.edu/visual-identity/logo).
