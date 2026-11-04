"""``define-syntax`` and ``syntax-rules`` — hygienic macros.

``defmacro`` is the raw tool: a procedure over forms. This module is the
*hygienic* one. A ``syntax-rules`` macro matches the use against a set of
``(pattern template)`` clauses and instantiates the first that fits — but
unlike ``defmacro`` it renames the identifiers its template introduces, so a
template's own ``tmp`` cannot capture a caller's ``tmp``, and a template's use
of ``list`` cannot be captured by a caller that has rebound ``list``.

The two directions of hygiene, and how each is handled:

* **Template binders are renamed.** ``(let ((x ...)) ...)`` inside a template
  gets a fresh ``x#hN`` (a hash and a counter), and so do its references — a
  caller's ``x`` is safe.
* **Free template identifiers are captured *by resolution*.** ``list`` in a
  template becomes a private alias pinned to whatever ``list`` meant where the
  macro was defined, so a caller's local ``list`` cannot shadow it.

What a transformer supports, beyond R7RS's minimum: ``_`` and literals, dotted
patterns, ``...`` at any depth (a pattern may nest — ``((_ (x ...) ...) ...)``),
and *stacked* ellipses in a template (``x ... ...``) that flatten one level per
``...``. A **vector** is a pattern and a template too: ``((_ #(a b)) ...)``
matches ``#(1 2)``, and a ``#(x ...)`` template builds one. A **dotted tail**
binds the forms after the fixed ones, usable either way a variadic macro needs
it: ``'rest`` is the tail as data, ``rest ...`` splices it back into code.
Macros may be bound locally with ``let-syntax`` / ``letrec-syntax``.

Deviations worth knowing: a template's ``(define name ...)`` keeps its written
name (so macros that define helpers stay visible), and only the binding forms
``lambda``/``let``/``let*``/``letrec`` are scope-analysed. An identifier that
was *unbound* where the macro was defined has no binding to pin, so it resolves
at the use site; define a helper before the macro that expands to it (or use
``defmacro`` with ``gensym``) when use-site capture would matter. There is no
``syntax-case`` and no custom ellipsis identifier: the transformer is always
``(syntax-rules (<literal> ...) (pattern template) ...)``.
"""
from __future__ import annotations

from typing import Any

from .env import Environment
from .errors import LispSyntaxError
from .printer import to_string
from .types import (
    NIL,
    Pair,
    Symbol,
    SyntaxRules,
    Vector,
    from_cells,
    intern,
    is_nil,
    make_list,
)

#: ``...`` repeats the subpattern before it.
ELLIPSIS = intern("...")
#: ``_`` in a pattern matches anything and binds nothing.
UNDERSCORE = intern("_")
SYNTAX_RULES = intern("syntax-rules")

LAMBDA = intern("lambda")
LET = intern("let")
LET_STAR = intern("let*")
LETREC = intern("letrec")

_counter = 0


# --------------------------------------------------------------------------- #
#  Parsing a transformer                                                       #
# --------------------------------------------------------------------------- #

def eval_define_syntax(expr: list, env: Environment) -> Any:
    """``(define-syntax name (syntax-rules (lit...) (pattern template)...))``."""
    if len(expr) != 3 or not isinstance(expr[1], Symbol):
        raise LispSyntaxError(
            "define-syntax: expected (define-syntax name (syntax-rules ...))"
        )
    env.define(expr[1], _parse_transformer(expr[1], expr[2], env, "define-syntax"))
    return expr[1]


def eval_let_syntax(expr: list, env: Environment, *, recursive: bool) -> Any:
    """``(let-syntax ((name (syntax-rules ...)) ...) body ...)``.

    The bindings are **local**: they shadow an outer macro (or a function) of
    the same name for the body's extent only, and vanish when it ends. In
    ``letrec-syntax`` the macros are pinned in the local frame, so a template
    may refer to a sibling macro; in ``let-syntax`` they are pinned in the
    enclosing frame, so a sibling is invisible to them — the only difference
    that matters, since a ``syntax-rules`` transformer is declarative data and
    is never run at definition time.
    """
    from .evaluator import _body_form, evaluate

    where = "letrec-syntax" if recursive else "let-syntax"
    if len(expr) < 3:
        raise LispSyntaxError(f"{where}: expected ({where} ((name ...) ...) body ...)")
    bindings = expr[1]
    if is_nil(bindings):
        pairs: list = []
    elif isinstance(bindings, list):
        pairs = list(bindings)
    else:
        raise LispSyntaxError(f"{where}: the bindings must be a list")

    local = Environment(parent=env)
    defining = local if recursive else env
    for binding in pairs:
        if not (isinstance(binding, list) and len(binding) == 2):
            raise LispSyntaxError(f"{where}: each binding is (name (syntax-rules ...))")
        name = binding[0]
        if not isinstance(name, Symbol):
            raise LispSyntaxError(f"{where}: the macro name must be a symbol")
        local.define(name, _parse_transformer(name, binding[1], defining, where))
    # The body rule is the evaluator's own (`_body_form`), so a single form and
    # a sequence of forms mean here exactly what they mean in a `lambda` body.
    return evaluate(_body_form(expr[2:]), local)


