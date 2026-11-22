"""Generate optional text-selected PNG masks with local GroundingDINO + SAM2.

The capture manifest and Meshroom mask preflight retain their existing owners.
This producer never starts reconstruction. Review actual-source previews before
passing a complete run's masks/ directory to reconstruction settings.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import platform
from pathlib import Path
import sys
import time

from reconstruction import outside, read, sha, verify_images, write


def verify_models(manifest_path, directory):
    """Verify all local model bodies against the separately pinned model recipe."""
    manifest_path = Path(manifest_path).resolve(strict=True)
    directory = outside(directory).resolve(strict=True)
    manifest = read(manifest_path)
    if manifest.get('schema_version') != 1:
        raise ValueError('Model manifest schema_version must be 1')
    sam, dino = manifest['sam2'], manifest['grounding_dino']
    if sam.get('build_cuda') is not False:
        raise ValueError('This recipe requires SAM2_BUILD_CUDA=0')

    def checked(relative, record):
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Model asset paths must be relative inside model_directory')
        path = directory / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory):
            raise ValueError(f'Model must be a regular local file inside model_directory: {path}')
        if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
            raise ValueError(f'Model file changed or is incomplete: {path}')
        return path.resolve()

    checkpoint = checked(sam['checkpoint']['path'], sam['checkpoint'])
    dino_directory = directory / dino['path']
    names = [item['name'] for item in dino['files']]
    if not names or len(names) != len(set(names)):
        raise ValueError('DINO model manifest files must be nonempty and unique')
    for item in dino['files']:
        checked(Path(dino['path']) / item['name'], item)
    actual = {str(path.relative_to(dino_directory)).replace('\\', '/')
              for path in dino_directory.rglob('*') if path.is_file()}
    if actual != set(names) or any(path.is_symlink() for path in dino_directory.rglob('*')):
        raise ValueError('DINO directory differs from the pinned complete file inventory')
    return {'manifest': str(manifest_path), 'manifest_sha256': sha(manifest_path),
            'pins': manifest, 'sam2_checkpoint': checkpoint, 'sam2_config': sam['config'],
            'grounding_dino_directory': dino_directory.resolve()}


def load_settings(path):
    path = Path(path).resolve(strict=True)
    config = read(path)
    allowed = {'schema_version', 'images', 'input_manifest', 'models_manifest', 'model_directory',
               'prompt', 'selection', 'box_threshold', 'text_threshold', 'device', 'preview_count'}
    if set(config) - allowed:
        raise ValueError('Unknown settings: ' + ', '.join(sorted(set(config) - allowed)))
    if config.get('schema_version') != 1:
        raise ValueError('Settings schema_version must be 1')
    if not isinstance(config.get('prompt'), str) or not config['prompt'].strip():
        raise ValueError('A nonempty object prompt is required')
    if config.get('selection', 'single') not in ('single', 'union'):
        raise ValueError('selection must be single (exactly one instance) or union (all matches)')
    for field in ('box_threshold', 'text_threshold'):
        value = config.get(field, 0.25)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value < 1:
            raise ValueError(f'{field} must be strictly between 0 and 1')
        config[field] = value
    device = config.get('device', 'cuda')
    if device != 'cpu' and device != 'cuda' and not (
            isinstance(device, str) and device.startswith('cuda:') and device[5:].isdigit()):
        raise ValueError('device must be cpu, cuda, or cuda:N')
    previews = config.get('preview_count', 6)
    if isinstance(previews, bool) or not isinstance(previews, int) or not 4 <= previews <= 8:
        raise ValueError('preview_count must be 4..8 (all frames for smaller captures)')
    config.update(device=device, preview_count=previews, selection=config.get('selection', 'single'))
    for field in ('images', 'input_manifest', 'models_manifest', 'model_directory'):
        if not isinstance(config.get(field), str) or not config[field]:
            raise ValueError(f'{field} must be an explicit path')
        config[field] = str((path.parent / config[field]).resolve())
    return path, config


def input_frames(config):
    """Reuse capture admission, then add the PNG producer's raw-raster contract."""
    from PIL import Image

    directory = outside(config['images']).resolve(strict=True)
    manifest = outside(config['input_manifest']).resolve(strict=True)
    files = verify_images(directory, manifest)
    stems, frames = set(), []
    for item in files:
        path = directory / item['name']
        stem = path.stem
        if stem.casefold() in stems:
            raise ValueError(f'Duplicate image stem cannot identify native masks: {stem}')
        stems.add(stem.casefold())
        with Image.open(path) as image:
            image.load()
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError(f'Only single-raster images are supported: {path}')
            frames.append({**item, 'image': str(path), 'mask_name': stem + '.png',
                           'width': image.width, 'height': image.height,
                           'exif_orientation': image.getexif().get(274, 1),
                           'coordinates': 'raw decoded raster; no EXIF transpose'})
    # Bind the manifest body which actually passed the existing owner's checks.
    return frames, {'path': str(manifest), 'sha256': sha(manifest)}


