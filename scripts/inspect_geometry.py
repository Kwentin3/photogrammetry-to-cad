"""Render real cloud/mesh and source frames with repeatable scene-camera views.

Uses native Open3D readers and an orthographic Pillow preview; no GUI server,
texture, smoothing, hidden-surface reconstruction or implicit geometry edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw, ImageFont


def artifact(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


def native_read(path, mesh=False):
    """Relative ASCII basename avoids the qualified Windows Unicode IO issue."""
    path = Path(path).resolve(strict=True)
    previous = Path.cwd()
    try:
        os.chdir(path.parent)
        result = (o3d.io.read_triangle_mesh(path.name) if mesh
                  else o3d.io.read_point_cloud(path.name))
    finally:
        os.chdir(previous)
    if result.is_empty():
        raise ValueError(f"Empty or unreadable geometry: {path}")
    return result


def render(args):
    inputs = {key: artifact(value) for key, value in vars(args).items()
              if key in ("cloud", "mesh", "scene", "compare_cloud", "highlight_cloud") and value}
    inputs["script"] = artifact(__file__)
    inputs["context"] = [artifact(path) for path in args.context]
    cloud = native_read(args.cloud)
    points = np.asarray(cloud.points).copy()
    mesh = native_read(args.mesh, mesh=True)
    vertices = np.asarray(mesh.vertices).copy()
    if args.mesh_axes == "obj":
        vertices *= np.array([1., -1., -1.])
    faces = np.asarray(mesh.triangles).copy()
    after = (np.asarray(native_read(args.compare_cloud).points).copy()
             if args.compare_cloud else None)
    highlight = (np.asarray(native_read(args.highlight_cloud).points).copy()
                 if args.highlight_cloud else None)
    for array in (points, vertices, after, highlight):
        if array is not None and (not len(array) or not np.isfinite(array).all()):
            raise ValueError("Geometry must be nonempty and finite")
    if not len(faces) or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Invalid triangle indices")
    scene = json.loads(args.scene.read_text(encoding="utf-8-sig"))
    views = {Path(item["path"]).name: item for item in scene["views"]}
    poses = {str(item["poseId"]): item["pose"]["transform"]
             for item in scene["poses"]}
    origin = np.median(points, axis=0)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
        small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17)
    except OSError:
        font = small = ImageFont.load_default()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    figures = []
    for name in args.view:
        frame = args.frames / name
        frame_info = artifact(frame)
        pose = poses[str(views[name]["poseId"])]
        # AliceVision serializes Eigen matrices in column-major order.
        rotation = np.asarray(pose["rotation"], dtype=float).reshape(3, 3).T
        if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-7):
            raise ValueError("Invalid scene camera rotation")
        p = (points - origin) @ rotation.T
        v = (vertices - origin) @ rotation.T
        panels = [("Before cloud" if after is not None else "Cloud", p, None)]
        if after is not None:
            panels.append(("After cloud", (after - origin) @ rotation.T, None))
        panels.append(("Original raw mesh", v, faces))
        # Bounds include every input point and triangle, including removed points.
        bounds = np.concatenate([a[:, :2] for _, a, _ in panels])
        low, high = bounds.min(0), bounds.max(0)
        margin = .03 * np.maximum(high - low, 1e-9)
        low -= margin
        high += margin
        width, height = 600 * len(panels), 1160
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((15, 10), f"Source {name} / scene view {views[name]['viewId']}",
                  font=font, fill="black")
        draw.text((15, 42), "Orthographic camera / common bounds / all points and faces / artificial color / coordinate units follow source; preview does not establish physical scale",
                  font=small, fill="black")
        with Image.open(frame) as source:
            source.thumbnail((550, 350))
            canvas.paste(source, (20, 75))
        draw.text((600, 90), "Source is perspective; geometry views are orthographic.",
                  font=small, fill="black")
        draw.text((600, 120), "Use originals for identity and coverage, not pixel overlay.",
                  font=small, fill="black")
        scale = min(550 / (high[0] - low[0]), 635 / (high[1] - low[1]))
        for col, (title, coords, triangles) in enumerate(panels):
            x0, y0 = col * 600 + 15, 470
            draw.rectangle((x0, y0, x0 + 570, y0 + 665), fill=(239, 242, 245))
            pad = (np.array([570, 665]) - scale * (high - low)) / 2
            xy = np.array([x0, y0]) + pad + (coords[:, :2] - low) * scale
            if triangles is None:
                for i in np.argsort(coords[:, 2])[::-1]:
                    draw.point(tuple(xy[i]), fill=(25, 65, 125))
                if col == 0 and highlight is not None:
                    marked = (highlight - origin) @ rotation.T
                    marked_xy = np.array([x0, y0]) + pad + (marked[:, :2] - low) * scale
                    for pixel in marked_xy:
                        draw.ellipse((pixel[0] - 1, pixel[1] - 1, pixel[0] + 1, pixel[1] + 1), fill=(220, 50, 25))
                count = f"{len(coords):,} points"
            else:
                tri = coords[triangles]
                normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                shade = .35 + .6 * np.abs(normals[:, 2]) / np.maximum(np.linalg.norm(normals, axis=1), 1e-30)
                for i in np.argsort(tri[:, :, 2].mean(1))[::-1]:
                    k = shade[i]
                    draw.polygon([tuple(q) for q in xy[triangles[i]]],
                                 fill=(int(k * 115), int(k * 184), int(k * 242)))
                count = f"{len(triangles):,} triangles"
            draw.text((x0, y0 - 30), f"{title}: {count}", font=font, fill="black")
        if highlight is not None:
            draw.text((600, 150), "Red: highlighted points overlaid on Before (including occluded points).", font=small, fill=(200, 40, 20))
        output = args.output_dir / f"geometry-{Path(name).stem}.png"
        canvas.save(output)
        figures.append({"image": artifact(output), "source": frame_info,
                        "view_id": views[name]["viewId"], "rotation": rotation.tolist(),
                        "origin": origin.tolist(), "projected_bounds": [low.tolist(), high.tolist()],
                        "pixels_per_scene_unit": float(scale)})
    for key in ("cloud", "mesh", "scene", "compare_cloud", "highlight_cloud"):
        if key in inputs and artifact(getattr(args, key)) != inputs[key]:
            raise ValueError(f"Source changed during review: {key}")
    result = {"status": "rendered_requires_visual_review", "inputs": inputs,
              "runtime": {"python": platform.python_version(), "open3d": o3d.__version__,
                          "numpy": np.__version__},
              "mesh_axes": args.mesh_axes, "cloud_points": len(points),
              "compare_cloud_points": None if after is None else len(after),
              "mesh_vertices": len(vertices), "mesh_triangles": len(faces),
              "geometry_unchanged": True, "figures": figures,
              "display": "all geometry, no crop/decimation; descending camera Z painter; artificial shading"}
    output = args.evidence or args.output_dir / "geometry-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(output), "figures": [r["image"]["path"] for r in figures]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud", type=Path, required=True)
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--mesh-axes", choices=("obj", "ply"), default="obj",
                        help="Native AliceVision OBJ needs diag(1,-1,-1); exported PLY axes do not")
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--view", action="append", required=True, help="Exact original frame basename; repeat for several views")
    parser.add_argument("--compare-cloud", type=Path)
    parser.add_argument("--highlight-cloud", type=Path, help="Overlay selected points in red on the first cloud, including occluded points")
    parser.add_argument("--context", type=Path, action="append", default=[], help="Settings, frame manifest or project to record by SHA")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, help="Private JSON destination; contains absolute input paths")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
