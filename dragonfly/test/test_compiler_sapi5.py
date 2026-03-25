import sys
import types
import unittest

from dragonfly import Literal, Repetition

try:
    from dragonfly.engines.backend_sapi5.compiler import Sapi5Compiler
except ImportError:
    sys.modules.pop("dragonfly.engines.backend_sapi5.compiler", None)
    client = types.ModuleType("win32com.client")
    client.constants = type(
        "Constants", (), {"SRATopLevel": 1, "SRADynamic": 2}
    )()
    win32com = types.ModuleType("win32com")
    win32com.client = client
    sys.modules.setdefault("win32com", win32com)
    sys.modules["win32com.client"] = client
    from dragonfly.engines.backend_sapi5.compiler import Sapi5Compiler


class _FakeState(object):

    def __init__(self, rule):
        self.Rule = rule
        self.word_transitions = []

    def AddWordTransition(self, dst_state, text):
        self.word_transitions.append((dst_state, text))

    def AddRuleTransition(self, dst_state, rule_handle):
        raise AssertionError("Unexpected rule transition during test")

    def AddSpecialTransition(self, dst_state, special):
        raise AssertionError("Unexpected special transition during test")


class _FakeRule(object):

    def __init__(self):
        self.states = []

    def AddState(self):
        state = _FakeState(self)
        self.states.append(state)
        return state


class TestCompilerSapi5(unittest.TestCase):

    @staticmethod
    def _serialize_transitions(state, labels):
        return [(labels[dst_state], text) for dst_state, text
                in state.word_transitions]

    def test_zero_or_more_unbounded_repetition_stays_optional(self):
        compiler = Sapi5Compiler()
        rule = _FakeRule()
        src = _FakeState(rule)
        dst = _FakeState(rule)

        compiler.compile_element(
            Repetition(Literal("hello"), min=0, unbounded=True,
                       optimize=False),
            src, dst, None, None,
        )

        labels = {src: "src", dst: "dst", rule.states[0]: "s0"}
        self.assertEqual(
            self._serialize_transitions(src, labels),
            [("dst", ""), ("s0", "hello")],
        )
        self.assertEqual(
            self._serialize_transitions(rule.states[0], labels),
            [("src", ""), ("dst", "")],
        )

    def test_unbounded_repetition_preserves_minimum(self):
        compiler = Sapi5Compiler()
        rule = _FakeRule()
        src = _FakeState(rule)
        dst = _FakeState(rule)

        compiler.compile_element(
            Repetition(Literal("hello"), min=3, unbounded=True,
                       optimize=False),
            src, dst, None, None,
        )

        labels = {src: "src", dst: "dst"}
        labels.update(
            {state: "s%d" % index for index, state in enumerate(rule.states)}
        )

        self.assertEqual(
            self._serialize_transitions(src, labels),
            [("s0", "hello")],
        )
        self.assertEqual(
            self._serialize_transitions(rule.states[0], labels),
            [("s1", "hello")],
        )
        self.assertEqual(
            self._serialize_transitions(rule.states[1], labels),
            [("s2", "hello")],
        )
        self.assertEqual(
            self._serialize_transitions(rule.states[2], labels),
            [("s1", ""), ("dst", "")],
        )
