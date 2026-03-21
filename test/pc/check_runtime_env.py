import site

print("usersite=", site.getusersitepackages())

import PIL
import sympy
import torch
import torchaudio
import torchvision
import typing_extensions

print("torch=", torch.__version__, "cuda=", torch.version.cuda, "avail=", torch.cuda.is_available())
print("torchvision=", torchvision.__version__)
print("torchaudio=", torchaudio.__version__)
print("PIL=", PIL.__version__)
print("sympy=", sympy.__version__)
print("typing_extensions=", getattr(typing_extensions, "__version__", "n/a"))
