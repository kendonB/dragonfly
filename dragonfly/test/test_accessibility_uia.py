import importlib
import sys
import warnings

import pytest

import dragonfly.accessibility as accessibility
from dragonfly.accessibility import base
from dragonfly.accessibility import utils
from dragonfly.accessibility import uia


class _FakePatternIds(object):
    TextPattern = 1
    TextPattern2 = 2
    ValuePattern = 3


class _FakePropertyIds(object):
    ValueIsReadOnlyProperty = 10
    RangeValueIsReadOnlyProperty = 11


class _FakeTextAttributeIds(object):
    IsReadOnlyAttribute = 20


class _FakeTextPatternRangeEndpoint(object):
    Start = 0
    End = 1


class _FakeAuto(object):
    PatternId = _FakePatternIds
    PropertyId = _FakePropertyIds
    TextAttributeId = _FakeTextAttributeIds
    TextPatternRangeEndpoint = _FakeTextPatternRangeEndpoint

    @staticmethod
    def TextRange(textRange=None):
        if isinstance(textRange, _FakeRawCaretRange):
            return _FakeWrappedTextRange(textRange)
        if isinstance(textRange, _FakeTextRange):
            return textRange
        raise TypeError("not a text range")

class _FakeTextRange(object):
    def __init__(self, text, read_only, select_result=True):
        self._text = text
        self._read_only = read_only
        self._select_result = select_result
        self._end_text = text

    def Clone(self):
        clone = _FakeTextRange(self._text,
                               self._read_only,
                               select_result=self._select_result)
        clone._end_text = self._end_text
        return clone

    def GetText(self, max_length):
        return self._end_text

    def MoveEndpointByRange(self, src_endpoint, text_range, target_endpoint):
        if hasattr(text_range, "_prefix_text"):
            self._end_text = text_range._prefix_text
            return
        if hasattr(text_range, "textRange") and hasattr(text_range.textRange, "_prefix_text"):
            self._end_text = text_range.textRange._prefix_text
            return
        if hasattr(text_range, "_end_text"):
            self._end_text = ""
            return
        if not hasattr(text_range, "textRange"):
            raise AttributeError("expected wrapped text range")
        self._end_text = ""

    def GetAttributeValue(self, attribute_id):
        if attribute_id == _FakeTextAttributeIds.IsReadOnlyAttribute:
            return self._read_only
        return None

    def Move(self, text_unit, count):
        return count

    def Select(self):
        return self._select_result


class _FakeCaretTextRange(object):
    textRange = object()

    def GetText(self, max_length):
        return ""

    def Clone(self):
        return self

    def MoveEndpointByRange(self, src_endpoint, text_range, target_endpoint):
        pass


class _FakeRawCaretRange(object):
    def Clone(self):
        return self

    def GetText(self, max_length):
        return ""

    def MoveEndpointByRange(self, src_endpoint, text_range, target_endpoint):
        pass


class _FakeWrappedTextRange(_FakeCaretTextRange):
    def __init__(self, raw_range):
        self.textRange = raw_range


class _FakeTextPattern(object):
    def __init__(self, text, read_only=False, selection=None,
                 select_result=True, raise_on_document_range=False):
        self._text = text
        self._read_only = read_only
        self._selection = [] if selection is None else [selection]
        self._select_result = select_result
        self._raise_on_document_range = raise_on_document_range

    @property
    def DocumentRange(self):
        if self._raise_on_document_range:
            raise RuntimeError("DocumentRange getter failed")
        return _FakeTextRange(self._text,
                              self._read_only,
                              select_result=self._select_result)

    def GetSelection(self):
        return self._selection


class _FakeTextPattern2(object):
    def __init__(self, result=None, document_range=None, selection=None,
                 expose_pattern=True):
        if expose_pattern:
            self.pattern = self
        self._result = result
        self._document_range = document_range
        self._selection = [] if selection is None else [selection]

    def GetCaretRange(self):
        return self._result

    @property
    def DocumentRange(self):
        return self._document_range

    def GetSelection(self):
        return self._selection


class _FakeValuePattern(object):
    def __init__(self, value, read_only=False, raise_on_is_read_only=False):
        self.Value = value
        self._read_only = read_only
        self._raise_on_is_read_only = raise_on_is_read_only

    @property
    def IsReadOnly(self):
        if self._raise_on_is_read_only:
            raise RuntimeError("IsReadOnly getter failed")
        return self._read_only


class _FakeSelectionRange(object):
    def __init__(self, prefix_text, collapsed=True):
        self._prefix_text = prefix_text
        self._collapsed = collapsed

    def CompareEndpoints(self, src_endpoint, other, target_endpoint):
        return 0 if self._collapsed else 1


