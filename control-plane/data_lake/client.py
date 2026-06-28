import os
from contextlib import contextmanager
from typing import Any, Iterator
import hdfs

class DataLakeClient:
    """Client for Data Lake operations on HDFS."""

    def __init__(self, url: str | None = None, user: str | None = None):
        self.url = url or os.environ.get("HDFS_URL", "http://localhost:9870")
        self.user = user or os.environ.get("HDFS_USER", "root")
        self._client = hdfs.InsecureClient(self.url, user=self.user)

    def write_file(self, hdfs_path: str, data: bytes, overwrite: bool = True) -> None:
        """Write a file to the data lake."""
        self._client.write(hdfs_path, data, overwrite=overwrite)

    def read_file(self, hdfs_path: str) -> bytes:
        """Read a file from the data lake."""
        with self._client.read(hdfs_path) as reader:
            return reader.read()

    def list_dir(self, hdfs_path: str) -> list[str]:
        """List contents of a directory."""
        return self._client.list(hdfs_path)

    def delete(self, hdfs_path: str, recursive: bool = False) -> bool:
        """Delete a file or directory."""
        return self._client.delete(hdfs_path, recursive=recursive)

    def status(self, hdfs_path: str) -> dict[str, Any] | None:
        """Get file status."""
        return self._client.status(hdfs_path, strict=False)
