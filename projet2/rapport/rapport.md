---
title: "Projet MLSF — Partie II : un langage de contraintes compilé vers SAT"
subtitle: "Rapport — binôme : DAL MONTE Nicolò, DE MEDEIROS André Filipe"
date: "Novembre 2026"
lang: fr
---

# Introduction

Le compilateur (`cspc/`) lit un modèle, le traduit en FNC, appelle le solveur de la partie I (`solver/`, repris
sans modification) et affiche les valeurs dans les termes du modèle. Mode d'emploi, arborescence et tests : `README.md`.

```
texte --Lark--> AST --analyse--> modèle vérifié --déroulement--> contraintes sur des cases
      --encodage--> FNC --solveur--> modèle SAT --décodage--> grid[1][2] = 5
```

Les quatre modèles de l'énoncé donnent les réponses attendues (tableau 1), et les solutions sont vérifiées par
des programmes indépendants (`tests/test_examples.py`) : pigeonhole UNSAT, queens, coloring, sudoku SAT.

# Q1 — Du fragment propositionnel au solveur

Le fragment propositionnel est un cas particulier de la chaîne générale : une variable `bool` est une case sans
indice, encodée par un seul booléen. Les noms sont rendus dans les commentaires Dimacs (`c var 3 z`) et dans
l'objet `Encoding` (`var_of`) qui sert au décodage ; les variables auxiliaires n'ont pas de nom et ne sont pas
affichées.

**Mise en FNC** (`Encoder.add_formula`). La formule est mise en forme normale négative (négations poussées vers
les feuilles, `<->` développé), puis en FNC par la variante de Plaisted-Greenbaum de la transformation de
Tseitin : pour une conjonction `C` imbriquée sous une disjonction, on introduit `a` et on n'écrit que
`a -> C` (`¬a ∨ c_i` pour chaque `c_i`). Un seul sens suffit car, en forme normale négative, `a` n'apparaît
qu'avec la polarité positive ; on économise la moitié des clauses de Tseitin. On évite en plus toute variable
auxiliaire lorsque la contrainte est déjà une clause (`a or b`, `a -> b`, `not (a and b)`), et pour
`l ∨ (a ∧ b)` (distribution : `(l ∨ a) ∧ (l ∨ b)`). Une conjonction au sommet donne autant de contraintes.
Une équivalence `a <-> b` entre sous-formules non élémentaires passe par un littéral équivalent (`lit_of`,
deux sens), pour ne pas dupliquer les sous-formules.

**Validation** (`tests/test_encode.py`, `tests/oracle.py`). Un interpréteur naïf du langage, indépendant du
compilateur, donne la vérité sur chaque valuation. Sur 80 modèles aléatoires (4 booléens, 4 entiers, 2
énumérés, comparaisons, contraintes globales ; ≈ 5000 valuations chacun), on vérifie que
« l'oracle accepte la valuation » ⇔ « FNC + unités fixant les variables nommées est satisfiable » (test exact :
les variables auxiliaires restent libres), et que le modèle rendu par le solveur est accepté par l'oracle. Un
mutant du code (`<` traduit en `<=`) est bien détecté.

# Q2 — Analyse syntaxique

`cspc/syntax.py` : grammaire Lark en LALR(1) (`parser="lalr"`, lexer `basic`), sans conflit. Priorités par
niveaux, du plus faible au plus fort : `->` (associatif à droite) < `or` < `and` < `not` < comparaison < `+ -`
< `*` < moins unaire < atomes. Une comparaison n'est pas récursive (`arith CMP arith`) : `a = b = c` est une
erreur de syntaxe, et comme `not` est plus faible, `not x = 2` se lit `not (x = 2)`.

Points qui demandaient réflexion :

- `=` sert à `const N = 3` et aux comparaisons ; `*` à la multiplication et au joker. Il n'y a **pas** de
  terminal `CMP` regroupant `=`, `<`, … (collision de `=` avec la déclaration) : chaque comparaison est une
  alternative nommée.
