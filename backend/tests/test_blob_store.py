"""Cold-instance durability and immutable record reads for the hosted store."""
import io,json,shutil,zipfile
from types import SimpleNamespace
import pytest
from clavius import blob_store as store

class FakeBlob:
 def __init__(self):self.objects={}
 def put_blob(self,key,body,**kwargs):
  assert kwargs['access']=='private'
  assert key not in self.objects
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
