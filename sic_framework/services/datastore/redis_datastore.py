"""
Redis Datastore Service: Unified Key-Value Store + Vector RAG

This module provides persistent **scoped key-value** storage (the same Redis keyspace is
often used for per-user / interactant records with general scope identifiers) and
vector-based retrieval-augmented generation (RAG), backed by **Redis Stack**.

All functionality is accessed via SIC service requests through RedisDatastoreComponent.

=== ORGANIZATIONAL STRUCTURE ===

1. Configuration:
   - RedisDatastoreConf: Redis connection and keyspace namespacing

2. Request Classes:
   - Scoped key-value storage: SetScopedKeyValuesRequest, GetScopedKeyValuesRequest,
     DeleteScopedKeyValuesRequest, GetScopedKeysRequest, GetScopedRecordRequest
   - Datastore Management: DeleteDeveloperSegmentRequest, DeleteVersionSegmentRequest, DeleteNamespaceRequest
   - Vector RAG: IngestVectorDocsRequest, QueryVectorDBRequest

3. Response Messages:
   - ScopedKeyValuesMessage, ScopedKeysMessage, VectorDBResultsMessage, SICSuccessMessage

4. Service Component:
   - RedisDatastoreComponent: Handles all requests via on_request()
   - RedisDatastore: SIC connector for client usage

=== USAGE ===

**Single command (Docker + datastore service)** — requires Docker installed:

    run-redis --data-dir /path/to/persist/redis-data

Optional: ``--skip-docker`` if Redis Stack is already running; tune Redis with
``--redis-args`` (``REDIS_ARGS``) and/or ``--redis-conf`` (host file mounted into the
container). Default password matches ``DB_PASS`` / ``changemeplease`` used by SIC Redis.


Send requests from your application:

    from sic_framework.services.datastore import (
        RedisDatastore,
        RedisDatastoreConf,
        SetScopedKeyValuesRequest,
        IngestVectorDocsRequest,
        QueryVectorDBRequest,
    )

    # Connect to the Redis service
    db = RedisDatastore(conf=RedisDatastoreConf(redis_url="redis://:password@localhost:6379/0"))

    # Key-value (per-user example)
    db.request(SetScopedKeyValuesRequest(scope_id=123, keyvalues={"name": "Alice"}))
    # Same storage, arbitrary scope id (session, device bucket, etc.)
    db.request(SetScopedKeyValuesRequest(scope_id="sess-1", keyvalues={"state": "idle"}))

    # Ingest documents into vector DB (auto-index mode)
    # Creates one index per directory containing matching files
    # For example, if you have: docs/legal/contracts/*.pdf and docs/technical/specs/*.pdf
    # This creates indices: "myproject_legal__contracts" and "myproject_technical__specs"
    result = db.request(IngestVectorDocsRequest(
        input_path="/path/to/documents",
        auto_index_from_folders=True,
        index_prefix="myproject_",
        embedding_model="text-embedding-3-large",
        override_existing=True,
    ))

    # Or ingest into a single named index
    result = db.request(IngestVectorDocsRequest(
        input_path="/path/to/documents",
        index_name="my_knowledge_base",
        embedding_model="text-embedding-3-large",
        override_existing=True,
    ))

    # Query vector DB using explicit index name
    response = db.request(QueryVectorDBRequest(
        index_name="my_knowledge_base",
        query_text="What is the main theme?",
        k=5,
        openai_api_key="sk-...",
        embedding_model="text-embedding-3-large",
    ))
    print(response.payload)
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import redis
from redis.exceptions import OutOfMemoryError, DataError, RedisError

from sic_framework import SICConfMessage, SICComponentManager, SICMessage, SICRequest, SICSuccessMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.utils import is_sic_instance, str_if_bytes


# ============================================================================
# CONSTANTS
# ============================================================================

REDIS_STACK_INSTALL_MESSAGE = (
    "RediSearch module is not available. You must use Redis Stack, not regular Redis.\n"
    "Install Redis Stack with:\n"
    "  docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 "
    "-v redis-stack-data:/data -e REDIS_ARGS=\"--requirepass changemeplease\" redis/redis-stack:latest\n"
)

REDIS_CONNECTION_ERROR_MESSAGE = (
    "Failed to connect to Redis. Make sure Redis Stack is running.\n"
    "Start Redis with: docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 "
    "-v redis-stack-data:/data -e REDIS_ARGS=\"--requirepass changemeplease\" redis/redis-stack:latest\n"
    "Or use: run-redis [--data-dir HOST_PATH]"
)

DEFAULT_REDIS_STACK_IMAGE = "redis/redis-stack:latest"
DOCKER_NOT_INSTALLED_MESSAGE = (
    "Docker is not installed or not on PATH. Install Docker to use run-redis, "
    "or start Redis Stack yourself and pass --skip-docker."
)


# ============================================================================
# CONFIGURATION
# ============================================================================
class RedisDatastoreConf(SICConfMessage):
    """
    Configuration for setting up the connection to a persistent Redis datastore.

    Args:
        host: IP address of the Redis server. If omitted, uses ``DB_IP`` (default ``127.0.0.1``).
        port: Port of the Redis server. If omitted, uses ``DB_PORT`` (default ``6379``).
        password: optional password to redis server.
        username: optional username to redis server.
        socket_connect_timeout: timeout for connecting to Redis server. Default is 2 seconds.
        socket_timeout: socket timeout in seconds. Default is 2 seconds.
        decode_responses: whether to decode standard byte response from Redis server. Default is True.
        namespace: basic namespace of the redis datastore. Default is 'store'.
        version: version of the namespace. Default is 'v1'.
        developer_id: id of the developer user. Default is 0.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, db: int = 0,
                 redis_url: Optional[str] = None,
                 password: Optional[str] = None, username: Optional[str] = None,
                 socket_connect_timeout: float = 2.0, socket_timeout: float = 2.0,
                 max_connections: int = 50, decode_responses: bool = True,
                 namespace: str = "store", version: str = "v1", developer_id: str | int = 0):
        super(SICConfMessage, self).__init__()

        # Redis basic configuration (``DB_IP`` / ``DB_PORT`` match SIC messaging + ``run-redis``)
        self.host = host if host is not None else os.getenv("DB_IP", "127.0.0.1")
        self.port = port if port is not None else int(os.getenv("DB_PORT", "6379"))
        self.db = db
        self.redis_url = redis_url
        self.password = password
        self.username = username
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections
        self.decode_responses = decode_responses

        # Redis store keyspace management
        self.namespace = namespace
        self.version = version
        self.developer_id = developer_id


