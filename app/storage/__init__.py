"""Object storage abstraction — local filesystem or S3-compatible (MinIO/AWS)."""
from app.storage.object_store import ObjectStore, get_object_store

__all__ = ["ObjectStore", "get_object_store"]
