# Installing shs

`shs` is one pure-standard-library Python package. There is nothing to compile
and nothing to download besides the source itself: any Python **3.11 or newer**
with `pip` is the whole requirement list. (3.11 is a hard floor, not a
suggestion: the evaluator's million-deep recursion ceiling relies on 3.11's
stackless Python-to-Python calls, so on 3.10 a deep non-tail recursion in the
REPL would exhaust the C stack instead of raising a Lisp error.)

## 1. Pick an install method

### From a clone (best if you want to read or hack on the interpreter)

```sh
git clone https://github.com/sharavsambuu/shs-python-scheme-dsl
cd shs-python-scheme-dsl
pip install .
```

### Straight from GitHub (best for using it in a project)

The `git+` prefix is **mandatory** — without it pip treats the URL as a
downloadable archive and fails with `cannot detect archive format`:

```sh
pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git
```

Pinned to a tag or commit, for a project that depends on a known version:

```sh
pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git@v0.1.0
```

In your project's requirements.txt, the same line without the leading `pip install`:

```
shs @ git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git@v0.1.0
```

### From PyPI — not us (yet, and never under this name)

There **is** a package called `shs` on PyPI, but it is an unrelated project
("Security Hygiene Scanner") — `pip install shs` will *not* give you this
language. Our distribution is published — or will be — as **`shs-scheme-dsl`**:

```sh
pip install shs-scheme-dsl          # once published; the `shs` command it
                                    # installs is the one this manual documents
```

Until then, install from GitHub as shown above.

## 2. Verify the install

Both the command and the importable module are installed together:

```sh
shs --version                      # shs 0.1.0
shs -e "(fold + 0 (iota 5 1))"     # 15  (SRFI 1 is pre-imported)

python -c "import lisp; print(lisp.run('(+ 40 2)'))"   # 42
```

Then take it for a spin:

```sh
shs                                # the REPL; ,help inside, ,quit to leave
```

The runnable examples live in the repository's `examples/` directory — they are
not copied into site-packages, so to run them, be inside a clone:

```sh
shs run examples/fizzbuzz.scm      # from your clone of the project
```

## 3. Where things land

| Name | What it is |
| --- | --- |
| `shs` | the command: REPL, `run`, `-e`, `--profile` (an alias `lisppy` also exists) |
| `lisp` | the Python package a host project imports (`make_env`, `run`, `install_primitives`) |
| `SHS_PATH` | optional environment variable: extra module directories, `os.pathsep`-separated (`:` on Unix, `;` on Windows) |

The working directory is always on the load path, so `shs run program.scm`
resolves `(load "my-module")` relative to where you invoke it — no
configuration needed for the common case.

## 4. Notes and troubleshooting

- **Use a virtualenv if you can** (`python3 -m venv .venv && source .venv/bin/activate`).
  The package installs cleanly anywhere — it has zero dependencies — but a venv
  keeps the `shs` command scoped to the project that uses it.
- **`Cannot unpack file … cannot detect archive format`** — you forgot the
  `git+` prefix. Use `pip install git+https://…`, not `pip install https://…`.
- **`pip install shs` installed something strange** — that PyPI name belongs
  to an unrelated project ("Security Hygiene Scanner"). Uninstall it
  (`pip uninstall shs`) and install ours from GitHub or as `shs-scheme-dsl`
  (see §1).
- **`shs: command not found` after installing** — the Scripts/bin directory of
  your Python environment is not on `PATH`. Inside a venv, activate the venv
  first; for a system Python, ensure `$(python3 -m site --user-base)/bin` is
  on `PATH`.
- **Upgrading** — re-run the same install command; pip re-installs over the
  old version. For a clone, `git pull` first.
- **Uninstalling** — `pip uninstall shs` removes the package, the `shs`
  command, and the `lisppy` alias.
- **Threads** — one `Environment` is not safe to share across Python threads;
  give each thread its own `make_env()`.

## 5. What next

- The tutorial: [`lisp_tutorial/README.md`](lisp_tutorial/README.md) — from
  "Lisp in ten minutes" to the SRFI layer.
- The one-stop language reference: [`language.md`](language.md).
- Embedding in your own project: [`lisp_tutorial/27-embedding-in-python.md`](lisp_tutorial/27-embedding-in-python.md)
  and the runnable [`examples/embed_inventory_host.py`](../examples/embed_inventory_host.py).
