"""Local immutable artifacts and persistent job/run metadata."""
import hashlib,json,sqlite3,threading,time,uuid
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
 if not p.exists():p.write_bytes(raw)
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
