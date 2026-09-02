# Recall batteries

Probes for [the taxonomy](../SKILL.md#taxonomy). Every hit needs semantic judgment — the batteries over-match by design and under-match by nature, so pair them with an unpatterned read of the densest prose in scope.

## Invocation rules

- Exclusions go last so a later include cannot re-admit them: append `--glob '!node_modules/**' --glob '!apps/web/dist/**' --glob '!.claude/skills/ss-trim-cot-leakage/**'` (this skill quotes leaked wording as calibration) plus any recorded fixture directory in scope.
- Natural-language lines carry `-i` so sentence-initial capitals hit ("This PR adds…", "Probably fine…"). The first line matches code-ish patterns and stays case-sensitive — `-i` would turn `\bT\d\b` into noise.
- Bound complete phrases. `\bthis PR\b` must match "this PR adds" without matching "this project", "this process", or "this provider".
- A zero-hit pattern proves nothing until it matches a known positive; a noisy pattern proves nothing until it rejects a near-miss negative. Calibrate both before trusting a corpus result.
- Restrict to prose-bearing files when a probe is noisy: `--glob '*.{py,ts,tsx,md,yml,yaml}'`.

## English battery

```sh
rg -n '\(decision \d|\(audit [A-Z]\d|design §|plan §|\bP-I\b|\bT\d\b' <scope>
rg -n -i '\bthis PR\b|\bthis branch\b|\blater PRs?\b|\bprevious commits?\b|\bthis commit\b' <scope>
rg -n -i '\bused to\b|\bno longer\b|\bpreviously\b|\bthe old\b|\bwas renamed\b|\bwas moved\b|\bwe removed\b' <scope>
rg -n -i '\bfor now\b|this cut|\btoday\b|\bcurrently we\b|roadmap|\bTBD\b' <scope>
rg -n -i 'rejected in review|review round|the reviewer|as requested' <scope>
rg -n -i 'probably |should be enough|should suffice|it simply|is safe —|is safe --|just to be safe' <scope>
```

## Chinese-residue battery

```sh
# Chinese slips in otherwise-English Markdown.
rg -n '设计稿|评审|上一?轮|旧版|老的|不再|以前|本版|遗留|临时|先这样' --glob '*.md' <scope>

# Chinese slips in English code comments and docstrings.
rg -n '#[^\r\n]*(评审|旧版|老的|不再|以前|遗留|临时|先这样)' --glob '*.py' <scope>
rg -n '(//|/\*|\*)[^\r\n]*(评审|旧版|老的|不再|以前|遗留|临时|先这样)' --glob '*.{ts,tsx,js,jsx,css}' <scope>
```

## Known false-positive families

Expect these; judge and keep them.

- **Instrumental "used to"** — "the key used to sign requests". The temporal form has a subject state before it.
- **Runtime old/new** — "the old session drains before the new one accepts orders" names live objects during handover.
- **"This PR" in process docs** — `AGENTS.md` and PR templates legitimately say "PR".
- **`v1` as a path or protocol segment** — `/api/v1/...`, wire-format names.
- **"currently" describing runtime state** — "the position currently held" is state, not repo history.
- **Migration and compatibility facts** — "rows written before the default may hold NULL" is a live data contract.
- **"today" in prompts and tests that ask for the current date** — natural time, not a version stamp. Wording that reaches a model or user still needs behavior evidence before any edit.
- **`# noqa` / `# type: ignore` reasons** — required prose; fix a wrong reason rather than deleting it.
