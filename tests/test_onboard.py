# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Hand identities, native adapter deltas, incomplete accounting and compatibility."""
from copy import deepcopy
import asyncio
import json
import math
from pathlib import Path
import subprocess
import sys
import pytest
from acdt.ai.jet import load_spec
from acdt.ai.onboard import onboard_size
from acdt.core.onboard import analyse_onboard, validate_onboard
from acdt.domains.aircraft.onboard import size_onboard

ROOT=Path(__file__).resolve().parents[1]


def recipe(kind):
    r=deepcopy(load_spec(ROOT/f'examples/onboard/{kind}.yaml'))
    if isinstance(r['aircraft'],str): r['aircraft']=load_spec(ROOT/'examples/onboard'/r['aircraft'])
    return r


def checks(r): return {c['name']:c for c in r['checks']}


def test_duty_efficiency_and_bsfc_hand_check():
    s=recipe('thermal')['onboard']; r=analyse_onboard(s,'prop',3600)
    assert r['load_average_W']==25
    assert r['load_peak_W']==100
    assert r['sources'][0]['terminal_average_W']==pytest.approx(25/.9)
    assert r['shaft_extraction_W']==pytest.approx(25/.9/.8)
    assert r['fuel_flow_kg_s']*3600==pytest.approx(25/.9/.8/1000*.3)
    assert r['sources'][0]['energy_Wh']==pytest.approx(25/.9)
    assert r['incremental_payload_kg']==1 and r['incremental_equipment_kg']==.5


def test_dedicated_battery_usable_reserve_boundary_and_missing():
    s=recipe('thermal')['onboard'];x=s['sources'][0]
    x.clear();x.update(id='bus',kind='battery',item_id='power_unit',delivery_efficiency=1,source='PRESSUPOSTO',usable_Wh=30,reserve_fraction=.2,continuous_W=25,peak_W=100)
    r=analyse_onboard(s,'prop',3600)
    assert checks(r)['bus:energy']['passed'] is True
    assert checks(r)['bus:energy']['required_Wh']==30
    x['usable_Wh']=29.99
    assert checks(analyse_onboard(s,'prop',3600))['bus:energy']['passed'] is False
    del x['reserve_fraction']
    assert checks(analyse_onboard(s,'prop',3600))['bus:energy']['passed'] is None
    assert checks(analyse_onboard(s,'prop'))['bus:energy']['passed'] is None


def test_unknown_extraction_stops_native_sizing_not_free_electricity():
    r=recipe('jet');del r['onboard']['sources'][0]['fuel_kg_kWh_terminal']
    o=size_onboard(r)
    assert o['aircraft_result'] is None and o['status']=='unassessed'
    assert o['combined_checks_passed'] is None and 'bus:extraction_model' in o['issues']


@pytest.mark.parametrize('kind',['jet','vtol','thermal','electric'])
def test_actual_load_and_mass_coupling(kind):
    r=recipe(kind);lo=size_onboard(r)
    load=r['onboard']['loads'][0];load['power_W']*=2;load['peak_W']*=2
    hi=size_onboard(r);a,b=lo['aircraft_result'],hi['aircraft_result']
    assert lo['energy_coupled'] and hi['energy_coupled']
    if kind in ('electric','vtol'): assert b['energy_nominal_Wh']>a['energy_nominal_Wh']
    if kind=='vtol':
        assert b['mass_kg']==a['mass_kg']==25
        assert b['battery_mass_kg']>a['battery_mass_kg']
        assert b['energy_Wh']-a['energy_Wh']==pytest.approx((50*.5/.9)*a['t_total_s']/3600)
    else: assert b['mtow_kg']>a['mtow_kg']
    r=recipe(kind);r['onboard']['items'][0]['mass_kg']+=1
    heavier=size_onboard(r)
    if kind=='vtol':
        assert heavier['aircraft_result']['mass_kg']==25
        assert checks(heavier)['VTOL_inclusive_mass_budget']['margin_kg']==pytest.approx(checks(lo)['VTOL_inclusive_mass_budget']['margin_kg']-1)
    else: assert heavier['aircraft_result']['mtow_kg']>a['mtow_kg']
    assert hi['combined_checks_passed'] is not True # failures dominate missing checks
    assert 'CG' in hi['unassessed_checks']


def test_vtol_inclusion_ledger_and_peak_are_not_average():
    r=recipe('vtol');base=size_onboard(r)
    r['onboard']['loads'][0]['peak_W']=500
    high=size_onboard(r)
    assert high['aircraft_result']['energy_nominal_Wh']==base['aircraft_result']['energy_nominal_Wh']
    assert high['aircraft_result']['battery_mass_kg']>base['aircraft_result']['battery_mass_kg']
    del r['mass_ledger']
    assert checks(size_onboard(r))['VTOL_inclusive_mass_budget']['passed'] is None
    r['onboard']['items'][0]['mass_accounting']='incremental';del r['onboard']['items'][0]['included_in']
    with pytest.raises(ValueError,match='inclusive MTOW'): size_onboard(r)
    r=recipe('vtol');r['onboard']['items'][0]['mass_kg']=26
    assert size_onboard(r)['combined_checks_passed'] is False


