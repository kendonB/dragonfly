import unittest

from dragonfly import (Choice, Compound, CompoundRule, Function, Literal,
                       MappingRule, Optional, Repetition, Sequence)
from dragonfly.engines import get_engine
from dragonfly.parsing.parse import ParseError
from dragonfly.test import ElementTester
from dragonfly.test.rule_test_grammar import RuleTestGrammar


class CompoundInlineRepetitionElementTests(unittest.TestCase):

    def setUp(self):
        self.engine = get_engine("text")

    def test_compound_value_func_returns_repeated_extra_list(self):
        element = Compound(
            "test <word>{1,}",
            extras=[Choice("word", {"alpha": "A", "bravo": "B"})],
            value_func=lambda node, extras: extras["word"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test alpha bravo"), ["A", "B"])

    def test_compound_value_func_returns_empty_list_for_star(self):
        element = Compound(
            "test <word>{0,}",
            extras=[Choice("word", {"alpha": "A", "bravo": "B"})],
            value_func=lambda node, extras: extras["word"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test"), [])

    def test_compound_value_func_wraps_omitted_repeated_extra_default(self):
        element = Compound(
            "test <word>{0,}",
            extras=[Choice("word", {"alpha": "A"}, default="fallback")],
            value_func=lambda node, extras: extras["word"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test"), ["fallback"])

    def test_compound_value_func_collects_reused_repeated_extra_values(self):
        element = Compound(
            "test <word> <word>{1,}",
            extras=[Choice("word", {
                "alpha": "A",
                "bravo": "B",
                "charlie": "C",
            })],
            value_func=lambda node, extras: extras["word"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(
            tester.recognize("test alpha bravo charlie"),
            ["A", "B", "C"],
        )

    def test_named_compound_value_func_collects_repeated_extra_values(self):
        element = Compound(
            "test <word>{1,}",
            name="phrase",
            extras=[Choice("word", {"alpha": "A", "bravo": "B"})],
            value_func=lambda node, extras: extras["word"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test alpha bravo"), ["A", "B"])

    def test_compound_value_func_uses_matched_branch_repetition_shape(self):
        element = Compound(
            "(single <item>) | (many <item>{1,})",
            extras=[Choice("item", {"alpha": "A", "bravo": "B"})],
            value_func=lambda node, extras: extras["item"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("single alpha"), "A")
        self.assertEqual(tester.recognize("many alpha bravo"), ["A", "B"])

    def test_compound_value_func_keeps_repeated_shape_inside_omitted_wrapper(self):
        element = Compound(
            "test [prefix <item>{0,}]",
            extras=[Choice("item", {"alpha": "A", "bravo": "B"})],
            value_func=lambda node, extras: extras["item"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test"), [])

    def test_compound_value_func_omitted_mixed_optional_branch_stays_scalar(self):
        element = Compound(
            "test [single <item> | many <item>{1,}]",
            extras=[Choice("item", {"alpha": "A", "bravo": "B"},
                           default="fallback")],
            value_func=lambda node, extras: extras["item"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("test"), "fallback")
        self.assertEqual(tester.recognize("test single alpha"), "A")
        self.assertEqual(tester.recognize("test many alpha bravo"),
                         ["A", "B"])

    def test_named_repetition_extra_keeps_historical_shape(self):
        element = Compound(
            "<repetition>",
            extras=[Repetition(Literal("hello"), min=1, max=3,
                               name="repetition")],
            value_func=lambda node, extras: extras["repetition"],
        )
        tester = ElementTester(element, engine=self.engine)
        self.assertEqual(tester.recognize("hello hello"), ["hello", "hello"])

    def test_compound_rejects_unbounded_empty_match(self):
        with self.assertRaises(ParseError):
            Compound("test [word]{0,}")

    def test_unbounded_repetition_rejects_reused_empty_child(self):
        optional = Optional(Literal("word"))
        with self.assertRaises(ValueError):
            Repetition(Sequence([optional, optional]), min=0, unbounded=True)

    def test_unbounded_repetition_rejects_empty_alternative(self):
        with self.assertRaises(ValueError):
            Repetition(Choice("word", {}), min=0, unbounded=True)

    def test_unbounded_repetition_rejects_empty_literal(self):
        with self.assertRaises(ValueError):
            Repetition(Literal(""), min=0, unbounded=True)

    def test_bounded_repetition_remains_greedy(self):
        element = Sequence([
            Repetition(Literal("a"), min=1, max=3),
            Optional(Literal("a")),
        ])
        tester = ElementTester(element, engine=self.engine)

        self.assertEqual(tester.recognize("a a"), [["a", "a"], None])


class CompoundInlineRepetitionRuleTests(unittest.TestCase):

    def setUp(self):
        self.engine = get_engine("text")
        self.grammar = RuleTestGrammar(engine=self.engine)

    def tearDown(self):
        if self.grammar.loaded:
            self.grammar.unload()
        for rule in self.grammar.rules:
            self.grammar.remove_rule(rule)
        for lst in self.grammar.lists:
            self.grammar.remove_list(lst)

    def test_compound_rule_repeated_choice_returns_list(self):
        class TestRule(CompoundRule):
            spec = "test <word>{1,}"
            extras = [Choice("word", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("test alpha bravo")
        self.assertEqual(extras["word"], ["A", "B"])

    def test_compound_rule_star_returns_empty_list(self):
        class TestRule(CompoundRule):
            spec = "test <word>{0,}"
            extras = [Choice("word", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("test")
        self.assertEqual(extras["word"], [])

    def test_compound_rule_uses_matched_branch_repetition_shape(self):
        class TestRule(CompoundRule):
            spec = "(single <item>) | (many <item>{1,})"
            extras = [Choice("item", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.assertEqual(self.grammar.recognize_extras("single alpha")["item"],
                         "A")
        self.assertEqual(
            self.grammar.recognize_extras("many alpha bravo")["item"],
            ["A", "B"],
        )

    def test_compound_rule_star_preserves_default_when_omitted(self):
        class TestRule(CompoundRule):
            spec = "test <word>{0,}"
            extras = [Choice("word", {"alpha": "A", "bravo": "B"})]
            defaults = {"word": ["fallback"]}

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("test")
        self.assertEqual(extras["word"], ["fallback"])

    def test_compound_rule_star_prefers_element_default_when_omitted(self):
        class TestRule(CompoundRule):
            spec = "test <word>{0,}"
            extras = [Choice("word", {"alpha": "A"}, default="element")]
            defaults = {"word": "rule"}

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("test")
        self.assertEqual(extras["word"], ["element"])

    def test_compound_rule_named_repetition_extra_keeps_historical_shape(self):
        class TestRule(CompoundRule):
            spec = "<repetition>"
            extras = [Repetition(Literal("hello"), min=1, max=3,
                                 name="repetition")]

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("hello hello")
        self.assertEqual(extras["repetition"], ["hello", "hello"])

    def test_compound_rule_named_repeated_branch_keeps_child_default(self):
        items = Repetition(
            Choice("item", {"alpha": "A", "bravo": "B"}),
            min=1, max=4, name="items",
        )

        class TestRule(CompoundRule):
            spec = "(single <item>) | (many <items>)"
            extras = [Choice("item", {"alpha": "A", "bravo": "B"}), items]
            defaults = {"item": "fallback"}

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("many alpha bravo")
        self.assertEqual(extras["item"], "fallback")
        self.assertEqual(extras["items"], ["A", "B"])

    def test_mapping_rule_function_binding_uses_repeated_list(self):
        captured = []

        class TestRule(MappingRule):
            mapping = {
                "test <word>{1,}": Function(lambda word: captured.append(word)),
            }
            extras = [Choice("word", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.grammar.recognize("test alpha bravo")
        self.assertEqual(captured, [["A", "B"]])

    def test_mapping_rule_non_repeated_choice_stays_scalar(self):
        captured = []

        class TestRule(MappingRule):
            mapping = {
                "test <word>": Function(lambda word: captured.append(word)),
            }
            extras = [Choice("word", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.grammar.recognize("test alpha")
        self.assertEqual(captured, ["A"])

    def test_mapping_rule_uses_matched_branch_repetition_shape(self):
        captured = []

        class TestRule(MappingRule):
            mapping = {
                "(single <item>) | (many <item>{1,})":
                    Function(lambda item: captured.append(item)),
            }
            extras = [Choice("item", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.grammar.recognize("single alpha")
        self.grammar.recognize("many alpha bravo")
        self.assertEqual(captured, ["A", ["A", "B"]])

    def test_mapping_rule_keeps_repeated_shape_inside_omitted_wrapper(self):
        captured = []

        class TestRule(MappingRule):
            mapping = {
                "test [prefix <item>{0,}]":
                    Function(lambda item: captured.append(item)),
            }
            extras = [Choice("item", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.grammar.recognize("test")
        self.assertEqual(captured, [[]])

    def test_mapping_rule_whole_spec_extra_still_binds(self):
        captured = []

        class TestRule(MappingRule):
            mapping = {
                "<choice>": Function(lambda choice: captured.append(choice)),
            }
            extras = [Choice("choice", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        self.grammar.recognize("alpha")
        self.assertEqual(captured, ["A"])

    def test_mapping_rule_whole_spec_extra_still_reaches_process_extras(self):
        class TestRule(MappingRule):
            mapping = {
                "<choice>": "value",
            }
            extras = [Choice("choice", {"alpha": "A", "bravo": "B"})]

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("alpha")
        self.assertEqual(extras["choice"], "A")

    def test_mapping_rule_whole_spec_repetition_still_reaches_process_extras(self):
        class TestRule(MappingRule):
            mapping = {
                "<rep>": "value",
            }
            extras = [Repetition(Literal("hello"), min=1, max=4, name="rep")]

        self.grammar.add_rule(TestRule())
        extras = self.grammar.recognize_extras("hello hello")
        self.assertEqual(extras["rep"], ["hello", "hello"])

    def test_unbounded_repetition_handles_long_match(self):
        words = " ".join(["a"] * 1200)
        element = Repetition(Literal("a"), min=1, unbounded=True)
        tester = ElementTester(element, engine=self.engine)

        result = tester.recognize(words)
        self.assertEqual(len(result), 1200)