def _parse_transformer(
    name: Symbol, transformer: Any, env: Environment, where: str
) -> SyntaxRules:
    """Validate a ``(syntax-rules ...)`` form and return it as a transformer.

    *where* names the form that is asking (``define-syntax`` or a local
    ``let-syntax``), so a malformed binding says which one it was.
    """
    if not (isinstance(transformer, list) and transformer and transformer[0] is SYNTAX_RULES):
        raise LispSyntaxError(f"{where}: the transformer must be syntax-rules")
    if len(transformer) < 3:
        raise LispSyntaxError("syntax-rules: expected literals and at least one rule")
    literals = transformer[1]
    if is_nil(literals):
        literal_set: frozenset = frozenset()
    elif isinstance(literals, list):
        if not all(isinstance(x, Symbol) for x in literals):
            raise LispSyntaxError("syntax-rules: literals must be symbols")
        literal_set = frozenset(literals)
    else:
        raise LispSyntaxError("syntax-rules: literals must be a list")

    rules = []
    for rule in transformer[2:]:
        if not isinstance(rule, list) or len(rule) != 2:
            raise LispSyntaxError("syntax-rules: each rule is (pattern template)")
        rules.append((rule[0], rule[1]))
    return SyntaxRules(str(name), literal_set, rules, env)


# --------------------------------------------------------------------------- #
#  Expansion                                                                   #
# --------------------------------------------------------------------------- #

def expand(rules: SyntaxRules, form: list) -> Any:
    """Rewrite *form* (the whole macro use, keyword included) to its expansion."""
    key = to_string(form, write=True)
    # Memoise by rendered form — but never when the form holds an opaque host
    # value (rendered as ``#<…>``), since two different objects would collide.
    cacheable = "#<" not in key
    if cacheable:
        cached = rules.cache.get(key)
        if cached is not None:
            return cached
    for pattern, template in rules.rules:
        bindings = _match_rule(rules, pattern, form)
        if bindings is not None:
            result = _instantiate(template, dict(bindings), {}, rules)
            if cacheable:
                rules.cache[key] = result
            return result
    raise LispSyntaxError(f"{rules.name}: no syntax-rules pattern matched")


def _match_rule(rules: SyntaxRules, pattern: Any, form: list) -> Any:
    """Match *pattern* against *form*; return bindings (possibly empty) or None."""
    if isinstance(pattern, Symbol):
        if pattern is not rules.name and pattern is not UNDERSCORE:
            return None
        return {} if len(form) == 1 else None
    items, tail = _split(pattern)
    if not items:
        return None
    head = items[0]
    if head is not UNDERSCORE and head != rules.name:
        return None
    bindings: dict = {}
    if _match_seq(items[1:], tail, make_list(form[1:]), rules.literals, bindings):
        return bindings
    return None


def _match(pat: Any, form: Any, literals: frozenset, binds: dict) -> bool:
    if isinstance(pat, Symbol):
        if pat is UNDERSCORE:
            return True
        if pat in literals:
            return isinstance(form, Symbol) and form == pat
        binds[pat] = form
        return True
    if is_nil(pat):
        return is_nil(form)
    if isinstance(pat, Vector):
        # A vector pattern matches a vector element for element (and length for
        # length); `...` works inside it exactly as it does inside a list.
        if not isinstance(form, Vector):
            return False
        return _match_seq(list(pat.items), NIL, list(form.items), literals, binds)
    if isinstance(pat, (list, Pair)):
        items, tail = _split(pat)
        return _match_seq(items, tail, form, literals, binds)
    return _equal_literal(pat, form)


