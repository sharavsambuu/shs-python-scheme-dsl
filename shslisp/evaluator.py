"""The evaluator — the heart of the language.

``evaluate`` is a **trampoline**: instead of recursing for the last
expression of a body it rebinds ``expr``/``env`` and loops. That single
decision is what makes recursive Lisp programs work in a host that has no
tail-call elimination of its own — a tail call costs no Python stack frame,
so ``(loop 1000000)`` runs in constant stack.

Everything else follows from the reader's quote expansion:

* special forms are matched **before** their head is evaluated (``if`` must
  not evaluate both branches; ``define`` must not evaluate its name);
* a macro is recognised by looking its head up *unevaluated*, expanded, and
  the loop continues — the expanded form is then compiled normally;
* an application either calls a primitive, or rebinds ``env`` to a closure's
  scope and loops with the body (a tail call), or applies a closure
  non-tail (through :func:`apply_procedure`).
"""
from __future__ import annotations

import sys
import threading
from fractions import Fraction
from typing import Any, List, Optional

from .env import Environment
from .errors import (
    LispArityError,
    LispBudgetError,
    LispError,
    LispRaise,
    LispRecursionError,
    LispSyntaxError,
    LispTypeError,
)
from .reader import (
    DOT,
    QUASIQUOTE,
    QUOTE,
    UNQUOTE,
    UNQUOTE_SPLICING,
)
from .types import (
    NIL,
    ByteVector,
    Char,
    Closure,
    Complex,
    ErrorObject,
    Macro,
    Pair,
    Primitive,
    Record,
    RecordType,
    Srfi160Vector,
    Srfi19Date,
    Srfi19Time,
    Symbol,
    SyntaxRules,
    Tagged,
    Values,
    Vector,
    Keyword,
    from_cells,
    intern,
    is_nil,
    is_true,
    list_to_python,
    make_list,
    tag_cells,
)

# --------------------------------------------------------------------------- #
#  The stack budget                                                            #
# --------------------------------------------------------------------------- #

#: How many nested evaluations a program may go before the interpreter raises
#: :class:`~shslisp.errors.LispRecursionError`. Tail calls are flat (the
#: trampoline loops), so this bounds argument-position nesting and non-tail
#: recursion — and it is exactly one unit per non-tail Lisp call, so it reads
#: directly as "a million calls deep". Past that a program still gets a clean
#: Lisp error, never the host's: a runaway recursion ends, it does not crash.
DEPTH_LIMIT = 1_000_000

#: Roughly how many Python frames one unit of depth costs; used to size the
#: host stack once, so ``DEPTH_LIMIT`` is reached before Python's own limit is.
_FRAMES_PER_CALL = 4

#: How many trampoline steps one root evaluation may spend. The companion
#: backstop to :data:`DEPTH_LIMIT`: tail-position loops are flat, so an
#: infinite ``(let loop () (force))`` costs no depth — but it must still end,
#: with a Lisp error, not as a hang. The budget is *per root call* (one hook
#: call, one ``lisp run`` program, one entry from a test), so a program whose
#: legitimate work needs hundreds of thousands of steps passes while an
#: endless loop dies at 5,000,000 — and is tunable in an embedder the way
#: DEPTH_LIMIT is. One step is one trampoline transition — a literal, a tail
#: jump, one special-form dispatch — so a simple tail loop spends about five
#: per iteration: the default bounds such a loop at roughly a million
#: iterations, and a host that needs more raises the budget.
STEPS_BUDGET = 5_000_000

#: How many macro expansions ``macroexpand`` will take before it declares the
#: macro divergent. It is a *separate* ceiling from :data:`STEPS_BUDGET` because
#: expansion runs outside the trampoline: a template that expands to itself
#: would spin in Python, which no step charge can see and no depth check can
#: catch. Small on purpose — real chains are a handful of steps deep.
MACROEXPAND_LIMIT = 1_000

#: Depth and step counters live per thread. An embedder may run two programs on
#: two threads; a shared counter would let one program's depth and step budget
#: (and its root-reset) corrupt the other's. The root budget object is fetched
#: once per ``evaluate`` and threaded through ``_run`` so the per-step charge
#: stays one attribute increment, not a thread-local lookup per trampoline step.
class _Budget:
    __slots__ = ("steps", "depth")

    def __init__(self) -> None:
        self.steps = 0
        self.depth = 0


_local = threading.local()
_sized_for = None


def _ensure_stack() -> None:
    """Raise Python's recursion limit so ``DEPTH_LIMIT`` Lisp calls fit.

    Re-runs when ``DEPTH_LIMIT`` changes, so a test (or an embedder) that tunes
    the budget gets a host stack sized for the budget it now has — and lowering
    the budget never lowers the host limit, only leaves it high enough.
    """
    global _sized_for
    if _sized_for == DEPTH_LIMIT:
        return
    needed = DEPTH_LIMIT * _FRAMES_PER_CALL + 1000
    if sys.getrecursionlimit() < needed:
        sys.setrecursionlimit(needed)
    _sized_for = DEPTH_LIMIT


# --------------------------------------------------------------------------- #
#  Special-form heads, interned once                                           #
# --------------------------------------------------------------------------- #

IF = intern("if")
DEFINE = intern("define")
SET = intern("set!")
LAMBDA = intern("lambda")
LET = intern("let")
LET_STAR = intern("let*")
LETREC = intern("letrec")
LETREC_STAR = intern("letrec*")
CASE_LAMBDA = intern("case-lambda")
BEGIN = intern("begin")
COND = intern("cond")
WHEN = intern("when")
UNLESS = intern("unless")
AND = intern("and")
OR = intern("or")
DEFMACRO = intern("defmacro")
CASE = intern("case")
ELSE = intern("else")
ARROW = intern("=>")
GUARD = intern("guard")
LET_VALUES = intern("let-values")
LET_STAR_VALUES = intern("let*-values")
DEFINE_VALUES = intern("define-values")
DEFINE_SYNTAX = intern("define-syntax")
LET_SYNTAX = intern("let-syntax")
LETREC_SYNTAX = intern("letrec-syntax")
MATCH = intern("match")
#: The project's tag-dispatch matcher, renamed so ``match`` can be SRFI 241.
VARIANT_MATCH = intern("variant-match")
DEFINE_VARIANT = intern("define-variant")
DEFINE_RECORD_TYPE = intern("define-record-type")
COND_EXPAND = intern("cond-expand")
INCLUDE = intern("include")
INCLUDE_CI = intern("include-ci")
IMPORT = intern("import")
DEFINE_LIBRARY = intern("define-library")
SYNTAX_ERROR = intern("syntax-error")
UNDERSCORE = intern("_")

_SPECIAL_FORMS = frozenset(
    {
        QUOTE, QUASIQUOTE, IF, DEFINE, SET, LAMBDA, LET, LET_STAR, LETREC,
        LETREC_STAR, CASE_LAMBDA, BEGIN, COND, WHEN, UNLESS, AND, OR, DEFMACRO,
        CASE, GUARD, LET_VALUES, LET_STAR_VALUES, DEFINE_VALUES, DEFINE_SYNTAX,
        LET_SYNTAX, LETREC_SYNTAX, MATCH, DEFINE_VARIANT, DEFINE_RECORD_TYPE,
        COND_EXPAND, INCLUDE, INCLUDE_CI, IMPORT, DEFINE_LIBRARY, SYNTAX_ERROR,
    }
)


# --------------------------------------------------------------------------- #
#  Declared variants — the closed sets ``match`` refuses to guess at            #
# --------------------------------------------------------------------------- #
#
# `define-variant` registers what it declares so a non-exhaustive `match` can
# *name* the cases it was given and the tag it did not handle. That is the whole
# difference between typed control flow and a `cond` that falls through: the
# refusal says "expected ok or err", not "no default".
#
# The registry is global (like the interned symbol table) because a tag's
# meaning is not lexical: `result?` must answer the same way in any scope.

_VARIANTS: dict = {}       #: union name -> (tag, ...)
_TAG_UNIONS: dict = {}     #: tag -> the union that declared it


def variant_tags(union: Any) -> Any:
    """The tags a declared union lists, or ``None`` if it was never declared."""
    return _VARIANTS.get(union)


def variant_of(tag: Any) -> Any:
    """The union that declared *tag*, or ``None``."""
    return _TAG_UNIONS.get(tag)


# --------------------------------------------------------------------------- #
#  Public entry points                                                         #
# --------------------------------------------------------------------------- #

def evaluate(expr: Any, env: Environment) -> Any:
    """Evaluate one form in *env*.

    Two budgets bound a program's runaway costs, mirroring the shape a
    self-hosted runtime must own:

    * :data:`DEPTH_LIMIT` — *nested* evaluation: argument lists and non-tail
      recursion. Tail calls cost no host stack, so this reads directly as
      "how deep"; the raise is a :class:`~shslisp.errors.LispRecursionError`.
    * :data:`STEPS_BUDGET` — *work*: every trampoline step each root
      evaluation spends. An infinite tail loop is flat and depth-free but
      must still end, so the raise is a :class:`~shslisp.errors.LispBudgetError`.
      The counter is per thread (and per root call): nested evaluations inside
      one walk share its budget, and a fresh root (depth returning to zero)
      resets it, without two threads stepping on each other's count.
    """
    _ensure_stack()
    budget = getattr(_local, "budget", None)
    if budget is None or budget.depth == 0:
        budget = _Budget()      # a fresh root evaluation — its own budget
        _local.budget = budget
    budget.depth += 1
    try:
        if budget.depth > DEPTH_LIMIT:
            raise LispRecursionError(
                f"evaluation nested deeper than {DEPTH_LIMIT} frames "
                "(a non-tail recursion? try a tail call or a loop)"
            )
        return _run(expr, env, budget)
    except RecursionError:
        raise LispRecursionError("the host stack ran out") from None
    finally:
        budget.depth -= 1


