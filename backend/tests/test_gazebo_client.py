"""Transport and readiness checks. All worker replies here are protocol fixtures,
not evidence of a native Gazebo run or physical validation.
"""
import copy,hashlib,json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from fastapi.testclient import TestClient
from clavius.gazebo_client import GazeboClient,GazeboUnavailable,validate_result,save_worker_sources
from clavius.gazebo_package import canonical_hash
from clavius.paths import RUNTIME

def test_unconfigured_worker_has_no_native_engine_fallback(monkeypatch):
 monkeypatch.delenv('CLAVIUS_GAZEBO_URL',raising=False)
 client=GazeboClient()
 assert not client.capabilities()['available']
 with pytest.raises(GazeboUnavailable,match='No Gazebo worker'):client.call('/jobs',{})

def test_client_does_not_follow_redirects_or_forward_worker_token():
 paths=[]
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   paths.append(self.path)
   if self.path=='/health':self.send_response(302);self.send_header('Location','/redirected');self.end_headers()
   else:self.send_response(200);self.end_headers();self.wfile.write(b'{}')
  def log_message(self,*_):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  status=GazeboClient(f'http://127.0.0.1:{server.server_port}',token='fixture-token').capabilities()
  assert not status['available'];assert '302' in status['reason'];assert paths==['/health']
 finally:server.shutdown();server.server_close();thread.join()

def test_protocol_fixture_requires_matching_bundle_and_real_clock_coverage():
 envelope={'sha256':'a'*64,'payload':{'robot_id':'b'*24,'request':{'duration_s':.1}}}
 # Deliberately synthetic values solely exercise rejection rules.
 row={'t_s':.005,'east_m':0.,'north_m':0.,'up_m':0.,'speed_m_s':0.,'roll_deg':0.,'pitch_deg':0.,'mechanical_w':0.,'mobility_bus_power_w':12.,'quaternion_xyzw':[0.,0.,0.,1.]}
 fixture={'input_bundle_sha256':'a'*64,'robot_id':'b'*24,'engine':{'name':'Gazebo','backend':'gz.sim8.TestFixture'},'request':{'duration_s':.1},'trace':[row,{**row,'t_s':.1}]}
 validate_result(fixture,envelope)
 bad=copy.deepcopy(fixture);bad['input_bundle_sha256']='c'*64
 with pytest.raises(GazeboUnavailable,match='different inputs'):validate_result(bad,envelope)
 bad=copy.deepcopy(fixture);bad['engine']['name']='MuJoCo'
 with pytest.raises(GazeboUnavailable,match='requested Gazebo'):validate_result(bad,envelope)
 bad=copy.deepcopy(fixture);bad['trace'][-1]['t_s']=.05
 with pytest.raises(GazeboUnavailable,match='duration'):validate_result(bad,envelope)
 bad=copy.deepcopy(fixture);bad['trace'][-1]['quaternion_xyzw']=[0,0,0,0]
 with pytest.raises(GazeboUnavailable,match='quaternion'):validate_result(bad,envelope)

def test_worker_source_snapshot_hash_and_paths_are_verified():
 files={'example.py':'print("fixture only")\n'};h=hashlib.sha256()
 for name,value in sorted(files.items()):h.update(name.encode());h.update(value.encode())
 identity=h.hexdigest();save_worker_sources({'source_sha256':identity,'files':files,'requirements':'fixture==1'})
 assert (RUNTIME/'implementations'/identity/'clavius/example.py').read_text()==files['example.py']
 with pytest.raises(GazeboUnavailable,match='invalid path'):save_worker_sources({'source_sha256':identity,'files':{'../escape.py':'bad'}})
 with pytest.raises(GazeboUnavailable,match='checksum'):save_worker_sources({'source_sha256':identity,'files':{'example.py':'tampered'}})

def test_worker_http_reports_missing_runtime_and_requires_configured_token(monkeypatch):
 from clavius import gazebo_worker
 caps={'runtime_available':False,'reason':'Native runtime missing in protocol test.','runtime_identity':'fixture','worker_source_sha256':'0'*64}
 monkeypatch.setattr(gazebo_worker,'runtime_capabilities',lambda:caps)
 client=TestClient(gazebo_worker.app)
 response=client.get('/health');assert response.status_code==200
 assert not response.json()['runtime_available']
 assert not response.json()['benchmark']['passed']
 response=client.post('/jobs',json={});assert response.status_code==503
 monkeypatch.setenv('CLAVIUS_GAZEBO_TOKEN','fixture-required-token')
 assert client.get('/health').status_code==401
 assert client.get('/health',headers={'Authorization':'Bearer fixture-required-token'}).status_code==200


def test_worker_without_explicit_site_identity_cannot_be_selected(monkeypatch):
 from clavius.gazebo_package import PROTOCOL
 client=GazeboClient('http://127.0.0.1:1',token='')
 monkeypatch.setattr(client,'call',lambda *args,**kwargs:{'protocol':PROTOCOL,'runtime_available':True,'worker_source_sha256':'fixture','benchmark':{'passed':True,'worker_source_sha256':'fixture'}})
 report=client.capabilities()
 assert not report['available'] and 'site/frame' in report['reason']