- `var c : Color;` (nom d'un type) et `var x : N..5;` (intervalle) commencent par un nom : LALR(1) tranche sur
  le symbole suivant (`;` ou `..`). De même `forall c in Color` / `forall i in 1..N`. Ils ne sont pas ambigus.
- Les 11 mots-clés sont réservés par le lexer : une chaîne littérale a priorité sur `NAME`, mais `variable`,
  `index` restent des noms (testé). `abs` et les contraintes globales ne sont pas des mots-clés : ce sont des
  appels `NAME "(" args ")"`, donc ajouter une contrainte globale ne change pas la grammaire.
- Chaque nœud de l'AST mémorise sa position (ligne, colonne) (`propagate_positions` + `v_args(meta=True)`),
  ignorée par `==`. Les erreurs de syntaxe sont converties en `CompileError` avec les jetons attendus.

`pretty` affiche l'arbre (`--ast`) ; `source` réimprime un AST en texte entièrement parenthésé :
`parse(source(ast)) == ast` est vérifié sur tous les modèles.

# Q3 — Analyse et transformation

Deux passes, séparées parce que leurs erreurs ne sont pas de même nature :

1. **Analyse** (`analyze.py`, une fois, statique). Table des symboles unique (constantes, types, valeurs
   énumérées, variables, tableaux, indices de boucle). Chaque expression reçoit un type (entier, booléen,
   énuméré *E*) et un drapeau « connu ». Détecte : nom non déclaré / redéclaré (y compris indice de boucle),
   types incompatibles (`x = c`, `b + 1`, `b < b`), valeur inconnue exigée (`x + 1 = y`, indice ou borne non
   connus), mauvais nombre d'indices, tranche hors d'une contrainte globale, mauvais arguments
   (`allDifferent(b)`, fonction inconnue, `abs(1, 2)`), tableaux constants mal formés, domaine vide… ≈ 60 cas
   testés avec message et position.
2. **Déroulement** (`expand.py` + `evaluate.py`). Chaque `forall` est remplacé par ses instances ; chaque
   contrainte est évaluée par `Evaluator`, qui renvoie soit une valeur connue (int, bool, valeur énumérée) soit
   une formule *sur des cases* (`ground.py`).

**Évaluation paresseuse.** `and`, `or`, `->` n'évaluent pas leur opérande droit quand le gauche décide. Ainsi
`i < N -> grid[i+1][1] != grid[i][1]` ne lit jamais `grid[N+1]`. Un accès hors bornes effectivement évalué est
l'erreur `index 1 of 'a' is 4, out of range 1..3` (position de l'accès). C'est la raison de séparer les passes :
l'analyse ne peut pas décider des bornes, qui dépendent des valeurs et d'une condition qui protège.

**Simplifications et normalisation** (constructeurs `mk_*` de `ground.py`) : constantes repliées, `And`/`Or`
aplatis, `not (x = 2)` → `x != 2`, `not (x < y)` → `y <= x`, `x > y` → `y < x`, une case seule à gauche de
`=`/`!=`, `x = x` → vrai. Les valeurs énumérées deviennent leur numéro. Une contrainte vraie disparaît ; une
conjonction au sommet donne plusieurs contraintes ; une contrainte fausse est conservée (clause vide) et
signalée par un avertissement avec ses indices de boucle (`i=2`). Les contraintes globales dont les arguments
sont partiellement connus sont simplifiées (`exactlyOne(b, 1 = 1, x = 1)` → `!b`, `x != 1`).

# Q4 — Traduction en FNC

**Encodage direct** : pour chaque case, un booléen par valeur et les clauses « exactement une valeur » ;
`bool` = un booléen ; les énumérés sont numérotés 0, 1, … Les variables Dimacs 1..*n* sont celles des cases,
dans l'ordre de déclaration ; les auxiliaires viennent après.

**Comparaisons** (`Encoder.compare`). Tous les choix sont corrects parce que *exactement un* booléen par domaine
est vrai :

| Comparaison | Traduction | Taille |
|---|---|---|
| `x = c`, `x != c` | un littéral, ou sa négation | 1 |
| `x < c`, `x <= c`, `c < x`… | le plus court de « *x* prend une bonne valeur » (une clause) et « *x* ne prend aucune mauvaise valeur » (unités) | ≤ \|dom\|/2 |
| `x = y` | `x_v -> y_v` pour tout *v* | \|dom\| clauses binaires |
| `x != y` | `¬(x_v ∧ y_v)` pour tout *v* commun | \|dom\| clauses binaires |
| `x < y`, `x <= y` | `x_v -> (y_w1 ∨ y_w2 ∨ …)`, *w* > *v* (ou ≥) | \|dom\| clauses de longueur ≤ \|dom\| |

