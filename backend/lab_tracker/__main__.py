"""Run the local API server with its required single worker."""

import uvicorn

from lab_tracker.diagnostics import configure_application_logging


def main() -> None:
    configure_application_logging()
    uvicorn.run(
        "lab_tracker.main:app",
        host="127.0.0.1",
        port=8000,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    main()
