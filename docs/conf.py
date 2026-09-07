from importlib.metadata import version as package_version

project = "SnapshotFS"
author = "SnapshotFS contributors"
release = package_version("snapshotfs")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

exclude_patterns = ["_build"]
html_theme = "furo"
html_title = f"SnapshotFS {release}"

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "signature"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
