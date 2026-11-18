# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Actual incremental mass/load comparisons; ALL new numbers are PRESSUPOSTOS.
Run from repository root: PYTHONPATH=src python examples/onboard/check_examples.py
"""
from copy import deepcopy
from pathlib import Path
import json
from acdt.ai.jet import load_spec
from acdt.ai.onboard import onboard_size

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/onboard/examples'
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for kind in ('jet','vtol','thermal','electric'):
    recipe=load_spec(ROOT/f'examples/onboard/{kind}.yaml')
    if isinstance(recipe['aircraft'],str):recipe['aircraft']=load_spec(ROOT/'examples/onboard'/recipe['aircraft'])
    cases={}
    for label in ('baseline','double_load','extra_payload_kg'):
        spec=deepcopy(recipe)
        if label=='double_load':
            spec['onboard']['loads'][0]['power_W']*=2
            spec['onboard']['loads'][0]['peak_W']*=2
        if label=='extra_payload_kg':spec['onboard']['items'][0]['mass_kg']+=1
        r=onboard_size(spec)
        (OUT/f'{kind}_{label}.json').write_text(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
        a=r['aircraft_result']
        cases[label]={k:a[k] for k in ('mtow_kg','mass_kg','energy_nominal_Wh','battery_mass_kg','fuel_or_battery_mass_kg') if k in a}
        if kind=='jet':cases[label]['fuel_mass_kg']=a['weights']['fuel_mass_kg']
        if kind=='vtol':cases[label]['inclusive_mass_margin_kg']=next(c['margin_kg'] for c in r['checks'] if c['name']=='VTOL_inclusive_mass_budget')
        cases[label].update(run_id=r['run_id'],combined_checks_passed=r['combined_checks_passed'],issues=r['issues'])
    rows.append({'model':kind,'cases':cases})
print(json.dumps(rows,ensure_ascii=False,indent=2))
(OUT/'comparisons.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
