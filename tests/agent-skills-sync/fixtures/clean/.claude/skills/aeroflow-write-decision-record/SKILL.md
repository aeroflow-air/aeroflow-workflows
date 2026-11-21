---
name: aeroflow-write-decision-record
description: Write an AeroFlow decision record (ADR) in the right place, format and lifecycle so the validator passes. Use when a change makes a choice another squad, or a future reader, needs to know, or when asked to propose, accept or supersede an ADR.
license: MIT
---

# Write a decision record

## When to use
- When you are choosing between real alternatives that constrain future work: a pattern, a tool, a contract or a process.
- Not for how-to detail. That goes in a design doc (`docs/design/`), linked from the record's `design-doc`.

## Steps
1. **Pick the home.** Would another squad have to read it to do its job? Then it belongs in
   `platform-handbook/docs/decisions/`. If it only constrains one service, it goes in that repo's own
   `docs/decisions/`, with the same format.
2. **Read first.** Read the existing records, and don't re-propose something already rejected unless its
   revisit trigger has fired.
3. **Create the file.** Copy `_template.md` to `<id>-<slug>.md`, using the next free id zero-padded to four digits
   (`id:` in the frontmatter is the plain integer). Set `status: draft`, today's ISO date and `affects`.
4. **Write four sections in order:** Context, Decision, Consequences, Alternatives considered. Put the
   decision in one present-tense paragraph. Name the costs. Every rejected alternative gives the trigger that
   would make it worth revisiting. Keep it terse, about a page.
5. **Validate locally.** In platform-handbook, run `python3 scripts/validate-decisions.py --base main`.
6. **One lifecycle step per merged PR:** `draft → in-review → accepted`, or `rejected`. A PR can't go from
   draft to accepted. "Proposed" isn't a status; use `draft`.
7. **Never edit an accepted record.** Only `status` and `superseded-by` may change. To change your mind, write a
   new record with `supersedes: <id>` and, in the same PR, set the old one to `superseded` with `superseded-by`.
8. **Service-local CI.** Call `aeroflow-air/aeroflow-workflows/.github/workflows/validate-decisions.yml@v0.6.0`.
   The `@v1` shown in the handbook README doesn't exist (ADR-0023 gap).
9. **Link it.** Add the design doc link to the handbook README if there is one, and reference the ADR id in the PR title,
   e.g. `ADR-0024 (draft): ...`.

## Example
- Process and rules: [decisions README](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/README.md)
- Template: [_template.md](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/_template.md)
- A good record: [ADR-0022](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0022-observability-on-the-golden-path.md) with its [design doc](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/design/observability.md)
- Validator: [validate-decisions.py](https://github.com/aeroflow-air/platform-handbook/blob/main/scripts/validate-decisions.py), reusable [validate-decisions.yml](https://github.com/aeroflow-air/aeroflow-workflows/blob/main/.github/workflows/validate-decisions.yml)
