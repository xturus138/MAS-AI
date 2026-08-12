# Simplified Bayesian Notebook Visualization Design

## Goal

Simplify `experiment/bayesian/bayesian_dummy_closed_loop.ipynb` so its
visual output follows the referenced scikit-optimize Colab example and is
easier to explain, without changing the independent One-Hot, TF-IDF with SVD,
Multilingual E5, and Random experiments.

## Applicability to the Firebase Chat Experiment

The reference visualization can be used, but the meaning of its horizontal
axis changes. The reference optimizes a continuous one-dimensional function.
This experiment selects from 69 discrete test cases represented in separate
high-dimensional matrices. Therefore, each plotted point is a real posterior
or acquisition value for one test candidate, while any line connecting those
points is only a visual guide over the fixed Excel order. It must not be
described as a continuous objective function.

## Visual Output

The notebook will contain only two visualization types:

1. One convergence plot comparing cumulative dummy bugs against executed test
   count for One-Hot, TF-IDF with SVD, Multilingual E5, and Random.
2. One reference-style iteration figure for each Bayesian representation.
   Every figure uses repeated two-column rows:
   - Left: red dashed dummy truth, green dashed Gaussian Process mean, green
     uncertainty band, and red observed outcomes.
   - Right: blue cost-aware acquisition values, blue filled area, and a blue
     marker for the next selected test case.

Random appears only in the convergence plot because it has no surrogate
posterior or acquisition function.

The standalone truth plot, cost convergence plot, bug-discovery-position plot,
and feature-coverage plot will be removed. Tables and CSV/ZIP export remain
because they are experiment artifacts rather than additional visualizations.

## Independence of the Methods

Each representation continues to run through its own closed loop. Matrices are
not concatenated, averaged, or used to train one another. The methods share
only the fixed dummy oracle, initial feature seed, costs, and BO parameters so
their convergence remains comparable.

## Snapshot Semantics

Each Bayesian method will show the same four snapshot counts: after the
initial feature seed, and after 5, 15, and 30 additional selections. Tested
candidates receive zero display height in the acquisition panel so the
remaining peaks and next-query marker are visually legible. Candidate
selection itself continues to use the original acquisition array before this
display-only transformation.

## Verification

Notebook contract tests will verify that only the requested plot categories
remain, all three Bayesian methods still run independently, Random remains a
baseline, and the iteration figures are generated per representation. A local
smoke run with E5 explicitly disabled will verify the real 69-case workbook,
One-Hot, TF-IDF with SVD, Random, figures, and exports. E5 remains enabled by
default for Google Colab.
