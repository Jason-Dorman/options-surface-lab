"""Reflex entry point (AD-8): resolves rxconfig's app_name to the real app module.

Keep this logic-free — the app lives in options_surface_app.py (the rubric's *app.py).
"""

from options_surface_lab.options_surface_app import app

__all__ = ["app"]
