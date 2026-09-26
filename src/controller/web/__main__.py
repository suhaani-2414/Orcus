"""`python -m controller.web` — serve the web dashboard at http://127.0.0.1:8000."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("controller.web.server:app", host="127.0.0.1", port=8000, log_level="warning")
