# dashpublish — FAQ

### What does it cost to run?

Indexing is the expensive part: roughly **$2.84 per hour of footage** on sentrysearch's Gemini
backend at default settings. Scanning and compiling are cheap; publishing is free.

Start with a small folder. `[embeddings].backend = "local"` runs a Qwen3-VL model on your own
hardware instead — no per-clip cost, but it needs a GPU.

### Can I try it without paying anything?

Yes. `DASHPUBLISH_FAKE=1` runs the whole pipeline offline with no keys — sentrysearch, the LLM,
and YouTube are all replaced with fakes. Do that first.

### Can it accidentally make a video public?

No. `publish upload` uses `[youtube].default_privacy`, which is typed to accept only `private` or
`unlisted` — `"public"` is not a value it will take. The only way to a public video is running
`dashpublish publish go` yourself.

### Should I be publishing dashcam footage at all?

Worth thinking about before you do, and the tool cannot think about it for you.

The moments this surfaces are, by definition, ones where somebody drove badly — and the footage
contains their vehicle, their number plate, sometimes their face, and the road outside wherever
it happened. Depending on where you are, publishing that may engage data-protection law, and it
may invite a level of attention on an identifiable person that the moment does not warrant.

The two-step publish flow exists partly for this: it is a deliberate pause between "the computer
made a video" and "the world can see it". Use it.

### Do I need sentrysearch?

For real indexing, yes — it does the semantic video search. `dashpublish init` warns rather than
failing if it is absent, so you can explore everything else in fake mode.

### Which embeddings backend should I use?

`gemini` is the default and the cheapest to start. `dashscope` is an alternative hosted option.
`local` costs nothing per clip and needs a GPU.

### Why is my video still private after uploading?

By design. Run `dashpublish publish go RECORD_ID` once you have watched it.

If you meant "why can I not verify my OAuth app": unverified apps are capped at 100 users, which
is irrelevant for personal use, and Google's review is not worth pursuing for a personal tool.
Add yourself as a test user.

### Does the LLM see my footage?

It sees the **edit decision list inputs** — clip metadata, timings, and categories — not the
video itself. Embeddings are produced by sentrysearch with whichever backend you configured; that
is the component that processes the footage.

### Can I run it fully offline?

For a demo, yes — fake mode. For real use, `[embeddings].backend = "local"` and
`[llm].provider = "ollama"` move both models onto your hardware. YouTube publishing obviously
needs the network.

### Does `scan --dry-run` change anything?

No. It uses a throwaway database and a fake client, so it never touches your real data — which is
what makes it safe for tuning thresholds.

### Is the web UI safe to expose?

No. There is no authentication, and the API can upload to your YouTube channel using the cached
token. Keep it local or put it behind a proxy that authenticates. See
[Deployment](./deployment.md).

### What is `#Shorts` doing in my title?

The short profile guarantees the suffix, because YouTube uses it to classify the video. The long
profile leaves the title alone.
