"""Configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable application configuration."""

    # IMAP
    imap_host: str = "outlook.office365.com"
    imap_port: int = 993
    email_address: str = ""
    email_password: str = ""

    # Email filters
    target_sender: str = "BOSOFinance@Purdue.edu"
    target_subject: str = "TooCOOL Order Confirmation"

    # Storage
    download_dir: Path = field(default_factory=lambda: Path("downloads"))
    db_path: Path = field(default_factory=lambda: Path("hkn_pos.db"))

    # IDLE reconnect interval (seconds) — Office 365 drops after ~29 min
    idle_timeout: int = 25 * 60  # 25 minutes, safe margin

    # API server
    api_port: int = 8042
    api_passkey: str = ""

    # Webhook (interrupt to external server)
    webhook_url: str = ""
    ack_timeout: int = 30  # seconds to wait for ACK before re-firing

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> Config:
        """Load configuration from environment variables / .env file."""
        load_dotenv(dotenv_path or ".env")

        download = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
        download.mkdir(parents=True, exist_ok=True)

        return cls(
            imap_host=os.getenv("IMAP_HOST", cls.imap_host),
            imap_port=int(os.getenv("IMAP_PORT", str(cls.imap_port))),
            email_address=os.getenv("EMAIL_ADDRESS", ""),
            email_password=os.getenv("EMAIL_PASSWORD", ""),
            target_sender=os.getenv("TARGET_SENDER", cls.target_sender),
            target_subject=os.getenv("TARGET_SUBJECT", cls.target_subject),
            download_dir=download,
            idle_timeout=int(os.getenv("IDLE_TIMEOUT", str(25 * 60))),
            db_path=Path(os.getenv("DB_PATH", "hkn_pos.db")),
            api_port=int(os.getenv("API_PORT", "8042")),
            api_passkey=os.getenv("API_PASSKEY", ""),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            ack_timeout=int(os.getenv("ACK_TIMEOUT", "30")),
        )