def _charge(budget: _Budget) -> None:
    """One trampoline step, against the root evaluation's budget.

    Charged at the head of :func:`_run`'s loop, so every shape of progress —
    a tail transition, a literal, an application — costs exactly one, and the
    special-form steps a deeper :func:`evaluate` reaches funnel back through
    this same loop. Past the budget the raise is a Lisp error on purpose: a
    runaway program ends like any other error in the program's host, never a
    crash inside the interpreter.
    """
    budget.steps += 1
    if budget.steps > STEPS_BUDGET:
        raise LispBudgetError(
            f"one evaluation spent more than {STEPS_BUDGET:,} steps — an "
            "endless loop? (tail calls cost no depth, so only this budget "
            "can see it)"
        )


def _run(expr: Any, env: Environment, budget: _Budget) -> Any:
    """The trampoline: evaluate *expr*, looping in tail position."""
    while True:
        _charge(budget)
        if isinstance(expr, Symbol):
            value = env.lookup(expr)
            if isinstance(value, (Macro, SyntaxRules)):
                raise LispTypeError(
                    f"a macro is not a value: {expr} can only head a form"
                )
            return value

        if isinstance(expr, Pair):
            # A dotted form such as ``(begin . 1)`` is not code: every
            # application and special form is a proper list. Treating it as
            # self-evaluating data would silently turn a typo into a value.
            raise LispSyntaxError("improper list in expression position")

        if not isinstance(expr, list):
            return expr  # a number, string, boolean, or NIL literal

        if not expr:
            return NIL

        head = expr[0]

        if isinstance(head, Symbol) and head not in _SPECIAL_FORMS:
            macro = _find_macro(env, head)
            if macro is not None:
                if isinstance(macro, SyntaxRules):
                    from .syntax import expand as _expand_syntax

                    expr = _expand_syntax(macro, expr)
                else:
                    expr = _expand_macro(macro, expr[1:])
                continue

        if isinstance(head, Symbol):
            if head is QUOTE:
                _check_arity("quote", expr, 1)
                return expr[1]
            if head is QUASIQUOTE:
                _check_arity("quasiquote", expr, 1)
                return quasiquote(expr[1], env)
            if head is IF:
                expr = _step_if(expr, env)
                continue
            if head is BEGIN:
                if len(expr) == 1:
                    return NIL
                for form in expr[1:-1]:
                    evaluate(form, env)
                expr = expr[-1]
                continue
            if head is DEFINE:
                return _eval_define(expr, env)
            if head is DEFMACRO:
                return _eval_defmacro(expr, env)
            if head is SET:
                _check_arity("set!", expr, 2)
                value = evaluate(expr[2], env)
                env.set(expr[1], value)
                return value
            if head is LAMBDA:
                if len(expr) < 3:
                    raise LispSyntaxError(
                        "lambda: expected (lambda params body...)"
                    )
                params, rest = _parse_params(expr[1], "lambda")
                return Closure(params, rest, expr[2:], env, "lambda")
            if head is LET:
                expr = _step_let(expr)
                continue
            if head is LET_STAR:
                expr = _step_let_star(expr)
                continue
            if head is LETREC:
                expr = _step_letrec(expr, "letrec")
                continue
            if head is LETREC_STAR:
                expr = _step_letrec(expr, "letrec*")
                continue
            if head is CASE_LAMBDA:
                return _eval_case_lambda(expr, env)
            if head is COND:
                result = _step_cond(expr, env)
                if isinstance(result, _Result):
                    return result.value
                expr = result
                continue
            if head is WHEN:
                expr = _step_when(expr, env, negate=False)
                continue
            if head is UNLESS:
                expr = _step_when(expr, env, negate=True)
                continue
            if head is AND:
                result = _step_and(expr, env)
                if result is not _TAIL:
                    return result
                expr = expr[-1]
                continue
            if head is OR:
                result = _step_or(expr, env)
                if result is not _TAIL:
                    return result
                expr = expr[-1]
                continue
            if head is CASE:
                result = _step_case(expr, env)
                if isinstance(result, _Result):
                    return result.value
                expr = result
                continue
            if head is MATCH:
                result = _srfi241_match(expr, env)
                if isinstance(result, _Result):
                    return result.value
                expr = result
                continue
            if head is VARIANT_MATCH:
                result = _step_match(expr, env)
                if isinstance(result, _Result):
                    return result.value
                expr = result
                continue
            if head is _SRFI241_QQ:
                return _srfi241_qq(expr, env)
            if head is DEFINE_VARIANT:
                return _eval_define_variant(expr, env)
            if head is DEFINE_RECORD_TYPE:
                return _eval_define_record_type(expr, env)
            if head is COND_EXPAND:
                return _eval_cond_expand(expr, env)
            if head is INCLUDE:
                return _eval_include(expr, env, fold_case=False)
            if head is INCLUDE_CI:
                return _eval_include(expr, env, fold_case=True)
            if head is IMPORT:
                from .library import eval_import

                return eval_import(expr, env)
            if head is DEFINE_LIBRARY:
                from .library import eval_define_library

                return eval_define_library(expr, env)
            if head is SYNTAX_ERROR:
                return _eval_syntax_error(expr, env)
            if head is GUARD:
                return _eval_guard(expr, env)
            if head is LET_VALUES:
                return _eval_let_values(expr, env, sequential=False)
            if head is LET_STAR_VALUES:
                return _eval_let_values(expr, env, sequential=True)
            if head is DEFINE_VALUES:
                return _eval_define_values(expr, env)
            if head is DEFINE_SYNTAX:
                from .syntax import eval_define_syntax

                return eval_define_syntax(expr, env)
            if head is LET_SYNTAX or head is LETREC_SYNTAX:
                from .syntax import eval_let_syntax

                return eval_let_syntax(expr, env, recursive=head is LETREC_SYNTAX)

        # An application.
        proc = evaluate(head, env)
        args = [evaluate(arg, env) for arg in expr[1:]]
        if isinstance(proc, (Macro, SyntaxRules)):
            raise LispTypeError("a macro is not a value; it can only be applied")
        if isinstance(proc, Closure):
            env = _bind(proc, args)
            expr = _body_form(proc.body)
            continue
        return apply_procedure(proc, args)


def evaluate_program(forms: List[Any], env: Environment) -> Any:
    """Evaluate a sequence of forms; return the last value (``NIL`` if none)."""
    result: Any = NIL
    for form in forms:
        result = evaluate(form, env)
    return result


def apply_procedure(proc: Any, args: List[Any]) -> Any:
    """Apply *proc* to already-evaluated *args* (the non-tail path)."""
    if isinstance(proc, Primitive):
        try:
            return proc.fn(*args)
        except LispError:
            raise
        except (TypeError, ValueError, IndexError, KeyError) as exc:
            raise LispTypeError(f"{proc.name}: {exc}") from exc
    if isinstance(proc, Closure):
        return _apply_closure(proc, args)
    raise LispTypeError(f"not a procedure: {type(proc).__name__}")


def _apply_closure(proc: Closure, args: List[Any]) -> Any:
    """Call a closure non-tail (the depth budget is charged in :func:`evaluate`)."""
    return evaluate(_body_form(proc.body), _bind(proc, args))


# --------------------------------------------------------------------------- #
#  Parameter lists and binding                                                 #
# --------------------------------------------------------------------------- #

def _parse_params(form: Any, who: str) -> tuple[list[Symbol], Optional[Symbol]]:
    """Split a parameter list into fixed params and an optional rest param.

    ``(a b)`` → ``([a, b], None)``; ``(a b . rest)`` → ``([a, b], rest)``;
    a bare symbol → ``([], sym)``. A dotted list arrives as a :class:`Pair`
    chain from the reader, so the walk here is the one place a Lisp decides a
    ``.`` means "rest" — the syntactically proper place to decide it.
    """
    if isinstance(form, Symbol):
        return [], form
    if is_nil(form):
        return [], None
    if isinstance(form, Pair):
        head: list = []
        node: Any = form
        while isinstance(node, Pair):
            head.append(node.car)
            node = node.cdr
        if not is_nil(node) and not isinstance(node, Symbol):
            raise LispSyntaxError(f"{who}: rest parameter must be a symbol")
        if not all(isinstance(p, Symbol) for p in head):
            raise LispSyntaxError(f"{who}: parameters must be symbols")
        return head, (node if isinstance(node, Symbol) else None)
    if not isinstance(form, list):
        raise LispSyntaxError(f"{who}: bad parameter list")
    if DOT in form:
        dot = form.index(DOT)
        if dot != len(form) - 2:
            raise LispSyntaxError(f"{who}: '.' must precede one final parameter")
        rest = form[-1]
        if not isinstance(rest, Symbol):
            raise LispSyntaxError(f"{who}: rest parameter must be a symbol")
        head = form[:dot]
        if not all(isinstance(p, Symbol) for p in head):
            raise LispSyntaxError(f"{who}: parameters must be symbols")
        return list(head), rest
    if not all(isinstance(p, Symbol) for p in form):
        raise LispSyntaxError(f"{who}: parameters must be symbols")
    return list(form), None


