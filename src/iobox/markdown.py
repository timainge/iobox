"""
Markdown Conversion Module.

Re-exports from markdown_converter.py and utils.py for backward compatibility.
"""

from iobox.markdown_converter import (
    generate_yaml_frontmatter,
    convert_html_to_markdown,
    _clean_email_markdown,
    convert_email_to_markdown,
    strip_html_tags,
)

from iobox.utils import (
    create_markdown_filename,
    slugify_text,
)