def _match_seq(
    items: list, tail: Any, form: Any, literals: frozenset, binds: dict
) -> bool:
    # A sequence pattern does not *match* a value that is not a sequence; it
    # must not raise, or a clause like ``((_ x (f a ...)) ...)`` would blow up
    # on ``(m x f)`` instead of letting the next clause try.
    if not (is_nil(form) or isinstance(form, (list, Pair))):
        return False
    f_items, f_tail = _split(form)
    if ELLIPSIS in items:
        index = items.index(ELLIPSIS)
        if items.count(ELLIPSIS) > 1 or index == 0 or index != len(items) - 1:
            raise LispSyntaxError("syntax-rules: '...' follows one subpattern, at the end")
        before = items[: index - 1]
        repeated = items[index - 1]
        after = items[index + 1 :]
        if len(f_items) < len(before) + len(after):
            return False
        for p, f in zip(before, f_items[: len(before)]):
            if not _match(p, f, literals, binds):
                return False
        middle = f_items[len(before) : len(f_items) - len(after)]
        collected: dict = {
            v: []
            for v in _vars_in(repeated)
            if v not in literals and v is not UNDERSCORE and v is not ELLIPSIS
        }
        for f in middle:
            sub: dict = {}
            if not _match(repeated, f, literals, sub):
                return False
            for key, value in sub.items():
                collected.setdefault(key, []).append(value)
        for key, value in collected.items():
            binds[key] = _Seq(value)
        for p, f in zip(after, f_items[len(f_items) - len(after) :]):
            if not _match(p, f, literals, binds):
                return False
        if is_nil(tail):
            return is_nil(f_tail)
        return _match_tail(tail, f_tail, literals, binds)

    if len(f_items) < len(items):
        return False
    for p, f in zip(items, f_items[: len(items)]):
        if not _match(p, f, literals, binds):
            return False
    if is_nil(tail):
        return len(f_items) == len(items) and is_nil(f_tail)
    rest = from_cells(f_items[len(items) :], f_tail)
    return _match_tail(tail, rest, literals, binds)


def _match_tail(tail: Any, form_tail: Any, literals: frozenset, binds: dict) -> bool:
    """Match the part of a pattern after the fixed elements.

    A ``Symbol`` tail is the *variadic* idiom (``((_ a . rest) ...)``), so it is
    bound to something that works both ways: ``'rest`` is the tail as a datum,
    and ``rest ...`` repeats it. Only a proper tail can be repeated; an improper
    one takes the ordinary path.
    """
    if is_nil(tail):
        return is_nil(form_tail)
    if isinstance(tail, Symbol) and tail is not UNDERSCORE and tail not in literals:
        items, rest = _split(form_tail)
        if is_nil(rest):
            binds[tail] = _Rest(items)
            return True
    return _match(tail, form_tail, literals, binds)


class _Seq(list):
    """A binding produced by ``...``: one entry per repeated match."""


class _Rest(_Seq):
    """A binding produced by a dotted tail: the forms after the fixed ones.

    Like ``_Seq`` it repeats (``rest ...``), but unlike ``_Seq`` it is also
    usable *plainly* — ``'rest`` is the tail as a datum rather than the
    "used without a matching ``...``" error — because a dotted pattern is the
    idiom for a variadic macro.
    """


# --------------------------------------------------------------------------- #
#  Instantiation (with hygiene)                                                #
# --------------------------------------------------------------------------- #

def _instantiate(template: Any, binds: dict, scope: dict, rules: SyntaxRules) -> Any:
    if isinstance(template, Symbol):
        if template in binds:
            value = binds[template]
            if isinstance(value, _Seq):
                if isinstance(value, _Rest):
                    return make_list(list(value))
                raise LispSyntaxError(
                    f"{rules.name}: '{template}' used without a matching '...'"
                )
            return value
        return _hygienic(template, scope, rules)
    if is_nil(template):
        return NIL
    if isinstance(template, Vector):
        return Vector(
            _walk_items(
                list(template.items),
                binds,
                lambda item, b: _instantiate(item, b, scope, rules),
            )
        )
    if isinstance(template, (list, Pair)):
        items, tail = _split(template)
        head = items[0] if items else None
        if head is LAMBDA:
            return _instantiate_lambda(items, binds, scope, rules)
        if head is LET or head is LET_STAR or head is LETREC:
            return _instantiate_let(items, binds, scope, rules)
        out = _walk_items(
            items, binds, lambda item, b: _instantiate(item, b, scope, rules)
        )
        new_tail = NIL if is_nil(tail) else _instantiate(tail, binds, scope, rules)
        return from_cells(out, new_tail) if not is_nil(new_tail) else make_list(out)
    return template