def _bind(proc: Closure, args: List[Any]) -> Environment:
    """A fresh frame for *proc* with *args* bound to its parameters."""
    local = Environment(parent=proc.env)
    fixed = len(proc.params)
    if proc.rest is None:
        if len(args) != fixed:
            raise LispArityError(proc.name, str(fixed), len(args))
    elif len(args) < fixed:
        raise LispArityError(proc.name, f"at least {fixed}", len(args))

    for name, value in zip(proc.params, args):
        local.define(name, value)
    if proc.rest is not None:
        local.define(proc.rest, make_list(args[fixed:]))
    return local


def _body_form(body: List[Any]) -> Any:
    """A body of forms as one form: the single expression, or a ``begin``."""
    if not body:
        return NIL
    if len(body) == 1:
        return body[0]
    return [BEGIN, *body]


# --------------------------------------------------------------------------- #
#  Macros and quasiquotation                                                   #
# --------------------------------------------------------------------------- #

def _find_macro(env: Environment, name: Symbol) -> Any:
    frame = env.find(name)
    if frame is None:
        return None
    value = frame.vars[name]
    return value if isinstance(value, (Macro, SyntaxRules)) else None


def _expand_macro(macro: Macro, raw_args: List[Any]) -> Any:
    """Run *macro* on the raw argument forms; the result is the new code."""
    params, rest = macro.params, macro.rest
    local = Environment(parent=macro.env)
    fixed = len(params)
    if rest is None and len(raw_args) != fixed:
        raise LispArityError(macro.name, str(fixed), len(raw_args))
    if rest is not None and len(raw_args) < fixed:
        raise LispArityError(macro.name, f"at least {fixed}", len(raw_args))
    for name, value in zip(params, raw_args):
        local.define(name, value)
    if rest is not None:
        local.define(rest, make_list(raw_args[fixed:]))
    return evaluate(_body_form(macro.body), local)


def macroexpand(expr: Any, env: Environment, *, once: bool = False) -> Any:
    """Rewrite *expr* while its head names a macro; return the rewritten form.

    ``once=True`` is ``macroexpand-1`` — one step, whatever comes out. The
    default is ``macroexpand``: it keeps expanding while the head is a macro,
    which is what a macro author reaches for when a template did not do what
    they expected. A head that is not a macro (a variable, a special form, a
    lambda) stops the walk and is returned unchanged.

    The walk is *bounded*: a macro that expands to itself would otherwise spin
    forever, so it stops by name after :data:`MACROEXPAND_LIMIT` steps rather
    than hanging a REPL.
    """
    steps = 0
    while (
        isinstance(expr, list)
        and expr
        and isinstance(expr[0], Symbol)
        and expr[0] not in _SPECIAL_FORMS
    ):
        macro = _find_macro(env, expr[0])
        if macro is None:
            break
        if isinstance(macro, SyntaxRules):
            from .syntax import expand as _expand_syntax

            expr = _expand_syntax(macro, expr)
        else:
            expr = _expand_macro(macro, expr[1:])
        if once:
            break
        steps += 1
        if steps >= MACROEXPAND_LIMIT:
            raise LispBudgetError(
                f"macroexpand: {MACROEXPAND_LIMIT} expansions without reaching "
                f"a non-macro head — is {expr[0] if expr else '?'} divergent?"
            )
    return expr


def quasiquote(expr: Any, env: Environment, depth: int = 1) -> Any:
    """Build a template: ``unquote`` evaluates, ``unquote-splicing`` splices.

    Nested quasiquotes raise the depth and an ``unquote`` lowers it, so only
    the innermost matching ``unquote`` fires — the rule that lets a macro
    *build* a macro, and the one that makes `` `(1 ,,(+ 1 2)) `` answer
    ``(1 3)`` (the outer comma spends the depth the inner one needs).
    """
    if isinstance(expr, Pair):
        items, node = [], expr
        while isinstance(node, Pair):
            items.append(node.car)
            node = node.cdr
        out: list = []
        for item in items:
            if _is_splice(item, depth):
                out.extend(list_to_python(evaluate(item[1], env)))
            else:
                out.append(
                    quasiquote(item, env, depth)
                    if isinstance(item, (list, Pair))
                    else item
                )
        tail = quasiquote(node, env, depth) if isinstance(node, (list, Pair)) else node
        return from_cells(out, tail)
    if isinstance(expr, list):
        if expr and expr[0] is UNQUOTE:
            if depth == 1:
                return _eval_unquoted(expr[1], env)
            return [UNQUOTE, quasiquote(expr[1], env, depth - 1)]
        if expr and expr[0] is QUASIQUOTE:
            return [QUASIQUOTE, quasiquote(expr[1], env, depth + 1)]

        out = []
        for item in expr:
            if _is_splice(item, depth):
                out.extend(list_to_python(evaluate(item[1], env)))
            else:
                out.append(
                    quasiquote(item, env, depth)
                    if isinstance(item, (list, Pair))
                    else item
                )
        return make_list(out)
    return expr


def _eval_unquoted(template: Any, env: Environment) -> Any:
    """The template an ``unquote`` fires with, at depth zero.

    Usually it is an ordinary expression and simply evaluates. When the
    template is itself an ``unquote`` — a double comma, ``,,x`` inside one
    quasiquote — the outer comma has spent the depth the inner one needs, so
    by R7RS's depth arithmetic (a substitution happens when the depth reaches
    zero) the inner one fires *now*: `` `(1 ,,(+ 1 2)) `` is ``(1 3)``, not an
    error about evaluating ``(unquote (+ 1 2))`` as code. An
    ``unquote-splicing`` at depth zero has no list to splice into at the fire
    site, so it evaluates to its list as one value.
    """
    if (
        isinstance(template, list)
        and len(template) == 2
        and (template[0] is UNQUOTE or template[0] is UNQUOTE_SPLICING)
    ):
        return evaluate(template[1], env)
    return evaluate(template, env)


def _is_splice(item: Any, depth: int) -> bool:
    """Is *item* an active ``,@`` splice at this quasiquote depth?"""
    return (
        depth == 1
        and isinstance(item, list)
        and bool(item)
        and item[0] is UNQUOTE_SPLICING
    )


# --------------------------------------------------------------------------- #
#  Special-form helpers                                                        #
# --------------------------------------------------------------------------- #

def _check_arity(name: str, expr: list, n: int) -> None:
    if len(expr) - 1 != n:
        raise LispArityError(name, str(n), len(expr) - 1)


def _step_if(expr: list, env: Environment) -> Any:
    if len(expr) not in (3, 4):
        raise LispSyntaxError("if: expected (if test then [else])")
    if is_true(evaluate(expr[1], env)):
        return expr[2]
    return expr[3] if len(expr) == 4 else NIL


def _eval_define(expr: list, env: Environment) -> Any:
    if len(expr) < 3:
        raise LispSyntaxError("define: expected (define name value) or (define (name ...) body...)")
    target = expr[1]
    if isinstance(target, Symbol):  # (define name value)
        if len(expr) != 3:
            raise LispSyntaxError("define: too many forms after a name")
        env.define(target, evaluate(expr[2], env))
        return target
    # (define (name params...) body...) — params may be a dotted Pair chain.
    name, param_form = _signature(target, "define")
    params, rest = _parse_params(param_form, str(name))
    env.define(name, Closure(params, rest, expr[2:], env, str(name)))
    return name


def _signature(target: Any, who: str) -> tuple[Symbol, Any]:
    """Split ``(name params...)`` — a list or a dotted pair — into name and form."""
    if isinstance(target, Pair):
        name, param_form = target.car, target.cdr
    elif isinstance(target, list) and target:
        name, param_form = target[0], make_list(target[1:])
    else:
        raise LispSyntaxError(f"{who}: bad target")
    if not isinstance(name, Symbol):
        raise LispSyntaxError(f"{who}: name must be a symbol")
    return name, param_form


def _eval_defmacro(expr: list, env: Environment) -> Any:
    if len(expr) < 3 or not isinstance(expr[1], (list, Pair)):
        raise LispSyntaxError("defmacro: expected (defmacro (name params...) body...)")
    name, param_form = _signature(expr[1], "defmacro")
    params, rest = _parse_params(param_form, str(name))
    env.define(name, Macro(params, rest, expr[2:], env, str(name)))
    return name


def _parse_bindings(raw: Any, who: str) -> list:
    """Validate a ``((name initializer) ...)`` binding list.

    The reader represents a proper list as a Python ``list`` and an improper
    one as a :class:`Pair`, so this is the one place a binding list's *shape*
    is checked. Every malformed case — a missing initializer, an extra form, a
    non-symbol name, a dotted list — becomes a :class:`LispSyntaxError`; none
    of them may reach the index-based expansion below and surface as a host
    ``IndexError``. An empty binding list is valid in every binding form.
    """
    if is_nil(raw):
        return []
    if isinstance(raw, Pair):
        raise LispSyntaxError(f"{who}: the binding list must be a proper list")
    if not isinstance(raw, list):
        raise LispSyntaxError(f"{who}: bad binding list")
    for binding in raw:
        if not isinstance(binding, list) or len(binding) != 2:
            raise LispSyntaxError(
                f"{who}: each binding must be (name initializer)"
            )
        if not isinstance(binding[0], Symbol):
            raise LispSyntaxError(f"{who}: a binding name must be a symbol")
    return list(raw)


