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
Only the wand-occluded left curl uses a fitted ImageGen repair; its source and
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

## Remaining acceptance gates

Audit and the source reading gate are complete; the overall reconstruction is
**not yet accepted**. Other scenes, guest choreography, final executable, alpha
backgrounds, scale and performance checks remain. Mathematical joint checks
supplement visual review; changing hashes does not prove animation.

Original master artwork, user profiles, AI/OSINT functionality and old release
artifacts remain protected. No real API requests are needed for animation QA.
