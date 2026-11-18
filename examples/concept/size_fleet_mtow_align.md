# size_fleet ↔ acdt size MTOW alignment

**Before (bug):** `size_fleet` defaulted to `level=L0`, which overwrote `aero.fidelity: lowfi` in the
mission YAML. `acdt size` keeps the YAML fidelity. Same file → different MTOW (silent).

| mission | W0 YAML / acdt size | W0 size_fleet old default (L0) | Δ |
|---|---|---|---|
| `examples/uav_gasoline_150kg.yaml` | 136.34 kg | 141.13 kg | **+4.79 kg** |
| `examples/concept/illegal_fishing/variant_L.yaml` | 120.39 kg | 127.87 kg | **+7.48 kg** |

**After:** omit `level` → same pipeline and fidelity as `acdt size`. Pass `level=L0|L1` only to force
handbook/lowfi; the result then carries `mtow_alignment` explaining the scope. Opt-in: feed a prior
`run_id` from `acdt size` / `toolkit.size`.

```bash
python - <<'PY'
from acdt.ai import concept as C
print(C.compare_size_fleet_mtow("examples/concept/illegal_fishing/variant_L.yaml"))
print(C.compare_size_fleet_mtow("examples/concept/illegal_fishing/variant_L.yaml", level="L0"))
PY
```

Radar electrical power in fuel burn remains a separate Nansei open point (HANDOFF); not invented here.
