import copy
import re

from lark import Lark, Transformer

from dragonfly.grammar.elements_basic import (Literal, Optional, Sequence,
                                              Alternative, Repetition,
                                              id_generator)

grammar_string = r"""
?start: alternative

// ? means that the rule will be inlined iff there is a single child
?alternative: sequence ("|" sequence)*
sequence: single* special*

?single: atom REPEAT_RANGE      -> quantified
       | atom

?atom: WORD                     -> word
     | "<" WORD ">"            -> reference
     | "[" alternative "]"     -> optional
     | "(" alternative ")"     -> grouped

special: SPECIAL                 -> special_specifier

// Match anything which is not whitespace or a control character,
// we will let the engine handle invalid words
WORD: /[^\s\[\]<>|(){}]+/
REPEAT_RANGE.2: /\{\d+(?:,\d*)?\}/
SPECIAL.1: /\{(?=[^\s\[\]<>|(){}]*[^\s\[\]<>|(){}\d,])[^\s\[\]<>|(){}]+\}/

%import common.WS_INLINE
%ignore WS_INLINE
"""

_spec_parser = Lark(
    grammar_string,
    parser="lalr",
    lexer="contextual",
)
spec_parser = _spec_parser

class ParseError(Exception):
    pass


class _LiteralWord(str):
    pass


def _copy_element_for_specials(element):
    cloned = copy.copy(element)
    cloned._id = next(id_generator)
    return cloned


class CompoundTransformer(Transformer):
    """
        Visits each node of the parse tree starting with the leaves
        and working up, replacing lark Tree objects with the
        appropriate dragonfly classes.
    """

    def __init__(self, extras=None, *args, **kwargs):
        self.extras = extras or {}
        Transformer.__init__(self, *args, **kwargs)

    def optional(self, args):
        return Optional(self._coerce_element(args[0]))

    def grouped(self, args):
        return self._coerce_element(args[0])

    def word(self, args):
        return _LiteralWord(str(args[0]))

    def sequence(self, args):
        children = []
        literal_words = []
        specifiers = []

        def flush_literal_words():
            if literal_words:
                children.append(Literal(" ".join(literal_words)))
                del literal_words[:]

        for arg in args:
            if isinstance(arg, _LiteralWord):
                literal_words.append(arg)
            elif isinstance(arg, tuple) and arg and arg[0] == "special":
                flush_literal_words()
                specifiers.append(arg[1])
            else:
                flush_literal_words()
                children.append(self._coerce_element(arg))

        flush_literal_words()

        if not children:
            element = Sequence([])
        elif len(children) == 1:
            element = children[0]
        else:
            element = Sequence(children)

        if specifiers and len(children) == 1:
            element = _copy_element_for_specials(element)

        for specifier in specifiers:
            element = self._apply_special(element, specifier)
        return element

    def alternative(self, args):
        args = [self._coerce_element(arg) for arg in args]
        if len(args) == 1:
            return args[0]
        return Alternative(args)

    def reference(self, args):
        ref = args[0]
        try:
            return self.extras[ref]
        except KeyError:
            raise Exception("Unknown reference name %r" % (str(ref)))

    def brace_repeat_quantifier(self, args):
        text = str(args[0])[1:-1]
        if text.endswith(","):
            return ("unbounded", int(text[:-1]))
        if "," in text:
            minimum, maximum = text.split(",", 1)
            minimum = int(minimum)
            maximum = int(maximum)
            if minimum > maximum:
                raise ParseError("Invalid repetition range {%d,%d}" %
                                 (minimum, maximum))
            return ("range", minimum, maximum)
        return ("exact", int(text))

    def special_specifier(self, args):
        return ("special", str(args[0])[1:-1])

    def quantified(self, args):
        return self._make_repetition(
            self._coerce_element(args[0]),
            self.brace_repeat_quantifier([args[1]]),
        )

    def _make_repetition(self, child, quantifier):
        kind = quantifier[0]
        if kind == "unbounded":
            return Repetition(child, min=quantifier[1], unbounded=True)
        if kind == "exact":
            return Repetition(child, min=quantifier[1], max=None)
        if kind == "range":
            return Repetition(child, min=quantifier[1], max=quantifier[2] + 1)
        raise ParseError("Unknown repetition quantifier %r" % (quantifier,))

    def _apply_special(self, child, specifier):
        if re.match(r"^\d+(,\d*)?$", specifier):
            raise ParseError("Numeric brace bodies must be attached directly "
                             "to a single item for repetition")
        if '=' in specifier:
            name, value = specifier.split('=')

            # Try to convert the value to a bool, None or a float.
            if value in ['True', 'False']:
                value = bool(value)
            elif value == 'None':
                value = None
            else:
                try:
                    value = float(value)
                except ValueError:
                    # Conversion failed, value is just a string.
                    pass
        else:
            name, value = specifier, True

        if name in ['weight', 'w']:
            child.weight = float(value)
        elif name in ['test_special']:
            child.test_special = value
        else:
            raise ParseError("Unrecognized special specifier: {%s}" %
                             specifier)

        return child

    def _coerce_element(self, value):
        if isinstance(value, _LiteralWord):
            return Literal(str(value))
        return value
