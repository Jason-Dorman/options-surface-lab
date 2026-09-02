"""Reflex project config — app_name resolves to options_surface_lab/options_surface_lab.py.

No `frontend_path`: the published site is a static page built by build_preview.py, not a
Reflex export, so there is no Pages subpath to compensate for (AD-4, 2026-08-31).
"""

import reflex as rx

config = rx.Config(
    app_name="options_surface_lab",
    # No sitemap needed for a single-page class project; silences the default-plugin warning
    disable_plugins=["reflex.plugins.sitemap.SitemapPlugin"],
)
