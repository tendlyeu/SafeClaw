"""Shared constants used across SafeClaw modules."""

# Common parameter key names that may contain file/resource paths.
# Used by the engine, policy checker, and preference checker when
# extracting resource paths from tool-call parameters.
PATH_PARAM_KEYS = (
    "file_path",
    "path",
    "filepath",
    "filename",
    "dest",
    "destination",
    "target",
    "source",
    "src",
    "dir",
    "directory",
    "folder",
)
