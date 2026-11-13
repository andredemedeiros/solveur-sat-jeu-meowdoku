# Projet MLSF — Partie II : un langage de contraintes compilé vers SAT

Un compilateur lit un modèle écrit dans un petit langage de contraintes, le traduit en FNC (Dimacs), appelle
le solveur SAT de la partie I, puis affiche la solution dans les termes du modèle.

```
modèle (texte) --Lark--> AST --analyse--> modèle vérifié --déroulement--> contraintes sur des cases
      --encodage direct + Tseitin--> FNC --solveur partie I--> modèle SAT --décodage--> grid[1][2] = 5
```

Python ≥ 3.12, bibliothèque `lark` (`pip install -r requirements.txt`). Toutes les commandes se lancent depuis
ce dossier.

## Utilisation

```sh
python csp.py exemples/sudoku.csp --solve        # résolution : s SATISFIABLE + une ligne « nom = valeur » par variable
python csp.py exemples/queens.csp                # FNC au format Dimacs sur la sortie standard
python csp.py exemples/queens.csp --dimacs f.cnf # FNC écrite dans f.cnf
python csp.py modele.csp --ast                   # arbre de syntaxe          (Q2)
python csp.py modele.csp --ground                # contraintes déroulées     (Q3)
python csp.py modele.csp --solve --mode dpll --amo sinz --stats
```

| Option | Rôle |
|---|---|
| `--solve` | résout avec le solveur de la partie I ; `--mode optimized` (défaut, CDCL + DPLL_H) ou `dpll` (algorithme 2) |
| `--amo pairwise\|sinz` | encodage de « au plus un » : deux à deux (défaut) ou compteur séquentiel de Sinz |
| `--stats` | tailles et temps, sur stderr |

Une erreur du modèle est signalée sur stderr avec sa position (code de sortie 1), jamais par une trace Python :

```
model.csp: line 2, column 12: arithmetic is only allowed on known values (constants and loop indices), not on variables
```

Une contrainte qui se simplifie en « faux » donne un avertissement (`warning: constraint (i=2) is always false`) :
le modèle est insatisfiable.

## Arborescence

```
csp.py                  ligne de commande
cspc/                   le compilateur (paquet Python)
  syntax.py             Q2  grammaire Lark (LALR), AST, ASTBuilder, pretty-printer, source()
  model.py, analyze.py  Q3  table des symboles, vérification (noms, types, valeurs connues, arité)
  evaluate.py           Q3  évaluation paresseuse : calcul des valeurs connues, tranches, simplifications
  expand.py             Q3  déroulement des forall -> contraintes sans boucle
  ground.py             Q3  formules « sur des cases » + constructeurs qui simplifient et normalisent
  encode.py             Q4  encodage direct des domaines, comparaisons, contraintes globales, mise en FNC
  solving.py            Q5  appel du solveur de la partie I
  compiler.py           la chaîne complète ; errors.py : CompileError (message + position)
solver/, sat.py         solveur de la partie I, repris tel quel (non modifié)
meowdoku/               grilles, vérificateur indépendant et générateur de la partie I (repris tels quels)
models/meowdoku/        Q6  règles du Meowdoku, quatre modèles
tools/                  Q6  grid2csp, solve_grid, benchmark, brute_force
exemples/               les quatre modèles de l'énoncé       examples/  le fragment propositionnel (code de départ)
tests/                  tests (python -m pytest -q tests)
results/                mesures de la question 6
rapport/rapport.md      rapport : choix, justifications, résultats
```

## Le langage

Celui de l'énoncé, sans changement : `const`, `enum`, `var`, `array` (indices à partir de 1 ou types énumérés),
`constraint`, `forall`, connecteurs `not and or ->`, comparaisons, arithmétique sur valeurs connues, accès
`a[i][j]`, tranches `a[i][*]`, contraintes globales `atLeastOne atMostOne exactlyOne allDifferent`.

**Extension** (Q6.4) : *liste en compréhension* comme unique argument d'une contrainte globale,

```
atLeastOne(cat[i][j] forall i in 1..N, j in 1..M : region[i][j] = z)
```

désigne les `cat[i][j]` des instances de la boucle où la condition (connue, facultative) est vraie. Aucune
tranche ne désigne les cases d'une région ; cette liste le permet. Elle réutilise `forall` et `:` : aucun nouveau
mot réservé, donc tout modèle de l'énoncé reste accepté.

## Tests

```sh
python -m pytest -q tests          # ≈ 40 s
```

- `test_syntax.py` : priorités, associativités, erreurs de syntaxe (avec position), mots-clés, aller-retour
  `parse(source(ast)) == ast` sur tous les modèles.
- `test_analyze.py` : ≈ 60 modèles erronés (message et position) ; ≈ 50 modèles dont le déroulement est connu,
  dont l'évaluation paresseuse (accès hors bornes protégé par une condition fausse, ou non).
- `test_encode.py` : validation de la FNC contre un interpréteur naïf indépendant (`tests/oracle.py`) sur 80
  modèles aléatoires (2 encodages de « au plus un ») : pour **chaque** valuation complète, « le modèle l'accepte »
  ssi « la FNC + les unités qui la fixent est satisfiable » ; le modèle rendu par le solveur est accepté.
- `test_examples.py` : les quatre modèles de l'énoncé avec vérificateurs indépendants, la ligne de commande,
  les modèles du Meowdoku (vérificateur de la partie I, recherche exhaustive sur 80 grilles aléatoires).

## Question 6 (Meowdoku)

```sh
python -m tools.grid2csp ../projet1/data/examples/grille1.txt --model cells -o grille1.csp   # Q6.1
python csp.py grille1.csp --solve
python -m tools.solve_grid ../projet1/data/examples/grille1.txt --model general             # Q6.2 : résout et vérifie
python -m tools.benchmark --sizes 6 8 10 12 --seeds 3 -o results/benchmark.csv                # Q6.3, Q6.4, Q6.6
```

Modèles (`--model`) : `positions` (modèle 1), `cells` (modèle 2 complété), `cells_redundant` (Q6.4),
`general` (Q6.5, N, M, K libres). Voir le rapport pour les mesures et leur analyse.
