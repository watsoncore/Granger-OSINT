# Optional visual CPU models

GeoCLIP © 2024 Vicente Vivanco, MIT. The official geoclip1.3.0 distribution
provides its heads and GPS gallery. OpenAI CLIP © 2021 OpenAI, MIT, supplies
the CLIP ViT-L/14 backbone through a pinned safetensors conversion.

Waypoint © 2026 KillaMeep, MIT. Granger translates selected preprocessing,
sampling and adaptive LightGlue control flow into an offline Python worker.
The Waypoint desktop application and retrieval clients are not copied.

PLONK © 2024 Nicolas Dufour, MIT. The selected YFCC model is converted into
one ONNX Riemannian flow step. Original DINOv2 ViT-L/14 with registers is
Apache2.0; its position embedding is resampled to336px in the published ONNX.
DISK depth and LightGlue DISK pretrained weights are Apache2.0. DISK is
exported as a UNet graph; LightGlue is split into stage graphs.

Granger uses the published graphs unchanged, limits DISK keypoints to1024
for CPU, and adds its own normalized8-point RANSAC geometric check. This
check differs from Waypoint's seven-point implementation.

The full original licenses/model cards accompany this notice. Their pinned
sources and SHA256 are in provenance.json; individual model artifact hashes
are in grangerpet/visual_models/manifest.json. Original wheel license files
remain in optional site-packages/*dist-info/licenses.

StreetCLIP, SuperPoint, Cell-DINO and Xray-DINO weights are not included.
