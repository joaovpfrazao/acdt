<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Camber flap — trim drag & gap (opt-in)

```bash
PYTHONPATH=src python examples/camber/trim_gap_demo.py
```

```yaml
assumptions:
  aero:
    camber_flap:
      kind: camber
      trim_drag: true          # HT induced CD from Δcm0(δ*) — Nelson/Etkin
      gap:
        # pick one:
        sealed: true
        source: "XFOIL GDES/FLAP sealed-gap assumption"
        # or: {dCD: 0.001, source: "DATCOM/test — dated"}
        # chord_ratio alone → unassessed (no invented correlation)
```

Default omits trim/gap (legacy two-point envelope polar unchanged).
