"""Data-only URDF imports; no xacro, scripts, external URLs or XML entities execute."""
import hashlib,io,json,math,posixpath,stat,struct,zipfile
from pathlib import PurePosixPath
from defusedxml import ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from jsonschema import Draft202012Validator
from referencing import Registry,Resource
from .paths import ROOT,RUNTIME
from . import store

class ImportIssue(ValueError):pass

def numbers(text,n=3,default=None):
 values=[float(x) for x in text.split()] if text else (default if default is not None else [0.]*n)
 if len(values)!=n or not all(math.isfinite(x) for x in values):raise ImportIssue('Invalid finite numeric vector in URDF.')
 return values

def origin(node):
 item=node.find('origin') if node is not None else None
 xyz=numbers(item.get('xyz','') if item is not None else '')
 rpy=numbers(item.get('rpy','') if item is not None else '')
 return {'xyz':xyz,'rpy':rpy}

def matrix(pose):
 t=np.eye(4);t[:3,:3]=Rotation.from_euler('xyz',pose['rpy']).as_matrix();t[:3,3]=pose['xyz'];return t

def safe_name(name):
 name=name.replace('\\','/')
 if name.startswith('/') or ':' in name or '..' in PurePosixPath(name).parts:raise ImportIssue('Package paths must stay inside the robot archive.')
 return name

def local_reference(uri,base):
 uri=uri.replace('\\','/')
 if uri.startswith('/') or ':' in uri or '\x00' in uri:raise ImportIssue('Visual dependencies must stay inside the robot archive.')
 return safe_name(posixpath.normpath(posixpath.join(posixpath.dirname(base),uri)))

def unpack(raw,filename):
 if len(raw)>30*1024*1024:raise ImportIssue('Robot package exceeds 30 MB.')
 if filename.lower().endswith('.urdf'):return {safe_name(PurePosixPath(filename).name):raw}
 if not filename.lower().endswith('.zip'):raise ImportIssue('Upload a .urdf file or .zip containing a resolved URDF and its meshes.')
 try:
  z=zipfile.ZipFile(io.BytesIO(raw));members=z.infolist()
 except zipfile.BadZipFile as e:raise ImportIssue('Invalid robot ZIP archive.') from e
 if len(members)>500 or sum(m.file_size for m in members)>100*1024*1024:raise ImportIssue('Robot archive has too many files or exceeds 100 MB expanded.')
 files={}
 for member in members:
  name=safe_name(member.filename)
  if stat.S_ISLNK(member.external_attr>>16):raise ImportIssue('Symbolic links are not supported in robot packages.')
  if member.is_dir():continue
  if PurePosixPath(name).suffix.lower() not in {'.urdf','.json','.stl','.obj','.dae','.glb','.gltf','.bin','.png','.jpg','.jpeg','.mtl','.txt'}:continue
  files[name]=z.read(member)
 return files

