# 07 · actors — private state, mailboxes, request/reply

```sh
python examples/concurrency/07-actors/actors.py
```

The actor pattern, on this little stage:

- an **actor** is a mailbox (`queue.Queue`) plus a behavior loop in its own
  `make_env()` on its own thread;
- messages are the only traffic in or out — typically Scheme lists like
  `(add 5)`, dispatched by `car` (or `variant-match`, SRFI 241, if you want
  exhaustive dispatch);
- **state is private and lives in the loop's argument** — nothing else can
  reach it, which is why the transcript needs zero locks around the work.

The demo runs three actors: a counter (messages mutate only its own
state), a request/reply exchange with the main thread (`(get 'main)` sends
the answer back to an address, like Erlang's `!` with self()), and a
five-round ping-pong conversation between two actors, printed as a
timestamped interleaved transcript.

## The one seam sharp edge

Scheme `(eq? msg 'add)` compares against an interned **Symbol**; a Python
`str` `"add"` would never match. Host-built messages go through the
`msg()` helper, which interns strings — `msg("add", 10)` *is* `(add 10)`.
Bare control symbols (`begin`, `stop`) are sent with `intern()` directly.

## What to notice

- The actor loop is six lines of Scheme (actors.scm) — the whole runtime
  is the spawn machinery plus a dict of mailboxes.
- Sending is **fire-and-forget**: `(send! 'counter ...)` returns before the
  counter ever processes the message; the request/reply exchange shows how
  asynchrony becomes a conversation anyway.
- All actors stop via the one message every actor understands — `'stop` —
  and the join proves the threads end.
