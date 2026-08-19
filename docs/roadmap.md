# dashpublish — Roadmap

Direction, not a schedule. Defects are in
[`internal/known-issues.md`](./internal/known-issues.md).

## Where it is

The full pipeline works: index, semantic scan, curate, LLM-planned compile, render, upload, and
publish — from a CLI, a web UI, or a watching daemon. Fake mode runs all of it offline, and the
test suite uses that to cover the pipeline end to end.

## Considered

**Authentication on `serve`.** There is none, and the API can upload to your YouTube channel with
the cached token. Even a single shared password would change what "expose it on the LAN" costs.

**A real database.** Two containers on one SQLite file is fine at current write volumes and is
the first thing to hit if the worker is ever scaled out.

**Overlays on the long profile.** Timestamps, location, or a category label; the profile table
already lists them as absent.

**Cost visibility.** Indexing spends real money per hour of footage, and nothing in the tool says
how much a pending job will cost before it runs. An estimate on `index` would make the
`watch` daemon much easier to leave running.

**Number-plate blurring.** Optional automatic redaction would remove the sharpest edge of the
"should I publish this" question — see [FAQ](./faq.md). It is a real feature, not a filter, which
is why it is here rather than assumed.

**More detection categories.** They are seeded rows, so adding one is cheap; the work is in
writing a query that discriminates well.

## Non-goals

**Publishing automatically.** The two-step flow is the design. A pipeline that took footage from
a memory card to a public video with nobody watching would be both a bad idea and, given what
dashcam footage contains, an irresponsible one.

**Editing beyond cut, crop, and duck.** This assembles clips. Titles, effects, and colour grading
are what a video editor is for, and the EDL is exportable.

**A hosted service.** Self-hosted is the point; a hosted version would mean holding other
people's footage of other people's number plates.

**Removing the manual curation step.** The scan finds candidates and a person decides. The
scoring is good enough to shortlist and not good enough to publish unreviewed — and the
difference between those two is the entire value of the web UI.

**Supporting every dashcam format.** Tesla event folders and generic mp4/mov trees cover the
common cases; ffmpeg handles the rest if you can get the files into a directory.

## Contributing

Issues and pull requests welcome — see the
[Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md).

`DASHPUBLISH_FAKE=1` means you can work on any stage of the pipeline without a key or a bill.