def _step_let(expr: list) -> Any:
    """``let`` — including named ``let`` — becomes a lambda application.

    Compiling it away (rather than interpreting it) is what keeps a named
    ``let`` loop in constant stack: ``(let loop () ...)`` is just
    ``((lambda () ...))`` called through the trampoline.
    """
    if len(expr) < 3:
        raise LispSyntaxError("let: expected (let (bindings...) body...)")
    if isinstance(expr[1], Symbol):  # named let
        name = expr[1]
        bindings = _parse_bindings(expr[2], "let")
        names = [b[0] for b in bindings]
        inits = [b[1] for b in bindings]
        lam = [LAMBDA, make_list(names), *expr[3:]]
        return [LETREC, [[name, lam]], [name, *inits]]
    bindings = _parse_bindings(expr[1], "let")
    names = [b[0] for b in bindings]
    inits = [b[1] for b in bindings]
    return [make_list([LAMBDA, make_list(names), *expr[2:]]), *inits]


def _step_let_star(expr: list) -> Any:
    """``let*`` — each binding sees the previous ones, one nested ``let`` deep.

    The recursion must stay ``let*``: nesting a plain ``let`` of the *whole*
    remaining binding list would bind those names in parallel, so with three
    or more bindings a later initialiser could not see an earlier name.
    """
    if len(expr) < 3:
        raise LispSyntaxError("let*: expected (let* (bindings...) body...)")
    bindings = _parse_bindings(expr[1], "let*")
    if not bindings:
        return [LET, NIL, *expr[2:]]
    first, rest = bindings[0], bindings[1:]
    inner: Any = [LET_STAR, rest, *expr[2:]] if rest else _body_form(expr[2:])
    return [LET, [first], inner]


def _step_letrec(expr: list, who: str = "letrec") -> Any:
    """``letrec``/``letrec*`` — bind all names first, then assign.

    Pre-binding is what lets a closure in one initialiser refer to a name bound
    by another; assigning in order then gives ``letrec*``'s sequential
    visibility, which for this expansion is the same form. ``letrec`` in the
    standard leaves the initialisers' order unspecified, so compiling both to
    the sequential form is the honest superset.
    """
    if len(expr) < 3:
        raise LispSyntaxError(f"{who}: expected ({who} (bindings...) body...)")
    bindings = _parse_bindings(expr[1], who)
    names = [b[0] for b in bindings]
    blanks = [[n, NIL] for n in names]
    assigns = [[SET, b[0], b[1]] for b in bindings]
    return [LET, blanks, *assigns, *expr[2:]]


def _eval_case_lambda(expr: list, env: Environment) -> Any:
    """``case-lambda`` — one procedure, a different body per arity.

    Each clause becomes its own closure over the definition scope, and the
    procedure is a Python-side dispatcher: it counts the arguments it was
    handed and applies the first clause whose formals accept that count — a
    fixed clause exactly ``n``, a variadic clause (``(a b . rest)``) at least
    ``n``. The dispatch lives here rather than in an expansion that calls
    ``length``/``apply`` by name, which is what keeps the form *hygienic*: a
    caller's local binding of those helpers cannot change what ``case-lambda``
    means (the report's syntax is not up for capture). The dispatched clause
    runs through the same non-tail path the old expansion's ``apply`` did, so
    the depth budget sees one unit per dispatch, as before. Falling off the
    end raises the same condition ``(error ...)`` would — naming the count,
    never a silent #f.
    """
    if len(expr) < 2:
        raise LispSyntaxError("case-lambda: expected at least one clause")
    clauses: List[tuple[int, bool, Closure]] = []
    for clause in expr[1:]:
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("case-lambda: each clause is (formals body...)")
        params, rest = _parse_params(clause[0], "case-lambda")
        clauses.append(
            (
                len(params),
                rest is not None,
                Closure(params, rest, clause[1:], env, "lambda"),
            )
        )

    def dispatch(*args: Any) -> Any:
        count = len(args)
        for fixed, variadic, clause_closure in clauses:
            accepts = count >= fixed if variadic else count == fixed
            if accepts:
                return apply_procedure(clause_closure, list(args))
        raise LispRaise(
            ErrorObject(
                "case-lambda: no clause accepts this many arguments", [count]
            )
        )

    return Primitive("case-lambda", dispatch)


def _step_cond(expr: list, env: Environment) -> Any:
    for clause in expr[1:]:
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("cond: each clause is (test body...)")
        if clause[0] is ELSE:
            return NIL if len(clause) == 1 else _body_form(clause[1:])
        if len(clause) >= 3 and clause[1] is ARROW:
            value = evaluate(clause[0], env)
            if is_true(value):
                return _Result(apply_procedure(evaluate(clause[2], env), [value]))
            continue
        value = evaluate(clause[0], env)
        if is_true(value):
            if len(clause) == 1:
                # A test-only clause yields the test's own value. It was just
                # computed; hand it back as a result rather than making the
                # trampoline evaluate the test form a second time (which would
                # repeat every side effect).
                return _Result(value)
            return _body_form(clause[1:])
    return NIL


def _step_when(expr: list, env: Environment, negate: bool) -> Any:
    if len(expr) < 2:
        raise LispSyntaxError("when/unless: expected a test")
    truth = is_true(evaluate(expr[1], env))
    if truth is negate:
        return NIL
    return _body_form(expr[2:])


class _Tail:
    """Sentinel: ``and``/``or`` want the tail expression evaluated in place."""


_TAIL = _Tail()


class _Result:
    """A *computed value* handed back through the trampoline.

    ``cond``/``case`` with ``=>`` must call a procedure on a value that only
    exists at run time, so it cannot be spliced back into the code form the
    loop evaluates. Wrapping it keeps a returned list from being mistaken for
    code.
    """

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def _step_and(expr: list, env: Environment) -> Any:
    if len(expr) == 1:
        return True
    for form in expr[1:-1]:
        value = evaluate(form, env)
        if not is_true(value):
            return value
    return _TAIL


def _step_or(expr: list, env: Environment) -> Any:
    if len(expr) == 1:
        return False
    for form in expr[1:-1]:
        value = evaluate(form, env)
        if is_true(value):
            return value
    return _TAIL


def _step_case(expr: list, env: Environment) -> Any:
    if len(expr) < 2:
        raise LispSyntaxError("case: expected (case key clauses...)")
    # R7RS compares the key with each datum by ``eqv?``, not ``equal?``: the
    # exactness of a number is part of its identity, so ``(case 1 ...)`` must
    # not match a ``1.0`` clause. Imported lazily to keep the evaluator free of
    # a module-level cycle with ``builtins``.
    from .builtins import _eqv

    key = evaluate(expr[1], env)
    for clause in expr[2:]:
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("case: bad clause")
        datums = clause[0]
        if datums is ELSE:
            if len(clause) >= 3 and clause[1] is ARROW:
                return _Result(apply_procedure(evaluate(clause[2], env), [key]))
            return NIL if len(clause) == 1 else _body_form(clause[1:])
        if not isinstance(datums, list):
            raise LispSyntaxError("case: datum list expected")
        if any(_eqv(key, datum) for datum in datums):
            if len(clause) >= 3 and clause[1] is ARROW:
                return _Result(apply_procedure(evaluate(clause[2], env), [key]))
            return NIL if len(clause) == 1 else _body_form(clause[1:])
    return NIL


# --------------------------------------------------------------------------- #
#  Typed control flow: `define-variant` and `match`                            #
# --------------------------------------------------------------------------- #
#
# A *variant* is a closed set of tags, declared once. `match` destructures a
# value against patterns, and — crucially — refuses to fall through: with no
# matching clause and no `else`, it raises and *names* the value, its tag, and
# the cases the union declared. That is "typed" in the only sense this language
# can promise: the shape is declared, and a case you forgot is loud, never a
# silent default. (`cond` without a test would quietly yield `()`; this will not.)

def _eval_define_variant(expr: list, env: Environment) -> Any:
    """``(define-variant name (tag field...) ...)`` — declare a closed set.

    Defines, for each case:

    * the **constructor** ``tag`` (a procedure of exactly the named fields);
    * the **accessors** ``tag-field`` (each refuses a value on the wrong tag);

    and for the union: the **predicate** ``name?``. It also records the tags so
    ``match`` can report the set when a clause is missing.
    """
    if len(expr) < 3 or not isinstance(expr[1], Symbol):
        raise LispSyntaxError(
            "define-variant: expected (define-variant name (tag field...) ...)"
        )
    union = expr[1]
    cases: List[Any] = []
    seen: set = set()
    for clause in expr[2:]:
        if not isinstance(clause, list) or not clause or not isinstance(clause[0], Symbol):
            raise LispSyntaxError("define-variant: each case is (tag field ...)")
        tag = clause[0]
        if tag in seen:
            raise LispSyntaxError(f"define-variant: tag {tag} is declared twice")
        seen.add(tag)
        for field_name in clause[1:]:
            if not isinstance(field_name, Symbol):
                raise LispSyntaxError("define-variant: field names must be symbols")
        cases.append((tag, clause[1:]))
    _VARIANTS[union] = tuple(tag for tag, _ in cases)
    for tag, _ in cases:
        _TAG_UNIONS[tag] = union
    for tag, fields in cases:
        _define_variant_case(env, union, tag, fields)
    env.define(
        intern(f"{union}?"),
        Primitive(
            f"{union}?",
            lambda value, _union=union: (
                isinstance(value, Tagged) and _TAG_UNIONS.get(value.tag) is _union
            ),
        ),
    )
    return union


