;; announcement.scm — a tiny library: one function, one value.
;; Loaded by the chapter-07 module example (and by `shs` via the load path).

(define (announce who)
  (string-append "hello, " who))

"announcement-loaded"
