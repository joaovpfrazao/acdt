# Melhorias futuras (registadas, ainda não aprovadas)

Ideias discutidas com o João e deixadas **em espera**. Nada aqui é para implementar sem aprovação explícita.
Cada entrada diz o que existe hoje, o que faltaria e quando poderá fazer sentido.

## 1. Forma defletida da asa em voo (1g) — discutido a 10 nov 2026

**Hoje**: com `assumptions.structures.flex: true`, o `size` itera a torção elástica de cruzeiro (1g, W0) com a
linha sustentadora de Glauert e passa-a ao AVL como incidência de secção (`ainc`). A flecha de flexão é calculada
e reportada em `structures.deflections`, mas não deforma a geometria (ver `docs/structures-l1.md`).

**Faltaria**:
* flecha a 1g no AVL como deslocamento vertical das secções (diedro efetivo), com aviso quando o diedro
  efetivo passar de ~1°;
* exportar a forma em voo (torção + flecha) para CFD;
* forma de fabrico (*jig*) = forma em voo − deformação a 1g.

**Quando faz sentido**: asas esbeltas e flexíveis (UAV de grande alongamento em carbono), onde o diedro efetivo
mexe no efeito diedro e no rolamento holandês. Para asas rígidas (C172) o ganho é pequeno. A torção, que é o
efeito dominante na carga e no arrasto induzido, já está no ciclo. CFD e *jig* ficam para a alta fidelidade.

## 2. Laminados por componente e acoplamento flexão–torção (aeroelastic tailoring) — discutido a 10 nov 2026

**Hoje**: os compósitos são isotrópicos equivalentes (CLT, Jones) com cut-offs de deformação; o ortotrópico
completo só na alta fidelidade. A posição das longarinas é a única alavanca aeroelástica na Fase 5.

**Faltaria**:
* ficha de laminado própria por componente (banzos ~0°, almas e pele ±45°, pele sanduíche);
* termo de acoplamento flexão–torção EK na viga e na aeroelasticidade de faixas, com a orientação das fibras
  como variável (Weisshaar; Shirk, Hertz & Weisshaar 1986).

**Quando faz sentido**: asa e estrutura interna em carbono, quando for preciso ganhar margem de divergência ou
flutter sem massa. Ambos são leves (correm no box).
