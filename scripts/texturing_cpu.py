"""Bound pinned native CPU Texturing without changing the saved graph.

Run with the Linux bundle Python inside the operator's existing resource limit.
Meshroom owns dependency selection, statuses, logging, and computation. This
adapter only supplies the native executable's supported hardware arguments.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

import reconstruction


def positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('Native memory bytes and saved resources.threads must be positive integers')
    return value


def hardware_arguments(memory_bytes, cores):
    return ['--maxMemoryAvailable', str(positive_integer(memory_bytes)),
            '--maxCoresAvailable', str(positive_integer(cores))]


def inspect_run(run, memory_bytes):
    root, effective, graph, module = reconstruction.load(run)
    target = reconstruction.node(graph, 'Texturing')
    if target.getMrNodeType().name != 'COMMANDLINE':
        raise ValueError('CPU Texturing adapter requires the native COMMANDLINE descriptor')
    if target.globalStatus in {'RUNNING', 'SUBMITTED'} or any(
            chunk.getStatusName() in {'RUNNING', 'SUBMITTED'} for chunk in target.getAllChunks()):
        raise ValueError('Native Texturing is active/submitted; inspect its owner before another run')
    pending, _ = graph.dfsToProcess(startNodes=[target])
    upstream = [item.name for item in pending if item is not target]
    if upstream:
        raise ValueError('Finish native upstream dependencies before CPU Texturing: ' + ', '.join(upstream))
    chunks = target.getChunks()
    if len(chunks) != 1:
        raise ValueError('Pinned CPU Texturing requires one existing native command chunk')
    provider = target.nodeDesc.provider
    environment = provider.runtimeEnv
    if (not isinstance(environment, dict) or provider.runtimeEnv is not environment
            or not isinstance(environment.get('PATH'), str)):
        raise ValueError('Native provider must expose its persistent runtime PATH dictionary')
    if provider.commandPrefix or provider.commandSuffix:
        raise ValueError('CPU Texturing wrapper requires the native direct command environment')
    command = target.nodeDesc.buildCommandLine(chunks[0])
    argv = shlex.split(command)
    if not argv or argv[0] != 'aliceVision_texturing':
        raise ValueError('Native Texturing command must resolve aliceVision_texturing through provider PATH')
    if any(value.startswith(('--maxMemory', '--maxCores')) for value in argv[1:]):
        raise ValueError('Native command already contains hardware flags; do not supply duplicate aliases')
    executable = shutil.which('aliceVision_texturing', path=environment['PATH'])
    if executable is None:
        raise ValueError('aliceVision_texturing is absent from the actual native provider PATH')
    executable = str(Path(executable).resolve(strict=True))
    caps = hardware_arguments(memory_bytes, effective['settings']['resources']['threads'])
    plan = {'run': str(root), 'node': target.name, 'native_status': target.globalStatus,
            'native_node': target.toDict(), 'native_command': command,
            'effective_native_argv': [executable, *argv[1:], *caps],
            'max_memory_bytes': memory_bytes, 'max_cores': effective['settings']['resources']['threads'],
            'scope': 'native Texturing only; outer process/cgroup limit remains operator-owned'}
    return graph, module, target, provider, executable, caps, plan


def wrapper_source(executable, caps):
    return (f'#!{sys.executable}\n'
            'import json, os, sys\n'
            f'argv = [{executable!r}] + sys.argv[1:] + {caps!r}\n'
            "print(json.dumps({'effective_native_argv': argv}), flush=True)\n"
            'os.execv(argv[0], argv)\n')


@contextmanager
def wrapped_executable(provider, executable, caps):
    environment = provider.runtimeEnv
    original_path = environment['PATH']
    with tempfile.TemporaryDirectory(prefix='photogrammetry-texturing-cpu-') as temporary:
        wrapper = Path(temporary) / 'aliceVision_texturing'
        wrapper.write_text(wrapper_source(executable, caps), encoding='utf-8', newline='\n')
        wrapper.chmod(0o700)
        try:
            environment['PATH'] = str(wrapper.parent) + os.pathsep + original_path
            if shutil.which('aliceVision_texturing', path=provider.runtimeEnv['PATH']) != str(wrapper):
                raise ValueError('Native provider PATH does not select the task-owned Texturing wrapper')
            yield
        finally:
            environment['PATH'] = original_path


def run(args):
    if sys.platform != 'linux':
        raise ValueError('CPU Texturing adapter runs in the pinned Linux bundle environment')
    graph, module, target, provider, executable, caps, plan = inspect_run(args.run, args.max_memory_bytes)
    print(json.dumps({'mode': 'plan' if args.plan else 'execute', **plan}), flush=True)
    if args.plan or target.globalStatus == 'SUCCESS':
        return
    with wrapped_executable(provider, executable, caps):
        # Native owner performs its normal graph save, status transitions,
        # command logging and synchronous execution. No custom state writer.
        module.executeGraph(graph, [target])
    if target.globalStatus != 'SUCCESS':
        raise ValueError(f'Native Texturing did not complete successfully: {target.globalStatus}')
    print(json.dumps({'status': 'completed', 'node': target.name,
                      'native_status': target.globalStatus}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--max-memory-bytes', type=int, required=True,
                        help='Explicit native soft memory allowance; outer memory limit remains required')
    parser.add_argument('--plan', action='store_true', help='Inspect actual native command without computing')
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
