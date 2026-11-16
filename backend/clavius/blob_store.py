"""Durable hosted records and evidence; immutable versions avoid stale CDN reads."""
import hashlib,io,json,re,time,uuid,zipfile,threading
from functools import wraps
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from .paths import RUNTIME

_progress=ContextVar('clavius_hosted_progress',default=None)
_files=threading.RLock()

def synchronized(function):
 @wraps(function)
 def call(*args,**kwargs):
  with _files:return function(*args,**kwargs)
 return call

def client():
 from vercel.blob import sync
 return sync

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def valid_id(identity):
 if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',identity):raise ValueError('Invalid record identity.')
 return identity

def put(kind,value,identity=None):
 identity=valid_id(identity or str(uuid.uuid4()));valid_id(kind)
 value={**value,'id':identity}
 pending=_progress.get()
 if pending is not None and kind=='job' and value.get('state')=='running':
  pending[identity]=value;return value
 version=f'{time.time_ns():020d}-{kind}-{uuid.uuid4().hex}'
 client().put_blob(f'records/{identity}/{version}.json',canonical(value),access='private',content_type='application/json')
 if pending is not None:pending.pop(identity,None)
 return value

def get(identity):
 valid_id(identity)
 pending=_progress.get()
 if pending is not None and identity in pending:return pending[identity]
 versions=list(client().query_blobs(prefix=f'records/{identity}/'))
 if not versions:return None
 selected=max(versions,key=lambda item:item.pathname)
 return json.loads(client().get_blob(selected.url,access='private').body)

def listing(kind,limit=100):
 valid_id(kind);latest={}
 for item in client().query_blobs(prefix='records/'):
  parts=item.pathname.split('/')
  if len(parts)!=3:continue
  version=parts[-1]
  if version.split('-',2)[1]!=kind:continue
  identity=parts[1]
  if identity not in latest or version>latest[identity].pathname.split('/')[-1]:latest[identity]=item
 selected=sorted(latest.values(),key=lambda item:item.pathname.split('/')[-1],reverse=True)[:limit]
 return [json.loads(client().get_blob(item.url,access='private').body) for item in selected]

def request_cancel(identity):
 client().put_blob('cancellations/'+valid_id(identity),b'cancelled',access='private',allow_overwrite=True)

def cancel_requested(identity):
 try:client().head_blob('cancellations/'+valid_id(identity))
 except FileNotFoundError:return False
 return True

@contextmanager
def defer_progress():
 """Hosted requests wait for computation; publish their terminal job state."""
 token=_progress.set({})
 try:yield
 finally:_progress.reset(token)

@synchronized
def persist_file(path):
 path=Path(path);relative=path.relative_to(RUNTIME).as_posix();key='evidence/'+relative
 try:client().head_blob(key)
 except FileNotFoundError:
  # Concurrent cold instances may publish the same immutable evidence key.
  client().put_blob(key,path.read_bytes(),access='private',content_type='application/octet-stream',allow_overwrite=True)
 return path

@synchronized
def restore_file(path):
 path=Path(path)
 if not path.is_file():
  raw=client().get_blob('evidence/'+path.relative_to(RUNTIME).as_posix(),access='private').body
  path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 return path

def artifact(value):
 raw=canonical(value);identity=hashlib.sha256(raw).hexdigest();path=RUNTIME/'artifacts'/(identity+'.json')
 if not path.exists():path.write_bytes(raw)
 persist_file(path)
 return identity

@synchronized
def persist_directory(path):
 path=Path(path);archive=path.with_suffix('.zip')
 if not archive.is_file():
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w',zipfile.ZIP_DEFLATED) as out:
   for member in sorted(path.rglob('*')):
    if member.is_file():out.write(member,member.relative_to(path).as_posix())
  archive.write_bytes(raw.getvalue())
 persist_file(archive)

@synchronized
def restore_directory(path):
 path=Path(path)
 if path.is_dir() and any(path.iterdir()):return path
 archive=restore_file(path.with_suffix('.zip'));path.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as source:
  for member in source.infolist():
   target=(path/member.filename).resolve()
   if member.is_dir():continue
   if not target.is_relative_to(path.resolve()):raise ValueError('Invalid evidence archive path.')
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read(member))
 return path
