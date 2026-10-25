#!/usr/bin/env python3
"""Question 5 -- Analyse des mesures (results/benchmark/bench.csv) : tableaux Markdown
(results/benchmark/tables.md) et figures (results/benchmark/fig_*.png).

    python experiments/analyze.py [--csv results/benchmark/bench.csv]
"""
import argparse
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# palette de référence (skill dataviz), ordre fixe
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
GREY = "#a9a8a4"
INK, INK2 = "#0b0b0b", "#52514e"

NAMES = {"alg2": "Alg2 (aléatoire)", "cdcl": "CDCL (optimisé)", "dpllh:H0": "H0 CA", "dpllh:H1": "H1 PVL",
         "dpllh:H2s": "H2s VPPM", "dpllh:H2d": "H2d VPPM", "dpllh:H3s": "H3s LP", "dpllh:H3d": "H3d LP",
         "dpllh:H4s": "H4s VFCM", "dpllh:H4d": "H4d VFCM", "dpllh:H5s": "H5s LFCM", "dpllh:H5d": "H5d LFCM",
         "dpllh:H6s": "H6s VJW", "dpllh:H6d": "H6d VJW", "dpllh:H7s": "H7s LJW", "dpllh:H7d": "H7d LJW",
         "dpllh:H8": "H8 MOMS-P", "dpllh:H9": "H9 MRV"}
ORDER = list(NAMES)


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GREY)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(True, color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)


def gmean(x):
    x = np.asarray(x, dtype=float)
    return float(np.exp(np.mean(np.log(np.maximum(x, 1e-4))))) if len(x) else float("nan")


