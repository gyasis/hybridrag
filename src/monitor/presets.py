"""
Pattern Presets for HybridRAG Monitor
=====================================

Predefined include/exclude patterns for common use cases.
These help users quickly configure new databases without
manually specifying file patterns.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class PatternPreset:
    """A preset pattern configuration."""
    name: str
    display_name: str
    description: str
    include_patterns: List[str]
    exclude_patterns: List[str]
    file_extensions: List[str]
    source_type: str = "filesystem"


# Built-in presets
PRESETS: Dict[str, PatternPreset] = {
    "specstory": PatternPreset(
        name="specstory",
        display_name="SpecStory",
        description="Claude Code SpecStory AI conversation files",
        include_patterns=[
            "**/.specstory/**/*.md",
            "**/.specstory/**/*.json",
        ],
        exclude_patterns=[
            ".git/**",
            "node_modules/**",
        ],
        file_extensions=[".md", ".json"],
        source_type="specstory"
    ),

    "documentation": PatternPreset(
        name="documentation",
        display_name="Documentation",
        description="Markdown docs, README files, RST documentation",
        include_patterns=[
            "**/*.md",
            "**/*.rst",
            "**/*.txt",
            "docs/**",
            "README*",
            "CHANGELOG*",
        ],
        exclude_patterns=[
            "node_modules/**",
            ".git/**",
            ".venv/**",
            "__pycache__/**",
            "*.pyc",
            "dist/**",
            "build/**",
        ],
        file_extensions=[".md", ".rst", ".txt"],
        source_type="filesystem"
    ),

    "code-python": PatternPreset(
        name="code-python",
        display_name="Python Code",
        description="Python source files and notebooks",
        include_patterns=[
            "**/*.py",
            "**/*.pyi",
            "**/*.ipynb",
        ],
        exclude_patterns=[
            "**/__pycache__/**",
            "**/.venv/**",
            "**/venv/**",
            "**/.tox/**",
            "**/.pytest_cache/**",
            "**/*.pyc",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
            "**/*.egg-info/**",
            "**/test*/**",  # Optional - may want tests
        ],
        file_extensions=[".py", ".pyi", ".ipynb"],
        source_type="filesystem"
    ),

    "code-javascript": PatternPreset(
        name="code-javascript",
        display_name="JavaScript/TypeScript",
        description="JS, TS, JSX, TSX source files",
        include_patterns=[
            "**/*.js",
            "**/*.jsx",
            "**/*.ts",
            "**/*.tsx",
            "**/*.mjs",
            "**/*.cjs",
        ],
        exclude_patterns=[
            "**/node_modules/**",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
            "**/.next/**",
            "**/coverage/**",
            "**/*.min.js",
            "**/*.bundle.js",
        ],
        file_extensions=[".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
        source_type="filesystem"
    ),

    "code-mixed": PatternPreset(
        name="code-mixed",
        display_name="Mixed Code",
        description="Common programming languages",
        include_patterns=[
            "**/*.py",
            "**/*.js",
            "**/*.ts",
            "**/*.go",
            "**/*.rs",
            "**/*.java",
            "**/*.c",
            "**/*.cpp",
            "**/*.h",
            "**/*.hpp",
            "**/*.cs",
            "**/*.rb",
            "**/*.php",
        ],
        exclude_patterns=[
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/.git/**",
            "**/.venv/**",
            "**/venv/**",
            "**/target/**",
            "**/dist/**",
            "**/build/**",
            "**/vendor/**",
        ],
        file_extensions=[".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php"],
        source_type="filesystem"
    ),

    "all-markdown": PatternPreset(
        name="all-markdown",
        display_name="All Markdown",
        description="All markdown files recursively",
        include_patterns=[
            "**/*.md",
        ],
        exclude_patterns=[
            "**/node_modules/**",
            "**/.git/**",
            "**/.venv/**",
        ],
        file_extensions=[".md"],
        source_type="filesystem"
    ),

    "config-files": PatternPreset(
        name="config-files",
        display_name="Config Files",
        description="Configuration files (YAML, JSON, TOML, INI)",
        include_patterns=[
            "**/*.yaml",
            "**/*.yml",
            "**/*.json",
            "**/*.toml",
            "**/*.ini",
            "**/*.cfg",
            "**/*.conf",
            "**/.*rc",
        ],
        exclude_patterns=[
            "**/node_modules/**",
            "**/.git/**",
            "**/package-lock.json",
            "**/yarn.lock",
            "**/poetry.lock",
        ],
        file_extensions=[".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf"],
        source_type="filesystem"
    ),

    "sql-files": PatternPreset(
        name="sql-files",
        display_name="SQL Files",
        description="SQL and database migration files",
        include_patterns=[
            "**/*.sql",
            "**/migrations/**/*.py",
            "**/migrations/**/*.sql",
        ],
        exclude_patterns=[
            "**/.git/**",
            "**/node_modules/**",
        ],
        file_extensions=[".sql"],
        source_type="filesystem"
    ),

    "custom": PatternPreset(
        name="custom",
        display_name="Custom",
        description="User-defined patterns",
        include_patterns=[],
        exclude_patterns=[
            ".git/**",
        ],
        file_extensions=[],
        source_type="filesystem"
    ),
}


def get_preset(name: str) -> Optional[PatternPreset]:
    """Get a preset by name."""
    return PRESETS.get(name.lower())


def list_presets() -> List[PatternPreset]:
    """List all available presets."""
    return list(PRESETS.values())


def get_preset_names() -> List[str]:
    """Get list of preset names."""
    return list(PRESETS.keys())


def create_custom_preset(
    name: str,
    include_patterns: List[str],
    exclude_patterns: Optional[List[str]] = None,
    file_extensions: Optional[List[str]] = None,
    description: Optional[str] = None
) -> PatternPreset:
    """Create a custom preset."""
    return PatternPreset(
        name=name,
        display_name=name.title().replace("-", " ").replace("_", " "),
        description=description or f"Custom preset: {name}",
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns or [".git/**"],
        file_extensions=file_extensions or [],
        source_type="filesystem"
    )


def validate_pattern(pattern: str) -> bool:
    """
    Validate a glob pattern.

    Returns True if the pattern appears valid.
    """
    # Basic validation - check for common issues
    if not pattern or pattern.isspace():
        return False

    # Check for balanced brackets
    if pattern.count('[') != pattern.count(']'):
        return False

    if pattern.count('{') != pattern.count('}'):
        return False

    return True


def validate_patterns(patterns: List[str]) -> List[str]:
    """
    Validate a list of patterns.

    Returns list of invalid patterns, empty if all valid.
    """
    invalid = []
    for pattern in patterns:
        if not validate_pattern(pattern):
            invalid.append(pattern)
    return invalid


# Pattern templates for common scenarios
PATTERN_TEMPLATES = {
    "all_files_extension": "**/*.{ext}",
    "specific_folder": "{folder}/**",
    "files_in_folder": "{folder}/*.{ext}",
    "hidden_folders": "**/.*/**",
    "specific_file": "**/{filename}",
}


def expand_template(template_name: str, **kwargs) -> str:
    """Expand a pattern template with provided values."""
    template = PATTERN_TEMPLATES.get(template_name, "")
    return template.format(**kwargs)
