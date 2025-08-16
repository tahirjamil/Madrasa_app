#!/usr/bin/env python3
"""
Test script to verify KeyDB connection in Docker
"""
import asyncio
import redis.asyncio as redis
from utils.helpers.improved_funtions import get_env_var

async def test_keydb_connection():
    """Test KeyDB connection"""
    try:
        # Connect to KeyDB
        client = redis.Redis(
            host='localhost',
            port=6379,
            password='password',
            decode_responses=True,
            socket_connect_timeout=5.0
        )
        
        # Test basic operations
        await client.set('test_key', 'test_value')
        value = await client.get('test_key')
        await client.delete('test_key')
        
        print("✅ KeyDB connection successful!")
        print(f"Test value retrieved: {value}")
        
        # Test ping
        pong = await client.ping()
        print(f"Ping response: {pong}")
        
        await client.close()
        
    except Exception as e:
        print(f"❌ KeyDB connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_keydb_connection())
