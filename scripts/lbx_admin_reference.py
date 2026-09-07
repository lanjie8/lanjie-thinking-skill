#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import requests

URL='https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json'
OUT=Path('admin_reference_output'); OUT.mkdir(exist_ok=True)
TARGET={'120000','140000','150000','310000','320000','330000','340000','360000','370000','410000','420000','430000','440000','450000','520000','610000','620000','640000','110000'}

def center(node):
 c=node.get('center') or {}
 try:return float(c.get('longitude')),float(c.get('latitude'))
 except:return None,None

r=requests.get(URL,timeout=45); r.raise_for_status(); data=r.json()
rows=[]
for prov in data:
 pc=str(prov.get('code') or '')
 if pc not in TARGET: continue
 pname=str(prov.get('name') or '')
 plon,plat=center(prov)
 rows.append({'code':pc,'name':pname,'level':'province','province':pname,'province_code':pc,'prefecture':pname if pname.endswith('市') else '', 'prefecture_code':pc if pname.endswith('市') else '', 'longitude':plon,'latitude':plat})
 for child in prov.get('children') or []:
  cc=str(child.get('code') or ''); cname=str(child.get('name') or ''); level=str(child.get('level') or '')
  clon,clat=center(child)
  if level=='prefecture':
   pref,prefc=cname,cc
  else:
   pref,prefc=(pname,pc) if pname.endswith('市') else ('','')
  rows.append({'code':cc,'name':cname,'level':level,'province':pname,'province_code':pc,'prefecture':pref,'prefecture_code':prefc,'longitude':clon,'latitude':clat})
  for county in child.get('children') or []:
   kc=str(county.get('code') or ''); kname=str(county.get('name') or ''); kl=str(county.get('level') or '')
   klon,klat=center(county)
   rows.append({'code':kc,'name':kname,'level':kl,'province':pname,'province_code':pc,'prefecture':cname if level=='prefecture' else pref,'prefecture_code':cc if level=='prefecture' else prefc,'longitude':klon,'latitude':klat})
(OUT/'admin_reference.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
# compact name index, preserving duplicate district names across provinces
name_index={}
for x in rows:name_index.setdefault(x['name'],[]).append(x)
(OUT/'admin_name_index.json').write_text(json.dumps(name_index,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps({'rows':len(rows),'names':len(name_index),'source':URL},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rows':len(rows),'names':len(name_index)},ensure_ascii=False))
