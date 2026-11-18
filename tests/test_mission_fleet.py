# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Hand fleet/charge identities and actual N1 model feedback, no requested-endurance proof."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import pytest
from acdt.ai.jet import load_spec
from acdt.ai.mission_fleet import mission_fleet_study
from acdt.core.concept.fleet_feedback import fleet,turnaround
from acdt.domains.aircraft.mission_fleet import evaluate_study,validate_study

ROOT=Path(__file__).resolve().parents[1]
P='PRESSUPOSTO unit test'


def spec(name='prop_electric'):
    return deepcopy(load_spec(ROOT/f'examples/fleet/{name}.yaml'))


def settings(**over):
    return dict(availability=1.,n_stations=1,handoff_overlap_h=0.,reserve_h=0.,source=P,**over)


def test_fleet_rounding_hand_case_and_availability():
    # Ha cycle: 5.5 h station, 2 h transit, 4 h ground => ceil(11.5/5.5)=3.
    s=settings();r=fleet(5.5,2,4,s)
    assert r['cycle']['aircraft_per_station']==3 and r['fleet_expected']==3
    s['availability']=.8;s['n_stations']=2
    assert fleet(5.5,2,4,s)['fleet_expected']==8 # ceil(6/.8)
    s['availability']={'mtbf_h':80,'mttr_h':20}
    assert fleet(5.5,2,4,s)['fleet_expected']==8
    assert fleet(1,0,0,settings())['fleet_expected']==1
    assert fleet(1,1,0,settings())['fleet_expected']==2
    assert fleet(1,1+1e-8,0,settings())['fleet_expected']==3


@pytest.mark.parametrize('station,overlap',[(0,0),(.1,.1),(.1,.2)])
def test_no_effective_station(station,overlap):
    s=settings();s['handoff_overlap_h']=overlap
    r=fleet(station,1,1,s)
    assert not r['cycle']['feasible'] and r['fleet_expected'] is None


def test_confidence_limit_never_falls_back_to_mean_fleet():
    s=settings();s.update(confidence=.99,availability=.001)
    r=fleet(1,1,1,s)
    assert r['fleet_expected']==3000 and r['fleet_for_confidence'] is None
    s['confidence']=1
    with pytest.raises(ValueError):fleet(0,1,1,s)
    d=spec();d['candidates']=d['candidates'][1:2];d['operations'].update(availability=.001,confidence=.99)
    r=evaluate_study(d)['rows'][0]['n1']
    assert r['eligible'] is None and r['metrics']['fleet_required'] is None


def test_charge_identity_efficiency_serial_parallel_and_dedicated_allocation():
    s=dict(method='charge',average_input_W=100,efficiency=.8,allocation='dedicated_per_aircraft',fixed_h=.5,combine='serial',source=P)
    r=turnaround(s,160)
    assert r['charge_h']==2 and r['duration_h']==2.5 and r['grid_Wh']==200
    s['combine']='parallel';assert turnaround(s,160)['duration_h']==2
    s['allocation']='shared';assert turnaround(s,160)['assessed'] is False
    s['allocation']='dedicated_per_aircraft'
    assert not turnaround(s,None)['assessed']
    assert not turnaround(s,160,has_fuel=True)['assessed']
    assert not turnaround(s,160,multiple_packs=True)['assessed']
    assert turnaround(dict(method='supplied',duration_h=.3,activity='fuel/swap/service total',source=P))['duration_h']==.3


def test_real_electric_thermal_feedback_and_hybrid_retained():
    r=evaluate_study(spec());rows={x['candidate_id']:x for x in r['rows']}
    e,t,h=[rows[k] for k in ('elétrico','térmico','híbrido-aberto')]
    for row in (e,t):
        n=row['n1'];assert n['eligible'] is True
        assert n['native']['mass_coupled'] and n['native']['energy_coupled']
        assert n['native']['aircraft_result']['mission_pointmass']['aborted'] is None
        assert len(n['history'])==3
        assert row['feedback']['N1_fixed_mission_fleet']>row['feedback']['n0_bounds'][0]
    assert e['n1']['metrics']['mission_energy_Wh']>0 and t['n1']['metrics']['mission_fuel_kg']>0
    assert e['n1']['turnaround']['battery_terminal_Wh']==e['n1']['metrics']['mission_energy_Wh']
    assert e['n1']['turnaround']['required_dedicated_chargers']==e['n1']['metrics']['fleet_required']
    assert h['n1']['eligible'] is None and h['n0']['corners']
    assert all('híbrido-aberto' not in c['pareto'] for c in r['comparisons'])
    assert r['convergence']['converged'] is None and 'ranking' not in r['comparisons'][0]