# ============================================================================
# SCOPED KEY-VALUE REQUESTS
# ============================================================================

class SetScopedKeyValuesRequest(SICRequest):

    def __init__(self, scope_id: str | int, keyvalues: dict) -> None:
        """
        Set fields on the scoped key-value record for ``scope_id``.

        Args:
            scope_id: partition id (user/interactant/session/device bucket/etc.)
            keyvalues: fields to set, e.g. ``{'key_1': 'value_1'}``
        """
        super().__init__()
        self.scope_id = scope_id
        self.keyvalues = keyvalues


class GetScopedKeyValuesRequest(SICRequest):

    def __init__(self, scope_id: str | int, keys: list) -> None:
        """
        Read selected keys from the scoped key-value record for ``scope_id``.

        Args:
            scope_id: partition id
            keys: field names to read
        """
        super().__init__()
        self.scope_id = scope_id
        self.keys = keys


class DeleteScopedKeyValuesRequest(SICRequest):

    def __init__(self, scope_id: str | int, keys: list) -> None:
        """
        Delete selected fields from the scoped key-value record for ``scope_id``.

        Args:
            scope_id: partition id
            keys: field names to remove
        """
        super().__init__()
        self.scope_id = scope_id
        self.keys = keys


class GetScopedKeysRequest(SICRequest):

    def __init__(self, scope_id: str | int) -> None:
        """
        List field names on the scoped key-value record for ``scope_id``.

        Args:
            scope_id: partition id
        """
        super().__init__()
        self.scope_id = scope_id


class GetScopedRecordRequest(SICRequest):

    def __init__(self, scope_id: str | int) -> None:
        """
        Read the full scoped key-value hash for ``scope_id``.

        Args:
            scope_id: partition id
        """
        super().__init__()
        self.scope_id = scope_id


class DeleteScopedRecordRequest(SICRequest):

    def __init__(self, scope_id: str | int) -> None:
        """
        Delete all datastore keys for ``scope_id``.

        Args:
            scope_id: partition id
        """
        super().__init__()
        self.scope_id = scope_id


# ============================================================================
# DATASTORE MANAGEMENT REQUESTS
# ============================================================================

class DeleteDeveloperSegmentRequest(SICRequest):

    def __init__(self, developer_id: int | str = None) -> None:
        """
        Delete the datastore entries belonging to the specified developer.

        When no developer_id is provided, the segment of the active developer is deleted.

        Args:
            developer_id: the ID of the developer.
        """
        super().__init__()
        self.developer_id = developer_id


class DeleteVersionSegmentRequest(SICRequest):

    def __init__(self, version: str = None) -> None:
        """
        Delete the datastore entries belonging to the specified version.

        When no version is provided, the segment of the active version is deleted.

        Args:
            version: the version label.
        """
        super().__init__()
        self.version = version


class DeleteNamespaceRequest(SICRequest):

    def __init__(self, namespace: str = None) -> None:
        """
        Delete the datastore entries belonging to the specified namespace.

        When no namespace is provided, the segment of the active namespace is deleted.

        Args:
            namespace: the namespace label.
        """
        super().__init__()
        self.namespace = namespace


# ============================================================================
# VECTOR RAG REQUESTS
# ============================================================================

class IngestVectorDocsRequest(SICRequest):

    def __init__(
        self,
        *,
        input_path: str,
        openai_api_key: str,
        index_name: str = "",
        partition: str = "default",
        glob: str = "**/*",
        chunk_chars: int = 1200,
        chunk_overlap: int = 150,
        batch_size: int = 256,
        force_recreate_index: bool = False,
        override_existing: bool = False,
        auto_index_from_folders: bool = False,
        index_prefix: str = "",
        embedding_model: str = "text-embedding-3-large",
    ) -> None:
        """
        Request to ingest documents into Redis vector indexes.
        
        Two modes are supported:
        
        1. Single Index Mode (auto_index_from_folders=False):
           - Requires explicit index_name
           - All documents from input_path go into one index
           
        2. Auto-Index Mode (auto_index_from_folders=True):
           - Recursively finds all directories containing matching files
           - Creates one index per directory using its path components
           - Example: docs/legal/contracts/*.pdf -> index "legal__contracts"
           - Use index_prefix to namespace your indices (e.g., "myapp_legal__contracts")
        
        Args:
            input_path: Path to file or directory containing documents
            openai_api_key: OpenAI API key for generating embeddings
            index_name: Explicit index name (required if auto_index_from_folders=False)
            partition: Logical partition for isolation/filtering within an index
            glob: File glob pattern to match documents (default: "**/*")
            chunk_chars: Max characters per chunk (default: 1200)
            chunk_overlap: Character overlap between consecutive chunks (default: 150)
            batch_size: Redis pipeline flush size (default: 256)
            force_recreate_index: Drop and recreate index - DESTRUCTIVE (default: False)
            override_existing: Delete existing docs for this partition before ingesting (default: False)
            auto_index_from_folders: Auto-create one index per directory with matching files (default: False)
            index_prefix: Prefix for auto-created index names (default: "")
            embedding_model: OpenAI embedding model name (default: "text-embedding-3-large")
        """
        super().__init__()
        self.input_path = input_path
        self.openai_api_key = openai_api_key
        self.index_name = index_name
        self.partition = partition
        self.glob = glob
        self.chunk_chars = chunk_chars
        self.chunk_overlap = chunk_overlap
        self.batch_size = batch_size
        self.force_recreate_index = force_recreate_index
        self.override_existing = override_existing
        self.auto_index_from_folders = auto_index_from_folders
        self.index_prefix = index_prefix
        self.embedding_model = embedding_model


