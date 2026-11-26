"""Actual CSV/config binding at the native-runtime boundary; no native compute."""
import argparse
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruction
from capture_measurements import FIELDS


class MeasurementInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='measurement-inputs-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sheet = self.root / 'measurements.csv'
        self.row = dict.fromkeys(FIELDS, '')
        self.row.update(measurement_id='base', purpose='scale',
                        from_point='cctag3:7:center', to_point='cctag3:23:center',
                        planned_mm='1500', status='planned')
        self.write_sheet()

    def write_sheet(self):
        with self.sheet.open('w', encoding='utf-8', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(self.row)

    def request(self, mode='measured_baseline'):
        return {'mode': mode, 'measurements': self.sheet.name}

    def confirm(self):
        self.row.update(status='confirmed_nominal', method='checked at placement',
                        confirmation_source='operator reply: both centers set 1500 mm apart')
        self.write_sheet()

    def test_planned_input_stops_before_native_runtime_and_unknown_is_explicit(self):
        images = self.root / 'images'
        images.mkdir()
        (images / 'one.jpg').write_bytes(b'input identity only')
        (images / 'two.jpg').write_bytes(b'second input identity only')
        manifest = self.root / 'manifest.json'
        reconstruction.manifest(argparse.Namespace(images=images, output=manifest, source='test'))
        config = self.root / 'config.json'
        config.write_text(json.dumps({'pipeline': 'legacy', 'images': 'images',
            'input_manifest': 'manifest.json', 'resources': {'threads': 1},
            'nodes': {}, 'scale': self.request()}), encoding='utf-8')
        args = argparse.Namespace(settings=config, run=self.root / 'run', meshroom=self.root / 'missing-runtime')
        with mock.patch.object(reconstruction, 'init_runtime', side_effect=AssertionError('native boundary')):
            with self.assertRaisesRegex(ValueError, 'confirmed'):
                reconstruction.prepare(args)
        self.assertFalse(args.run.exists())
        unknown = reconstruction.resolve_scale_request(self.request('unknown'), self.root)
        self.assertEqual(unknown['mode'], 'unknown')
        self.assertNotIn('distance', unknown)

    def test_confirmed_input_resolves_once_and_rejects_manual_duplicate(self):
        self.confirm()
        resolved = reconstruction.resolve_scale_request(self.request(), self.root)
        self.assertEqual(resolved['ids'], [7, 23])
        self.assertEqual(resolved['distance'], 1500)
        self.assertIsNone(resolved['measurement_uncertainty_mm'])
        self.assertEqual(resolved['measurements_sha256'], reconstruction.sha(self.sheet))
        with self.assertRaisesRegex(ValueError, 'not both'):
            reconstruction.resolve_scale_request({**self.request(), 'distance': 1490}, self.root)
        manual = {'mode': 'measured_baseline', 'ids': [7, 23], 'distance': 14.9,
                  'units': 'cm', 'measurement_source': 'historical manual input'}
        self.assertEqual(reconstruction.resolve_scale_request(manual, self.root), manual)
        self.assertEqual(reconstruction.resolve_scale_request({'mode': 'unknown'}, self.root), {'mode': 'unknown'})

    def test_actual_sheet_mutation_invalidates_saved_run_even_when_scale_is_unchanged(self):
        self.confirm()
        images = self.root / 'images'
        images.mkdir()
        (images / 'one.jpg').write_bytes(b'input identity only')
        (images / 'two.jpg').write_bytes(b'second input identity only')
        manifest = self.root / 'manifest.json'
        reconstruction.manifest(argparse.Namespace(images=images, output=manifest, source='test'))
        config = {'images': 'images', 'input_manifest': 'manifest.json', 'scale': self.request()}
        settings = self.root / 'config.json'
        reconstruction.write(settings, config)
        run = self.root / 'run'
        run.mkdir()
        effective = {'settings': config, 'settings_file': str(settings),
                     'settings_sha256': reconstruction.sha(settings),
                     'scale': reconstruction.resolve_scale_request(self.request(), self.root),
                     'input_manifest': str(manifest), 'input_manifest_sha256': reconstruction.sha(manifest)}
        reconstruction.write(run / 'effective-settings.json', effective)
        reconstruction.verify_run_inputs(run)
        self.row['notes'] = 'changed after prepare'
        self.write_sheet()
        with self.assertRaisesRegex(ValueError, 'measurement sheet changed'):
            reconstruction.verify_run_inputs(run)


if __name__ == '__main__':
    unittest.main()
