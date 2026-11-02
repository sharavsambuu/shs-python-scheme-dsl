;; actor_loop.scm — the supervision edition's actor loop (same six lines as
;; 07-actors). `handle` is supplied by the behavior source that loads this.

(define (actor-loop state)
  (let ((m (recv!)))
    (if (eq? m 'stop)
        (begin (log "clean stop") state)
        (actor-loop (handle state m)))))