def parse_urdf(raw,filename):
 files=unpack(raw,filename);urdfs=[n for n in files if n.lower().endswith('.urdf')]
 if len(urdfs)!=1:raise ImportIssue('Include exactly one resolved .urdf file per robot package.')
 name=urdfs[0]
 try:root=ET.fromstring(files[name])
 except Exception as e:raise ImportIssue('URDF XML could not be read safely. Expand xacro before uploading.') from e
 if root.tag!='robot':raise ImportIssue('URDF root must be <robot>.')
 # Visual formats can themselves reference remote buffers/textures. Keep the
 # complete dependency graph inside the uploaded archive, not just URDF meshes.
 for asset,content in files.items():
  extension=PurePosixPath(asset).suffix.lower();uris=[];internal_ids=set()
  try:
   if extension in {'.gltf','.glb'}:
    document=content
    if extension=='.glb':
     if len(content)<20 or content[:4]!=b'glTF':raise ImportIssue('Invalid GLB visual asset.')
     length,kind=struct.unpack_from('<II',content,12)
     if kind!=0x4e4f534a:raise ImportIssue('GLB asset must start with a JSON chunk.')
     document=content[20:20+length]
    parsed=json.loads(document);uris=[v['uri'] for group in ['buffers','images'] for v in parsed.get(group,[]) if 'uri' in v]
   elif extension=='.dae':
    visual=ET.fromstring(content);internal_ids={node.get('id') for node in visual.iter() if node.get('id')};uris=[node.text.strip() for node in visual.iter() if node.tag.rsplit('}',1)[-1]=='init_from' and node.text]
  except (ValueError,TypeError,KeyError,struct.error) as e:raise ImportIssue(f'Invalid visual asset: {asset}.') from e
  for uri in uris:
   if uri.startswith(('data:','#')) or uri in internal_ids:continue
   candidate=local_reference(uri,asset)
   if candidate not in files:raise ImportIssue(f'Visual dependency {uri} must be included inside the robot archive.')
 links=[];joints=[];issues=[]
 def geometry(parent):
  g=parent.find('geometry')
  if g is None or len(g)!=1:raise ImportIssue('Each visual/collision must contain one supported geometry.')
  child=g[0];kind=child.tag;entry={'type':kind,'origin':origin(parent)}
  if kind=='box':entry['size']=numbers(child.get('size',''))
  elif kind=='cylinder':entry.update(radius=float(child.get('radius','0')),length=float(child.get('length','0')))
  elif kind=='sphere':entry['radius']=float(child.get('radius','0'))
  elif kind=='mesh':
   uri=child.get('filename','')
   if uri.startswith(('http:','https:','file:')):raise ImportIssue('External mesh URLs are not loaded. Include mesh files in the ZIP.')
   path=uri.removeprefix('package://')
   candidates=[local_reference(path,name)]
   if not path.startswith('..'):candidates.append(safe_name(path))
   suffix=path.split('/',1)[-1] if uri.startswith('package://') else path
   found=next((c for c in candidates if c in files),None)
   if found is None:
    matches=[f for f in files if f.endswith('/'+suffix) or f==suffix]
    if len(matches)>1:raise ImportIssue(f'Ambiguous mesh reference: {uri}. Use a package-relative path.')
    found=matches[0] if matches else None
   entry.update(file=found,scale=numbers(child.get('scale',''),default=[1.,1.,1.]))
   if not found:issues.append({'severity':'error','code':'MISSING_MESH','message':f'Mesh {uri} is missing from the package.'})
  else:raise ImportIssue(f'Unsupported URDF geometry: {kind}.')
  numeric=[v for k,v in entry.items() if k in {'radius','length'}]+entry.get('size',[])+entry.get('scale',[])
  if any(not math.isfinite(x) or x<=0 for x in numeric):raise ImportIssue('Geometry dimensions and mesh scales must be positive finite values.')
  return entry
 for link in root.findall('link'):
  link_name=link.get('name','')
  if not link_name or link_name in [l['name'] for l in links]:raise ImportIssue('Every link needs a unique name.')
  inertial=link.find('inertial');mass=None;inertia=None
  if inertial is not None:
   mass_node=inertial.find('mass');tensor=inertial.find('inertia')
   if mass_node is not None:mass=float(mass_node.get('value','nan'))
   if tensor is not None:
    xx,xy,xz,yy,yz,zz=[float(tensor.get(k,'nan')) for k in ['ixx','ixy','ixz','iyy','iyz','izz']]
    inertia=[[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]]
   valid_mass=mass is not None and math.isfinite(mass) and mass>0
   valid_inertia=inertia is not None and np.isfinite(inertia).all() and np.linalg.eigvalsh(inertia).min()>0
   if valid_inertia:
    eig=np.linalg.eigvalsh(inertia);valid_inertia=eig[-1]<=eig[:2].sum()+1e-8
   if not(valid_mass and valid_inertia):issues.append({'severity':'error','code':'INVALID_INERTIA','message':f'{link_name}: specify positive mass and a physically valid inertia tensor.'})
  else:issues.append({'severity':'error','code':'MISSING_INERTIA','message':f'{link_name}: physical mass/inertia is missing.'})
  visuals=[geometry(v) for v in link.findall('visual')];collisions=[geometry(v) for v in link.findall('collision')]
  if not collisions:issues.append({'severity':'warning','code':'MISSING_COLLIDER','message':f'{link_name}: collision geometry is missing.'})
  links.append({'name':link_name,'mass_kg':mass,'inertia_kg_m2':inertia,'inertial_origin':origin(inertial),'visuals':visuals,'collisions':collisions})
 if not links:raise ImportIssue('URDF has no links.')
 link_names={l['name'] for l in links};children=set()
 for joint in root.findall('joint'):
  typ=joint.get('type');parent=joint.find('parent');child=joint.find('child')
  if typ not in {'fixed','continuous','revolute','prismatic'}:raise ImportIssue(f'Unsupported joint type: {typ}.')
  p=parent.get('link') if parent is not None else None;c=child.get('link') if child is not None else None
  if p not in link_names or c not in link_names or c in children or p==c:raise ImportIssue('Joint tree has invalid or repeated parent/child links.')
  children.add(c);axis=joint.find('axis');v=numbers(axis.get('xyz','') if axis is not None else '',default=[1.,0.,0.])
  if np.linalg.norm(v)<1e-8:raise ImportIssue('Joint axis cannot be zero.')
  limit=joint.find('limit');limits={k:float(limit.get(k)) for k in ['lower','upper','effort','velocity'] if limit is not None and limit.get(k) is not None}
  if any(not math.isfinite(x) for x in limits.values()):raise ImportIssue('Joint limits must be finite.')
  joints.append({'name':joint.get('name',''),'type':typ,'parent':p,'child':c,'origin':origin(joint),'axis':(np.array(v)/np.linalg.norm(v)).tolist(),'limits':limits})
 if len({j['name'] for j in joints})!=len(joints) or any(not j['name'] for j in joints):raise ImportIssue('Joints require unique names.')
 roots=link_names-children
 if len(roots)!=1:raise ImportIssue('Robot must have exactly one root link.')
 transforms={next(iter(roots)):np.eye(4)}
 for _ in links:
  for j in joints:
   if j['parent'] in transforms:transforms[j['child']]=transforms[j['parent']]@matrix(j['origin'])
 if len(transforms)!=len(links):raise ImportIssue('Robot tree is cyclic or disconnected.')
 mass_sum=0.;com=np.zeros(3)
 for l in links:
  if l['mass_kg'] and math.isfinite(l['mass_kg']) and l['mass_kg']>0:
   t=transforms[l['name']]@matrix(l['inertial_origin']);mass_sum+=l['mass_kg'];com+=l['mass_kg']*t[:3,3]
  l['zero_pose_matrix']=transforms[l['name']].tolist()
 model={'name':root.get('name','Imported rover'),'root_link':next(iter(roots)),'links':links,'joints':joints,'mass_kg':mass_sum,'center_of_mass_body_m':(com/mass_sum).tolist() if mass_sum else None,'urdf_file':name,'issues':issues,'physical_ready':not any(i['severity']=='error' for i in issues)}
 # Missing tensors are null, never nonfinite JSON values.
 for l in model['links']:
  if l['mass_kg'] is not None and not math.isfinite(l['mass_kg']):l['mass_kg']=None
  if l['inertia_kg_m2'] is not None and not np.isfinite(l['inertia_kg_m2']).all():l['inertia_kg_m2']=None
 return model,files