class QueryVectorDBRequest(SICRequest):

    def __init__(
        self,
        *,
        index_name: str,
        query_text: str,
        openai_api_key: str,
        k: int = 5,
        partition: Optional[str] = None,
        embedding_model: str = "text-embedding-3-large",
    ) -> None:
        """
        Request to query the vector DB for documents similar to query_text.
        
        Args:
            index_name: Name of the Redis vector index to query
            query_text: Query string to find similar documents
            openai_api_key: OpenAI API key for generating embeddings
            k: Number of top results to return (default: 5)
            partition: Optional partition filter to limit search scope
            embedding_model: OpenAI embedding model name (default: "text-embedding-3-large")
        """
        super().__init__()
        self.index_name = index_name
        self.query_text = query_text
        self.openai_api_key = openai_api_key
        self.k = k
        self.partition = partition
        self.embedding_model = embedding_model


# ============================================================================
# RESPONSE MESSAGES
# ============================================================================

class VectorDBResultsMessage(SICMessage):

    def __init__(self, payload: dict[str, Any]) -> None:
        """
        Response message containing vector DB operation results.
        
        Args:
            payload: Result dict from ingestion or query operation
        """
        super().__init__()
        self.payload = payload


class ScopedKeyValuesMessage(SICMessage):

    def __init__(self, scope_id: str | int, keyvalues: dict) -> None:
        """
        Key-value payload for partition ``scope_id``.

        Args:
            scope_id: partition id
            keyvalues: field map returned from Redis
        """
        super().__init__()
        self.scope_id = scope_id
        self.keyvalues = keyvalues


class ScopedKeysMessage(SICMessage):

    def __init__(self, scope_id: str | int, keys: list) -> None:
        """
        Field names present on the scoped key-value record for ``scope_id``.

        Args:
            scope_id: partition id
            keys: Redis hash field names
        """
        super().__init__()
        self.scope_id = scope_id
        self.keys = keys


# ============================================================================
# KEYSPACE MANAGEMENT
# ============================================================================

class StoreKeyspace:
    """Hierarchical Redis keyspace: ``namespace:version:dev:developer_id:user:{id}`` (id is often a user / interactant)."""

    def __init__(self, namespace: str, version: str, developer_id: str | int):
        self.namespace = namespace
        self.version = version
        self.developer_id = developer_id

    def base(self) -> str:
        return f"{self.namespace}:{self.version}:dev:{self.developer_id}"

    def base_developer(self, developer_id: str | int = None) -> str:
        if developer_id:
            return f"{self.namespace}:{self.version}:dev:{developer_id}"
        else:
            return self.base()

    def base_version(self, version: str = None) -> str:
        if version:
            return f"{self.namespace}:{version}"
        return f"{self.namespace}:{self.version}"

    def base_namespace(self, namespace: str = None) -> str:
        if namespace:
            return namespace
        return self.namespace

    def user(self, user_id) -> str:
        return f"{self.base()}:user:{user_id}"

    def user_model(self, user_id) -> str:
        return f"{self.user(user_id)}:model"


# ============================================================================
# SERVICE COMPONENT
# ============================================================================

