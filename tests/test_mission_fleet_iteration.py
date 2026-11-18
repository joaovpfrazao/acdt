# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Schema 1.1: derived maximum station time, genuine sizing↔capability closure, reserve once."""
import asyncio
import json
from copy import deepcopy
from pathlib import Path
import pytest
from acdt.ai.jet import load_spec
from acdt.ai.mission_fleet import mission_fleet_study
from acdt.domains.aircraft import mission_endurance as EN
from acdt.domains.aircraft.mission_fleet import evaluate_study, validate_study

ROOT=Path(__file__).resolve().parents[1]
RES=dict(time_h=.05,divert_km=2,native_reserve='replace',source='PRESSUPOSTO test')


def spec(name):
    return deepcopy(load_spec(ROOT/f'examples/fleet/{name}.yaml'))


def v11(name):
    d=spec(name);d['schema_version']='1.1';return d


# ---- generic numerics -----------------------------------------------------
def test_bisection_analytic_conservative_and_states():
    r=EN.max_feasible(lambda T:T<=1.2345,.001,100,60)
    assert r['status']=='converged' and 1.2345-.001<=r['value_h']<=1.2345
    assert EN.max_feasible(lambda T:False,.01,10,40)['status']=='infeasible_at_zero_station'
    unb=EN.max_feasible(lambda T:True,.01,10,40)
    assert unb['status']=='not_bounded_within_search_limit' and unb['value_h'] is None and unb['lower_bound_h']==10
    assert EN.max_feasible(lambda T:T<=1.2345,1e-6,100,3)['status']=='max_iterations'
    assert EN.max_feasible(lambda T:None if T>.5 else True,.01,10,40)['status']=='unassessed'


def _ev(tmax,ok=None):
    return dict(derived=dict(status='converged',value_h=tmax),ok=ok or (lambda T:T<=tmax))


def test_closure_contracts_with_residual_history():
    # Analytic capability T_max(Td)=0.8 Td+0.1, requested 1.0: fixed point Td=1.125.
    cl=EN.capability_closure(lambda Td:_ev(.8*Td+.1),1.,.001,30)
    assert cl['status']=='converged' and cl['converged']
    res=[h['residual_h'] for h in cl['history']]
    assert all(b<a for a,b in zip(res,res[1:])) and cl['history'][-1]['requested_verified']
    assert all(h['design_station_h']>=1. for h in cl['history'])  # upward only
    assert len(cl['history'])>1


def test_closure_nonconvergence_states():
    assert EN.capability_closure(lambda Td:_ev(.5),1.,.01,10)['status']=='not_contracting'
    # 0.5 Td + 0.4: residuals .1, .05 ... — contracting but limited to one correction.
    assert EN.capability_closure(lambda Td:_ev(.5*Td+.4),1.,.0001,1)['status']=='max_iterations'
    assert EN.capability_closure(lambda Td:None,1.,.01,5)['status']=='sizing_failed'
    bad=lambda Td:dict(derived=dict(status='infeasible_at_zero_station',value_h=None),ok=lambda T:False)
    assert EN.capability_closure(bad,1.,.01,5)['status']=='capability_infeasible'


@pytest.mark.parametrize('bad',[{'tolerance_h':0},{'closure_tolerance_h':.001,'tolerance_h':.01},{'max_iterations':0},{'foo':1}])
def test_endurance_settings_validated(bad):
    with pytest.raises(ValueError):EN.settings(bad)


# ---- jet fixed-design identity -------------------------------------------
def test_jet_fixed_design_burn_reproduces_size_jet_trip():
    from acdt.domains.aircraft.jet.sizing import size_jet, fixed_design_burn
    a=spec('jet')['candidates'][0]['recipe']['aircraft']
    r=size_jet(a)
    assert r['converged']
    b=fixed_design_burn(a,r['mtow_kg'],a['range_m'])
    assert b['trip_burn_kg']==pytest.approx(r['weights']['trip_burn_kg'],rel=1e-6)
    assert fixed_design_burn(a,r['mtow_kg'],.5*a['range_m'])['trip_burn_kg']<b['trip_burn_kg']


