"""Generated wrapper and native-exec boundary; no native compute qualification."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import texturing_cpu as cpu


class TexturingCpuTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='texturing-cpu-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = {'PATH': os.environ.get('PATH', '')}
        self.provider = SimpleNamespace(runtimeEnv=self.environment, commandPrefix='', commandSuffix='')
        self.command = 'aliceVision_texturing --input "saved scene.usda" --multiBandNbContrib 1 0 0 0'
        self.descriptor = SimpleNamespace(provider=self.provider,
                                          buildCommandLine=lambda chunk: self.command)
        self.target = SimpleNamespace(name='Texturing_1', nodeType='Texturing', globalStatus='NONE',
                                      nodeDesc=self.descriptor, getMrNodeType=lambda: SimpleNamespace(name='COMMANDLINE'),
                                      toDict=lambda: {'uid': 'native-uid', 'inputs': {'textureSide': 8192, 'downscale': 4}})
        self.chunk = SimpleNamespace(getStatusName=lambda: self.target.globalStatus)
        self.target.getChunks = lambda: [self.chunk]
        self.target.getAllChunks = lambda: [self.chunk]
        sibling = SimpleNamespace(name='CopyFiles_1', nodeType='CopyFiles', globalStatus='NONE')
        self.graph = SimpleNamespace(nodes=[self.target, sibling],
                                     dfsToProcess=lambda startNodes: ([self.target], []))
        self.module = SimpleNamespace(executeGraph=mock.Mock())
        self.effective = {'settings': {'resources': {'threads': 2}}}
        self.load = mock.patch.object(cpu.reconstruction, 'load', return_value=(
            self.root, self.effective, self.graph, self.module))
        self.load.start()
        self.addCleanup(self.load.stop)

    def inspect(self):
        with mock.patch.object(cpu.shutil, 'which', return_value=sys.executable):
            return cpu.inspect_run(self.root, 2147483648)

    def test_wrapper_preserves_arguments_and_appends_genuine_caps_at_native_exec_boundary(self):
        wrapper = self.root / 'aliceVision_texturing'
        caps = cpu.hardware_arguments(2147483648, 2)
        wrapper.write_text(cpu.wrapper_source(sys.executable, caps), encoding='utf-8')
        arguments = ['--input', 'saved scene.usda', '--multiBandNbContrib', '1', '0', '0', '0']
        output = io.StringIO()
        # Native exec is the external boundary. Linux process replacement is
        # qualified on the real bundle, not through Windows CRT exec semantics.
        with mock.patch.object(sys, 'argv', [str(wrapper), *arguments]), \
                mock.patch.object(os, 'execv') as native_exec, redirect_stdout(output):
            runpy.run_path(str(wrapper), run_name='__main__')
        expected = [sys.executable, *arguments, *caps]
        self.assertEqual(native_exec.call_args.args, (sys.executable, expected))
        announced = json.loads(output.getvalue().splitlines()[0])['effective_native_argv']
        self.assertEqual(announced, expected)

    def test_plan_uses_native_command_and_saved_cores_without_execution_or_mutation(self):
        before = dict(self.environment)
        with mock.patch.object(cpu.sys, 'platform', 'linux'), \
                mock.patch.object(cpu.shutil, 'which', return_value=sys.executable), \
                mock.patch('builtins.print') as output:
            cpu.run(argparse.Namespace(run=self.root, max_memory_bytes=2147483648, plan=True))
        plan = json.loads(output.call_args.args[0])
        self.assertEqual(plan['native_node']['uid'], 'native-uid')
        self.assertEqual(plan['max_cores'], 2)
        self.assertEqual(plan['effective_native_argv'][-4:],
                         ['--maxMemoryAvailable', '2147483648', '--maxCoresAvailable', '2'])
        self.assertIn('saved scene.usda', plan['effective_native_argv'])
        self.assertEqual(self.environment, before)
        self.assertEqual(self.target.globalStatus, 'NONE')
        self.module.executeGraph.assert_not_called()

    def test_wrapper_restores_provider_path_and_removes_its_directory_after_failure(self):
        original = self.environment['PATH']
        with mock.patch.object(cpu.shutil, 'which', side_effect=lambda name, path: str(Path(path.split(os.pathsep)[0]) / name)):
            with self.assertRaisesRegex(RuntimeError, 'native failure'):
                with cpu.wrapped_executable(self.provider, sys.executable, cpu.hardware_arguments(2147483648, 2)):
                    directory = Path(self.environment['PATH'].split(os.pathsep)[0])
                    self.assertTrue((directory / 'aliceVision_texturing').is_file())
                    raise RuntimeError('native failure')
        self.assertEqual(self.environment['PATH'], original)
        self.assertFalse(directory.exists())

    def test_only_pending_actual_ancestors_block_plan_siblings_do_not(self):
        self.inspect()  # CopyFiles sibling has NONE; native DFS excludes it.
        ancestor = SimpleNamespace(name='MeshFiltering_1')
        self.graph.dfsToProcess = lambda startNodes: ([ancestor, self.target], [])
        with self.assertRaisesRegex(ValueError, 'MeshFiltering_1'):
            self.inspect()

    def test_active_target_and_duplicate_native_hardware_aliases_fail(self):
        self.target.globalStatus = 'RUNNING'
        with self.assertRaisesRegex(ValueError, 'active/submitted'):
            self.inspect()
        self.target.globalStatus = 'NONE'
        self.command += ' --maxMemory=4096'
        with self.assertRaisesRegex(ValueError, 'duplicate aliases'):
            self.inspect()

    def test_invalid_caps_or_saved_core_count_fail_before_execution(self):
        for memory, cores in ((0, 2), (2147483648, 0), (True, 2)):
            with self.subTest(memory=memory, cores=cores):
                with self.assertRaisesRegex(ValueError, 'positive integers'):
                    cpu.hardware_arguments(memory, cores)
        self.module.executeGraph.assert_not_called()


if __name__ == '__main__':
    unittest.main()
