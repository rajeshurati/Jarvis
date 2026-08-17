"""One-time interactive Gmail OAuth authorization command."""

from __future__ import annotations

from jarvis.adapters.productivity.gmail_oauth import GMAIL_SCOPES
from jarvis.core.config import get_settings


def run() -> None:
    """Open Google's consent screen and save a revocable local OAuth token."""
    settings = get_settings()
    client_file = settings.gmail_oauth_client_file
    token_file = settings.gmail_oauth_token_file
    if not client_file.is_file():
        raise SystemExit(
            f"OAuth client file not found: {client_file}. "
            "Download a Desktop app OAuth client JSON from Google Cloud first."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-not-found]
    except ImportError as error:
        raise SystemExit(
            'Gmail OAuth support is missing. Install with: pip install -e ".[gmail]"'
        ) from error
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), list(GMAIL_SCOPES))
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=True,
        authorization_prompt_message="Opening Google authorization in your browser...",
        success_message="Jarvis Gmail authorization succeeded. You may close this tab.",
    )
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    token_file.chmod(0o600)
    print("Jarvis Gmail authorization saved locally.")


if __name__ == "__main__":
    run()