def _define_variant_case(env: Environment, union: Symbol, tag: Symbol, fields: List[Any]) -> None:
    """Install one case's constructor and its per-field accessors."""
    arity = len(fields)

    def construct(*args: Any, _tag: Symbol = tag, _arity: int = arity) -> Tagged:
        if len(args) != _arity:
            raise LispArityError(str(_tag), str(_arity), len(args))
        return Tagged(_tag, args)

    env.define(tag, Primitive(str(tag), construct))

    for index, field_name in enumerate(fields):
        accessor = intern(f"{tag}-{field_name}")

        def read(value: Any, _tag: Symbol = tag, _index: int = index, _name: str = str(accessor)) -> Any:
            if not (isinstance(value, Tagged) and value.tag is _tag):
                raise LispTypeError(
                    f"{_name}: expected a {_tag} {union}, got {_describe_value(value)}"
                )
            return value.fields[_index]

        env.define(accessor, Primitive(str(accessor), read))


def _eval_define_record_type(expr: list, env: Environment) -> Any:
    """``(define-record-type name (ctor field...) pred (field acc [mod])...)``.

    One generic :class:`~shslisp.types.Record` carries the type name, so a program
    declares its shape at run time. Fields are ordered by the field clauses,
    not by the constructor's argument list; a field the constructor does not
    mention starts as ``#f`` (the documented "unspecified" value) and can be
    set later only if its clause names a modifier.

    The type name is bound to a :class:`~shslisp.types.RecordType` descriptor, as
    R7RS asks; the constructor, predicate, accessors, and modifiers are bound
    beside it in the current environment.
    """
    if len(expr) < 4 or not isinstance(expr[1], Symbol):
        raise LispSyntaxError(
            "define-record-type: expected "
            "(define-record-type name (constructor field ...) predicate "
            "(field accessor [modifier]) ...)"
        )
    type_name = expr[1]

    constructor_spec = expr[2]
    if (
        not isinstance(constructor_spec, list)
        or not constructor_spec
        or not isinstance(constructor_spec[0], Symbol)
    ):
        raise LispSyntaxError(
            "define-record-type: constructor spec must be (name field ...)"
        )
    constructor_name = constructor_spec[0]
    constructor_fields = constructor_spec[1:]
    if any(not isinstance(field, Symbol) for field in constructor_fields):
        raise LispSyntaxError("define-record-type: constructor fields must be symbols")
    if len(set(constructor_fields)) != len(constructor_fields):
        raise LispSyntaxError(
            f"define-record-type: {constructor_name} names a field twice"
        )

    predicate_name = expr[3]
    if not isinstance(predicate_name, Symbol):
        raise LispSyntaxError("define-record-type: predicate must be a symbol")

    field_names: List[Symbol] = []
    accessors: List[tuple[Symbol, Symbol, Optional[Symbol]]] = []
    for clause in expr[4:]:
        if not isinstance(clause, list) or not 2 <= len(clause) <= 3:
            raise LispSyntaxError(
                "define-record-type: each field clause is "
                "(field accessor [modifier])"
            )
        field_name, accessor_name = clause[0], clause[1]
        modifier_name = clause[2] if len(clause) == 3 else None
        if not isinstance(field_name, Symbol) or not isinstance(accessor_name, Symbol):
            raise LispSyntaxError(
                "define-record-type: field and accessor names must be symbols"
            )
        if modifier_name is not None and not isinstance(modifier_name, Symbol):
            raise LispSyntaxError("define-record-type: modifier must be a symbol")
        if field_name in field_names:
            raise LispSyntaxError(
                f"define-record-type: field {field_name} is declared twice"
            )
        field_names.append(field_name)
        accessors.append((field_name, accessor_name, modifier_name))

    index_of = {field: index for index, field in enumerate(field_names)}
    for field in constructor_fields:
        if field not in index_of:
            raise LispSyntaxError(
                f"define-record-type: constructor names undeclared field {field}"
            )

    mutable = tuple(modifier is not None for _, _, modifier in accessors)
    record_type = RecordType(type_name, field_names)

    def construct(*args: Any) -> Record:
        if len(args) != len(constructor_fields):
            raise LispArityError(
                str(constructor_name), str(len(constructor_fields)), len(args)
            )
        values: list[Any] = [False] * len(field_names)
        for field, value in zip(constructor_fields, args):
            values[index_of[field]] = value
        return Record(type_name, values, mutable)

    def is_record(value: Any) -> bool:
        return isinstance(value, Record) and value.type_name is type_name

    env.define(constructor_name, Primitive(str(constructor_name), construct))
    env.define(predicate_name, Primitive(str(predicate_name), is_record))
    env.define(type_name, record_type)

    for index, (field_name, accessor_name, modifier_name) in enumerate(accessors):

        def read(
            value: Any,
            _index: int = index,
            _name: Symbol = accessor_name,
            _type: Symbol = type_name,
        ) -> Any:
            if not (isinstance(value, Record) and value.type_name is _type):
                raise LispTypeError(
                    f"{_name}: expected a {_type} record, got {_describe_value(value)}"
                )
            return value.fields[_index]

        env.define(accessor_name, Primitive(str(accessor_name), read))

        if modifier_name is None:
            continue

        def write(
            value: Any,
            new_value: Any,
            _index: int = index,
            _name: Symbol = modifier_name,
            _field: Symbol = field_name,
            _type: Symbol = type_name,
        ) -> Any:
            if not (isinstance(value, Record) and value.type_name is _type):
                raise LispTypeError(
                    f"{_name}: expected a {_type} record, got {_describe_value(value)}"
                )
            if not value.mutable[_index]:
                raise LispTypeError(f"{_name}: field {_field} is immutable")
            value.fields[_index] = new_value
            return NIL

        env.define(modifier_name, Primitive(str(modifier_name), write))

    return type_name


def _feature_requirement(value: Any, env: Optional[Environment] = None) -> bool:
    """Evaluate a ``cond-expand`` feature requirement against the host.

    The grammar is R7RS §4.2.1: a feature identifier, or ``(and ...)``,
    ``(or ...)``, ``(not ...)``, ``(library <name>)``. ``else`` is a whole
    clause, never a requirement, so it is rejected here.
    """
    from .features import feature_names

    if isinstance(value, Symbol):
        if str(value) == "else":
            raise LispSyntaxError("cond-expand: else is a clause, not a requirement")
        extra = getattr(env, "feature_extra", ()) or ()
        return str(value) in feature_names(extra)
    if not isinstance(value, list) or not value or not isinstance(value[0], Symbol):
        raise LispSyntaxError(f"cond-expand: bad feature requirement: {_describe_value(value)}")
    head = str(value[0])
    if head == "and":
        return all(_feature_requirement(item, env) for item in value[1:])
    if head == "or":
        return any(_feature_requirement(item, env) for item in value[1:])
    if head == "not":
        if len(value) != 2:
            raise LispSyntaxError("cond-expand: (not ...) takes one requirement")
        return not _feature_requirement(value[1], env)
    if head == "library":
        if len(value) != 2:
            raise LispSyntaxError("cond-expand: (library ...) takes one name")
        from .library import library_available

        return library_available(env, value[1]) if env is not None else False
    raise LispSyntaxError(f"cond-expand: unknown requirement {head}")


def _eval_cond_expand(expr: list, env: Environment) -> Any:
    """``(cond-expand (requirement body...) ...)`` — the first true clause wins."""
    for clause in expr[1:]:
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("cond-expand: each clause is (requirement body...)")
        requirement = clause[0]
        if isinstance(requirement, Symbol) and str(requirement) == "else":
            return evaluate_program(clause[1:], env)
        if _feature_requirement(requirement, env):
            return evaluate_program(clause[1:], env)
    raise LispSyntaxError("cond-expand: no clause matched and there is no else")


def _eval_syntax_error(expr: list, env: Environment) -> Any:
    """``(syntax-error message irritant ...)`` — fail at expansion time."""
    if len(expr) < 2:
        raise LispSyntaxError("syntax-error: needs a message")
    message = expr[1]
    if isinstance(message, str) and not isinstance(message, Symbol):
        shown = message
    else:
        shown = _describe_value(message)
    if len(expr) > 2:
        irritants = " ".join(_describe_value(item) for item in expr[2:])
        raise LispError(f"syntax-error: {shown} {irritants}")
    raise LispError(f"syntax-error: {shown}")


def _eval_include(expr: list, env: Environment, fold_case: bool) -> Any:
    """``(include "file" ...)`` / ``(include-ci ...)`` — textual inclusion.

    The loader resolves the path exactly as ``load`` does, so a file beside the
    including one is found first. Inclusion is *not* cached: the file is read
    and evaluated every time, which is what R7RS's textual inclusion means.
    """
    if len(expr) < 2:
        raise LispSyntaxError("include: needs at least one file name")
    loader = env.loader
    if loader is None:
        raise LispError("include: no loader is attached to this environment")
    value: Any = NIL
    for spec in expr[1:]:
        if not isinstance(spec, str) or isinstance(spec, Symbol):
            raise LispSyntaxError("include: expected a file-name string")
        value = loader.include_file(spec, fold_case=fold_case)
    return value


# --------------------------------------------------------------------------- #
#  SRFI 241 — the standard `match`                                            #
# --------------------------------------------------------------------------- #

#: SRFI 241's auxiliary syntax, recognized *structurally* (the library exports
#: only `match`, so the auxiliary names cannot collide with anything).
_SRFI241_UNQUOTE = intern("unquote")
_SRFI241_UNQUOTE_SPLICING = intern("unquote-splicing")
_SRFI241_ELLIPSIS = intern("...")
_SRFI241_GUARD = intern("guard")
_SRFI241_ARROW = intern("->")
#: The hidden special form the clause body's ``quasiquote`` rewrites into.
_SRFI241_QQ = intern("%srfi241-quasiquote")


