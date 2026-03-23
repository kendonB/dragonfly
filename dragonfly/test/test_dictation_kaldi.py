#
# This file is part of Dragonfly.
# Licensed under the LGPL.
#

import unittest

from dragonfly.grammar.elements_basic import Dictation
from dragonfly.engines.backend_kaldi.dictation import (
    AlternativeDictation,
    DefaultDictation,
    _get_dictation_nonterminal,
)


class TestKaldiDictationNonterminal(unittest.TestCase):

    def test_specialized_dictation_elements_choose_expected_nonterminal(self):
        cases = (
            (Dictation("text"), '#nonterm:dictation'),
            (AlternativeDictation("text"), '#nonterm:dictation_cloud'),
            (DefaultDictation("text"), '#nonterm:dictation'),
            (AlternativeDictation("text", alternative=False), '#nonterm:dictation'),
            (DefaultDictation("text", alternative=True), '#nonterm:dictation_cloud'),
        )

        for element, expected in cases:
            with self.subTest(element=repr(element)):
                self.assertEqual(expected, _get_dictation_nonterminal(element))