def select_candidates(candidates, selection, width, height):
    """Never choose the first box or replace a failed detection with a white mask."""
    if not candidates:
        raise ValueError('Target not found: zero detector candidates; revise prompt or capture explicitly')
    if selection == 'single' and len(candidates) != 1:
        raise ValueError(f'Ambiguous target: single requires exactly one candidate, got {len(candidates)}; '
                         'review recorded boxes, change prompt or explicitly choose union')
    for candidate in candidates:
        if not isinstance(candidate.get('text'), str) or not candidate['text'].strip():
            raise ValueError('Detector candidate has no text-supported target label')
        box = candidate['box_xyxy']
        if (len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
                or not box[0] < box[2] or not box[1] < box[3]):
            raise ValueError('Detector returned an invalid source-coordinate box')
        if box[2] <= 0 or box[3] <= 0 or box[0] >= width or box[1] >= height:
            raise ValueError('Detector candidate is outside the source raster')
    return candidates


def save_mask(path, segments, size):
    from PIL import Image, ImageChops

    mask = Image.new('L', size, 0)
    scores = []
    if not segments:
        raise ValueError('SAM2 returned no masks')
    for segment, score in segments:
        if segment.mode != 'L' or segment.size != size:
            raise ValueError('SAM2 mask must be grayscale in exact source width/height')
        if any(value not in (0, 255) for _, value in segment.getcolors(256) or []):
            raise ValueError('SAM2 mask must contain only 0 and 255')
        mask = ImageChops.lighter(mask, segment)
        scores.append(score)
    with path.open('xb') as stream:
        mask.save(stream, format='PNG')
    with Image.open(path) as decoded:
        decoded.load()
        if decoded.mode != 'L' or decoded.size != size or decoded.tobytes() != mask.tobytes():
            raise ValueError('Lossless PNG read-back differs')
        histogram = decoded.histogram()
        keep = histogram[255]
        border = (decoded.crop((0, 0, size[0], 1)).getbbox() is not None
                  or decoded.crop((0, size[1] - 1, size[0], size[1])).getbbox() is not None
                  or decoded.crop((0, 0, 1, size[1])).getbbox() is not None
                  or decoded.crop((size[0] - 1, 0, size[0], size[1])).getbbox() is not None)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
            'keep_fraction': keep / (size[0] * size[1]), 'zero': keep == 0,
            'full': keep == size[0] * size[1], 'unique_values': [i for i, n in enumerate(histogram) if n],
            'touches_border': border, 'sam2_predicted_iou': scores}