def validate_profile(profile):
 schemas=[json.loads(p.read_text()) for p in (ROOT/'contracts/v0.1').glob('*.schema.json')]
 registry=Registry().with_resources((s['$id'],Resource.from_contents(s)) for s in schemas)
 schema=next(s for s in schemas if s.get('title')=='Robot capability profile')
 errors=list(Draft202012Validator(schema,registry=registry).iter_errors(profile))
 if errors:raise ImportIssue('; '.join(f'{".".join(map(str,e.path))}: {e.message}' for e in errors[:6]))
 p=profile['power'];m=profile['mobility']
 if p['reserve_wh']>p['battery_capacity_wh']:raise ImportIssue('Battery reserve cannot exceed battery capacity.')
 if abs(np.linalg.norm(p['array_normal_body_unit'])-1)>.001:raise ImportIssue('Solar array normal must be a unit vector.')
 if any(x<=0 for x in profile['dimensions_m']):raise ImportIssue('Robot dimensions must be positive.')
 d=m['validity_domain']
 if d['slope_min_deg']>d['slope_max_deg'] or d['speed_min_m_s']>d['speed_max_m_s']:raise ImportIssue('Mobility validity ranges are inverted.')
 if not d['speed_min_m_s']<=m['nominal_speed_m_s']<=d['speed_max_m_s']:raise ImportIssue('Nominal speed lies outside the response model domain.')
 def finite(value):
  if isinstance(value,dict):return all(finite(v) for v in value.values())
  if isinstance(value,list):return all(finite(v) for v in value)
  return not isinstance(value,(int,float)) or math.isfinite(value)
 if not finite(profile):raise ImportIssue('Robot profile contains a nonfinite number.')
 return profile

