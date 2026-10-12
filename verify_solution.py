#!/usr/bin/env python3
"""Vérifie un fichier solution Meowdoku (format figure 2) : cohérence du
dictionnaire et de la grille de *, et respect des 4 règles du jeu.

    python verify_solution.py solution.txt
"""
import sys

from meowdoku.grid import cats_from_cells, check_solution, read_solution


def main(path):
    grid, cats, stars = read_solution(path)
    errors = check_solution(grid, cats)
    star_cells = {(i + 1, j + 1) for i, row in enumerate(stars) for j, s in enumerate(row) if s == "*"}
    if star_cells != set(cats.values()):
        errors.append("la grille de * ne correspond pas au dictionnaire")
    else:
        cats_from_cells(grid, star_cells)
    print("OK" if not errors else "INVALIDE :\n  " + "\n  ".join(errors))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
