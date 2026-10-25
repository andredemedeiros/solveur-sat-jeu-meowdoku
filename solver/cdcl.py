"""Question 6 -- Solveur optimisé (mode ``--mode optimized`` de sat.py).

Conclusion de la question 5 : sur les instances Meowdoku comme sur les
instances aléatoires, le coût de DPLL « par copie de formule » est dominé
(1) par la reconstruction de F à chaque nœud, O(|F|), et (2) par la
ré-exploration de sous-arbres d'échec identiques (aucune mémoire des
conflits). Le solveur optimisé conserve le principe DPLL (propagation
unitaire + branchement + retour arrière) mais remplace chaque composant :

* structures incrémentales : affectation par littéral (tableau), pile
  d'affectation (trail) et niveaux de décision -- le retour arrière consiste
  à dépiler, sans recopier la formule ;
* propagation unitaire par **2 littéraux surveillés** (watched literals),
  avec un traitement dédié des clauses binaires (majoritaires dans
  l'encodage Meowdoku : contraintes « au plus un ») ;
* **apprentissage de clauses** (analyse de conflit 1-UIP, minimisation
  locale) et retour arrière non chronologique (backjumping) ;
* heuristique de branchement **VSIDS** : version dynamique et à coût quasi
  nul de « variable la plus fréquente dans les conflits récents » ;
  sauvegarde de phase (polarité initiale négative : dans Meowdoku, la
  quasi-totalité des x_ij sont fausses) ;
* **redémarrages** selon la suite de Luby et **nettoyage** périodique des
  clauses apprises (critère LBD, Audemard & Simon 2009).

Codage des littéraux : x_v -> 2v, ¬x_v -> 2v+1 ; la négation est ``l ^ 1``
et la variable ``l >> 1``. ``val[l]`` vaut 1 (vrai), -1 (faux) ou 0.
"""

from __future__ import annotations

import time
from heapq import heapify, heappop, heappush


def luby(x: int) -> int:
    """x-ième terme (x ≥ 0) de la suite de Luby 1,1,2,1,1,2,4,1,1,2,...
    (même calcul que MiniSat)."""
    size, seq = 1, 0
    while size < x + 1:
        seq += 1
        size = 2 * size + 1
    while size - 1 != x:
        size = (size - 1) >> 1
        seq -= 1
        x %= size
    return 1 << seq


