;; Exercise, chapter 06 — a hygienic `unless-not`.
;;
;; The chapter asks for a macro that expands `(unless-not test body ...)` to
;; `(when (not test) body ...)`. This file is the worked answer, and the point
;; is what the *caller's* names do: `t` below is the caller's, and the template
;; cannot touch it.
;;
;;   ../python_tetris/env/bin/python -m lisp run \
;;       docs/lisp_tutorial/exercises/unless-not.scm --no-tetris

(define-syntax unless-not
  (syntax-rules ()
    ((_ test body ...) (when (not test) body ...))))

;; 1. The plain case: the body runs only when the test is false.
(display (unless-not #f "ran"))          ; ran
(newline)
(display (unless-not #t "did not run"))  ; () — `when` is one-armed
(newline)

;; 2. The hygienic case: `t` here is the caller's, and the macro leaves it alone.
(define t 99)
(display (unless-not #f t))              ; 99, not a captured temporary
(newline)
