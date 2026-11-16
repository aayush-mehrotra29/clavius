"""Local immutable artifacts and persistent job/run metadata."""
import hashlib,json,sqlite3,threading,time,uuid,os
from .paths import RUNTIME
_lock=threading.RLock()
def connection():
 c=sqlite3.connect(RUNTIME/'clavius.sqlite3',timeout=20);c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL');return c
with connection() as c:
 c.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT PRIMARY KEY,created REAL,data TEXT)')
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def artifact(value):
 raw=canonical(value);h=hashlib.sha256(raw).hexdigest();p=RUNTIME/'artifacts'/f'{h}.json'
 if not p.exists():
  temporary=p.with_name(f'.{h}-{uuid.uuid4()}.tmp')
  try:
   temporary.write_bytes(raw);temporary.replace(p)
  finally:temporary.unlink(missing_ok=True)
 return h

def put(kind,value,identity=None):
 identity=identity or str(uuid.uuid4()); value={**value,'id':identity};raw=canonical(value).decode()
 with _lock,connection() as c:
  c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)',(kind,identity,time.time(),raw))
 return value

def get(identity):
 with connection() as c:row=c.execute('SELECT data FROM records WHERE id=?',(identity,)).fetchone()
 return json.loads(row['data']) if row else None

def listing(kind,limit=100):
 with connection() as c:rows=c.execute('SELECT data FROM records WHERE kind=? ORDER BY created DESC LIMIT ?',(kind,limit)).fetchall()
 return [json.loads(r['data']) for r in rows]

# Local launchers retain SQLite; hosted instances use private durable storage.
def persist_file(path):return path
def restore_file(path):return path
def persist_directory(path):return path
def restore_directory(path):return path
def request_cancel(identity):return None
def cancel_requested(identity):return False

if os.environ.get('CLAVIUS_STORAGE')=='vercel-blob':
 from .blob_store import put,get,listing,artifact,persist_file,restore_file,persist_directory,restore_directory,request_cancel,cancel_requested
