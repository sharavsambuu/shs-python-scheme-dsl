# About

A custom Scheme/LISP DSL running on Python, created to bring LISP-style expressions into personal Python projects. Over time, my projects began evolving into disparate LISP dialects, so I created this repository to establish a lightweight mini-standard based on Scheme's R7RS-small specification and selected SRFIs. While it serves as a practical introductory tool for embedded LISP design, it is not intended as a robust general-purpose solution for serious production use. Please note that this repository was built strictly for personal needs and will not be actively maintained. Thanks for stopping by!

You can check docs/lisp_tutorial/ for more usages and also you can check my Tetris demo code how to use this library
https://github.com/sharavsambuu/python-lisp-tetris-exp


# shs — a small Scheme DSL over Python

`shs` is a gosh-shaped command line for a small Scheme-flavored Lisp that runs
on Python. The language is one pure-standard-library package (`shslisp`) you can
install, script with, embed in your own Python projects, and read in an
afternoon.

It uses the following SRFIs,
all pre-imported by the default profile:

| SRFI | Name | What you get |
| --- | --- | --- |
| SRFI 1 | List library | `iota`, the `fold` family, `filter`, association lists, set operations |
| SRFI 26 | Specializing | `cut` / `cute` — partial application without lambda boilerplate |
| SRFI 88 | Keyword objects | `host:` — self-evaluating keywords, similar to Erlang's atoms |
| SRFI 89 | Optional and named parameters | `define*` / `lambda*` with optional positional and keyword parameters |
| SRFI 197 | Pipeline operators | `chain`, `chain-and`, `chain-when`, `chain-lambda`, `nest` |
| SRFI 241 | Pattern matching | `match` with quasiquote patterns, guards, ellipsis, catamorphism |
| SRFI 19 | Time and date | `time-utc`/`date`, duration arithmetic, Julian day, `date->string`/`string->date` |
| SRFI 158 | Generators and accumulators | the full combinator set, multi-generator drains, and the accumulator half |
| SRFI 160 | Numeric vectors | `f64vector` and its cousins over the buffer protocol — the pandas/numpy bridge, `#f64(...)` literals |

> **Note on SRFI 204.** SRFI 204 (the Wright–Cartwright–Shinn matcher) is
> *withdrawn* and is deliberately not implemented — `(srfi 204)` fails with a
> pointer to `(srfi 241)`, which is the final matcher SRFI.

The three trading-layer SRFIs (19, 158, 160) landed as S10–S12 in
[`docs/SRFI_TASKS.md`](docs/SRFI_TASKS.md), each with its documented
deviations in [`docs/srfi.md`](docs/srfi.md).

## Install

Full details — pinned installs, troubleshooting, the `git+` gotcha — are in
[`docs/INSTALL.md`](docs/INSTALL.md). The short version:

```sh
# from a clone (best if you want to hack on the interpreter or the tutorial)
git clone https://github.com/sharavsambuu/shs-python-scheme-dsl
cd shs-python-scheme-dsl
pip install .

# or straight from GitHub — note the mandatory `git+` prefix
pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git

# pinned to a tag/commit, for a project that depends on it
pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git@v0.2.2
```

No runtime dependencies: the interpreter is pure Python standard library
(Python 3.11+). Both the `shs` command and the `import shslisp` module are installed.

> **Do not `pip install shs`** — that PyPI name belongs to an unrelated
> project ("Security Hygiene Scanner"). Ours is `shslisp`; the command
> it installs is still called `shs`.

## The `shs` command

```sh
shs                              # interactive REPL (the default)
shs -e "(+ 1 2)"                 # evaluate an expression, print the value
shs run program.scm              # run a script
shs program.scm                  # the same, gosh-style: the file is the command
shs run program.scm arg1 arg2    # args become *command-line-args*
shs --profile r7rs               # strict R7RS-small: no SRFIs preloaded
shs --plugin mypkg -e "(host-verb)"   # load a host vocabulary, then evaluate
shs --version
```

