"""
This module initializes the accessibility controller for the current
platform.
"""

import contextlib
import os
import sys
import warnings

from . import controller

from .utils import (CursorPosition, TextQuery)


def _get_windows_controller_class():
    backend_name = os.environ.get(
        "DRAGONFLY_WINDOWS_ACCESSIBILITY_BACKEND", "uia").strip().lower()

    if backend_name in ("", "uia"):
        from . import uia
        return uia.Controller

    if backend_name == "ia2":
        warnings.warn("The Windows IA2 accessibility backend is deprecated. "
                      "Set DRAGONFLY_WINDOWS_ACCESSIBILITY_BACKEND=uia or "
                      "remove the override to use the supported UIA backend.",
                      DeprecationWarning)
        from . import ia2
        return ia2.Controller

    raise ValueError("Unknown Windows accessibility backend: %r" %
                     backend_name)


def _get_os_controller_class():
    # Note: dragonfly._platform_checks is not used here in an effort to keep
    # the accessibility sub-package modular. Please see the module docstring
    # of utils.py.
    if ":" in os.environ.get("DISPLAY", ""):
        # Use the AT-SPI controller on X11.
        from . import atspi
        return atspi.Controller

    if sys.platform.startswith("win"):
        # Use the UI Automation controller on Windows by default.
        return _get_windows_controller_class()

    return None


os_controller_class = _get_os_controller_class()

controller_instance = None

def get_accessibility_controller():
    """Get the OS-independent accessibility controller which is the gateway to all
    accessibility functionality. Returns None if OS is not supported."""

    global controller_instance
    if os_controller_class and (not controller_instance or controller_instance.stopped):
        os_controller = os_controller_class()
        controller_instance = controller.AccessibilityController(os_controller)
    return controller_instance

@contextlib.contextmanager
def get_stopping_accessibility_controller():
    """Same as :func:`get_accessibility_controller`, but automatically stops when
    used in a `with` context."""

    yield get_accessibility_controller()
    if controller_instance:
        controller_instance.stop()