def test_hotel_load_and_charger_power_change_actual_mission_and_fleet():
    d=spec();d['candidates']=d['candidates'][:1]
    base=evaluate_study(d)['rows'][0]['n1']
    d['candidates'][0]['recipe']['onboard']['loads'][0].update(power_W=300,peak_W=400)
    changed=evaluate_study(d)['rows'][0]['n1']
    assert changed['eligible'] is True
    assert changed['metrics']['mission_energy_Wh']>base['metrics']['mission_energy_Wh']
    assert changed['metrics']['fleet_required']>base['metrics']['fleet_required']
    d=spec();d['candidates']=d['candidates'][:1]
    d['candidates'][0]['turnaround']['average_input_W']=1000
    faster=evaluate_study(d)['rows'][0]['n1']
    assert faster['metrics']['mission_energy_Wh']==pytest.approx(base['metrics']['mission_energy_Wh'])
    assert faster['metrics']['fleet_required']<base['metrics']['fleet_required']


def test_capacity_unknown_and_missing_extraction_cannot_enter_frontier():
    d=spec();d['candidates']=d['candidates'][:2]
    d['candidates'][0].pop('pack_power')
    d['candidates'][1]['recipe']['onboard']['sources'][0].pop('generator_efficiency')
    r=evaluate_study(d)
    assert all(x['n1']['eligible'] is None for x in r['rows'])
    assert not r['comparisons'][0]['pareto']
    assert r['rows'][1]['n1']['native']['aircraft_result'] is None


def test_low_pack_rating_fails_not_unknown_pass():
    d=spec();d['candidates']=d['candidates'][:1]
    d['candidates'][0]['pack_power'].update(continuous_C=.001,peak_C=.001)
    n=evaluate_study(d)['rows'][0]['n1']
    assert n['eligible'] is False and not n['pack_power_checks'][0]['passed']


def test_declared_uncertainty_and_multiple_nondominated_candidates_retained():
    d=spec();c=deepcopy(d['candidates'][1]);c['id']='térmico-mais-pesado-serviço-rápido'
    c['turnaround']['duration_h']=0
    c['recipe']['onboard']['items'][1]['mass_kg']=30
    d['candidates']=[d['candidates'][1],c]
    r=evaluate_study(d)
    assert len(r['rows'])==2 and set(r['comparisons'][0]['pareto'])=={x['id'] for x in d['candidates']}
    assert all(row['source']==d['source'] for row in r['rows'])


@pytest.mark.parametrize('kind',['jet','vtol'])
def test_native_jet_and_vtol_link_without_claiming_dynamic_simulator(kind):
    r=evaluate_study(spec(kind));n=r['rows'][0]['n1']
    assert n['eligible'] is True and n['metrics']['fleet_required']>0
    assert n['native']['aircraft_result']
    assert n['metrics']['mission_fuel_kg']>0 if kind=='jet' else n['metrics']['mission_energy_Wh']>0
    assert 'mission_pointmass' not in n['native']['aircraft_result']
    if kind=='vtol':assert n['native']['aircraft_result']['mass_kg']==25


def test_fixed_requested_mission_not_max_endurance_and_native_failure_blocks():
    d=spec();d['candidates']=d['candidates'][:1]
    a=evaluate_study(d)
    assert a['rows'][0]['n1']['operations']['on_station_h']==.25
    assert a['rows'][0]['n1']['operations']['flight_duration_h']==pytest.approx(.25+20_000/30/3600)
    d['candidates'][0]['recipe']['aircraft']['assumptions']['weights']['fixed_fraction']=.9999
    n=evaluate_study(d)['rows'][0]['n1']
    assert n['eligible'] is not True


def test_n0_geometry_free_missing_n1_and_transit_infeasible_corner_retained():
    d=spec();d['candidates']=d['candidates'][:1];d['candidates'][0].pop('recipe')
    d['candidates'][0]['n0']['endurance_h']=[0,.1]
    r=evaluate_study(d)['rows'][0]
    assert r['n0']['fleet_required_bounds'] is None
    assert r['n0']['corners'][0]['available_on_station_h']<0
    assert r['n1']['eligible'] is None and r['n1']['native'] is None


def test_reserve_time_not_equated_to_native_energy_fraction():
    d=spec();d['operations']['reserve_h']=.1;d['candidates']=d['candidates'][:1]
    r=evaluate_study(d)
    assert r['rows'][0]['n1']['eligible'] is None and not r['comparisons'][0]['pareto']


@pytest.mark.parametrize('mutation',[
    lambda d:d['mission']['samples'][0].update(speed_m_s=float('nan')),
    lambda d:d['mission']['samples'][0].update(payload_kg=-1),
    lambda d:d['mission']['envelope'].update(speed_m_s=[50,20]),
    lambda d:d['candidates'].append(deepcopy(d['candidates'][0])),
    lambda d:d['mission']['samples'].append(deepcopy(d['mission']['samples'][0])),
    lambda d:d['operations'].update(availability=0),
    lambda d:d['operations'].update(n_stations=1.5),
    lambda d:d['operations'].update(confidence=1.1),
    lambda d:d.update(objectives={}),
    lambda d:d.update(schema_version='2.0'),
])
def test_invalid_study(mutation):
    d=spec();mutation(d)
    with pytest.raises(ValueError):validate_study(d)