class RedisDatastoreComponent(SICService):
    """
    Redis Datastore Service Component
    
    Provides persistent key-value storage and vector RAG functionality.
    Requires Redis (preferably Redis Stack) to be running before initialization.
    """

    def __init__(self, *args, **kwargs):
        super(RedisDatastoreComponent, self).__init__(*args, **kwargs)

        if self.params.redis_url:
            self.redis = redis.Redis.from_url(
                self.params.redis_url,
                decode_responses=self.params.decode_responses,
                socket_connect_timeout=self.params.socket_connect_timeout,
                socket_timeout=self.params.socket_timeout,
                max_connections=self.params.max_connections,
            )
            # Binary connection for vector operations
            self.redis_binary = redis.Redis.from_url(
                self.params.redis_url,
                decode_responses=False,
                socket_connect_timeout=self.params.socket_connect_timeout,
                socket_timeout=self.params.socket_timeout,
                max_connections=self.params.max_connections,
            )
        else:
            pool = redis.ConnectionPool(
                host=self.params.host,
                port=self.params.port,
                username=self.params.username,
                password=self.params.password,
                db=self.params.db,
                decode_responses=self.params.decode_responses,
                socket_connect_timeout=self.params.socket_connect_timeout,
                socket_timeout=self.params.socket_timeout,
                max_connections=self.params.max_connections,
            )
            self.redis = redis.Redis(connection_pool=pool)
            
            # Binary connection pool for vector operations
            binary_pool = redis.ConnectionPool(
                host=self.params.host,
                port=self.params.port,
                username=self.params.username,
                password=self.params.password,
                db=self.params.db,
                decode_responses=False,
                socket_connect_timeout=self.params.socket_connect_timeout,
                socket_timeout=self.params.socket_timeout,
                max_connections=self.params.max_connections,
            )
            self.redis_binary = redis.Redis(connection_pool=binary_pool)

        # Fail fast: catch config/network issues early
        try:
            self.redis.ping()
        except Exception as e:
            raise RuntimeError(
                "{}\nOriginal error: {}".format(REDIS_CONNECTION_ERROR_MESSAGE, e)
            ) from e

        self.keyspace_manager = StoreKeyspace(namespace=self.params.namespace,
                                              version=self.params.version,
                                              developer_id=self.params.developer_id)

    @staticmethod
    def get_inputs():
        return [
            SetScopedKeyValuesRequest,
            GetScopedKeyValuesRequest,
            DeleteScopedKeyValuesRequest,
            GetScopedKeysRequest,
            GetScopedRecordRequest,
            DeleteScopedRecordRequest,
            IngestVectorDocsRequest,
            QueryVectorDBRequest,
            DeleteDeveloperSegmentRequest,
            DeleteVersionSegmentRequest,
            DeleteNamespaceRequest,
        ]

    @staticmethod
    def get_output():
        return [
            SICSuccessMessage,
            ScopedKeyValuesMessage,
            ScopedKeysMessage,
            VectorDBResultsMessage,
        ]

    @staticmethod
    def get_conf():
        return RedisDatastoreConf()

    def on_message(self, message):
        pass

    def on_request(self, request):
        return self.handle_datastore_actions(request)

    def handle_datastore_actions(self, request):
        try:
            # User model CRUD operations
            if is_sic_instance(request, SetScopedKeyValuesRequest):
                redis_key_user = self.keyspace_manager.user(request.scope_id)
                if not self.redis.exists(redis_key_user):
                    self.redis.hset(redis_key_user, mapping={'created_at': datetime.now(timezone.utc).isoformat()})
                self.redis.hset(self.keyspace_manager.user_model(request.scope_id), mapping=request.keyvalues)
                return SICSuccessMessage()

            elif is_sic_instance(request, GetScopedKeyValuesRequest):
                values = self.redis.hmget(self.keyspace_manager.user_model(request.scope_id), request.keys)
                return ScopedKeyValuesMessage(scope_id=request.scope_id, keyvalues=dict(zip(request.keys, values)))

            elif is_sic_instance(request, GetScopedKeysRequest):
                keys = self.redis.hkeys(self.keyspace_manager.user_model(request.scope_id))
                return ScopedKeysMessage(scope_id=request.scope_id, keys=keys)

            elif is_sic_instance(request, GetScopedRecordRequest):
                keyvalues = self.redis.hgetall(self.keyspace_manager.user_model(request.scope_id))
                return ScopedKeyValuesMessage(scope_id=request.scope_id, keyvalues=keyvalues)

            elif is_sic_instance(request, DeleteScopedKeyValuesRequest):
                self.redis.hdel(self.keyspace_manager.user_model(request.scope_id), *request.keys)
                return SICSuccessMessage()

            elif is_sic_instance(request, DeleteScopedRecordRequest):
                return self.delete(self.keyspace_manager.user(request.scope_id))

            # Datastore management operations
            elif is_sic_instance(request, DeleteDeveloperSegmentRequest):
                return self.delete(self.keyspace_manager.base_developer(request.developer_id))

            elif is_sic_instance(request, DeleteVersionSegmentRequest):
                return self.delete(self.keyspace_manager.base_version(request.version))

            elif is_sic_instance(request, DeleteNamespaceRequest):
                return self.delete(self.keyspace_manager.base_namespace(request.namespace))

            # Vector RAG operations
            elif is_sic_instance(request, IngestVectorDocsRequest):
                return VectorDBResultsMessage(payload=_ingest_vector_docs(self.redis_binary, request))

            elif is_sic_instance(request, QueryVectorDBRequest):
                return VectorDBResultsMessage(payload=_query_vector_db(self.redis_binary, request))

            else:
                self.logger.error("Unknown request type: {}".format(type(request)))
                
        except OutOfMemoryError as e:
            self.logger.error("Redis store is out of memory: {}".format(e))
        except DataError as e:
            self.logger.error("Invalid data for Redis operation: {}".format(e))
        except RedisError as e:
            self.logger.error("Redis error occurred: {}".format(e))

    def delete(self, keyspace):
        """Delete all keys matching the specified keyspace pattern."""
        all_keys = list(self.redis.scan_iter(match=f'{keyspace}:*'))
        if all_keys:
            self.redis.delete(*all_keys)
        return SICSuccessMessage()

    def _cleanup(self):
        """Clean up Redis connections when component stops."""
        # Stop the handler threads for this component to prevent duplicate message handling
        try:
            if hasattr(self, 'request_handler_thread') and self.request_handler_thread:
                self.logger.debug("Unregistering request handler thread")
                self._redis.unregister_callback(self.request_handler_thread)
                self.logger.debug("Request handler thread unregistered")
        except Exception as e:
            self.logger.error(f"Error unregistering request handler thread: {e}")
        
        try:
            if hasattr(self, 'message_handler_thread') and self.message_handler_thread:
                self.logger.debug("Unregistering message handler thread")
                self._redis.unregister_callback(self.message_handler_thread)
                self.logger.debug("Message handler thread unregistered")
        except Exception as e:
            self.logger.error(f"Error unregistering message handler thread: {e}")
        
        try:
            # Close the text-mode Redis connection
            r = getattr(self, "redis", None)
            if r is not None and hasattr(r, "close"):
                self.logger.debug("Closing datastore Redis connection")
                r.close()
                self.logger.debug("Datastore Redis connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing datastore Redis connection: {e}")
        
        try:
            # Close the binary-mode Redis connection
            r_binary = getattr(self, "redis_binary", None)
            if r_binary is not None and hasattr(r_binary, "close"):
                self.logger.debug("Closing datastore binary Redis connection")
                r_binary.close()
                self.logger.debug("Datastore binary Redis connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing datastore binary Redis connection: {e}")


# ============================================================================
# VECTOR RAG IMPLEMENTATION
# ============================================================================

# File I/O helpers

def _iter_files(input_path: Path, glob_pattern: str) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path
        return
    if not input_path.is_dir():
        raise FileNotFoundError("Input path not found: {}".format(input_path))
    yield from (p for p in input_path.rglob(glob_pattern) if p.is_file())


def _read_document(path: Path) -> str:
    """Read a document file (text or PDF) and return its content as a string."""
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency: pypdf.\n"
                "Install it with: pip install pypdf\n"
                "Original import error: {}".format(e)
            ) from e

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts)
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


# Text processing helpers

def _chunk_text(text: str, chunk_chars: int, chunk_overlap: int) -> list[str]:
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_chars:
        raise ValueError("chunk_overlap must be < chunk_chars")
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


