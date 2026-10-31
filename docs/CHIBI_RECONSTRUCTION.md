# Chibi reconstruction: audit and acceptance

The released baseline is commit `b4acbe778ffd0262764b1936b0e40ef45525ee33`.
Its executable SHA-256 is
`4126f5ecdf9cadbe95765ca77c41b3950826a96b04027c5964f76b102f13f458`.

## Reproduced defects

The released executable was run with an isolated profile and captured 39 times
through its live production surface. The two inspection scripts preserve those
captures; this is native surface evidence, not a desktop video. The first driver
failed while packing the GIF after successful shutdown (Pillow `size` is a
property); its original report is retained and a separate assembly report records
the repair. Evidence is under `output/chibi-reconstruction/`.

* Reading arms have fixed endpoints and are painted before the book. The book
  hides both hands; no shared grip transform exists.
* Page motion uses elapsed modulo 4.2 seconds independently of the fingers.
* Head motion is about two degrees. The samples inspected have open eyes;
  the code has a short periodic blink. The user's closed-eye screenshot alone
  does not establish a permanently closed-eye bug.
* The head polygon clips the right hair contour and leaves the original wand
  crossing the left hair. Torso/limb masks also need clean overlap boundaries.
* Guests use a rotating cropped arm and head with unrelated periodic mouth
  motion. Harry is a recolored Ron with glasses; independent art is still needed.
* Scene images render at 256 pixels, downsample to logical size, then scale again
  to the monitor DPR. Live scenes need direct device-pixel rendering.
* The 720-second guest category gap and 1200–1800-second individual cooldowns
  make the current scenes too rare for their low category weight.

## Reading gate

`scene_pose.py` now describes retrieval, opening, line scans, a finger-led curled
page, closing and pocket occlusion. `articulated.py` resolves two-bone arms and
draws hands over the book. The costume/face/footwear remain source textures.
The wand-occluded left curl and garment-contaminated lower fringe use a fitted ImageGen repair; its source and
hashes are recorded in `assets/scenes/articulated-provenance.json`. The original
master is unchanged. Independent head and overlapping side-curl roots replace
the old clipped head layer. Reading renders at requested device resolution.

Three 18-second live source-window recordings contain 436 native widget grabs
each, averaging 23.81 captured frames/second. Their 12-moment timelines were
inspected for closed retrieval, both grips, scanning, page contact and stowing.
Evidence: `output/chibi-reconstruction/reading-native-source/`. These recordings
predate the final secondary-curl split; final EXE evidence is still required.
The offline 100/195/512-pixel timelines are explicitly labeled as deterministic
renderer previews. Nine physical/narrative checks pass; the relevant pet suite
passes 71 checks. One real defect caught by continuity checks—a wrist snapping
back to the first page corner after turning—was repaired, not waived.

## Critical addendum: reopened visual gates

The user rejected the earlier guest storyboards. Those recordings remain
historical evidence and are **not final visual acceptance**. The addendum is
tracked in the existing reconstruction; no project or face redesign was started.

The released EXE was additionally captured 99 times in the Malfoy scene.
`diagnose_draco_loop.py` reproduces the later preview's exact folded sleeve
functions and disables logical layers. The sleeve-only render contains 2554
enclosed transparent pixels; the united sleeve pieces contain zero. The old
torso mask also retained a separate original sleeve/hand fragment. A 256px head
crop retained detached shoulder corners. Garment isolation and jaw/hair masks
remove those independent defects. Painter matrices restore exactly, and all
intermediate surfaces use premultiplied alpha. The native released EXE and the
later procedural preview are explicitly distinguished in the diagnosis report.

`key_poses.py` now supplies authored full-body drawings: turn, explain, point,
open palms, listen, wave, reject, folded arms, stomp, wand retort, retreat, nod
and glasses adjustment. Polar forearm inbetweens prevent elbows passing through
wrists; bounded projected joints keep both segments anatomical. The note is
64x44 source pixels, with explicit `held_by_ron → transferring →
held_by_hermione` ownership and two edge contacts. Ron releases an open palm;
Hermione retracts, raises, reads, reacts, acknowledges and stows the one note.

Real compositor capture over the owned application with text is available.
It verifies an opaque owned client and rejects foreign occlusion before and
after BitBlt. Early attempts were rejected for foreground/occlusion and a crop
with the dock closed. Cloaked windows are now distinguished and the existing
Hermione area is opened for this QA; no interface design changes were made.
Successful source evidence is under `addendum-real-text-dock/`. The isolated
background is temporarily topmost during recording and restored afterward.

Final executable, full-motion review of all variants, measured performance,
natural guest scheduling and release preservation remain required.

## Other tracks and shared guest stage

The same actor renderer now handles the seven base states, all legacy local
actions, three shy and annoyed variants, four wand variants, phone and daydream.
The sleeve contour unites drawn tapered pieces before outlining: a folded
envelope could intersect itself and expose background holes. An alpha review on white also caught old
sleeves surviving in the head and torso masks; those fragments are removed.
The elbow bend sign was corrected so resting arms bend outward. Drag poses use
independent hip/knee/ankle transforms instead of slicing/scaling a whole raster.

Guests have source heads/torso/footwear and independent joint arms, heads, gaze,
mouths and stride. Harry has a new independent ImageGen master. One owned,
input-transparent stage paints both actors and one note at a shared timestamp;
the primary pet retains its live hit region. Ron's note has explicit transfer
ownership and two edge grips during handoff. There are two Malfoy, Harry and Ron
conversation scripts. Reading interruption, closing/stowing and note reading
use the same character/prop anchors as solo scenes.

The initial source guest recording was interrupted by real mouse input and is
retained as failed visual evidence. A separate guarded recording of all four
guest actions averages about 23.8 native widget captures/second. Recording-only
click-through prevents the isolated QA overlay intercepting user clicks; it is
restored when recording ends. Normal interaction QA uses ordinary input.

Guest deadlines now start after 120–240 seconds, with 300–600 seconds between
category starts, per-scene 600–900-second cooldowns, actor anti-repeat and overdue
category selection. The clock remains figure-relative. No room or an occupied
arbiter postpones a guest instead of cutting off the current action.

Audit is complete; visual acceptance is **in progress**, with the earlier source
gates reopened by the critical addendum. The final executable, all variants,
native backgrounds, scale and performance checks remain. Mathematical joint checks
supplement visual review; changing hashes does not prove animation.

Original master artwork, user profiles, AI/OSINT functionality and old release
artifacts remain protected. No real API requests are needed for animation QA.

The focused native pet suite passed 141 checks before the last interpolation
polish; the current choreography regression file passes 21 checks, including
physical grips, segment bounds, continuity, original-sleeve exclusion and the
specific hollow-sleeve regression. These are supporting checks, not an artistic
quality verdict. The final full suite and frozen-source verification are pending.
