"""Fase 8 — controlo e simulação de voo de baixa fidelidade.

* :mod:`.controls` — dimensionamento das superfícies de controlo por requisitos de desempenho
  (rolamento, rotação na descolagem, compensação, vento cruzado, OEI) e momentos de charneira (AVL HM).
* :mod:`.aeromodel` — modelo aerodinâmico/propulsivo/inercial para 6-DOF (tabelas AVL α × flap).
* :mod:`.sixdof` — integrador 6-DOF próprio (terra plana, quaterniões) com trim e solo.
* :mod:`.jsbsim_export` / :mod:`.jsbsim_runner` — exportação para JSBSim (LGPL, processo separado).
* :mod:`.autopilot`, :mod:`.wind`, :mod:`.mission` — piloto automático clássico, Dryden/rajadas e missão YAML.
* :mod:`.pointmass` — o mesmo YAML em massa pontual (3-DOF, Anderson 1999 / Raymer 2018), com sensor e falhas.
* :mod:`.study` — encadeia superfícies → modelo de voo → missão → JSBSim (usado por ``acdt controls``,
  ``acdt simulate`` e pelas ferramentas MCP ``size_control_surfaces`` / ``simulate_mission``).
"""
