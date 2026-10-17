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
commands. Part XI also includes narration and the live-kernel shot sequence.
Part XII includes narration for native inspection, history and Restricted Mode
scenes, its actual editor command list and shot list. Its episode metadata declares
`recording_interface: vscode-native-window`; these scenes require actual window
footage and must never use a terminal recording as a substitute. Preparation does
not establish that a recording exists.

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

Before each native editor take, verify a preview of the dedicated Academy window
and bind the recorder to that exact window. Exclude the desktop, chat, other
applications and ordinary VS Code workspaces. Stop on a missing or ambiguous
window; do not fall back to display recording. Preserve the approved preview and
window/capture identity with the actual footage. A failed or wrongly framed take
does not qualify the lesson and must not enter the review export.

The optional macOS recorder source is
`scripts/qualification/docs/academy_window.swift` (ScreenCaptureKit, macOS 15+).
Compile it with `swiftc -parse-as-library -swift-version 5` and an explicit output
path outside the checkout. Its `--self-test` checks selection without capturing.
Capture commands refuse missing macOS authorization and never grant it silently.
After explicit operator authorization, `--preview /absolute/new/preview.png`
selects the sole VS Code window whose title starts with `Apizr Academy XII`.
Visually check that preview before `--record /absolute/new/preview.png.json`.
The recorder requires the same window ID and process ID, records no audio or
child windows, and stops when `preview.png.stop` exists or after 180 seconds.
There is no desktop fallback. macOS permission covers more than this selected
window; obtaining it remains a separate operator decision. Without that permission,
retain the scenario and narration as preparation only.

The live-kernel sequence uses
`python -m scripts.qualification.experiments.academy_kernel --notebook /path/to/jupyter-capture.ipynb --workspace /absolute/new/workspace`.
Run it with the installed candidate interpreter and qualified Jupyter dependencies;
`PYTHONPATH` may point at this checkout to load the qualification module. It
reuses the existing qualified kernel lifecycle, sends the committed cells and
repeats `first-variant`. It verifies four retained Runs and their actual kernel
cell counts. `--pause 3` leaves reading time between real executions. The generated
recording commands expect `APIZR_ACADEMY_KERNEL_WORKSPACE` to identify a new
directory outside the checkout. This terminal sequence shows a real kernel;
it does not depict the Jupyter graphical interface.

Review the full rendered movie, sound, captions and cover before publication.
Keep drafts local until the maintainer authorizes publication. Only then add
the actual public URL and measured duration to the Academy index, preserving
click-to-load privacy-enhanced playback and the authoritative written guides.