# ---- VTOL analytic maximum, monotonic with load, reserve once ---------------
def _vtol_closed_form(d,reserve_h=0.,native_reserve=None):
    from acdt.domains.aircraft.vtol.size import size_vtol
    from acdt.domains.aircraft.onboard import size_onboard
    from acdt.domains.aircraft.mission_fleet import _bind
    c=d['candidates'][0];s=d['mission']['samples'][0]
    b=size_onboard(_bind(c['recipe'],s,station_h=0.))
    a=b['aircraft_result'];e=a['inputs_resolved']['electric']
    res=e['reserve'] if native_reserve is None else native_reserve
    budget=d['candidates'][0]['recipe']['aircraft']['mass_kg']-b['onboard']['item_mass_kg']-c['recipe']['mass_ledger']['remaining_nonbattery_mass_kg']
    slope=a['cruise']['P_elec_W']+e['systems_power_W']
    usable=budget*e['pack_Wh_kg']*e['dod']/(1+res)
    return (usable-a['energy_Wh'])/slope-reserve_h


def test_vtol_derived_maximum_matches_closed_form_energy_limit():
    d=v11('vtol');n=evaluate_study(d)['rows'][0]['n1']
    T=_vtol_closed_form(d);e=n['endurance']
    assert e['status']=='converged' and T-.01<=e['derived_max_on_station_h']<=T+1e-9
    assert n['closure']['status']=='not_applicable_fixed_supplied_mtow'


def test_derived_endurance_decreases_with_hotel_load():
    out=[]
    for P in (0,300,600):
        d=v11('vtol');d['candidates'][0]['recipe']['onboard']['loads'][0].update(power_W=P,peak_W=max(2*P,1))
        out.append(evaluate_study(d)['rows'][0]['n1']['endurance']['derived_max_on_station_h'])
    assert out[0]>out[1]+.01>out[2]+.02


def test_operational_reserve_applied_once_vtol():
    d0=v11('vtol');d0['operations']['operational_reserve']=dict(RES,time_h=0,divert_km=0)
    d1=v11('vtol');d1['operations']['operational_reserve']=dict(RES)
    n0=evaluate_study(d0)['rows'][0]['n1'];n1=evaluate_study(d1)['rows'][0]['n1']
    t_res=RES['time_h']+RES['divert_km']/(d1['mission']['samples'][0]['speed_m_s']*3.6)
    # Native fraction replaced (0), reserve flown once at cruise power in capability only.
    assert n1['reserve']['native_replaced']==[dict(path='aircraft.electric.reserve',original=.2,replaced_by=0.)]
    assert n0['endurance']['derived_max_on_station_h']-n1['endurance']['derived_max_on_station_h']==pytest.approx(t_res,abs=.021)
    T=_vtol_closed_form(d1,reserve_h=t_res,native_reserve=0.)
    assert T-.01<=n1['endurance']['derived_max_on_station_h']<=T+1e-9
    # Held reserve is NOT in nominal consumption/charging.
    assert n1['metrics']['mission_energy_Wh']==pytest.approx(n0['metrics']['mission_energy_Wh'])
    assert n1['turnaround']['battery_terminal_Wh']==n1['metrics']['mission_energy_Wh']


def test_jet_reserve_replaces_native_fraction_and_is_held():
    d=v11('jet');d['operations']['operational_reserve']=dict(RES,time_h=.5,divert_km=370)
    n=evaluate_study(d)['rows'][0]['n1']
    assert n['eligible'] is True and n['reserve']['native_replaced'][0]['path']=='aircraft.reserve_fraction'
    w=n['native']['aircraft_result']['weights']
    assert w['reserve_fuel_kg']==0 and n['metrics']['mission_fuel_kg']<w['trip_burn_kg']
    assert n['endurance']['derived_max_on_station_h']>=d['mission']['samples'][0]['on_station_h']-1e-9


def test_thermal_prop_reserve_unassessed_not_doubled():
    d=v11('prop_electric');d['candidates']=d['candidates'][1:2];d['operations']['operational_reserve']=dict(RES)
    r=evaluate_study(d);n=r['rows'][0]['n1']
    assert n['eligible'] is None and 'not separable' in ' '.join(n['issues'])
    assert not r['comparisons'][0]['pareto']


