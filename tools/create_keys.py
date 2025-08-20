#!/usr/bin/env python3
"""
Create missing secret keys in the project's .env file.

This tool generates and persists the following keys if missing:
- SECRET_KEY                (random urlsafe)
- ENCRYPTION_KEY           (Fernet key)
- POWER_KEY                (random urlsafe)

Usage:
  python tools/create_keys.py            # generate and save missing keys
  python tools/create_keys.py --dry-run  # show what would be created

Exit codes:
  0 on success, non-zero on failure.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from utils.helpers.improved_functions import get_env_var

try:
    from cryptography.fernet import Fernet
except Exception:  # cryptography should be installed per requirements.txt
    Fernet = None  # type: ignore

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def generate_urlsafe_token(num_bytes: int = 32) -> str:
    return secrets.token_urlsafe(num_bytes)


def generate_fernet_key() -> str:
    if Fernet is None:
        raise RuntimeError("cryptography is not installed; cannot generate ENCRYPTION_KEY")
    return Fernet.generate_key().decode("ascii")


KEY_GENERATORS: Dict[str, Callable[[], str]] = {
    "SECRET_KEY": generate_urlsafe_token,
    "ENCRYPTION_KEY": generate_fernet_key,
    "POWER_KEY": generate_urlsafe_token,
}


def mask_value(value: str | None) -> str:
    if not value:
        return "<missing>"
    return "*" * min(8, len(value))


def read_env_to_os(env_path: Path) -> None:
    if load_dotenv is None:
        return
    # Do not override already-set environment variables
    load_dotenv(dotenv_path=str(env_path), override=False)


def list_missing_keys() -> List[str]:
    missing: List[str] = []
    for key in KEY_GENERATORS.keys():
        if not get_env_var(key):
            missing.append(key)
    return missing


def append_keys_to_env(env_path: Path, kv_pairs: Dict[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    banner = f"# Added by tools/create_keys.py on {datetime.now().isoformat()}"
    with open(env_path, "a", encoding="utf-8") as f:
        if env_path.exists() and env_path.stat().st_size > 0:
            f.write("\n")
        f.write(banner + "\n")
        for k, v in kv_pairs.items():
            f.write(f"{k}={v}\n")


def main(argv: List[str]) -> int:
    values = {k: gen() for k, gen in KEY_GENERATORS.items()}
    print({k: v for k, v in values.items()})
    
    parser = argparse.ArgumentParser(description="Generate missing secret keys in .env")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would change")
    parser.add_argument(
        "--env", dest="env_path", default=str(ENV_PATH), help="Path to .env file (default: project .env)"
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_path)
    read_env_to_os(env_path)

    # Determine missing keys
    missing = list_missing_keys()
    print("🔑 Checking required keys in environment/.env...")
    for k in KEY_GENERATORS.keys():
        print(f" - {k}: {'present' if k not in missing else 'missing'}")

    if not missing:
        print("\n✅ All required keys are present. Nothing to do.")
        return 0

    # Generate values for missing keys
    to_write: Dict[str, str] = {}
    for key in missing:
        try:
            to_write[key] = KEY_GENERATORS[key]()
        except Exception as exc:
            print(f"❌ Failed to generate value for {key}: {exc}")
            return 2

    # Show summary
    print("\n📝 Missing keys to add:")
    for k, v in to_write.items():
        shown = v if k == "ENCRYPTION_KEY" else mask_value(v)
        print(f" - {k}: {shown}")

    if args.dry_run:
        print("\nℹ️  Dry run: not writing changes. Re-run without --dry-run to apply.")
        return 0

    # Append to .env
    try:
        append_keys_to_env(env_path, to_write)
        # Make env file user-readable/writable only
        try:
            os.chmod(env_path, 0o600)
        except Exception:
            pass
    except Exception as exc:
        print(f"❌ Failed to write to {env_path}: {exc}")
        return 3

    # Update this process environment so subsequent commands can see them
    os.environ.update(to_write)

    print(f"\n✅ Wrote {len(to_write)} key(s) to {env_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


