"""
Redis Database Service: Unified Key-Value Store + Vector RAG

This module provides both persistent key-value storage (user models) and vector-based
retrieval-augmented generation (RAG) for document search, backed by Redis Stack.

All functionality is accessed via SIC service requests through RedisDatabaseComponent.

=== ORGANIZATIONAL STRUCTURE ===

1. Configuration:
   - RedisDatabaseConf: Redis connection and keyspace namespacing

2. Request Classes:
   - User Model: SetUsermodelValuesRequest, GetUsermodelValuesRequest, DeleteUsermodelValuesRequest, etc.
   - Database Management: DeleteDeveloperSegmentRequest, DeleteVersionSegmentRequest, DeleteNamespaceRequest
   - Vector RAG: IngestVectorDocsRequest, QueryVectorDBRequest

3. Response Messages:
   - UsermodelKeyValuesMessage, UsermodelKeysMessage, VectorDBResultsMessage, SICSuccessMessage

4. Service Component:
   - RedisDatabaseComponent: Handles all requests via on_request()
   - RedisDatabase: SIC connector for client usage

=== USAGE ===

Start Redis Stack manually:
    docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 -v redis-stack-data:/data redis/redis-stack:latest

Start the service (components auto-start on launch):
    run-redis

Send requests from your application:

    from sic_framework.services.database import (
        RedisDatabase,
        RedisDatabaseConf,
        SetUsermodelValuesRequest,
        IngestVectorDocsRequest,
        QueryVectorDBRequest,
    )

    # Connect to the Redis service
    db = RedisDatabase(conf=RedisDatabaseConf(redis_url="redis://:password@localhost:6379/0"))

    # User model operations
    db.request(SetUsermodelValuesRequest(user_id=123, keyvalues={"name": "Alice"}))

    # Ingest documents into vector DB
    result = db.request(IngestVectorDocsRequest(
        input_path="/path/to/documents",
        auto_index_from_folders=True,
        index_prefix="myproject_",
        embedding_model="text-embedding-3-large",
        override_existing=True,
    ))

    # Query vector DB
    response = db.request(QueryVectorDBRequest(
        episode="episode1",
        character="trudy",
        query_text="What is the main theme?",
        k=5,
        index_prefix="myproject_",
        embedding_model="text-embedding-3-large",
    ))
    print(response.payload)

=== PREREQUISITES ===

Redis Stack must be running and accessible before starting this service.
The service will raise an error on startup if it cannot connect to Redis.
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import redis
from redis.exceptions import OutOfMemoryError, DataError, RedisError

from sic_framework import SICConfMessage, SICComponentManager, SICMessage, SICRequest, SICSuccessMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.utils import is_sic_instance


# ============================================================================
# CONFIGURATION
# ============================================================================


class RedisDatabaseConf(SICConfMessage):
    """
    Configuration for setting up the connection to a persistent Redis database.

    Args:
        host: IP address of the Redis server. Default is localhost.
        port: Port of the Redis server. Default is 6379.
        password: optional password to redis server.
        username: optional username to redis server.
        socket_connect_timeout: timeout for connecting to Redis server. Default is 2 seconds.
        socket_timeout: socket timeout in seconds. Default is 2 seconds.
        decode_responses: whether to decode standard byte response from Redis server. Default is True.
        namespace: basic namespace of the redis database. Default is 'store'.
        version: version of the namespace. Default is 'v1'.
        developer_id: id of the developer user. Default is 0.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0,
                 redis_url: Optional[str] = None,
                 password: Optional[str] = None, username: Optional[str] = None,
                 socket_connect_timeout: float = 2.0, socket_timeout: float = 2.0,
                 max_connections: int = 50, decode_responses: bool = True,
                 namespace: str = "store", version: str = "v1", developer_id: str | int = 0):
        super(SICConfMessage, self).__init__()

        # Redis basic configuration
        self.host = host
        self.port = port
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
# USER MODEL REQUESTS
# ============================================================================

class SetUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """

        Sets a value in the user model under the specified key of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super().__init__()
        self.user_id = user_id
        self.keyvalues = keyvalues


class GetUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        Request to retrieve values from user models based on the provided list of keys

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list of keys of which the values need to be retrieved
        """
        super().__init__()
        self.user_id = user_id
        self.keys = keys


class DeleteUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        Message to delete values from user models based on the provided list of keys

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list of keys of which the values need to be deleted
        """
        super().__init__()
        self.user_id = user_id
        self.keys = keys


class GetUsermodelKeysRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to inspect the existing user model keys for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


class GetUsermodelRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to retrieve the whole user model for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


class DeleteUserRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Delete user with ID user_id

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


# ============================================================================
# DATABASE MANAGEMENT REQUESTS
# ============================================================================

class DeleteDeveloperSegmentRequest(SICRequest):

    def __init__(self, developer_id: int | str = None) -> None:
        """
        Delete the database entries belonging to the specified developer.

        When no developer_id is provided, the segment of the active developer is deleted.

        Args:
            developer_id: the ID of the developer.
        """
        super().__init__()
        self.developer_id = developer_id


class DeleteVersionSegmentRequest(SICRequest):

    def __init__(self, version: str = None) -> None:
        """
        Delete the database entries belonging to the specified version.

        When no version is provided, the segment of the active version is deleted.

        Args:
            version: the version label.
        """
        super().__init__()
        self.version = version


class DeleteNamespaceRequest(SICRequest):

    def __init__(self, namespace: str = None) -> None:
        """
        Delete the database entries belonging to the specified namespace.

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
        
        Args:
            input_path: Path to file or directory containing documents
            index_name: Explicit index name (required if auto_index_from_folders=False)
            partition: Logical partition for isolation/filtering
            glob: File glob pattern when input_path is a directory
            chunk_chars: Max characters per chunk
            chunk_overlap: Character overlap between consecutive chunks
            batch_size: Redis pipeline flush size
            force_recreate_index: Drop and recreate index (destructive)
            override_existing: Delete existing docs for this partition before ingesting
            auto_index_from_folders: Auto-create indexes from <episode>/<character>/ structure
            index_prefix: Prefix for auto-created index names
            embedding_model: OpenAI embedding model name
        """
        super().__init__()
        self.input_path = input_path
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
        episode: str,
        character: str,
        query_text: str,
        k: int = 5,
        partition: Optional[str] = None,
        index_prefix: str = "",
        embedding_model: str = "text-embedding-3-large",
    ) -> None:
        """
        Request to query the vector DB for documents similar to query_text.
        
        Args:
            episode: Episode name (used to compose index name)
            character: Character name (used to compose index name)
            query_text: Query string to find similar documents
            k: Number of top results to return
            partition: Optional partition filter
            index_prefix: Index name prefix
            embedding_model: OpenAI embedding model name
        """
        super().__init__()
        self.episode = episode
        self.character = character
        self.query_text = query_text
        self.k = k
        self.partition = partition
        self.index_prefix = index_prefix
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


class UsermodelKeyValuesMessage(SICMessage):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """
        Dictionary containing the user model (or a selection thereof) of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super().__init__()
        self.user_id = user_id
        self.keyvalues = keyvalues


