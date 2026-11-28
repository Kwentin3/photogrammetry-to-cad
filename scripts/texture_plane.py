"""Project one original photo onto a fitted planar patch; preserve source units."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from visible_patch_camera import camera, project

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--plane', type=Path, required=True)
    p.add_argument('--photo', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    scene = json.loads(a.scene.read_text(encoding='utf-8'))
    plane = json.loads(a.plane.read_text(encoding='utf-8'))
    if hashlib.sha256(a.scene.read_bytes()).hexdigest() != plane['scene_sha256']:
        raise ValueError('The fitted plane belongs to another camera scene')
    if a.out_dir.exists() and any(a.out_dir.iterdir()):
        raise ValueError('Select an empty output directory')
    cam = camera(scene, a.photo.name)
    width, height = cam['size']
    corners = np.array(plane['patch_corners'])
    uv = np.array(plane['patch_uv']); low, high = uv.min(0), uv.max(0)
    tex_width = 1024
    tex_height = max(64, round(tex_width * (high[1]-low[1]) / (high[0]-low[0])))
    if tex_height > 4096:
        tex_width = max(1, round(tex_width * 4096 / tex_height))
        tex_height = 4096
    x, y = np.meshgrid((np.arange(tex_width)+.5)/tex_width, 1-(np.arange(tex_height)+.5)/tex_height)
    world = np.array(plane['origin']) + (low[0]+x*(high[0]-low[0]))[..., None]*plane['u'] + (low[1]+y*(high[1]-low[1]))[..., None]*plane['v']
    pixels, depth = project(world, cam)
    image = np.array(Image.open(a.photo).convert('RGB'))
    if image.shape[:2] != (height, width):
        raise ValueError('Original photo dimensions differ from the saved scene')
    px, py = pixels[..., 0], pixels[..., 1]
    if not ((depth > 0) & (px >= 0) & (py >= 0) & (px < width-1) & (py < height-1)).all():
        raise ValueError('Plane extends outside the original photo')
    texture = np.stack([map_coordinates(image[..., channel].astype(float), [py, px], order=1, mode='nearest') for channel in range(3)], -1).clip(0, 255).astype('uint8')
    a.out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(texture).save(a.out_dir/'panel-texture.png')
    with (a.out_dir/'panel.obj').open('w', encoding='utf-8') as f:
        f.write('# Native OBJ coordinates, arbitrary source units; no physical scale.\nmtllib panel.mtl\n')
        for point in corners*[1, -1, -1]:
            f.write('v '+' '.join(map(str, point))+'\n')
        for coord in (uv-low)/(high-low):
            f.write('vt '+' '.join(map(str, coord))+'\n')
        f.write('usemtl panel\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')
    (a.out_dir/'panel.mtl').write_text('newmtl panel\nKd 1 1 1\nKa 1 1 1\nKs 0 0 0\nillum 1\nmap_Kd panel-texture.png\n', encoding='utf-8')
    print(json.dumps({'obj':str(a.out_dir/'panel.obj'), 'texture_size':[tex_width, tex_height]}))

if __name__ == '__main__':
    main()
