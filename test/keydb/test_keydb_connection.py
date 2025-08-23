#!/usr/bin/env python3
"""
KeyDB/Redis Connection Diagnostic Tool

This standalone script exercises multiple connection methods and error cases
for the KeyDB/Redis client used by the app (redis.asyncio / redis-py 5.x).

It mirrors the style of the MySQL diagnostic test and can be run directly:
    python -m test.test_keydb_connection
or
    python test/test_keydb_connection.py
"""

import sys
import os
import asyncio
from typing import Any



# Add project root to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.helpers.improved_functions import get_env_var
from config import config  # noqa: E402
from utils.keydb.keydb_utils import (  # noqa: E402
    connect_to_keydb,
    close_keydb,
)


def _mask(value: str | None) -> str:
    if not value:
        return "None"
    return "*" * 8


def test_config_loading() -> bool:
    print("🔧 Testing KeyDB Configuration Loading...")
    print("-" * 50)
    try:
        print("✅ Config loaded successfully")
        print(f"   KEYDB_HOST: {config.KEYDB_HOST}")
        print(f"   KEYDB_PORT: {config.KEYDB_PORT}")
        print(f"   KEYDB_DB:   {config.KEYDB_DB}")
        print(f"   KEYDB_SSL:  {config.KEYDB_SSL}")
        print(f"   KEYDB_PASSWORD: {_mask(config.KEYDB_PASSWORD)}")
        return True
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False


def test_environment_variables() -> bool:
    print("\n🌍 Testing Environment Variables for KeyDB...")
    print("-" * 50)
    required = [
        "KEYDB_HOST",
        "KEYDB_PORT",
        "KEYDB_DB",
    ]
    missing = []
    for var in required:
        value = get_env_var(var)
        if value is None:
            print(f"❌ {var}: Not set (using defaults: {getattr(config, var, None)})")
            missing.append(var)
        else:
            print(f"✅ {var}: {value}")
    if missing:
        print("\n⚠️ Missing environment variables (defaults will be used).")
    else:
        print("\n✅ All required environment variables are set or have defaults")
    return True


def test_url_generation() -> bool:
    print("\n🔗 Testing KeyDB URL Generation...")
    print("-" * 50)
    try:
        # Clear cache to reflect current KEYDB_* values
        try:
            config.get_keydb_url.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        url = config.get_keydb_url()
        print(f"   Generated URL: {url}")
        if not url or not isinstance(url, str) or not url.startswith("redis://"):
            print("❌ URL is missing or not in expected format (redis://...)")
            return False
        print("✅ URL generation looks correct")
        return True
    except Exception as e:
        print(f"❌ URL generation failed: {e}")
        return False


async def _try_connect_direct_via_url() -> bool:
    print("\n🔌 Testing Direct Connection (URL) via redis.asyncio.from_url...")
    print("-" * 50)
    try:
        import redis.asyncio as redis  # Local import for isolation

        # Ensure we use latest URL based on current config
        try:
            config.get_keydb_url.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass

        url = config.get_keydb_url()
        if not url:
            print("❌ No URL generated; skipping direct URL test")
            return False

        client = redis.from_url(
            url,
            db=config.KEYDB_DB,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2.0,
        )
        pong = await client.ping()
        print(f"✅ Direct URL connection successful, PING: {pong}")
        if hasattr(client, "aclose"):
            await client.aclose()
        else:
            await client.close()
        return True
    except Exception as e:
        print(f"❌ Direct URL connection failed: {e}")
        return False


async def _try_connect_via_utils() -> bool:
    print("\n🔌 Testing Connection via keydb_utils.connect_to_keydb()...")
    print("-" * 50)
    try:
        client = await connect_to_keydb()
        if not client:
            print("❌ keydb_utils returned None (connection failed)")
            return False
        pong = await client.ping()
        print(f"✅ keydb_utils connection successful, PING: {pong}")
        await close_keydb(client)
        return True
    except Exception as e:
        print(f"❌ keydb_utils connection failed: {e}")
        return False


async def _try_connect_direct_via_address(bogus: bool = False) -> bool:
    print("\n🔌 Testing Direct Connection (address) via redis.asyncio.Redis...")
    print("-" * 50)
    try:
        import redis.asyncio as redis

        host = "invalid.host.local" if bogus else config.KEYDB_HOST
        port = 6390 if bogus else config.KEYDB_PORT

        password = config.KEYDB_PASSWORD or None
        client = redis.Redis(
            host=host,
            port=port,
            db=config.KEYDB_DB,
            password=password,
            encoding="utf-8",
            decode_responses=True,
            ssl=str(config.KEYDB_SSL).lower() in ("1", "true", "yes", "on"),
            socket_connect_timeout=1.0 if bogus else 2.0,
        )
        pong = await client.ping()
        print(f"✅ Direct address connection successful, PING: {pong}")
        if hasattr(client, "aclose"):
            await client.aclose()
        else:
            await client.close()
        return True
    except Exception as e:
        if bogus:
            print(f"✅ Expected failure for bogus host/port: {e}")
            return True
        print(f"❌ Direct address connection failed: {e}")
        return False


def test_invalid_url_scheme() -> bool:
    print("\n🧪 Testing Invalid URL Scheme Handling...")
    print("-" * 50)
    try:
        import redis.asyncio as redis
        # Use an intentionally invalid scheme
        url = "http://localhost:6379/0"
        async def _run() -> None:
            client = redis.from_url(url, socket_connect_timeout=0.5)
            await client.ping()
        try:
            asyncio.run(_run())
            print("❌ Unexpected success with invalid URL scheme")
            return False
        except Exception as e:
            print(f"✅ Raised error for invalid URL as expected: {e}")
            return True
    except Exception as e:
        print(f"❌ Test errored unexpectedly: {e}")
        return False


def test_aioredis_missing() -> bool:
    print("\n🧪 Testing Behavior When aioredis Is Missing...")
    print("-" * 50)
    try:
        import utils.keydb.keydb_utils as kdu
        original = kdu.redis
        kdu.redis = None
        async def _run() -> None:
            try:
                await kdu.connect_to_keydb()
                print("❌ Expected RuntimeError when aioredis is None, but got success")
            except RuntimeError as e:
                print(f"✅ Raised RuntimeError as expected: {e}")
                raise SystemExit(0)
        try:
            asyncio.run(_run())
        except SystemExit:
            return True
        finally:
            kdu.redis = original
        return False
    except Exception as e:
        print(f"❌ aioredis-missing test failed: {e}")
        return False


def main() -> None:
    print("🧪 KeyDB/Redis Connection Diagnostic Tool")
    print("=" * 60)

    tests: list[tuple[str, Any]] = [
        ("Environment Variables", test_environment_variables),
        ("Configuration Loading", test_config_loading),
        ("URL Generation", test_url_generation),
        ("Direct URL Connection", lambda: asyncio.run(_try_connect_direct_via_url())),
        ("Direct Address Connection", lambda: asyncio.run(_try_connect_direct_via_address(bogus=False))),
        ("Direct Address Connection (Bogus Host)", lambda: asyncio.run(_try_connect_direct_via_address(bogus=True))),
        ("Connect via keydb_utils", lambda: asyncio.run(_try_connect_via_utils())),
        ("Invalid URL Scheme", test_invalid_url_scheme),
    ]

    results: list[tuple[str, bool]] = []
    for name, func in tests:
        try:
            ok = func()
        except Exception as e:
            print(f"❌ {name} raised unexpected exception: {e}")
            ok = False
        results.append((name, bool(ok)))

    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} {name}")
    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed. Please review the messages above.")


if __name__ == "__main__":
    main()


