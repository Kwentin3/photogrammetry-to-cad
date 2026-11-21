"""Check the actual DepthMap image route without computing or resaving its graph.

Run with the pinned bundle Python/environment: check_dense_images.py RUN_ROOT.
Native convertSfMFormat owns the marker-only JSON representation; pyalicevision
owns EXR pixels/metadata. The registered-camera contract is shared with reports.
ExportImages metadata differs from PrepareDenseScene metadata in pinned 2026.
"""

import argparse
import json
from pathlib import Path
import re

from check_marker_scale import identifier, scene_reconstructed_views
from reconstruction import convert, load, node, outside, read, sha, write


PROJECTION_KEYS = {'AliceVision:P', 'AliceVision:K', 'AliceVision:R',
                   'AliceVision:t', 'AliceVision:downscale'}
EXPOSURE_KEYS = {'AliceVision:EV', 'AliceVision:EVComp'}
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def artifact(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'Expected a file: {path}')
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def scene_export(root, source):
    """Reuse only a JSON export bound to the unchanged native source and bytes."""
    output = root / 'dense-views.json'
    binding = root / 'dense-views-binding.json'
    source_artifact = artifact(source)
    if output.exists() or binding.exists():
        if not output.is_file() or not binding.is_file():
            raise ValueError('Incomplete dense-views export/binding; preserve it and inspect the interrupted export')
        receipt = read(binding)
        if receipt != {'native_source': source_artifact, 'export': artifact(output)}:
            raise ValueError('dense-views export or native source changed; refusing to reuse or overwrite it')
    else:
        convert(source, output, 'markers')
        if artifact(source) != source_artifact:
            raise ValueError('Native scene changed during export; no binding was accepted')
        receipt = {'native_source': source_artifact, 'export': artifact(output)}
        write(binding, receipt)
    return read(output), receipt


def projection_check(metadata, pipeline, np):
    present = PROJECTION_KEYS & set(metadata)
    if not present and pipeline == 'standard':
        return {'status': 'not_provided_by_native_exportimages',
                'scope': 'ExportImages adds exposure metadata; it does not write PDS projection fields'}
    if present != PROJECTION_KEYS:
        raise ValueError(f'Missing projection metadata: {sorted(PROJECTION_KEYS - present)}')

    def matrix(key, shape):
        values = np.asarray([float(v) for v in re.findall(NUMBER, metadata[key])])
        if values.size != int(np.prod(shape)) or not np.isfinite(values).all():
            raise ValueError(f'Invalid finite metadata matrix: {key}')
        return values.reshape(shape)

    p = matrix('AliceVision:P', (4, 4))
    k = matrix('AliceVision:K', (3, 3))
    r = matrix('AliceVision:R', (3, 3))
    t = matrix('AliceVision:t', (3,))
    if float(metadata['AliceVision:downscale']) != 1.0:
        raise ValueError('Dense-image projection metadata has downscale != 1')
    residual = float(np.max(np.abs(p[:3] - k @ np.column_stack((r, t)))))
    relative = residual / max(1., float(np.max(np.abs(p))))
    rotation = float(np.max(np.abs(r @ r.T - np.eye(3))))
    if (relative >= 1e-4 or not np.allclose(p[3], [0, 0, 0, 1], atol=1e-6)
            or rotation >= 1e-4 or abs(float(np.linalg.det(r)) - 1.) >= 1e-4):
        raise ValueError('Projection metadata fails P=K[R|t] or orthonormal rotation check')
    return {'status': 'passed', 'relative_residual': relative,
            'rotation_residual': rotation,
            'scope': 'internal native metadata consistency; not an independent camera calibration'}


