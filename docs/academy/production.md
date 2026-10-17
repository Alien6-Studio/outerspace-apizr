# Academy recording preparation

Parts VI–XII continue the existing Academy production project. The original
local sources are in `.output/academy-videos/production` and
`.output/install-tutorial/production`, rather than in the published site.
The narrator explicitly reuses Continuum Attest's local Kokoro voice:
`af_heart`, speed `1.04`, quantized Kokoro 82M. Keep the existing Apizr colours,
logo, terminal layout, chapter cards, captions, closing sequence and covers.

Prepare reviewable lesson inputs from the executable written guides:

```sh
python3 -m scripts.qualification.docs.academy_lessons --output /absolute/new/directory
```

The output directory must be outside the checkout and must not already exist.
The manifest records source and guide identities. Parts VI–X include compatible
`production/episode.json`, `production/narration.json` and the exact guide
commands. Parts XI–XII include their notebook or actual editor command list and
a shot list. Preparation does not establish that a recording exists.

Copy each prepared production folder into a new local recording project. Use
the original `prepare_voice.cjs`, `record_episode.py` and `make_movie.py`; retain
the original source hashes alongside any adapted copies. Select an isolated
installed candidate engine instead of the old 0.4.3 environment, and read the
hero version from the episode metadata. Do not overwrite Parts I–V or reuse old
Run history. Rehearse the guide commands before real-time recording.

For terminal lessons, retain actual casts, command exit statuses, capture hashes,
speed and the final media validation. Narration and captions must match what is
visible. A live-kernel recording is required for Part XI. Part XII requires
the real installed VS Code extension, including stale-result and Restricted Mode
behaviour; a terminal demonstration is not evidence of the editor journey.

Review the full rendered movie, sound, captions and cover before publication.
Keep drafts local until the maintainer authorizes publication. Only then add
the actual public URL and measured duration to the Academy index, preserving
click-to-load privacy-enhanced playback and the authoritative written guides.
