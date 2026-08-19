# Known Issues — dashpublish

Concrete defects and gaps found while writing this repository's documentation in
August 2026. **Nothing here was changed** — each one needs a code, configuration, or
licensing decision rather than a documentation one.

Ordered by severity. See [`docs/roadmap.md`](../roadmap.md) for the narrative version,
which also covers deliberate non-goals.

**0 open.**

Unusually for this sweep, reading through this repository turned up nothing worth recording as a
defect. That is a finding in itself, so the checks that were made are listed here rather than
left implicit.

## What was checked

| Area | Result |
|---|---|
| `.gitignore` coverage | `/dashpublish.toml`, `/footage/`, `/music/`, `.env`, and the sqlite files are all ignored. 221 MB of sample footage is untracked, as is the real config |
| Secrets in the repository | None. `dashpublish.example.toml` carries no keys, and the file states that secrets live in environment variables |
| The publish guard | `PrivacyStatus = Literal["private", "unlisted"]` — `upload_compilation` cannot produce a public video, and the only `set_privacy(..., "public")` call is reached solely by `publish go` |
| Upload preconditions | `upload_compilation` refuses a compilation that is not `rendered`, or whose `output_path` does not exist on disk |
| Destructive-flag safety | `scan --dry-run` uses a throwaway database and a fake client, so it cannot touch real data |
| Documentation accuracy | The README's CLI reference, config table, and environment table all matched the code |

## Things the documentation now states that were previously implicit

Not defects, but worth having written down:

- **`[embeddings].backend` has a bill attached** — roughly $2.84 per hour of footage on the
  Gemini default. The README mentioned it under Troubleshooting; it is now in the quickstart, the
  configuration page, and the FAQ, because it is a decision made before the first real run.
- **`serve` has no authentication, and the cached OAuth token is a refresh token for the user's
  YouTube channel.** Anyone reaching the port can upload to it. Stated in `api.md`,
  `deployment.md`, and `faq.md`.
- **Publishing dashcam footage identifies other people.** The two-step flow is partly a pause for
  that consideration; `faq.md` says so.

---

## Also, across every repository

**`.bandit` is present on disk but untracked in git.** Verified in PyWorkout, treklogger,
skyscanner-cli, booking-cli, piggy, and aibot — the config file exists locally in each but
`git ls-files` does not know about it, so none of it reached GitHub.

The August 2026 security sweep therefore looks complete locally and landed nowhere. Worth
checking across all 44 repositories it covered.
