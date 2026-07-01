"""This file contains the UI Automation-based accessibility controller
implementation for Windows.
"""


import threading
import traceback

from six.moves                import queue

from dragonfly.accessibility  import base


auto = None


def _get_text_pattern2_source(text_pattern2):
    if not text_pattern2:
        return None
    if any(hasattr(text_pattern2, name) for name in (
            "DocumentRange", "GetSelection", "GetCaretRange")):
        return text_pattern2
    return getattr(text_pattern2, "pattern", text_pattern2)


class Controller(object):
    """Provides access to the UI Automation subsystem. All accesses to this
    subsystem must be run in a single thread, which is managed here."""

    class Capture(object):
        def __init__(self, closure):
            self.closure = closure
            self.done_event = threading.Event()
            self.exception = None
            self.return_value = None

    def __init__(self):
        self._closure_queue = queue.Queue(1)
        self._shutdown_event = threading.Event()
        self._ready_event = threading.Event()
        self._startup_exception = None
        self._thread = None

    def _get_context(self):
        focused = None
        try:
            focused = auto.GetFocusedControl()
        except Exception:
            traceback.print_exc()
        return Context(Accessible(focused) if focused else None)

    def _start_blocking(self):
        global auto
        initialized = False
        try:
            import uiautomation as auto
            auto.InitializeUIAutomationInCurrentThread()
            initialized = True
        except Exception as exception:
            self._startup_exception = exception
            self._ready_event.set()
            return

        self._ready_event.set()
        try:
            while not self._shutdown_event.is_set():
                try:
                    capture = self._closure_queue.get(timeout=1e-2)
                except queue.Empty:
                    continue
                try:
                    capture.return_value = capture.closure(self._get_context())
                except base.AccessibilityError as exception:
                    capture.exception = exception
                    # Checked exception, don't print.
                    pass
                except Exception as exception:
                    capture.exception = exception
                    traceback.print_exc()
                capture.done_event.set()
        finally:
            if initialized:
                try:
                    auto.UninitializeUIAutomationInCurrentThread()
                except Exception:
                    traceback.print_exc()

    def start(self):
        self._shutdown_event.clear()
        self._ready_event.clear()
        self._startup_exception = None
        self._thread = threading.Thread(target=self._start_blocking)
        self._thread.setDaemon(True)
        self._thread.start()
        self._ready_event.wait()
        if self._startup_exception:
            raise self._startup_exception

    def stop(self):
        self._shutdown_event.set()
        if self._thread:
            self._thread.join(1)

    def run_sync(self, closure):
        capture = self.Capture(closure)
        self._closure_queue.put(capture)
        capture.done_event.wait()
        if capture.exception:
            raise capture.exception
        return capture.return_value


class Context(object):
    """Provides access to the current UIA context, such as focused objects."""

    def __init__(self, focused=None):
        self.focused = focused


