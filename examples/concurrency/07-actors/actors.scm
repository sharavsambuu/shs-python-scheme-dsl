;; actors.scm — the actor loop every actor runs, in six lines.
;;
;; Loaded by each actor's thread into that actor's own environment. An actor
;; is: a mailbox (a Python queue), a behavior (`handle`), and this loop. The
;; loop is tail-recursive, so it runs forever without growing the stack.
;;
;; `handle` is provided by whoever spawns the actor (see the BEHAVIORS in
;; actors.py); it receives the current state and one message, and answers
;; the next state. State never leaves the actor — that is the whole model.

(define (actor-loop state)
  (let ((msg (recv!)))
    (if (eq? msg 'stop)
        (begin (log "received stop; goodbye") 'stopped)
        (actor-loop (handle state msg)))))
