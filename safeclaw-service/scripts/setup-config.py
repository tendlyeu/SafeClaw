#!/usr/bin/env python3
"""Generate default ~/.safeclaw/config.json."""

import argparse
import sys
from pathlib import Path

# Allow running from the scripts/ directory or project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safeclaw.config_template import generate_config, write_config


def main():
    parser = argparse.ArgumentParser(description="Generate SafeClaw config file")
    parser.add_argument("--user-id", default="", help="User ID for the config")
    parser.add_argument(
        "--mode",
        choices=["embedded", "remote", "hybrid"],
        default="embedded",
        help="Operating mode (default: embedded)",
    )
    parser.add_argument(
        "--service-url",
        default="http://localhost:8420/api/v1",
        help="Remote service URL (default: http://localhost:8420/api/v1)",
    )
    args = parser.parse_args()

    config_path = Path.home() / ".safeclaw" / "config.json"

    if config_path.exists():
        print(f"Config already exists at {config_path}")
        print("Delete it first if you want to regenerate.")
        return

    config = generate_config(
        user_id=args.user_id,
        mode=args.mode,
        service_url=args.service_url,
    )
    write_config(config_path, config)
    print(f"SafeClaw config written to {config_path}")


if __name__ == "__main__":
    main()
