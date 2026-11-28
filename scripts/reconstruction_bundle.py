"""Inspect native OBJ material closure and account for actual bundle bytes.

This is a file boundary, not a replacement for native graph/status ownership.
Only OBJ is qualified; binary model formats need their own closure reader.
"""

import hashlib
from pathlib import Path, PurePosixPath
import re
import shlex


def file_record(path, allow_empty=False):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or (not allow_empty and path.stat().st_size == 0):
        raise ValueError(f'Missing or empty artifact: {path}')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def relative_file(root, source, reference):
    """References stay relative within the supplied bundle; never repair them."""
    name = PurePosixPath(reference)
    if (not reference or name.is_absolute() or '..' in name.parts
            or ':' in reference or '\\' in reference):
        raise ValueError(f'External or traversing artifact reference: {source}: {reference}')
    target = (Path(source).parent / reference).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f'Artifact reference outside bundle: {source}: {reference}')
    return target


def directory_records(root):
    root = Path(root).resolve(strict=True)
    result = []
    for path in sorted(root.rglob('*'), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f'Bundle needs actual files/directories, not symlink dependencies: {path}')
        if path.is_file():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError(f'Artifact outside bundle: {path}')
            record = file_record(path, allow_empty=True)
            record['path'] = path.relative_to(root).as_posix()
            result.append(record)
    return result


def image_size(path):
    # Existing local geometry requirements include Pillow. Native export can use
    # its bundled pyalicevision reader instead, without modifying that runtime.
    from PIL import Image
    with Image.open(path) as image:
        image.load()
        return list(image.size)


def obj_bundle(root, model, textured=False, read_image=image_size):
    root = Path(root).resolve(strict=True)
    model = relative_file(root, root / '_root', model)
    if model.suffix.lower() != '.obj':
        raise ValueError('Derived bundle supports OBJ only; other formats need explicit closure qualification')
    references, libraries, used, materials, maps = [], [], set(), set(), {}
    diffuse_materials, map_bindings = set(), []

    def linked(source, value):
        target = relative_file(root, source, value)
        references.append({'source': source.relative_to(root).as_posix(), 'reference': value,
                           'target': target.relative_to(root).as_posix()})
        return target

    for line in model.read_text(encoding='utf-8-sig').splitlines():
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        if fields[0] == 'mtllib':
            libraries.extend(linked(model, value) for value in fields[1:])
        elif fields[0] == 'usemtl':
            used.add(' '.join(fields[1:]))
    for library in sorted(set(libraries), key=lambda item: item.relative_to(root).as_posix()):
        current = None
        for line in library.read_text(encoding='utf-8-sig').splitlines():
            fields = shlex.split(line, comments=True)
            if not fields:
                continue
            command = fields[0].lower()
            if command == 'newmtl':
                current = ' '.join(fields[1:])
                if not current or current in materials:
                    raise ValueError(f'Missing or duplicate material: {library}: {current}')
                materials.add(current)
            elif command.startswith('map_') or command in {'bump', 'disp', 'decal', 'norm'}:
                if current is None or len(fields) < 2:
                    raise ValueError(f'Material map has no material or filename: {library}: {line}')
                # Pinned AliceVision writes a bare filename, no MTL option DSL.
                # Do not guess which token owns a filename in unqualified output.
                if len(fields) != 2:
                    raise ValueError(f'Unsupported native material map syntax: {library}: {line}')
                target = linked(library, fields[1])
                name = target.relative_to(root).as_posix()
                map_bindings.append({'material': current, 'semantic': command, 'path': name})
                if command == 'map_kd':
                    diffuse_materials.add(current)
                if name not in maps:
                    size = list(read_image(target))
                    if len(size) != 2 or min(size) <= 0:
                        raise ValueError(f'Unreadable material image: {target}')
                    maps[name] = {'path': name, 'size': size}
    if used - materials:
        raise ValueError('Undefined OBJ materials: ' + ', '.join(sorted(used - materials)))
    if textured and (not used or not maps):
        raise ValueError('Texturing bundle needs used materials and readable texture maps')
    if textured and used - diffuse_materials:
        raise ValueError('Texturing materials lack photographic diffuse maps: ' + ', '.join(sorted(used - diffuse_materials)))
    return {'model': model.relative_to(root).as_posix(), 'files': directory_records(root),
            'references': sorted(references, key=lambda item: (item['source'], item['reference'])),
            'materials': sorted(materials), 'used_materials': sorted(used),
            'maps': [maps[key] for key in sorted(maps)], 'map_bindings': map_bindings}


def native_source(path):
    """Hash native inputs including pinned AV ASCII USD landmark payloads.

    Same bounded writer contract as the existing backup: ASCII main layer,
    relative @assets@, only sibling *_landmarks.usdc binary leaves. This does
    not claim to parse arbitrary USD composition or binary nested references.
    """
    path = Path(path).resolve(strict=True)
    if path.is_dir():
        return {'path': str(path), 'files': directory_records(path)}
    result = file_record(path)
    if path.suffix.lower() in {'.usd', '.usda', '.usdc'}:
        if path.suffix.lower() == '.usdc':
            raise ValueError('Native USD source requires its ASCII main layer, not a binary leaf')
        text = path.read_text(encoding='utf-8')
        if not text.startswith('#usda'):
            raise ValueError('Native USD source is outside pinned ASCII main-layer contract')
        assets = re.findall(r'@([^@\r\n]+)@', text)
        payloads = []
        for reference in sorted(set(assets)):
            target = relative_file(path.parent, path, reference)
            if target.name != path.stem + '_landmarks.usdc':
                raise ValueError(f'USD asset outside pinned AV landmark-leaf contract: {reference}')
            payloads.append({'reference': reference, **file_record(target)})
        result['payloads'] = payloads
        result['reference_contract'] = 'AliceVision d012d055 ASCII main layer / sibling *_landmarks.usdc leaf'
    return result
