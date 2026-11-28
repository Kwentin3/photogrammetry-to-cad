"""Prepare native Meshroom projects and export their results; no compute scheduler.

Run with the pinned bundle Python/environment. Inputs/cache stay outside Git.
Native meshroom_compute and remote_job.sh own computation and resume.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from fetch_dataset import check_input_entries
from check_marker_scale import markers_from_scene, verify_applied_baseline
from capture_measurements import confirmed_scale, load_measurements
from reconstruction_bundle import file_record, native_source, obj_bundle

REPO = Path(__file__).resolve().parents[1]
IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1.]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, allow_nan=False) + '\n'
    expected = json.loads(text)  # Native node dictionaries contain tuple values and integer UID keys.
    path.write_text(text, encoding='utf-8')
    if read(path) != expected:
        raise ValueError(f'JSON read-back mismatch: {path}')


def outside(path):
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('Keep data, projects, cache and diagnostics outside the checkout')
    return path


def verify_images(directory, manifest):
    records = read(manifest)
    if records.get('schema_version') != 1 or records.get('complete') is not True:
        raise ValueError('A complete capture manifest v1 is required')
    files = records['files']
    check_input_entries(directory, [item['name'] for item in files])
    for item in files:
        path = directory / item['name']
        if path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError(f'Capture input changed: {path}')
    if len(files) < 2:
        raise ValueError('Reconstruction requires at least two images')
    return files


def manifest(args):
    directory = outside(args.images).resolve(strict=True)
    output = outside(args.output)
    if output.exists():
        raise FileExistsError('Preserve the existing manifest; choose another output')
    extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr'}
    files = sorted(path for path in directory.iterdir() if path.suffix.lower() in extensions)
    check_input_entries(directory, [path.name for path in files])
    write(output, {'schema_version': 1, 'complete': True,
                   'source': {'description': args.source},
                   'files': [{'name': path.name, 'bytes': path.stat().st_size,
                              'sha256': sha(path)} for path in files]})


def init_runtime(root):
    root = root.resolve(strict=True)
    expected = read(REPO / 'configs/runtime-2026.json')
    # Bootstrap owns full archive verification; retain its install binding.
    binding = root / '.archive.sha256'
    archive_sha = expected['archive_sha256']
    if not binding.is_file() or binding.read_text().strip() != archive_sha:
        raise ValueError('Bootstrap the pinned archive before preparing a graph')
    os.environ['MESHROOM_INSTALL_DIR'] = str(root)
    import meshroom
    meshroom.setupEnvironment()
    import meshroom.core
    from meshroom.core import graph
    meshroom.core.initPipelines()
    meshroom.core.initPlugins()
    meshroom.core.initNodes()
    if not Path(meshroom.__file__).resolve().is_relative_to(root):
        raise ValueError('Meshroom must come from the pinned bundle')
    return graph, expected


def _setting_attribute(node, name):
    try:
        attr = node.attribute(name)
    except (KeyError, AttributeError) as error:
        raise ValueError(f'Unsupported setting: {node.name}.{name}') from error
    if attr is None:
        raise ValueError(f'Unsupported setting: {node.name}.{name}')
    return attr


def _setting_has_links(attr):
    return (attr.isLink or getattr(attr, 'hasAnyInputLinks', False) or getattr(attr, 'hasAnyOutputLinks', False)
            or any(_setting_has_links(child) for child in getattr(attr, 'flatStaticChildren', ())))


def _set_setting(attr, value, label, linked):
    if attr.isLink:
        linked.append((attr, value, label))
    elif isinstance(value, dict) and callable(getattr(attr, 'childAttribute', None)):
        for key, child_value in value.items():
            child = attr.childAttribute(key)
            if child is None:
                raise ValueError(f'Unsupported setting: {label}.{key}')
            _set_setting(child, child_value, f'{label}.{key}', linked)
    elif isinstance(value, list) and callable(getattr(attr, 'at', None)) and (
            any(_setting_has_links(child) for child in attr)
            or (len(attr) == len(value) and all(isinstance(v, dict) and
                callable(getattr(attr.at(i), 'childAttribute', None)) for i, v in enumerate(value)))):
        # Native ListAttribute.value replaces children and removes their edges.
        # Keep linked children and generated fields in partial Group updates.
        # Resizing a linked list requires an explicit native graph edit.
        if len(attr) != len(value):
            raise ValueError(f'Cannot resize linked list setting without changing native edges: {label}')
        for index, child_value in enumerate(value):
            _set_setting(attr.at(index), child_value, f'{label}[{index}]', linked)
    else:
        try:
            attr.value = value  # Native descriptors own validation and conversion.
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError(f'Unsupported value for {label}: {error}') from error


def _setting_matches(attr, value, label):
    while attr.isLink:
        attr = attr.inputLink
    if isinstance(value, dict) and callable(getattr(attr, 'childAttribute', None)):
        for key, child_value in value.items():
            child = attr.childAttribute(key)
            if child is None:
                raise ValueError(f'Unsupported setting: {label}.{key}')
            if not _setting_matches(child, child_value, f'{label}.{key}'):
                return False
        return True
    if isinstance(value, list) and callable(getattr(attr, 'at', None)):
        return len(attr) == len(value) and all(
            _setting_matches(attr.at(index), child_value, f'{label}[{index}]')
            for index, child_value in enumerate(value))
    validate = getattr(attr, 'validateValue', None)
    expected = validate(value) if callable(validate) else value
    return attr.value == expected


def _check_linked_settings(linked):
    for attr, value, label in linked:
        if not _setting_matches(attr, value, label):
            raise ValueError(f'Conflicting linked setting after native settings: {label}')


def settings(node, values, linked=None):
    pending = [] if linked is None else linked
    for name, value in values.items():
        _set_setting(_setting_attribute(node, name), value, f'{node.name}.{name}', pending)
    if linked is None:
        _check_linked_settings(pending)


def _required_settings(target, values, overrides, origin, linked):
    explicit = overrides.get(target.name, {})
    for name, value in values.items():
        if name in explicit:
            attr = _setting_attribute(target, name)
            validate = getattr(attr, 'validateValue', None)
            requested = validate(explicit[name]) if callable(validate) else explicit[name]
            required = validate(value) if callable(validate) else value
            if requested != required:
                raise ValueError(f'Conflicting setting {target.name}.{name}: {origin} requires {value!r}, nodes requests {explicit[name]!r}')
    settings(target, values, linked)


def node(graph, kind):
    found = [item for item in graph.nodes if item.nodeType == kind]
    if len(found) != 1:
        raise ValueError(f'Expected one native {kind}, got {len(found)}')
    return found[0]


def result_nodes(graph):
    """Expose native endpoints; --toNode owns how much of the graph is run."""
    kinds = {'meshing': 'Meshing', 'filtering': 'MeshFiltering', 'texturing': 'Texturing'}
    return {key: node(graph, kind).name for key, kind in kinds.items()}


def configure_standard_transform(graph, overrides, linked=None):
    transform = node(graph, 'SfMTransform')
    # Preserve the accepted identity default, while honoring explicit native settings.
    values = {'method': 'transformation', 'transformation': '', 'scale': 1.,
              'applyScale': True, 'applyRotation': False, 'applyTranslation': False}
    requested = overrides.get(transform.name, {})
    values.update(requested)
    if any(key == 'manualTransform' or key.startswith('manualTransform.')
           for key in requested) and values['method'] != 'manual':
        raise ValueError(f'{transform.name}.manualTransform requires native method=manual; '
                         f'requested method={values["method"]!r}')
    settings(transform, values, linked)


def save_native_mesh(source, root):
    """Preserve the actual Meshing output, without conversion or smoothing."""
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f'Native Meshing outputMesh is missing or empty: {source}')
    # glTF can reference a sibling .bin: preserve its native UID directory as
    # a bundle instead of moving only the JSON document and breaking references.
    bundle = Path(root) / 'meshing-output' if source.suffix.lower() == '.gltf' else None
    destination = bundle / source.name if bundle else Path(root) / ('mesh' + source.suffix)
    if bundle and bundle.exists():
        raise FileExistsError(f'Preserve previous mesh bundle: {bundle}')
    if destination.exists():
        raise FileExistsError(f'Preserve previous mesh export: {destination}')
    digest = sha(source)
    if bundle:
        shutil.copytree(source.parent, bundle)
    else:
        shutil.copyfile(source, destination)
    if sha(destination) != digest or sha(source) != digest:
        raise ValueError('Mesh changed during copy; preserve both files and inspect')
    return {'path': str(destination), 'native_path': str(source), 'sha256': digest,
            'bytes': destination.stat().st_size, 'bundle_directory': str(bundle) if bundle else None,
            'node_output': 'Meshing.outputMesh',
            'processing': 'native raw mesh; no MeshFiltering or smoothing'}


def preflight_masks(base, masks):
    folder = outside(base / masks['folder']).resolve(strict=True)
    extension = masks['extension'].lstrip('.')
    if not extension or not extension.isalnum():
        raise ValueError('Mask extension must be explicit')
    if not folder.is_dir() or not any(
            path.is_file() and path.suffix == '.' + extension for path in folder.iterdir()):
        raise ValueError(f'Masks folder must contain at least one .{extension} file: {folder}')
    if masks.get('invert', False):
        raise ValueError('Dense masks must already have keep=nonzero, reject=zero polarity')
    return folder, extension


def configure_masks(graph, pipeline, masks, folder, extension, overrides=None, linked=None):
    overrides = overrides or {}
    if masks.get('features', True):
        _required_settings(node(graph, 'FeatureExtraction'), {
            'masksFolder': str(folder), 'maskExtension': extension, 'maskInvert': False},
            overrides, 'masks', linked)
    dense = node(graph, 'ExportImages' if pipeline == 'standard' else 'PrepareDenseScene')
    values = {'masksFolders': [str(folder)], 'maskExtension': extension}
    if pipeline == 'legacy':
        # The masked dense route requires alpha and native camera metadata.
        values.update(outputFileType='exr', saveMetadata=True)
    _required_settings(dense, values, overrides, 'masks', linked)


def configure_nodes(graph, pipeline, overrides, threads, masks, mask_input, image_paths):
    """Order native setters/initialize; native attributes and graph keep meaning."""
    camera = node(graph, 'CameraInit')
    pending = []
    # Native CameraInit.initialize resets these two collections, not its upper parameters.
    after_initialize = {key: value for key, value in overrides.get(camera.name, {}).items()
                        if key in ('intrinsics', 'viewpoints')}
    for name, values in overrides.items():
        before = ({key: value for key, value in values.items() if key not in after_initialize}
                  if name == camera.name else values)
        settings(graph.node(name), before, pending)
    _required_settings(node(graph, 'FeatureExtraction'), {'maxThreads': threads},
                       overrides, 'resources.threads', pending)
    if pipeline == 'standard':
        configure_standard_transform(graph, overrides, pending)
    if masks:
        configure_masks(graph, pipeline, masks, *mask_input, overrides=overrides, linked=pending)
    camera.nodeDesc.initialize(camera, image_paths, [])
    settings(camera, after_initialize, pending)
    return camera, pending


def verify_camera_inputs(camera, image_paths):
    """Grouping/metadata may change; the wrapped verified capture may not."""
    actual = [Path(point.path.value).resolve() for point in camera.viewpoints]
    expected = {Path(path).resolve() for path in image_paths}
    if len(actual) != len(image_paths) or set(actual) != expected:
        missing = sorted(str(path) for path in expected - set(actual))
        unexpected = sorted(str(path) for path in set(actual) - expected)
        raise ValueError(f'CameraInit viewpoints changed verified input images: '
                         f'expected count={len(image_paths)}, actual count={len(actual)}, '
                         f'missing={missing}, unexpected={unexpected}')


def mask_files(folder, extension, views):
    """Match native ID-before-stem lookup; every requested view must be covered."""
    matched, errors = [], []
    for view in views:
        candidates = (folder / f"{view['view_id']}.{extension}",
                      folder / (Path(view['image']).stem + '.' + extension))
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            errors.append(f"{view['image']} (view {view['view_id']}): missing {candidates[0].name} or {candidates[1].name}")
        elif not path.is_file():
            errors.append(f"{view['image']} (view {view['view_id']}): mask is not a file: {path}")
        else:
            matched.append({**view, 'path': str(path.resolve()),
                            'bytes': path.stat().st_size, 'sha256': sha(path)})
    if errors:
        raise ValueError('Masks do not cover every frame:\n' + '\n'.join(errors))
    return matched


def native_mask_size(path):
    # Use the bundled reader used by the native pipeline, not an extra package.
    from pyalicevision import image as av
    options = av.ImageReadOptions()
    options.workingColorSpace = av.EImageColorSpace_stringToEnum('linear')
    image = av.Image_uchar()
    av.readImage(str(path), image, options)
    return image.width(), image.height()


def validate_masks(folder, extension, views, read_size=native_mask_size):
    files = mask_files(folder, extension, views)
    errors = []
    for item in files:
        try:
            actual = tuple(read_size(Path(item['path'])))
            expected = (item['width'], item['height'])
            if actual != expected or min(actual) <= 0:
                errors.append(f"{item['image']} (view {item['view_id']}): {item['path']} has {actual}, expected {expected}")
            if sha(item['path']) != item['sha256']:
                errors.append(f"{item['image']}: mask changed while being checked")
        except (OSError, ValueError, RuntimeError) as error:
            errors.append(f"{item['image']} (view {item['view_id']}): unreadable mask {item['path']}: {error}")
    if errors:
        raise ValueError('Invalid masks:\n' + '\n'.join(errors))
    return {'folder': str(folder), 'extension': extension, 'files': files,
            'coverage': 'all_input_views', 'lookup': 'view_id_then_image_stem',
            'reader': 'pyalicevision.image / bundled OpenImageIO'}


def camera_mask_views(camera):
    intrinsics = {item['intrinsicId']: item for item in camera.intrinsics.getPrimitiveValue()}
    views = []
    for view in camera.viewpoints.getPrimitiveValue():
        intrinsic = intrinsics[view['intrinsicId']]
        width, height = int(intrinsic['width']), int(intrinsic['height'])
        if view['viewId'] < 0 or min(width, height) <= 0:
            raise ValueError(f"CameraInit did not provide mask identity/dimensions for {view['path']}")
        views.append({'image': view['path'], 'view_id': view['viewId'],
                      'width': width, 'height': height})
    return views


def resolve_scale_request(request, base):
    """Resolve the working sheet once; manual numbers are the existing alternative."""
    if not isinstance(request, dict):
        raise ValueError('scale must be an object')
    if 'measurements' not in request:
        return dict(request)
    if set(request) != {'mode', 'measurements'}:
        raise ValueError('Use the measurement sheet or manual scale fields, not both')
    if request['mode'] not in ('unknown', 'measured_baseline'):
        raise ValueError('Distance sheets support unknown or measured_baseline scale')
    filename = request['measurements']
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError('scale.measurements must name the working CSV')
    path = outside(Path(base) / filename).resolve(strict=True)
    sheet = load_measurements(path)
    if request['mode'] == 'unknown':
        return {'mode': 'unknown', 'measurements_file': sheet['path'],
                'measurements_sha256': sheet['sha256']}
    return confirmed_scale(sheet)


def verify_run_inputs(run):
    """Check saved input bindings without importing Meshroom or changing the run."""
    root = outside(run).resolve(strict=True)
    effective = read(root / 'effective-settings.json')
    config = effective['settings']
    config_path = Path(effective['settings_file'])
    if sha(config_path) != effective['settings_sha256']:
        raise ValueError('Settings file changed; create a new run')
    if 'measurements' in config.get('scale', {}):
        current_scale = resolve_scale_request(config['scale'], config_path.parent)
        saved_scale = {key: value for key, value in effective['scale'].items()
                       if key != 'applied_evidence'}
        if current_scale != saved_scale:
            raise ValueError('Confirmed measurement sheet changed; preserve this run and create a new one')
    images = (config_path.parent / config['images']).resolve(strict=True)
    verify_images(images, Path(effective['input_manifest']))
    if sha(effective['input_manifest']) != effective['input_manifest_sha256']:
        raise ValueError('Input manifest changed; create a new run')
    if config.get('masks'):
        receipt = effective.get('mask_inputs')
        if not receipt:
            raise ValueError('Masked run has no verified mask binding; create a new run')
        folder, extension = preflight_masks(config_path.parent, config['masks'])
        views = [{key: item[key] for key in ('image', 'view_id', 'width', 'height')}
                 for item in receipt['files']]
        current = mask_files(folder, extension, views)
        if current != receipt['files']:
            changed = [item['image'] for item, previous in zip(current, receipt['files']) if item != previous]
            raise ValueError('Masks changed; create a new run: ' + ', '.join(changed))
    return root, effective


def verify(args):
    root, effective = verify_run_inputs(args.run)
    print(json.dumps({'status': 'verified', 'run': str(root),
                      'input_manifest_sha256': effective['input_manifest_sha256'],
                      'settings_sha256': effective['settings_sha256'],
                      'mask_count': len(effective.get('mask_inputs', {}).get('files', []))}))


def prepare(args):
    root = outside(args.run)
    if root.exists():
        raise FileExistsError('Choose a fresh run directory; resume the saved project explicitly')
    cache = outside(args.cache) if getattr(args, 'cache', None) else root / 'cache'
    config_path = args.settings.resolve(strict=True)
    config = read(config_path)
    base = config_path.parent
    images = outside(base / config['images']).resolve(strict=True)
    input_manifest = outside(base / config['input_manifest']).resolve(strict=True)
    files = verify_images(images, input_manifest)
    pipeline = config['pipeline']
    if pipeline not in ('standard', 'legacy'):
        raise ValueError('Supported base pipelines: standard, legacy')
    threads = config['resources']['threads']
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError('resources.threads must be a positive integer')
    scale = resolve_scale_request(config.get('scale', {'mode': 'unknown'}), base)
    if scale['mode'] not in ('unknown', 'measured_baseline', 'marker_coords'):
        raise ValueError('Invalid physical scale mode')
    if scale['mode'] == 'marker_coords':
        raise ValueError('Use the historical native from_markers recipe for surveyed XYZ; this adapter qualifies scalar scale only')
    describers = [describer for values in config.get('nodes', {}).values()
                  for describer in values.get('describerTypes', [])]
    if pipeline == 'standard' and (scale['mode'] != 'unknown' or any(
            str(describer).lower().startswith('cctag') for describer in describers)):
        raise ValueError('CCTag ID encoding in the new SfM DAG is unqualified; choose legacy for marker diagnostics/scale')
    if any(str(describer).lower().startswith('cctag') and describer != 'cctag3'
           for describer in describers):
        raise ValueError('Only cctag3 (exact native spelling) is supported for CCTag export and baseline scale')
    masks = config.get('masks')
    mask_input = preflight_masks(base, masks) if masks else None
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        os.environ[key] = str(threads)
    module, runtime = init_runtime(args.meshroom)
    graph = module.Graph('reconstruction')
    filename = 'photogrammetry.mgt' if pipeline == 'standard' else 'photogrammetryLegacy.mgt'
    requested_template = getattr(args, 'template', None)
    template = (Path(requested_template) if requested_template is not None else
                args.meshroom.resolve() / 'aliceVision/share/meshroom' / filename).resolve(strict=True)
    if not template.is_file() or template.suffix.lower() not in {'.mgt', '.mg'}:
        raise ValueError('Native template must be a .mgt or .mg file')
    with module.GraphModification(graph):
        graph.initFromTemplate(str(template), keepOutputNodes=True)
        # Preserve the template. Native --toNode selects the computation endpoint.
        camera, linked = configure_nodes(graph, pipeline, config.get('nodes', {}), threads,
                                         masks, mask_input, [str(images / item['name']) for item in files])
    # GraphModification has now updated native outputs/UIDs; linked expectations
    # see all requested source values, independent of JSON insertion order.
    _check_linked_settings(linked)
    verify_camera_inputs(camera, [str(images / item['name']) for item in files])
    if any(item.isCompatibilityNode for item in graph.nodes):
        raise ValueError('Native template contains compatibility nodes')
    mask_inputs = (validate_masks(*mask_input, camera_mask_views(camera)) if masks else None)
    root.mkdir(parents=True)
    project = root / 'project.mg'
    cache.mkdir(parents=True, exist_ok=True)
    graph.save(str(project))
    graph.setExplicitCacheDir(str(cache))
    graph.save(str(project))
    effective = {'schema_version': 1, 'runtime': runtime, 'meshroom_root': str(args.meshroom.resolve()),
                 'input_manifest': str(input_manifest), 'input_manifest_sha256': sha(input_manifest),
                 'settings_file': str(config_path), 'settings_sha256': sha(config_path),
                 'settings': config, 'scale': scale, 'project': str(project), 'cache': str(cache),
                 'template_file': str(template), 'template_sha256': sha(template),
                 'sparse_node': node(graph, 'SfMExpanding' if pipeline == 'standard' else 'StructureFromMotion').name,
                 'dense_node': node(graph, 'Meshing').name,
                 'result_nodes': result_nodes(graph),
                 'nodes': {item.name: item.toDict() for item in graph.nodes}}
    if mask_inputs is not None:
        effective['mask_inputs'] = mask_inputs
    write(root / 'effective-settings.json', effective)
    print(json.dumps({key: effective[key] for key in ('project', 'cache', 'sparse_node', 'dense_node')}))


def load(run):
    root, effective = verify_run_inputs(run)
    module, _ = init_runtime(Path(effective['meshroom_root']))
    graph = module.loadGraph(effective['project'], strictCompatibility=True)
    graph.cacheDir = effective['cache']
    return root, effective, graph, module


def convert(source, output, kind):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Preserve previous export: {output}')
    argv = ['aliceVision_convertSfMFormat', '--input', str(source), '--output', str(output)]
    if kind == 'markers':
        argv += ['--describerTypes', 'cctag3', '--views', 'true', '--intrinsics', 'true',
                 '--extrinsics', 'true', '--structure', 'true', '--observations', 'true']
    else:
        argv += ['--describerTypes', 'unknown', '--views', 'false', '--intrinsics', 'false',
                 '--extrinsics', 'false', '--structure', 'true', '--observations', 'false']
    print(json.dumps({'native_command': argv}), flush=True)
    subprocess.run(argv, check=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise ValueError('Native export missing or empty')


def scale(args):
    root, effective, graph, module = load(args.run)
    request = effective['scale']
    if (root / 'scale-plan.json').exists():
        raise FileExistsError('Scale already prepared; continue the saved graph')
    sparse = graph.node(effective['sparse_node'])
    before = root / 'sparse-before.json'
    convert(sparse.output.value, before, 'markers')
    if request['mode'] == 'unknown':
        transforms = [item for item in graph.nodes if item.nodeType == 'SfMTransform']
        # Unknown physical units do not imply an identity orientation or scale.
        # The native consumer owns the resulting matrix; these are prepared inputs.
        plan = {'mode': 'unknown', 'transform': None,
                'native_transforms': [{'node': item.name, 'inputs': item.toDict()['inputs'],
                                       'status': 'prepared_not_computed'} for item in transforms]}
    else:
        if request['units'] not in ('mm', 'cm', 'm'):
            raise ValueError('Explicit scale units are required')
        with module.GraphModification(graph):
            transform = (node(graph, 'SfMTransform') if effective['settings']['pipeline'] == 'standard'
                         else graph.addNewNode('SfMTransform'))
            if request['mode'] == 'measured_baseline':
                ids, distance = request['ids'], float(request['distance'])
                if len(ids) != 2 or len(set(ids)) != 2 or any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i <= 31 for i in ids):
                    raise ValueError('Two distinct CCTag3 IDs (0..31) are required')
                if not request.get('measurement_source') or not math.isfinite(distance) or distance <= 0:
                    raise ValueError('Positive measured distance and its source are required')
                observed = markers_from_scene(read(before), ids, 'unscaled')
                ratio = distance / observed['distance']
                if not math.isfinite(ratio) or ratio <= 0:
                    raise ValueError('Invalid computed scale')
                settings(transform, {'method': 'transformation', 'transformation': '', 'scale': ratio,
                                     'applyScale': True, 'applyRotation': False, 'applyTranslation': False})
                plan = {'mode': request['mode'], 'units': request['units'], 'source': request,
                        'before': observed, 'transform': {'scale': ratio, 'rotation': IDENTITY, 'translation': [0., 0., 0.]}}
            else:
                # Full surveyed/generated XYZ is distinct from a scalar measurement.
                raise ValueError('marker_coords is reserved; use the historical native from_markers recipe until separately qualified')
            if effective['settings']['pipeline'] == 'legacy':
                graph.addEdge(sparse.output, transform.input)
                graph.addEdge(transform.output, node(graph, 'PrepareDenseScene').input)
        graph.save(effective['project'])
    write(root / 'scale-plan.json', plan)


def export(args):
    root, effective, graph, _ = load(args.run)
    plan = read(root / 'scale-plan.json')
    scene, cloud = root / 'scene.json', root / 'dense.ply'
    # Read actual native edges/UIDs; never choose an arbitrary first cache glob.
    # Colorizing overwrites landmark RGB, including the red-channel CCTag ID.
    # Keep marker diagnostics before that node; IntrinsicsTransforming changes
    # image calibration, not the world coordinates of this physical frame.
    source = (node(graph, 'SfMTransform').output.value
              if effective['settings']['pipeline'] == 'standard'
              else node(graph, 'DepthMap').input.value)
    meshing = node(graph, 'Meshing')
    dense = meshing.output.value
    # This output is already produced by the same Meshing calculation as the cloud.
    # Copy bytes instead of rebuilding a surface from dense.ply.
    mesh = save_native_mesh(meshing.outputMesh.value, root)
    convert(source, scene, 'markers')
    convert(dense, cloud, 'cloud')
    artifact_sha256 = {'scene': sha(scene), 'cloud': sha(cloud), 'mesh': mesh['sha256']}
    if plan['mode'] != 'unknown':
        request = plan['source']
        check = verify_applied_baseline(read(scene), request['ids'], request['distance'], 'scaled')
        after = check['after']
        if not check['passed'] or any(a['reconstructed_view_ids'] != b['reconstructed_view_ids']
                                   for a, b in zip(plan['before']['markers'], after['markers'])):
            raise ValueError('Native scale verification failed; exports are preserved for diagnosis')
        evidence = {**plan, 'status': 'passed', 'applied': True, 'scene_sha256': sha(scene),
                    'artifact_sha256': artifact_sha256,
                    'verification': {key: value for key, value in check.items() if key != 'passed'}}
        evidence_path = root / 'scale-evidence.json'
        write(evidence_path, evidence)
        effective['scale']['applied_evidence'] = str(evidence_path)
    effective['artifacts'] = {'scene': str(scene), 'cloud': str(cloud),
                              'native_scene': str(source), 'native_dense': str(dense),
                              'mesh': mesh['path'], 'native_mesh': mesh['native_path']}
    effective['mesh_export'] = mesh
    effective['artifact_sha256'] = artifact_sha256
    write(root / 'effective-settings.json', effective)


def _resolved_attribute(attr):
    while attr.isLink:
        attr = attr.inputLink
    primitive = attr.getPrimitiveValue()
    if isinstance(primitive, dict) and callable(getattr(attr, 'childAttribute', None)):
        return {key: _resolved_attribute(attr.childAttribute(key)) for key in primitive}
    if isinstance(primitive, list) and callable(getattr(attr, 'at', None)):
        return [_resolved_attribute(attr.at(index)) for index in range(len(primitive))]
    return attr.value


def export_derived(args):
    """Copy one explicit native derived result; raw export/scale bindings stay intact."""
    root, effective, graph, _ = load(args.run)
    selected = graph.node(args.node)
    if selected is None or selected.nodeType not in {'MeshFiltering', 'Texturing'}:
        raise ValueError('Select an existing native MeshFiltering or Texturing node')
    if selected.globalStatus != 'SUCCESS':
        raise ValueError(f'Derived export requires native SUCCESS, got {selected.globalStatus}')
    output = outside(args.output)
    if output.exists():
        raise FileExistsError(f'Preserve previous derived export: {output}')
    project = Path(effective['project']).resolve(strict=True)
    serialized = selected.toDict()
    saved = read(project)['graph'][selected.name]
    # A loaded graph is not evidence that the project was saved after edits.
    for field in ('nodeType', 'uid', 'inputs'):
        if serialized.get(field) != saved.get(field):
            raise ValueError(f'Save the native project before derived export: {selected.name}.{field}')
    if not serialized.get('uid'):
        raise ValueError('Derived native node needs its computed UID')
    resolved = {group: {name: _resolved_attribute(selected.attribute(name))
                        for name in serialized[group]}
                for group in ('inputs', 'outputs')}
    mesh = Path(selected.outputMesh.value).resolve(strict=True)
    if mesh.suffix.lower() != '.obj':
        raise ValueError('Derived export currently qualifies OBJ material bundles only; select outputMeshFileType=obj')
    source_root = (Path(selected.output.value).resolve(strict=True)
                   if selected.nodeType == 'Texturing' else mesh.parent)
    if not mesh.is_relative_to(source_root):
        raise ValueError('Native outputMesh is outside the selected output folder')
    if source_root == output or source_root in output.parents:
        raise ValueError('Derived destination must be outside native node output')
    # File and material closure, including image decoding, precede any copying.
    model_name = mesh.relative_to(source_root).as_posix()
    inspected = obj_bundle(source_root, model_name, textured=selected.nodeType == 'Texturing',
                           read_image=native_mask_size)
    upstream = {}
    for name in ('inputMesh', 'input', 'imagesFolder', 'inputRefMesh', 'normalsFolder'):
        value = resolved['inputs'].get(name)
        if value:
            upstream[name] = native_source(value)
    raw = native_source(node(graph, 'Meshing').outputMesh.value)
    raw_binding = effective.get('mesh_export')
    if raw_binding and raw_binding['sha256'] != raw['sha256']:
        raise ValueError('Raw Meshing source differs from saved native export SHA-256')
    # Preserve native linked outputs and their exact bytes. Texturing's wildcard
    # outputTextures omits some normal/displacement maps, so copy the whole folder.
    model_root = output / 'model'
    if selected.nodeType == 'Texturing':
        shutil.copytree(source_root, model_root)
    else:
        model_root.mkdir(parents=True)
        names = {inspected['model']} | {item['target'] for item in inspected['references']}
        for name in sorted(names):
            destination = model_root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / name, destination)
    bundle = obj_bundle(model_root, inspected['model'],
                        textured=selected.nodeType == 'Texturing', read_image=native_mask_size)
    expected_files = (inspected['files'] if selected.nodeType == 'Texturing' else
                      [item for item in inspected['files'] if item['path'] in names])
    if bundle['files'] != expected_files:
        raise ValueError('Native output changed during copy; preserve derived export for diagnosis')
    provenance = output / 'provenance'
    provenance.mkdir()
    snapshots = {}
    for name, source in (('project.mg', project), ('effective-settings.json', root / 'effective-settings.json')):
        destination = provenance / name
        before = file_record(source)
        shutil.copyfile(source, destination)
        copied = file_record(destination)
        if copied['sha256'] != before['sha256']:
            raise ValueError('Provenance changed during copy; preserve derived export for diagnosis')
        snapshots[name] = {**copied, 'path': 'provenance/' + name, 'source': before['path']}
    receipt = {'schema_version': 1, 'kind': 'native_derived_mesh', 'run': str(root),
               'runtime': effective['runtime'], 'scale': effective['scale'],
               'node': {'name': selected.name, 'serialized': serialized, 'resolved': resolved,
                        'native_status': selected.globalStatus},
               'upstream': upstream, 'raw_meshing': raw,
               'raw_export_sha256': raw_binding['sha256'] if raw_binding else None,
               'source': {'folder': str(source_root), 'model': str(mesh),
                          'files': inspected['files']},
               'provenance': snapshots, 'bundle': bundle,
               'coordinate_frame': {
                   'convention': 'AliceVision d012d055 native OBJ writer (x,-y,-z) relative to SfM/cloud',
                   'actual_geometry_validation': 'required separately against raw/cloud; convention is not a fitted alignment',
                   'export_transform': None, 'bytes_preserved': True}}
    receipt_path = output / 'derived-export.json'
    write(receipt_path, receipt)
    effective.setdefault('derived_exports', []).append(file_record(receipt_path))
    write(root / 'effective-settings.json', effective)
    print(json.dumps({'derived_receipt': str(receipt_path), 'model': str(model_root / bundle['model'])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    item = commands.add_parser('manifest')
    item.add_argument('images', type=Path)
    item.add_argument('--source', required=True)
    item.add_argument('--output', type=Path, required=True)
    item.set_defaults(function=manifest)
    item = commands.add_parser('prepare')
    item.add_argument('settings', type=Path)
    item.add_argument('run', type=Path)
    item.add_argument('meshroom', type=Path)
    item.add_argument('--cache', type=Path, help='Explicit native cache for serial reuse by a new run; default RUN/cache')
    item.add_argument('--template', type=Path, help='Explicit native .mgt/.mg template; default pinned pipeline template')
    item.set_defaults(function=prepare)
    for name, function in [('verify', verify), ('scale', scale), ('export', export)]:
        item = commands.add_parser(name)
        item.add_argument('run', type=Path)
        item.set_defaults(function=function)
    item = commands.add_parser('export-derived', help='Copy an explicit computed MeshFiltering/Texturing result')
    item.add_argument('run', type=Path)
    item.add_argument('--node', required=True, help='Exact saved native node name')
    item.add_argument('--output', type=Path, required=True, help='Fresh directory outside the checkout/cache')
    item.set_defaults(function=export_derived)
    args = parser.parse_args()
    args.function(args)


if __name__ == '__main__':
    main()