# OpenAI embedding helpers

def _openai_embed_texts(texts: list[str], *, model: str, api_key: str) -> list[list[float]]:
    """Embed a list of texts using OpenAI embeddings API."""
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: openai.\n"
            "Install it with: pip install openai\n"
            "Original import error: {}".format(e)
        ) from e
    if not api_key:
        raise RuntimeError("openai_api_key parameter is required")
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=texts)
    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]


def _openai_embed_text(text: str, *, model: str, api_key: str) -> list[float]:
    return _openai_embed_texts([text], model=model, api_key=api_key)[0]


def _to_float32_blob(vec) -> bytes:
    try:
        import numpy as np  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: numpy.\n"
            "Install it with: pip install numpy\n"
            "Original import error: {}".format(e)
        ) from e
    return np.asarray(vec, dtype=np.float32).tobytes(order="C")


# Redis connection helpers

# Index management

def sanitize_index_name(name: str) -> str:
    """Replace non-alphanumeric chars with underscores for safe Redis index names."""
    cleaned = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in name.strip())
    return cleaned or "index"


def compose_index_name_from_path(folder_names: list[str], index_prefix: str = "") -> str:
    """
    Utility: Compose index name from a list of folder names.
    
    This constructs an index name by joining folder names with double underscores.
    Format: <prefix><folder1>__<folder2>__<folder3>
    
    Args:
        folder_names: List of folder names to join (e.g., ["episode1", "character1"])
        index_prefix: Optional prefix to prepend to the index name
    
    Returns:
        Sanitized index name
    
    Example:
        compose_index_name_from_path(["docs", "legal"], "myapp_")
        # Returns: "myapp_docs__legal"
    """
    joined = "__".join(folder_names)
    return sanitize_index_name("{}{}".format(index_prefix, joined))


def _ensure_index(r: redis.Redis, index_name: str, dim: int, *, key_prefix: str, force_recreate: bool) -> None:
    """Ensure Redis vector search index exists with correct schema."""
    # Check if index exists
    try:
        r.execute_command("FT.INFO", index_name)
        exists = True
    except redis.ResponseError as e:
        error_msg = str(e).lower()
        if "unknown command" in error_msg or "ft.info" in error_msg:
            raise RuntimeError(
                "{}\nOriginal error: {}".format(REDIS_STACK_INSTALL_MESSAGE, e)
            ) from e
        exists = False
    
    # Drop index if recreating
    if force_recreate and exists:
        try:
            r.execute_command("FT.DROPINDEX", index_name, "DD")
        except redis.ResponseError as e:
            error_msg = str(e).lower()
            if "unknown command" in error_msg:
                raise RuntimeError(
                    "{}\nOriginal error: {}".format(REDIS_STACK_INSTALL_MESSAGE, e)
                ) from e
            raise
        exists = False
    
    # Create index if needed
    if not exists:
        try:
            r.execute_command(
                "FT.CREATE", index_name,
                "ON", "HASH",
                "PREFIX", 1, key_prefix,
                "SCHEMA",
                "partition", "TAG", "SEPARATOR", "|",
                "doc_path", "TEXT",
                "chunk_id", "NUMERIC",
                "content", "TEXT",
                "embedding", "VECTOR", "HNSW", 6,
                "TYPE", "FLOAT32",
                "DIM", dim,
                "DISTANCE_METRIC", "COSINE",
            )
        except redis.ResponseError as e:
            error_msg = str(e).lower()
            if "unknown command" in error_msg or "ft.create" in error_msg:
                raise RuntimeError(
                    "{}\nOriginal error: {}".format(REDIS_STACK_INSTALL_MESSAGE, e)
                ) from e
            raise


def _delete_existing_docs(r: redis.Redis, *, key_prefix: str, partition: str, batch_size: int) -> int:
    """Delete all existing documents for a partition before re-ingesting."""
    pattern = "{}{}:*".format(key_prefix, partition)
    pipe = r.pipeline(transaction=False)
    deleted = 0
    
    for key in r.scan_iter(match=pattern, count=1000):
        pipe.unlink(key) if hasattr(pipe, 'unlink') else pipe.delete(key)
        deleted += 1
        if pipe.command_stack and len(pipe.command_stack) >= batch_size:
            pipe.execute()
    
    if pipe.command_stack:
        pipe.execute()
    
    return deleted


# Ingestion logic

def _ingest_one_index(
    *,
    redis_conn: redis.Redis,
    index_name: str,
    partition: str,
    input_path: Path,
    glob_pattern: str,
    chunk_chars: int,
    chunk_overlap: int,
    batch_size: int,
    force_recreate_index: bool,
    override_existing: bool,
    embedding_model: str,
    openai_api_key: str,
) -> dict[str, Any]:
    """Ingest documents from a path into a single Redis vector index."""
    key_prefix = "vec:{}:".format(index_name)
    
    # Ensure index exists with correct dimensionality
    embedding_dim = len(_openai_embed_text("dimension probe", model=embedding_model, api_key=openai_api_key))
    _ensure_index(redis_conn, index_name, embedding_dim, key_prefix=key_prefix, force_recreate=force_recreate_index)
    
    # Optionally clear existing docs for this partition
    if override_existing and not force_recreate_index:
        _delete_existing_docs(redis_conn, key_prefix=key_prefix, partition=partition, batch_size=batch_size)
    
    # Collect and validate files
    files = list(_iter_files(input_path, glob_pattern))
    if not files:
        raise RuntimeError("No files matched under {} with glob {!r}".format(input_path, glob_pattern))
    
    # Process each file: read → chunk → embed → store
    total_chunks = 0
    pipe = redis_conn.pipeline(transaction=False)
    for file_path in files:
        chunks = _chunk_text(_read_document(file_path), chunk_chars, chunk_overlap)
        if not chunks:
            continue
        
        file_id = _sha1(str(file_path.resolve()))
        total_chunks += len(chunks)
        embeddings = _openai_embed_texts(chunks, model=embedding_model, api_key=openai_api_key)
        
        for i, chunk in enumerate(chunks):
            key = "{}{}:{}:{}".format(key_prefix, partition, file_id, i).encode("utf-8")
            pipe.hset(key, mapping={
                b"partition": partition.encode("utf-8"),
                b"doc_path": str(file_path).encode("utf-8"),
                b"chunk_id": str(i).encode("utf-8"),
                b"content": chunk.encode("utf-8", errors="ignore"),
                b"embedding": _to_float32_blob(embeddings[i]),
            })
            if pipe.command_stack and len(pipe.command_stack) >= batch_size:
                pipe.execute()
    
    if pipe.command_stack:
        pipe.execute()
    
    return {"ok": True, "index": index_name, "partition": partition, "files": len(files), "chunks": total_chunks}


