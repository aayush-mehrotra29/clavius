"""Cold-instance durability and immutable record reads for the hosted store."""
import io,json,shutil,zipfile
from types import SimpleNamespace
import pytest
from clavius import blob_store as store

class FakeBlob:
 def __init__(self):self.objects={}
 def put_blob(self,key,body,**kwargs):
  assert kwargs['access']=='private'
  assert key not in self.objects or kwargs.get('allow_overwrite')
  self.objects[key]=bytes(body)
 def query_blobs(self,prefix):
  return [SimpleNamespace(pathname=p,url=p) for p in self.objects if p.startswith(prefix)]
 def get_blob(self,key,**kwargs):return SimpleNamespace(body=self.objects[key])
 def head_blob(self,key):
  if key not in self.objects:raise FileNotFoundError(key)

@pytest.fixture
def hosted(monkeypatch,tmp_path):
 blob=FakeBlob();monkeypatch.setattr(store,'client',lambda:blob);monkeypatch.setattr(store,'RUNTIME',tmp_path)
 (tmp_path/'artifacts').mkdir()
 return blob,tmp_path

def test_records_use_new_object_paths_and_survive_instance_cache_loss(hosted):
 blob,_=hosted
 store.put('job',{'state':'queued'},'job-one')
 store.put('job',{'state':'completed','result_id':'run-one'},'job-one')
 assert len(blob.objects)==2
 assert store.get('job-one')['state']=='completed'
 assert store.get('absent') is None
 store.put('run',{'name':'Saved mission'},'run-one')
 assert [r['id'] for r in store.listing('run')]==['run-one']
 assert len(store.listing('job'))==1

def test_progress_is_deferred_but_terminal_results_are_durable(hosted):
 blob,_=hosted
 store.put('job',{'state':'queued'},'job-one')
 with store.defer_progress():
  for i in range(50):store.put('job',{'state':'running','progress':i/50},'job-one')
  assert store.get('job-one')['progress']==49/50
  assert len(blob.objects)==1
  store.put('job',{'state':'completed'},'job-one')
 assert store.get('job-one')['state']=='completed'
 assert len(blob.objects)==2

def test_evidence_and_original_robot_bytes_restore_on_a_fresh_instance(hosted):
 _,root=hosted
 digest=store.artifact({'measured':None,'count':0})
 artifact=root/'artifacts'/(digest+'.json');original=artifact.read_bytes();artifact.unlink()
 assert store.restore_file(artifact).read_bytes()==original
 folder=root/'robots'/'package-hash';folder.mkdir(parents=True)
 (folder/'original-upload.bin').write_bytes(b'original uploaded bytes')
 (folder/'meshes').mkdir();(folder/'meshes'/'wheel.obj').write_bytes(b'vertices')
 store.persist_directory(folder);shutil.rmtree(folder);folder.with_suffix('.zip').unlink()
 store.restore_directory(folder)
 assert (folder/'original-upload.bin').read_bytes()==b'original uploaded bytes'
 assert (folder/'meshes'/'wheel.obj').read_bytes()==b'vertices'

def test_evidence_archive_cannot_write_outside_its_runtime_directory(hosted):
 blob,root=hosted
 raw=io.BytesIO()
 with zipfile.ZipFile(raw,'w') as out:out.writestr('../escape',b'bad')
 blob.objects['evidence/robots/bad.zip']=raw.getvalue()
 with pytest.raises(ValueError,match='Invalid evidence archive path'):store.restore_directory(root/'robots'/'bad')
 assert not (root/'robots'/'escape').exists()

def test_invalid_identity_does_not_reach_blob(hosted):
 blob,_=hosted
 with pytest.raises(ValueError):store.get('../somewhere')
 assert not blob.objects

def test_cancellation_marker_is_visible_without_shared_process_memory(hosted):
 assert not store.cancel_requested('job-one')
 store.request_cancel('job-one');store.request_cancel('job-one')
 assert store.cancel_requested('job-one')

def test_hosted_job_finishes_before_returning_a_response(monkeypatch):
 from clavius import api
 monkeypatch.setenv('CLAVIUS_HOSTED','1')
 monkeypatch.setattr(api.pool,'submit',lambda *a:pytest.fail('Hosted work escaped the request.'))
 def work(progress,cancel):
  progress(.5,'Computing');assert not cancel()
  return {'name':'Hosted lifecycle acceptance','status':'test_fixture'}
 result=api.submit('test_fixture',{},work)
 assert result['state']=='completed'
 assert api.store.get(result['result_id'])['name']=='Hosted lifecycle acceptance'

def test_hosted_timeout_does_not_accept_a_result(monkeypatch):
 from clavius import api
 monkeypatch.setenv('CLAVIUS_HOSTED','1')
 times=iter([0,271]);monkeypatch.setattr(api.time,'monotonic',lambda:next(times))
 result=api.submit('test_fixture',{},lambda *_:pytest.fail('Expired work executed.'))
 assert result['state']=='failed' and result['error']=='TimeoutError'
 assert result['result_id'] is None

def test_profile_schema_selection_is_independent_of_filesystem_order(monkeypatch):
 from pathlib import Path
 from clavius.paths import ROOT
 from clavius.robots import validate_profile,ImportIssue
 original=Path.glob
 def common_first(path,pattern):
  results=list(original(path,pattern))
  if path==ROOT/'contracts/v0.1':results.sort(key=lambda p:p.name!='common.schema.json')
  return iter(results)
 monkeypatch.setattr(Path,'glob',common_first)
 profile=json.loads((ROOT/'public/robots/clavius-r1-profile.json').read_text())
 assert validate_profile(profile)==profile
 profile.pop('mass_kg')
 with pytest.raises(ImportIssue):validate_profile(profile)
