"""Real relocatable OBJ/MTL/PNG boundary; native loading is a storage double.

These tests qualify export accounting and reporting, not native computation.
"""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruction as reconstruction
import reconstruction_bundle as bundles
import reconstruction_report as reporting


class StoredAttribute:
    isLink = False

    def __init__(self, value):
        self.value = value

    def getPrimitiveValue(self):
        return self.value


class StoredNode:
    def __init__(self, name, kind, inputs, resolved, outputs):
        self.name, self.nodeType, self.globalStatus = name, kind, 'SUCCESS'
        self.serialized = {'nodeType': kind, 'uid': kind + '-native-uid',
                           'inputs': inputs, 'outputs': outputs}
        self.attrs = {key: StoredAttribute(value) for key, value in {**resolved, **outputs}.items()}

    def attribute(self, name):
        return self.attrs[name]

    def __getattr__(self, name):
        return self.attrs[name]

    def toDict(self):
        return deepcopy(self.serialized)


class DerivedExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='derived-export-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.run = self.root / 'run'
        self.run.mkdir()
        self.cache = self.root / 'cache' / 'Texturing' / 'native-uid'
        self.cache.mkdir(parents=True)
        self.raw = self.root / 'raw.obj'
        self.raw.write_bytes(b'v 0 0 0\nv 2 -3 -4\nv 1 -2 -1\nf 1 2 3\n')
        self.mesh = self.cache / 'texturedMesh.obj'
        self.mesh.write_bytes(b'mtllib texturedMesh.mtl\n' + self.raw.read_bytes().replace(
            b'f 1 2 3', b'usemtl TextureAtlas_1001\nf 1 2 3\nusemtl TextureAtlas_1002\nf 1 3 2'))
        self.mtl = self.cache / 'texturedMesh.mtl'
        self.mtl.write_text('newmtl TextureAtlas_1001\nmap_Kd texture_1001.png\n'
                            'norm normal_1001.png\ndisp displacement_1001.png\n'
                            'newmtl TextureAtlas_1002\nmap_Kd texture_1002.png\n', encoding='utf-8')
        from PIL import Image
        for name in ('texture_1001.png', 'texture_1002.png', 'normal_1001.png', 'displacement_1001.png'):
            Image.new('RGB', (3, 2), (123, 74, 11)).save(self.cache / name)
        (self.cache / 'unused-native-file.txt').write_text('preserve whole native Texturing directory')
        (self.cache / 'empty.log').touch()
        self.dense = self.root / 'densePointCloud.usda'
        self.dense.write_text('#usda 1.0\nprepend payload = @densePointCloud_landmarks.usdc@\n', encoding='utf-8')
        self.payload = self.root / 'densePointCloud_landmarks.usdc'
        self.payload.write_bytes(b'pinned-leaf-fixture')
        self.images = self.root / 'prepared-images'
        self.images.mkdir()
        (self.images / '42.exr').write_bytes(b'upstream file accounting only')
        inputs = {'inputMesh': '{MeshFiltering_1.outputMesh}', 'input': '{Meshing_1.output}',
                  'imagesFolder': '{DepthMap_1.imagesFolder}', 'textureSide': 2048, 'downscale': 1,
                  'outputColorSpace': 'sRGB', 'fillHoles': False, 'subdivisionTargetRatio': 0.0,
                  'colorMapping': {'enable': True, 'colorMappingFileType': 'png'}}
        resolved = {**inputs, 'inputMesh': str(self.raw), 'input': str(self.dense),
                    'imagesFolder': str(self.images)}
        self.texturing = StoredNode('Texturing_1', 'Texturing', inputs, resolved,
                                    {'outputMesh': str(self.mesh), 'output': str(self.cache)})
        self.meshing = StoredNode('Meshing_1', 'Meshing', {}, {}, {'outputMesh': str(self.raw)})
        self.graph = SimpleNamespace(nodes=[self.texturing, self.meshing],
                                     node=lambda name: next((n for n in self.graph.nodes if n.name == name), None))
        self.project = self.run / 'project.mg'
        reconstruction.write(self.project, {'graph': {self.texturing.name: self.texturing.toDict()}})
        self.manifest = self.root / 'manifest.json'
        reconstruction.write(self.manifest, {})
        self.scene = self.root / 'scene.json'
        reconstruction.write(self.scene, {'views': [], 'poses': [], 'intrinsics': [], 'structure': []})
        self.cloud = self.root / 'dense.ply'
        self.cloud.write_bytes(b'ply\nformat binary_little_endian 1.0\nelement vertex 2\n'
                               b'property float x\nproperty float y\nproperty float z\nend_header\n'
                               + struct.pack('<ffffff', 0, 0, 0, 2, 3, 4))
        self.settings_path = self.run / 'effective-settings.json'
        self.settings = {'runtime': {'alicevision_git_commit': 'd012d055'}, 'scale': {'mode': 'unknown'},
                         'settings_sha256': 'configured-input-settings-binding',
                         'project': str(self.project), 'input_manifest': str(self.manifest),
                         'input_manifest_sha256': reconstruction.sha(self.manifest),
                         'mesh_export': {'path': str(self.raw), 'sha256': reconstruction.sha(self.raw)},
                         'artifacts': {'mesh': str(self.raw)},
                         'artifact_sha256': {'mesh': reconstruction.sha(self.raw),
                                             'scene': reconstruction.sha(self.scene),
                                             'cloud': reconstruction.sha(self.cloud)}}
        reconstruction.write(self.settings_path, self.settings)
        self.output = self.root / 'derived'

    def export(self, node='Texturing_1'):
        # External native graph/decoder boundaries only. Filesystem closure,
        # hashes, copy, snapshots, settings update, and report remain real.
        with mock.patch.object(reconstruction, 'load', side_effect=lambda run:
                               (self.run, reconstruction.read(self.settings_path), self.graph, None)), \
                mock.patch.object(reconstruction, 'native_mask_size', bundles.image_size):
            reconstruction.export_derived(argparse.Namespace(run=self.run, node=node, output=self.output))
        return reconstruction.read(self.output / 'derived-export.json')

    def test_complete_relocated_bundle_and_actual_parameter_provenance(self):
        before = self.raw.read_bytes()
        receipt = self.export()
        self.assertEqual(receipt['node']['serialized']['uid'], 'Texturing-native-uid')
        self.assertEqual(receipt['node']['serialized']['inputs']['inputMesh'], '{MeshFiltering_1.outputMesh}')
        self.assertEqual(receipt['node']['resolved']['inputs']['inputMesh'], str(self.raw))
        self.assertEqual(receipt['node']['resolved']['inputs']['textureSide'], 2048)
        self.assertEqual(receipt['node']['resolved']['inputs']['outputColorSpace'], 'sRGB')
        self.assertEqual(receipt['upstream']['input']['payloads'][0]['sha256'], reconstruction.sha(self.payload))
        self.assertEqual(len(receipt['bundle']['maps']), 4)
        self.assertEqual(receipt['bundle']['maps'][0]['size'], [3, 2])
        self.assertTrue((self.output / 'model/unused-native-file.txt').is_file())
        self.assertTrue((self.output / 'model/empty.log').is_file())
        effective = reconstruction.read(self.settings_path)
        for field in ('artifacts', 'artifact_sha256', 'mesh_export'):
            self.assertEqual(effective[field], self.settings[field])
        self.assertEqual(self.raw.read_bytes(), before)
        relocated = self.root / 'relocated'
        shutil.move(self.output, relocated)
        result = reporting.report(self.scene, self.cloud, self.settings_path, mesh_path=self.raw,
                                  derived_paths=[relocated / 'derived-export.json'])
        self.assertEqual(result['mesh']['processing'], 'raw native Meshing output; no filtering/smoothing')
        self.assertIn('Texturing native output', result['derived_meshes'][0]['mesh']['processing'])
        self.assertEqual(result['derived_meshes'][0]['provenance']['bundle']['maps'], receipt['bundle']['maps'])
        self.assertEqual(self.raw.read_bytes(), before)

    def test_missing_map_blocks_export_before_any_copy_or_settings_mutation(self):
        (self.cache / 'normal_1001.png').unlink()
        before = self.settings_path.read_bytes()
        with self.assertRaises(FileNotFoundError):
            self.export()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.settings_path.read_bytes(), before)

    def test_real_map_mutation_and_missing_dependency_fail_report(self):
        self.export()
        settings = reconstruction.read(self.settings_path)
        copied_map = self.output / 'model' / 'texture_1002.png'
        from PIL import Image
        Image.new('RGB', (3, 2), (0, 255, 0)).save(copied_map)
        with self.assertRaisesRegex(ValueError, 'differs from saved export manifest'):
            reporting.verified_derived(self.output / 'derived-export.json', settings)
        copied_map.unlink()
        with self.assertRaises(FileNotFoundError):
            reporting.verified_derived(self.output / 'derived-export.json', settings)

    def test_incomplete_copy_of_whole_texturing_folder_is_not_accepted(self):
        copytree = shutil.copytree

        def omit_native_file(source, destination):
            result = copytree(source, destination)
            (Path(destination) / 'unused-native-file.txt').unlink()
            return result

        before = self.settings_path.read_bytes()
        with mock.patch.object(reconstruction.shutil, 'copytree', side_effect=omit_native_file):
            with self.assertRaisesRegex(ValueError, 'Native output changed during copy'):
                self.export()
        self.assertEqual(self.settings_path.read_bytes(), before)
        self.assertFalse((self.output / 'derived-export.json').exists())

    def test_native_parameters_must_match_saved_project_before_export(self):
        self.texturing.serialized['inputs']['textureSide'] = 4096
        with self.assertRaisesRegex(ValueError, 'Save the native project'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_in_progress_native_result_cannot_be_exported_as_completed(self):
        self.texturing.globalStatus = 'RUNNING'
        with self.assertRaisesRegex(ValueError, 'requires native SUCCESS'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_export_receipt_cannot_be_substituted_without_owner_binding(self):
        receipt = self.export()
        receipt['node']['serialized']['inputs']['fillHoles'] = True
        reconstruction.write(self.output / 'derived-export.json', receipt)
        with self.assertRaisesRegex(ValueError, 'no saved export binding'):
            reporting.verified_derived(self.output / 'derived-export.json', reconstruction.read(self.settings_path))

    def test_unsupported_model_format_is_explicit_and_does_not_create_output(self):
        other = self.cache / 'texturedMesh.gltf'
        other.write_text('{}', encoding='utf-8')
        self.texturing.attrs['outputMesh'].value = str(other)
        self.texturing.serialized['outputs']['outputMesh'] = str(other)
        reconstruction.write(self.project, {'graph': {self.texturing.name: self.texturing.toDict()}})
        with self.assertRaisesRegex(ValueError, 'OBJ material bundles only'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_used_material_without_diffuse_map_is_incomplete(self):
        self.mtl.write_text(self.mtl.read_text(encoding='utf-8').replace('map_Kd texture_1002.png', ''))
        with self.assertRaisesRegex(ValueError, 'lack photographic diffuse'):
            self.export()

    def test_saved_raw_binding_rejects_changed_source_before_derived_copy(self):
        self.raw.write_bytes(self.raw.read_bytes() + b'# changed upstream\n')
        with self.assertRaisesRegex(ValueError, 'Raw Meshing source differs'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_actual_map_mutation_and_removed_map_fail_verification_after_relocation(self):
        self.export()
        from PIL import Image
        path = self.output / 'model/texture_1001.png'
        Image.new('RGB', (3, 2), (9, 8, 7)).save(path)
        effective = reconstruction.read(self.settings_path)
        with self.assertRaisesRegex(ValueError, 'differs from saved export manifest'):
            reporting.verified_derived(self.output / 'derived-export.json', effective)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            reporting.verified_derived(self.output / 'derived-export.json', effective)

    def test_changed_native_parameters_must_be_saved_first(self):
        self.texturing.serialized['inputs']['textureSide'] = 4096
        with self.assertRaisesRegex(ValueError, 'Save the native project'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_raw_sha_gate_does_not_accept_derived_mesh(self):
        self.export()
        with self.assertRaisesRegex(ValueError, 'Mesh differs from saved native export'):
            reporting.report(self.scene, self.cloud, self.settings_path,
                             mesh_path=self.output / 'model/texturedMesh.obj')

    def test_forged_receipt_is_rejected_even_with_self_consistent_bundle(self):
        self.export()
        path = self.output / 'derived-export.json'
        receipt = reconstruction.read(path)
        receipt['node']['resolved']['inputs']['textureSide'] = 8192
        reconstruction.write(path, receipt)
        with self.assertRaisesRegex(ValueError, 'no saved export binding'):
            reporting.verified_derived(path, reconstruction.read(self.settings_path))

    def test_missing_usd_payload_blocks_export(self):
        self.payload.unlink()
        with self.assertRaises(FileNotFoundError):
            self.export()
        self.assertFalse(self.output.exists())

    def test_undefined_or_external_material_links_fail(self):
        original = self.mesh.read_text(encoding='utf-8')
        for reference in ('../outside.mtl', '/outside.mtl', 'C:/outside.mtl'):
            with self.subTest(reference=reference):
                self.mesh.write_text(original.replace('texturedMesh.mtl', reference), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'External or traversing'):
                    self.export()
        self.mesh.write_text(original.replace('usemtl TextureAtlas_1001', 'usemtl undefined'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Undefined OBJ materials'):
            self.export()

    def test_filtering_exports_only_mesh_closure_and_preserves_raw(self):
        mesh = self.cache / 'filtered.obj'
        mesh.write_bytes(self.raw.read_bytes() + b'# derived topology\n')
        filtering = StoredNode('MeshFiltering_1', 'MeshFiltering', {'inputMesh': '{Meshing_1.outputMesh}',
                               'smoothingIterations': 0}, {'inputMesh': str(self.raw), 'smoothingIterations': 0},
                               {'outputMesh': str(mesh)})
        self.graph.nodes.append(filtering)
        project = reconstruction.read(self.project)
        project['graph'][filtering.name] = filtering.toDict()
        reconstruction.write(self.project, project)
        receipt = self.export('MeshFiltering_1')
        self.assertEqual([item['path'] for item in receipt['bundle']['files']], ['filtered.obj'])
        self.assertEqual(receipt['node']['resolved']['inputs']['smoothingIterations'], 0)
        reporting.verified_derived(self.output / 'derived-export.json', reconstruction.read(self.settings_path))


if __name__ == '__main__':
    unittest.main()