def _walk_items(items: list, binds: dict, build: Any) -> list:
    """Instantiate *items*, expanding each ``...`` into one item per iteration.

    Ellipses may *stack*: ``x ... ...`` descends one level per ``...``, so a
    doubly-repeated pattern variable can be flattened (``(list x ... ...)``) as
    well as kept nested (``(list (list x ...) ...)``).
    """
    out: list = []
    i = 0
    while i < len(items):
        item = items[i]
        depth = 0
        while i + 1 + depth < len(items) and items[i + 1 + depth] is ELLIPSIS:
            depth += 1
        if depth == 0:
            out.append(build(item, binds))
            i += 1
            continue
        # Repeat only over the sequences this subpattern actually uses, so one
        # clause's ellipsis never dictates another's length.
        repeated = [v for v in _vars_in(item) if isinstance(binds.get(v), _Seq)]
        if not repeated:
            raise LispSyntaxError("syntax-rules: '...' repeats nothing")
        for projected in _descend(binds, repeated, depth):
            out.append(build(item, projected))
        i += depth + 1
    return out


def _descend(binds: dict, names: list, depth: int) -> Any:
    """Yield one binding set per leaf, *depth* levels into the *names*.

    Every name must be a ``_Seq`` at every level reached, and all the names
    must agree on their length there — the two malformed cases a template can
    write and R7RS leaves to the implementation to report.
    """
    def rec(current: dict, level: int) -> Any:
        seqs = [current[name] for name in names]
        for seq in seqs:
            if not isinstance(seq, _Seq):
                raise LispSyntaxError(
                    "syntax-rules: too many '...' for this pattern variable"
                )
        length = len(seqs[0])
        if any(len(seq) != length for seq in seqs):
            raise LispSyntaxError("syntax-rules: '...' has mismatched lengths")
        for index in range(length):
            picked = {name: current[name][index] for name in names}
            if level == depth:
                row = dict(binds)
                row.update(picked)
                yield row
            else:
                yield from rec(picked, level + 1)

    yield from rec(binds, 1)


def _vars_in(form: Any) -> list:
    """Every symbol occurring in *form* (as a template fragment)."""
    found: list = []
    stack = [form]
    while stack:
        node = stack.pop()
        if isinstance(node, Symbol):
            found.append(node)
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, Vector):
            stack.extend(node.items)
        elif isinstance(node, Pair):
            stack.append(node.car)
            stack.append(node.cdr)
    return found


def _hygienic(name: Symbol, scope: dict, rules: SyntaxRules) -> Symbol:
    if name in scope:
        return scope[name]
    binding = _find(rules.env, name)
    if binding is not None:
        return _alias(name, rules)
    return name


def _alias(name: Symbol, rules: SyntaxRules) -> Symbol:
    alias = rules.aliases.get(name)
    if alias is None:
        alias = _fresh(str(name))
        rules.aliases[name] = alias
        root = _root(rules.env)
        root.define(alias, rules.env.lookup(name))
    return alias


def _instantiate_lambda(
    items: list, binds: dict, scope: dict, rules: SyntaxRules
) -> Any:
    if len(items) < 3:
        raise LispSyntaxError("syntax-rules: (lambda params body...) in a template")
    params, rest = _split(items[1])
    inner = dict(scope)
    new_params = _walk_items(
        params, binds, lambda p, b: _binder(p, b, inner, rules)
    )
    params_tail = NIL
    if not is_nil(rest):
        params_tail = _binder(rest, binds, inner, rules)
    param_form = (
        from_cells(new_params, params_tail) if not is_nil(params_tail) else make_list(new_params)
    )
    body = [_instantiate(form, binds, inner, rules) for form in items[2:]]
    return make_list([LAMBDA, param_form, *body])


