"""Configuration for OpenTrack automation."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass
class OpenTrackConfig:
    """Configuration for connecting to OpenTrack."""

    base_url: str = "https://norway.opentrack.run"
    username: str = ""
    password: str = ""
    headless: bool = False  # Set to True for CI/automated runs
    slow_mo: int = 0  # Milliseconds to slow down operations (helpful for debugging)

    @classmethod
    def from_env(cls) -> "OpenTrackConfig":
        """Load configuration from environment variables."""
        return cls(
            base_url=os.getenv("OPENTRACK_URL", "https://norway.opentrack.run"),
            username=os.getenv("OPENTRACK_USERNAME", ""),
            password=os.getenv("OPENTRACK_PASSWORD", ""),
            headless=os.getenv("OPENTRACK_HEADLESS", "false").lower() == "true",
            slow_mo=int(os.getenv("OPENTRACK_SLOW_MO", "0")),
        )


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
RECORDINGS_DIR = PROJECT_ROOT / "recordings"