def _ingest_vector_docs(redis_conn: redis.Redis, request: IngestVectorDocsRequest) -> dict[str, Any]:
    """Handle IngestVectorDocsRequest by ingesting documents into Redis vector indexes."""
    root = Path(request.input_path)

    # Auto-index mode: create one index per leaf directory containing matching files
    if request.auto_index_from_folders:
        if not root.exists() or not root.is_dir():
            raise RuntimeError("input_path must be a directory when auto_index_from_folders=True")
        
        results: list[dict[str, Any]] = []
        
        # Recursively find directories that should each get their own index.
        def find_document_dirs(base_path: Path) -> list[tuple[Path, list[str]]]:
            """
            Recursively find directories with matching documents.
            Returns list of (directory_path, folder_name_components) tuples.
            """
            doc_dirs: list[tuple[Path, list[str]]] = []
            subdirs = [p for p in sorted(base_path.iterdir()) if p.is_dir()]

            for sub in subdirs:
                doc_dirs.extend(find_document_dirs(sub))

            if not doc_dirs and any(_iter_files(base_path, request.glob)):
                relative_path = base_path.relative_to(root)
                folder_names = list(relative_path.parts)
                doc_dirs.append((base_path, folder_names))

            return doc_dirs
        
        document_directories = find_document_dirs(root)
        
        if not document_directories:
            raise RuntimeError("No directories with matching documents found in {}".format(root))
        
        for doc_dir, folder_names in document_directories:
            index_name = compose_index_name_from_path(folder_names, request.index_prefix)
            
            results.append(_ingest_one_index(
                redis_conn=redis_conn,
                index_name=index_name,
                partition="default",
                input_path=doc_dir,
                glob_pattern=request.glob,
                chunk_chars=request.chunk_chars,
                chunk_overlap=request.chunk_overlap,
                batch_size=request.batch_size,
                force_recreate_index=request.force_recreate_index,
                override_existing=request.override_existing,
                embedding_model=request.embedding_model,
                openai_api_key=request.openai_api_key,
            ))
        
        return {"ok": True, "results": results}

    # Single index mode: use explicit index_name
    if not request.index_name:
        raise RuntimeError("index_name is required when auto_index_from_folders=False")

    single = _ingest_one_index(
        redis_conn=redis_conn,
        index_name=sanitize_index_name(request.index_name),
        partition=request.partition,
        input_path=root,
        glob_pattern=request.glob,
        chunk_chars=request.chunk_chars,
        chunk_overlap=request.chunk_overlap,
        batch_size=request.batch_size,
        force_recreate_index=request.force_recreate_index,
        override_existing=request.override_existing,
        embedding_model=request.embedding_model,
        openai_api_key=request.openai_api_key,
    )
    return {"ok": True, "results": [single]}


# Query logic

def _query_vector_db(redis_conn: redis.Redis, request: QueryVectorDBRequest) -> dict[str, Any]:
    """Handle QueryVectorDBRequest by searching for similar documents in Redis vector index."""
    if request.k <= 0:
        raise ValueError("k must be > 0")
    
    index = sanitize_index_name(request.index_name)
    
    # Embed query and prepare vector search
    query_embedding = _openai_embed_text(request.query_text, model=request.embedding_model, api_key=request.openai_api_key)
    blob = _to_float32_blob(query_embedding)
    
    # Build RediSearch query with optional partition filter
    filter_base = "@partition:{{{}}}".format(request.partition) if request.partition else "*"
    query = "{}=>[KNN {} @embedding $vec AS score]".format(filter_base, request.k)
    
    # Execute vector similarity search
    try:
        res = redis_conn.execute_command(
            "FT.SEARCH", index, query,
            "PARAMS", 2, "vec", blob,
            "SORTBY", "score",
            "RETURN", 4, "score", "doc_path", "chunk_id", "content",
            "DIALECT", 2,
        )
    except redis.ResponseError as e:
        error_msg = str(e).lower()
        if "unknown command" in error_msg or "ft.search" in error_msg:
            raise RuntimeError(
                "{}\nOriginal error: {}".format(REDIS_STACK_INSTALL_MESSAGE, e)
            ) from e
        if "no such index" in error_msg or "unknown index" in error_msg:
            raise RuntimeError(
                "Index '{}' does not exist. Ingest documents first using IngestVectorDocsRequest.\n"
                "Original error: {}".format(index, e)
            ) from e
        raise
    
    if not res:
        return {"index": index, "total": 0, "results": []}
    
    # Parse results
    total = int(res[0])
    results = []
    for i in range(1, len(res), 2):
        doc_id = str_if_bytes(res[i], errors="ignore")
        fields = res[i + 1]
        
        # Parse field list into dict
        parsed = {}
        if isinstance(fields, list):
            for j in range(0, len(fields), 2):
                parsed[str_if_bytes(fields[j], errors="ignore")] = fields[j + 1]
        
        # Extract and parse score
        score_str = str_if_bytes(parsed.get("score", b""), errors="ignore")
        try:
            score = float(score_str)
        except Exception:
            score = score_str
        
        results.append({
            "doc_id": doc_id,
            "score": score,
            "doc_path": str_if_bytes(parsed.get("doc_path", b""), errors="ignore"),
            "chunk_id": str_if_bytes(parsed.get("chunk_id", b""), errors="ignore"),
            "content": str_if_bytes(parsed.get("content", b""), errors="ignore").strip(),
        })
    
    return {"index": index, "total": total, "results": results}