def _instantiate_let(
    items: list, binds: dict, scope: dict, rules: SyntaxRules
) -> Any:
    head = items[0]
    if head is LET and len(items) >= 3 and isinstance(items[1], Symbol):
        name = items[1]  # named let: the loop name is bound in the body
        bindings_form = items[2]
        body_forms = items[3:]
        inner = dict(scope)
        loop_name = _binder(name, binds, inner, rules)
        bindings = _instantiate_bindings(
            bindings_form, binds, scope, inner, rules, sequential=False
        )
        body = [_instantiate(form, binds, inner, rules) for form in body_forms]
        return make_list([LET, loop_name, bindings, *body])
    if len(items) < 3:
        raise LispSyntaxError("syntax-rules: (let bindings body...) in a template")
    bindings_form = items[1]
    body_forms = items[2:]
    inner = dict(scope)
    if head is LETREC:
        bindings = _instantiate_letrec(bindings_form, binds, inner, rules)
    else:
        bindings = _instantiate_bindings(
            bindings_form, binds, scope, inner, rules, sequential=(head is LET_STAR)
        )
    body = [_instantiate(form, binds, inner, rules) for form in body_forms]
    return make_list([head, bindings, *body])


def _instantiate_letrec(
    bindings_form: Any, binds: dict, inner: dict, rules: SyntaxRules
) -> Any:
    """``letrec``: every binder is in scope for every init, so bind names first."""
    raw, _tail = _split(bindings_form) if not is_nil(bindings_form) else ([], NIL)
    names = _walk_items(raw, binds, lambda b, bd: _letrec_part(b, bd, inner, rules)[0])
    inits = _walk_items(raw, binds, lambda b, bd: _letrec_part(b, bd, inner, rules)[1])
    return make_list([make_list([n, i]) for n, i in zip(names, inits)])


def _letrec_part(
    binding: Any, binds: dict, inner: dict, rules: SyntaxRules
) -> tuple:
    pair, _ = _split(binding)
    if len(pair) != 2:
        built = _instantiate(binding, binds, inner, rules)
        return built, built
    return _binder(pair[0], binds, inner, rules), _instantiate(
        pair[1], binds, inner, rules
    )


def _instantiate_bindings(
    bindings_form: Any,
    binds: dict,
    outer: dict,
    inner: dict,
    rules: SyntaxRules,
    sequential: bool,
) -> Any:
    raw, _tail = _split(bindings_form) if not is_nil(bindings_form) else ([], NIL)
    return make_list(
        _walk_items(
            raw,
            binds,
            lambda binding, b: _one_binding(binding, b, outer, inner, rules, sequential),
        )
    )


def _one_binding(
    binding: Any,
    binds: dict,
    outer: dict,
    inner: dict,
    rules: SyntaxRules,
    sequential: bool,
) -> Any:
    pair, _ = _split(binding)
    if len(pair) != 2:
        return _instantiate(binding, binds, inner, rules)
    # The initialiser runs in the *outer* scope (or, for let*, the scope built
    # so far); the binder is renamed in the inner scope.
    init_scope = inner if sequential else outer
    init = _instantiate(pair[1], binds, init_scope, rules)
    name = _binder(pair[0], binds, inner, rules)
    return make_list([name, init])


def _binder(symbol: Any, binds: dict, scope: dict, rules: SyntaxRules) -> Any:
    if isinstance(symbol, Symbol):
        if symbol in binds:
            return binds[symbol]  # a pattern variable stands for the caller's name
        existing = scope.get(symbol)
        if existing is not None:
            return existing  # already renamed in this scope: keep the same name
        fresh = _fresh(str(symbol))
        scope[symbol] = fresh
        return fresh
    return _instantiate(symbol, binds, scope, rules)


# --------------------------------------------------------------------------- #
#  Small helpers                                                               #
# --------------------------------------------------------------------------- #

def _fresh(name: str) -> Symbol:
    global _counter
    _counter += 1
    return intern(f"{name}#h{_counter}")


def _split(form: Any) -> tuple[list, Any]:
    """A list or pair chain as ``([items...], tail)``."""
    if is_nil(form):
        return [], NIL
    if isinstance(form, list):
        return list(form), NIL
    if isinstance(form, Pair):
        items: list = []
        node: Any = form
        while isinstance(node, Pair):
            items.append(node.car)
            node = node.cdr
        return items, node
    raise LispSyntaxError("syntax-rules: a list was expected")


def _find(env: Environment, name: Symbol) -> Any:
    return env.find(name)


def _root(env: Environment) -> Environment:
    while env.parent is not None:
        env = env.parent
    return env


def _equal_literal(a: Any, b: Any) -> bool:
    from .evaluator import equal

    return equal(a, b)
