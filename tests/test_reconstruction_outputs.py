"""File/export boundaries and actual local mesh reading; no native compute."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruction
import reconstruction_report as reporting


OBJ = b'v 1 -2 -3\nv 4 -6 -8\nv 0 0 0\nf 1 2 3\n'


class ReconstructionOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='reconstruction-outputs-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cache = self.root / 'cache' / 'native-uid'
        self.cache.mkdir(parents=True)
        self.output = self.root / 'results'
        self.output.mkdir()
        self.mesh = self.cache / 'mesh.obj'
        self.mesh.write_bytes(OBJ)
        self.cloud = self.root / 'dense.ply'
        header = b'ply\nformat binary_little_endian 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nend_header\n'
        self.cloud.write_bytes(header + struct.pack('<ffffff', 1, 2, 3, 4, 6, 8))
        self.scene = self.root / 'scene.json'
        self.scene.write_text(json.dumps({'views': [], 'poses': [], 'intrinsics': [], 'structure': []}), encoding='utf-8')
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text('{}', encoding='utf-8')
        self.settings = self.root / 'effective-settings.json'
        self.config = {'runtime': {}, 'input_manifest': str(self.manifest), 'scale': {'mode': 'unknown'}}
        self.settings.write_text(json.dumps(self.config), encoding='utf-8')

    def test_native_mesh_is_copied_exactly_and_never_overwritten(self):
        receipt = reconstruction.save_native_mesh(self.mesh, self.output)
        self.assertEqual(Path(receipt['path']).read_bytes(), OBJ)
        self.assertEqual(self.mesh.read_bytes(), OBJ)
        self.assertEqual(receipt['sha256'], reconstruction.sha(self.mesh))
        self.assertEqual(receipt['node_output'], 'Meshing.outputMesh')
        self.mesh.write_bytes(OBJ + b'# changed\n')
        with self.assertRaisesRegex(FileExistsError, 'Preserve previous mesh'):
            reconstruction.save_native_mesh(self.mesh, self.output)
        self.assertEqual(Path(receipt['path']).read_bytes(), OBJ)

    def test_gltf_keeps_native_sibling_buffer_bundle(self):
        source = self.cache / 'mesh.gltf'
        source.write_text(json.dumps({'buffers': [{'uri': 'mesh.bin', 'byteLength': 4}]}), encoding='utf-8')
        (self.cache / 'mesh.bin').write_bytes(b'1234')
        receipt = reconstruction.save_native_mesh(source, self.output)
        saved = Path(receipt['path'])
        bundle = json.loads(saved.read_text(encoding='utf-8'))
        self.assertEqual((saved.parent / bundle['buffers'][0]['uri']).read_bytes(), b'1234')
        self.assertEqual(saved.read_bytes(), source.read_bytes())
        with self.assertRaisesRegex(FileExistsError, 'Preserve previous mesh bundle'):
            reconstruction.save_native_mesh(source, self.output)

    def test_actual_mesh_read_preserves_raw_frame_and_reports_native_rotation(self):
        before = self.mesh.read_bytes()
        cwd = Path.cwd()
        result = reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        self.assertEqual(result['cloud']['point_count'], 2)
        self.assertEqual(result['mesh']['vertex_count'], 3)
        self.assertEqual(result['mesh']['triangle_count'], 1)
        self.assertEqual(result['mesh']['bbox_min'], [0, -6, -8])
        transform = result['mesh']['mesh_to_cloud']
        self.assertEqual(transform['bbox_max_in_cloud_frame'], [4, 6, 8])
        self.assertEqual(transform['bbox_delta_max'], 3)
        self.assertFalse(transform['applied_to_file'])
        self.assertEqual(result['mesh']['units'], 'unknown')
        self.assertEqual(self.mesh.read_bytes(), before)
        self.assertEqual(Path.cwd(), cwd)

    def test_point_cloud_cannot_substitute_for_surface_and_cwd_is_restored(self):
        self.mesh.write_bytes(b'v 0 0 0\nv 1 1 1\n')
        cwd = Path.cwd()
        with self.assertRaisesRegex(ValueError, 'point cloud is not a mesh'):
            reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        self.assertEqual(Path.cwd(), cwd)

    def test_mutating_bound_mesh_is_rejected_at_unchanged_path(self):
        self.config['mesh_export'] = {'sha256': reconstruction.sha(self.mesh)}
        self.settings.write_text(json.dumps(self.config), encoding='utf-8')
        reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        self.mesh.write_bytes(OBJ + b'# real mutation\n')
        with self.assertRaisesRegex(ValueError, 'Mesh differs from saved native export'):
            reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)

    def test_cli_preserves_mesh_even_when_settings_are_invalid(self):
        self.settings.write_text('invalid JSON', encoding='utf-8')
        result = subprocess.run([sys.executable, reporting.__file__, '--scene', str(self.scene),
                                 '--cloud', str(self.cloud), '--settings', str(self.settings),
                                 '--mesh', str(self.mesh), '--output', str(self.mesh)],
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Output must differ', result.stderr)
        self.assertEqual(self.mesh.read_bytes(), OBJ)


if __name__ == '__main__':
    unittest.main()
