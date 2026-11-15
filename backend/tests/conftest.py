import os,tempfile
_runtime=tempfile.TemporaryDirectory(prefix='clavius-test-')
os.environ['CLAVIUS_RUNTIME']=_runtime.name
