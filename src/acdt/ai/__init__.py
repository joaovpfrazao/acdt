"""AI-native layer of acdt (Model Context Protocol server + the plain-Python toolkit it exposes).

* :mod:`acdt.ai.toolkit`   — the tool functions (pure Python, JSON-serialisable in/out); usable without MCP.
* :mod:`acdt.ai.registry`  — run registry / provenance under ``runs/`` (inputs, assumptions, versions, git hash,
  outputs, calibration, external data).
* :mod:`acdt.ai.external`  — validation of externally researched material/component data (units, plausibility
  ranges, mandatory source URL + date).
* :mod:`acdt.ai.guard`     — compute guard for the high-fidelity steps (cost estimate, explicit user approval).
* :mod:`acdt.ai.jobs`      — async job pattern for long runs (start → job id → status/result).
* :mod:`acdt.ai.catalogue` — methods catalogue (from the module docstrings), reference data, docs.
* :mod:`acdt.ai.mcp_server`— MCP registration (needs the optional ``mcp`` package: ``pip install 'acdt[ai]'``).
"""
