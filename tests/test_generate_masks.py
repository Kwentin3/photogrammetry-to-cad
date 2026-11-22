"""Real-file producer contracts. The inference double does NOT qualify ML models."""

import builtins
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_masks as masks
import mask_models


class InferenceBoundary:
    """Deliberate raster fixture for artifact handling, never a model simulation."""

    runtime = {'fixture': 'artifact-contract-only; not ML inference'}

    def __init__(self, models, device):
        pass

    def detect(self, image, prompt, box_threshold, text_threshold):
        return [{'box_xyxy': [1, 1, 5, 3], 'score': 0.8, 'text': prompt}]

    def segment(self, image, candidates):
        mask = Image.new('L', image.size, 0)
        mask.paste(255, (1, 1, 5, 3))
        return [(mask, 0.75) for _ in candidates]

    def memory(self):
        return {'cuda_peak_allocated_bytes': None, 'cuda_peak_reserved_bytes': None}


class GenerateMasksTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mask-producer-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.images = self.root / 'images'
        self.images.mkdir()
        self.files = []
        for name in ('first.png', 'second.png', 'third.png', 'fourth.png'):
            path = self.images / name
            Image.new('RGB', (8, 5), (80, 100, 120)).save(path)
            self.files.append({'name': name, 'bytes': path.stat().st_size, 'sha256': masks.sha(path)})
        masks.write(self.root / 'manifest.json', {'schema_version': 1, 'complete': True, 'files': self.files})
        self.models = self.root / 'models'
        self.models.mkdir()
        (self.models / 'checkpoint.pt').write_bytes(b'fixture checkpoint is NOT a model')
        dino = self.models / 'dino'
        dino.mkdir()
        (dino / 'model.safetensors').write_bytes(b'fixture detector is NOT a model')
        def record(path):
            return {'bytes': path.stat().st_size, 'sha256': masks.sha(path)}
        self.model_manifest = {
            'schema_version': 1,
            'sam2': {'revision': 'pinned-source-fixture', 'config': 'configs/sam2.1/sam2.1_hiera_s.yaml',
                     'build_cuda': False, 'checkpoint': {'path': 'checkpoint.pt', **record(self.models / 'checkpoint.pt')}},
            'grounding_dino': {'repo_id': 'fixture', 'revision': 'fixture', 'path': 'dino',
                              'files': [{'name': 'model.safetensors', **record(dino / 'model.safetensors')}]}}
        masks.write(self.root / 'models.json', self.model_manifest)
        self.config = {'schema_version': 1, 'images': 'images', 'input_manifest': 'manifest.json',
                       'models_manifest': 'models.json', 'model_directory': 'models',
                       'prompt': 'a test object.', 'selection': 'single', 'box_threshold': .3,
                       'text_threshold': .25, 'device': 'cpu', 'preview_count': 4}
        self.settings = self.root / 'settings.json'
        self.output = self.root / 'output'

    def save_settings(self):
        masks.write(self.settings, self.config)
        return self.settings

    def run_fixture(self, engine=InferenceBoundary):
        self.save_settings()
        with mock.patch.object(mask_models, 'ModelInference', engine):
            return masks.run(self.settings, self.output)

    def test_complete_pngs_are_binary_source_size_and_bind_real_sources(self):
        result = self.run_fixture()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['frames']), 4)
        self.assertEqual(len(result['previews']), 4)
        self.assertGreater(result['rss_peak_bytes'], 0)
        for original, frame in zip(self.files, result['frames']):
            self.assertEqual(frame['sha256'], original['sha256'])
            self.assertEqual(frame['mask']['keep_fraction'], .2)
            self.assertEqual(frame['mask']['unique_values'], [0, 255])
            with Image.open(frame['mask']['path']) as mask:
                self.assertEqual((mask.mode, mask.size), ('L', (8, 5)))
                self.assertEqual(mask.getpixel((1, 1)), 255)
                self.assertEqual(mask.getpixel((0, 0)), 0)
        self.assertEqual(masks.read(self.output / 'mask-diagnostics.json')['status'], 'complete')

    def test_overlay_contains_actual_source_and_marked_object_pixels(self):
        result = self.run_fixture()
        with Image.open(result['previews'][0]['path']) as overlay:
            self.assertEqual(overlay.getpixel((0, 44)), (80, 100, 120))
            self.assertNotEqual(overlay.getpixel((2, 46)), (80, 100, 120))

    def test_source_body_mutation_blocks_before_inference_and_preserves_error(self):
        (self.images / 'first.png').write_bytes(b'a changed image')
        self.save_settings()
        with mock.patch.object(mask_models, 'ModelInference', side_effect=AssertionError('must not infer')) as engine:
            result = masks.run(self.settings, self.output)
        engine.assert_not_called()
        self.assertEqual(result['status'], 'error')
        self.assertIn('Capture input changed', result['error'])
        self.assertEqual(masks.read(self.output / 'mask-diagnostics.json')['status'], 'error')

    def test_model_body_mutation_blocks_before_inference(self):
        (self.models / 'checkpoint.pt').write_bytes(b'changed actual checkpoint')
        self.save_settings()
        with mock.patch.object(mask_models, 'ModelInference', side_effect=AssertionError('must not infer')) as engine:
            result = masks.run(self.settings, self.output)
        engine.assert_not_called()
        self.assertIn('Model file changed', result['error'])

    def test_unlisted_model_file_rejected(self):
        (self.models / 'dino' / 'unexpected.bin').write_bytes(b'unknown')
        result = self.run_fixture()
        self.assertEqual(result['status'], 'error')
        self.assertIn('complete file inventory', result['error'])

    def test_duplicate_stems_rejected(self):
        path = self.images / 'first.jpg'
        Image.new('RGB', (8, 5)).save(path)
        files = self.files + [{'name': path.name, 'bytes': path.stat().st_size, 'sha256': masks.sha(path)}]
        masks.write(self.root / 'manifest.json', {'schema_version': 1, 'complete': True, 'files': files})
        result = self.run_fixture()
        self.assertIn('Duplicate image stem', result['error'])

    def test_zero_and_multiple_candidates_are_explicit_and_preserved(self):
        for count in (0, 2):
            with self.subTest(candidates=count):
                self.output = self.root / f'output-{count}'
                class BadDetection(InferenceBoundary):
                    def detect(self, *args):
                        return super().detect(*args) * count
                result = self.run_fixture(BadDetection)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['failed_frames'], 4)
                self.assertEqual(len(result['previews']), 4)
                for frame in result['frames']:
                    self.assertEqual(len(frame['candidates']), count)
                    self.assertNotIn('mask', frame)
                    self.assertIn('zero detector' if count == 0 else 'Ambiguous', frame['error'])
                self.assertFalse(list((self.output / 'masks').glob('*.png')))

    def test_union_keeps_all_instances(self):
        class TwoInstances(InferenceBoundary):
            def detect(self, *args):
                return super().detect(*args) * 2
            def segment(self, image, candidates):
                a, b = Image.new('L', image.size), Image.new('L', image.size)
                a.putpixel((1, 1), 255)
                b.putpixel((6, 3), 255)
                return [(a, .7), (b, .8)]
        self.config['selection'] = 'union'
        result = self.run_fixture(TwoInstances)
        self.assertEqual(result['status'], 'complete')
        with Image.open(result['frames'][0]['mask']['path']) as image:
            self.assertEqual(image.getpixel((1, 1)), 255)
            self.assertEqual(image.getpixel((6, 3)), 255)
            self.assertEqual(sum(image.histogram()[1:]), 2)

    def test_empty_and_full_masks_saved_but_not_declared_success(self):
        for value in (0, 255):
            with self.subTest(value=value):
                self.output = self.root / f'output-{value}'
                class Degenerate(InferenceBoundary):
                    def segment(self, image, candidates):
                        return [(Image.new('L', image.size, value), .9)]
                result = self.run_fixture(Degenerate)
                self.assertEqual(result['status'], 'error')
                self.assertTrue(result['frames'][0]['mask']['zero' if value == 0 else 'full'])
                self.assertTrue(Path(result['frames'][0]['mask']['path']).is_file())

    def test_transposed_model_mask_is_rejected_without_resize(self):
        class WrongSize(InferenceBoundary):
            def segment(self, image, candidates):
                return [(Image.new('L', (image.height, image.width), 255), .9)]
        result = self.run_fixture(WrongSize)
        self.assertEqual(result['status'], 'error')
        self.assertIn('exact source width/height', result['frames'][0]['error'])
        self.assertFalse(list((self.output / 'masks').glob('*.png')))

    def test_nonbinary_model_mask_is_rejected(self):
        class Nonbinary(InferenceBoundary):
            def segment(self, image, candidates):
                return [(Image.new('L', image.size, 128), .9)]
        result = self.run_fixture(Nonbinary)
        self.assertEqual(result['status'], 'error')
        self.assertIn('only 0 and 255', result['frames'][0]['error'])

    def test_textless_candidate_is_not_target_success(self):
        class Textless(InferenceBoundary):
            def detect(self, *args):
                return [{'box_xyxy': [1, 1, 5, 3], 'score': .9, 'text': ''}]
        result = self.run_fixture(Textless)
        self.assertEqual(result['status'], 'error')
        self.assertIn('no text-supported', result['frames'][0]['error'])

    def test_partial_frame_failure_preserves_successful_outputs_and_no_complete_contract(self):
        class FailsSecond(InferenceBoundary):
            calls = 0
            def detect(self, *args):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError('deliberate inference-boundary failure')
                return super().detect(*args)
        result = self.run_fixture(FailsSecond)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['failed_frames'], 1)
        self.assertEqual(len(list((self.output / 'masks').glob('*.png'))), 3)
        self.assertNotIn('mask_inputs', result)

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / 'do-not-overwrite.txt'
        sentinel.write_text('owner data')
        self.save_settings()
        with self.assertRaises(FileExistsError):
            masks.run(self.settings, self.output)
        self.assertEqual(sentinel.read_text(), 'owner data')
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_raw_exif_orientation_and_dimensions_are_preserved(self):
        path = self.images / 'rotated.jpg'
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (8, 5)).save(path, exif=exif)
        files = self.files + [{'name': path.name, 'bytes': path.stat().st_size, 'sha256': masks.sha(path)}]
        masks.write(self.root / 'manifest.json', {'schema_version': 1, 'complete': True, 'files': files})
        result = self.run_fixture()
        frame = result['frames'][-1]
        self.assertEqual((frame['width'], frame['height'], frame['exif_orientation']), (8, 5, 6))
        with Image.open(frame['mask']['path']) as image:
            self.assertEqual(image.size, (8, 5))

    def test_source_mutation_during_inference_cannot_be_covered_by_receipt(self):
        path = self.images / 'first.png'
        class MutatesSource(InferenceBoundary):
            def detect(self, *args):
                Image.new('RGB', (8, 5), 'red').save(path)
                return super().detect(*args)
        result = self.run_fixture(MutatesSource)
        self.assertEqual(result['status'], 'error')
        self.assertIn('changed', result['frames'][0]['error'])
        self.assertNotIn('mask_inputs', result)

    def test_validate_and_help_do_not_import_ml(self):
        self.save_settings()
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name.split('.')[0] in {'torch', 'torchvision', 'transformers', 'sam2'}:
                raise AssertionError(f'Unexpected ML import: {name}')
            return original_import(name, *args, **kwargs)
        for arguments in (['--help'], ['--settings', str(self.settings), '--validate-only']):
            with self.subTest(arguments=arguments), mock.patch('builtins.__import__', side_effect=guarded), \
                    mock.patch.object(sys, 'argv', ['generate_masks.py', *arguments]), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as outcome:
                    runpy.run_path(str(Path(masks.__file__)), run_name='__main__')
                self.assertEqual(outcome.exception.code, 0)

    def test_settings_reject_typos_and_implicit_instance_selection(self):
        for field, value in (('selection', 'first'), ('box_threshold', 0),
                             ('device', 'auto'), ('preview_count', 3), ('unknown', 'typo')):
            with self.subTest(field=field):
                config = dict(self.config)
                config[field] = value
                masks.write(self.settings, config)
                with self.assertRaises(ValueError):
                    masks.load_settings(self.settings)


if __name__ == '__main__':
    unittest.main()
