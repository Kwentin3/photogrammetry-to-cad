"""Confirmation behavior through the real operator-sheet boundary."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from capture_measurements import FIELDS, confirmed_scale, load_measurements, scale_row


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'operator.csv'

    def write(self, *rows):
        with self.path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for updates in rows:
                row = dict.fromkeys(FIELDS, '')
                row.update(measurement_id='base', purpose='scale', from_point='cctag3:7:center',
                           to_point='cctag3:23:center', planned_mm='1500', status='planned')
                row.update(updates)
                writer.writerow(row)
        return load_measurements(self.path)

    def test_plan_and_print_confirmation_cannot_scale(self):
        sheet = self.write({}, dict(measurement_id='print', purpose='print_check',
                                  from_point='page1_x0', to_point='page1_x1', planned_mm='100',
                                  measured_mm='100', status='measured', method='линейка',
                                  confirmation_source='оператор: проверил только печать'))
        self.assertIsNone(scale_row(sheet)['confirmed_mm'])
        with self.assertRaisesRegex(ValueError, 'not confirmed'):
            confirmed_scale(sheet)

    def test_confirmed_installation_keeps_actual_column_empty(self):
        sheet = self.write(dict(status='confirmed_nominal', method='выставлено и проверено при установке',
                                confirmation_source='оператор: первую пару выставил по заданию'))
        request = confirmed_scale(sheet)
        self.assertEqual((request['ids'], request['distance'], request['units']), ([7, 23], 1500, 'mm'))
        self.assertIsNone(sheet['rows'][0]['measured_mm'])
        self.assertIsNone(request['measurement_uncertainty_mm'])

    def test_actual_deviation_and_control_never_replace_scale(self):
        sheet = self.write(dict(status='measured', measured_mm='1487', method='рулетка',
                                confirmation_source='оператор: получилось 1487'),
                           dict(measurement_id='other', purpose='check', from_point='cctag3:5:center',
                                to_point='cctag3:11:center', planned_mm='1000', status='confirmed_nominal',
                                method='установка', confirmation_source='вторая пара по заданию'))
        self.assertEqual(confirmed_scale(sheet)['distance'], 1487)
        self.assertEqual(sheet['rows'][1]['confirmed_mm'], 1000)
        with self.assertRaisesRegex(ValueError, 'status=measured'):
            self.write(dict(status='confirmed_nominal', measured_mm='1487', method='рулетка',
                            confirmation_source='отклонение'))

    def test_explicit_confirmation_and_valid_uncertainty(self):
        for changes in ({'method': ''}, {'confirmation_source': ''}, {'uncertainty_mm': '-1'},
                        {'measured_mm': 'nan'}, {'measured_mm': '0'}):
            row = dict(status='measured', measured_mm='1500', method='рулетка', confirmation_source='оператор')
            row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.write(row)

    def test_scale_role_and_exact_center_ids(self):
        sheet = self.write(dict(from_point='cctag3:1:center', to_point='cctag3:10:center',
                                status='confirmed_nominal', method='установка', confirmation_source='чат'))
        self.assertEqual(confirmed_scale(sheet)['ids'], [1, 10])
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            confirmed_scale(self.write({}, dict(measurement_id='second')))

    def test_scale_pair_cannot_be_its_own_independent_control(self):
        sheet = self.write({}, dict(measurement_id='control', purpose='check',
                                   from_point='cctag3:23:center', to_point='cctag3:7:center'))
        with self.assertRaisesRegex(ValueError, 'independent check'):
            scale_row(sheet)


if __name__ == '__main__':
    unittest.main()
