"""Local input/attribute-boundary checks; no Meshroom or GPU computation."""

import argparse
import base64
import json
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

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

    def test_legacy_rejects_unsupported_cctag_before_runtime(self):
        self.config['pipeline'] = 'legacy'
        for node in ('FeatureExtraction_1', 'FeatureMatching_1'):
            for index, describer in enumerate(('cctag4', 'CCTAG4', 'CCTAG3', 'cctagFuture')):
                with self.subTest(node=node, describer=describer):
                    self.config['nodes'] = {node: {'describerTypes': ['dspsift', describer]}}
                    self.assert_rejected_before_runtime(node + '-unsupported-' + str(index), 'Only cctag3')

    def test_legacy_cctag3_is_not_blocked_by_family_guard(self):
        self.config['pipeline'] = 'legacy'
        self.config['nodes'] = {'FeatureExtraction_1': {'describerTypes': ['dspsift', 'cctag3']}}
        # Proves only admission at the Python/runtime boundary, not native compute.
        with mock.patch.object(reconstruction, 'init_runtime', side_effect=RuntimeError('native boundary')):
            with self.assertRaisesRegex(RuntimeError, 'native boundary'):
                reconstruction.prepare(self.args('supported-cctag3'))

    def test_explicit_cache_inside_checkout_is_rejected_without_creating_run(self):
        args = self.args('bad-cache')
        args.cache = reconstruction.REPO / 'cache'
        with mock.patch.object(reconstruction, 'init_runtime', side_effect=AssertionError('No native work needed')):
            with self.assertRaisesRegex(ValueError, 'outside the checkout'):
                reconstruction.prepare(args)
        self.assertFalse(args.run.exists())

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

    def test_explicit_standard_transform_settings_are_not_silently_reset(self):
        transform = AttributeNode('SfMTransform', method='', transformation='', scale=0.,
                                  applyScale=False, applyRotation=True, applyTranslation=True)
        graph = SimpleNamespace(nodes=[transform])
        reconstruction.configure_standard_transform(graph, {})
        self.assertEqual(transform.attribute('method').value, 'transformation')
        self.assertIs(transform.attribute('applyRotation').value, False)
        reconstruction.configure_standard_transform(graph, {
            transform.name: {'method': 'auto_from_cameras', 'applyRotation': True}})
        self.assertEqual(transform.attribute('method').value, 'auto_from_cameras')
        self.assertIs(transform.attribute('applyRotation').value, True)
        self.assertEqual(transform.attribute('scale').value, 1.)

    def test_standard_dense_only_masks_use_native_export_attributes(self):
        feature = AttributeNode('FeatureExtraction')
        dense = AttributeNode('ExportImages', masksFolders=[], maskExtension='exr')
        folder = self.root / 'masks'
        reconstruction.configure_masks(SimpleNamespace(nodes=[feature, dense]), 'standard',
                                       {'features': False}, folder, 'png')
        self.assertEqual(dense.attribute('masksFolders').value, [str(folder)])
        self.assertEqual(dense.attribute('maskExtension').value, 'png')
        self.assertEqual(feature.attributes, {})


