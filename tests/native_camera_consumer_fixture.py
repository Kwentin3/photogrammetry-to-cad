"""Controlled actual-native-consumer fixture, explicitly not from-scratch SfM.

Use real output intrinsics from adapter -> native CameraInit. Keep 19 known
poses in a COPY of baseline SfMData; remove pose and observations for 20.JPG,
then require the native solver to resect it and perform BA with these locks.
"""
from pathlib import Path
import json
import subprocess
import sys
sys.path.insert(0, '/work/candidate/scripts')
import reconstruction as r
root = Path('/work/partial-from-camera')
root.mkdir()
scene = r.read('/work/baseline/sparse-full.json')
target = next(v for v in scene['views'] if v['path'].endswith('/20.JPG'))
view_id, pose_id = str(target['viewId']), str(target['poseId'])
scene['poses'] = [p for p in scene['poses'] if str(p['poseId']) != pose_id]
for point in scene['structure']:
    point['observations'] = [o for o in point.get('observations',[]) if str(o['observationId']) != view_id]
scene['structure'] = [p for p in scene['structure'] if len(p['observations']) >= 2]
_, _, graph, _ = r.load('/work/candidate20-estimated-locked')
camera_path = graph.node('CameraInit_1').output.value
camera = r.read(camera_path)
assert {str(i['intrinsicId']) for i in scene['intrinsics']} == {str(i['intrinsicId']) for i in camera['intrinsics']}
assert {str(v['viewId']) for v in scene['views']} == {str(v['viewId']) for v in camera['views']}
scene['intrinsics'] = camera['intrinsics']
path = root / 'input19.sfm'
r.write(path,scene)
_, _, base_graph, _ = r.load('/work/baseline')
command = ['aliceVision_incrementalSfM','--input',str(path),
    '--featuresFolders',base_graph.node('FeatureExtraction_1').output.value,
    '--matchesFolders',base_graph.node('FeatureMatching_1').output.value,
    '--describerTypes','sift','--output',str(root/'refined.sfm'),
    '--outputViewsAndPoses',str(root/'cameras.sfm'),'--extraInfoFolder',str(root),
    '--useAutoTransform','false','--computeStructureColor','false',
    '--lockAllIntrinsics','false','--lockScenePreviouslyReconstructed','false']
with (root/'sfm.log').open('w',encoding='utf-8') as log:
    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
after=r.read(root/'refined.sfm')
a,b=camera['intrinsics'][0],after['intrinsics'][0]
assert len(after['poses'])==20
assert a['distortionType']==b['distortionType']=='brown'
for key in ('locked','scaleLocked','offsetLocked','distortionLocked'):
    assert str(a[key]).lower()==str(b[key]).lower()=='true',key
for key in ('focalLength','pixelRatio'):
    assert abs(float(a[key])-float(b[key]))<1e-10,key
for key in ('principalPoint','distortionParams'):
    assert len(a[key])==len(b[key])
    assert max(abs(float(x)-float(y)) for x,y in zip(a[key],b[key]))<1e-10,key
result={'scope':'Controlled real-photo native resection/BA fixture, not from-scratch reconstruction or independent physical calibration',
    'fixture_construction':'Copy baseline native scene; remove pose and observations of20.JPG; copy matching intrinsic-ID from actual native CameraInit',
    'initial_poses':19,'removed_view':view_id,'removed_pose':pose_id,'result_poses':len(after['poses']),
    'landmarks':len(after['structure']),'before':a,'after':b,'passed':True,'command':command,
    'input_sha256':r.sha(path),'camera_init_sha256':r.sha(camera_path),'output_sha256':r.sha(root/'refined.sfm'),
    'adapter_sha256':r.sha(Path('/work/candidate/scripts/reconstruction.py'))}
r.write(root/'acceptance.json',result)
print(json.dumps(result))
