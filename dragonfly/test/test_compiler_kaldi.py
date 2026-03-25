import unittest

from dragonfly import Literal, Repetition
from dragonfly.engines.backend_kaldi.compiler import KaldiCompiler


class _DummyFst(object):

    eps = "<eps>"
    eps_disambig = "#0"

    def __init__(self):
        self.next_state = 2
        self.arcs = []

    def add_state(self, initial=False, final=False):
        state = self.next_state
        self.next_state += 1
        return state

    def add_arc(self, src, dst, label, output=None, weight=None):
        self.arcs.append((src, dst, label, output, weight))

    def has_eps_path(self, src, dst, eps_like_nonterms):
        return False


class _DummyKaldiCompiler(object):

    _eps_like_nonterms = frozenset()

    def add_weight_linkage(self, src, dst, weight, fst):
        return src

    def get_weight(self, element):
        return 1

    def compile_element(self, element, src, dst, grammar, kaldi_rule, fst):
        if isinstance(element, Literal):
            fst.add_arc(src, dst, tuple(element.words), None, None)
            return
        return KaldiCompiler._compile_sequence(
            self, element, src, dst, grammar, kaldi_rule, fst,
        )


class TestCompilerKaldi(unittest.TestCase):

    def test_unbounded_repetition_optimize_false_zero_or_more_has_skip_arc(self):
        fst = _DummyFst()
        compiler = _DummyKaldiCompiler()

        KaldiCompiler._compile_sequence(
            compiler,
            Repetition(Literal("hello"), min=0, unbounded=True,
                       optimize=False),
            0, 1, None, None, fst,
        )

        assert fst.arcs == [
            (0, 1, None, None, None),
            (0, 2, None, None, None),
            (2, 3, ("hello",), None, None),
            (3, 2, "#0", "<eps>", None),
            (3, 1, None, None, None),
        ]

    def test_unbounded_repetition_optimize_false_preserves_minimum(self):
        fst = _DummyFst()
        compiler = _DummyKaldiCompiler()

        KaldiCompiler._compile_sequence(
            compiler,
            Repetition(Literal("hello"), min=3, unbounded=True,
                       optimize=False),
            0, 1, None, None, fst,
        )

        assert fst.arcs == [
            (0, 2, ("hello",), None, None),
            (2, 3, ("hello",), None, None),
            (3, 4, None, None, None),
            (4, 5, ("hello",), None, None),
            (5, 4, "#0", "<eps>", None),
            (5, 1, None, None, None),
        ]
