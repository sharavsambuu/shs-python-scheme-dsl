"""A deliberately generic host: an inventory store, no games in sight.

Run with:  python examples/embed_inventory_host.py

Shows the three things a random Python project needs from the DSL:
1. a stateful Python object driven by Lisp policy;
2. Python exceptions crossing the seam and being caught as Lisp data;
3. the SRFI layer (1, 197, guard) working over host facts.
"""
from lisp import install_primitives, make_env, run


class Inventory:
    def __init__(self):
        self.stock = {}

    def add(self, sku, qty):
        self.stock[sku] = self.stock.get(sku, 0) + qty
        return qty

    def take(self, sku, qty):
        have = self.stock.get(sku, 0)
        if have < qty:
            raise ValueError(f"short: have {have}, want {qty}")
        self.stock[sku] = have - qty
        return qty

    def level(self, sku):
        return self.stock.get(sku, 0)


inv = Inventory()
env = make_env()  # a general Scheme; the SRFI profile is preloaded
install_primitives(
    env,
    [
        ("inv-add!", inv.add),
        ("inv-take!", inv.take),
        ("inv-level", inv.level),
    ],
    source="inventory-demo",
)

program = """
(define (ship! sku qty)
  (if (= (inv-level sku) 0) (list 'skip sku)
      (begin (inv-take! sku qty) (list 'shipped sku qty))))

(for-each (lambda (p) (inv-add! (car p) (cadr p)))
          '(("widget" 10) ("gizmo" 3)))

(display (list 'total (fold + 0 (map inv-level '("widget" "gizmo"))))) (newline)
(display (chain-and (inv-level "widget") (* _ 2) (< _ 50))) (newline)
(display (guard (e (#t (list 'refused (error-object-message e))))
           (inv-take! "gizmo" 99))) (newline)
(display (ship! "widget" 4)) (newline)
"""

run(program, env)
print("python sees:", inv.stock)
