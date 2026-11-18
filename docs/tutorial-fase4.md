# Tutorial — Fase 4: alta fidelidade (L3), calibração, dimensionamento detalhado

Continua o [tutorial da Fase 3](tutorial-fase3.md). A Fase 4 **verifica** o desenho L1/L2 com
ferramentas de alta fidelidade (não redimensiona) e devolve fatores de calibração rastreáveis:

* geometria OpenVSP (`.vsp3`, STEP em metros, STL, CompGeom, render 3-D);
* SU2 RANS-SA 2-D da secção vs XFOIL, com convergência de malha (GCI, Celik et al. 2008);
* asa 3-D SU2 Euler vs AVL e caso RANS do avião completo (preparados; correm se couberem na máquina);
* caixão da asa em CalculiX (cascas S8R + vigas B32): estática, encurvadura linear, modos;
* flutter com modos FEM + doublet-lattice (PanelAero, p-k) e deck Nastran SOL 145 (pyNastran);
* pesos Classe II de Roskam (Parte V) como verificação cruzada do Raymer;
* dimensionamento detalhado: nervuras (esmagamento de Brazier, Niu), ligação à raiz (Bruhn D1),
  superfícies de comando (Roskam VI) e netlist KiCad do arnês.

Regras: métodos citados no código; nenhum número afinado; um passo sem ferramenta fica marcado
como não corrido, com o motivo.

## 0. Pré-requisitos

* `pip install -e ".[dev,aero,mdo,hifi]"` (pyNastran, PanelAero, scipy, kinparse);
* executáveis `SU2_CFD` (8.5), `ccx` (CalculiX 2.23) e `gmsh` (chamado como processo separado sobre ficheiros `.geo`; a biblioteca Python do Gmsh não é importada), no `PATH` ou numa pasta indicada em
  `ACDT_HIFI_BIN` (por exemplo um ambiente conda-forge com `su2 calculix gmsh`);
* OpenVSP: `ACDT_VSP_PYTHON` aponta para o Python com o módulo `openvsp`.

```bash
export ACDT_HIFI_BIN=/caminho/para/env/bin
export ACDT_VSP_PYTHON=/caminho/para/python-com-openvsp
```

Neste PC, a 18 nov 2026, o Windows continua sem OpenVSP: não há executável e `ACDT_VSP_PYTHON` está vazio. A exportação usou o OpenVSP 3.48.2 que já está no contentor MDO Lab. O visor do VSPAERO não vem nessa imagem. Esse contentor não substitui um instalador no Windows, e não vê o disco do Windows montado: o caso entra por cópia para a pasta partilhada e as saídas voltam à mesma cópia. O processo acdt não importa `openvsp`. O gestor de análises escreve o caso e pára; o binário do solver corre noutro processo, porque o lançamento pelo gestor não regressa.

## 1. Correr

```bash
acdt hifi examples/cessna172_check.yaml -o examples/output/cessna172_check_hifi
acdt hifi examples/uav_endurance_payload.yaml -o examples/output/uav_endurance_payload_hifi \
     --steps geometry,cfd2d,fem,flutter,nastran,detailed,calibration
```

Passos: `geometry, cfd2d, gci, wing_euler, rans_case, fem, flutter, nastran, detailed, calibration`.
Cada passo grava um JSON na sua pasta e é reutilizado na corrida seguinte (`--force` recorre). Assim
um passo longo pode correr uma vez, ou noutra máquina, e o relatório é regenerado.

Saídas: `report_fase4.md` (comparação HiFi vs low-fi e tabela de calibração) e `calibration.json`.
Os ficheiros pesados dos solvers (`*.su2`, `*.frd`, `*.dat`, `*.bdf`, `*.stl`, …) ficam fora do git;
recriam-se com `acdt hifi`.

## 2. Guarda de computação

Antes de correr, cada caso estima RAM e tempo (`hifi/tools.budget`). Se passar 70 % da RAM disponível
ou o limite de tempo, o caso é **escrito** (malha/configuração + comando) mas não corrido, e aparece na
secção 9 do relatório, "Para uma máquina mais potente". Exemplo: o RANS-SA do avião completo
(`rans_case/`) fica com os comandos

```bash
gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2
mpirun -n <N> SU2_CFD aircraft_rans.cfg   # repetir para α = 0, 2, 4 (+ varrimento de perda)
```

A 18 nov 2026 a quarta malha 2-D da secção do C172 (refine = 2, α = 2°, 107922 células) foi corrida.
O CD ficou com deriva 0,42 % nas últimas 10 % das iterações, por isso o GCI fino de 3,0 % não é aceite.
Os α 0° e 4° não foram corridos. O RANS só da asa e da fuselagem estima 1,2×10⁷ células e 22 GB e não
cabe nesta máquina; o caso do avião completo, e o avião com trem e hélice, continuam por correr.
Números em `examples/output/cessna172_check_hifi_win/h5_c172_gci.json`. O `gci/gci.json` de três malhas
não foi reescrito.

## 3. Ler o relatório

* **Secção 2 (SU2 vs XFOIL):** o RANS é totalmente turbulento (SA) e o XFOIL tem transição; parte da
  diferença em cd é física. Perto da perda, RANS estacionário tem ±10 % em cl_max.
* **Secção 5 (FEM vs viga da Fase 3):** flecha, torção, λ de encurvadura (a Fase 3 dimensiona para
  λ = 1 à carga última) e frequências.
* **Secção 6 (flutter):** V_F com g = 0 e g = 0,03 contra 1,2 V_D EAS; compara com a estimativa de
  faixas da Fase 3.
* **Secção 8 (calibração):** cada fator é a razão (ou diferença) alta/baixa fidelidade do mesmo desenho.

## 4. Aplicar a calibração

Opt-in, por grupo, no YAML da missão:

```yaml
assumptions:
  calibration:
    apply: [aero, flutter]
    file: examples/output/uav_endurance_payload_hifi/calibration.json
```

Os métodos L1/L2 não mudam; os fatores são aplicados aos resultados e o relatório L1/L2 mostra quais
foram aplicados e de onde vêm. Os fatores de estruturas são só reportados.

## 5. Otimização com restrições de qualidades de voo e aeroelasticidade

Opcional, desligado por omissão:

```yaml
assumptions:
  mdo:
    hq_aeroel_constraints: true
```

As margens de divergência, inversão e flutter entram como restrições g = 1 − V/(1,2 V_D) ≤ 0 (modelo
de faixas da Fase 3, calibrado pelo `k_flutter` da Fase 4 se `calibration.apply` incluir `flutter`).
As verificações `hq:` (MIL-F-8785C, scissor) e `aeroel:` entram no filtro de aceitação: um passo que
crie uma falha nova é rejeitado. Os níveis de qualidades de voo são discretos, por isso funcionam como
filtro e não como penalidade suave.

## 6. Limitações

* GCI e Euler 3-D só correm se pedidos e se couberem na máquina; o RANS do avião completo fica preparado. O RANS só da asa e da fuselagem do C172 foi estimado a 18 nov 2026 (22 GB) e não correu.
* O deck Nastran SOL 145 é relido com pyNastran, mas não é corrido (sem MSC/NX Nastran).
* C_h das superfícies de comando e V_H ≈ 1,1 V_C são pressupostos.
* Roskam Classe II fora da base estatística (UAV de 25 kg) é só indicativo; as Eqs. 5.12–5.13
  (Cessna, empenagem) são mostradas mas excluídas por darem valores implausíveis.
* OpenFOAM é stub.
