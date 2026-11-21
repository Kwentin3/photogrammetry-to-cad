"""Small SYNTHETIC pinhole fixture; requires Pillow, never proves capture accuracy."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import random

from PIL import Image, ImageDraw, __version__ as pillow_version


PIN = "71021443af3f7946e8e9025a37634b57e7aad77d"
SOURCE_ROOT = f"https://github.com/alicevision/CCTag/blob/{PIN}/markersToPrint/generators/"
# Exact first two rows (zero-based IDs) of the pinned official cctag3.txt.
RADII = {0: [90, 80, 70, 60, 50], 1: [90, 80, 70, 60, 45]}
BOARD_MM = (320.0, 240.0)
BOARD_PIXELS = (1200, 900)
FRAME_PIXELS = (1200, 900)
K = [[1000.0, 0.0, 600.0], [0.0, 1000.0, 450.0], [0.0, 0.0, 1.0]]
CENTERS = {0: [-50.0, 0.0, 0.0], 1: [50.0, 0.0, 0.0]}
OUTER_RADIUS_MM = 22.0


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(a):
    length = math.sqrt(dot(a, a))
    return [x / length for x in a]


def multiply(a, b):
    return [[dot(row, column) for column in zip(*b)] for row in a]


def inverse3(a):
    # Adjugate, with row/column transpose explicit.
    cofactors = []
    for i in range(3):
        row = []
        for j in range(3):
            minor = [[a[r][c] for c in range(3) if c != j] for r in range(3) if r != i]
            row.append((-1) ** (i + j) * (minor[0][0] * minor[1][1] - minor[0][1] * minor[1][0]))
        cofactors.append(row)
    determinant = dot(a[0], cofactors[0])
    if abs(determinant) < 1e-12:
        raise ValueError("Degenerate homography")
    return [[cofactors[j][i] / determinant for j in range(3)] for i in range(3)]


def project(point, rotation, translation):
    camera = [dot(row, point) + offset for row, offset in zip(rotation, translation)]
    if camera[2] <= 0:
        raise ValueError("Point behind the camera")
    homogeneous = [dot(row, camera) for row in K]
    return [homogeneous[0] / homogeneous[2], homogeneous[1] / homogeneous[2]]


def make_board():
    board = Image.new("L", BOARD_PIXELS, 215)
    draw = ImageDraw.Draw(board)
    random_source = random.Random(20261121)
    for _ in range(2200):
        x = random_source.randrange(BOARD_PIXELS[0])
        y = random_source.randrange(BOARD_PIXELS[1])
        radius = random_source.randrange(3, 15)
        shade = random_source.randrange(25, 200)
        if random_source.random() < 0.5:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=shade)
        else:
            draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=shade)
    pixels_per_mm = BOARD_PIXELS[0] / BOARD_MM[0]
    for marker_id, center in CENTERS.items():
        cx = (center[0] + BOARD_MM[0] / 2) * pixels_per_mm
        cy = (BOARD_MM[1] / 2 - center[1]) * pixels_per_mm
        # White margin proportional to the official generator's radius500/margin400.
        margin_radius = OUTER_RADIUS_MM * 1.4 * pixels_per_mm
        draw.rectangle((cx - margin_radius, cy - margin_radius, cx + margin_radius, cy + margin_radius), fill=255)
        # Official generate.py: outer black disk, then five nested alternating disks.
        for index, ratio in enumerate([100] + RADII[marker_id]):
            radius = OUTER_RADIUS_MM * pixels_per_mm * ratio / 100
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=0 if index % 2 == 0 else 255)
    return board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        parser.error("Fixture output must be outside the checkout")
    if output.exists() and any(output.iterdir()):
        parser.error("Fixture output must be empty; preserve existing evidence")
    images = output / "images"
    images.mkdir(parents=True, exist_ok=True)
    board = make_board()
    board.save(output / "source_board.png")
    pixels_per_mm = BOARD_PIXELS[0] / BOARD_MM[0]
    source_to_world_plane = [[1 / pixels_per_mm, 0, -BOARD_MM[0] / 2],
                             [0, -1 / pixels_per_mm, BOARD_MM[1] / 2], [0, 0, 1]]
    angles = [(-20, -15), (-10, -20), (0, -20), (10, -20), (20, -15),
              (20, 15), (10, 20), (0, 20), (-10, 20), (-20, 15)]
    views = []
    for index, (yaw, pitch) in enumerate(angles):
        center = [500 * math.tan(math.radians(yaw)), 500 * math.tan(math.radians(pitch)), 500.0]
        forward = unit([-value for value in center])
        right = unit(cross(forward, [0.0, 1.0, 0.0]))
        down = cross(forward, right)
        rotation = [right, down, forward]
        translation = [-dot(row, center) for row in rotation]
        plane_camera = [[row[0], row[1], offset] for row, offset in zip(rotation, translation)]
        homography = multiply(multiply(K, plane_camera), source_to_world_plane)
        inverse = inverse3(homography)
        check_identity = multiply(homography, inverse)
        assert max(abs(check_identity[i][j] - (1 if i == j else 0)) for i in range(3) for j in range(3)) < 1e-9
        coefficients = [value / inverse[2][2] for row in inverse for value in row][:8]
        filename = f"synthetic_{index:02}.png"
        with board.transform(FRAME_PIXELS, Image.Transform.PERSPECTIVE, coefficients,
                             Image.Resampling.BICUBIC, fillcolor=110) as frame:
            frame.save(images / filename)
        markers = []
        for marker_id, position in CENTERS.items():
            xy = project(position, rotation, translation)
            radii = []
            for step in range(32):
                angle = 2 * math.pi * step / 32
                edge = [position[0] + OUTER_RADIUS_MM * math.cos(angle),
                        position[1] + OUTER_RADIUS_MM * math.sin(angle), 0.0]
                projected = project(edge, rotation, translation)
                radii.append(math.dist(xy, projected))
            if min(radii) < 30:
                raise ValueError("Projected marker outer radius below 30 pixels")
            markers.append({"id": marker_id, "center_mm": position, "center_px": xy,
                            "minimum_projected_outer_radius_px": min(radii)})
        corners = [project([x, y, 0], rotation, translation)
                   for x, y in [(-160, -120), (160, -120), (160, 120), (-160, 120)]]
        assert all(5 < x < FRAME_PIXELS[0] - 5 and 5 < y < FRAME_PIXELS[1] - 5 for x, y in corners)
        views.append({"file": "images/" + filename, "sha256": hashlib.sha256((images / filename).read_bytes()).hexdigest(),
                      "yaw_pitch_deg": [yaw, pitch], "camera_center_mm": center,
                      "world_to_camera_R": rotation, "world_to_camera_t_mm": translation,
                      "source_pixel_to_image_H": homography, "board_corners_px": corners, "markers": markers})
    board.close()
    truth = {"synthetic": True, "purpose": "Known-distance numerical supplement, not real capture or physical accuracy validation",
             "pillow_version": pillow_version, "units": "mm", "board_size_mm": BOARD_MM,
             "board_texture_pixels": BOARD_PIXELS, "image_size_pixels": FRAME_PIXELS,
             "K": K, "distortion": "none", "horizontal_field_of_view_deg": math.degrees(2 * math.atan(FRAME_PIXELS[0] / (2 * K[0][0]))),
             "camera_convention": "x right, y down, z forward; p_camera=R*p_world+t; board z=0, world y up",
             "marker_center_distance_mm": 100.0, "markers": [{"id": key, "center_mm": value, "radii_percent": [100] + RADII[key]} for key, value in CENTERS.items()],
             "marker_outer_radius_mm": OUTER_RADIUS_MM,
             "sources": {"revision": PIN, "bank_url": SOURCE_ROOT + "cctag3.txt", "bank_git_blob_sha1": "e711a44568f5645a10c43e14cb91569c97eff94b",
                         "generator_url": SOURCE_ROOT + "generate.py", "generator_git_blob_sha1": "5138d35b89301171dd3784d16302decdde758bd8", "source_license": "MPL-2.0"},
             "views": views}
    truth_path = output / "truth.json"
    truth_path.write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    assert json.loads(truth_path.read_text(encoding="utf-8"))["synthetic"] is True
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(json.dumps({"synthetic": True, "views": len(views), "total_bytes": size,
                      "minimum_marker_radius_px": min(m["minimum_projected_outer_radius_px"] for view in views for m in view["markers"])}))


if __name__ == "__main__":
    main()
