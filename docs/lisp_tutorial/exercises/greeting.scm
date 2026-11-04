;; Exercise, chapter 08 — a module that loads by bare name.
;;
;; Create this file (or use this one), put its directory on the search path,
;; and load it twice: the second load is a no-op and `(loaded-modules)` lists it
;; once.
;;
;;   ../python_tetris/env/bin/python -m lisp run \
;;       docs/lisp_tutorial/exercises/greeting.scm --no-tetris

(define (hello name)
  (string-append "hello, " name))