A *plugin* is the same extension shape `shslisp.embed` documents: an
importable Python module whose `install(env)` function binds the host's
primitives. `--plugin MOD[:ATTR]` is repeatable (`ATTR` defaults to
`install`), and `SHS_PLUGINS` (an `os.pathsep`-separated list, like `PATH`)
does the same for every invocation — `run`, `-e` and `repl`. A spec that does
not import, or an attribute that is not callable, stops the command with a
non-zero exit and an error naming the spec.

Scripts may begin with a shebang and be executable directly:

```scheme
#!/usr/bin/env shs
(display (fold + 0 (iota 5 1)))   ; => 15
(newline)
```

```sh
chmod +x program.scm
./program.scm
```

Inside the REPL: `,help` shows the commands (`,load PATH`, `,quit`); everything
else is Lisp. Put extra module directories on the load path with `SHS_PATH`
(`os.pathsep`-separated — `:` on Unix, `;` on Windows, like `PATH`).

## Examples

Runnable scripts live in [`examples/`](examples/):

```sh
shs run examples/fizzbuzz.scm          # a first script
python examples/embed_inventory_host.py  # a generic Python host (no Tetris!)
```

The second one is the generality proof in miniature: a stateful Python
`Inventory` class drives a Lisp policy layer — with the SRFI list library, a
SRFI 197 pipeline, and Python exceptions caught as Lisp conditions via `guard`.

## Learn it

- **The tutorial** — [`docs/lisp_tutorial/README.md`](docs/lisp_tutorial/README.md):
  from "Lisp in ten minutes" to macros, modules, ROP, and the SRFI layer, with
  every example machine-checked by the test suite.
- **The practical handbook** — [`docs/practical_tutorial/README.md`](docs/practical_tutorial/README.md):
  the tooling track, P0–P6: the REPL as a workbench, reading a failure,
  programs across files, ports and files, features and the walls, shipping a
  host extension, and testing Lisp from the host — every `Try it` example
  machine-checked by `tests/test_practical.py`.
- **The language guide** — [`docs/language.md`](docs/language.md): the one-stop
  reference with verified examples.
- **The SRFI contract** — [`docs/srfi.md`](docs/srfi.md): exactly what each SRFI
  provides, the import collisions the profile resolves for you, and the
  deviations.
- **The DSL specification** — [`docs/lisp-dsl.md`](docs/lisp-dsl.md): the target
  language contract (R7RS-small subset + the SRFIs above).
- **The capability assessment** — [`docs/capabilities.md`](docs/capabilities.md):
  the honest answer to "what is this good enough to build?" — the parity
  table, the documented gaps in three tiers, and the fitness-for-use verdict
  with the Python escape hatch spelled out.
- **The quant playbook** — [`docs/quant_stuffs/README.md`](docs/quant_stuffs/README.md):
  where strategy rules stay in Scheme and numeric kernels stay in Python,
  with the measured cost of the seam and the step-budget limits.
- **The release history** — [`CHANGELOG.md`](CHANGELOG.md): what each
  release changed, honestly.

## Security / trust model

Lisp code is **trusted code** — there is no sandbox. A script can `load`,
read/write files via ports, `eval`, and call any primitive you expose with
`install_primitives`. The host is the trust boundary: only publish primitives
you want Lisp to reach, and do not `run`/`load` untrusted input — it has the
same privilege as your Python process. This is by design for embedded DSL use
(game logic, policy layers, config). Hardening ledger: [`docs/HARDENING_TASKS.md`](docs/HARDENING_TASKS.md) H1.

## Embed it in your own Python project

```python
from shslisp import install_primitives, make_env, run

env = make_env()                       # a general Scheme, SRFIs preloaded
install_primitives(env, [("double", lambda n: n * 2)])
run("(double 21)", env)                # -> 42
```

The seam is declared, total, and loud: a host publishes a plain list of
`name -> callable` pairs; duplicates and non-callables are refused at install
time. See chapter 27 of the tutorial.

## Development

```sh
python -m pytest -q
```

The suite includes the tutorial's own harness: every `Try it` block in every
chapter is executed and its output compared with what the page shows.

## License

MIT — see [LICENSE](LICENSE). Built for personal use.
