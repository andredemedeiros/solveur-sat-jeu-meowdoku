# Projet MLSF — Partie I : solveur SAT et Meowdoku

Python ≥ 3.12, **bibliothèque standard uniquement** pour le solveur (`sat.py`).
Outils d'analyse : `pycosat` (solveur de référence pour la validation),
`pandas`, `matplotlib`, `pytest`.

## Arborescence

| Fichier | Rôle | Question |
|---|---|---|
| `solver/cnf.py` | lecture/écriture DIMACS, structure CNF, vérification de modèles | Q2.1 |
| `solver/dpll.py` | algorithmes 1 et 2 de l'énoncé (DPLL récursif, choix aléatoire) | Q2.2 |
| `solver/heuristics.py` | heuristiques H0–H7 (statiques `s` / dynamiques `d`) + H8 (MOMS-produit) | Q4 |
| `solver/dpll_h.py` | algorithme 3 (DPLL_H) instrumenté (décisions, retours arrière, …) | Q4, Q5 |
| `solver/cdcl.py` | solveur optimisé (CDCL : watched literals, 1-UIP, VSIDS, restarts) | Q6 |
| `solver/runner.py` | exécution instrumentée d'un solveur sur un fichier | Q2–Q5 |
| `meowdoku/grid.py` | fichiers grille / solution, vérificateur indépendant des règles | Q1, Q3 |
| `meowdoku/encode.py` | codage grille → CNF, décodage valuation → chats | Q1 |
| `meowdoku/generate.py` | générateur de grilles à solution plantée (option unicité) | Q1 |
| `meow2cnf.py` | CLI : grille → DIMACS | Q1 |
| `generate_grids.py` | CLI : génération de grilles | Q1 |
| `solve_meowdoku.py` | CLI : grille → solution (format figure 2) via le solveur | Q3 |
| `verify_solution.py` | CLI : vérification d'un fichier solution | Q3 |
| `gen_cnf.py` | génération des instances de test (3-SAT, PHP, Meowdoku) | Q2, Q5 |
| `validate.py` | validation croisée de tous les solveurs (statut + modèles) | Q2.3, Q4 |
| `benchmark.py`, `analyze.py` | campagne de mesures et analyse | Q5 |
| `sat.py` | **point d'entrée imposé** | Q6 |
| `competition.py` | simulation de la compétition (appelle `sat.py`) | Q6 |
| `tests/` | tests unitaires (`python -m pytest -q tests`) | — |
| `data/` | instances DIMACS (SATLIB + générées) et grilles | — |
| `results/` | CSV de mesures, tableaux et figures | Q5 |
| `rapport/` | rapport | — |

## Exemples

```sh
# Q1 : conversion et génération
python meow2cnf.py data/grids/grille1.txt -o grille1.cnf
python generate_grids.py 10 --count 5 --unique -o data/grids/gen

# Q3 : résolution d'une grille
python solve_meowdoku.py data/grids/grille1.txt -o grille1.sol.txt
python verify_solution.py grille1.sol.txt

# Q2 / Q4 : validation, Q5 : mesures
python validate.py --timeout 20
python benchmark.py --timeout 30 && python analyze.py

# Q6 : interface imposée
python sat.py instance.cnf --mode dpll
python sat.py instance.cnf --mode optimized --output-model
python competition.py data/cnf --timeout 60
```
