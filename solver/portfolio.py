"""Question 6 -- Mode ``--mode optimized`` de sat.py : portfolio CDCL + DPLL.

Le CDCL (cdcl.py) résout en moins d'une seconde la quasi-totalité des
instances. Il existe pourtant une famille où il est battu par le DPLL de la
question 4 : le principe des tiroirs (``hole9`` : CDCL > 120 s, DPLL_H1
≈ 30 s). Ces formules sont si symétriques que toutes les heuristiques font
exactement le même nombre de décisions (9! - 1 pour ``hole9``, cf. Q5) :
l'apprentissage n'apporte rien et c'est le coût par nœud qui décide.

Stratégie (la machine de compétition accorde 4 CPU par exécution) :

1. lancer le CDCL seul pendant ``DELAY`` secondes -- c'est le cas de presque
   toutes les instances, sans aucun surcoût ;
2. s'il n'a pas conclu, démarrer dans un **processus fils** DPLL_H avec H1
   (heuristique au coût par décision le plus faible, la plus rapide sur
   ``hole9``) et poursuivre le CDCL dans le processus principal ;
3. retenir la première réponse ; le processus perdant est arrêté.

Un modèle renvoyé par le fils est vérifié contre toutes les clauses avant
d'être accepté (défense en profondeur : le mode ``optimized`` ne doit jamais
répondre faux). Le fils surveille le processus principal et s'arrête s'il
est tué (limite de temps de la compétition), pour ne pas lui survivre.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time

from .cdcl import CDCL
from .cnf import check_model

DELAY = 2.0          # s de CDCL seul avant de lancer le DPLL en parallèle
POLL = 0.25          # s de CDCL entre deux consultations du processus fils
HELPER_HEURISTIC = "H1"


def _watch_parent(ppid: int) -> None:
    """Arrête le processus fils dès que le processus principal disparaît.

    L'infrastructure de compétition tue ``sat.py`` (SIGKILL) à la limite de
    temps : sans cette surveillance, le DPLL continuerait, orphelin, à occuper
    un CPU pendant les instances suivantes. Sous Linux, un processus orphelin
    est rattaché à un autre parent : ``os.getppid()`` change."""
    while os.getppid() == ppid:
        time.sleep(0.1)
    os._exit(0)


def _dpll_worker(clauses, num_vars, conn, ppid) -> None:
    """Processus fils : DPLL_H, résultat envoyé par le tube."""
    from . import dpll_h

    threading.Thread(target=_watch_parent, args=(ppid,), daemon=True).start()
    try:
        sat, model, _ = dpll_h.solve(clauses, num_vars, HELPER_HEURISTIC)
        conn.send((sat, [model[v] for v in range(1, num_vars + 1)] if sat else None))
    except BaseException:       # échec du fils : le CDCL continue seul
        conn.send(None)
    finally:
        conn.close()


def _context():
    # fork (Linux) : démarrage immédiat, la formule déjà lue est partagée ;
    # spawn ailleurs (Windows), où fork n'existe pas.
    methods = mp.get_all_start_methods()
    return mp.get_context("fork" if "fork" in methods else "spawn")


def solve(clauses, num_vars: int, delay: float = DELAY):
    """Renvoie (sat, modèle complet ou None)."""
    s = CDCL(num_vars, clauses)
    try:
        sat = s.solve(timeout=delay)
        return sat, (s.model() if sat else None)
    except TimeoutError:
        pass

    ctx = _context()
    recv, send = ctx.Pipe(duplex=False)
    helper = ctx.Process(target=_dpll_worker, args=(clauses, num_vars, send, os.getpid()), daemon=True)
    helper.start()
    send.close()
    try:
        while True:
            try:
                sat = s.solve(timeout=POLL)
                return sat, (s.model() if sat else None)
            except TimeoutError:
                pass
            if recv.poll():
                try:
                    res = recv.recv()
                except EOFError:     # fils mort sans réponse
                    res = None
                if res is not None:
                    sat, values = res
                    if not sat:
                        return False, None
                    model = {v: values[v - 1] for v in range(1, num_vars + 1)}
                    if check_model(clauses, model):
                        return True, model
                # pas de réponse exploitable : le CDCL poursuit seul
                recv.close()
                recv = None
                break
        sat = s.solve()
        return sat, (s.model() if sat else None)
    finally:
        if helper.is_alive():
            helper.terminate()
        helper.join(1)
        if recv is not None:
            recv.close()
