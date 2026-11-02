# 08 · supervision — let it crash, restart with fresh state, give up

```sh
python examples/concurrency/08-supervision/supervision.py
```

Erlang's one big idea: an actor that hits an error does not patch itself up
mid-flight — it **crashes**, its supervisor notices, and the actor comes
back fresh: same behavior, **clean state**. This is 07-actors's machinery
with one addition: the actor's thread wraps the loop in try/except, so a
`LispError` escaping the loop *is* the crash signal — no new vocabulary.
The interpreter's own error objects are what crosses the boundary, which
makes the supervisor's decision data-driven (`last words: ...`).

## The transcript's story

```
count -> 42, count -> 142          # state builds
supervisor: crashed — restarting 1/3, state reset
count -> 10, count -> 42           # climbing again — from zero
...three crashes...                # each life starts from 0
supervisor: used all 3 restarts — giving up, actor declared dead
supervisor: last words: counter: poisoned state detected
```

## What to notice

- The behavior contains **no error handling at all** — crashing is its
  whole strategy; recovery is the supervisor's job. Business logic and
  error policy never touch.
- "State reset" is visible: after every restart the count climbs from zero,
  because state was never meant to survive a crash.
- A dead actor's mailbox still accepts mail — it just holds it. The
  supervisor outlives the actor; the caller decides what dead means.
- If a behavior wants to handle a *specific* failure itself, `guard`
  composes: handle what you can, crash on the rest (04 shows guard
  catching nursery errors as data).
