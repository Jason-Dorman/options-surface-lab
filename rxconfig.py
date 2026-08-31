"""Reflex project config — app_name resolves to options_surface_lab/options_surface_lab.py."""

import reflex as rx

config = rx.Config(
    app_name="options_surface_lab",
    # No sitemap needed for a single-page class project; silences the default-plugin warning
    disable_plugins=["reflex.plugins.sitemap.SitemapPlugin"],
)