class _FakeWrappedSelectionRange(object):
    def __init__(self, raw_range):
        self.textRange = raw_range

    def CompareEndpoints(self, src_endpoint, other, target_endpoint):
        raise AssertionError("wrapper CompareEndpoints should not be used")


class _FakeController(object):
    def __init__(self, focused):
        self._focused = focused

    def run_sync(self, closure):
        return closure(uia.Context(self._focused))


class _FakeControl(object):
    def __init__(self, parent=None, text_pattern=None, text_pattern2=None,
                 value_pattern=None, properties=None):
        self._parent = parent
        self._text_pattern = text_pattern
        self._text_pattern2 = text_pattern2
        self._value_pattern = value_pattern
        self._properties = properties or {}

    def GetParentControl(self):
        return self._parent

    def GetTextPattern(self):
        return self._text_pattern

    def GetValuePattern(self):
        return self._value_pattern

    def GetPattern(self, pattern_id):
        if pattern_id == _FakePatternIds.TextPattern:
            return self._text_pattern
        if pattern_id == _FakePatternIds.TextPattern2:
            return self._text_pattern2
        if pattern_id == _FakePatternIds.ValuePattern:
            return self._value_pattern
        return None

    def GetPropertyValue(self, property_id):
        return self._properties.get(property_id)

    def GetPropertyValueEx(self, property_id, ignore_default_value):
        if ignore_default_value:
            return self._properties.get(property_id)
        return self.GetPropertyValue(property_id)


class _FakeUnsupportedFocusedText(object):
    expanded_text = "alpha bravo"
    cursor = 0

    def set_cursor(self, offset):
        raise base.UnsupportedSelectionError()


class _FakeTextAccessible(object):
    def __init__(self, text):
        self._text = text

    def as_text(self):
        return self._text


def _reload_accessibility_for_windows(backend_name=None):
    patch = pytest.MonkeyPatch()
    patch.setattr(sys, "platform", "win32")
    patch.setenv("DISPLAY", "")
    if backend_name is None:
        patch.delenv("DRAGONFLY_WINDOWS_ACCESSIBILITY_BACKEND", raising=False)
    else:
        patch.setenv("DRAGONFLY_WINDOWS_ACCESSIBILITY_BACKEND", backend_name)
    try:
        return patch, importlib.reload(accessibility)
    except Exception:
        patch.undo()
        importlib.reload(accessibility)
        raise


def _restore_accessibility(patch):
    patch.undo()
    importlib.reload(accessibility)


def test_windows_backend_defaults_to_uia():
    patch, module = _reload_accessibility_for_windows()
    try:
        assert module.os_controller_class is module.uia.Controller
    finally:
        _restore_accessibility(patch)


def test_windows_backend_ia2_override_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        patch, module = _reload_accessibility_for_windows("ia2")
    try:
        assert module.os_controller_class is module.ia2.Controller
        assert any("deprecated" in str(item.message).lower()
                   for item in caught)
    finally:
        _restore_accessibility(patch)