class Accessible(object):
    """Wraps a UI Automation control."""

    def __init__(self, control):
        self._control = control

    def _iter_controls(self):
        control = self._control
        while control:
            yield control
            try:
                control = control.GetParentControl()
            except Exception:
                break

    def _get_pattern(self, control, getter_name, pattern_id):
        try:
            getter = getattr(control, getter_name, None)
            if getter:
                pattern = getter()
                if pattern:
                    return pattern
        except Exception:
            pass
        try:
            return control.GetPattern(pattern_id)
        except Exception:
            return None

    def _find_text_provider(self):
        for control in self._iter_controls():
            text_pattern = self._get_pattern(control, "GetTextPattern",
                                             auto.PatternId.TextPattern)
            text_pattern2 = self._get_pattern(control, "GetTextPattern2",
                                              auto.PatternId.TextPattern2)
            value_pattern = self._get_pattern(control, "GetValuePattern",
                                              auto.PatternId.ValuePattern)
            if text_pattern or text_pattern2:
                return control, text_pattern, text_pattern2, value_pattern
            if value_pattern:
                return control, None, None, value_pattern

        return None

    def _get_text_read_only(self, control, text_pattern, text_pattern2,
                            value_pattern):
        if value_pattern:
            try:
                return value_pattern.IsReadOnly
            except Exception:
                pass

        document_range = None
        if text_pattern:
            try:
                document_range = text_pattern.DocumentRange
            except Exception:
                pass
        elif text_pattern2:
            try:
                source = _get_text_pattern2_source(text_pattern2)
                document_range = getattr(source, "DocumentRange", None)
                if document_range and not hasattr(document_range,
                                                 "GetAttributeValue"):
                    document_range = auto.TextRange(textRange=document_range)
            except Exception:
                pass

        if document_range:
            try:
                value = document_range.GetAttributeValue(
                    auto.TextAttributeId.IsReadOnlyAttribute)
                if isinstance(value, bool):
                    return value
            except Exception:
                pass

        get_property_value_ex = getattr(control, "GetPropertyValueEx", None)
        if get_property_value_ex:
            try:
                value = get_property_value_ex(
                    auto.PropertyId.ValueIsReadOnlyProperty, True)
                if isinstance(value, bool):
                    return value
            except Exception:
                pass

        return None

    def as_text(self):
        provider = self._find_text_provider()
        if not provider:
            return None
        _, text_pattern, text_pattern2, value_pattern = provider
        return AccessibleTextNode(text_pattern, text_pattern2, value_pattern)

    def is_editable(self):
        provider = self._find_text_provider()
        if not provider:
            return False
        control, text_pattern, text_pattern2, value_pattern = provider
        read_only = self._get_text_read_only(control,
                                             text_pattern,
                                             text_pattern2,
                                             value_pattern)
        if read_only is not None:
            return not read_only
        return False


class BoundingBox(object):
    """Represents a bounding box in screen coordinates."""

    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __str__(self):
        return "x=%s, y=%s, width=%s, height=%s" % (
            self.x, self.y, self.width, self.height)


