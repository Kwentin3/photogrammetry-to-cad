"""Operator distance sheet: planned values become known only by confirmation.

This owns CSV meaning, not marker detection, geometry, or native scaling.
The agent records an ordinary operator reply in the working copy of the form.
"""
import csv
import hashlib
import io
import math
from pathlib import Path
import re

FIELDS = (
    'measurement_id', 'purpose', 'from_point', 'to_point', 'planned_mm',
    'measured_mm', 'uncertainty_mm', 'status', 'method',
    'confirmation_source', 'notes',
)
STATUSES = {'planned', 'unknown', 'confirmed_nominal', 'measured'}
PURPOSES = {'scale', 'check', 'print_check', 'manual_parameter'}
_CENTER = re.compile(r'cctag3:(\d+):center')


def optional_number(text, field, row_id):
    if not text:
        return None
    value = float(text)
    if not math.isfinite(value) or value < 0 or (field != 'uncertainty_mm' and value == 0):
        raise ValueError(f'{row_id}: {field} must be finite and positive (uncertainty may be zero)')
    return value


def load_measurements(path):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    header = reader.fieldnames or []
    if len(header) != len(set(header)) or set(header) != set(FIELDS):
        raise ValueError('Measurement CSV needs the issued fields: ' + ', '.join(FIELDS))
    rows, seen = [], set()
    for line, raw in enumerate(reader, 2):
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f'Measurement CSV row {line} has the wrong number of cells')
        row = {key: raw[key].strip() for key in FIELDS}
        row_id = row['measurement_id']
        if not row_id or row_id in seen:
            raise ValueError(f'Measurement IDs must be nonempty and unique: {row_id!r}')
        seen.add(row_id)
        if row['purpose'] not in PURPOSES:
            raise ValueError(f'{row_id}: unknown purpose {row["purpose"]!r}')
        if row['status'] not in STATUSES:
            raise ValueError(f'{row_id}: explicit planned/unknown/confirmed_nominal/measured status required')
        if not row['from_point'] or not row['to_point'] or row['from_point'] == row['to_point']:
            raise ValueError(f'{row_id}: two distinct described endpoints required')
        for key in ('planned_mm', 'measured_mm', 'uncertainty_mm'):
            row[key] = optional_number(row[key], key, row_id)
        endpoints = [_CENTER.fullmatch(row[key]) for key in ('from_point', 'to_point')]
        row['marker_ids'] = [int(m.group(1)) for m in endpoints] if all(endpoints) else None
        if row['marker_ids'] and len(set(row['marker_ids'])) != 2:
            raise ValueError(f'{row_id}: marker centers must have distinct IDs')
        row['confirmed_mm'] = None
        if row['status'] in {'confirmed_nominal', 'measured'}:
            if not row['method'] or not row['confirmation_source']:
                raise ValueError(f'{row_id}: confirmed distance needs method and operator confirmation source')
            if row['status'] == 'confirmed_nominal':
                if row['planned_mm'] is None:
                    raise ValueError(f'{row_id}: confirmed_nominal needs a planned distance')
                if row['measured_mm'] is not None and row['measured_mm'] != row['planned_mm']:
                    raise ValueError(f'{row_id}: actual length differs from plan; record status=measured')
                row['confirmed_mm'] = row['planned_mm']
            else:
                if row['measured_mm'] is None:
                    raise ValueError(f'{row_id}: measured status needs the actual measured_mm')
                row['confirmed_mm'] = row['measured_mm']
        rows.append(row)
    if not rows:
        raise ValueError('Measurement sheet is empty')
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'rows': rows}


def scale_row(sheet):
    selected = [row for row in sheet['rows'] if row['purpose'] == 'scale']
    if len(selected) != 1:
        raise ValueError('Exactly one scale row is required; check pairs never fit scale')
    row = selected[0]
    if row['marker_ids'] is None:
        raise ValueError('Scale endpoints must be two CCTag3 centers')
    if any(other['purpose'] == 'check' and other['marker_ids'] is not None
           and set(other['marker_ids']) == set(row['marker_ids']) for other in sheet['rows']):
        raise ValueError('An independent check must differ from the scale pair')
    return row


def confirmed_scale(sheet):
    row = scale_row(sheet)
    if row['confirmed_mm'] is None:
        raise ValueError(f'{row["measurement_id"]}: scale distance is not confirmed by the operator')
    return {
        'mode': 'measured_baseline', 'ids': row['marker_ids'],
        'distance': row['confirmed_mm'], 'units': 'mm',
        'measurement_source': row['confirmation_source'],
        'measurement_id': row['measurement_id'], 'measurement_status': row['status'],
        'measurement_method': row['method'], 'measurement_uncertainty_mm': row['uncertainty_mm'],
        'measurements_file': sheet['path'], 'measurements_sha256': sheet['sha256'],
    }
