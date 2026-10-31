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

## Acceptance gates

Audit is complete; reconstruction is **not yet accepted**. Reading must first
show retrieval of a closed book, two-hand opening/grip, open downward gaze,
finger-led page turn, closing and physical stowing. Review at 100 and 195 pixels
before expanding the same articulation to other scenes. Mathematical joint
checks supplement visual review; changing hashes does not prove animation.

Original master artwork, user profiles, AI/OSINT functionality and old release
artifacts remain protected. No real API requests are needed for animation QA.
