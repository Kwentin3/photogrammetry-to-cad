"""Adapter call-order/edge regressions; storage doubles do not qualify native SfM.

Contracts are the pinned CameraInit initialize reset, public inputLink,
childAttribute and ListAttribute.at APIs. Actual pinned-bundle consumption is a
separate native qualification, not simulated by these tests.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruction as r


class StoredAttribute:
    def __init__(self, value=None, source=None):
        self._value = value
        self.inputLink = source
        self.outputs = []
        if source is not None:
            source.outputs.append(self)

    @property
    def isLink(self):
        return self.inputLink is not None

    @property
    def hasAnyOutputLinks(self):
        return bool(self.outputs)

    @property
    def value(self):
        return self.inputLink.value if self.isLink else self._value

    @value.setter
    def value(self, value):
        if self.isLink:
            raise AssertionError('Adapter must not write a linked destination')
        self._value = deepcopy(value)


class StoredGroup(StoredAttribute):
    def __init__(self, **children):
        super().__init__(children)

    def childAttribute(self, name):
        return self._value.get(name)

    def __getattr__(self, name):
        try:
            return self._value[name]
        except KeyError as error:
            raise AttributeError(name) from error

    @property
    def flatStaticChildren(self):
        return list(self._value.values())


class StoredList(StoredAttribute):
    def __init__(self, values=()):
        super().__init__(list(values))

    def at(self, index):
        return self._value[index]

    def __len__(self):
        return len(self._value)

    def __iter__(self):
        return iter(self._value)


def primitive(attr):
    if attr.isLink:
        return primitive(attr.inputLink)
    if isinstance(attr, StoredGroup):
        return {key: primitive(value) for key, value in attr._value.items()}
    if isinstance(attr, StoredList):
        return [primitive(value) for value in attr]
    return attr.value


class StoredNode:
    def __init__(self, kind, **attrs):
        self.nodeType, self.name = kind, kind + '_1'
        self.attrs = {key: value if isinstance(value, StoredAttribute) else StoredAttribute(value)
                      for key, value in attrs.items()}

    def attribute(self, name):
        return self.attrs[name]

    def __getattr__(self, name):
        try:
            return self.attrs[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def toDict(self):
        return {'nodeType': self.nodeType, 'inputs': {key: primitive(attr) for key, attr in self.attrs.items()}}


class StoredGraph:
    def __init__(self, pipeline='standard'):
        self.initializations = []
        camera = StoredNode('CameraInit', defaultFieldOfView=45., intrinsics=StoredList(), viewpoints=StoredList())

        def initialize(node, paths, recursive):
            self.initializations.append(node.attribute('defaultFieldOfView').value)
            # Same reset boundary as native initialize; native consumer is not mocked as proof.
            node.attribute('intrinsics')._value = [StoredGroup(
                intrinsicId=StoredAttribute(11), width=StoredAttribute(4272), height=StoredAttribute(2848),
                type=StoredAttribute('pinhole'), distortionType=StoredAttribute('radialk3'),
                distortionParams=StoredAttribute([0., 0., 0.]), locked=StoredAttribute(False))]
            node.attribute('viewpoints')._value = [StoredGroup(
                path=StoredAttribute(path), intrinsicId=StoredAttribute(11), viewId=StoredAttribute(index))
                for index, path in enumerate(paths)]

        camera.nodeDesc = SimpleNamespace(initialize=initialize)
        feature = StoredNode('FeatureExtraction', maxThreads=1, describerTypes=['dspsift'],
                             masksFolder='', maskExtension='exr', maskInvert=True)
        matching = StoredNode('FeatureMatching', describerTypes=StoredAttribute(source=feature.attribute('describerTypes')))
        dense = StoredNode('ExportImages' if pipeline == 'standard' else 'PrepareDenseScene',
                           masksFolders=[], maskExtension='exr', outputFileType='jpg', saveMetadata=False)
        transform = StoredNode('SfMTransform', method='auto_from_cameras', transformation='', scale=1.,
                               applyScale=True, applyRotation=True, applyTranslation=True,
                               manualTransform=StoredGroup(manualRotation=StoredGroup(z=StoredAttribute(0.))))
        self.nodes = [camera, feature, matching, dense, transform]

    def node(self, name):
        return next(n for n in self.nodes if n.name == name)


class NativeSettingsOrderTests(unittest.TestCase):
    def configure(self, graph, overrides):
        camera, pending = r.configure_nodes(graph, 'standard', overrides, 2, None, None, ['first.jpg', 'second.jpg'])
        r._check_linked_settings(pending)
        r.verify_camera_inputs(camera, ['first.jpg', 'second.jpg'])
        return camera

    def test_initialize_controls_before_and_intrinsics_viewpoints_after_reset(self):
        camera_values = {'intrinsics': [{'distortionType': 'brown', 'distortionParams': [0.] * 5, 'locked': True}],
                         'viewpoints': [{'intrinsicId': 11}, {'intrinsicId': 11}], 'defaultFieldOfView': 90.}
        for values in (camera_values, dict(reversed(list(camera_values.items())))):
            with self.subTest(order=list(values)):
                graph = StoredGraph()
                camera = self.configure(graph, {'CameraInit_1': values})
                self.assertEqual(graph.initializations, [90.])
                intrinsic = primitive(camera.attribute('intrinsics'))[0]
                self.assertEqual((intrinsic['intrinsicId'], intrinsic['width'], intrinsic['height']), (11, 4272, 2848))
                self.assertEqual((intrinsic['distortionType'], intrinsic['distortionParams'], intrinsic['locked']), ('brown', [0.] * 5, True))
                self.assertEqual([v['path'] for v in primitive(camera.attribute('viewpoints'))], ['first.jpg', 'second.jpg'])

    def test_baseline_defaults_and_intentional_native_scaling_remain_available(self):
        graph = StoredGraph()
        camera = self.configure(graph, {})
        self.assertFalse(primitive(camera.attribute('intrinsics'))[0]['locked'])
        transform = graph.node('SfMTransform_1')
        self.assertEqual(transform.attribute('method').value, 'transformation')
        self.assertTrue(transform.attribute('applyScale').value)
        self.configure(graph, {'SfMTransform_1': {'method': 'auto_from_cameras', 'scale': 2., 'applyScale': True}})
        self.assertEqual(transform.attribute('method').value, 'auto_from_cameras')
        self.assertEqual(transform.attribute('scale').value, 2.)
        self.assertTrue(transform.attribute('applyScale').value)

    def test_deferred_viewpoints_preserve_verified_image_identities(self):
        graph = StoredGraph()
        with self.assertRaisesRegex(ValueError, 'CameraInit viewpoints changed verified input images.*foreign.jpg'):
            self.configure(graph, {'CameraInit_1': {'viewpoints': [{'path': 'foreign.jpg'}, {}]}})
        graph = StoredGraph()
        camera = self.configure(graph, {'CameraInit_1': {
            'intrinsics': [{'locked': True}],
            'viewpoints': [{'path': 'second.jpg', 'intrinsicId': 11},
                           {'path': 'first.jpg', 'intrinsicId': 11}]}})
        self.assertEqual([v['path'] for v in primitive(camera.attribute('viewpoints'))], ['second.jpg', 'first.jpg'])
        self.assertTrue(primitive(camera.attribute('intrinsics'))[0]['locked'])
        self.assertEqual(primitive(camera.attribute('intrinsics'))[0]['intrinsicId'], 11)

    def test_linked_nodes_are_independent_of_json_node_order_and_preserve_edges(self):
        requested = {'FeatureMatching_1': {'describerTypes': ['sift']},
                     'FeatureExtraction_1': {'describerTypes': ['sift']}}
        for overrides in (requested, dict(reversed(list(requested.items())))):
            graph = StoredGraph()
            dst = graph.node('FeatureMatching_1').attribute('describerTypes')
            source = dst.inputLink
            self.configure(graph, overrides)
            self.assertIs(dst.inputLink, source)
            self.assertEqual(source.outputs, [dst])
            self.assertEqual(dst.value, ['sift'])

    def test_linked_group_children_work_in_both_key_orders(self):
        for reverse in (False, True):
            source = StoredAttribute(1)
            destination = StoredAttribute(source=source)
            group = StoredGroup(destination=destination, source=source)
            node = StoredNode('Example', group=group)
            request = {'destination': 7, 'source': 7}
            if reverse:
                request = dict(reversed(list(request.items())))
            r.settings(node, {'group': request})
            self.assertEqual(destination.value, 7)
            self.assertIs(destination.inputLink, source)

    def test_inconsistent_linked_requests_fail_in_both_orders(self):
        request = {'FeatureMatching_1': {'describerTypes': ['dspsift']},
                   'FeatureExtraction_1': {'describerTypes': ['sift']}}
        for overrides in (request, dict(reversed(list(request.items())))):
            graph = StoredGraph()
            with self.assertRaisesRegex(ValueError, 'Conflicting linked setting.*FeatureMatching_1.describerTypes'):
                self.configure(graph, overrides)
            self.assertTrue(graph.node('FeatureMatching_1').attribute('describerTypes').isLink)

    def test_native_list_child_edges_survive_and_resize_is_explicit_conflict(self):
        source = StoredAttribute('folder')
        child = StoredAttribute(source=source)
        values = StoredList([child])
        node = StoredNode('Example', folders=values)
        r.settings(node, {'folders': ['folder']})
        self.assertIs(values.at(0), child)
        self.assertIs(child.inputLink, source)
        with self.assertRaisesRegex(ValueError, 'Cannot resize linked list'):
            r.settings(node, {'folders': ['folder', 'other']})
        nested = StoredList([StoredGroup(path=child)])
        with self.assertRaisesRegex(ValueError, 'Cannot resize linked list'):
            r.settings(StoredNode('Example', nested=nested), {'nested': [{}, {}]})

    def test_linked_collection_is_checked_after_initialization_populates_source(self):
        graph = StoredGraph()
        camera = graph.node('CameraInit_1')
        consumer = StoredNode('CalibrationConsumer', intrinsics=StoredAttribute(source=camera.attribute('intrinsics')))
        graph.nodes.append(consumer)
        self.configure(graph, {'CalibrationConsumer_1': {'intrinsics': [{'intrinsicId': 11, 'locked': True}]},
                               'CameraInit_1': {'intrinsics': [{'locked': True}]}})
        self.assertTrue(consumer.attribute('intrinsics').isLink)

    def test_required_resources_and_masks_conflicts_stop_before_initialize(self):
        graph = StoredGraph()
        with self.assertRaisesRegex(ValueError, 'resources.threads'):
            self.configure(graph, {'FeatureExtraction_1': {'maxThreads': 9}})
        self.assertEqual(graph.initializations, [])
        graph = StoredGraph('legacy')
        with self.assertRaisesRegex(ValueError, 'masks requires'):
            r.configure_nodes(graph, 'legacy', {'PrepareDenseScene_1': {'outputFileType': 'jpg'}},
                              2, {'features': False}, (Path('/masks'), 'png'), ['first.jpg', 'second.jpg'])
        self.assertEqual(graph.initializations, [])

    def test_manual_transform_requires_native_manual_method_in_either_key_order(self):
        request = {'manualTransform': {'manualRotation': {'z': 90.}}, 'method': 'manual',
                   'applyScale': False, 'applyRotation': True, 'applyTranslation': False}
        for values in (request, dict(reversed(list(request.items())))):
            graph = StoredGraph()
            self.configure(graph, {'SfMTransform_1': values})
            inputs = graph.node('SfMTransform_1').toDict()['inputs']
            self.assertEqual(inputs['method'], 'manual')
            self.assertEqual(inputs['manualTransform']['manualRotation']['z'], 90.)
            self.assertFalse(inputs['applyScale'])
            self.assertTrue(inputs['applyRotation'])
        for method in ('transformation', 'auto_from_cameras'):
            graph = StoredGraph()
            with self.assertRaisesRegex(ValueError, 'manualTransform requires native method=manual'):
                self.configure(graph, {'SfMTransform_1': {**request, 'method': method}})
            self.assertEqual(graph.initializations, [])

    def test_unsupported_attributes_are_named_before_initialization(self):
        graph = StoredGraph()
        with self.assertRaisesRegex(ValueError, 'Unsupported setting: FeatureExtraction_1.missing'):
            self.configure(graph, {'FeatureExtraction_1': {'missing': True}})
        self.assertEqual(graph.initializations, [])

    def test_unknown_physical_scale_does_not_claim_identity_or_computed_orientation(self):
        with tempfile.TemporaryDirectory(prefix='unknown-transform-plan-') as temporary:
            root = Path(temporary)
            transform = StoredGraph().node('SfMTransform_1')
            r.settings(transform, {'method': 'manual', 'applyScale': False,
                                  'applyRotation': True, 'applyTranslation': False,
                                  'manualTransform': {'manualRotation': {'z': 90.}}})
            sparse = StoredNode('SfMExpanding', output='native.usda')
            graph = StoredGraph(); graph.nodes = [transform, sparse]
            effective = {'scale': {'mode': 'unknown'}, 'sparse_node': sparse.name}
            with mock.patch.object(r, 'load', return_value=(root, effective, graph, None)), \
                    mock.patch.object(r, 'convert', side_effect=lambda source, target, kind: r.write(target, {})):
                r.scale(SimpleNamespace(run=root))
            plan = r.read(root / 'scale-plan.json')
            self.assertEqual(plan['mode'], 'unknown')
            self.assertIsNone(plan['transform'])
            self.assertEqual(plan['native_transforms'][0]['status'], 'prepared_not_computed')
            self.assertFalse(plan['native_transforms'][0]['inputs']['applyScale'])
            self.assertEqual(plan['native_transforms'][0]['inputs']['manualTransform']['manualRotation']['z'], 90.)


if __name__ == '__main__':
    unittest.main()