def import_robot(raw,filename,profile=None):
 model,files=parse_urdf(raw,filename);h=hashlib.sha256(raw).hexdigest();directory=RUNTIME/'robots'/h
 if profile:
  validate_profile(profile)
  if abs(profile['mass_kg']-model['mass_kg'])>max(.001,.01*model['mass_kg']):raise ImportIssue('Profile total mass differs from the imported URDF by more than 1%. Reconcile the robot and capability profile.')
  if model['center_of_mass_body_m'] is not None and np.linalg.norm(np.array(profile['center_of_mass_body_m'])-model['center_of_mass_body_m'])>.01:raise ImportIssue('Profile center of mass differs from the imported URDF by more than 1 cm.')
 directory.mkdir(exist_ok=True)
 (directory/'original-upload.bin').write_bytes(raw)
 for name,content in files.items():
  target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
 result={'schema_version':'0.2.0','name':model['name'],'package_filename':filename,'package_sha256':h,'model':model,'profile':profile,'profile_sha256':store.artifact(profile) if profile else None,'source_class':'user_supplied','assets':[{'path':n,'url':f'/api/v1/robot-assets/{h}/{n}'} for n in files]}
 identity=hashlib.sha256((h+(result['profile_sha256'] or '')).encode()).hexdigest()[:24]
 store.persist_directory(directory)
 return store.get(identity) or store.put('robot',result,identity=identity)

def revise_mechanics(current,changes):
 """Author a new URDF package with reviewed physical properties, preserving assets."""
 import xml.etree.ElementTree as XML
 if not isinstance(changes,list) or not changes:raise ImportIssue('Provide at least one link property change.')
 directory=RUNTIME/'robots'/current['package_sha256']
 store.restore_directory(directory)
 files={a['path']:(directory/a['path']).read_bytes() for a in current['assets']}
 root=ET.fromstring(files[current['model']['urdf_file']]);links={node.get('name'):node for node in root.findall('link')};seen=set()
 for change in changes:
  if not isinstance(change,dict):raise ImportIssue('Each mechanical change must be a link property object.')
  name=change.get('link')
  if name not in links or name in seen:raise ImportIssue('Mechanical edits must refer to unique existing links.')
  seen.add(name)
  try:
   mass=float(change['mass_kg']);inertia=[float(v) for v in change['inertia_kg_m2']]
   xyz=[float(v) for v in change.get('origin_xyz_m',[0,0,0])];rpy=[float(v) for v in change.get('origin_rpy_rad',[0,0,0])]
  except (KeyError,TypeError,ValueError) as e:raise ImportIssue('Supply mass, six inertia terms, and the center-of-mass pose.') from e
  if mass<=0 or len(inertia)!=6 or len(xyz)!=3 or len(rpy)!=3 or not all(math.isfinite(v) for v in [mass,*inertia,*xyz,*rpy]):raise ImportIssue('Mechanical properties must be finite with positive mass and valid vector lengths.')
  xx,yy,zz,xy,xz,yz=inertia;tensor=np.array([[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]])
  eigen=np.linalg.eigvalsh(tensor)
  if eigen.min()<=0 or eigen[-1]>eigen[:2].sum()+1e-8:raise ImportIssue(f'{name}: inertia must be positive definite and satisfy principal-moment triangle inequalities.')
  link=links[name];old=link.find('inertial')
  if old is not None:link.remove(old)
  inertial=XML.SubElement(link,'inertial');XML.SubElement(inertial,'origin',xyz=' '.join(map(str,xyz)),rpy=' '.join(map(str,rpy)))
  XML.SubElement(inertial,'mass',value=str(mass));XML.SubElement(inertial,'inertia',**dict(zip(['ixx','iyy','izz','ixy','ixz','iyz'],map(str,inertia))))
 files[current['model']['urdf_file']]=XML.tostring(root,encoding='utf-8',xml_declaration=True)
 def package():
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   for name,value in files.items():z.writestr(name,value)
  return out.getvalue()
 parsed,_=parse_urdf(package(),'revised.zip');profile=json.loads(json.dumps(current.get('profile'))) if current.get('profile') else None
 if profile:
  profile.update(mass_kg=parsed['mass_kg'],center_of_mass_body_m=parsed['center_of_mass_body_m'])
  profile['provenance']['notes']+=' Mechanical mass/inertia edited by the user; response and efficiency assumptions need review.'
  profile_name=next((n for n in files if n.endswith('clavius-profile.json')),'clavius-profile.json');files[profile_name]=json.dumps(profile,indent=2).encode()
 revised=import_robot(package(),'revised.zip',profile);revised.update(parent_robot_id=current['id'],source_class=current['source_class'],mechanical_revision='user-declared physical properties; not automatically calibrated')
 return store.put('robot',revised,revised['id'])
