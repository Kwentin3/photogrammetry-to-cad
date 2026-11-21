"""Local input/attribute-boundary checks; no Meshroom or GPU computation."""

import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruction


PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1sAAAAASUVORK5CYII=')


class AttributeNode:
    """Storage double for native attributes, not a reconstruction engine."""

    def __init__(self, kind, **values):
        self.nodeType = kind
        self.name = kind + '_1'
        self.attributes = {name: SimpleNamespace(value=value, isLink=False)
                           for name, value in values.items()}

    def attribute(self, name):
        return self.attributes[name]


class ReconstructionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='reconstruction-preflight-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        images = self.root / 'images'
        images.mkdir()
        files = []
        for name in ('first.png', 'second.png'):
            path = images / name
            path.write_bytes(PNG)
            files.append({'name': name, 'bytes': len(PNG), 'sha256': reconstruction.sha(path)})
        (self.root / 'manifest.json').write_text(json.dumps({
            'schema_version': 1, 'complete': True, 'files': files}), encoding='utf-8')
        self.config = {'pipeline': 'standard', 'images': 'images',
                       'input_manifest': 'manifest.json', 'resources': {'threads': 2},
                       'nodes': {}, 'scale': {'mode': 'unknown'}}

    def args(self, suffix):
        path = self.root / (suffix + '.json')
        path.write_text(json.dumps(self.config), encoding='utf-8')
        return argparse.Namespace(settings=path, run=self.root / ('run-' + suffix),
                                  meshroom=self.root / 'runtime-not-installed')

    def assert_rejected_before_runtime(self, suffix, message):
        args = self.args(suffix)
        with mock.patch.object(reconstruction, 'init_runtime',
                               side_effect=AssertionError('Invalid input reached native runtime')):
            with self.assertRaisesRegex(ValueError, message):
                reconstruction.prepare(args)
        self.assertFalse(args.run.exists())

    def test_all_cctag_variants_rejected_before_native_runtime(self):
        for index, describer in enumerate(('cctag3', 'cctag4', 'CCTAG3', 'CcTag4', 'CCTagFuture')):
            with self.subTest(describer=describer):
                self.config['nodes'] = {'FeatureExtraction_1': {'describerTypes': ['dspsift', describer]}}
                self.assert_rejected_before_runtime('marker-' + str(index), 'CCTag ID encoding')

    def test_empty_wrong_extension_and_directory_masks_fail_before_runtime(self):
        self.config['pipeline'] = 'legacy'
        for case in ('empty', 'wrong-extension', 'directory'):
            with self.subTest(case=case):
                folder = self.root / case
                folder.mkdir()
                if case == 'wrong-extension':
                    (folder / 'first.jpg').write_bytes(PNG)
                elif case == 'directory':
                    (folder / 'first.png').mkdir()
                self.config['masks'] = {'folder': case, 'extension': 'png'}
                self.assert_rejected_before_runtime(case, 'at least one .png file')

    def test_preflight_accepts_actual_matching_file(self):
        folder = self.root / 'masks'
        folder.mkdir()
        (folder / 'first.png').write_bytes(PNG)
        actual = reconstruction.preflight_masks(self.root, {'folder': 'masks', 'extension': '.png'})
        self.assertEqual(actual, (folder.resolve(), 'png'))

    def test_legacy_masks_enforce_exr_alpha_and_metadata(self):
        feature = AttributeNode('FeatureExtraction', masksFolder='', maskExtension='exr', maskInvert=True)
        dense = AttributeNode('PrepareDenseScene', masksFolders=[], maskExtension='exr',
                              outputFileType='jpg', saveMetadata=False)
        graph = SimpleNamespace(nodes=[feature, dense])
        folder = self.root / 'masks'
        reconstruction.configure_masks(graph, 'legacy', {}, folder, 'png')
        self.assertEqual(dense.attribute('outputFileType').value, 'exr')
        self.assertIs(dense.attribute('saveMetadata').value, True)
        self.assertEqual(dense.attribute('masksFolders').value, [str(folder)])
        self.assertEqual(dense.attribute('maskExtension').value, 'png')
        self.assertEqual(feature.attribute('masksFolder').value, str(folder))
        self.assertIs(feature.attribute('maskInvert').value, False)

    def test_standard_dense_only_masks_use_native_export_attributes(self):
        feature = AttributeNode('FeatureExtraction')
        dense = AttributeNode('ExportImages', masksFolders=[], maskExtension='exr')
        folder = self.root / 'masks'
        reconstruction.configure_masks(SimpleNamespace(nodes=[feature, dense]), 'standard',
                                       {'features': False}, folder, 'png')
        self.assertEqual(dense.attribute('masksFolders').value, [str(folder)])
        self.assertEqual(dense.attribute('maskExtension').value, 'png')
        self.assertEqual(feature.attributes, {})


if __name__ == '__main__':
    unittest.main()