def test_stable_replay_json_registry_cli_and_mcp(tmp_path,monkeypatch):
    from acdt.cli import main
    from acdt.ai.mcp_server import build_server
    from mcp import Client
    monkeypatch.setenv('ACDT_RUNS_DIR',str(tmp_path/'runs'))
    s=ROOT/'examples/fleet/jet.yaml'
    a=mission_fleet_study(s,False);b=mission_fleet_study(s,False)
    assert a==b
    r=mission_fleet_study(s)
    assert json.loads(Path(r['files']['result']).read_text())==r
    assert main(['fleet','study','--input',str(s),'-o',str(tmp_path/'cli.json')])==0
    assert main(['fleet','study','--input',str(ROOT/'examples/fleet/prop_electric.yaml'),'-o',str(tmp_path/'partial.json')])==1
    async def call():
        async with Client(build_server()) as c:
            result=await c.call_tool('mission_fleet_study',{'spec':spec('vtol'),'record':False})
            assert not result.is_error
            return json.loads(result.content[0].text)
    assert asyncio.run(call())['rows'][0]['n1']['eligible'] is True


def test_overlap_consumes_full_flown_cycle_and_availability_rounds_conservatively():
    s=settings();s['handoff_overlap_h']=.4
    # Full cycle 1+.4=1.4 h; replacement every 1-.4=.6 h => ceil=3.
    assert fleet(1,.4,0,s)['cycle']['aircraft_per_station']==3
    s=settings();s['availability']=1-1e-10
    assert fleet(1,0,0,s)['fleet_expected']==2


def test_payload_change_affects_actual_native_mass():
    d=spec();d['candidates']=d['candidates'][1:2]
    a=evaluate_study(d)['rows'][0]['n1']
    d['mission']['envelope']['payload_kg'][1]=12
    d['mission']['samples'][0]['payload_kg']=12
    b=evaluate_study(d)['rows'][0]['n1']
    assert b['eligible'] is True
    assert b['metrics']['fleet_mtow_kg']/b['metrics']['fleet_required']>a['metrics']['fleet_mtow_kg']/a['metrics']['fleet_required']


def test_requested_missing_spatial_constraint_blocks_assessed_frontier():
    d=spec();d['candidates']=d['candidates'][:1]
    d['candidates'][0]['recipe']['onboard']['constraints']={'available_volume_m3':1}
    n=evaluate_study(d)['rows'][0]['n1']
    assert n['eligible'] is not True


def test_comparison_partitioned_by_actual_model_phase_coverage(monkeypatch):
    import acdt.domains.aircraft.mission_fleet as module
    d=spec();d['candidates']=d['candidates'][:2]
    # Structural comparison test with canned adapter results; real native adapter
    # execution is exercised independently above, at its applicable mission speed.
    def native(c,s,o):
        coverage='airborne_level_pointmass' if c['id']=='elétrico' else 'native_VTOL_segments'
        return dict(eligible=True,status='assessed_in_scope',coverage_class=coverage,
                    issues=[],metrics=dict(fleet_required=4,fleet_mtow_kg=80))
    monkeypatch.setattr(module,'_n1',native)
    r=module.evaluate_study(d)
    assert len(r['comparisons'])==2
    assert all(len(comp['pareto'])==1 for comp in r['comparisons'])
    assert {comp['coverage_class'] for comp in r['comparisons']}=={'airborne_level_pointmass','native_VTOL_segments'}


@pytest.mark.parametrize('recipe',[42,[],None])
def test_invalid_recipe_types_fail_clearly(recipe):
    d=spec();d['candidates'][0]['recipe']=recipe
    with pytest.raises(ValueError):mission_fleet_study(d,False)


def test_missing_objective_not_a_zero_or_false_winner():
    d=spec();d['candidates']=d['candidates'][:2];d['objectives']={'mission_fuel_kg':'min'}
    r=evaluate_study(d)
    assert 'elétrico' not in r['comparisons'][0]['pareto']
    assert r['comparisons'][0]['rows'][0]['missing']==['mission_fuel_kg']



def test_decimal_cycle_identity_no_spurious_extra_aircraft_and_positive_confidence():
    assert fleet(.1,.2,0,settings())['fleet_expected']==3
    s=settings();s.update(availability=.8,confidence=.95)
    # Need 3 simultaneous cycle aircraft: P(Bin(5,.8)>=3)=.94208,
    # P(Bin(6,.8)>=3)=.98304, so confidence requires six, not mean four.
    assert fleet(1,1,1,s)['fleet_for_confidence']==6



def test_fixed_dwell_baseline_separates_schedule_change_from_native_feedback():
    r=evaluate_study(spec());rows={x['candidate_id']:x for x in r['rows']}
    for c in ('elétrico','térmico'):
        assert rows[c]['n0']['fleet_required_bounds']==[3,3]
        assert rows[c]['n0']['fixed_mission_fleet_required_bounds']==[4,4]
    # electric We/W0 from Raymer Table 3.1 'uav_small' (statistical method): the N1 feedback adds 6 aircraft
    assert rows['elétrico']['feedback']['delta_from_fixed_mission_bounds']==[6,6]
    assert rows['térmico']['feedback']['delta_from_fixed_mission_bounds']==[0,0]