def check_image(path, view, intrinsic, pipeline, masks, av, np, options,
                exposure_state=None, ev_correction=None):
    before = artifact(path)
    metadata = {str(key): str(value)
                for key, value in av.readImageMetadataAsMap(str(path)).items()}
    exposure_check = None
    if pipeline == 'standard':
        if not EXPOSURE_KEYS <= set(metadata):
            raise ValueError(f'Missing ExportImages exposure metadata: {sorted(EXPOSURE_KEYS - set(metadata))}')
        ev = float(metadata['AliceVision:EV'])
        compensation = float(metadata['AliceVision:EVComp'])
        if not np.isfinite(compensation) or compensation <= 0:
            raise ValueError('ExportImages EVComp must be finite and positive')
        if exposure_state is None:
            raise ValueError('Missing native source exposure binding')
        if not np.isfinite(ev) and not (exposure_state['status'] == 'unknown'
                                       and ev_correction is False):
            raise ValueError('Nonfinite EV without native unknown exposure and disabled correction')
        exposure_check = {**exposure_state, 'ev_correction': ev_correction,
                          'ev_metadata': metadata['AliceVision:EV'],
                          'ev_compensation': compensation,
                          'warning': ('native unknown-exposure EV sentinel; DepthMap image cache does not consume EV'
                                      if not np.isfinite(ev) else None)}
    projection = projection_check(metadata, pipeline, np)
    image = av.Image_RGBAfColor()
    av.readImage(str(path), image, options)
    rgba = image.getNumpyArray()
    # Standard can transform intrinsics/resolution; source view dimensions may differ.
    size = intrinsic if 'width' in intrinsic and 'height' in intrinsic else view
    expected = (int(size['height']), int(size['width']), 4)
    if min(expected[:2]) <= 0 or rgba.shape != expected:
        raise ValueError(f'RGBA shape {rgba.shape} differs from native target dimensions {expected}')
    if not np.isfinite(rgba).all():
        raise ValueError('Nonfinite RGBA pixels')
    alpha = rgba[:, :, 3]
    low, high = float(alpha.min()), float(alpha.max())
    if low < 0 or high > 1:
        raise ValueError(f'Alpha outside [0, 1]: {low}, {high}')
    zero = int(np.count_nonzero(alpha == 0))
    one = int(np.count_nonzero(alpha == 1))
    # Native undistortion/remapping initializes out-of-source pixels with RGBA=0.
    # Thus zero/fractional alpha is valid even without external masks. Without
    # capture-specific truth, alpha alone cannot prove that a mask was applied.
    if one == 0:
        raise ValueError('Dense image has no fully opaque foreground')
    if artifact(path) != before:
        raise ValueError('EXR changed while being checked')
    return {**before, 'status': 'passed', 'source_image': view.get('path'),
            'shape': list(rgba.shape),
            'dimension_source': 'target_intrinsics' if size is intrinsic else 'native_view',
            'alpha_min': low, 'alpha_max': high,
            'alpha_zero_pixels': zero, 'alpha_one_pixels': one,
            'alpha_fractional_pixels': int(alpha.size - zero - one),
            'external_masks_requested': bool(masks),
            'alpha_interpretation': 'native camera warp padding/source alpha and optional external masks; pixel cause not inferred',
            'exposure_status': exposure_state['status'] if exposure_state else 'not_checked',
            'exposure_check': exposure_check,
            'projection_metadata': projection,
            'alicevision_metadata': {k: v for k, v in metadata.items() if k.startswith('AliceVision:')}}


