"""Predeclared E1-FILL replacement only; not a model runner or authorization."""
import numpy as np
import torch
import torch.nn.functional as F


def gaussian_replacement(image):
    x=np.asarray(image)
    if x.ndim!=2 or x.dtype!=np.float32 or min(x.shape)<=10 or not np.isfinite(x).all():
        raise ValueError('finite prepared float32 image, dimensions > reflection pad required')
    with torch.no_grad():
        offsets=torch.arange(-10,11,dtype=torch.float32)
        kernel=torch.exp(-.5*(offsets/5.)**2);kernel/=kernel.sum()
        kernel=(kernel[:,None]*kernel[None,:])[None,None]
        value=F.conv2d(F.pad(torch.from_numpy(x.copy())[None,None],(10,10,10,10),mode='reflect'),kernel)
    return value[0,0].numpy().copy()