class AccessibleTextNode(object):
    """Provides a wrapper around a UIA text snapshot. Mutable methods will affect
    the underlying UIA element, but the changes will not be reflected here."""

    def __init__(self, text_pattern=None, text_pattern2=None,
                 value_pattern=None):
        self.is_leaf = True
        self._text_pattern = text_pattern
        self._text_pattern2 = text_pattern2
        self._value_pattern = value_pattern
        self.expanded_text = self._get_expanded_text()
        self.cursor = self._get_cursor()

    def _invalid_box(self):
        return BoundingBox(-1, -1, 0, 0)

    def _get_document_range(self):
        if self._text_pattern:
            try:
                return self._text_pattern.DocumentRange
            except Exception:
                return None
        if not self._text_pattern2:
            return None
        try:
            source = _get_text_pattern2_source(self._text_pattern2)
            return self._coerce_text_range(getattr(source, "DocumentRange", None))
        except Exception:
            return None

    def _get_expanded_text(self):
        document_range = self._get_document_range()
        if document_range:
            text = document_range.GetText(-1)
            return text if text is not None else ""
        if self._value_pattern:
            text = self._value_pattern.Value
            return text if text is not None else ""
        return ""

    def _coerce_text_range(self, raw_range):
        if not raw_range:
            return None
        if hasattr(raw_range, "textRange"):
            return raw_range
        if not all(hasattr(raw_range, name) for name in (
                "Clone", "GetText", "MoveEndpointByRange")):
            return None
        try:
            return auto.TextRange(textRange=raw_range)
        except Exception:
            return None

    def _compare_range_endpoints_with_self(self, text_range):
        raw_range = getattr(text_range, "textRange", None)
        if raw_range and hasattr(raw_range, "CompareEndpoints"):
            return raw_range.CompareEndpoints(
                auto.TextPatternRangeEndpoint.Start,
                raw_range,
            auto.TextPatternRangeEndpoint.End)
        return text_range.CompareEndpoints(
            auto.TextPatternRangeEndpoint.Start,
            text_range,
            auto.TextPatternRangeEndpoint.End)

    def _get_selection_ranges(self):
        if self._text_pattern:
            try:
                return self._text_pattern.GetSelection()
            except Exception:
                return []

        if not self._text_pattern2:
            return []

        try:
            source = _get_text_pattern2_source(self._text_pattern2)
            getter = getattr(source, "GetSelection", None)
            if not getter:
                return []
            selections = getter()
        except Exception:
            return []

        if not selections:
            return []
        if isinstance(selections, list):
            ranges = []
            for selection in selections:
                if hasattr(selection, "CompareEndpoints"):
                    ranges.append(selection)
                    continue
                text_range = self._coerce_text_range(selection)
                if text_range:
                    ranges.append(text_range)
            return ranges

        ranges = []
        try:
            length = selections.Length
        except Exception:
            return ranges
        for index in range(length):
            try:
                selection = selections.GetElement(index)
            except Exception:
                continue
            text_range = self._coerce_text_range(selection)
            if text_range:
                ranges.append(text_range)
        return ranges

    def _get_caret_range(self):
        if not self._text_pattern2:
            return None
        try:
            source = _get_text_pattern2_source(self._text_pattern2)
            getter = getattr(source, "GetCaretRange", None)
            if not getter:
                return None
            result = getter()
        except Exception:
            return None

        if isinstance(result, tuple):
            active = None
            items = []
            for item in result:
                if isinstance(item, bool):
                    active = item
                    continue
                items.append(item)
            if active is False:
                return None
            for item in items if active is not None else result:
                text_range = self._coerce_text_range(item)
                if text_range:
                    return text_range
            return None
        return self._coerce_text_range(result)

    def _offset_from_range_start(self, text_range):
        document_range = self._get_document_range()
        if not document_range or not text_range:
            return None
        prefix = document_range.Clone()
        prefix.MoveEndpointByRange(auto.TextPatternRangeEndpoint.End,
                                   text_range,
                                   auto.TextPatternRangeEndpoint.Start)
        text = prefix.GetText(-1)
        if text is None:
            return None
        return len(text)

    def _get_cursor_from_selection(self):
        if not self._get_document_range():
            return None
        selections = self._get_selection_ranges()
        if len(selections) != 1:
            return None
        selection = selections[0]
        if self._compare_range_endpoints_with_self(selection) != 0:
            return None
        return self._offset_from_range_start(selection)

    def _get_cursor(self):
        if not self._get_document_range():
            return None
        caret_range = self._get_caret_range()
        if caret_range:
            return self._offset_from_range_start(caret_range)
        return self._get_cursor_from_selection()

    def _get_range_at_offset(self, offset):
        document_range = self._get_document_range()
        if not document_range:
            return None
        offset = max(0, min(offset, len(self.expanded_text)))
        text_range = document_range.Clone()
        text_range.MoveEndpointByRange(auto.TextPatternRangeEndpoint.End,
                                       text_range,
                                       auto.TextPatternRangeEndpoint.Start)
        if offset:
            text_range.Move(auto.TextUnit.Character, offset)
        return text_range

    def set_cursor(self, offset):
        """Sets the cursor to the given offset. Note that the update will not be
        reflected in self.cursor."""

        text_range = self._get_range_at_offset(offset)
        if not text_range:
            raise base.UnsupportedSelectionError()
        if not text_range.Select():
            raise base.UnsupportedSelectionError()

    def get_bounding_box(self, offset):
        text_range = self._get_range_at_offset(offset)
        if not text_range:
            return self._invalid_box()
        if offset < len(self.expanded_text):
            text_range.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.End,
                                          auto.TextUnit.Character,
                                          1)
        rects = text_range.GetBoundingRectangles()
        if not rects:
            return self._invalid_box()
        rect = rects[0]
        return BoundingBox(rect.left, rect.top, rect.width(), rect.height())

    def select_range(self, start, end):
        text_range = self._get_range_at_offset(start)
        if not text_range:
            raise base.UnsupportedSelectionError()
        if end < start:
            start, end = end, start
            text_range = self._get_range_at_offset(start)
        text_range.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.End,
                                      auto.TextUnit.Character,
                                      end - start)
        if not text_range.Select():
            raise base.UnsupportedSelectionError()
