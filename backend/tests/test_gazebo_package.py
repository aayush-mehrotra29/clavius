"""Gazebo data/coordinate contract tests; these do not execute Gazebo."""
import copy,json
from xml.etree import ElementTree as ET
import numpy as np
import pytest
from clavius.paths import ROOT
from clavius.robots import import_robot
from clavius.dynamics import SegmentRequest,build_model
from clavius.gazebo_package import make_packet,read_packet,write_world,canonical_hash,GridTerrain,terrain_collada
from clavius.terrain import site

@pytest.fixture
def rover():return import_robot((ROOT/'public/robots/clavius-r1.zip').read_bytes(),'clavius-r1.zip',json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text()))

def test_worker_bundle_keeps_robot_source_and_measured_terrain(rover,tmp_path):
 request=SegmentRequest(robot_id=rover['id'],east_m=60,north_m=0,heading_deg=41,duration_s=20)
 envelope=make_packet(request,rover);packet,reconstructed,prepared=read_packet(envelope)
 assert reconstructed['id']==rover['id']
 assert packet.terrain.native_resolution_m==5
 assert packet.terrain.source_manifest['assets'][0]['sha256']==site().manifest['assets'][0]['sha256']
 assert prepared['heights_m'][40,40]==pytest.approx(float(site().height(60,0)),abs=1e-10)
 model,_,_,_=build_model(rover,request,site())
 root=model.body('base_link');np.testing.assert_allclose(root.pos,prepared['root_position_m'],atol=1e-9)
 p,_,_,metadata,path=write_world(envelope,tmp_path)
 sdf=ET.parse(path);assert sdf.findtext('./world/gravity')=='0 0 -1.62'
 assert len(sdf.findall('./world/model[@name="rover"]/link'))==5
 assert len(sdf.findall('./world/model[@name="rover"]/joint'))==4
 assert len(sdf.findall('.//plugin'))==1
 assert all(float(x.text)==3 for x in sdf.findall('./world/model[@name="rover"]/joint/axis/limit/effort'))
 assert metadata['terrain_mesh_spacing_m']==.5
 collada=ET.parse(tmp_path/'terrain.dae');ns={'c':'http://www.collada.org/2005/11/COLLADASchema'}
 assert collada.find('.//c:up_axis',ns).text=='Z_UP'
 assert collada.find('.//c:triangles',ns).attrib['count']=='12800'
 assert len(collada.find('.//c:float_array',ns).text.split())==6561*3

def test_worker_bundle_tamper_is_not_accepted(rover):
 envelope=make_packet(SegmentRequest(robot_id=rover['id']),rover,flat=True)
 changed=copy.deepcopy(envelope);changed['payload']['request']['speed_m_s']=.1
 with pytest.raises(ValueError,match='checksum'):read_packet(changed)
 changed=copy.deepcopy(envelope);changed['payload']['robot_upload_base64']='AAAA';changed['sha256']=canonical_hash(changed['payload'])
 with pytest.raises(ValueError,match='package checksum'):read_packet(changed)

def test_flat_benchmark_does_not_claim_nasa_measurement(rover,tmp_path):
 envelope=make_packet(SegmentRequest(robot_id=rover['id']),rover,flat=True)
 packet,_,_,_,path=write_world(envelope,tmp_path)
 assert packet.terrain.source_manifest is None
 assert ET.parse(path).find('.//model[@name="terrain"]/link/collision/geometry/plane') is not None
 assert not (tmp_path/'terrain.dae').exists()
 changed=copy.deepcopy(envelope);changed['payload']['terrain']['source_manifest']={'fake':'NASA'};changed['sha256']=canonical_hash(changed['payload'])
 with pytest.raises(ValueError,match='benchmark'):read_packet(changed)

def test_sdf_link_pose_and_inertia_match_authored_robot(rover,tmp_path):
 envelope=make_packet(SegmentRequest(robot_id=rover['id']),rover,flat=True)
 _,_,_,meta,path=write_world(envelope,tmp_path);world=ET.parse(path)
 mass=sum(float(x.text) for x in world.findall('.//model[@name="rover"]/link/inertial/mass'))
 assert mass==24
 for name,limits in [(w['joint'],w['effort_limit_nm']) for w in meta['wheels']]:assert limits==3
 tensor=world.find('.//model[@name="rover"]/link[@name="link_0"]/inertial/inertia')
 assert float(tensor.findtext('ixx'))==1.45
 assert world.findtext('.//model[@name="rover"]/link[@name="link_0"]/inertial/pose')=='0 0 0.4 0 0 0'

def test_terrain_mesh_supplies_normals_matching_an_analytical_plane(tmp_path):
 from types import SimpleNamespace
 axis=np.linspace(-20,20,81);east,north=np.meshgrid(axis,axis)
 # Synthetic geometry unit case only; no NASA provenance or physics claim.
 grid=SimpleNamespace(half_extent_m=20,heights_m=(.2*east+.1*north).ravel().tolist())
 path=tmp_path/'plane.dae';terrain_collada(grid,path)
 ns={'c':'http://www.collada.org/2005/11/COLLADASchema'};mesh=ET.parse(path)
 normal_values=np.fromstring(mesh.find('.//c:source[@id="normals"]/c:float_array',ns).text,sep=' ').reshape(-1,3)
 expected=np.array([-.2,-.1,1.]);expected/=np.linalg.norm(expected)
 np.testing.assert_allclose(normal_values,np.tile(expected,(6561,1)),atol=1e-11)
 triangles=mesh.find('.//c:triangles',ns)
 assert triangles.find('c:input[@semantic="NORMAL"]',ns).attrib=={'semantic':'NORMAL','source':'#normals','offset':'1'}
 indices=np.fromstring(triangles.find('c:p',ns).text,sep=' ',dtype=int).reshape(-1,2)
 np.testing.assert_array_equal(indices[:,0],indices[:,1])
 np.testing.assert_array_equal(indices[:3,0],[0,1,81])
