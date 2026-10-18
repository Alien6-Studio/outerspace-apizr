# Academy recording preparation

Parts I–XII share the current local Academy production project under
`.output/academy-videos/`. Its single command entry point is
`.output/academy-videos/production/academy.py`; see the adjacent `README.md`
for reconstruction, validation and manual YouTube kit commands. Published I–V
masters retain their original recorded version and sources. Parts VI–XI use the
0.4.6 candidate. The published [Part XII recording](https://www.youtube.com/watch?v=zkujF-thyyQ)
uses the real Wine example and native VS Code window captures. The Academy index
records its public link and 6:22 duration; this does not declare Apizr 0.4.6 released.
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
Part XII includes the Wine materials, narration for native inspection, history,
comparison and Restricted Mode scenes, its actual editor command list and shot
list. Its episode metadata declares
`recording_interface: vscode-native-window`; these scenes require actual window
footage and must never use a terminal recording as a substitute. Preparation does
not establish that a recording exists.

Copy each prepared production folder into a new local recording project. Use
the shared `prepare_voice.cjs`, `record_episode.py` and `render.py` through
`production/academy.py`; retain the original source hashes alongside adapted
inputs. `render` rebuilds I–XII from retained takes and narration. `record` requires
a new project outside the checkout and an explicitly installed 0.4.6 engine. It
prepares fresh lesson inputs and history without replacing retained masters. Select
an isolated installed candidate engine instead of the old 0.4.3 environment, and read the
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

## Teaching progression

The revised VI–XI scenarios use the existing synthetic fraud example as a common
case. They target advanced Python developers and data scientists who need to
interpret evidence, test failure modes and choose their next action. Each lesson has a concrete question, one
learning objective, a diagram, actual operations broken into readable steps,
interpretation of the observed result, a pause-and-answer exercise and a correction.
Length follows the explanation and reading time rather than a fixed short format.

`academy_curriculum.json` holds the reviewable English narration and exercises.
Preparation exports a fresh `materials/` project, learning objectives and narration
inputs for each lesson. The original written-guide commands remain as references.
`lab.py` reads actual saved engine JSON into short labelled projections; full
reports remain available. Scores are never assigned as demonstration constants.
The explicitly selected `prepare-holdout` action loads the trusted saved model
and derives `evaluation.csv` using the example's actual held-out split.

Parts X–XI start by executing the reviewed fraud notebook in a fresh local copy,
then derive that holdout before recording. They evaluate precision, recall and
flagged volume at different thresholds. The SDK example is `thresholds.py`.
For the live kernel, use `fraud-thresholds.ipynb` with the kernel driver's explicit
`--input evaluation.csv`; the selected CSV hash joins the retained kernel proof.
The notebook remains a terminal view of actual ipykernel execution. Part XII uses
the public UCI Wine dataset, with actual held-out accuracy and
macro F1 from SDK and Jupyter Runs. Its pause-and-answer exercise distinguishes
equal logged scores from claims about generalization. Native VS Code capture
remains separate. Keep the existing voice, colours, typography, opener
and covers; add diagrams and explanations within that visual identity.

Technical media checks establish readable captures, synchronized narration and
valid exports. Editorial review must also establish that the viewer can explain
the result and complete the exercise. A technically valid video is not sufficient
evidence of a useful lesson.

Advanced variants use actual operations: presentation-only notebook edits versus
scientific signal identity; a deliberately altered disposable history copy;
self-comparison with unknown evidence; stale model bytes refused during exposure;
SDK failure/exception propagation; and an intentionally unlogged live calibration
offset. These are explicit teaching mutations, not evidence of successful runs.
The Jupyter example keeps its selected CSV and threshold fixed while changing
live state, so a repeated cell can produce different metrics. A selected input
digest does not identify every object or setting in kernel memory.
