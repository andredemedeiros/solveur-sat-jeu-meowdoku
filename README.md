# Projet MLSF — Partie I : solveur SAT et Meowdoku

Python ≥ 3.12, **bibliothèque standard uniquement** pour le solveur (`sat.py`).
Outils d'analyse : `pycosat` (solveur de référence pour la validation),
`pandas`, `matplotlib`, `pytest` (`pip install -r requirements.txt`).
Toutes les commandes se lancent depuis la racine du dépôt.

## Arborescence

```
sat.py                  point d'entrée imposé (Q6) : --mode dpll | optimized
solver/                 solveurs SAT (paquet Python)
meowdoku/               modélisation du Meowdoku (paquet Python)
cli/                    outils en ligne de commande Meowdoku (Q1, Q3)
experiments/            validation, mesures et simulation de compétition (Q2, Q4–Q6)
tests/                  tests unitaires (python -m pytest -q tests)
data/
  examples/             exemples de l'énoncé : 3 lampes, grille de la figure 1 (+ CNF, solution)
  public-instances/     instances publiques des enseignants (41 fichiers + expected.json)
  satlib/               familles SATLIB (uf/uuf, aim, dubois, pigeon-hole, flat50)
  generated/cnf/        nos instances (3-SAT, PHP, Meowdoku) — experiments/gen_cnf.py
  generated/grids/      grilles Meowdoku correspondantes
results/
  validation/           Q2.3, Q4 : validation croisée des 19 solveurs
  benchmark/            Q4, Q5 : mesures (bench.csv), tableaux (tables.md), figures,
                        variantes de H9, principe des tiroirs (pigeon_hole.csv)
  competition/          Q6 : simulation de la compétition (modes dpll et optimized), hole8/9 seuls
rapport/                rapport.md (source), rapport.pdf (à rendre), build_pdf.py, style.css
docs/                   énoncé du projet
```

| Fichier | Rôle | Question |
|---|---|---|
| `solver/cnf.py` | lecture/écriture DIMACS, structure CNF, vérification de modèles | Q2.1 |
| `solver/dpll.py` | algorithmes 1 et 2 de l'énoncé (DPLL récursif, choix aléatoire) | Q2.2 |
| `solver/heuristics.py` | heuristiques H0–H7 (statiques `s` / dynamiques `d`) + H8 (MOMS-produit), H9 (MRV) | Q4 |
| `solver/dpll_h.py` | algorithme 3 (DPLL_H) instrumenté (décisions, retours arrière, …) | Q4, Q5 |
| `solver/cdcl.py` | solveur CDCL (watched literals, 1-UIP, VSIDS, restarts), interruptible et reprenable | Q6 |
| `solver/portfolio.py` | mode `optimized` : CDCL, relayé après 2 s par DPLL_H (H1) dans un processus parallèle | Q6 |
| `solver/runner.py` | exécution instrumentée d'un solveur ; statut attendu (`expected.json`, commentaire `status`, nom SATLIB) | Q2–Q5 |
| `meowdoku/grid.py` | fichiers grille / solution, vérificateur indépendant des règles | Q1, Q3 |
| `meowdoku/encode.py` | codage grille → CNF, décodage valuation → chats | Q1 |
| `meowdoku/generate.py` | générateur de grilles à solution plantée (option unicité) | Q1 |
| `cli/meow2cnf.py` | grille → DIMACS | Q1 |
| `cli/generate_grids.py` | génération de grilles | Q1 |
| `cli/solve_meowdoku.py` | grille → solution (format figure 2) via le solveur | Q3 |
| `cli/verify_solution.py` | vérification d'un fichier solution | Q3 |
| `experiments/gen_cnf.py` | génération des instances de test (3-SAT, PHP, Meowdoku) | Q2, Q5 |
| `experiments/validate.py` | validation croisée de tous les solveurs (statut + modèles) | Q2.3, Q4 |
| `experiments/benchmark.py`, `experiments/analyze.py` | campagne de mesures et analyse | Q5 |
| `experiments/h9_variants.py` | choix de la case dans la clause de H9 (moins / plus contraignante, indice) | Q4 |
| `experiments/competition.py` | simulation de la compétition (appelle `sat.py`, lit `expected.json`) | Q6 |

## Exemples

```sh
# Q1 : conversion et génération
python cli/meow2cnf.py data/examples/grille1.txt -o grille1.cnf
python cli/generate_grids.py 10 --count 5 --unique     # -> data/generated/grids/custom/

# Q3 : résolution d'une grille
python cli/solve_meowdoku.py data/examples/grille1.txt -o grille1.sol.txt
python cli/verify_solution.py grille1.sol.txt

# Q2 / Q4 : validation (inclut data/public-instances), Q5 : mesures
python experiments/validate.py --timeout 20
python experiments/benchmark.py --timeout 20 --jobs 6 && python experiments/analyze.py
python experiments/h9_variants.py --timeout 30 --jobs 6
python experiments/benchmark.py --timeout 120 --instances data/satlib/pigeon-hole/hole{9,10}.cnf \
    --solvers cdcl alg2 dpllh:H1 dpllh:H2d dpllh:H4d dpllh:H6d dpllh:H8 dpllh:H9 \
    --out results/benchmark/pigeon_hole.csv

# Q6 : interface imposée
python sat.py instance.cnf --mode dpll
python sat.py instance.cnf --mode optimized --output-model
python experiments/competition.py --mode optimized --jobs 1     # toutes les instances de data/
# conditions officielles (python:3.12-slim, 4 CPU, 8 Gio) :
docker run --rm --cpus=4 --memory=8g -v "$PWD":/w -w /w python:3.12-slim \
    python experiments/competition.py --jobs 1

# Rapport : rapport/rapport.md -> rapport/rapport.pdf (pandoc + Edge/Chrome)
python rapport/build_pdf.py
```