def check(root, report):
    root, effective, graph, _ = load(root)
    project_before = artifact(effective['project'])
    pipeline = effective['settings']['pipeline']
    if pipeline not in ('standard', 'legacy'):
        raise ValueError('Expected standard or legacy pipeline')
    depth = node(graph, 'DepthMap')
    producer = node(graph, 'ExportImages' if pipeline == 'standard' else 'PrepareDenseScene')
    source = Path(depth.input.value).resolve(strict=True)
    images = Path(depth.imagesFolder.value).resolve(strict=True)
    if images != Path(producer.output.value).resolve(strict=True):
        raise ValueError('DepthMap imagesFolder is not the selected native dense-image producer output')
    expected_source = (node(graph, 'IntrinsicsTransforming').output.value
                       if pipeline == 'standard' else producer.input.value)
    if source != Path(expected_source).resolve(strict=True):
        raise ValueError('DepthMap input differs from the native producer target scene')
    if not images.is_dir():
        raise ValueError('DepthMap imagesFolder is not a directory')
    if producer.outputFileType.value != 'exr':
        raise ValueError('This checker requires the actual dense-image producer outputFileType=exr')
    if pipeline == 'standard' and producer.namingMode.value != 'viewid':
        raise ValueError('This checker requires the actual ExportImages namingMode=viewid')
    if pipeline == 'standard' and producer.exportFullROD.value:
        raise ValueError('Full RoD has a different image-window contract; not qualified by this checker')
    masks = [str(Path(item.value).resolve(strict=True)) for item in producer.masksFolders]
    if any(not Path(folder).is_dir() for folder in masks):
        raise ValueError('Native dense mask input is not a directory')
    report['provenance'] = {
        'effective_settings': artifact(root / 'effective-settings.json'),
        'project': project_before, 'runtime': effective['runtime'],
        'pipeline': pipeline, 'depth_node': depth.name, 'producer_node': producer.name,
        'depth_input': str(source), 'images_folder': str(images),
        'masks_folders': masks, 'mask_extension': producer.maskExtension.value,
        'checker': artifact(__file__),
    }
    scene, binding = scene_export(root, source)
    report['provenance']['dense_views'] = binding
    registered = scene_reconstructed_views(scene, 'dense-image scene')
    if not registered:
        raise ValueError('Native DepthMap input has no independently posed views')
    views = {identifier(v['viewId'], 'viewId'): v for v in scene['views']}
    intrinsics = {identifier(v['intrinsicId'], 'intrinsicId'): v for v in scene['intrinsics']}
    names = {path.name for path in images.iterdir() if path.is_file() and path.suffix.lower() == '.exr'}
    expected = {f'{view_id}.exr' for view_id in registered}
    report.update(registered_view_count=len(registered),
                  registered_view_ids=sorted(registered), exr_count=len(names),
                  missing_files=sorted(expected - names), unexpected_files=sorted(names - expected))
    import numpy as np
    from pyalicevision import image as av
    av_file = Path(av.__file__).resolve(strict=True)
    if not av_file.is_relative_to(Path(effective['meshroom_root']).resolve(strict=True)):
        raise ValueError('EXR reader is not from the pinned runtime')
    report['reader'] = {'name': 'pyalicevision.image / bundled OpenImageIO', 'module': str(av_file)}
    options = av.ImageReadOptions(av.EImageColorSpace_stringToEnum('no_conversion'))
    exposures = {}
    exposure_source = None
    if pipeline == 'standard':
        from pyalicevision import sfmData, sfmDataIO
        exposure_source = artifact(producer.input.value)
        native_scene = sfmData.SfMData()
        if not sfmDataIO.load(native_scene, exposure_source['path'], sfmDataIO.VIEWS):
            raise ValueError('Native ExportImages source exposure scene cannot be read')
        for view_id, native_view in native_scene.getViews().items():
            exposure = native_view.getImage().getCameraExposureSetting()
            value = float(exposure.getExposure())
            if not np.isfinite(value):
                raise ValueError('Nonfinite native source exposure')
            unknown = value == -1.0 and not exposure.isPartiallyDefined()
            if not unknown and value <= 0:
                raise ValueError('Invalid native source exposure outside the unknown sentinel contract')
            exposures[int(view_id)] = {'status': 'unknown' if unknown else 'known',
                                       'native_exposure': value,
                                       'native_partially_defined': bool(exposure.isPartiallyDefined())}
        if not registered <= set(exposures):
            raise ValueError('ExportImages source exposure view IDs do not cover registered target views')
        report['provenance']['exposure_source'] = exposure_source
        report['provenance']['exposure_consumer_contract'] = (
            'Pinned DepthMapEstimator creates ImagesCache with NO_CORRECTION; '
            'mvsUtils/fileIO.cpp correction branch consumes EVComp, not EV')
    for view_id in sorted(registered):
        path = images / f'{view_id}.exr'
        record = {'view_id': view_id, 'path': str(path)}
        try:
            view = views[view_id]
            intrinsic = intrinsics[identifier(view['intrinsicId'], 'intrinsicId')]
            record.update(check_image(path, view, intrinsic, pipeline, masks, av, np, options,
                                      exposures.get(view_id),
                                      bool(producer.evCorrection.value) if pipeline == 'standard' else None))
        except Exception as error:
            if path.is_file():
                record.update(artifact(path))
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
        report['images'].append(record)
    if (artifact(source) != binding['native_source']
            or artifact(root / 'dense-views.json') != binding['export']
            or artifact(effective['project']) != project_before
            or (exposure_source is not None
                and artifact(exposure_source['path']) != exposure_source)):
        raise ValueError('Native scene, bound export or saved graph changed during image checks')
    report['status'] = ('passed' if not report['missing_files'] and not report['unexpected_files']
                        and all(item['status'] == 'passed' for item in report['images']) else 'failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_root', type=Path)
    args = parser.parse_args()
    root = outside(args.run_root).resolve(strict=True)
    report = {'schema_version': 1, 'status': 'failed', 'images': [],
              'scope': 'Native dense-image route/readability/alpha/metadata; not reconstruction accuracy'}
    try:
        check(root, report)
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write(root / 'dense-images-check.json', report)
    print(json.dumps({'status': report['status'], 'report': str(root / 'dense-images-check.json'),
                      'registered': report.get('registered_view_count'),
                      'checked': len(report['images']), 'error': report.get('error')}))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
