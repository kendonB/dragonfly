import unittest

from dragonfly import Literal, Repetition
from dragonfly.engines.backend_sphinx.compiler import (
    JSGFCompiler,
    SphinxJSGFCompiler,
)


class _DummyEngine(object):

    language = "en"

    @staticmethod
    def check_valid_word(word):
        return True


class TestCompilerSphinx(unittest.TestCase):

    def test_zero_or_more_unbounded_repetition_stays_optional(self):
        element = Repetition(
            Literal("hello"), min=0, unbounded=True, optimize=False,
        )

        expansion = JSGFCompiler().compile_element(element, None, set())
        self.assertEqual(expansion.compile(), "[(hello)+]")

        expansion = SphinxJSGFCompiler(_DummyEngine()).compile_element(
            element, None, set(),
        )
        self.assertEqual(expansion.compile(), "[(hello)[hello]*]")

    def test_unbounded_repetition_preserves_minimum(self):
        element = Repetition(
            Literal("hello"), min=3, unbounded=True, optimize=False,
        )

        expansion = JSGFCompiler().compile_element(element, None, set())
        self.assertEqual(expansion.compile(), "hello hello (hello)+")

        expansion = SphinxJSGFCompiler(_DummyEngine()).compile_element(
            element, None, set(),
        )
        self.assertEqual(expansion.compile(), "hello hello (hello)[hello]*")