def _default_redis_args_for_datastore(persist_data: bool) -> str:
    """
    Build default Redis server args used when creating a new Redis Stack container.

    Notes:
    - Always sets ``--requirepass changemeplease`` to match SIC defaults (``DB_PASS``).
    - Adds ``--appendonly yes`` only when ``persist_data`` is True (i.e. a ``--data-dir``
      host bind mount is requested), so writes are durably appended to AOF files in ``/data``.
    """
    args = "--requirepass changemeplease"
    if persist_data:
        args += " --appendonly yes"
    return args


def _docker_inspect_running(container_name: str) -> Optional[bool]:
    """
    Return True if container exists and is running, False if stopped, None if missing.
    """
    r = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            container_name,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip().lower()
    if out == "true":
        return True
    if out == "false":
        return False
    return None


def _docker_inspect_config(container_name: str) -> Optional[dict]:
    """
    Return full ``docker inspect`` config JSON for a container.

    Used to compare an already-existing container with the currently requested
    ``run-redis`` arguments (image, port mappings, mounts, REDIS_ARGS, command).
    Returns ``None`` when the container does not exist or inspect output is invalid.
    """
    r = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    try:
        parsed = json.loads(r.stdout or "[]")
    except Exception:
        return None
    return parsed[0] if parsed else None


def _container_matches_spec(
    inspect_data: dict,
    *,
    image: str,
    host_port: int,
    insight_port: int,
    data_dir: Optional[str],
    redis_conf: Optional[str],
    redis_args: Optional[str],
) -> tuple[bool, list[str]]:
    """
    Validate an existing container against the desired datastore runtime spec.

    This protects persistence semantics: if a user changes ``--data-dir`` (or other
    container-shaping args), we should not silently keep running an old container that
    points at a different storage location.

    Compared attributes:
    - image
    - host ports (6379 and 8001)
    - mount sources for ``/data`` and optional ``redis.conf``
    - ``REDIS_ARGS`` env (where applicable)
    - command argument including optional redis.conf path

    Returns:
        (is_match, mismatch_reasons)
    """
    reasons: list[str] = []
    desired_data_dir = str(Path(data_dir).expanduser().resolve()) if data_dir else None
    desired_conf = str(Path(redis_conf).expanduser().resolve()) if redis_conf else None
    desired_args = redis_args if redis_args is not None else _default_redis_args_for_datastore(bool(data_dir))

    current_image = (inspect_data.get("Config") or {}).get("Image", "")
    if current_image != image:
        reasons.append("image")

    ports = ((inspect_data.get("NetworkSettings") or {}).get("Ports") or {})
    p6379 = ports.get("6379/tcp")
    p8001 = ports.get("8001/tcp")
    current_6379 = p6379[0].get("HostPort") if p6379 else None
    current_8001 = p8001[0].get("HostPort") if p8001 else None
    if current_6379 != str(host_port):
        reasons.append("host-port")
    if current_8001 != str(insight_port):
        reasons.append("insight-port")

    mounts = inspect_data.get("Mounts") or []
    mount_map = {m.get("Destination"): m for m in mounts if m.get("Destination")}
    data_mount = mount_map.get("/data")
    conf_mount = mount_map.get("/usr/local/etc/redis/redis.conf")

    if desired_data_dir:
        if not data_mount or str(Path(data_mount.get("Source", "")).resolve()) != desired_data_dir:
            reasons.append("data-dir")
    else:
        if data_mount:
            reasons.append("data-dir")

    if desired_conf:
        if not conf_mount or str(Path(conf_mount.get("Source", "")).resolve()) != desired_conf:
            reasons.append("redis-conf")
    else:
        if conf_mount:
            reasons.append("redis-conf")

    env = (inspect_data.get("Config") or {}).get("Env") or []
    env_map = {}
    for item in env:
        if "=" in item:
            k, v = item.split("=", 1)
            env_map[k] = v
    current_args = env_map.get("REDIS_ARGS")
    if redis_conf:
        if redis_args is not None and current_args != desired_args:
            reasons.append("redis-args")
    else:
        if current_args != desired_args:
            reasons.append("redis-args")

    current_cmd = (inspect_data.get("Config") or {}).get("Cmd") or []
    has_conf_cmd = "/usr/local/etc/redis/redis.conf" in current_cmd
    if bool(desired_conf) != bool(has_conf_cmd):
        reasons.append("redis-conf-cmd")

    return len(reasons) == 0, reasons


def _wait_for_tcp(
    host: str,
    port: int,
    timeout_sec: float = 30.0,
    container_name: Optional[str] = None,
) -> None:
    """
    Wait for TCP readiness on ``host:port``.

    If ``container_name`` is provided, this also checks that the container has not
    transitioned to stopped state while waiting. If it has stopped, we surface recent
    container logs to make startup/persistence failures easier to debug.
    """
    deadline = time.time() + timeout_sec
    last_err = None
    while time.time() < deadline:
        if container_name:
            state = _docker_inspect_running(container_name)
            if state is False:
                logs = subprocess.run(
                    ["docker", "logs", "--tail", "40", container_name],
                    capture_output=True,
                    text=True,
                )
                raise RuntimeError(
                    "Redis container '{name}' is not running while waiting for {host}:{port}.\n"
                    "Recent logs:\n{logs}".format(
                        name=container_name,
                        host=host,
                        port=port,
                        logs=(logs.stdout or logs.stderr or "").strip(),
                    )
                )
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.4)
    raise RuntimeError(
        "Timed out waiting for Redis at {host}:{port}. Last error: {err}".format(
            host=host, port=port, err=last_err
        )
    )


