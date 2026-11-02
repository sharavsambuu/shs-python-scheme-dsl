"""cores.py — one Mandelbrot row per worker: watch all your cores light up.

Run with:  python examples/concurrency/06-core-saturation/cores.py

The demonstrable sibling of 05-parallel-map. Same shape — a pool of worker
processes, each owning one `make_env()`, each running the SAME Scheme
function on different data — but scaled to one task per CPU core, with live
progress and an ASCII picture at the end.

The Scheme side is where the math lives: `mandelbrot-row` renders one row of
the set as a string of palette characters. Strings are the perfect cargo for
this trip: built in Scheme, shipped between processes, assembled in Python.
Each row is an independent task — embarrassingly parallel, the honest kind.

What to watch: the progress lines arrive in a burst (rows complete roughly
together), then the speedup line compares one core against all of them.
"""

import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from lisp import make_env, run, to_string

# --- the Scheme side -------------------------------------------------------------

WORKER_SOURCE = """
;; the escape-time iteration for one pixel; the palette indexes how soon
;; the orbit escaped (dark = escaped fast, @ = never escaped)
(define palette " .:-=+*#%@")

(define (mandelbrot-char cr ci max-iter)
  (let loop ((i 0) (zr 0.0) (zi 0.0))
    (cond ((> (+ (* zr zr) (* zi zi)) 4.0)
           (string-ref palette
                       (min 8 (quotient (* i 8) max-iter))))
          ((>= i max-iter) (string-ref palette 8))
          (else (loop (+ i 1)
                      (+ (- (* zr zr) (* zi zi)) cr)
                      (+ (* 2.0 zr zi) ci))))))

;; one row = `width` pixels; answers a string, the ideal cross-process cargo
(define (mandelbrot-row row width height max-iter)
  (let loop ((col 0) (out (string->list "")))
    (if (>= col width)
        (list->string (reverse out))
        (let ((cr (- (* 3.5 (/ col width)) 2.5))
              (ci (- (* 2.0 (/ row height)) 1.0)))
          (loop (+ col 1)
                (cons (mandelbrot-char cr ci max-iter) out))))))
"""

WIDTH, HEIGHT, MAX_ITER = 100, 48, 50

# --- the worker side ---------------------------------------------------------------

ENV = None


def worker_init() -> None:
    global ENV
    ENV = make_env(install_tetris=False)
    run(WORKER_SOURCE, ENV)


def render_row(row: int) -> tuple[int, str, float, int]:
    began = time.perf_counter()
    art = run(f"(mandelbrot-row {row} {WIDTH} {HEIGHT} {MAX_ITER})", ENV)
    return row, art, time.perf_counter() - began, mp.current_process().pid


def main() -> None:
    cores = mp.cpu_count()
    workers = min(cores, HEIGHT)
    print(f"== Mandelbrot {WIDTH}x{HEIGHT}, {MAX_ITER} iterations, on {cores} cores ==")
    print(f"(main) spawning {workers} env-per-process workers; "
          f"{HEIGHT} rows of Scheme float arithmetic\n")

    # --- the parallel render: rows distributed over all cores --------------------
    began = time.perf_counter()
    rows: dict[int, str] = {}
    with mp.Pool(processes=workers, initializer=worker_init) as pool:
        for row, art, spent, pid in pool.imap_unordered(render_row, range(HEIGHT)):
            rows[row] = art
            print(f"  [pid {pid}] row {row:>2} rendered in {spent:.3f}s")
    par_time = time.perf_counter() - began

    # --- the sequential render: one core, same rows -------------------------------
    print("\n(main) now the same render on one core...")
    seq_env = make_env(install_tetris=False)
    run(WORKER_SOURCE, seq_env)
    began = time.perf_counter()
    for row in range(HEIGHT):
        run(f"(mandelbrot-row {row} {WIDTH} {HEIGHT} {MAX_ITER})", seq_env)
    seq_time = time.perf_counter() - began

    print(f"\n== the picture ({HEIGHT} rows, all computed by Scheme) ==")
    for row in range(HEIGHT):
        print(rows[row])

    print(f"\n  one core:   {seq_time:7.3f}s")
    print(f"  {workers} cores: {par_time:7.3f}s")
    print(f"  speedup:    {seq_time / par_time:7.2f}x")
    print("\n  Every character above was computed by the Scheme interpreter —"
          "\n  the cores were busy because the WORK was shaped for them.")


if __name__ == "__main__":
    main()
