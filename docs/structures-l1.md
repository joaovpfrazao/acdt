# Estruturas L1 — viga da aeronave e torção no ciclo de `size`

A asa continua a ser o caixão de `structures.py` (Megson, Bruhn, Bredt–Batho). Este nível acrescenta a fuselagem, as empenagens e a torção elástica de cruzeiro, e devolve massas e deflexões no `result.json`. O código está em `src/acdt/core/structures/` (núcleo numérico, sem importar `domains`) e em `src/acdt/domains/aircraft/structures_l1.py` (a aeronave).

`BoxFEM` é o FEM de cascas já existente (`core/fem`, QM6+MITC4). Não foi movido. `k_EI` e `k_GJ` multiplicam EI e GJ da asa quando o grupo `structures` está em `assumptions.calibration.apply`. Os fatores de tensão e de encurvadura continuam só de diagnóstico. A fuselagem não os usa.

## O que entra no ciclo

Por omissão `assumptions.structures.flex` e `mass_in_loop` são `false` (o alias `assumptions.aero.elastic` liga a torção). Com os dois desligados, W0, a polar, o ponto neutro e as verificações ficam no caminho rígido. O resultado traz na mesma `structures.masses` e `structures.deflections`.

Com `flex: true`, cada iteração do MDA reconstrói a polar rígida e multiplica K uma vez por CDi_flex/CDi_rígido, antes da energia elétrica e da linha de histórico. O ciclo pára também quando a torção de ponta muda menos de 0,02°. O CLα de manual não é substituído. `aero.elastic_correction.applied` fica verdadeiro só neste caso. A estabilidade usa o CLα flexível e o x_ac da asa só quando `applied` é verdadeiro. O ficheiro AVL recebe essa torção como incidência de secção (`ainc`, positivo nariz para cima) nas três secções da asa.

Com `mass_in_loop: true`, as massas da fuselagem e das empenagens no somatório de componentes passam a ser as da viga. A asa continua no método escolhido (`raymer` ou `box`).

Depois do estágio de estabilidade, a viga é recalculada na estação real da asa (ápice + quarto da corda média) e com o trem resolvido. Essa passagem não mexe na polar, no W0 nem nas verificações. Dentro do MDA a estação é 0,35 L; a nota do resultado diz qual das duas foi usada.

## O que é citado e o que é pressuposto

Citado, com a equação no docstring do código:

- Casca circular: tensão clássica 0,605 E t/R (Timoshenko e Gere, ν = 0,3) com o knockdown γ de NASA SP-8007 (1968). Em CFRP o mesmo γ é um knockdown conservativo, não um ensaio do laminado.
- Tubo fino: A = 2πRt, I = πR³t, J = 2πR³t; longarinas ideais I = n A_b R²/2 (Megson).
- Viga em consola integrada pela regra dos trapézios, encastrada a meio diâmetro da fuselagem.
- Carga da cauda atingível: Raymer Eq. 12.15. Equilíbrio e o incremento de 23.423(b). Aterragem: 14 CFR 23.473 através dos fatores já adoptados no trem.
- Linha sustentadora de Glauert (Anderson §5.3), a₀ = 0,95·2π (Raymer §12.4.1), o mesmo ponto fixo da Fase 5. Sem NeuralFoil neste caminho.
- Massa de referência da fuselagem: Raymer Eq. 15.49, a regressão de avião ligeiro metálico. Não se lhe aplica fator de compósito dentro da viga.

Pressuposto, dito nas notas do resultado:

- Perfil equivalente de raio, passo de cavernas, piso, duas anteparas à espessura mínima, área mínima de longarina.
- c_lmax de secção 1,0 no estabilizador e 0,8 na deriva. Carga uniforme em envergadura (M_raiz = L b/8).
- Raio de giração em arfagem 0,25 L para o incremento de 23.423. Centro de pressões da deriva a 0,40 da altura.
- Inércia de aterragem uniforme em [0, 2 x_cg].
- 14 CFR 23.427 (rajada) e 23.441 (leme) não entram. A torção assimétrica do estabilizador também não.
- A casca é um monocoque não reforçado mais longarinas mínimas: um pouco mais pesada do que um semi-monocoque verdadeiro. A equação de Raymer inclui portas, janelas e suportes que esta viga não tem.

O CG estrutural é reportado. As estações Roskam do peso e centragem não se movem.

## Critérios de aceitação

- Massa da fuselagem entre 75 % e 125 % de Raymer Eq. 15.49 no avião de referência (asa de 16,2 m², fuselagem de 8 m, W0 = 1150 kg, alumínio) e no Cessna 172 de exemplo. Fora da banda o resultado leva um aviso, não uma verificação que reprove o avião.
- Flecha e torção de uma caixa rectangular esbelta dentro de ±30 % do BoxFEM. Não é uma comparação com o CalculiX nem com a asa do avião.
- Com `flex: true`, K e a torção de ponta variam de forma monótona com k_GJ, e o ciclo de manual do C172 converge com |ΔW0|/W0 < 0,1 % e torção estável.

## O que isto não é

Não é o acoplamento OpenAeroStruct (esse continua no L2, fora do ciclo de `size`). Não há pressurização, fadiga nem não-linearidade geométrica. A divergência (|θ_ponta| > 25° ou CDi não finito) deixa K por aplicar.
