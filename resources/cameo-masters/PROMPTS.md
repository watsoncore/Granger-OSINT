# Cameo masters: prompts and provenance

Built-in ImageGen was used for Draco and Ron, with transparent_background=true
and `grangerpet/assets/character.png` as the local style reference. No vendor
installer, CLI fallback, API key or image uploaded through the Granger gateway
was used. Outputs were copied into this directory; originals were left intact.

## Draco — successful prompt

Use case: style-transfer. Create a project sprite by transforming the supplied
full-body Hermione sprite into DRACO MALFOY as a child Hogwarts student, age about
11–13. Input image is the strict drawing/style/proportions reference. Match exactly
its flat 2D chibi design: very large head, tiny robed body, clean dark brown outline,
simple cel fills, muted colors, identical eye design/detail density and brown-outline
shoes. One single complete full-body boy, slight three-quarter facing toward viewer's
left so he can talk to Hermione. Pale short straight side-parted platinum-blond hair,
small sly skeptical expression, gray-green eyes, black school robe with muted green
lining, white collar, silver-and-green tie, dark trousers, brown shoes. One small
expressive open hand near his chest, other hand down; simple relaxed standing pose,
both hands and feet visible. Same head-to-body ratio as reference, head roughly
55–60 percent of figure height. No wand, no book, no other characters. Entire figure
has clear margins and no cropped limbs. Genuine transparent alpha background, no
ground shadow or scenery, no labels, no text. Preserve 2D flat chibi style; no
realistic face, no 3D, no painterly shading, no gradients or glossy rendering.
Output is a clean reusable raster sprite master.

## Ron — successful prompt

Use case: style-transfer. Transform the supplied Hermione sprite into RON WEASLEY
as a Hogwarts boy for the same desktop sprite family. Input is the strict drawing
style/proportion reference. Exactly one complete full-body flat 2D chibi character,
huge head and tiny robed body, dark brown clean outline, simple cel fills and same
muted colors/detail density as Hermione. Tousled orange-red short hair, freckles
on cheeks, soft brown eyes, a friendly slightly awkward open-mouth smile. Black
school robe with burgundy lining, white shirt collar, burgundy-gold tie, dark
trousers, brown shoes. Stand in three-quarter view facing left; one small open hand
near chest conversational gesture, other hand down. Head occupies about 55–60
percent of figure height. Entire hair, hands and feet complete within generous
transparent margins. Genuine transparent alpha background, no scenery, no shadow,
no letters, no text, no other figures, no wand or book. Same face stylization as
reference. No realism, no 3D, no painterly or glossy render; clean reusable cartoon
sprite.

## Harry — deterministic native derivation

Two built-in generation attempts failed at output moderation (category `other`):
20b19b1e-9791-4ae7-bc90-3e6cbe860fd7 and a69c9ca7-c53d-447a-ad9c-15bfb0bb1a0a.
No successful generated Harry image is claimed. No CLI fallback was attempted.

The existing project raster/contour pipeline was extended instead. The normalized
Ron master keeps exactly the same body/outline proportions; documented masks change
hair to charcoal and irises to green. QPainter adds round dark frames and the small
lightning scar. Reproducible code: `scripts/build_pet_scene_assets.py`. Harry shares
the master family's outlines rather than using a separately rendered realistic face.

## Assembly

Normalize alpha (discard only values <=8 from nearly invisible generator noise),
crop by nonempty alpha, fit a complete 484px-high figure in a 512px transparent
canvas, align all feet to y=500. No white-background keying. The production renderer
uses the same size for Hermione and each guest. A head nod, separated greeting arm,
mouth and blink are articulated by QPainter; no video/model calls run at playback.
Original Hermione masters and all seven original atlases remain unchanged.
Hashes are recorded in `grangerpet/assets/scenes/provenance.json`.

The reference creator/license was not established in the existing project.
No claim of authorship of the reference or ownership of franchise characters.