def test_uia_accessible_uses_text_pattern_from_ancestor(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    parent = _FakeControl(text_pattern=_FakeTextPattern("alpha bravo"))
    child = _FakeControl(parent=parent)
    accessible = uia.Accessible(child)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "alpha bravo"
    assert accessible.is_editable() is True


def test_uia_accessible_falls_back_to_value_pattern(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(value_pattern=_FakeValuePattern("alpha", False))
    accessible = uia.Accessible(control)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "alpha"
    assert accessible.is_editable() is True


def test_uia_accessible_prefers_focused_value_pattern_over_ancestor_text(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    parent = _FakeControl(
        text_pattern=_FakeTextPattern(
            "document text", selection=_FakeSelectionRange("document ")))
    child = _FakeControl(parent=parent,
                         value_pattern=_FakeValuePattern("field text", False))
    accessible = uia.Accessible(child)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "field text"
    assert text_node.cursor is None
    assert accessible.is_editable() is True


def test_uia_read_only_value_pattern_is_not_editable(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(value_pattern=_FakeValuePattern("alpha", True))
    accessible = uia.Accessible(control)

    assert accessible.is_editable() is False


def test_uia_value_pattern_uses_value_is_read_only_property_when_getter_raises(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    parent = _FakeControl(
        text_pattern=_FakeTextPattern(
            "document text", selection=_FakeSelectionRange("document ")))
    child = _FakeControl(
        parent=parent,
        value_pattern=_FakeValuePattern("field text",
                                        raise_on_is_read_only=True),
        properties={_FakePropertyIds.ValueIsReadOnlyProperty: False})
    accessible = uia.Accessible(child)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "field text"
    assert text_node.cursor is None
    assert accessible.is_editable() is True


def test_uia_value_pattern_is_not_editable_when_read_only_is_unknown(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        value_pattern=_FakeValuePattern("alpha",
                                        raise_on_is_read_only=True))
    accessible = uia.Accessible(control)

    assert accessible.is_editable() is False


def test_uia_accessible_supports_textpattern2_only_provider(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern2=_FakeTextPattern2(
            document_range=_FakeTextRange("alpha bravo", False),
            selection=_FakeSelectionRange("alpha ")))
    accessible = uia.Accessible(control)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "alpha bravo"
    assert text_node.cursor == len("alpha ")
    assert accessible.is_editable() is True


def test_uia_accessible_supports_textpattern2_without_pattern_attr(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern2=_FakeTextPattern2(
            result=(False, _FakeRawCaretRange()),
            document_range=_FakeTextRange("alpha bravo", False),
            selection=_FakeSelectionRange("alpha "),
            expose_pattern=False))
    accessible = uia.Accessible(control)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "alpha bravo"
    assert text_node.cursor == len("alpha ")
    assert accessible.is_editable() is True


def test_uia_read_only_text_pattern_is_not_editable(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern=_FakeTextPattern("read only document", read_only=True),
        properties={_FakePropertyIds.ValueIsReadOnlyProperty: False})
    accessible = uia.Accessible(control)

    assert accessible.is_editable() is False


def test_uia_editable_text_pattern_uses_value_is_read_only_property(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern=_FakeTextPattern("editable document", read_only=None),
        properties={_FakePropertyIds.ValueIsReadOnlyProperty: False})
    accessible = uia.Accessible(control)

    assert accessible.is_editable() is True


def test_uia_document_range_failure_falls_back_to_value_pattern(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern=_FakeTextPattern("document text",
                                      raise_on_document_range=True),
        value_pattern=_FakeValuePattern("value text", False))
    accessible = uia.Accessible(control)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == "value text"
    assert text_node.cursor is None


def test_uia_document_range_failure_is_fail_closed_for_selection(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern=_FakeTextPattern("document text",
                                      raise_on_document_range=True))
    accessible = uia.Accessible(control)
    controller = _FakeController(accessible)

    text_node = accessible.as_text()

    assert text_node is not None
    assert text_node.expanded_text == ""
    assert text_node.cursor is None
    assert utils.set_cursor_offset(controller, 0) is False


def test_move_cursor_returns_false_for_value_only_text(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(value_pattern=_FakeValuePattern("alpha bravo", False))
    controller = _FakeController(uia.Accessible(control))

    result = utils.move_cursor(controller,
                               utils.TextQuery(end_phrase="bravo"),
                               utils.CursorPosition.BEFORE)

    assert result is False


def test_move_cursor_returns_false_when_set_cursor_select_fails(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    control = _FakeControl(
        text_pattern=_FakeTextPattern("alpha bravo", False, select_result=False))
    controller = _FakeController(uia.Accessible(control))

    result = utils.move_cursor(controller,
                               utils.TextQuery(end_phrase="alpha"),
                               utils.CursorPosition.BEFORE)

    assert result is False


def test_set_cursor_offset_returns_false_when_cursor_restore_is_unsupported():
    controller = _FakeController(
        _FakeTextAccessible(_FakeUnsupportedFocusedText()))

    result = utils.set_cursor_offset(controller, 3)

    assert result is False


def test_textpattern2_caret_range_accepts_tuple_with_flag_first(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    node = uia.AccessibleTextNode(
        text_pattern=_FakeTextPattern("alpha bravo", False),
        text_pattern2=_FakeTextPattern2((True, _FakeRawCaretRange())))

    assert node.cursor == 0


def test_textpattern2_inactive_caret_falls_back_to_selection(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    node = uia.AccessibleTextNode(
        text_pattern=_FakeTextPattern(
            "alpha bravo", False, selection=_FakeSelectionRange("alpha ")),
        text_pattern2=_FakeTextPattern2((False, _FakeRawCaretRange())))

    assert node.cursor == len("alpha ")


def test_selection_cursor_fallback_uses_raw_range_when_wrapper_compare_breaks(monkeypatch):
    monkeypatch.setattr(uia, "auto", _FakeAuto())
    selection = _FakeWrappedSelectionRange(_FakeSelectionRange("alpha "))
    node = uia.AccessibleTextNode(
        text_pattern=_FakeTextPattern("alpha bravo", False, selection=selection))

    assert node.cursor == len("alpha ")
