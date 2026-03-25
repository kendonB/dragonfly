# coding=utf-8

import unittest

from dragonfly.parsing.parse import spec_parser, CompoundTransformer, ParseError
from dragonfly import (Compound, Literal, Sequence, Optional, Alternative,
                       Repetition)

# ===========================================================================

extras = {"an_extra": Alternative([Literal(u"1"), Literal(u"2")])}


def check_parse_tree(spec, expected):
    tree = spec_parser.parse(spec)
    output = CompoundTransformer(extras).transform(tree)
    assert output.element_tree_string() == expected.element_tree_string()
    return output


class TestLarkParser(unittest.TestCase):
    def test_literal(self):
        check_parse_tree("test   ", Literal(u"test"))

    def test_multiple_literals(self):
        check_parse_tree("test  hello world ", Literal(u"test hello world"))

    def test_parens(self):
        check_parse_tree("(test )   ", Literal(u"test"))

    def test_punctuation(self):
        check_parse_tree(",", Literal(u","))
        check_parse_tree("*", Literal(u"*"))
        check_parse_tree("test's   ", Literal(u"test's"))
        check_parse_tree("cul-de-sac   ", Literal(u"cul-de-sac"))
        check_parse_tree("C++", Literal(u"C++"))

    def test_sequence(self):
        check_parse_tree(
            " test <an_extra> [op]",
            Sequence([Literal(u"test"), extras["an_extra"], Optional(Literal(u"op"))]),
        )
        check_parse_tree(
            " <an_extra> +",
            Sequence([extras["an_extra"], Literal(u"+")]),
        )
        check_parse_tree(
            " grade <an_extra>+",
            Sequence([Literal(u"grade"), extras["an_extra"], Literal(u"+")]),
        )
        check_parse_tree(
            " (test) *",
            Sequence([Literal(u"test"), Literal(u"*")]),
        )
        check_parse_tree(
            " (test)*",
            Sequence([Literal(u"test"), Literal(u"*")]),
        )

    def test_alternative_no_parens(self):
        check_parse_tree(
            " test |[op] <an_extra>",
            Alternative(
                [
                    Literal(u"test"),
                    Sequence([Optional(Literal(u"op")), extras["an_extra"]]),
                ]
            ),
        )

    def test_alternative_parens(self):
        check_parse_tree(
            "( test |[op] <an_extra>)",
            Alternative(
                [
                    Literal(u"test"),
                    Sequence([Optional(Literal(u"op")), extras["an_extra"]]),
                ]
            ),
        )

    def test_optional_alternative(self):
        check_parse_tree("[test|test's]", Optional(Alternative([Literal(u"test"), Literal(u"test's")])))

    def test_digit_in_word(self):
        check_parse_tree("F2", Literal(u"F2"))

    def test_unicode(self):
        check_parse_tree(u"touché", Literal(u"touché"))

    def test_bool_special_in_sequence(self):
        output = check_parse_tree(
            " test <an_extra> [op] {test_special}",
            Sequence([Literal(u"test"), extras["an_extra"], Optional(Literal(u"op"))]),
        )
        assert output.test_special == True
        assert all(getattr(child, 'test_special', None) == None for child in output.children)

    def test_other_special_in_sequence(self):
        output = check_parse_tree(
            " test <an_extra> [op] {test_special=4}",
            Sequence([Literal(u"test"), extras["an_extra"], Optional(Literal(u"op"))]),
        )
        assert output.test_special == 4
        assert all(getattr(child, 'test_special', None) == None for child in output.children)

    def test_bool_special_in_alternative(self):
        output = check_parse_tree(
            "foo | bar {test_special} | baz",
            Alternative([
                Literal(u"foo"),
                Literal(u"bar"),
                Literal(u"baz"),
            ]),
        )
        assert getattr(output.children[0], 'test_special', None) == None
        assert output.children[1].test_special == True
        assert getattr(output.children[2], 'test_special', None) == None

    def test_other_special_in_alternative(self):
        output = check_parse_tree(
            "foo | bar {test_special=4} | baz",
            Alternative([
                Literal(u"foo"),
                Literal(u"bar"),
                Literal(u"baz"),
            ]),
        )
        assert getattr(output.children[0], 'test_special', None) == None
        assert output.children[1].test_special == 4
        assert getattr(output.children[2], 'test_special', None) == None

    def test_special_on_single_reference_does_not_mutate_shared_extra(self):
        shared = Alternative([Literal(u"1"), Literal(u"2")])
        output = CompoundTransformer({"shared": shared}).transform(
            spec_parser.parse("<shared>{weight=0.1}")
        )

        self.assertIsNot(output, shared)
        self.assertEqual(output.weight, 0.1)
        self.assertIsNone(getattr(shared, "weight", None))

    def test_one_or_more_repeat(self):
        check_parse_tree(
            "<an_extra>{1,}",
            Repetition(extras["an_extra"], min=1, unbounded=True),
        )

    def test_zero_or_more_repeat(self):
        check_parse_tree(
            "<an_extra>{0,}",
            Repetition(extras["an_extra"], min=0, unbounded=True),
        )

    def test_bounded_repeat(self):
        check_parse_tree(
            "(test | hello){2,4}",
            Repetition(
                Alternative([Literal(u"test"), Literal(u"hello")]),
                min=2, max=5,
            ),
        )

    def test_repeat_after_bare_word_sequence(self):
        check_parse_tree(
            "test hello{2}",
            Sequence([
                Literal(u"test"),
                Repetition(Literal(u"hello"), min=2, max=3),
            ]),
        )

    def test_empty_sequence_keeps_historical_value_shape(self):
        check_parse_tree("", Sequence([]))
        check_parse_tree(
            "(foo |)",
            Alternative([Literal(u"foo"), Sequence([])]),
        )

    def test_invalid_repeat_range(self):
        with self.assertRaises(ParseError):
            Compound("hello{3,2}")


# ===========================================================================

if __name__ == "__main__":
    unittest.main()
