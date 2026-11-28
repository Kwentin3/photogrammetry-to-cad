"""Projection into an original AliceVision pinhole/radialk3 photograph with square pixels."""
from pathlib import Path

import numpy as np


def camera(scene, image):
    view = next(v for v in scene['views'] if Path(v['path']).name == image)
    intr = next(i for i in scene['intrinsics'] if i['intrinsicId'] == view['intrinsicId'])
    pose = next(p for p in scene['poses'] if p['poseId'] == view['poseId'])['pose']['transform']
    if intr['type'] != 'pinhole' or intr['distortionType'] != 'radialk3' or float(intr['pixelRatio']) != 1:
        raise ValueError('Only the qualified pinhole/radialk3 camera is supported')
    return dict(rotation=np.array(pose['rotation'], float).reshape(3, 3),
                center=np.array(pose['center'], float),
                size=np.array([view['width'], view['height']], float),
                focal=float(intr['focalLength']) / float(intr['sensorWidth']) * float(view['width']),
                principal=np.array(intr['principalPoint'], float),
                distortion=np.array(intr['distortionParams'], float))


def project(points, cam):
    local = (points - cam['center']) @ cam['rotation']
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        xy = local[..., :2] / local[..., 2:]
        r2 = np.sum(xy * xy, axis=-1)
        k = cam['distortion']
        xy = xy * (1 + k[0]*r2 + k[1]*r2**2 + k[2]*r2**3)[..., None]
        xy = xy * cam['focal'] + (cam['size']/2 + cam['principal'])
    return xy, local[..., 2]
