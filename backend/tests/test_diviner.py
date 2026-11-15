"""Real-source checks for historical temperature context, gaps and evidence identity."""
import copy,json,math
from pathlib import Path
import pytest
from clavius.diviner import sample,load,resolve_boundary,derive,digest
from clavius.thermal import ThermalConfig
from clavius.paths import DATA
from clavius.terrain import R,stereographic

def test_real_context_retains_native_source_row_and_missing_noon_bin():
 context=sample(-89.44,222.8);midnight,noon=context['bins'];spec=context['source_manifest']
 assert context['source_class']=='historical_observation_composite'
 assert midnight['covered'] and midnight['temperature_k']==148.724106
 assert midnight['source_row']==1751157 and midnight['center_distance_m']==pytest.approx(26.68327,abs=.001)
 assert not noon['covered'] and 'temperature_k' not in noon and 'reference' not in noon
 table=DATA/'raw/diviner'/spec['products'][0]['table_file']
 with table.open('rb') as stream:
  stream.seek(midnight['source_row']*59);row=stream.read(59).decode()
 values=[float(v) for v in row.split(',')]
 assert values[4]==midnight['temperature_k']
 assert values[3]==midnight['cell_center']['latitude_deg']
 assert values[2]==midnight['cell_center']['longitude_deg']


def test_source_projection_registration_and_each_product_sample_center():
 spec,data=load()
 assert [len(p['samples']) for p in data['products']]==[437,149]
 for product in data['products']:
  assert product['projection_check_maximum_residual_m']<.1
  # Sample a genuinely observed noon cell; missing at the origin is not global absence.
  x,y=stereographic(-89.44,222.8)
  row=min(product['samples'],key=lambda s:(s['polar_x_m']-x)**2+(s['polar_y_m']-y)**2)
  values=sample(row['latitude_deg'],row['longitude_deg'])['bins']
  selected=next(b for b in values if b['id']==product['id'])
  assert selected['covered'] and selected['source_row']==row['source_row']
 assert any(b['covered'] for b in sample(-89.427322,-139.487617)['bins'] if 'ltim49' in b['id'])


def test_uncovered_area_and_ambiguous_cell_edge_remain_missing():
 assert not any(b['covered'] for b in sample(-80,0)['bins'])
 spec,data=load();source=sample(-89.44,222.8)['bins'][0]
 row=next(r for r in data['products'][0]['samples'] if r['source_row']==source['source_row'])
 def query(dx):
  x=row['polar_x_m']+dx;y=row['polar_y_m'];latitude=math.degrees(2*math.atan(math.hypot(x,y)/(2*R))-math.pi/2);longitude=math.degrees(math.atan2(x,y))
  return sample(latitude,longitude)['bins'][0]
 assert query(117)['covered']
 assert not query(119)['covered']


def test_retained_ground_reference_is_checked_and_manual_forgery_rejected():
 b=sample(-89.44,222.8)['bins'][0];config=ThermalConfig(ground_temperature_c=b['temperature_c'],ground_reference=b['reference'])
 assert resolve_boundary(config)['sample']['temperature_k']==148.724106
 with pytest.raises(ValueError,match='differs'):resolve_boundary(config.model_copy(update={'ground_temperature_c':0}))
 for key,value in [('derivative_sha256','0'*64),('source_row',9999999),('product_id','missing_product')]:
  reference=config.ground_reference.model_copy(update={key:value})
  with pytest.raises(ValueError):resolve_boundary(config.model_copy(update={'ground_reference':reference}))


def test_altered_context_bytes_are_not_accepted(tmp_path,monkeypatch):
 spec,_=load();bad=tmp_path/'altered.json';bad.write_text('{}')
 monkeypatch.setenv('CLAVIUS_DIVINER_CONTEXT_PATH',str(bad))
 with pytest.raises(ValueError,match='checksum'):load()


def test_special_constant_is_missing_in_explicit_modified_label_fixture(tmp_path):
 spec,_=load();fixture=copy.deepcopy(spec);fixture['products']=fixture['products'][:1];fixture['derivative']['sha256']=None
 product=fixture['products'][0];source=DATA/'raw/diviner'/product['table_file'];xml=(DATA/'raw/diviner'/product['xml_file']).read_text().replace('<records>3604300</records>','<records>2</records>')
 (tmp_path/product['xml_file']).write_text(xml)
 with source.open('rb') as stream:
  header=stream.read(59);stream.seek(1751157*59);native=stream.read(59)
 missing=native[:47]+b'-9999.0000'+native[57:]
 assert len(missing)==59
 (tmp_path/product['table_file']).write_bytes(header+missing+native)
 output=tmp_path/'fixture-context.json';report=derive(fixture,tmp_path,output)
 rows=json.loads(output.read_text())['products'][0]['samples']
 assert report['products'][0]['source_records']==2
 assert len(rows)==1 and rows[0]['source_row']==2
