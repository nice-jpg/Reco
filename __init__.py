"""Build and reconcile Android XML region trees."""
from .model_interface import PageSession


def build_tree(xml: str):
    """Build a page session from XML content, not a file path."""
    return PageSession.build_tree(xml)


def sync(old, new):
    return old.sync(new)


__all__ = ["PageSession", "build_tree", "sync"]
