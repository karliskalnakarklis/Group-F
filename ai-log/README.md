# AI log

Record how you worked with coding agents, so that someone else can follow
what was generated, from which input, and what you changed.

## What to record

For **each variant**, create a file `ai-log/variant-a.md` and
`ai-log/variant-b.md` with:

| Field | Example |
|-------|---------|
| Tool | e.g. Claude Code, Codex, Cursor, GitHub Copilot |
| Model and version | as shown by the tool |
| Date(s) | |
| Who drove the session | |
| Input given | the version of `docs/design.md` (commit hash) and any other files |
| Prompts | the prompts in the order you used them, verbatim |
| Manual changes | what you changed by hand afterwards, with commit hashes |

Exported transcripts are welcome: put them next to the file, for example
`ai-log/variant-a-session-1.md`. Remove secrets and personal data first.

If you also used AI for other parts (design, criteria, DDD analysis,
report), say where and how in the same way, in `ai-log/other.md`.

## Findings

Everything the agent got wrong or did in a risky way goes into
[`findings.md`](findings.md), including what you found before the tests did.
A short list of real findings is worth more than a long list of trivial ones.