Pour `x < y`, l'alternative « deux à deux » (`¬x_v ∨ ¬y_w` pour *w* ≤ *v*) donne ≈ \|dom\|²/2 clauses binaires.
J'ai retenu la forme linéaire : moins de clauses ; l'inconvénient probable est une propagation unitaire plus
faible (clauses longues). Je ne l'ai pas mesuré séparément. Une valeur hors du domaine rend `x = c` faux sans erreur
(c'est une valeur, pas un indice) — le modèle 1 du Meowdoku en dépend (`row[z] = k`, avec `k = 0`).

**Comparaison de booléens** (`b = (x = 1)`) : équivalence (`Iff`) puis NNF ; `!=` est la négation.

**Contraintes globales.** `atLeastOne` : une clause ; `atMostOne` : encodage deux à deux (n(n−1)/2 clauses, sans
variable) ; `exactlyOne` : les deux ; `allDifferent` : pour chaque valeur *v*, au plus une des cases vaut *v*
(les arguments connus occupent leur valeur ; deux arguments connus égaux : faux). Les arguments booléens non
élémentaires sont remplacés par un littéral équivalent.

**Pour aller plus loin : compteur séquentiel de Sinz** (`--amo sinz`, `Encoder.sinz`) : 3n−4 clauses et n−1
variables auxiliaires (testé : `test_sequential_counter_sizes`). Il s'applique à *tout* « au plus un » assertée
au sommet (domaines inclus). **Sous une négation, c'est incorrect.** Les clauses de Sinz expriment « au plus un » sous la forme
« il *existe* des `s_i` qui satisfont les clauses » : valable quand la contrainte est assertée, car le solveur choisit
les `s_i`. Pour `b -> not atMostOne(...)`, il faudrait « *pour tous* les `s_i`, les clauses sont violées » ; or
le solveur est libre de choisir des `s_i` qui violent les clauses même si au plus un `x_i` est vrai, et
satisferait alors la négation à tort (des valuations qui respectent « au plus un » seraient acceptées sous
`b`). Les `s_i` ne sont pas définis (équivalence) par les `x_i` : seul un sens est écrit. Le compilateur
n'emploie donc Sinz que pour une contrainte globale au sommet ; sous un connecteur, il utilise l'encodage deux
à deux, exact sous toute polarité (`test_global_under_negation_is_exact`).

Effet sur le Meowdoku (grilles planifiées, 2 graines, `results/benchmark_*.md`, médiane) :

| N | encodage | clauses | variables | CDCL (s) | DPLL_H H9 (s) |
|---|---|---|---|---|---|
| 20 | deux à deux | 13 164 | 400 | 0,06 | 0,69 |
| 20 | Sinz | 4 102 | 1 540 | 0,07 | 0,91 |
| 30 | deux à deux | 44 665 | 900 | 0,14 | 12,1 (un timeout à 20 s) |
| 30 | Sinz | 9 452 | 3 510 | 0,20 | 6,6 |

Sinz réduit nettement les clauses (÷ 4,7 à N = 30). Le CDCL ne gagne rien (ses temps sont dominés par autre
chose) ; DPLL_H profite du plus petit nombre de clauses à grande taille, mais perd à N = 20 (plus de variables à
traiter). Pas de gain net à ces tailles : pour N ≤ 20, le deux à deux suffit.

# Q5 — Jonction avec la partie I

`solving.py` appelle `solver.portfolio.solve` (mode `optimized` de `sat.py`) ou `solver.dpll.solve`
(`--mode dpll`), en passant la liste de clauses (pas de fichier). Le modèle SAT est relu par
`Encoding.decode` : pour une case non booléenne, la valeur *v* telle que `x_v` est vraie (nom d'énuméré
restitué) ; sortie `s SATISFIABLE` puis `grid[1][2] = 5`, `color[3] = Red`, `b = true`. Le Dimacs porte les
commentaires `c var n nom=valeur`. Si une contrainte est fausse (clause vide), on répond UNSAT sans appeler le
solveur. Les clauses de la partie I (par ex. celle du principe des tiroirs) sont résolues par le même solveur.

# Q6 — Le modèle compte plus que le solveur

Tous les modèles sont dans `models/meowdoku/` : données de la grille + règles, dont le texte est assemblé par
`tools/meowdoku_models.py`.

**6.1** `python -m tools.grid2csp grille.txt [--model m]` convertit une grille de la partie I en `const N, M, K`,
`enum Zone`, `const region[N][M]`. Les noms de régions qui seraient des mots-clés ou des noms des règles sont
renommés (`Z_nom`) puis restitués.

**6.2** Le modèle 2 est complété par « au plus un chat par région », sans tranche pour une région : pour chaque
paire de cases distinctes (ordre lexicographique) de même région, on interdit les deux chats :
`(i1 < i2 or j1 < j2) and region[i1][j1] = region[i2][j2] -> not (cat[i1][j1] and cat[i2][j2])`.
`python -m tools.solve_grid grille.txt --model m` résout, décode et **vérifie** avec `check_solution` de la
partie I (indépendant du compilateur). Les quatre modèles trouvent, sur la grille de la figure 1, la solution
attendue ; sur 80 grilles aléatoires et sur des grilles plantées ils sont d'accord entre eux.

**6.3 Mesures** (`tools/benchmark.py`, grilles de `meowdoku.generate`, 3 graines, médianes, timeout 20 s ;
`results/benchmark.md`, `results/benchmark.csv`, toutes les solutions trouvées sont valides). « part1 » est
l'encodage dédié de la partie I, sans compilateur. CDCL = solveur `optimized`, H9 = DPLL_H avec l'heuristique H9,
DPLL = algorithme 2. `T` : au moins un timeout.

| N | modèle | variables | clauses | compil. (s) | CDCL (s) | DPLL_H H9 (s) | DPLL (s) |
|---|---|---|---|---|---|---|---|
| 8 | positions | 128 | 6 848 | 0,75 | 0,02 | 0,07 | 0,55 |
| 8 | cells | 64 | 861 | 0,04 | 0,00 | 0,02 | 0,01 |
| 10 | positions | 200 | 17 300 | 1,98 | 0,04 | 18,7 T | 8,2 T |
| 10 | cells | 100 | 1 645 | 0,10 | 0,00 | 0,03 | 0,03 |
| 12 | positions | 288 | 36 720 | 4,48 | 0,07 | 2,4 T | 20,0 T |
| 12 | cells | 144 | 2 854 | 0,20 | 0,01 | 0,07 | 0,13 |
| 14 | cells | 196 | 4 646 | 0,34 | 0,03 | 0,09 | 20,0 T |
| 16 | cells | 256 | 6 695 | 0,51 | 0,03 | 0,72 | 20,0 T |
| 20 | cells | 400 | 13 184 | 1,19 | 0,07 | 20,0 T | 20,0 T |
| 20 | cells_redundant | 400 | 13 204 | 1,23 | 0,01 | 0,52 | 0,48 |
| 20 | general | 400 | 13 164 | 0,20 | 0,09 | 0,50 | 0,45 |
| 20 | part1 | 400 | 11 289 | 0,01 | 0,02 | 0,50 | 0,46 |

(`positions` n'est pas mesuré au-delà de N = 12 pour limiter la durée de la campagne : sa compilation atteint 8,8 s à
N = 14, avec 69 188 clauses.)

Le compilateur et le solveur sont les mêmes ; seul le **texte du modèle** change, et avec lui la formule :

- *Taille.* `positions` a des variables « position » à N valeurs (2N·N booléens) et surtout la règle des chats
  voisins quantifiée sur `z1, z2, i, j, k, l` : ≈ N⁵ instances au déroulement, et 17 300 clauses contre 1 645
  pour `cells` à N = 10 (×10). La compilation suit (≈ N⁵ : 2 s à N = 10, 4,5 s à N = 12, 8,8 s à N = 14).
- *Qualité de la propagation.* `positions` exprime « le chat de z est dans z » par des clauses indirectes
  (`row[z] = i ∧ col[z] = j` interdit si `region[i][j] ≠ z`) : il faut deux déductions pour exclure une case.
  Dans `cells`, la contrainte est directe : chaque case est un booléen, ligne et colonne `exactlyOne`.
  Le solveur le plus faible (DPLL de base) ne résout pas `positions` dès N = 10 et pas non plus `cells`
  dès N = 14 : le modèle 2 sans règle redondante garde un espace de recherche que seule l'apprentissage du CDCL
  traverse en quelques centièmes de seconde.
- *Modèle contre solveur pour une même formule.* Sur `cells` à N = 20, CDCL 0,07 s contre 20 s+ pour les DPLL :
  un facteur > 280 dû au solveur. Mais sur `general` à N = 20, les trois solveurs sont à 0,1–0,5 s : un facteur
  ≈ 5 seulement. Et pour le même solveur (DPLL de base), `cells` → `cells_redundant` fait passer de > 20 s à
  0,48 s (facteur > 40), et `positions` à N = 10 reste hors de portée de DPLL_H et DPLL (> 8 s, > 18 s) alors que
  `cells` les résout en 0,03 s (facteur > 270).

**6.4 Règles redondantes.** « Au moins un chat par région » est une conséquence des autres règles quand N = M = K
(chaque ligne a exactement un chat, donc il y a N chats ; chaque région en a au plus un et il y a K = N
régions : principe des tiroirs, chacune en a exactement un). Aucune tranche ne désigne les
cases d'une région, donc **extension du langage** : liste en compréhension
`atLeastOne(cat[i][j] forall i in 1..N, j in 1..M : region[i][j] = z)` (c'est la question optionnelle
correspondante) ; elle réutilise `forall` et `:` et n'ajoute aucun mot réservé. Alternative sans extension, non
retenue : un tableau auxiliaire `reach[Zone][N][M]` (« un chat de *z* dans les cases jusqu'à (i, j) »), avec une
chaîne d'implications ; plus long et plus gros, c'est un compteur séquentiel écrit à la main.

| N | sans la règle (`cells`) | avec (`cells_redundant`) |
|---|---|---|
| 14 | DPLL : timeout ; H9 0,09 s | DPLL 0,09 s ; H9 0,10 s |
| 16 | DPLL : timeout ; H9 0,72 s | DPLL 4,05 s ; H9 0,33 s |
| 20 | DPLL, H9 : timeout ; CDCL 0,07 s | DPLL 0,48 s ; H9 0,52 s ; CDCL 0,01 s |

Explication : une clause `⋁_{c∈R} x_c` est une *clause positive qui porte sur la région*. Sans elle, aucune clause ne dit
« cette région doit placer son chat quelque part » : le fait n'est qu'une conséquence du principe des tiroirs,
que la propagation unitaire ne voit pas et que le solveur ne découvre qu'en explorant. Avec elle, la propagation
unitaire déduit « dernière case libre de la région » (comme dans la partie I, option `redundant`), ce qui réduit
fortement le nombre de décisions et de retours en arrière. Elle ajoute seulement K clauses (8 à N = 8, 20 à
N = 20) : le coût est négligeable. Le CDCL apprend de lui-même des clauses équivalentes, d'où un gain
moindre (0,07 → 0,01 s) mais toujours présent.

**6.5 Modèle général** (`general.csp`, N, M, K libres) : au plus un chat par ligne et par colonne
(`atMostOne(cat[i][*])`), exactement un par région (comprehension), pas de chats diagonaux (les voisins
orthogonaux sont déjà exclus par les lignes/colonnes). Il est vérifié contre une **recherche exhaustive**
(`tools/brute_force.py`) sur 80 grilles aléatoires de 1 à 5 lignes/colonnes et K ≤ 5, partitions quelconques :
mêmes réponses SAT/UNSAT (au moins 5 de chaque), solutions vérifiées par `check_solution`
(`test_general_model_against_exhaustive_search`). Ses mesures sont celles de la partie I (tableau ci-dessus) :
mêmes ordres de grandeur que l'encodage dédié (`part1`), avec 0,2 s de compilation à N = 20.

**6.6 Conclusion.** Dans ces expériences, le **choix du modèle** a le plus d'effet *à solveur donné* : passer
de `positions` à `cells` divise la taille de la formule par 10 et rend résolubles des instances que les DPLL ne
résolvent pas ; ajouter une seule famille de K clauses redondantes fait passer le DPLL de base de plus de 20 s
à 0,5 s. Le **solveur** compte aussi (le CDCL résout `cells` en centièmes de seconde là où les DPLL échouent),
mais il *compense* un mauvais modèle plus qu'il n'en profite : avec le bon modèle, les trois solveurs de la
partie I sont dans un rapport de 1 à 10 (et tous sous la seconde à N = 20), alors qu'avec le mauvais, l'écart
atteint plusieurs centaines (≥ 280 sur `cells` à N = 20, ≥ 470 sur `positions` à N = 10, minorants). Les heuristiques (H9 contre l'algorithme 2) comptent peu devant ces deux facteurs ; les
optimisations de la partie I (CDCL) suffisent à rattraper un modèle médiocre, pas à égaler un bon modèle à
résolution équivalente. Limites : grilles planifiées uniquement (satisfiables), N ≤ 20 pour les trois solveurs,
3 graines, temps CPU de Python, timeout coopératif de 20 s (les « T » sont des minorants).

# Limites et choix à connaître

- Une valeur énumérée n'est pas un booléen ; `true`/`false` ne sont pas des littéraux du langage (non listés
  dans l'énoncé), les booléens connus ne viennent que de comparaisons.
- Les tableaux constants ne contiennent que des entiers ou des valeurs d'un même énuméré, avec dimensions entières.
- `a[i]` sur un tableau à plus d'une dimension (indices incomplets) est une erreur ; les tranches exigent tous
  les indices (`grid[i][*]`).
- L'interface est celle conseillée par l'énoncé (`python csp.py model.csp [--dimacs f] [--solve]`).
- Dépendance : `lark` ; le solveur et le vérificateur de la partie I sont repris sans modification
  (`solver/`, `meowdoku/`, `sat.py`).
- Aide d'un assistant IA pour l'écriture du code ; le code a été relu et testé
  (235 tests).
