from typing import Any, Literal, NotRequired, TypedDict
import abc
import asyncio
from dataclasses import dataclass


FileOperationError = Literal[
    "file_not_found",  # Download: file doesn't exist
    "permission_denied",  # Both: access denied
    "is_directory",  # Download: tried to download directory as file
    "invalid_path",  # Both: path syntax malformed (parent dir missing, invalid chars)
]

"""文件上传/下载操作的标准化错误码。

错误码涵盖常见且可恢复的错误，LLM 能够理解并尝试修复：
- file_not_found: 请求的文件不存在（下载时）
- parent_not_found: 父目录不存在（上传时）
- permission_denied: 操作权限被拒绝
- is_directory: 尝试将目录作为文件下载
- invalid_path: 路径格式非法或包含非法字符
"""

class FileInfo(TypedDict):
    """Structured file listing info.

    Minimal contract used across backends. Only "path" is required.
    Other fields are best-effort and may be absent depending on backend.
    """

    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]  # bytes (approx)
    modified_at: NotRequired[str]  # ISO timestamp if known

class GrepMatch(TypedDict):
    """Structured grep match entry."""

    path: str
    line: int
    text: str

@dataclass
class FileDownloadResponse:
    """Result of a single file download operation.

    The response is designed to allow partial success in batch operations.
    The errors are standardized using FileOperationError literals
    for certain recoverable conditions for use cases that involve
    LLMs performing file operations.

    Attributes:
        path: The file path that was requested. Included for easy correlation
            when processing batch results, especially useful for error messages.
        content: File contents as bytes on success, None on failure.
        error: Standardized error code on failure, None on success.
            Uses FileOperationError literal for structured, LLM-actionable error reporting.

    Examples:
        >>> # Success
        >>> FileDownloadResponse(path="/app/config.json", content=b"{...}", error=None)
        >>> # Failure
        >>> FileDownloadResponse(path="/wrong/path.txt", content=None, error="file_not_found")
    """

    path: str
    content: bytes | None = None
    error: FileOperationError | None = None


@dataclass
class FileUploadResponse:
    """Result of a single file upload operation.

    The response is designed to allow partial success in batch operations.
    The errors are standardized using FileOperationError literals
    for certain recoverable conditions for use cases that involve
    LLMs performing file operations.

    Attributes:
        path: The file path that was requested. Included for easy correlation
            when processing batch results and for clear error messages.
        error: Standardized error code on failure, None on success.
            Uses FileOperationError literal for structured, LLM-actionable error reporting.

    Examples:
        >>> # Success
        >>> FileUploadResponse(path="/app/data.txt", error=None)
        >>> # Failure
        >>> FileUploadResponse(path="/readonly/file.txt", error="permission_denied")
    """

    path: str
    error: FileOperationError | None = None

@dataclass
class WriteResult:
    """Result from backend write operations.

    Attributes:
        error: Error message on failure, None on success.
        path: Absolute path of written file, None on failure.
        files_update: State update dict for checkpoint backends, None for external storage.
            Checkpoint backends populate this with {file_path: file_data} for LangGraph state.
            External backends set None (already persisted to disk/S3/database/etc).

    Examples:
        >>> # Checkpoint storage
        >>> WriteResult(path="/f.txt", files_update={"/f.txt": {...}})
        >>> # External storage
        >>> WriteResult(path="/f.txt", files_update=None)
        >>> # Error
        >>> WriteResult(error="File exists")
    """

    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None

@dataclass
class EditResult:
    """Result from backend edit operations.

    Attributes:
        error: Error message on failure, None on success.
        path: Absolute path of edited file, None on failure.
        files_update: State update dict for checkpoint backends, None for external storage.
            Checkpoint backends populate this with {file_path: file_data} for LangGraph state.
            External backends set None (already persisted to disk/S3/database/etc).
        occurrences: Number of replacements made, None on failure.

    Examples:
        >>> # Checkpoint storage
        >>> EditResult(path="/f.txt", files_update={"/f.txt": {...}}, occurrences=1)
        >>> # External storage
        >>> EditResult(path="/f.txt", files_update=None, occurrences=2)
        >>> # Error
        >>> EditResult(error="File not found")
    """

    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None

