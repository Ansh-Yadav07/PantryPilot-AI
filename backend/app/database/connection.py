"""
MongoDB connection management.

A single MongoClient (with its own connection pool) is shared by the whole
process. There is deliberately NO in-memory fallback: if Atlas is unreachable,
requests fail with 503 instead of silently writing to a database that vanishes
on restart.
"""

import logging
import socket
import threading
from typing import Optional

import certifi
from fastapi import HTTPException, status
from pymongo import MongoClient
from pymongo.database import Database as MongoDatabase

from ..config.settings import settings

logger = logging.getLogger("pantrypilot.db")

# Some networks (notably macOS on certain Wi-Fi setups) fail on IPv6 routes to
# Atlas ([Errno 65] No route to host). Resolve Atlas hosts over IPv4 only.
_orig_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_force_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and ("mongodb.net" in host or "mongodb.com" in host):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_force_ipv4


class Database:
    client: Optional[MongoClient] = None
    _lock = threading.Lock()

    @classmethod
    def connect_db(cls) -> Optional[MongoClient]:
        with cls._lock:
            if cls.client is not None:
                return cls.client
            if not settings.mongodb_uri:
                logger.error("MONGODB_URI is not set; database features are unavailable.")
                return None
            kwargs = {
                "serverSelectionTimeoutMS": 10000,
                "connectTimeoutMS": 10000,
                "retryWrites": True,
                "appname": "pantrypilot-api",
            }
            if settings.mongodb_uri.startswith("mongodb+srv://") or "tls=true" in settings.mongodb_uri:
                kwargs["tlsCAFile"] = certifi.where()
            try:
                # MongoClient connects lazily; constructing it never blocks.
                cls.client = MongoClient(settings.mongodb_uri, **kwargs)
            except Exception as e:  # invalid URI etc. — never log the URI itself
                logger.error("Invalid MongoDB configuration: %s", type(e).__name__)
                cls.client = None
            return cls.client

    @classmethod
    def close_db(cls) -> None:
        with cls._lock:
            if cls.client is not None:
                cls.client.close()
                cls.client = None

    @classmethod
    def get_db(cls) -> Optional[MongoDatabase]:
        client = cls.client or cls.connect_db()
        if client is None:
            return None
        return client[settings.database_name]

    @classmethod
    def ping(cls) -> bool:
        client = cls.client or cls.connect_db()
        if client is None:
            return False
        try:
            client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB ping failed: %s", type(e).__name__)
            return False

    # Backwards-compatible name used by older code.
    is_connected = ping


db = Database()


def get_database() -> MongoDatabase:
    """FastAPI dependency returning the database or failing with 503."""
    database = Database.get_db()
    if database is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Please try again later.",
        )
    return database
