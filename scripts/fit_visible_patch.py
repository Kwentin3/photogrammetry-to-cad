"""Fit one visible planar patch from two registered image ROIs.

Selection JSON contains views with image, role (fit1, fit2, holdout), and
normalized_polygon. Coordinates and residuals retain the source cloud units.
The scene must use the AliceVision pinhole/radialk3 camera schema.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

# Open3D parallel RANSAC can otherwise change its sampled winner between runs.
os.environ['OMP_NUM_THREADS'] = '1'
import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, Delaunay


from visible_patch_camera import camera, project


def roi_mask(points, cam, polygon, depth_check):
    pixels_xy, depth = project(points, cam)
    xy = pixels_xy / cam['size']
    finite = np.isfinite(xy).all(1) & np.isfinite(depth)
    mask = np.zeros(len(points), bool)
    polygon = np.asarray(polygon, dtype=float)
    if polygon.ndim != 2 or polygon.shape[1] != 2 or not np.isfinite(polygon).all() or np.any((polygon < 0) | (polygon > 1)):
        raise ValueError("Expected finite normalized image coordinates")
    hull = ConvexHull(polygon).vertices.tolist()
    first = hull.index(0) if 0 in hull else 0
    order = hull[first:] + hull[:first]
    if order not in [list(range(len(polygon))), [0, *range(len(polygon)-1, 0, -1)]]:
        raise ValueError("Image ROI must be an ordered convex polygon")
    mask[finite] = (depth[finite] > 0) & (Delaunay(polygon).find_simplex(xy[finite]) >= 0)
    if depth_check:
        # 4px nearest-depth cells reject points behind observed foreground.
        size = np.ceil(cam['size']/4).astype(int)
        pixels = (np.nan_to_num(np.clip(xy, -1000, 1000))*cam['size']/4).astype(int)
        valid = finite & (depth > 0) & (pixels >= 0).all(1) & (pixels < size).all(1)
        keys = np.clip(pixels[:, 1], 0, size[1]-1)*size[0] + np.clip(pixels[:, 0], 0, size[0]-1)
        nearest = np.full(int(np.prod(size)), np.inf)
        np.minimum.at(nearest, keys[valid], depth[valid])
        mask &= depth <= nearest[keys] + .03
    return mask


def residual_summary(values, threshold):
    if not len(values):
        return dict(points=0, absolute_residual_quantiles=None, fraction_within_threshold=None)
    return dict(points=len(values), absolute_residual_quantiles=dict(zip(
        ['p50', 'p90', 'p95', 'max'], np.quantile(values, [.5, .9, .95, 1]).tolist())),
        fraction_within_threshold=float(np.mean(values <= threshold)))


def write_obj(path, points, comment):
    with path.open('w', encoding='ascii') as stream:
        stream.write('# ' + comment + '\n')
        for point in points:
            stream.write('v ' + ' '.join(map(str, point)) + '\n')
        for point in [[0, 0], [1, 0], [1, 1], [0, 1]]:
            stream.write('vt ' + ' '.join(map(str, point)) + '\n')
        stream.write('f 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')


def run(cloud_path, scene_path, selection_path, threshold, out_dir):
    if threshold <= 0 or not np.isfinite(threshold):
        raise ValueError('Threshold must be finite and positive in source units')
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError('Output directory must be empty; preserve prior accepted artifacts')
    scene = json.loads(scene_path.read_text(encoding='utf8'))
    selection = json.loads(selection_path.read_text(encoding='utf8'))
    fit_views = [v for v in selection['views'] if v['role'].startswith('fit')]
    if len(fit_views) != 2 or fit_views[0]['image'] == fit_views[1]['image']:
        raise ValueError('Exactly two fit image ROIs are required')
    cloud = o3d.io.read_point_cloud(str(cloud_path))
    points = np.asarray(cloud.points)
    if not len(points) or not np.isfinite(points).all():
        raise ValueError('Expected a nonempty finite source cloud')
    selected = np.ones(len(points), bool)
    cameras = []
    selection_evidence = []
    for view in fit_views:
        cam = camera(scene, view['image'])
        mask = roi_mask(points, cam, view['normalized_polygon'], True)
        selected &= mask
        cameras.append(cam)
        selection_evidence.append(dict(image=view['image'], polygon=view['normalized_polygon'], points=int(mask.sum())))
    indices = np.flatnonzero(selected)
    if len(indices) < 30:
        raise ValueError('Fit ROI intersection contains fewer than 30 points')
    train_idx = indices[np.arange(len(indices)) % 5 != 0]
    holdout_idx = indices[np.arange(len(indices)) % 5 == 0]
    training = cloud.select_by_index(train_idx.tolist())
    o3d.utility.random.seed(42)
    _, inliers = training.segment_plane(threshold, 3, 2000)
    support_idx = train_idx[inliers]
    support = points[support_idx]
    origin = support.mean(0)
    _, _, vh = np.linalg.svd(support-origin, full_matrices=False)
    normal = vh[-1]
    if normal[np.argmax(abs(normal))] < 0:
        normal *= -1
    axis = np.eye(3)[np.argmin(abs(normal))]
    u = axis - (axis @ normal)*normal
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    uv = np.column_stack(((support-origin)@u, (support-origin)@v))
    low, high = np.quantile(uv, [.02, .98], axis=0)
    rectangle = np.array([[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]]])
    center = rectangle.mean(0)
    for factor in np.arange(1, .04, -.01):
        final_uv = center + (rectangle-center)*factor
        corners = origin + final_uv[:, :1]*u + final_uv[:, 1:]*v
        if all(roi_mask(corners, cam, view['normalized_polygon'], False).all()
               for cam, view in zip(cameras, fit_views)):
            break
    else:
        raise ValueError('Cannot place a rectangle inside both observed image ROIs')
    camera_direction = np.mean([cam['center'] for cam in cameras], axis=0)-origin
    facing_normal = normal.copy()
    if normal @ camera_direction < 0:
        corners = corners[::-1]
        final_uv = final_uv[::-1]
        facing_normal *= -1
    report = dict(source_sha256=hashlib.sha256(cloud_path.read_bytes()).hexdigest(),
        scene_sha256=hashlib.sha256(scene_path.read_bytes()).hexdigest(),
        selection_sha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        units='source units; physical scale unknown', coordinate_system='plane/frame in native PLY; final patch.obj in native OBJ',
        obj_from_ply=[1, -1, -1], source_points=len(points), roi_points=len(indices),
        train_points=len(train_idx), support_points=len(support_idx), threshold=threshold,
        origin=origin.tolist(), u=u.tolist(), v=v.tolist(), normal=normal.tolist(),
        normal_toward_cameras=facing_normal.tolist(),
        plane=[*normal.tolist(), float(-normal@origin)],
        support_rms=float(np.sqrt(np.mean(((support-origin)@normal)**2))),
        point_holdout=residual_summary(abs((points[holdout_idx]-origin)@normal), threshold),
        patch_corners=corners.tolist(), patch_uv=final_uv.tolist(),
        patch_corners_obj=(corners*[1, -1, -1]).tolist(), rectangle_shrink_factor=float(factor),
        all_vertices_inside_both_fit_polygons=True, fit_views=selection_evidence,
        depth_selection=dict(cell_pixels=4, tolerance_source_units=.03),
        limitations=['One interior visible planar patch; wall boundaries, openings and thickness are not inferred',
                    'No metric scale or independent depth truth; residuals compare to the same reconstructed cloud',
                    '2-98 percent support rectangle is shrunk to fit both image ROIs; not an observed material boundary'])
    for view in selection['views']:
        if view['role'] != 'holdout':
            continue
        cam = camera(scene, view['image'])
        mask = roi_mask(points, cam, view['normalized_polygon'], False)
        observed = points[mask]
        local = np.column_stack(((observed-origin)@u, (observed-origin)@v))
        same = Delaunay(final_uv).find_simplex(local) >= 0
        report['view_holdout'] = dict(image=view['image'], **residual_summary(abs((observed-origin)@normal), threshold))
        report['view_holdout_same_patch'] = dict(image=view['image'], **residual_summary(abs((observed[same]-origin)@normal), threshold),
            selection='Image ROI intersected with final in-plane footprint; no residual-based selection')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir/'plane.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    np.save(out_dir/'selected-indices.npy', indices)
    o3d.io.write_point_cloud(str(out_dir/'support.ply'), cloud.select_by_index(support_idx.tolist()))
    write_obj(out_dir/'patch.obj', corners*[1, -1, -1], 'Native OBJ coordinates; camera-facing winding; source units')

    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['cloud', 'scene', 'selection', 'out-dir']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--threshold', type=float, required=True)
    args = parser.parse_args()
    report = run(args.cloud, args.scene, args.selection, args.threshold, args.out_dir)
    print(json.dumps({key: report[key] for key in ['roi_points', 'support_points', 'rectangle_shrink_factor', 'support_rms']}, indent=2))


if __name__ == '__main__':
    main()