def _srfi241_match(expr: list, env: Environment) -> Any:
    """``(match value clause ...)`` — SRFI 241's pattern matcher.

    A *clause* is ``(pattern body...)`` or ``(pattern (guard expr ...) body...)``.
    Patterns: `,_` (wildcard), `,x` (pattern variable, spelled ``(unquote x)`` by
    the reader), a pattern symbol or any constant (matched by ``equal?``), `()`,
    proper and dotted list patterns, one ellipsis ``pe ...`` per list, vector
    patterns ``#(...)`` with the same shape rules, quoted data, and the
    catamorphism `,[x]` / `,[op -> x ...]` (S6b). A guard is recognized
    structurally: the clause's second element is a form headed by the auxiliary
    symbol ``guard``; if the pattern matches but a guard expression is false, the
    clause fails and matching continues — the failed clause's bindings never
    leak. The clause body's ``quasiquote`` is ellipsis-aware (S6b).
    """
    if len(expr) < 2:
        raise LispSyntaxError("match: expected (match value clause...)")
    value = evaluate(expr[1], env)
    clauses = expr[2:]
    return _srfi241_clauses(clauses, value, env, (clauses, env))


def _srfi241_clauses(clauses: list, value: Any, env: Environment, ctx: tuple) -> Any:
    """Match *value* against the clauses; the matched clause's body, as a form.

    The clause body is returned as a ``let`` form in *tail* position. The
    catamorphism's default operator re-enters here (a nested call, not a
    trampolined tail call — see docs/srfi.md for the documented deviation).
    """
    for clause in clauses:
        if not isinstance(clause, list) or len(clause) < 2:
            raise LispSyntaxError("match: each clause is (pattern body...)")
        pattern, body = clause[0], clause[1:]
        guard = None
        if (
            body
            and isinstance(body[0], list)
            and body[0]
            and body[0][0] is _SRFI241_GUARD
        ):
            guard = body[0][1:]
            body = body[1:]
        binds: dict = {}
        catas: list = []
        seen: dict = {}
        if not _srfi241_pattern(pattern, value, binds, catas, seen):
            continue
        # A repeated pattern variable becomes an equality constraint, checked
        # with the clause's guards.
        extra_guards = [
            [intern("equal?"), var, intern(f"{var}#{i}")]
            for var, count in seen.items()
            if isinstance(count, int) and count > 1
            for i in range(2, count + 1)
        ]
        if extra_guards:
            guard = extra_guards if guard is None else extra_guards + guard
        # The pattern variables and cata variables must be pairwise disjoint.
        cata_vars = [v for _, _, vars_ in catas for v in vars_]
        if len(set(cata_vars)) != len(cata_vars) or any(v in seen for v in cata_vars):
            raise LispSyntaxError("match: repeated cata variable in match clause")
        if guard is not None and not _srfi241_guard_ok(guard, binds, env):
            continue
        # The cata pass: operators are evaluated in the environment extended by
        # the pattern's bindings, then invoked on the matched values; the cata
        # variables are bound left to right afterwards. A variable bound by a
        # cata pattern inside an ellipsis repeats, so its results collect into
        # a list.
        ext = _srfi241_ext_env(binds, env)
        pending = []
        for op_expr, matched, vars_ in catas:
            if op_expr is None:
                # The default cata operator: the match itself, re-entered with
                # the matched value as the new input.
                proc = Primitive(
                    "match-cata", lambda arg, c=clauses, e=env, x=ctx: (
                        evaluate(_srfi241_clauses(c, arg, e, x), e)
                    )
                )
            else:
                proc = evaluate(op_expr, ext)
            pending.append((proc, matched, vars_))
        pending_values: dict = {}
        for proc, matched, vars_ in pending:
            results = values_list(apply_procedure(proc, [matched]))
            if len(results) != len(vars_):
                raise LispError(
                    f"match: a cata operator returned {len(results)} value(s); "
                    f"expected {len(vars_)}"
                )
            for var, bound in zip(vars_, results):
                pending_values.setdefault(var, []).append(bound)
        for var, vals in pending_values.items():
            binds[var] = vals[0] if len(vals) == 1 else vals
        return _match_body(_srfi241_rewrite_bodies(body), binds)
    raise LispError(_unmatched(value))


def _srfi241_ext_env(binds: dict, env: Environment) -> Environment:
    """The environment extended by the clause's pattern bindings."""
    return Environment(parent=env, vars=dict(binds))


def _srfi241_rewrite_bodies(body: list) -> list:
    """Bind ``quasiquote`` to the ellipsis-aware form inside a clause body."""
    return [_srfi241_rewrite_qq(form) for form in body]


def _srfi241_rewrite_qq(form: Any) -> Any:
    if isinstance(form, list):
        if len(form) == 2 and form[0] is QUOTE:
            return form  # data, not code: leave a quoted datum untouched
        if len(form) == 2 and form[0] is QUASIQUOTE:
            return [_SRFI241_QQ, form[1]]
        return [_srfi241_rewrite_qq(item) for item in form]
    return form


def _srfi241_guard_ok(guard: list, binds: dict, env: Environment) -> bool:
    """The clause's guard expressions, with the pattern's bindings in scope."""
    bindings = [[name, [QUOTE, bound]] for name, bound in binds.items()]
    for form in guard:
        if evaluate([LET, bindings, form], env) is False:
            return False
    return True


# -- S6b: the ellipsis-aware quasiquote inside match bodies ------------------ #

def _srfi241_qq(expr: list, env: Environment) -> Any:
    """``(%srfi241-quasiquote template)`` — SRFI 241's ellipsis-aware quasiquote.

    ``...`` after a subform splices the list the subtemplate's commas evaluate
    to; `(... form)` disables ellipsis meaning inside *form*; `,@` is
    `,` followed by `...`; a nested ``quasiquote`` is ellipsis-aware too.
    """
    if len(expr) != 2:
        raise LispSyntaxError("%srfi241-quasiquote: expected one template")
    return _srfi241_qq_template(expr[1], env, True)


def _srfi241_splice(value: Any) -> list:
    """The elements a spliced subtemplate contributes."""
    cells = tag_cells(value)
    if cells is None:
        raise LispTypeError(
            f"%srfi241-quasiquote: ... needs a list to splice, got {_describe_value(value)}"
        )
    return cells


def _srfi241_qq_template(tmpl: Any, env: Environment, ellipsis: bool) -> Any:
    # A template that *is* a comma form: evaluate it (the parent handles a
    # following `...`).
    if (
        isinstance(tmpl, list)
        and len(tmpl) == 2
        and tmpl[0] is _SRFI241_UNQUOTE
    ):
        return evaluate(tmpl[1], env)
    if isinstance(tmpl, Vector):
        return Vector(
            [_srfi241_qq_template(item, env, ellipsis) for item in tmpl.items]
        )
    if not isinstance(tmpl, (list, Pair)):
        return tmpl
    items, tail = _pattern_cells(tmpl)
    # (... template) — ellipses inside have no special meaning.
    if (
        ellipsis
        and len(items) == 2
        and items[0] is _SRFI241_ELLIPSIS
        and is_nil(tail)
    ):
        return _srfi241_qq_template(items[1], env, False)
    out: list = []
    i = 0
    while i < len(items):
        elt = items[i]
        # A comma evaluates whether or not ellipses are special; only the
        # splicing (`...` after the comma) needs ellipses to be special.
        if isinstance(elt, list) and len(elt) == 2 and elt[0] is _SRFI241_UNQUOTE:
            if ellipsis and i + 1 < len(items) and items[i + 1] is _SRFI241_ELLIPSIS:
                out.extend(_srfi241_splice(evaluate(elt[1], env)))
                i += 2
                continue
            out.append(evaluate(elt[1], env))
            i += 1
            continue
        if (
            ellipsis
            and isinstance(elt, list)
            and len(elt) == 2
            and elt[0] is _SRFI241_UNQUOTE_SPLICING
        ):
            out.extend(_srfi241_splice(evaluate(elt[1], env)))
            i += 1
            continue
        out.append(_srfi241_qq_template(elt, env, ellipsis))
        i += 1
    if is_nil(tail):
        return out
    # The dotted tail: a subtemplate (often a comma form). A list result
    # continues the list (``(a . ,x)`` with x a list is ``(a 1 2)``); an atom
    # tail makes a dotted pair.
    tail_value = _srfi241_qq_template(tail, env, ellipsis)
    if isinstance(tail_value, list):
        return out + tail_value
    return from_cells(out, tail_value)