def previews(output, frames, count):
    """Actual source overlays, including extremes and errors; never generated imagery."""
    from PIL import Image, ImageDraw

    if not frames:
        return []
    successful = [frame for frame in frames if frame.get('mask')]
    selected = []
    if successful:
        selected += [min(successful, key=lambda f: f['mask']['keep_fraction']),
                     max(successful, key=lambda f: f['mask']['keep_fraction'])]
    selected += [frame for frame in frames if frame.get('error') or frame.get('mask', {}).get('touches_border')]
    selected += [frames[0], frames[len(frames) // 2], frames[-1]]
    selected += frames
    chosen, seen = [], set()
    for frame in selected:
        if frame['name'] not in seen:
            seen.add(frame['name'])
            chosen.append(frame)
        if len(chosen) >= count:
            break
    directory = output / 'previews'
    directory.mkdir(exist_ok=True)
    paths = []
    for index, frame in enumerate(chosen):
        with Image.open(frame['image']) as raw:
            source = raw.convert('RGB')
        if frame.get('mask'):
            with Image.open(frame['mask']['path']) as mask:
                tint = Image.new('RGB', source.size, (0, 255, 80))
                source = Image.composite(Image.blend(source, tint, 0.4), source, mask)
        draw = ImageDraw.Draw(source)
        for candidate in frame.get('candidates', []):
            draw.rectangle(candidate['box_xyxy'], outline=(255, 80, 0), width=3)
        source.thumbnail((960, 720))  # Preview only; model outputs are never resized here.
        canvas = Image.new('RGB', (source.width, source.height + 44), 'white')
        canvas.paste(source, (0, 44))
        text = f"{frame['name']} | {frame.get('error') or frame.get('mask', {}).get('keep_fraction', 'no mask')}"
        # Pillow's default font cannot display every Unicode source basename.
        ImageDraw.Draw(canvas).text((6, 5), text.encode('ascii', 'backslashreplace').decode(), fill='black')
        path = directory / f'{index + 1:02}-{Path(frame["name"]).stem}.png'
        canvas.save(path)
        paths.append({'source': frame['name'], 'path': str(path), 'sha256': sha(path)})
    return paths


def peak_rss():
    if sys.platform != 'win32':
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == 'darwin' else value * 1024)
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (key, ctypes.c_size_t) for key in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                'PagefileUsage', 'PeakPagefileUsage')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    if not get_memory(get_process(), ctypes.byref(counters), counters.cb):
        raise OSError('GetProcessMemoryInfo failed')
    return counters.PeakWorkingSetSize