class BackendProtocol(abc.ABC):  # noqa: B024
    """Protocol for pluggable memory backends (single, unified).

    Backends can store files in different locations (state, filesystem, database, etc.)
    and provide a uniform interface for file operations.

    All file data is represented as dicts with the following structure:
    {
        "content": list[str], # Lines of text content
        "created_at": str, # ISO format timestamp
        "modified_at": str, # ISO format timestamp
    }
    """

    def ls_info(self, path: str) -> list["FileInfo"]:
        """List all files in a directory with metadata.

        Args:
            path: Absolute path to the directory to list. Must start with '/'.

        Returns:
            List of FileInfo dicts containing file metadata:

            - `path` (required): Absolute file path
            - `is_dir` (optional): True if directory
            - `size` (optional): File size in bytes
            - `modified_at` (optional): ISO 8601 timestamp
        """
        raise NotImplementedError

    async def als_info(self, path: str) -> list["FileInfo"]:
        """Async version of ls_info."""
        return await asyncio.to_thread(self.ls_info, path)

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers.

        Args:
            file_path: Absolute path to the file to read. Must start with '/'.
            offset: Line number to start reading from (0-indexed). Default: 0.
            limit: Maximum number of lines to read. Default: 2000.

        Returns:
            String containing file content formatted with line numbers (cat -n format),
            starting at line 1. Lines longer than 2000 characters are truncated.

            Returns an error string if the file doesn't exist or can't be read.

        !!! note
            - Use pagination (offset/limit) for large files to avoid context overflow
            - First scan: `read(path, limit=100)` to see file structure
            - Read more: `read(path, offset=100, limit=200)` for next section
            - ALWAYS read a file before editing it
            - If file exists but is empty, you'll receive a system reminder warning
        """
        raise NotImplementedError

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Async version of read."""
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list["GrepMatch"] | str:
        """Search for a literal text pattern in files.

        Args:
            pattern: Literal string to search for (NOT regex).
                     Performs exact substring matching within file content.
                     Example: "TODO" matches any line containing "TODO"

            path: Optional directory path to search in.
                  If None, searches in current working directory.
                  Example: "/workspace/src"

            glob: Optional glob pattern to filter which FILES to search.
                  Filters by filename/path, not content.
                  Supports standard glob wildcards:
                  - `*` matches any characters in filename
                  - `**` matches any directories recursively
                  - `?` matches single character
                  - `[abc]` matches one character from set

        Examples:
                  - "*.py" - only search Python files
                  - "**/*.txt" - search all .txt files recursively
                  - "src/**/*.js" - search JS files under src/
                  - "test[0-9].txt" - search test0.txt, test1.txt, etc.

        Returns:
            On success: list[GrepMatch] with structured results containing:
                - path: Absolute file path
                - line: Line number (1-indexed)
                - text: Full line content containing the match

            On error: str with error message (e.g., invalid path, permission denied)
        """
        raise NotImplementedError

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list["GrepMatch"] | str:
        """Async version of grep_raw."""
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list["FileInfo"]:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern with wildcards to match file paths.
                     Supports standard glob syntax:
                     - `*` matches any characters within a filename/directory
                     - `**` matches any directories recursively
                     - `?` matches a single character
                     - `[abc]` matches one character from set

            path: Base directory to search from. Default: "/" (root).
                  The pattern is applied relative to this path.

        Returns:
            list of FileInfo
        """
        raise NotImplementedError

    async def aglob_info(self, pattern: str, path: str = "/") -> list["FileInfo"]:
        """Async version of glob_info."""
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Write content to a new file in the filesystem, error if file exists.

        Args:
            file_path: Absolute path where the file should be created.
                       Must start with '/'.
            content: String content to write to the file.

        Returns:
            WriteResult
        """
        raise NotImplementedError

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Async version of write."""
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        """Perform exact string replacements in an existing file.

        Args:
            file_path: Absolute path to the file to edit. Must start with '/'.
            old_string: Exact string to search for and replace.
                       Must match exactly including whitespace and indentation.
            new_string: String to replace old_string with.
                       Must be different from old_string.
            replace_all: If True, replace all occurrences. If False (default),
                        old_string must be unique in the file or the edit fails.

        Returns:
            EditResult
        """
        raise NotImplementedError

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        """Async version of edit."""
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to the sandbox.

        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.

        Args:
            files: List of (path, content) tuples to upload.

        Returns:
            List of FileUploadResponse objects, one per input file.
            Response order matches input order (response[i] for files[i]).
            Check the error field to determine success/failure per file.

        Examples:
            ```python
            responses = sandbox.upload_files(
                [
                    ("/app/config.json", b"{...}"),
                    ("/app/data.txt", b"content"),
                ]
            )
            ```
        """
        raise NotImplementedError

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Async version of upload_files."""
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from the sandbox.

        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.

        Args:
            paths: List of file paths to download.

        Returns:
            List of FileDownloadResponse objects, one per input path.
            Response order matches input order (response[i] for paths[i]).
            Check the error field to determine success/failure per file.
        """
        raise NotImplementedError

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Async version of download_files."""
        return await asyncio.to_thread(self.download_files, paths)


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================
# Behavioral guidance is baked into the description so it's part of the
# static tool schema (cached, never changes mid-conversation).
#
# Paths use virtual absolute form (must start with '/'). Maps to BackendProtocol.

LS_INFO_SCHEMA = {
    "name": "list_directory",
    "description": (
        "List files and subdirectories in a directory with metadata. "
        "Use this instead of ls/find in terminal when working through the file backend. "
        "Returns paths plus optional size, is_dir, and modified_at. "
        "Paths must be absolute and start with '/' (e.g. '/src', '/'). "
        "For recursive or pattern-based discovery, use glob_files instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute directory path to list. Must start with '/'.",
            },
        },
        "required": ["path"],
    },
}

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": (
        "Read a text file with line numbers and pagination. "
        "Use this instead of cat/head/tail in terminal. "
        "Output format: 'LINE_NUM|CONTENT' (line numbers start at 1 in the display). "
        "Paths must be absolute and start with '/'. "
        "Use offset and limit for large files — default limit is 2000 lines; "
        "lines longer than 2000 characters are truncated. "
        "ALWAYS read a file before editing it. "
        "First scan: limit=100 to see structure; then read more with offset. "
        "offset is 0-indexed (0 = first line). "
        "Returns an error string if the file is missing or unreadable. "
        "NOTE: Text only — cannot read images or binary; use download_files for raw bytes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file. Must start with '/'.",
            },
            "offset": {
                "type": "integer",
                "description": "Line index to start reading from (0-indexed, default: 0).",
                "default": 0,
                "minimum": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: 2000).",
                "default": 2000,
                "maximum": 2000,
            },
        },
        "required": ["file_path"],
    },
}

GREP_FILES_SCHEMA = {
    "name": "grep_files",
    "description": (
        "Search for a literal text substring inside files (NOT regex). "
        "Use this instead of grep when you need exact substring matches, e.g. 'TODO' or a function name. "
        "Optional path limits the search to a directory; optional file_glob filters by filename "
        "(e.g. '*.py', '**/*.ts'). "
        "Returns structured matches: path, line (1-indexed), and full line text. "
        "On failure returns a plain error string (invalid path, permission denied). "
        "For regex content search or ripgrep-style features, prefer a dedicated search_files tool if available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Literal substring to find in file contents (exact match, not regex).",
            },
            "path": {
                "type": "string",
                "description": (
                    "Optional absolute directory to search under. "
                    "Omit to search from the backend default root."
                ),
            },
            "file_glob": {
                "type": "string",
                "description": (
                    "Optional glob to filter which files are searched "
                    "(e.g. '*.py', '**/*.txt', 'src/**/*.js')."
                ),
            },
        },
        "required": ["pattern"],
    },
}

GLOB_FILES_SCHEMA = {
    "name": "glob_files",
    "description": (
        "Find files by glob pattern under a base directory. "
        "Use this instead of find/ls for pattern-based file discovery. "
        "Supports *, **, ?, and [abc] wildcards. "
        "Examples: '*.py', '**/*.md', 'src/**/*.ts'. "
        "Returns FileInfo entries (path required; size, is_dir, modified_at when available). "
        "Base path defaults to '/'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern relative to path (e.g. '**/*.py').",
            },
            "path": {
                "type": "string",
                "description": "Absolute base directory for the search. Default: '/'.",
                "default": "/",
            },
        },
        "required": ["pattern"],
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": (
        "Create a NEW text file with the given content. "
        "Fails if the file already exists — use edit_file to modify existing files. "
        "Paths must be absolute and start with '/'. "
        "Parent directories are created when the backend supports it. "
        "Do not use for partial updates; use edit_file for targeted replacements."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path for the new file. Must start with '/'.",
            },
            "content": {
                "type": "string",
                "description": "Full text content to write.",
            },
        },
        "required": ["file_path", "content"],
    },
}

EDIT_FILE_SCHEMA = {
    "name": "edit_file",
    "description": (
        "Perform exact find-and-replace edits in an EXISTING file. "
        "Use this instead of sed/awk for targeted changes. "
        "old_string must match exactly, including whitespace and indentation. "
        "new_string must differ from old_string (use '' to delete matched text). "
        "By default old_string must be unique in the file or the edit fails; "
        "set replace_all=true to replace every occurrence. "
        "ALWAYS read_file before editing so you have current content. "
        "Include surrounding context lines in old_string when uniqueness is unclear."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file. Must start with '/'.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to find. Must be unique unless replace_all=true.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text. Empty string deletes the match.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default: false).",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    },
}

UPLOAD_FILES_SCHEMA = {
    "name": "upload_files",
    "description": (
        "Upload one or more files to the backend in a single batch. "
        "Each item is written atomically per path; check per-file error codes in the response. "
        "Paths must be absolute and start with '/'. "
        "Use content_encoding='base64' for binary payloads. "
        "Standardized errors: permission_denied, invalid_path (and parent missing where applicable)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "Files to upload, in order. Response order matches input order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute destination path. Must start with '/'.",
                        },
                        "content": {
                            "type": "string",
                            "description": "File body as UTF-8 text or base64 when content_encoding is base64.",
                        },
                        "content_encoding": {
                            "type": "string",
                            "enum": ["utf8", "base64"],
                            "description": "How to decode content before writing (default: utf8).",
                            "default": "utf8",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
        "required": ["files"],
    },
}

DOWNLOAD_FILES_SCHEMA = {
    "name": "download_files",
    "description": (
        "Download one or more files from the backend in a single batch. "
        "Returns raw bytes per path on success; standardized error codes on failure: "
        "file_not_found, permission_denied, is_directory, invalid_path. "
        "Response order matches input paths. "
        "Use for binary assets or when read_file text formatting is not appropriate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute file paths to download. Must start with '/'. Directories are not supported.",
            },
        },
        "required": ["paths"],
    },
}

BACKEND_FILE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    LS_INFO_SCHEMA,
    READ_FILE_SCHEMA,
    GREP_FILES_SCHEMA,
    GLOB_FILES_SCHEMA,
    WRITE_FILE_SCHEMA,
    EDIT_FILE_SCHEMA,
    UPLOAD_FILES_SCHEMA,
    DOWNLOAD_FILES_SCHEMA,
]

