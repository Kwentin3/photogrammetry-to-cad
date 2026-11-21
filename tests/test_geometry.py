"""Synthetic boundary tests; these do not establish a photo-to-CAD integration."""

import copy
import importlib.util
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import open3d as o3d


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load_script("extract_plane")
cad = load_script("build_cad")


class GeometryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-planar-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        # A tilted, non-rectangular quadrilateral. Source units are explicitly synthetic.
        self.outline = np.array([[0., 0.], [3., 0.], [2.4, 1.7], [-.2, 1.1]])
        self.x_axis = np.array([1., 1., 0.]) / np.sqrt(2)
        self.normal = np.array([1., -1., 2.]) / np.sqrt(6)
        self.y_axis = np.cross(self.normal, self.x_axis)
        self.origin = np.array([5., -2., 4.])
        local = [*self.outline]
        # Triangulate only for deterministic fixture sampling, not implementation fitting.
        for i in range(1, len(self.outline) - 1):
            for a in np.linspace(0, 1, 11):
                for b in np.linspace(0, 1 - a, 11):
                    local.append(self.outline[0] * (1 - a - b) + self.outline[i] * a + self.outline[i + 1] * b)
        points = self.origin + np.outer(np.array(local)[:, 0], self.x_axis) + np.outer(np.array(local)[:, 1], self.y_axis)
        self.source = self.directory / "synthetic-nonrectangle.ply"
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
        self.assertTrue(o3d.io.write_point_cloud(str(self.source), cloud))
        roi = [*(points.min(axis=0) - .1), *(points.max(axis=0) + .1)]
        self.parameters = extract.extract_plane(self.source, roi=roi, meters_per_unit=.01,
                                                distance_mm=.001, scale_status="test_assumption",
                                                scale_note="Synthetic fixture: one source unit assigned 10 mm")

    def decided(self, thickness):
        parameters = copy.deepcopy(self.parameters)
        parameters["thickness"] = {"value_mm": thickness, "status": "test_assumption",
                                   "note": "Synthetic CAD test only; no physical thickness measurement"}
        return parameters

    def test_fitted_outline_units_and_tilt_are_preserved(self):
        frame = self.parameters["plane"]
        world = (np.asarray(frame["origin_mm"])
                 + np.outer(np.asarray(self.parameters["outline_mm"])[:, 0], frame["x_axis"])
                 + np.outer(np.asarray(self.parameters["outline_mm"])[:, 1], frame["y_axis"]))
        expected = (self.origin + np.outer(self.outline[:, 0], self.x_axis)
                    + np.outer(self.outline[:, 1], self.y_axis)) * 10
        # Compare in world coordinates; frame choice is intentionally arbitrary.
        for vertex in expected:
            self.assertLess(np.min(np.linalg.norm(world - vertex, axis=1)), 1e-5)
        for vertex in world:
            self.assertLess(np.min(np.linalg.norm(expected - vertex, axis=1)), 1e-5)
        self.assertAlmostEqual(abs(np.dot(frame["normal"], self.normal)), 1, places=8)
        self.assertLess(self.parameters["fit"]["maximum_absolute_residual_mm"], 1e-5)
        self.assertEqual(self.parameters["scale"]["status"], "test_assumption")
        extract.write_question(self.parameters, self.directory / "question.svg")
        self.assertIn("patch-01", (self.directory / "question.svg").read_text())

    def test_negative_normal_keeps_the_same_source_plane_and_offset(self):
        cloud = o3d.io.read_point_cloud(str(self.source))
        points = np.asarray(cloud.points)
        fitted = []

        class OppositePlaneCloud:
            """Native cloud and fit, with the equivalent opposite plane equation."""

            def __init__(self, native):
                self.native = native

            def __getattr__(self, name):
                return getattr(self.native, name)

            def select_by_index(self, indices):
                return OppositePlaneCloud(self.native.select_by_index(indices))

            def segment_plane(self, **kwargs):
                coefficients, indices = self.native.segment_plane(**kwargs)
                if coefficients[np.argmax(np.abs(coefficients[:3]))] > 0:
                    coefficients *= -1  # All four values describe the same plane.
                fitted.append((coefficients, coefficients.copy()))
                return coefficients, indices

        roi = [*(points.min(axis=0) - .1), *(points.max(axis=0) + .1)]
        # Only the sign representation changes; Open3D still selects and fits real points.
        with patch.object(o3d.io, "read_point_cloud", return_value=OppositePlaneCloud(cloud)):
            parameters = extract.extract_plane(
                self.source, roi=roi, meters_per_unit=.01, distance_mm=.001,
                scale_status="test_assumption", scale_note="Synthetic fixture: one source unit assigned 10 mm")
        coefficients, original = fitted[0]
        self.assertLess(original[np.argmax(np.abs(original[:3]))], 0)
        self.assertGreater(abs(original[3]), 1)
        np.testing.assert_array_equal(coefficients, original)
        frame = parameters["plane"]
        origin = np.asarray(frame["origin_mm"])
        self.assertAlmostEqual(float(original[:3] @ origin + original[3]), 0, places=8)
        expected_equation = -original / np.linalg.norm(original[:3])
        np.testing.assert_allclose(frame["equation_mm"], expected_equation, atol=1e-8)
        world = (origin + np.outer(np.asarray(parameters["outline_mm"])[:, 0], frame["x_axis"])
                 + np.outer(np.asarray(parameters["outline_mm"])[:, 1], frame["y_axis"]))
        expected = (self.origin + np.outer(self.outline[:, 0], self.x_axis)
                    + np.outer(self.outline[:, 1], self.y_axis)) * 10
        for vertex in expected:
            self.assertLess(np.min(np.linalg.norm(world - vertex, axis=1)), 1e-5)
        for vertex in world:
            self.assertLess(np.min(np.linalg.norm(expected - vertex, axis=1)), 1e-5)
        self.assertLess(parameters["fit"]["maximum_absolute_residual_mm"], 1e-5)

    def test_unresolved_thickness_blocks_before_any_export(self):
        source = self.directory / "parameters.json"
        source.write_text(json.dumps(self.parameters), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unresolved"):
            cad.build(source, self.directory / "unresolved")
        self.assertFalse((self.directory / "unresolved").exists())

    def test_step_and_parameter_edit_use_actual_builder(self):
        source = self.directory / "parameters.json"
        first = self.decided(2)
        source.write_text(json.dumps(first), encoding="utf-8")
        original = cad.build(source, self.directory / "first")
        self.assertAlmostEqual(original["volume_mm3"], 808, places=5)
        front = (self.origin + np.outer(self.outline[:, 0], self.x_axis)
                 + np.outer(self.outline[:, 1], self.y_axis)) * 10
        all_vertices = np.vstack((front, front + 2 * self.normal))
        np.testing.assert_allclose(original["bounds_min_mm"], all_vertices.min(axis=0), atol=1e-5)
        np.testing.assert_allclose(original["bounds_max_mm"], all_vertices.max(axis=0), atol=1e-5)
        # Execute the emitted standalone code, detached from project imports.
        model = runpy.run_path(str(self.directory / "first" / "model.py"))
        edited = copy.deepcopy(model["PARAMETERS"])
        edited["thickness"]["value_mm"] = 5
        rebuilt = model["export_and_inspect"](edited, self.directory / "edited.step")
        self.assertAlmostEqual(rebuilt["volume_mm3"] / original["volume_mm3"], 2.5, places=7)
        self.assertEqual(first["outline_mm"], edited["outline_mm"])
        self.assertEqual(first["plane"], edited["plane"])
        self.assertTrue(original["valid"] and rebuilt["valid"])
        self.assertEqual(original["solids"], 1)

    def test_invalid_frame_is_rejected_instead_of_repaired(self):
        parameters = self.decided(2)
        parameters["plane"]["x_axis"][0] += .1
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            cad.make_shape(parameters)


if __name__ == "__main__":
    unittest.main()
