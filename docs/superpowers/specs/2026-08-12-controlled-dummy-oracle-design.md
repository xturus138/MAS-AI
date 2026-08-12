# Controlled dummy oracle design

## Purpose

Replace the Firebase Chat notebook's arbitrary fixed dummy bug IDs with one
controlled, documented oracle that contains patterns a test-case
representation could reasonably learn. This remains a synthetic experiment.
It does not identify real application defects.

## Fixed oracle

The oracle contains two fault themes derived from the human-readable QA
scenarios. A case is marked as a dummy bug when its TCS ID appears in one of
these lists.

| Theme | Meaning | TCS IDs |
| --- | --- | --- |
| Message delivery and read state | Delivery status, read status, unread state, and read receipts | `FC-MN-006`, `FC-MN-007`, `FC-CRP-007`, `FC-CRP-008`, `FC-CRG-004`, `FC-CRG-007`, `FC-MIF-001`, `FC-MIF-002`, `FC-MIF-003` |
| Group membership permission | Adding members and showing the control only to the group creator | `FC-NCP-004`, `FC-NCP-005`, `FC-GPR-002`, `FC-GPR-003` |

The oracle has 13 dummy bugs across 69 cases. It is fixed, explicit, and
shared by all methods.

## Warm start

The initial set remains the lexicographically first test case from each Menu:
`FC-LGN-001`, `FC-REG-001`, `FC-MN-001`, `FC-NCG-001`, `FC-CRG-001`,
`FC-GPR-001`, `FC-MIF-001`, `FC-FSI-001`, and `FC-PRF-001`.

This selection rule does not use the oracle labels. In the controlled oracle,
`FC-MIF-001` belongs to the delivery and read-state theme. BO therefore starts
with one known dummy bug and eight known passes, which models a small set of
historical execution outcomes.

## Acquisition

The notebook keeps cost-aware Upper Confidence Bound:

`acquisition(x) = [clip(mean(x), 0, 1) + kappa * std(x)] / cost(x)^gamma`

It uses `kappa = 1.5` and `gamma = 0.5`. Kappa controls how strongly the
optimizer values unknown candidates. Gamma applies a square-root cost penalty,
so expensive tests are penalized without always losing to the cheapest test.

The left snapshot panel clips the displayed GP mean and uncertainty interval
to `[0, 1]`. This is a display correction for binary dummy outcomes. The
selection calculation remains unchanged and uses the stated acquisition.

## Random comparison

The notebook runs 200 reproducible random orders with the same warm start.
The convergence chart shows their mean as a dashed gray line and their 5th to
95th percentile range as a gray band. A single random ordering is not used as
the performance claim.

## Interpretation

The notebook may conclude only whether a representation identifies these two
synthetic themes earlier than the random distribution. It must not call the
labels real bugs or treat the selected kappa as a final production setting.
