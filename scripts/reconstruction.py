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
import subprocess

from fetch_dataset import check_input_entries
from check_marker_scale import markers_from_scene

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


def settings(node, values):
    for name, value in values.items():
        attr = node.attribute(name)
        if attr.isLink:
            if attr.value != value:
                raise ValueError(f'Conflicting linked setting: {node.name}.{name}')
        else:
            attr.value = value


def node(graph, kind):
    found = [item for item in graph.nodes if item.nodeType == kind]
    if len(found) != 1:
        raise ValueError(f'Expected one native {kind}, got {len(found)}')
    return found[0]


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


def configure_masks(graph, pipeline, masks, folder, extension):
    if masks.get('features', True):
        settings(node(graph, 'FeatureExtraction'), {
            'masksFolder': str(folder), 'maskExtension': extension, 'maskInvert': False})
    dense = node(graph, 'ExportImages' if pipeline == 'standard' else 'PrepareDenseScene')
    values = {'masksFolders': [str(folder)], 'maskExtension': extension}
    if pipeline == 'legacy':
        # The masked dense route requires alpha and native camera metadata.
        values.update(outputFileType='exr', saveMetadata=True)
    settings(dense, values)


def prepare(args):
    root = outside(args.run)
    if root.exists():
        raise FileExistsError('Choose a fresh run directory; resume the saved project explicitly')
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
    scale = config.get('scale', {'mode': 'unknown'})
    if scale['mode'] not in ('unknown', 'measured_baseline', 'marker_coords'):
        raise ValueError('Invalid physical scale mode')
    if scale['mode'] == 'marker_coords':
        raise ValueError('Use the historical native from_markers recipe for surveyed XYZ; this adapter qualifies scalar scale only')
    describers = config.get('nodes', {}).get('FeatureExtraction_1', {}).get('describerTypes', ['sift'])
    if pipeline == 'standard' and (scale['mode'] != 'unknown' or any(
            str(describer).lower().startswith('cctag') for describer in describers)):
        raise ValueError('CCTag ID encoding in the new SfM DAG is unqualified; choose legacy for marker diagnostics/scale')
    masks = config.get('masks')
    mask_input = preflight_masks(base, masks) if masks else None
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        os.environ[key] = str(threads)
    module, runtime = init_runtime(args.meshroom)
    graph = module.Graph('reconstruction')
    filename = 'photogrammetry.mgt' if pipeline == 'standard' else 'photogrammetryLegacy.mgt'
    template = args.meshroom.resolve() / 'aliceVision/share/meshroom' / filename
    with module.GraphModification(graph):
        graph.initFromTemplate(str(template))
        # Stop at native dense geometry. Presentation/texturing is separate.
        for item in list(graph.nodes):
            if item.nodeType in ('Texturing', 'MeshFiltering', 'CopyFiles'):
                graph.removeNode(item.name)
        for name, values in config.get('nodes', {}).items():
            settings(graph.node(name), values)
        settings(node(graph, 'FeatureExtraction'), {'maxThreads': threads})
        if pipeline == 'standard':
            # A baseline changes scale, not the SfM orientation or origin.
            settings(node(graph, 'SfMTransform'), {
                'method': 'transformation', 'transformation': '', 'scale': 1.,
                'applyScale': True, 'applyRotation': False, 'applyTranslation': False})
        if masks:
            configure_masks(graph, pipeline, masks, *mask_input)
        camera = node(graph, 'CameraInit')
        # All initialization-affecting settings, including FOV, are already set.
        camera.nodeDesc.initialize(camera, [str(images / item['name']) for item in files], [])
    if len(camera.viewpoints) != len(files):
        raise ValueError('CameraInit did not admit every verified input image')
    if any(item.isCompatibilityNode for item in graph.nodes):
        raise ValueError('Native template contains compatibility nodes')
    root.mkdir(parents=True)
    project, cache = root / 'project.mg', root / 'cache'
    cache.mkdir()
    graph.save(str(project))
    graph.setExplicitCacheDir(str(cache))
    graph.save(str(project))
    effective = {'schema_version': 1, 'runtime': runtime, 'meshroom_root': str(args.meshroom.resolve()),
                 'input_manifest': str(input_manifest), 'input_manifest_sha256': sha(input_manifest),
                 'settings_file': str(config_path), 'settings_sha256': sha(config_path),
                 'settings': config, 'scale': scale, 'project': str(project), 'cache': str(cache),
                 'template_sha256': sha(template),
                 'sparse_node': node(graph, 'SfMExpanding' if pipeline == 'standard' else 'StructureFromMotion').name,
                 'dense_node': node(graph, 'Meshing').name,
                 'nodes': {item.name: item.toDict() for item in graph.nodes}}
    write(root / 'effective-settings.json', effective)
    print(json.dumps({key: effective[key] for key in ('project', 'cache', 'sparse_node', 'dense_node')}))


def load(run):
    root = outside(run).resolve(strict=True)
    effective = read(root / 'effective-settings.json')
    config = effective['settings']
    config_path = Path(effective['settings_file'])
    # Never silently change capture/settings between stages or after resume.
    if sha(config_path) != effective['settings_sha256']:
        raise ValueError('Settings file changed; create a new run')
    images = (config_path.parent / config['images']).resolve(strict=True)
    verify_images(images, Path(effective['input_manifest']))
    if sha(effective['input_manifest']) != effective['input_manifest_sha256']:
        raise ValueError('Input manifest changed')
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
        plan = {'mode': 'unknown', 'transform': {'scale': 1., 'rotation': IDENTITY, 'translation': [0., 0., 0.]}}
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
    dense = node(graph, 'Meshing').output.value
    convert(source, scene, 'markers')
    convert(dense, cloud, 'cloud')
    if plan['mode'] != 'unknown':
        request = plan['source']
        after = markers_from_scene(read(scene), request['ids'], 'scaled')
        error = abs(after['distance'] - request['distance'])
        tolerance = 1e-6 + 1e-8 * request['distance']
        if error > tolerance or any(a['reconstructed_view_ids'] != b['reconstructed_view_ids']
                                   for a, b in zip(plan['before']['markers'], after['markers'])):
            raise ValueError('Native scale verification failed; exports are preserved for diagnosis')
        evidence = {**plan, 'status': 'passed', 'applied': True, 'scene_sha256': sha(scene),
                    'verification': {'after': after, 'baseline_error': error, 'numeric_tolerance': tolerance,
                                     'scope': 'numerical transfer, not physical capture accuracy'}}
        evidence_path = root / 'scale-evidence.json'
        write(evidence_path, evidence)
        effective['scale']['applied_evidence'] = str(evidence_path)
    effective['artifacts'] = {'scene': str(scene), 'cloud': str(cloud),
                              'native_scene': str(source), 'native_dense': str(dense)}
    write(root / 'effective-settings.json', effective)


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
    item.set_defaults(function=prepare)
    for name, function in [('scale', scale), ('export', export)]:
        item = commands.add_parser(name)
        item.add_argument('run', type=Path)
        item.set_defaults(function=function)
    args = parser.parse_args()
    args.function(args)


if __name__ == '__main__':
    main()
