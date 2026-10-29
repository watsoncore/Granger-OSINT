---
license: mit
tags:
- model_hub_mixin
- plonk
- geolocalization
- diffusion
- pytorch_model_hub_mixin
- yfcc
- riemanian_flow
---

This is a model of the approach described in the paper ["Around the World in 80 Timesteps: A Generative Approach to Global Visual Geolocation"](https://arxiv.org/abs/2412.06781)

```
@misc{dufour2024world80timestepsgenerative,
      title={Around the World in 80 Timesteps: A Generative Approach to Global Visual Geolocation}, 
      author={Nicolas Dufour and David Picard and Vicky Kalogeiton and Loic Landrieu},
      year={2024},
      eprint={2412.06781},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2412.06781}, 
}
```
- Code: https://github.com/nicolas-dufour/plonk
- Docs:
The model can be simply run by doing:
```bash
pip install diff-plonk
```

```python
from plonk import PLONKPipeline

pipeline = PLONKPipeline("nicolas-dufour/PLONK_YFCC")

gps_coords = pipeline(images, batch_size=1024)
```