def test_source_peak_limit_fails_even_small_average():
    s=recipe('electric')['onboard'];s['sources'][0]['peak_W']=50
    r=analyse_onboard(s,'electric',100)
    assert checks(r)['bus:continuous_W']['passed'] is True
    assert checks(r)['bus:peak_W']['passed'] is False
    s['sources'][0].pop('continuous_W')
    assert checks(analyse_onboard(s,'electric'))['bus:continuous_W']['passed'] is None


def test_thermal_breguet_auxiliary_exact_solution_and_reserve_once():
    from acdt.domains.aircraft.weights import PropulsionData,MissionLeg,fuel_fraction,SEGMENT_FRACTIONS
    from acdt import G0
    p=PropulsionData(c_p=1e-7,eta_p=.8,auxiliary_fuel_flow_kg_s=1e-4,auxiliary_pre_s=60,auxiliary_post_s=20)
    l=MissionLeg('loiter',3600,50,15)
    a=G0*l.V*p.c_p/(p.eta_p*l.LD)
    m=(1000*SEGMENT_FRACTIONS['warmup_takeoff']*SEGMENT_FRACTIONS['climb']-p.auxiliary_fuel_flow_kg_s*60)
    m=(m*math.exp(-a*3600)-p.auxiliary_fuel_flow_kg_s*(-math.expm1(-a*3600))/a)*SEGMENT_FRACTIONS['landing']-p.auxiliary_fuel_flow_kg_s*20
    assert fuel_fraction([l],p,initial_mass_kg=1000)==pytest.approx(1.06*(1-m/1000))
    with pytest.raises(ValueError):fuel_fraction([l],p)


def test_jet_cruise_auxiliary_constant_drag_analytic():
    from acdt.domains.aircraft.jet.sizing import integrate_cruise
    r=integrate_cruise(1000,10000,100,1e-5,lambda m:1000,auxiliary_fuel_flow_kg_s=.01)
    assert r['end_mass_kg']==pytest.approx(998)


def test_electric_reserve_dod_not_applied_twice():
    from acdt.domains.aircraft.weights import PropulsionData,MissionLeg,battery_energy
    p=PropulsionData(kind='electric',systems_power=0,dod=.8,energy_reserve=.2)
    legs=[MissionLeg('loiter',3600,20,10)]
    lo=battery_energy(10,legs,p,0);p.systems_power=100
    assert battery_energy(10,legs,p,0)-lo==pytest.approx(100*3600*1.2/.8)


def test_included_jet_mass_is_not_added_again():
    r=recipe('jet');r['onboard']['items'][0].update(mass_accounting='included',included_in='payload')
    a=size_onboard(r)
    assert a['resolved_aircraft']['payload_kg']==r['aircraft']['payload_kg']
    assert a['resolved_aircraft']['auxiliary']['empty_mass_kg']==30
    w=a['aircraft_result']['weights']
    assert a['aircraft_result']['mtow_kg']==pytest.approx(w['empty_mass_kg']+w['crew_kg']+w['payload_kg']+w['fuel_mass_kg'],abs=.02)


def test_component_jet_equipment_is_supplied_once_not_residual():
    r=recipe('jet');r['aircraft']=load_spec(ROOT/'examples/jet/coupled_components.yaml')
    out=size_onboard(r);w=out['aircraft_result']['weights']['build_up']
    assert out['resolved_aircraft']['auxiliary']['empty_mass_kg']==0
    row=[i for i in w['items'] if i['name']=='power_unit'];assert len(row)==1
    assert row[0]['mass_kg']==30


@pytest.mark.parametrize('mutation',[
    lambda s:s['items'].append(deepcopy(s['items'][0])),
    lambda s:s['loads'].append(deepcopy(s['loads'][0])),
    lambda s:s['sources'].append(deepcopy(s['sources'][0])),
    lambda s:s['loads'][0].update(duty=1.1),
    lambda s:s['loads'][0].update(power_W=float('nan')),
    lambda s:s['loads'][0].update(power_W=-1),
    lambda s:s['loads'][0].update(peak_W=1),
    lambda s:s['loads'][0].update(source_id='missing'),
    lambda s:s['sources'][0].update(delivery_efficiency=0),
    lambda s:s['sources'][0].update(item_id='instrument'),
    lambda s:s['items'][0].update(included_in='payload'),
    lambda s:s['items'][0].update(source=''),
    lambda s:s.update(schema_version='2.0'),
])
def test_invalid_accounting(mutation):
    s=recipe('thermal')['onboard'];mutation(s)
    with pytest.raises(ValueError):validate_onboard(s)