def md(df, floatfmt="{:.3g}"):
    cols = list(df.columns)
    out = ["| " + " | ".join([df.index.name or ""] + cols) + " |",
           "|" + "---|" * (len(cols) + 1)]
    for idx, row in df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append("—" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join([str(idx)] + cells) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/benchmark/bench.csv")
    ap.add_argument("--outdir", default="results/benchmark")
    ap.add_argument("--timeout", type=float, default=20,
                    help="limite utilisée par benchmark.py (PAR-2 = 2 × limite)")
    a = ap.parse_args()
    df = pd.read_csv(a.csv)
    # limite nominale : le temps mesuré d'une exécution interrompue la dépasse
    # légèrement (délai contrôlé tous les 64 nœuds)
    T = a.timeout
    df["solved"] = df.status != "TIMEOUT"
    df["name"] = df.solver.map(NAMES)
    df["par2"] = np.where(df.solved, df.cpu, 2 * T)
    df["truth"] = df.expected
    solvers = [s for s in ORDER if s in set(df.solver)]
    out = [f"# Résultats de la campagne (Question 5)\n\nLimite de temps CPU : {T:.0f} s par exécution. "
           f"PAR-2 : temps CPU, une exécution non terminée comptant 2×{T:.0f} s. Solveurs aléatoires "
           f"(Alg2, H0) : 3 graines, chaque exécution comptée séparément.\n"]

    wrong = df[df.correct == False]  # noqa: E712
    out.append(f"Réponses incorrectes : **{len(wrong)}** sur {len(df)} exécutions.\n")

    # ---------------- tableau global ----------------
    rows = []
    for s in solvers:
        d = df[df.solver == s]
        n_inst = d.instance.nunique()
        rows.append({"solveur": NAMES[s],
                     "résolues %": 100 * d.solved.mean(),
                     "SAT %": 100 * d[d.truth == "SAT"].solved.mean(),
                     "UNSAT %": 100 * d[d.truth == "UNSAT"].solved.mean(),
                     "PAR-2 moy (s)": d.par2.mean(),
                     "CPU géo (s)": gmean(d.par2),
                     "ratio heur. %": 100 * d[d.solved].heur_ratio.mean() if "heur_ratio" in d else np.nan})
    g = pd.DataFrame(rows).set_index("solveur")
    out.append("## Vue globale\n\n" + md(g) + "\n")

    # ---------------- compteurs sur les instances résolues par tous les DPLL_H ----------------
    dh = df[df.solver.str.startswith("dpllh") | (df.solver == "alg2")]
    common = dh.groupby("instance").solved.all()
    common = set(common[common].index)
    out.append(f"## Compteurs (moyennes géométriques sur les {len(common)} instances résolues par tous les "
               "solveurs DPLL)\n")
    for cat in ["3-SAT", "structuré", "Meowdoku"]:
        for truth in ["SAT", "UNSAT"]:
            sub = dh[dh.instance.isin(common) & (dh.category == cat) & (dh.truth == truth)]
            if sub.empty:
                continue
            rows = []
            for s in solvers:
                d = sub[sub.solver == s]
                if d.empty:
                    continue
                rows.append({"solveur": NAMES[s], "décisions": gmean(d.decisions + 1) - 1,
                             "retours arr.": gmean(d.backtracks + 1) - 1,
                             "prop. unit.": gmean(d.unit_props + 1) - 1,
                             "lit. purs": gmean(d.pure_lits + 1) - 1,
                             "nœuds": gmean(d.nodes), "CPU (ms)": 1000 * gmean(d.cpu),
                             "heur. %": 100 * d.heur_ratio.mean()})
            t = pd.DataFrame(rows).set_index("solveur")
            out.append(f"### {cat} — {truth} ({sub.instance.nunique()} instances)\n\n" + md(t) + "\n")

    # ---------------- par famille : % résolu et PAR-2 ----------------
    piv = df.pivot_table(index="family", columns="name", values="solved", aggfunc="mean") * 100
    piv = piv[[NAMES[s] for s in solvers]]
    out.append("## Taux de résolution (%) par famille\n\n" + md(piv.round(0), "{:.0f}") + "\n")
    piv2 = df.pivot_table(index="family", columns="name", values="par2", aggfunc=gmean)
    piv2 = piv2[[NAMES[s] for s in solvers]]
    out.append("## CPU (moyenne géométrique PAR-2, s) par famille\n\n" + md(piv2) + "\n")

    # ---------------- statique vs dynamique ----------------
    rows = []
    for i in range(2, 8):
        s, d_ = f"dpllh:H{i}s", f"dpllh:H{i}d"
        if s not in solvers or d_ not in solvers:
            continue
        A = df[df.solver == s].set_index("instance")
        B = df[df.solver == d_].set_index("instance")
        both = A.index[A.solved & B.loc[A.index].solved]
        rows.append({"heuristique": f"H{i}", "résolues s": int(A.solved.sum()), "résolues d": int(B.solved.sum()),
                     "décisions d/s": gmean((B.loc[both].decisions + 1) / (A.loc[both].decisions + 1)),
                     "CPU d/s": gmean(B.loc[both].cpu / A.loc[both].cpu.clip(lower=1e-4)),
                     "heur. % s": 100 * A.loc[both].heur_ratio.mean(),
                     "heur. % d": 100 * B.loc[both].heur_ratio.mean()})
    if rows:
        out.append("## Statique vs dynamique (rapports géométriques sur les instances résolues par les deux)\n\n"
                   + md(pd.DataFrame(rows).set_index("heuristique")) + "\n")

    # ---------------- Meowdoku : effet des clauses redondantes ----------------
    m = df[df.family.isin(["meow_sat", "meow_nored"])].copy()
    if not m.empty:
        m["grid"] = m.instance.map(lambda p: re.split(r"[\\/]", p)[-1])  # séparateur Windows ou Linux
        rows = []
        for s in solvers:
            A = m[(m.solver == s) & (m.family == "meow_sat")].set_index(["grid", "seed"])
            B = m[(m.solver == s) & (m.family == "meow_nored")].set_index(["grid", "seed"])
            idx = A.index.intersection(B.index)
            ok = A.loc[idx].solved & B.loc[idx].solved
            rows.append({"solveur": NAMES[s], "résolues avec": int(A.solved.sum()), "résolues sans": int(B.solved.sum()),
                         "CPU sans/avec": gmean(B.loc[idx][ok].cpu.clip(lower=1e-4) / A.loc[idx][ok].cpu.clip(lower=1e-4)),
                         "décisions sans/avec": gmean((B.loc[idx][ok].decisions.fillna(0) + 1) /
                                                      (A.loc[idx][ok].decisions.fillna(0) + 1))})
        out.append("## Meowdoku : clauses redondantes L≥1 / C≥1\n\n" + md(pd.DataFrame(rows).set_index("solveur")) + "\n")

    with open(os.path.join(a.outdir, "tables.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    # ================= figures =================
    sel = [s for s in ["alg2", "dpllh:H1", "dpllh:H2d", "dpllh:H4d", "dpllh:H6d", "dpllh:H8", "dpllh:H9", "cdcl"]
           if s in solvers]
    # cactus (solveurs aléatoires : graine 0 seulement, une courbe = une exécution par instance)
    d0 = df[df.solved & (df.seed == 0)]
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    for s in solvers:
        if s in sel:
            continue
        t = np.sort(d0[d0.solver == s].cpu.values)
        ax.plot(np.arange(1, len(t) + 1), t, color=GREY, linewidth=1, alpha=.6)
    for k, s in enumerate(sel):
        t = np.sort(d0[d0.solver == s].cpu.values)
        ax.plot(np.arange(1, len(t) + 1), t, color=C[k], linewidth=2, label=NAMES[s])
    ax.set_yscale("log")
    ax.set_xlabel("nombre d'instances résolues", color=INK2)
    ax.set_ylabel("temps CPU (s), échelle log", color=INK2)
    ax.set_title("Instances résolues en fonction du temps (gris : autres heuristiques)", color=INK, fontsize=10, loc="left")
    style(ax)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(a.outdir, "fig_cactus.png"))
    plt.close(fig)

    # Meowdoku : temps en fonction de N
    mm = df[df.family == "meow_sat"].copy()
    if not mm.empty:
        mm["N"] = mm.instance.map(lambda p: int(re.search(r"_(\d+)x", p).group(1)))
        fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
        for k, s in enumerate(sel):
            d = mm[mm.solver == s].groupby("N").par2.apply(gmean)
            ax.plot(d.index, d.values, color=C[k], linewidth=2, marker="o", markersize=4, label=NAMES[s])
        ax.set_yscale("log")
        ax.set_xticks(sorted(mm.N.unique()))
        ax.set_xlabel("taille de grille N (= M = K)", color=INK2)
        ax.set_ylabel("CPU PAR-2, moy. géo. (s)", color=INK2)
        ax.set_title("Meowdoku (solution plantée) : temps de résolution selon N", color=INK, fontsize=10, loc="left")
        style(ax)
        ax.legend(frameon=False, fontsize=7.5, ncol=2)
        fig.tight_layout()
        fig.savefig(os.path.join(a.outdir, "fig_meow_scaling.png"))
        plt.close(fig)

    # décisions SAT vs UNSAT (3-SAT 50 variables)
    r = df[df.family.isin(["uf50", "uuf50"]) & df.solver.str.startswith("dpllh")]
    if not r.empty:
        hs = [s for s in solvers if s.startswith("dpllh")]
        fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=150)
        x = np.arange(len(hs))
        for k, (fam, lab) in enumerate([("uf50", "uf50 (SAT)"), ("uuf50", "uuf50 (UNSAT)")]):
            vals = [gmean(r[(r.solver == s) & (r.family == fam) & r.solved].decisions + 1) for s in hs]
            ax.bar(x + (k - .5) * .38, vals, width=.36, color=C[k], label=lab)
        ax.set_yscale("log")
        ax.set_xticks(x, [NAMES[s].split()[0] for s in hs], fontsize=8)
        ax.set_ylabel("décisions (moy. géo.)", color=INK2)
        ax.set_title("3-SAT aléatoire, 50 variables : nombre de décisions", color=INK, fontsize=10, loc="left")
        style(ax)
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(a.outdir, "fig_decisions_uf50.png"))
        plt.close(fig)
    print("écrit :", os.path.join(a.outdir, "tables.md"))


if __name__ == "__main__":
    main()