def _srfi241_pattern(pattern: Any, value: Any, binds: dict, catas: list, seen: dict) -> bool:
    """One SRFI 241 pattern against one value, recording bindings in *binds*.

    Catamorphism patterns record requests in *catas* — processed after the
    guards pass — instead of binding immediately; *seen* counts pattern
    variables so a repeat can become an equality constraint, as the SRFI
    requires.
    """
    if isinstance(value, list) and not value:
        value = NIL  # an empty slice is the empty list: normalize to NIL
    if (
        isinstance(pattern, list)
        and len(pattern) == 2
        and pattern[0] is _SRFI241_UNQUOTE
    ):
        var = pattern[1]
        if isinstance(var, (list, Pair)):
            # ,([...]) — a cata pattern: (op -> x ...) or (x ...)
            items, tail = _pattern_cells(var)
            if not is_nil(tail):
                raise LispSyntaxError(
                    "match: the cata pattern's variables must be a proper list"
                )
            if len(items) >= 2 and items[1] is _SRFI241_ARROW:
                op_expr, vars_ = items[0], items[2:]
            elif items and items[0] is _SRFI241_ARROW:
                raise LispSyntaxError(
                    "match: the cata pattern needs an operator before ->"
                )
            else:
                op_expr, vars_ = None, items
            if not vars_:
                raise LispSyntaxError("match: a cata pattern needs a variable")
            for var_ in vars_:
                if not isinstance(var_, Symbol):
                    raise LispSyntaxError("match: a cata variable must be a symbol")
            catas.append((op_expr, value, list(vars_)))
            return True
        if var is UNDERSCORE:
            return True  # ,_ matches anything, binds nothing
        if var in seen:
            # A repeated pattern variable binds a fresh location; an equality
            # constraint (built later from *seen*) makes both occurrences
            # match equal values.
            seen[var] = seen[var] + 1
            binds[intern(f"{var}#{seen[var]}")] = value
            return True
        seen[var] = 1
        binds[var] = value
        return True
    if isinstance(pattern, Symbol):
        return equal(pattern, value)  # a pattern symbol is a constant
    if pattern is True or pattern is False or pattern is NIL:
        return equal(pattern, value)
    if isinstance(pattern, (int, float, str, Char)):
        return equal(pattern, value)
    if isinstance(pattern, Vector):
        return _srfi241_vector(pattern, value, binds, catas, seen)
    if isinstance(pattern, (list, Pair)):
        items, tail = _pattern_cells(pattern)
        if len(items) == 2 and items[0] is QUOTE and is_nil(tail):
            return equal(items[1], value)  # a quoted datum pattern: ('ok)
        if items and items[-1] is _SRFI241_ELLIPSIS:
            if not is_nil(tail) or len(items) < 2:
                raise LispSyntaxError(
                    "match: the ellipsis ... must end a proper list pattern"
                )
            return _srfi241_repeat(items[-2], items[:-2], value, binds, catas, seen)
        return _srfi241_sequence(items, tail, value, binds, catas, seen)
    return equal(pattern, value)


def _srfi241_sequence(items: List[Any], tail: Any, value: Any, binds: dict, catas: list, seen: dict) -> bool:
    """A list pattern with no ellipsis: fixed arity, or a dotted tail."""
    cells = tag_cells(value)
    if cells is None:
        return False
    if is_nil(tail):
        if len(cells) != len(items):
            return False
        return all(_srfi241_pattern(p, c, binds, catas, seen) for p, c in zip(items, cells))
    if len(cells) < len(items):
        return False
    if not all(_srfi241_pattern(p, c, binds, catas, seen) for p, c in zip(items, cells[: len(items)])):
        return False
    return _srfi241_pattern(tail, cells[len(items) :], binds, catas, seen)


def _srfi241_repeat(pe: Any, fixed: List[Any], value: Any, binds: dict, catas: list, seen: dict) -> bool:
    """``pe ...`` — *pe* matches zero or more elements after *fixed*.

    Deterministic and bounded: the fixed patterns take the first elements and
    the ellipsis pattern takes the rest; there is no backtracking because a
    list pattern carries at most one ellipsis. Each element's bindings are
    collected in order, so a variable bound by *pe* becomes a list — across a
    surrounding ellipsis this is what makes nested repeats collect lists of
    lists. Variables *pe* could bind are pre-bound to empty lists, so a
    variable that never matched (zero elements) still binds ``()``.
    """
    cells = tag_cells(value)
    if cells is None:
        return False
    if len(cells) < len(fixed):
        return False
    if not all(_srfi241_pattern(p, c, binds, catas, seen) for p, c in zip(fixed, cells[: len(fixed)])):
        return False
    collected: dict = {var: [] for var in _srfi241_vars(pe)}
    for element in cells[len(fixed) :]:
        element_binds: dict = {}
        element_catas: list = []
        element_seen: dict = {}
        if not _srfi241_pattern(pe, element, element_binds, element_catas, element_seen):
            return False
        for name, bound in element_binds.items():
            collected.setdefault(name, []).append(bound)
        for op_expr, matched, vars_ in element_catas:
            # A cata pattern inside an ellipsis repeats: each element's value
            # goes to the operator, and the results collect into lists (the
            # cata variables' per-element groups are one-element lists).
            catas.append((op_expr, matched, [[name] for name in vars_]))
    binds.update(collected)
    return True


def _srfi241_vars(pattern: Any) -> list:
    """The pattern variables a pattern could bind, in order."""
    out: list = []
    _srfi241_collect_vars(pattern, out)
    return out


def _srfi241_collect_vars(pattern: Any, out: list) -> None:
    if (
        isinstance(pattern, list)
        and len(pattern) == 2
        and pattern[0] is _SRFI241_UNQUOTE
    ):
        var = pattern[1]
        if not isinstance(var, (list, Pair)) and var is not UNDERSCORE:
            out.append(var)
        return
    if isinstance(pattern, Vector):
        for item in pattern.items:
            _srfi241_collect_vars(item, out)
        return
    if isinstance(pattern, (list, Pair)):
        items, tail = _pattern_cells(pattern)
        if len(items) == 2 and items[0] is QUOTE and is_nil(tail):
            return  # a quoted datum is a constant, not a binder
        for item in items:
            _srfi241_collect_vars(item, out)
        if not is_nil(tail):
            _srfi241_collect_vars(tail, out)


def _srfi241_vector(pattern: Vector, value: Any, binds: dict, catas: list, seen: dict) -> bool:
    """``#(p1 ... pn)``, with the same fixed/ellipsis rules as list patterns."""
    if not isinstance(value, Vector):
        return False
    items = pattern.items
    if items and items[-1] is _SRFI241_ELLIPSIS:
        if len(items) < 2:
            raise LispSyntaxError(
                "match: the ellipsis ... must follow a vector pattern element"
            )
        return _srfi241_repeat(items[-2], items[:-2], value.items, binds, catas, seen)
    if len(items) != len(value.items):
        return False
    return all(_srfi241_pattern(p, c, binds, catas, seen) for p, c in zip(items, value.items))


def _step_match(expr: list, env: Environment) -> Any:
    """``(match value (pattern body...) ...)`` — first matching clause wins.

    *pattern* is one of:

    * ``_`` — matches anything, binds nothing;
    * a bare symbol — matches anything, binds it;
    * a literal (number, string, character, ``#t``/``#f``/``()``) or a quoted
      datum ``'x`` — matches by ``equal?``;
    * ``(tag p ...)`` — a **tag pattern** when ``tag`` is a symbol the program
      declared with ``define-variant``: the head is read as the tag (not a
      binder) and the fields are matched by the sub-patterns, so ``(ok v)``
      reads the tag ``ok`` and binds its field. ``('ok v)`` spells the same
      thing with an explicit quote, which also works for an undeclared tag;
    * ``(p1 ... pn)`` or ``(p1 ... . rest)`` — any other list pattern. It reads a
      value's *cells*: a :class:`Tagged` views as ``(tag . fields)``, so a list
      of the same shape matches the same pattern.

    ``else`` (last clause only) is the explicit catch-all. With no matching
    clause and no ``else``, the match is *non-exhaustive* and raises — naming the
    value, and the declared cases if the tag belongs to a variant.
    """
    if len(expr) < 2:
        raise LispSyntaxError("match: expected (match value (pattern body...)...)")
    value = evaluate(expr[1], env)
    clauses = expr[2:]
    for index, clause in enumerate(clauses):
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("match: each clause is (pattern body...)")
        if clause[0] is ELSE:
            if index != len(clauses) - 1:
                raise LispSyntaxError("match: else must be the last clause")
            return _match_body(clause[1:], None)
        binds: dict = {}
        if _match_pattern(clause[0], value, binds):
            return _match_body(clause[1:], binds)
    raise LispError(_unmatched(value))


def _match_body(body: List[Any], binds: Optional[dict]) -> Any:
    """The matched clause's body, with bindings threaded through a ``let``.

    Quoting each already-evaluated value is what keeps the clause in *tail*
    position: the returned form is ``(let ((name 'value) ...) body...)``, which
    the trampoline runs in place rather than by nesting a call.
    """
    forms = body or [NIL]
    if not binds:
        return _body_form(forms)
    bindings = [[name, [QUOTE, bound]] for name, bound in binds.items()]
    return [LET, bindings, *forms]


def _match_pattern(pattern: Any, value: Any, binds: dict) -> bool:
    """Match one pattern against one value, recording bindings in *binds*."""
    if pattern is UNDERSCORE:
        return True
    if isinstance(pattern, Symbol):
        binds[pattern] = value
        return True
    if pattern is True or pattern is False or pattern is NIL:
        return equal(pattern, value)
    if isinstance(pattern, (int, float, str, Char)):
        return equal(pattern, value)
    if isinstance(pattern, (list, Pair)):
        items, tail = _pattern_cells(pattern)
        if len(items) == 2 and items[0] is QUOTE and is_nil(tail):
            return equal(items[1], value)  # a quoted datum: ('ok)
        if (
            is_nil(tail)
            and items
            and isinstance(items[0], Symbol)
            and items[0] in _TAG_UNIONS
        ):
            # A *declared* tag in head position is a tag pattern, not a binder:
            # `(ok v)` reads the tag `ok` and binds its field. Writing `ok` where
            # it can only mean the declared tag is the whole point of declaring
            # the set — and it is why the ergonomic spelling needs no quote.
            return _match_tagged(items[0], items[1:], value, binds)
        return _match_sequence(items, tail, value, binds)
    return equal(pattern, value)


def _match_tagged(tag: Symbol, fields: List[Any], value: Any, binds: dict) -> bool:
    """Match a declared tag and its fields, on a tagged value or a like list."""
    cells = tag_cells(value)
    if not cells or cells[0] != tag:
        return False
    rest = cells[1:]
    if len(rest) != len(fields):
        return False
    return all(_match_pattern(p, c, binds) for p, c in zip(fields, rest))