class UsermodelKeysMessage(SICMessage):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        List containing all the keys in the user model of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list containing all the user model keys.
        """
        super().__init__()
        self.user_id = user_id
        self.keys = keys


# ============================================================================
# KEYSPACE MANAGEMENT
# ============================================================================

class StoreKeyspace:
    """Manages hierarchical Redis keyspace: namespace:version:dev:developer_id:user:user_id"""

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

class RedisDatabaseComponent(SICService):
    """
    Redis Database Service Component
    
    Provides persistent key-value storage and vector RAG functionality.
    Requires Redis Stack to be running before initialization.
    """

    def __init__(self, *args, **kwargs):
        super(RedisDatabaseComponent, self).__init__(*args, **kwargs)

        if self.params.redis_url:
            self.redis = redis.Redis.from_url(
                self.params.redis_url,
                decode_responses=self.params.decode_responses,
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

        # Fail fast: catch config/network issues early
        try:
            self.redis.ping()
        except Exception as e:
            raise RuntimeError(
                "Failed to connect to Redis. Make sure Redis Stack is running.\n"
                "Start Redis with: docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 "
                "-v redis-stack-data:/data redis/redis-stack:latest\n"
                "Original error: {}".format(e)
            ) from e

        self.keyspace_manager = StoreKeyspace(namespace=self.params.namespace,
                                              version=self.params.version,
                                              developer_id=self.params.developer_id)

    @staticmethod
    def get_inputs():
        return [SetUsermodelValuesRequest, GetUsermodelValuesRequest, DeleteUsermodelValuesRequest,
                GetUsermodelKeysRequest, GetUsermodelRequest, DeleteUserRequest,
                IngestVectorDocsRequest, QueryVectorDBRequest]

    @staticmethod
    def get_output():
        return [SICSuccessMessage, UsermodelKeyValuesMessage, UsermodelKeysMessage, VectorDBResultsMessage]

    @staticmethod
    def get_conf():
        return RedisDatabaseConf()

    def on_message(self, message):
        pass

    def on_request(self, request):
        return self.handle_database_actions(request)

    def handle_database_actions(self, request):
        try:
            # User model CRUD operations
            if is_sic_instance(request, SetUsermodelValuesRequest):
                redis_key_user = self.keyspace_manager.user(request.user_id)
                if not self.redis.exists(redis_key_user):
                    self.redis.hset(redis_key_user, mapping={'created_at': datetime.now(timezone.utc).isoformat()})
                self.redis.hset(self.keyspace_manager.user_model(request.user_id), mapping=request.keyvalues)
                return SICSuccessMessage()

            elif is_sic_instance(request, GetUsermodelValuesRequest):
                values = self.redis.hmget(self.keyspace_manager.user_model(request.user_id), request.keys)
                return UsermodelKeyValuesMessage(user_id=request.user_id, keyvalues=dict(zip(request.keys, values)))

            elif is_sic_instance(request, GetUsermodelKeysRequest):
                keys = self.redis.hkeys(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeysMessage(user_id=request.user_id, keys=keys)

            elif is_sic_instance(request, GetUsermodelRequest):
                keyvalues = self.redis.hgetall(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeyValuesMessage(user_id=request.user_id, keyvalues=keyvalues)

            elif is_sic_instance(request, DeleteUsermodelValuesRequest):
                self.redis.hdel(self.keyspace_manager.user_model(request.user_id), *request.keys)
                return SICSuccessMessage()

            elif is_sic_instance(request, DeleteUserRequest):
                return self.delete(self.keyspace_manager.user(request.user_id))

            # Database management operations
            elif is_sic_instance(request, DeleteDeveloperSegmentRequest):
                return self.delete(self.keyspace_manager.base_developer(request.developer_id))

            elif is_sic_instance(request, DeleteVersionSegmentRequest):
                return self.delete(self.keyspace_manager.base_version(request.version))

            elif is_sic_instance(request, DeleteNamespaceRequest):
                return self.delete(self.keyspace_manager.base_namespace(request.namespace))

            # Vector RAG operations
            elif is_sic_instance(request, IngestVectorDocsRequest):
                return VectorDBResultsMessage(payload=_ingest_vector_docs(self.params, request))

            elif is_sic_instance(request, QueryVectorDBRequest):
                return VectorDBResultsMessage(payload=_query_vector_db(self.params, request))

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

    def stop(self, *args):
        super(RedisDatabaseComponent, self).stop(*args)

    def _cleanup(self):
        try:
            r = getattr(self, "redis", None)
            if r is not None and hasattr(r, "close"):
                r.close()
        except Exception:
            pass


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

def _openai_embed_texts(texts: list[str], *, model: str) -> list[list[float]]:
    """Embed a list of texts using OpenAI embeddings API."""
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: openai.\n"
            "Install it with: pip install openai\n"
            "Original import error: {}".format(e)
        ) from e
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=texts)
    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]


def _openai_embed_text(text: str, *, model: str) -> list[float]:
    return _openai_embed_texts([text], model=model)[0]


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

def _redis_binary_connection_from_conf(conf: RedisDatabaseConf) -> redis.Redis:
    if conf.redis_url:
        return redis.Redis.from_url(
            conf.redis_url,
            decode_responses=False,
            socket_connect_timeout=conf.socket_connect_timeout,
            socket_timeout=conf.socket_timeout,
        )
    return redis.Redis(
        host=conf.host,
        port=conf.port,
        username=conf.username,
        password=conf.password,
        db=conf.db,
        decode_responses=False,
        socket_connect_timeout=conf.socket_connect_timeout,
        socket_timeout=conf.socket_timeout,
    )


def _b2s(x: Any) -> str:
    """Convert bytes to string, pass through other types as str."""
    if isinstance(x, (bytes, bytearray)):
        return x.decode("utf-8", errors="ignore")
    return str(x)


# Index management

def sanitize_index_name(name: str) -> str:
    """Replace non-alphanumeric chars with underscores for safe Redis index names."""
    cleaned = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in name.strip())
    return cleaned or "index"


def compose_index_name(*, episode: str, character: str, index_prefix: str = "") -> str:
    """Create index name from episode and character: <prefix><episode>__<character>"""
    return sanitize_index_name("{}{}__{}".format(index_prefix, episode, character))


def _ensure_index(r: redis.Redis, index_name: str, dim: int, *, key_prefix: str, force_recreate: bool) -> None:
    """Ensure Redis vector search index exists with correct schema."""
    # Check if index exists
    try:
        r.execute_command("FT.INFO", index_name)
        exists = True
    except redis.ResponseError:
        exists = False
    
    # Drop index if recreating
    if force_recreate and exists:
        r.execute_command("FT.DROPINDEX", index_name, "DD")
        exists = False
    
    # Create index if needed
    if not exists:
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
    conf: RedisDatabaseConf,
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
) -> dict[str, Any]:
    """Ingest documents from a path into a single Redis vector index."""
    r = _redis_binary_connection_from_conf(conf)
    key_prefix = "vec:{}:".format(index_name)
    
    # Ensure index exists with correct dimensionality
    embedding_dim = len(_openai_embed_text("dimension probe", model=embedding_model))
    _ensure_index(r, index_name, embedding_dim, key_prefix=key_prefix, force_recreate=force_recreate_index)
    
    # Optionally clear existing docs for this partition
    if override_existing and not force_recreate_index:
        _delete_existing_docs(r, key_prefix=key_prefix, partition=partition, batch_size=batch_size)
    
    # Collect and validate files
    files = list(_iter_files(input_path, glob_pattern))
    if not files:
        raise RuntimeError("No files matched under {} with glob {!r}".format(input_path, glob_pattern))
    
    # Process each file: read → chunk → embed → store
    total_chunks = 0
    pipe = r.pipeline(transaction=False)
    for file_path in files:
        chunks = _chunk_text(_read_document(file_path), chunk_chars, chunk_overlap)
        if not chunks:
            continue
        
        file_id = _sha1(str(file_path.resolve()))
        total_chunks += len(chunks)
        embeddings = _openai_embed_texts(chunks, model=embedding_model)
        
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


def _ingest_vector_docs(conf: RedisDatabaseConf, request: IngestVectorDocsRequest) -> dict[str, Any]:
    """Handle IngestVectorDocsRequest by ingesting documents into Redis vector indexes."""
    root = Path(request.input_path)

    # Auto-index mode: create one index per episode/character folder
    if request.auto_index_from_folders:
        if not root.exists() or not root.is_dir():
            raise RuntimeError("input_path must be a directory when auto_index_from_folders=True")
        
        results: list[dict[str, Any]] = []
        for episode_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
            for character_dir in sorted([p for p in episode_dir.iterdir() if p.is_dir()]):
                if not any(_iter_files(character_dir, request.glob)):
                    continue
                
                index_name = compose_index_name(
                    episode=episode_dir.name,
                    character=character_dir.name,
                    index_prefix=request.index_prefix,
                )
                results.append(_ingest_one_index(
                    conf=conf,
                    index_name=index_name,
                    partition="default",
                    input_path=character_dir,
                    glob_pattern=request.glob,
                    chunk_chars=request.chunk_chars,
                    chunk_overlap=request.chunk_overlap,
                    batch_size=request.batch_size,
                    force_recreate_index=request.force_recreate_index,
                    override_existing=request.override_existing,
                    embedding_model=request.embedding_model,
                ))
        
        if not results:
            raise RuntimeError("No documents found under episode/character folders in {}".format(root))
        return {"ok": True, "results": results}

    # Single index mode: use explicit index_name
    if not request.index_name:
        raise RuntimeError("index_name is required when auto_index_from_folders=False")

    single = _ingest_one_index(
        conf=conf,
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
    )
    return {"ok": True, "results": [single]}


# Query logic

def _query_vector_db(conf: RedisDatabaseConf, request: QueryVectorDBRequest) -> dict[str, Any]:
    """Handle QueryVectorDBRequest by searching for similar documents in Redis vector index."""
    if request.k <= 0:
        raise ValueError("k must be > 0")
    
    r = _redis_binary_connection_from_conf(conf)
    index = compose_index_name(episode=request.episode, character=request.character, index_prefix=request.index_prefix)
    
    # Embed query and prepare vector search
    query_embedding = _openai_embed_text(request.query_text, model=request.embedding_model)
    blob = _to_float32_blob(query_embedding)
    
    # Build RediSearch query with optional partition filter
    filter_base = "@partition:{{{}}}".format(request.partition) if request.partition else "*"
    query = "{}=>[KNN {} @embedding $vec AS score]".format(filter_base, request.k)
    
    # Execute vector similarity search
    res = r.execute_command(
        "FT.SEARCH", index, query,
        "PARAMS", 2, "vec", blob,
        "SORTBY", "score",
        "RETURN", 4, "score", "doc_path", "chunk_id", "content",
        "DIALECT", 2,
    )
    
    if not res:
        return {"index": index, "total": 0, "results": []}
    
    # Parse results
    total = int(res[0])
    results = []
    for i in range(1, len(res), 2):
        doc_id = _b2s(res[i])
        fields = res[i + 1]
        
        # Parse field list into dict
        parsed = {}
        if isinstance(fields, list):
            for j in range(0, len(fields), 2):
                parsed[_b2s(fields[j])] = fields[j + 1]
        
        # Extract and parse score
        score_str = _b2s(parsed.get("score", b""))
        try:
            score = float(score_str)
        except Exception:
            score = score_str
        
        results.append({
            "doc_id": doc_id,
            "score": score,
            "doc_path": _b2s(parsed.get("doc_path", b"")),
            "chunk_id": _b2s(parsed.get("chunk_id", b"")),
            "content": _b2s(parsed.get("content", b"")).strip(),
        })
    
    return {"index": index, "total": total, "results": results}


# ============================================================================
# SERVICE CONNECTOR & ENTRY POINT
# ============================================================================

class RedisDatabase(SICConnector):
    """Connector for Redis database component"""
    component_class = RedisDatabaseComponent


def main():
    SICComponentManager([RedisDatabaseComponent], name="RedisDatabase", auto_start=True)


if __name__ == "__main__":
    main()