def run(settings, output):
    settings_path, config = load_settings(settings)
    output = outside(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    diagnostic = {'schema_version': 1, 'status': 'running', 'settings': config,
                  'started_utc': datetime.now(timezone.utc).isoformat(),
                  'settings_file': str(settings_path), 'settings_sha256': sha(settings_path),
                  'generator_sha256': sha(__file__), 'adapter_sha256': sha(Path(__file__).with_name('mask_models.py')),
                  'runtime': {'python': sys.version, 'platform': platform.platform()},
                  'frames': [], 'manual_edits': [], 'excluded_frames': [],
                  'semantic_review': 'Inspect actual-source overlays and needed edges before MVS; '
                                     'candidate confidence/area cannot prove correct object identity.'}
    write(output / 'mask-diagnostics.json', diagnostic)
    engine = None
    try:
        frames, binding = input_frames(config)
        diagnostic['input_manifest'] = binding
        models = verify_models(config['models_manifest'], config['model_directory'])
        diagnostic['models'] = {key: value for key, value in models.items()
                                if key not in ('sam2_checkpoint', 'grounding_dino_directory')}
        diagnostic['timing'] = {'input_and_model_validation_seconds': time.monotonic() - started}
        load_started = time.monotonic()
        from mask_models import ModelInference
        engine = ModelInference(models, config['device'])
        diagnostic['runtime'].update(engine.runtime)
        diagnostic['timing']['model_load_seconds'] = time.monotonic() - load_started
        mask_directory = output / 'masks'
        mask_directory.mkdir()
        from PIL import Image
        for frame in frames:
            entry = {**frame, 'status': 'running', 'candidates': []}
            diagnostic['frames'].append(entry)
            frame_started = time.monotonic()
            try:
                if sha(frame['image']) != frame['sha256']:
                    raise ValueError('Source changed after capture verification')
                with Image.open(frame['image']) as raw:
                    image = raw.convert('RGB')
                entry['candidates'] = engine.detect(image, config['prompt'],
                                                     config['box_threshold'], config['text_threshold'])
                entry['candidate_count'] = len(entry['candidates'])
                entry['ambiguous'] = config['selection'] == 'single' and len(entry['candidates']) > 1
                chosen = select_candidates(entry['candidates'], config['selection'], image.width, image.height)
                segments = engine.segment(image, chosen)
                if len(segments) != len(chosen):
                    raise ValueError('SAM2 mask count differs from selected detector candidates')
                entry['mask'] = save_mask(mask_directory / frame['mask_name'], segments, image.size)
                if entry['mask']['zero'] or entry['mask']['full']:
                    raise ValueError('Empty/full mask requires explicit inspection; no valid target mask declared')
                if sha(frame['image']) != frame['sha256']:
                    raise ValueError('Source changed during inference')
                entry['status'] = 'complete'
            except Exception as error:
                entry.update(status='error', error=f'{type(error).__name__}: {error}')
            finally:
                entry['seconds'] = time.monotonic() - frame_started
                write(output / 'mask-diagnostics.json', diagnostic)
        # Recheck the real source artifacts and manifest, not only our receipt.
        input_frames(config)
        if sha(config['input_manifest']) != binding['sha256']:
            raise ValueError('Capture manifest changed during inference')
        diagnostic['previews'] = previews(output, diagnostic['frames'], config['preview_count'])
        failures = sum(frame['status'] != 'complete' for frame in diagnostic['frames'])
        diagnostic['failed_frames'] = failures
        if failures:
            raise ValueError(f'{failures}/{len(frames)} frames failed; partial masks and diagnostics preserved')
        # Producer names by source stem; actual native IDs do not exist until
        # CameraInit. Never invent IDs to satisfy the downstream native checker.
        diagnostic['mask_inputs'] = {
            'folder': str(mask_directory), 'extension': 'png', 'coverage': 'all_manifest_frames',
            'lookup': 'unique source stem', 'native_view_ids': 'not_assigned',
            'reader': 'Pillow lossless read-back; native pyalicevision check required at prepare',
            'files': [{'image': frame['image'], 'source_sha256': frame['sha256'],
                       'width': frame['width'], 'height': frame['height'], **frame['mask']}
                      for frame in diagnostic['frames']]}
        diagnostic['status'] = 'complete'
    except BaseException as error:
        diagnostic.update(status='error', error=f'{type(error).__name__}: {error}')
        if diagnostic['frames'] and 'previews' not in diagnostic:
            try:
                diagnostic['previews'] = previews(output, diagnostic['frames'], config['preview_count'])
            except Exception as preview_error:
                diagnostic['preview_error'] = str(preview_error)
    finally:
        diagnostic['finished_utc'] = datetime.now(timezone.utc).isoformat()
        diagnostic.setdefault('timing', {})['total_seconds'] = time.monotonic() - started
        diagnostic['timing']['generation_seconds'] = sum(frame.get('seconds', 0) for frame in diagnostic['frames'])
        try:
            diagnostic['rss_peak_bytes'] = peak_rss()
        except Exception as memory_error:
            diagnostic['rss_peak_bytes'] = None
            diagnostic['rss_error'] = str(memory_error)
        if engine is not None:
            try:
                diagnostic.update(engine.memory())
            except Exception as memory_error:
                diagnostic['memory_error'] = str(memory_error)
        write(output / 'mask-diagnostics.json', diagnostic)
    return diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='Fresh output directory outside checkout; never overwritten')
    parser.add_argument('--validate-only', action='store_true', help='Verify local inputs/models without ML imports')
    args = parser.parse_args()
    try:
        if args.validate_only:
            _, config = load_settings(args.settings)
            frames, binding = input_frames(config)
            models = verify_models(config['models_manifest'], config['model_directory'])
            print(json.dumps({'status': 'inputs_verified', 'frames': len(frames), 'input_manifest': binding,
                              'models_manifest_sha256': models['manifest_sha256']}))
            return 0
        if args.output is None:
            parser.error('--output is required unless --validate-only is selected')
        result = run(args.settings, args.output)
        print(json.dumps({'status': result['status'], 'diagnostics': str(args.output / 'mask-diagnostics.json'),
                          'error': result.get('error')}))
        return 0 if result['status'] == 'complete' else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