def _match_sequence(items: List[Any], tail: Any, value: Any, binds: dict) -> bool:
    cells = tag_cells(value)
    if cells is None:
        return False
    if is_nil(tail):
        if len(cells) != len(items):
            return False
        return all(_match_pattern(p, c, binds) for p, c in zip(items, cells))
    if len(cells) < len(items):
        return False
    if not all(_match_pattern(p, c, binds) for p, c in zip(items, cells[: len(items)])):
        return False
    return _match_pattern(tail, cells[len(items) :], binds)


def _pattern_cells(pattern: Any) -> tuple:
    """A pattern list or pair chain as ``([items], tail)``."""
    if isinstance(pattern, list):
        return list(pattern), NIL
    items: List[Any] = []
    node: Any = pattern
    while isinstance(node, Pair):
        items.append(node.car)
        node = node.cdr
    return items, node


def _unmatched(value: Any) -> str:
    """The refusal a non-exhaustive ``match`` raises — naming what it knew."""
    union = _TAG_UNIONS.get(value.tag) if isinstance(value, Tagged) else None
    expected = ""
    if union is not None:
        expected = f"; this {union} is one of " + " ".join(
            str(tag) for tag in _VARIANTS[union]
        )
    return f"match: no clause matched {_describe_value(value)}{expected}"


def _describe_value(value: Any) -> str:
    from .printer import to_string

    return to_string(value, write=True)


# --------------------------------------------------------------------------- #
#  Conditions, error objects, and multiple values                              #
# --------------------------------------------------------------------------- #

_RERAISE = object()


def _as_condition(exc: LispError) -> Any:
    """The object a handler sees for *exc*: what was raised, or an error object."""
    if isinstance(exc, LispRaise):
        return exc.value
    from .errors import FileError, ReadError

    kind = (
        "file"
        if isinstance(exc, FileError)
        else "read"
        if isinstance(exc, ReadError)
        else None
    )
    return ErrorObject(str(exc), kind=kind)


def _eval_guard(expr: list, env: Environment) -> Any:
    """``(guard (var clause...) body...)`` — catch, bind, and branch.

    A condition from the body is bound to *var* and the clauses run like
    ``cond``. If none matches, the original error is re-raised.
    """
    if len(expr) < 3 or not isinstance(expr[1], list) or not expr[1]:
        raise LispSyntaxError("guard: expected (guard (var clauses...) body...)")
    header = expr[1]
    var = header[0]
    if not isinstance(var, Symbol):
        raise LispSyntaxError("guard: the handler's first element must be a variable")
    clauses = header[1:]
    try:
        return evaluate(_body_form(expr[2:]), env)
    except LispError as exc:
        result = _guard_clauses(clauses, var, _as_condition(exc), env)
        if result is _RERAISE:
            raise
        return result


def _guard_clauses(clauses: list, var: Symbol, condition: Any, env: Environment) -> Any:
    local = Environment(parent=env)
    local.define(var, condition)
    for clause in clauses:
        if not isinstance(clause, list) or not clause:
            raise LispSyntaxError("guard: each clause is (test body...)")
        if clause[0] is ELSE:
            return NIL if len(clause) == 1 else evaluate(_body_form(clause[1:]), local)
        if len(clause) >= 3 and clause[1] is ARROW:
            value = evaluate(clause[0], local)
            if is_true(value):
                return apply_procedure(evaluate(clause[2], local), [value])
            continue
        value = evaluate(clause[0], local)
        if is_true(value):
            if len(clause) == 1:
                # Test-only clause: its value is the result. Evaluating the
                # test again here would run its side effects twice.
                return value
            return evaluate(_body_form(clause[1:]), local)
    return _RERAISE


def values_list(value: Any) -> list:
    """A multiple-value bundle as a list; any other value as a one-element list."""
    if isinstance(value, Values):
        return list(value)
    return [value]


def _names_of(form: Any, who: str) -> list:
    if is_nil(form):
        return []
    if isinstance(form, Pair):
        raise LispSyntaxError(f"{who}: binding names must be a proper list")
    try:
        names = list_to_python(form)
    except LispError:
        raise LispSyntaxError(f"{who}: binding names must be a list") from None
    if not all(isinstance(n, Symbol) for n in names):
        raise LispSyntaxError(f"{who}: binding names must be symbols")
    return names


def _eval_let_values(expr: list, env: Environment, sequential: bool) -> Any:
    """``let-values`` (parallel) and ``let*-values`` (sequential)."""
    who = "let*-values" if sequential else "let-values"
    if len(expr) < 3 or not (isinstance(expr[1], list) or is_nil(expr[1])):
        raise LispSyntaxError(f"{who}: expected ({who} (bindings...) body...)")
    bindings = [] if is_nil(expr[1]) else expr[1]
    local = Environment(parent=env)
    for binding in bindings:
        if not isinstance(binding, list) or len(binding) != 2:
            raise LispSyntaxError(f"{who}: each binding is ((names...) expr)")
        names = _names_of(binding[0], who)
        scope = local if sequential else env
        vals = values_list(evaluate(binding[1], scope))
        if len(vals) != len(names):
            raise LispArityError(who, f"{len(names)} value(s)", len(vals))
        for name, value in zip(names, vals):
            local.define(name, value)
    return evaluate(_body_form(expr[2:]), local)


def _eval_define_values(expr: list, env: Environment) -> Any:
    """``(define-values (a b) expr)`` — bind every value to a name."""
    if len(expr) != 3:
        raise LispSyntaxError("define-values: expected (define-values (names...) expr)")
    names = _names_of(expr[1], "define-values")
    vals = values_list(evaluate(expr[2], env))
    if len(vals) != len(names):
        raise LispArityError("define-values", f"{len(names)} value(s)", len(vals))
    for name, value in zip(names, vals):
        env.define(name, value)
    return NIL


# --------------------------------------------------------------------------- #
#  Equality (shared with the ``equal?`` primitive)                             #
# --------------------------------------------------------------------------- #

#: The numeric tower's host types, mirroring ``builtins.Number``. Kept here so
#: ``equal?`` can honour exactness without importing ``builtins`` (which imports
#: the evaluator).
_NUMBER_TYPES = (int, float, Fraction, Complex, complex)


def equal(a: Any, b: Any) -> bool:
    """Structural equality with Scheme's booleans-before-numbers rule.

    R7RS defines ``equal?`` recursively but compares atoms with ``eqv?``, so
    exactness is part of numeric identity: ``(equal? 1 1.0)`` is ``#f``, just
    as ``(eqv? 1 1.0)`` is. Without this rule ``case``/hash-table lookups and
    the numeric tower disagree about what "the same value" means.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, _NUMBER_TYPES) and isinstance(b, _NUMBER_TYPES):
        return type(a) is type(b) and a == b
    if a is NIL or b is NIL:
        return a is b
    # A keyword is a ``str`` subclass too, so the host ``==`` below would call
    # a keyword and a symbol (or a string) of the same spelling equal. SRFI 88
    # makes keywords a distinct kind: same spelling, same keyword; anything
    # else is not equal.
    if isinstance(a, Keyword) or isinstance(b, Keyword):
        return isinstance(a, Keyword) and isinstance(b, Keyword) and str(a) == str(b)
    # A symbol is a ``str`` subclass, so the host ``==`` below would call
    # ``'a`` and ``"a"`` equal. They are different kinds of value: a symbol is
    # an interned identifier, a string is text. Keep them apart here so
    # ``equal?`` agrees with :func:`hash_key`, which already keys them
    # separately.
    if isinstance(a, Symbol) or isinstance(b, Symbol):
        return isinstance(a, Symbol) and isinstance(b, Symbol) and str(a) == str(b)
    if isinstance(a, list) or isinstance(b, list):
        if not (isinstance(a, list) and isinstance(b, list)):
            return False
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if isinstance(a, Pair) or isinstance(b, Pair):
        if not (isinstance(a, Pair) and isinstance(b, Pair)):
            return False
        return equal(a.car, b.car) and equal(a.cdr, b.cdr)
    if isinstance(a, Vector) or isinstance(b, Vector):
        if not (isinstance(a, Vector) and isinstance(b, Vector)):
            return False
        return len(a.items) == len(b.items) and all(
            equal(x, y) for x, y in zip(a.items, b.items)
        )
    if isinstance(a, ByteVector) or isinstance(b, ByteVector):
        if not (isinstance(a, ByteVector) and isinstance(b, ByteVector)):
            return False
        return a.data == b.data
    if isinstance(a, Srfi160Vector) or isinstance(b, Srfi160Vector):
        if not (isinstance(a, Srfi160Vector) and isinstance(b, Srfi160Vector)):
            return False
        return a.typecode == b.typecode and a.data.tobytes() == b.data.tobytes()
    if isinstance(a, (Srfi19Time, Srfi19Date)) or isinstance(b, (Srfi19Time, Srfi19Date)):
        # SRFI 19's value types are distinct from everything else; equality is
        # field-wise (the classes define it), and a time never equals a date.
        return type(a) is type(b) and a == b
    if isinstance(a, Tagged) or isinstance(b, Tagged):
        if not (isinstance(a, Tagged) and isinstance(b, Tagged)):
            return False
        return (
            a.tag == b.tag
            and len(a.fields) == len(b.fields)
            and all(equal(x, y) for x, y in zip(a.fields, b.fields))
        )
    if isinstance(a, (Closure, Primitive, Macro, SyntaxRules)) or isinstance(
        b, (Closure, Primitive, Macro, SyntaxRules)
    ):
        return a is b
    return a == b
