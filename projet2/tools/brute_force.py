"""Q6.5 -- Exhaustive search for a Meowdoku solution, to cross-check the models.

One cat per region is chosen among the cells of the region (all the
combinations), and each choice is tested with the checker of part I. It is
only meant for small grids.
"""

from __future__ import annotations

from itertools import product

from meowdoku.grid import Grid, check_solution


def brute_force(grid: Grid, limit: int = 2_000_000):
    """A solution {region: cell}, or None if there is none.
    Raises OverflowError if there are more than `limit` combinations."""
    regions = grid.regions()
    count = 1
    for cells in regions.values():
        count *= len(cells)
    if count > limit:
        raise OverflowError(f"{count} combinations")
    zones = list(regions)
    for choice in product(*(regions[z] for z in zones)):
        cats = dict(zip(zones, choice))
        if not check_solution(grid, cats):
            return cats
    return None
