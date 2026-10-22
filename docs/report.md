# Report

> About five pages. Every claim about a variant is backed by a measurement, a
> test result, a log excerpt or a reference to code. Delete the quoted
> guidance when you are done.

Group: …
Members: …

## 1. Recommendation

> Three to five sentences for management: which decomposition, for which
> situation, and the most important price of that choice.

## 2. Results

> One row per criterion from `criteria.md`, for `v1` and `v2`. Link the
> evidence (file in `bench/results/`, test run, log excerpt, code). The
> monolith is a useful third column where it helps.

| ID | Criterion | A `v1` | B `v1` | A `v2` | B `v2` | Evidence |
|----|-----------|--------|--------|--------|--------|----------|
| C1 | | | | | | |

## 3. How far the change requests spread

> From `make impact` and your own observations: services touched, lines
> changed, interfaces between services that changed, data that had to be
> migrated. Which variant absorbed which change better, and why? What did your
> preparation for the change requests cost and bring?

## 4. Hypotheses and results

> For each criterion: what did you expect at `criteria-v1`, what did you
> measure, and if they differ, why? If you changed criteria after
> `criteria-v1`, explain it here.

## 5. Decision and trade-offs

> What do you gain and what do you give up with your recommendation? Go
> through the stakeholders: whose concern is met, whose is not, and what you
> would tell them.

## 6. What would change the decision

> Concrete conditions (a number, a requirement, an organisational change)
> under which you would recommend the other variant.

## 7. What the DDD analysis showed

> Two or three findings from `domain.md` that matter for the decision.

## 8. Limits of this comparison

> What does your setup not show? Think of everything running on one machine,
> the size of the data, the number of stores and tills, the test-only reset.

## 9. Reflection on working with the coding agent

> Refer to `ai-log/findings.md`. Which kinds of mistakes did the agent make?
> Which of them did the tests catch, and which only your review or your
> measurements? Did the agent respect the variant rules? What would you
> specify differently next time? What did the agent do well?