def ensure_redis_stack_container(
    container_name: str,
    host_port: int,
    insight_port: int,
    data_dir: Optional[str],
    redis_conf: Optional[str],
    redis_args: Optional[str],
    image: str = DEFAULT_REDIS_STACK_IMAGE,
) -> None:
    """
    Ensure a Redis Stack container is running with the requested runtime configuration.

    Behavior:
    1. If the container does not exist, create it.
    2. If it exists and matches the requested spec, start it if needed.
    3. If it exists but differs (ports/mounts/image/args/conf), recreate it so the
       runtime actually reflects current CLI arguments.

    Persistence semantics with ``data_dir``:
    - ``data_dir`` is bind-mounted to container ``/data``.
    - Redis loads existing AOF/RDB files from that directory on startup when present.
    - Redis does not blindly wipe the directory; data loss requires explicit destructive
      actions (deleting files, flush commands, changing mount target, etc.).

    :param data_dir: optional host directory bind-mounted to ``/data`` in the container.
    :param redis_conf: optional host path to ``redis.conf``, mounted read-only and passed to ``redis-stack-server``.
    :param redis_args: optional ``REDIS_ARGS`` env value for the container (redis-server arguments).
        If omitted, a default with ``--requirepass changemeplease`` is used (and ``--appendonly yes`` when ``data_dir`` is set).
    """
    if not shutil.which("docker"):
        raise RuntimeError(DOCKER_NOT_INSTALLED_MESSAGE)

    subprocess.run(["docker", "version"], capture_output=True, check=True)

    state = _docker_inspect_running(container_name)
    persist = bool(data_dir)
    default_args = _default_redis_args_for_datastore(persist)
    inspect_data = _docker_inspect_config(container_name) if state is not None else None
    if state is not None and inspect_data is not None:
        is_match, mismatches = _container_matches_spec(
            inspect_data,
            image=image,
            host_port=host_port,
            insight_port=insight_port,
            data_dir=data_dir,
            redis_conf=redis_conf,
            redis_args=redis_args,
        )
        if not is_match:
            if state is True:
                subprocess.run(["docker", "stop", container_name], check=True)
            subprocess.run(["docker", "rm", container_name], check=True)
            state = None
        elif state is True:
            _wait_for_tcp("127.0.0.1", host_port, container_name=container_name)
            return
        else:
            subprocess.run(["docker", "start", container_name], check=True)
            _wait_for_tcp("127.0.0.1", host_port, container_name=container_name)
            return

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--restart",
        "unless-stopped",
        "-p",
        "{h}:6379".format(h=host_port),
        "-p",
        "{ins}:8001".format(ins=insight_port),
    ]
    if data_dir:
        abs_data = str(Path(data_dir).expanduser().resolve())
        Path(abs_data).mkdir(parents=True, exist_ok=True)
        cmd.extend(["-v", "{p}:/data".format(p=abs_data)])
    if redis_conf:
        abs_conf = str(Path(redis_conf).expanduser().resolve())
        if not Path(abs_conf).is_file():
            raise FileNotFoundError("redis-conf not found: {}".format(abs_conf))
        cmd.extend(["-v", "{p}:/redis-stack.conf:ro".format(p=abs_conf)])
        if redis_args is not None:
            cmd.extend(["-e", "REDIS_ARGS={}".format(redis_args)])
    else:
        cmd.extend(["-e", "REDIS_ARGS={}".format(redis_args if redis_args is not None else default_args)])
    cmd.append(image)

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            "docker run failed (exit {code}): {err}\n{out}".format(
                code=r.returncode,
                err=(r.stderr or "").strip(),
                out=(r.stdout or "").strip(),
            )
        )
    _wait_for_tcp("127.0.0.1", host_port, container_name=container_name)


# ============================================================================
# SERVICE CONNECTOR & ENTRY POINT
# ============================================================================

class RedisDatastore(SICConnector):
    """Connector for Redis datastore component"""
    component_class = RedisDatastoreComponent
    component_group = "RedisDatastore"


def main():
    parser = argparse.ArgumentParser(
        description="Start Redis Stack in Docker (unless skipped) and run the SIC Redis datastore service."
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Do not start Docker; Redis Stack must already be reachable (e.g. messaging-only apps unchanged).",
    )
    parser.add_argument(
        "--container-name",
        default="sic-redis-stack",
        help="Docker container name for Redis Stack (default: sic-redis-stack).",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_REDIS_STACK_IMAGE,
        help="Redis Stack image (default: redis/redis-stack:latest).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        metavar="PATH",
        help="Host directory bind-mounted to /data in the container for persistence.",
    )
    parser.add_argument(
        "--host-port",
        type=int,
        default=6379,
        metavar="PORT",
        help="Host TCP port mapped to Redis 6379 inside the container. Sets DB_PORT for SIC.",
    )
    parser.add_argument(
        "--insight-port",
        type=int,
        default=8001,
        metavar="PORT",
        help="Host port mapped to RedisInsight 8001 in the container.",
    )
    parser.add_argument(
        "--redis-conf",
        default=None,
        metavar="PATH",
        help="Host path to redis.conf, mounted read-only at /usr/local/etc/redis/redis.conf.",
    )
    parser.add_argument(
        "--redis-args",
        default=None,
        metavar="STRING",
        help="REDIS_ARGS for the container. Default: --requirepass changemeplease "
        "(and --appendonly yes if --data-dir is set). With --redis-conf, omit unless you need extra flags.",
    )
    args = parser.parse_args()

    if not args.skip_docker:
        ensure_redis_stack_container(
            container_name=args.container_name,
            host_port=args.host_port,
            insight_port=args.insight_port,
            data_dir=args.data_dir,
            redis_conf=args.redis_conf,
            redis_args=args.redis_args,
            image=args.image,
        )

    os.environ.setdefault("DB_IP", "127.0.0.1")
    os.environ["DB_PORT"] = str(args.host_port)
    os.environ.setdefault("DB_PASS", "changemeplease")

    SICComponentManager([RedisDatastoreComponent], component_group="RedisDatastore")


if __name__ == "__main__":
    main()