def test_no_repeat_native_reserve_and_overlap():
    r=recipe('electric');r['onboard']['sources'][0]['reserve_fraction']=.2
    with pytest.raises(ValueError,match='once only'):size_onboard(r)
    r=recipe('electric');r['aircraft']['assumptions']['propulsion']['systems_power_W']=30
    with pytest.raises(ValueError,match='overlap'):size_onboard(r)
    r=recipe('thermal');r['aircraft']['systems']={'loads':[]}
    with pytest.raises(ValueError,match='legacy systems'):size_onboard(r)


def test_missing_spatial_heat_and_volume_never_pass_and_declared_limits_fail():
    s=recipe('thermal')['onboard'];a=analyse_onboard(s,'prop')
    assert all(checks(a)[k]['passed'] is None for k in ('CG','FOV_3D','declared_heat','allocated_volume'))
    for i in s['items']:i.update(volume_m3=.1,heat_W=100)
    s['constraints']=dict(available_volume_m3=.1,available_heat_rejection_W=150,source='PRESSUPOSTO')
    a=analyse_onboard(s,'prop')
    assert checks(a)['allocated_volume']['passed'] is False
    assert checks(a)['declared_heat']['passed'] is False


def test_hybrid_is_accounting_only_with_fixed_allocations():
    r=recipe('thermal');r['model']='hybrid';r['duration']=dict(accounting_s=3600,source='PRESSUPOSTO')
    a=size_onboard(r)
    assert a['aircraft_result'] is None and not a['energy_coupled']
    assert a['onboard']['sources'][0]['energy_Wh']>0
    assert 'hybrid_propulsion_dispatch_unimplemented' in a['issues']
    assert a['combined_checks_passed'] is None


def test_no_jet_oei_pass_with_native_auxiliary():
    from acdt.domains.aircraft.jet.sizing import size_jet
    r=load_spec(ROOT/'examples/jet/performance_l0.yaml')
    r['auxiliary']={'fuel_flow_kg_s':.001,'thrust_penalty_N':30}
    o=size_jet(r)
    assert o['performance']['requested_checks_passed'] is None
    assert o['performance']['ground'] is None
    assert o['combined_requested_checks_passed'] is False


def test_ignored_or_unsupported_options_rejected():
    r=recipe('jet');r['duration']['accounting_s']=10
    with pytest.raises(ValueError,match='accounting_s'):size_onboard(r)
    r=recipe('jet');r['onboard']['sources'][0]['bsfc_kg_kWh_shaft']=.3
    with pytest.raises(ValueError,match='BSFC'):size_onboard(r)
    r=recipe('thermal');r['aircraft']['assumptions']['propulsion']['propeller']={'type':'fixed_pitch'}
    assert size_onboard(r)['aircraft_result'] is None
    r=recipe('jet');r['mission']={'segments':[]}
    with pytest.raises(ValueError,match='prop only'):size_onboard(r)


def test_record_json_cli_and_mcp(tmp_path,monkeypatch):
    monkeypatch.setenv('ACDT_RUNS_DIR',str(tmp_path/'runs'))
    r=onboard_size(ROOT/'examples/onboard/jet.yaml')
    assert json.loads(Path(r['files']['result']).read_text())==r
    assert json.loads(Path(r['files']['run']).read_text())['status']=='partial'
    proc=subprocess.run([sys.executable,'-m','acdt.cli','onboard','size','--input',str(ROOT/'examples/onboard/vtol.yaml'),'-o',str(tmp_path/'out.json')],cwd=ROOT,text=True,capture_output=True)
    assert proc.returncode==1,proc.stderr
    assert json.loads((tmp_path/'out.json').read_text())['model']=='vtol'
    from acdt.ai.mcp_server import build_server
    srv=build_server();tools=asyncio.run(srv.list_tools())
    assert 'onboard_size' in [t.name for t in tools]
    from acdt.ai.catalogue import WORKFLOW
    assert any('onboard_size' in row['tools'] for row in WORKFLOW)


@pytest.mark.parametrize('kind',['thermal','electric'])
def test_optional_pointmass_consumes_coupled_loads(kind):
    r=recipe(kind)
    r['mission']={'name':'PRESSUPOSTO forward check','pointmass_dt':2,'initial':{'altitude_m':300},'segments':[{'type':'cruise','time_min':2,'speed_m_s':22 if kind=='electric' else 50,'altitude_m':300}]}
    lo=size_onboard(r)
    r['onboard']['loads'][0]['power_W']*=2;r['onboard']['loads'][0]['peak_W']*=2
    hi=size_onboard(r)
    a,b=lo['aircraft_result']['mission_pointmass'],hi['aircraft_result']['mission_pointmass']
    assert not a['aborted'] and not b['aborted']
    key='total_used_Wh' if kind=='electric' else 'total_used_kg'
    assert b[key]>a[key]
    assert lo['onboard_pointmass']['duration_s']==pytest.approx(a['total_time_min']*60)