class CDCL:
    RESTART_BASE = 100
    VAR_DECAY = 0.95
    MIN_LEARNTS = 2000
    CHECK_MASK = 255     # délai contrôlé toutes les CHECK_MASK + 1 décisions

    def __init__(self, num_vars: int, clauses):
        n = num_vars
        self.n = n
        self.val = [0] * (2 * n + 2)
        self.level = [0] * (n + 1)
        self.reason = [None] * (n + 1)
        self.seen = [0] * (n + 1)
        self.phase = [1] * (n + 1)          # 1 = polarité négative
        self.activity = [0.0] * (n + 1)
        self.var_inc = 1.0
        self.trail: list[int] = []
        self.trail_lim: list[int] = []
        self.qhead = 0
        self.watches = [[] for _ in range(2 * n + 2)]
        self.bins = [[] for _ in range(2 * n + 2)]
        self.clauses: list[list[int]] = []
        self.learnts: list[list[int]] = []
        self.learnt_lbd: list[int] = []
        self.ok = True
        self.conflicts = 0
        self.decisions = 0
        # état des redémarrages / du nettoyage, conservé entre deux appels à
        # solve() (recherche interrompue par un délai puis reprise : portfolio.py)
        self.started = False
        self.restart_idx = 0
        self.conflicts_here = 0
        self.max_learnts = 0
        for c in clauses:
            if not self.add_clause(c):
                self.ok = False
                break
        self.heap = [(0.0, v) for v in range(1, n + 1)]
        heapify(self.heap)

    # ------------------------------------------------------------------ #
    # Clauses
    # ------------------------------------------------------------------ #
    def add_clause(self, dimacs_lits) -> bool:
        """Ajout d'une clause au niveau 0 (avant la recherche) : suppression
        des doublons, des tautologies, des littéraux faux et des clauses
        satisfaites au niveau 0. Chemin rapide pour les clauses binaires
        (majoritaires dans les instances Meowdoku)."""
        c = [(x << 1) if x > 0 else ((-x << 1) | 1) for x in dimacs_lits]
        if len(c) == 2:
            a, b = c
            if a == b:
                c = [a]
            elif a ^ 1 == b:
                return True            # tautologie
        elif len(c) > 2:
            st = set(c)
            for l in st:
                if l ^ 1 in st:
                    return True        # tautologie
            if len(st) < len(c):
                c = list(st)
        if self.trail:                 # des littéraux sont déjà fixés au niveau 0
            val = self.val
            if any(val[l] == 1 for l in c):
                return True
            c = [l for l in c if val[l] == 0]
        if not c:
            return False               # clause vide
        if len(c) == 1:
            return self._enqueue(c[0], None)
        if len(c) == 2:
            a, b = c
            self.bins[a].append((b, c))
            self.bins[b].append((a, c))
        else:
            self.watches[c[0]].append(c)
            self.watches[c[1]].append(c)
        self.clauses.append(c)
        return True

    def _enqueue(self, l: int, reason) -> bool:
        v = self.val[l]
        if v == -1:
            return False
        if v == 0:
            self.val[l] = 1
            self.val[l ^ 1] = -1
            self.level[l >> 1] = len(self.trail_lim)
            self.reason[l >> 1] = reason
            self.trail.append(l)
        return True

    # ------------------------------------------------------------------ #
    # Propagation unitaire (2-watched literals)
    # ------------------------------------------------------------------ #
    def propagate(self):
        """Renvoie la clause en conflit, ou None."""
        val = self.val
        trail = self.trail
        watches = self.watches
        bins = self.bins
        level = self.level
        reason = self.reason
        lvl = len(self.trail_lim)
        qhead = self.qhead
        while qhead < len(trail):
            fl = trail[qhead] ^ 1            # littéral devenu faux
            qhead += 1
            # -- clauses binaires : implication directe
            for q, c in bins[fl]:
                vq = val[q]
                if vq == 0:
                    val[q] = 1
                    val[q ^ 1] = -1
                    level[q >> 1] = lvl
                    reason[q >> 1] = c
                    trail.append(q)
                elif vq == -1:
                    self.qhead = qhead
                    return c
            # -- clauses longues : déplacement du littéral surveillé
            ws = watches[fl]
            i = j = 0
            n = len(ws)
            while i < n:
                c = ws[i]
                i += 1
                if c[0] == fl:
                    c[0] = c[1]
                    c[1] = fl
                first = c[0]
                if val[first] == 1:
                    ws[j] = c
                    j += 1
                    continue
                for k in range(2, len(c)):
                    l = c[k]
                    if val[l] != -1:
                        c[1] = l
                        c[k] = fl
                        watches[l].append(c)
                        break
                else:
                    ws[j] = c
                    j += 1
                    if val[first] == -1:
                        ws[j:] = ws[i:]
                        self.qhead = qhead
                        return c
                    val[first] = 1
                    val[first ^ 1] = -1
                    level[first >> 1] = lvl
                    reason[first >> 1] = c
                    trail.append(first)
            del ws[j:]
        self.qhead = qhead
        return None

    # ------------------------------------------------------------------ #
    # Analyse de conflit 1-UIP
    # ------------------------------------------------------------------ #
    def _bump(self, v: int) -> None:
        act = self.activity
        a = act[v] + self.var_inc
        act[v] = a
        if a > 1e100:
            for u in range(1, self.n + 1):
                act[u] *= 1e-100
            self.var_inc *= 1e-100
            self._rebuild_heap()
        elif self.val[v << 1] == 0:
            heappush(self.heap, (-a, v))

    def _rebuild_heap(self) -> None:
        act, val = self.activity, self.val
        self.heap = [(-act[v], v) for v in range(1, self.n + 1) if val[v << 1] == 0]
        heapify(self.heap)

    def analyze(self, confl):
        seen = self.seen
        level = self.level
        reason = self.reason
        trail = self.trail
        cur = len(self.trail_lim)
        learnt = [0]
        path = 0
        p = -1
        idx = len(trail) - 1
        c = confl
        while True:
            for q in c:
                if q == p:
                    continue
                v = q >> 1
                if not seen[v] and level[v] > 0:
                    seen[v] = 1
                    self._bump(v)
                    if level[v] >= cur:
                        path += 1
                    else:
                        learnt.append(q)
            while not seen[trail[idx] >> 1]:
                idx -= 1
            p = trail[idx]
            idx -= 1
            v = p >> 1
            c = reason[v]
            seen[v] = 0
            path -= 1
            if path == 0:
                break
        learnt[0] = p ^ 1

        # Minimisation locale : q est redondant si tous les autres littéraux
        # de sa raison sont déjà dans la clause apprise (ou au niveau 0).
        out = [learnt[0]]
        for q in learnt[1:]:
            r = reason[q >> 1]
            if r is None:
                out.append(q)
                continue
            nq = q ^ 1
            for x in r:
                if x != nq and not seen[x >> 1] and level[x >> 1] > 0:
                    out.append(q)
                    break
        for q in learnt[1:]:
            seen[q >> 1] = 0

        # Niveau de retour : le plus haut parmi les autres littéraux, placé
        # en position 1 (second littéral surveillé).
        bt = 0
        if len(out) > 1:
            mi = 1
            for i in range(2, len(out)):
                if level[out[i] >> 1] > level[out[mi] >> 1]:
                    mi = i
            out[1], out[mi] = out[mi], out[1]
            bt = level[out[1] >> 1]
        lbd = len({level[q >> 1] for q in out})
        return out, bt, lbd

    # ------------------------------------------------------------------ #
    def cancel_until(self, lvl: int) -> None:
        if len(self.trail_lim) <= lvl:
            return
        val, reason, phase, act, heap = self.val, self.reason, self.phase, self.activity, self.heap
        trail = self.trail
        lim = self.trail_lim[lvl]
        for i in range(len(trail) - 1, lim - 1, -1):
            l = trail[i]
            v = l >> 1
            val[l] = 0
            val[l ^ 1] = 0
            reason[v] = None
            phase[v] = l & 1
            heappush(heap, (-act[v], v))
        del trail[lim:]
        del self.trail_lim[lvl:]
        self.qhead = lim
        if len(heap) > 8 * self.n + 1000:
            self._rebuild_heap()

    def pick_branch(self):
        heap, val, act = self.heap, self.val, self.activity
        while heap:
            a, v = heappop(heap)
            if val[v << 1] == 0 and -a == act[v]:
                return v
        return None

    def reduce_db(self) -> None:
        """Supprime la moitié des clauses apprises de plus mauvais LBD
        (on garde les « glue clauses » LBD ≤ 2 et les clauses raisons)."""
        reason, val = self.reason, self.val
        items = sorted(zip(self.learnt_lbd, self.learnts), key=lambda t: -t[0])
        limit = len(items) // 2
        keep_c, keep_l = [], []
        removed = 0
        for lbd, c in items:
            locked = val[c[0]] == 1 and reason[c[0] >> 1] is c
            if removed < limit and lbd > 2 and not locked:
                removed += 1
            else:
                keep_c.append(c)
                keep_l.append(lbd)
        self.learnts, self.learnt_lbd = keep_c, keep_l
        watches = [[] for _ in range(2 * self.n + 2)]
        for lst in (self.clauses, self.learnts):
            for c in lst:
                if len(c) > 2:
                    watches[c[0]].append(c)
                    watches[c[1]].append(c)
        self.watches = watches

    # ------------------------------------------------------------------ #
    def solve(self, timeout: float = float("inf")) -> bool:
        """True (SAT) / False (UNSAT) ; lève TimeoutError au-delà de ``timeout`` s.

        Le délai n'est contrôlé que juste après une décision : la propagation
        précédente s'est terminée sans conflit et le littéral de décision
        attend dans la pile, exactement l'état du début d'une itération. Un
        nouvel appel à solve() reprend donc la recherche là où elle s'était
        arrêtée (pile, clauses apprises, activités, suite de Luby conservées).
        Chaque appel fait au moins une décision : la reprise progresse."""
        deadline = time.perf_counter() + timeout
        if not self.ok:
            return False
        if not self.started:
            self.started = True
            if self.propagate() is not None:
                self.ok = False
                return False
            self.max_learnts = max(self.MIN_LEARNTS, len(self.clauses) // 3)
        decay = 1.0 / self.VAR_DECAY
        restart_limit = luby(self.restart_idx) * self.RESTART_BASE
        ticks = 0            # décisions prises pendant cet appel
        while True:
            confl = self.propagate()
            if confl is not None:
                self.conflicts += 1
                self.conflicts_here += 1
                if not self.trail_lim:
                    self.ok = False
                    return False
                learnt, bt, lbd = self.analyze(confl)
                self.cancel_until(bt)
                if len(learnt) == 1:
                    self._enqueue(learnt[0], None)
                elif len(learnt) == 2:
                    a, b = learnt
                    self.bins[a].append((b, learnt))
                    self.bins[b].append((a, learnt))
                    self._enqueue(a, learnt)
                else:
                    self.watches[learnt[0]].append(learnt)
                    self.watches[learnt[1]].append(learnt)
                    self.learnts.append(learnt)
                    self.learnt_lbd.append(lbd)
                    self._enqueue(learnt[0], learnt)
                self.var_inc *= decay
                if self.conflicts_here >= restart_limit:
                    self.conflicts_here = 0
                    self.restart_idx += 1
                    restart_limit = luby(self.restart_idx) * self.RESTART_BASE
                    self.cancel_until(0)
                if len(self.learnts) >= self.max_learnts + len(self.trail):
                    self.reduce_db()
                    self.max_learnts = int(self.max_learnts * 1.1)
            else:
                v = self.pick_branch()
                if v is None:
                    return True
                self.decisions += 1
                self.trail_lim.append(len(self.trail))
                self._enqueue((v << 1) | self.phase[v], None)
                ticks += 1
                if not ticks & self.CHECK_MASK and time.perf_counter() > deadline:
                    raise TimeoutError

    def model(self) -> dict[int, bool]:
        val = self.val
        return {v: val[v << 1] == 1 for v in range(1, self.n + 1)}


def solve(clauses, num_vars: int):
    s = CDCL(num_vars, clauses)
    sat = s.solve()
    return sat, (s.model() if sat else None)