@pytest.mark.parametrize('mutate',[
    lambda d:d['operations'].update(operational_reserve=dict(RES),reserve_h=.1),
    lambda d:d['operations'].update(operational_reserve=dict(RES,native_reserve='keep')),
    lambda d:d['operations'].update(operational_reserve=dict(RES,time_h=-1)),
    lambda d:d['operations'].update(dwell_policy='max'),
    lambda d:d.update(schema_version='1.0') or d['operations'].update(dwell_policy='derived_max'),
    lambda d:d.update(schema_version='1.0') or d['candidates'][0].update(endurance={}),
])
def test_invalid_schema_1_1(mutate):
    d=v11('prop_electric');mutate(d)
    with pytest.raises(ValueError):validate_study(d)


# ---- genuine prop closure and fleet dependency ------------------------------
def test_prop_rubber_closure_is_real_and_verified():
    r=evaluate_study(v11('prop_electric'))
    rows={x['candidate_id']:x['n1'] for x in r['rows']}
    for k in ('elétrico','térmico'):
        n=rows[k];cl=n['closure']
        assert cl['converged'] and cl['history'][-1]['requested_verified'] is True
        assert all(h['design_station_h']>=.25 for h in cl['history'])
        assert n['endurance']['held_noncruise_allowance']['value']>0
        assert n['endurance']['derived_max_on_station_h'] is not None
    assert rows['híbrido-aberto']['eligible'] is None
    assert r['convergence']['kind']=='per_candidate_capability_closure'
    assert 'no fleet→design dependency' in r['convergence']['fleet_feedback']


def test_derived_max_dwell_feeds_energy_charging_and_fleet():
    d=v11('vtol');d['operations']['dwell_policy']='derived_max'
    n=evaluate_study(d)['rows'][0]['n1'];byd=n['operations_by_dwell']
    assert byd['derived_max']['on_station_h']>byd['requested']['on_station_h']
    assert byd['derived_max']['mission_energy_Wh']>byd['requested']['mission_energy_Wh']
    assert byd['derived_max']['fleet_required']<byd['requested']['fleet_required']
    assert n['metrics']['fleet_required']==byd['derived_max']['fleet_required']
    assert any(c['name'].startswith('derived_dwell:') for c in n['checks'])


def test_infeasible_at_zero_station_blocks():
    d=v11('vtol');d['candidates'][0]['recipe']['mass_ledger']['remaining_nonbattery_mass_kg']=23.9
    n=evaluate_study(d)['rows'][0]['n1']
    assert n['endurance']['status']=='infeasible_at_zero_station' and n['eligible'] is False


def test_schema_1_0_output_unchanged_shape():
    r=evaluate_study(spec('vtol'))
    assert r['schema_version']=='1.0' and r['convergence']['kind']=='one_pass_feedback'
    assert 'endurance' not in r['rows'][0]['n1']


def test_examples_cli_mcp_and_registry(tmp_path,monkeypatch):
    from acdt.cli import main
    from acdt.ai.mcp_server import build_server
    from mcp import Client
    monkeypatch.setenv('ACDT_RUNS_DIR',str(tmp_path/'runs'))
    for name in ('iter_vtol','iter_jet'):
        r=mission_fleet_study(ROOT/f'examples/fleet/{name}.yaml')
        assert r['schema_version']=='1.1' and json.loads(Path(r['files']['result']).read_text())==r
        assert r['rows'][0]['n1']['eligible'] is True
    assert main(['fleet','study','--input',str(ROOT/'examples/fleet/iter_vtol.yaml'),'-o',str(tmp_path/'v.json')])==0
    async def call():
        async with Client(build_server()) as c:
            res=await c.call_tool('mission_fleet_study',{'spec':spec('iter_jet'),'record':False})
            assert not res.is_error
            return json.loads(res.content[0].text)
    assert asyncio.run(call())['convergence']['kind']=='per_candidate_capability_closure'