class MaskInputTests(unittest.TestCase):
    """Real file matching/decoding/binding tests. Pillow is the local decoder
    boundary; these do not qualify the Linux pyalicevision reader or dense run.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mask-inputs-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.images = self.root / 'images'
        self.masks = self.root / 'masks'
        self.images.mkdir()
        self.masks.mkdir()
        self.views = []
        for index, name in enumerate(('first.png', 'second.png')):
            Image.new('RGB', (3, 2), 'white').save(self.images / name)
            self.views.append({'image': str(self.images / name), 'view_id': 700 + index,
                               'width': 3, 'height': 2})

    @staticmethod
    def image_size(path):
        with Image.open(path) as image:
            image.load()  # Decode pixels, not just an extension/header check.
            return image.size

    def mask(self, name, size=(3, 2), value=255):
        Image.new('L', size, value).save(self.masks / name)

    def validate(self):
        return reconstruction.validate_masks(self.masks, 'png', self.views, self.image_size)

    def saved_run(self, masked=True):
        for name in ('first.png', 'second.png'):
            self.mask(name)
        manifest = self.root / 'manifest.json'
        reconstruction.manifest(argparse.Namespace(images=self.images, output=manifest, source='test capture'))
        config = {'images': 'images', 'input_manifest': 'manifest.json', 'scale': {'mode': 'unknown'}}
        if masked:
            config['masks'] = {'folder': 'masks', 'extension': 'png', 'features': False}
        settings = self.root / 'settings.json'
        reconstruction.write(settings, config)
        run = self.root / 'run'
        run.mkdir()
        effective = {'settings': config, 'settings_file': str(settings),
                     'settings_sha256': reconstruction.sha(settings),
                     'input_manifest': str(manifest), 'input_manifest_sha256': reconstruction.sha(manifest)}
        if masked:
            effective['mask_inputs'] = self.validate()
        reconstruction.write(run / 'effective-settings.json', effective)
        return run, settings, manifest, effective

    def test_unrelated_folder_and_missing_frame_are_reported(self):
        self.mask('unrelated_object.png')
        with self.assertRaisesRegex(ValueError, 'first.png.*missing') as failure:
            self.validate()
        self.assertIn('second.png', str(failure.exception))
        self.mask('first.png')
        with self.assertRaisesRegex(ValueError, 'second.png.*missing'):
            self.validate()

    def test_full_stem_and_view_id_sets_are_accepted_with_id_priority(self):
        self.mask('first.png', size=(1, 1))  # Native ignores this fallback when ID exists.
        self.mask('700.png')
        self.mask('701.png')
        receipt = self.validate()
        self.assertEqual([Path(item['path']).name for item in receipt['files']], ['700.png', '701.png'])
        (self.masks / '700.png').unlink()
        self.mask('first.png')
        self.assertEqual(Path(self.validate()['files'][0]['path']).name, 'first.png')

    def test_wrong_dimensions_even_same_area_and_unreadable_pixels_are_rejected(self):
        self.mask('first.png', size=(2, 3))
        self.mask('second.png')
        with self.assertRaisesRegex(ValueError, 'first.png.*expected'):
            self.validate()
        self.mask('first.png')
        (self.masks / '700.png').write_bytes(b'not a PNG')
        with self.assertRaisesRegex(ValueError, 'first.png.*unreadable'):
            self.validate()  # A corrupt preferred ID mask must not fall back to a valid stem.
        (self.masks / '700.png').unlink()
        (self.masks / '700.png').mkdir()
        with self.assertRaisesRegex(ValueError, 'not a file'):
            self.validate()

    def test_verify_accepts_unchanged_inputs_without_native_runtime_or_writes(self):
        run, _, _, _ = self.saved_run()
        paths = [path for path in self.root.rglob('*') if path.is_file()]
        before = {str(path): path.read_bytes() for path in paths}
        output = io.StringIO()
        with mock.patch.object(reconstruction, 'init_runtime', side_effect=AssertionError('No native runtime needed')):
            with contextlib.redirect_stdout(output):
                reconstruction.verify(argparse.Namespace(run=run))
        self.assertEqual(json.loads(output.getvalue())['mask_count'], 2)
        self.assertEqual(before, {str(path): path.read_bytes() for path in paths})

    def test_public_verify_cli_stops_after_actual_mask_mutation(self):
        run, _, _, _ = self.saved_run()
        command = [sys.executable, str(Path(reconstruction.__file__)), 'verify', str(run)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'verified')
        self.mask('second.png', value=0)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Masks changed', result.stderr)
        self.assertIn('second.png', result.stderr)

    def test_changed_mask_bytes_and_new_preferred_name_require_new_run(self):
        run, _, _, _ = self.saved_run()
        self.mask('first.png', value=0)
        with self.assertRaisesRegex(ValueError, 'Masks changed.*first.png'):
            reconstruction.verify_run_inputs(run)
        self.mask('first.png')
        self.mask('700.png')  # New native priority must be detected even if decoded pixels are identical.
        with self.assertRaisesRegex(ValueError, 'Masks changed.*first.png'):
            reconstruction.verify_run_inputs(run)

    def test_changed_photo_manifest_and_settings_at_same_paths_are_rejected(self):
        run, settings, manifest, _ = self.saved_run()
        for path, expected in ((self.images / 'first.png', 'Capture input changed'),
                               (manifest, 'Input manifest changed'), (settings, 'Settings file changed')):
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            try:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, expected):
                    reconstruction.verify_run_inputs(run)
            finally:
                path.write_bytes(original)

    def test_old_unmasked_runs_remain_valid_but_unbound_masked_runs_are_rejected(self):
        run, _, _, effective = self.saved_run(masked=False)
        reconstruction.verify_run_inputs(run)
        config = effective['settings']
        config['masks'] = {'folder': 'masks', 'extension': 'png'}
        reconstruction.write(effective['settings_file'], config)
        effective['settings_sha256'] = reconstruction.sha(effective['settings_file'])
        reconstruction.write(run / 'effective-settings.json', effective)
        with self.assertRaisesRegex(ValueError, 'no verified mask binding'):
            reconstruction.verify_run_inputs(run)


if __name__ == '__main__':
    unittest.main()