def test_missing_integration_and_inconsistent_remainder_do_not_fake_cg():
    r=recipe('vtol')
    r['integration']={'assembly':{'components':[]},'placements':{},'source':'PRESSUPOSTO'}
    o=size_onboard(r)
    assert 'incomplete_onboard_placements' in o['issues']
    assert checks(o['onboard'])['CG']['passed'] is None
    r['integration']['placements']={'instrument':{'r':[1,0,0]}}
    r['integration']['base']={'mass_kg':1,'cg':[0,0,0]}
    with pytest.raises(ValueError,match='reconcile'):size_onboard(r)


def test_prop_native_invalid_auxiliary_hook_and_duplicate_inventory():
    from acdt.domains.aircraft.sizing import _prop_data
    from acdt.domains.aircraft.mission import MissionSpec
    r=recipe('thermal')
    r['aircraft']['assumptions']['propulsion']['auxiliary_shaft_W']=-1
    with pytest.raises(ValueError):_prop_data(MissionSpec.from_dict(r['aircraft']))
    r=recipe('thermal')
    r['aircraft']['assumptions']['weights']['components']={'items':[{'name':'power_unit','mass_kg':.5}]}
    with pytest.raises(ValueError,match='already named'):size_onboard(r)


def test_unconverged_jet_not_marked_coupled_or_feasible():
    r=recipe('jet');r['aircraft']['mass_bounds_kg']=[20000,21000]
    out=size_onboard(r)
    assert out['status']=='not_converged' and not out['energy_coupled']
    assert out['combined_checks_passed'] is False


def test_mcp_actual_call_returns_versioned_coupled_result():
    from acdt.ai.mcp_server import build_server
    from mcp import Client
    async def call():
        async with Client(build_server()) as c:
            result=await c.call_tool('onboard_size',{'spec':recipe('vtol'),'record':False})
            return result
    r=asyncio.run(call())
    assert not r.is_error
    text=json.loads(r.content[0].text)
    assert text['schema_version']=='1.0' and text['mass_coupled']


def test_zero_duty_keeps_peak_extraction_and_unknown_oei_visible():
    r=recipe('thermal');r['onboard']['loads'][0]['duty']=0
    o=size_onboard(r)
    assert o['onboard']['fuel_flow_kg_s']==0
    assert 'generator_peak_cruise_shaft_headroom' in checks(o)
    r=recipe('jet');r['aircraft']=load_spec(ROOT/'examples/jet/performance_l0.yaml')
    r['onboard']['loads'][0]['duty']=0
    o=size_onboard(r)
    assert o['aircraft_result']['performance']['requested_checks_passed'] is None
    assert checks(o)['native_requested_performance']['passed'] is None


def test_native_storage_failure_visible_without_changing_native_feasible():
    r=recipe('vtol');r['aircraft']['storage']={'battery':{'nominal_Wh':1,'dod':.8},'assumption_sources':{'*':'PRESSUPOSTO'}}
    o=size_onboard(r)
    assert o['aircraft_result']['feasible'] is True
    assert checks(o)['native_requested_storage']['passed'] is False
    assert o['combined_checks_passed'] is False


def test_thermal_accessory_exhausted_trial_does_not_abort_valid_larger_root():
    from acdt.domains.aircraft.weights import PropulsionData,MissionLeg,EmptyWeightModel,size_takeoff_weight,fuel_fraction
    p=PropulsionData(c_p=0.,auxiliary_fuel_flow_kg_s=3.)
    legs=[MissionLeg('loiter',3600,50,15)]
    r=size_takeoff_weight(100,0,legs,p,EmptyWeightModel(fixed_fraction=.5))
    assert r.converged and r.W0>20000
    assert r.W0==pytest.approx(r.We+r.Wf+100,abs=.001)
    assert math.isfinite(r.Wf)
    assert fuel_fraction(legs,p,initial_mass_kg=r.W0)<1


def test_dedicated_jet_battery_cannot_ignore_unknown_noncruise_time():
    r=recipe('jet');r.pop('duration')
    x=r['onboard']['sources'][0]
    x.clear();x.update(id='bus',kind='battery',item_id='power_unit',delivery_efficiency=.9,usable_Wh=1e6,reserve_fraction=.2,continuous_W=10000,peak_W=10000,source='PRESSUPOSTO')
    out=size_onboard(r)
    assert out['aircraft_result'] is None and out['status']=='unassessed'
    assert 'onboard_noncruise_durations_unassessed' in out['issues']
    assert checks(out['onboard'])['bus:energy']['passed'] is None
