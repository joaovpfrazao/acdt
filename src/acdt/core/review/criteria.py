# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Critérios de entrada e de sucesso das revisões de projeto, declarados como dados.

Fonte: NASA, *NPR 7123.1D — NASA Systems Engineering Processes and Requirements* (em vigor desde 5 jul 2023, com a
Alteração 2), Apêndice G "Life-Cycle and Technical Review Entrance and Success Criteria": Tabela G-4 (SRR de
projetos), Tabela G-5 (MDR/SDR de projetos), Tabela G-6 (PDR), Tabela G-7 (CDR), Tabela G-8 (PRR) e Tabela G-10
(TRR). https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixG

O próprio apêndice diz que os critérios são "recommended best practices" e que "Tailoring and customizing are
expected" (G.1.2). Cada critério abaixo cita o texto da tabela (excerto literal, em inglês) e diz se o acdt o avalia
automaticamente (``check``) a partir dos registos (estado de projeto, matriz de verificação, proveniência, UQ, MDO,
V&V, calibração) ou se fica para a revisão humana (``check: None``). PRESSUPOSTO: a correspondência entre o texto da
NPR e o teste automático (``interpretacao``) é uma interpretação do acdt, não da NASA; um critério automático
cumprido mostra só que a evidência registada o suporta, nunca substitui a decisão do painel de revisão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

STANDARD: dict[str, str] = {
    "id": "NPR 7123.1D",
    "title": "NASA Systems Engineering Processes and Requirements (Change 2), Appendix G — Life-Cycle and "
             "Technical Review Entrance and Success Criteria",
    "effective": "2023-07-05",
    "url": "https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixG",
    "tailoring": "G.1.2: \"Tailoring and customizing are expected for projects and programs.\"",
}

GATES: dict[str, dict[str, str]] = {
    "SRR": {"title": "System Requirements Review", "table": "Tabela G-4 (SRR, projetos)", "section": "G.5",
            "purpose": "The SRR evaluates whether the functional and performance requirements defined for the system "
                       "of interest are responsive to the program's requirements and ensures the preliminary project "
                       "plan and requirements will satisfy the mission."},
    "PDR": {"title": "Preliminary Design Review", "table": "Tabela G-6 (PDR)", "section": "G.7",
            "purpose": "The PDR demonstrates that the preliminary design meets all system of interest requirements "
                       "with acceptable risk and within the cost and schedule constraints and establishes the basis "
                       "for proceeding with detailed design."},
    "CDR": {"title": "Critical Design Review", "table": "Tabela G-7 (CDR)", "section": "G.8",
            "purpose": "The CDR demonstrates that the maturity of the design is appropriate to support proceeding "
                       "with full-scale fabrication, assembly, integration, and test."},
    "MDR": {"title": "Mission Definition Review", "table": "Tabela G-5 (MDR/SDR, projetos)", "section": "G.6",
            "purpose": "The MDR/SDR evaluates whether the proposed mission/system architecture is responsive to the "
                       "program mission/system functional and performance requirements and whether requirements have "
                       "been allocated to the next lower product layer and to all functional elements of the "
                       "mission/system.  This table is to be used for projects and single-project programs."},
    "TRR": {"title": "Test Readiness Review", "table": "Tabela G-10 (TRR)", "section": "G.11",
            "purpose": "A TRR for each planned test or series of tests ensures that the test article "
                       "(hardware/software), test facility, support personnel, and test procedures are ready for "
                       "testing and data acquisition, reduction, and control."},
    "PRR": {"title": "Production Readiness Review", "table": "Tabela G-8 (PRR)", "section": "G.9",
            "purpose": "For projects developing or acquiring multiple systems/units (typically greater than three "
                       "or as determined by the project).  The PRR determines the readiness of the system developers "
                       "to efficiently produce the required number of systems.  It ensures that the production "
                       "plans, fabrication, assembly, integration enabling products, operational support, and "
                       "personnel are in place and ready to begin production."},
}

#: Nível de fidelidade mínimo das disciplinas primárias por revisão (escada L0…L3 de CAPABILITIES.md).
#: PRESSUPOSTO do acdt (a NPR não fala em níveis de fidelidade): SRR = L0 (manual), PDR = L1 (baixa fidelidade
#: física), CDR = L2. MDR, TRR e PRR ficam em L0: a norma não pede L2, e exigir L2 reprovaria a revisão por um
#: motivo que ela não escreve. Estes três níveis não usam o avaliador ``fidelidade_disciplinas``. Ajustável por
#: projeto (``required_level`` no ficheiro de critérios).
DEFAULT_REQUIRED_LEVEL: dict[str, str] = {"SRR": "L0", "PDR": "L1", "CDR": "L2", "MDR": "L0", "TRR": "L0",
                                           "PRR": "L0"}

#: Estados de um critério.
CRITERION_STATUSES = ("cumpre", "nao_cumpre", "insuficiente", "revisao_humana", "dispensado")
#: Veredito da revisão (só sobre os critérios automáticos declarados).
VERDICTS = ("pronto", "nao_pronto", "insuficiente")


@dataclass(frozen=True)
class Criterion:
    id: str
    gate: str
    phase: str                      # "entrada" | "sucesso"
    quote: str                      # excerto literal da tabela da NPR
    check: str | None               # avaliador automático (evaluate.CHECKS) ou None = revisão humana
    interpretacao: str = ""         # como o acdt lê o critério (PRESSUPOSTO de interpretação)
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{STANDARD['id']} {GATES[self.gate]['table']}, critério de {self.phase}"


def _c(gate: str, n: int, phase: str, quote: str, check: str | None = None, interp: str = "",
       **params: Any) -> Criterion:
    return Criterion(f"{gate}-{phase[0].upper()}{n:02d}", gate, phase, quote, check, interp, params)


_HUMAN = "fora do âmbito dos registos do acdt: decide o painel de revisão"

CRITERIA: dict[str, tuple[Criterion, ...]] = {
    "SRR": (
        _c("SRR", 1, "entrada", "Requirements for system being reviewed are ready to be baselined after the review",
           "requisitos_definidos", "há requisitos rastreáveis na matriz de verificação (acdt.verification/1)"),
        _c("SRR", 2, "entrada", "Preliminary verification and validation method identified for each requirement.",
           "metodo_por_requisito", "cada linha da matriz tem método de verificação declarado"),
        _c("SRR", 3, "sucesso", "The project utilizes a sound process for the allocation and control of "
           "requirements throughout all levels", "arvore_requisitos",
           "a árvore de requisitos não tem problemas (tree_issues vazio) e cada requisito tem fonte"),
        _c("SRR", 4, "sucesso", "The functional and performance requirements defined for the system are responsive "
           "to the stakeholder needs and parent requirements, reflect the system's intended operational use, and "
           "represent capabilities likely to be achieved within the scope of the project.", "conceito_viavel",
           "existe um dimensionamento registado e é viável (grandeza 'feasible')"),
        _c("SRR", 5, "sucesso", "Preliminary approaches have been determined for how requirements will be verified "
           "and validated.", "metodo_por_requisito",
           "cada linha da matriz tem método de verificação declarado"),
        _c("SRR", 6, "sucesso", "Major risks have been identified and technically assessed, and viable mitigation "
           "strategies have been defined.", None, _HUMAN + " (a lista de itens em aberto deste relatório é uma "
           "entrada para essa avaliação)"),
        _c("SRR", 7, "sucesso", "TBD and TBR items are clearly identified with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
        _c("SRR", 8, "entrada", "A preliminary SRR agenda, success criteria, and instructions to the review board "
           "have been agreed to", None, _HUMAN),
        _c("SRR", 9, "entrada", "Updated cost and schedule estimates for the project implementation.", None, _HUMAN),
    ),
    "PDR": (
        _c("PDR", 1, "entrada", "A preliminary design that can be shown to meet all technical requirements and "
           "performance measures or has waivers.", "requisitos_cumpridos",
           "nenhum requisito em falha (salvo dispensa declarada); nao_avaliado/desconhecido → insuficiente"),
        _c("PDR", 2, "entrada", "Baselined Verification and Validation Plan", "avaliador_por_requisito",
           "cada requisito tem avaliador declarado e registado (requisitos_sem_avaliador vazio)"),
        _c("PDR", 3, "sucesso", "The flow down of verifiable requirements is complete and proper, or, if not, an "
           "adequate plan exists for timely resolution of open items. Requirements are traceable to parent technical "
           "requirements and to mission goals and objectives.", "arvore_requisitos",
           "a árvore de requisitos não tem problemas (tree_issues vazio) e cada requisito tem fonte"),
        _c("PDR", 4, "sucesso", "The preliminary design is expected to meet the requirements at an acceptable level "
           "of risk.", "incerteza_requisitos",
           "existe estudo de incerteza (acdt.uq/1) e nenhum requisito fica em prob_falha; inconclusivo → insuficiente"),
        _c("PDR", 5, "sucesso", "Adequate technical and programmatic margins (e.g., mass, power, memory) and "
           "resources exist to complete the development within budget, schedule, and known risks.", "margens",
           "nenhum requisito avaliado fica no_limite (margem dentro da tolerância)"),
        _c("PDR", 6, "sucesso", "Preliminary analysis of the primary subsystems has been completed and summarized, "
           "highlighting performance and design margin challenges.", "fidelidade_disciplinas",
           "as disciplinas primárias têm resultados registados no nível exigido para a revisão"),
        _c("PDR", 7, "sucesso", "Appropriate modeling and analytical results are available and have been considered "
           "in the design.", "vv_modelos",
           "existe relatório de V&V (acdt.vv/1) sem casos em falha; casos não avaliados → insuficiente"),
        _c("PDR", 8, "sucesso", "Technical trade studies are mostly complete to sufficient detail and remaining "
           "trade studies are identified, plans exist for their closure, and potential impacts are understood.",
           "estudos_compromisso", "existe estudo MDO (acdt.mdo/1) com projeto viável escolhido"),
        _c("PDR", 9, "entrada", "Subsystem design specifications (hardware and software), with supporting "
           "trade-off analyses and data, as required, that are ready to be baselined after review comments are "
           "incorporated.", "linha_de_base",
           "a evidência confere com os SHA-256 registados e a proveniência não tem alterações por registar (git)"),
        _c("PDR", 10, "sucesso", "TBD and TBR items are clearly identified with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
        _c("PDR", 11, "sucesso", "The program/project cost, schedule, and JCL analysis (when required) are credible "
           "and within program/project constraints", None, _HUMAN),
        _c("PDR", 12, "sucesso", "Safety and mission assurance (e.g., safety, reliability, maintainability, quality "
           "controls, ...) have been adequately addressed in preliminary designs", None, _HUMAN),
        _c("PDR", 13, "sucesso", "Manufacturability has been adequately included in design.", None, _HUMAN),
        _c("PDR", 14, "entrada", "A preliminary PDR agenda, success criteria, and instructions to the review board "
           "have been agreed to", None, _HUMAN),
    ),
    "CDR": (
        _c("CDR", 1, "entrada", "A baselined detailed design that can be shown to meet all technical requirements "
           "and performance measures or has waivers.", "requisitos_cumpridos",
           "nenhum requisito em falha (salvo dispensa declarada); nao_avaliado/desconhecido → insuficiente"),
        _c("CDR", 2, "sucesso", "The detailed design is expected to meet the requirements with adequate margins.",
           "margens", "nenhum requisito avaliado fica no_limite", require_uq=True),
        _c("CDR", 3, "sucesso", "The product verification and product validation requirements and plans are "
           "complete.", "cobertura_completa",
           "cada requisito tem avaliador e foi avaliado (fração avaliada = 1, sem requisitos sem avaliador)"),
        _c("CDR", 4, "sucesso", "Risks to safety and mission success are understood and credibly assessed and plans "
           "and resources exist to effectively manage them.", "incerteza_requisitos",
           "existe estudo de incerteza e nenhum requisito fica em prob_falha; inconclusivo → insuficiente"),
        _c("CDR", 5, "sucesso", "Engineering test units, life test units, and/or modeling and simulations have been "
           "developed and tested per plan.", "vv_modelos",
           "existe relatório de V&V sem casos em falha nem por avaliar"),
        _c("CDR", 6, "sucesso", "Material properties tests are completed along with analyses of loads, stress, "
           "fracture control, contamination generation, and other analyses.", "ensaios_calibracao",
           "há pelo menos uma calibração contra ensaio real (não sintético) com decisão aplicar; dados sintéticos "
           "não contam como ensaio"),
        _c("CDR", 7, "entrada", "Technical data package (e.g., integrated schematics, spares provisioning list, "
           "interface control documents, engineering analyses, and specifications).", "fidelidade_disciplinas",
           "as disciplinas primárias têm análises registadas no nível exigido para a revisão"),
        _c("CDR", 8, "sucesso", "High confidence exists in the product baseline, and adequate documentation exists "
           "or will exist in a timely manner to allow proceeding with fabrication, assembly, integration, and test.",
           "linha_de_base",
           "a evidência confere com os SHA-256 registados e a proveniência não tem alterações por registar (git)"),
        _c("CDR", 9, "sucesso", "TBD and TBR items are clearly identified with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
        _c("CDR", 10, "sucesso", "Interface control documents are sufficiently mature to proceed with fabrication, "
           "assembly, integration, and test", None, _HUMAN),
        _c("CDR", 11, "sucesso", "The program/project cost and schedule estimates are credible and within "
           "program/project constraints.", None, _HUMAN),
        _c("CDR", 12, "sucesso", "Manufacturability has been adequately included in design.", None, _HUMAN),
    ),
    # Tabela G-5. A SDR de programas que não são de projeto único é a Tabela G-2 e não está aqui.
    "MDR": (
        _c("MDR", 1, "entrada", "The project has successfully completed the previously planned life-cycle reviews "
           "and all RFAs and RIDs have been addressed and resolved, or a timely closure plan exists for those "
           "items remaining open.", None, _HUMAN),
        _c("MDR", 2, "entrada", "A preliminary MDR/SDR agenda, success criteria, and instructions to the review "
           "board have been agreed to by the technical team, project manager, and review chair prior to the "
           "MDR/SDR.", None, _HUMAN),
        _c("MDR", 3, "sucesso", "The proposed mission/system architecture is credible and responsive to program "
           "requirements and constraints, including resources.", "conceito_viavel",
           "PRESSUPOSTO: só a grandeza de viabilidade do dimensionamento; recursos, custo e calendário não entram"),
        _c("MDR", 4, "sucesso", "All technical requirements are allocated to the architectural elements.",
           "arvore_requisitos",
           "PRESSUPOSTO: árvore sem problemas e com fonte; não demonstra a atribuição a cada elemento físico"),
        _c("MDR", 5, "sucesso", "The architecture tradeoffs are completed, and those planned for Phase B adequately "
           "address the option space.", "estudos_compromisso",
           "PRESSUPOSTO: estudo MDO com projeto viável escolhido; não demonstra a cobertura da Fase B"),
        _c("MDR", 6, "sucesso", "TBD and TBR items are clearly identified with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
    ),
    # Tabela G-10. Planos de ensaio, instalações, formação, segurança e espetro ficam humanos: o V&V dos modelos
    # não é o objetivo do ensaio.
    "TRR": (
        _c("TRR", 1, "entrada", "The objectives of the testing have been clearly defined and documented.", None,
           _HUMAN),
        _c("TRR", 2, "entrada", "Approved test plans, test procedures, test environment, and configuration of the "
           "test item(s) that support test objectives are available.", None, _HUMAN),
        _c("TRR", 3, "entrada", "As-built hardware and software documentation defining the configuration of the item "
           "under test are released and under configuration control.", "linha_de_base",
           "PRESSUPOSTO: só o SHA-256 e a proveniência dos ficheiros registados; não é um artigo físico"),
        _c("TRR", 4, "entrada", "All known system discrepancies have been identified and dispositioned in "
           "accordance with an agreed-upon plan.", "requisitos_cumpridos",
           "PRESSUPOSTO: só falhas de requisitos conhecidas; nao_avaliado/desconhecido não passa"),
        _c("TRR", 5, "sucesso", "Adequate test plans are completed and approved for the system under test.", None,
           _HUMAN),
        _c("TRR", 6, "sucesso", "TBD and TBR items are clearly identified with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
    ),
    # Tabela G-8. O âmbito («typically greater than three») fica no objetivo da revisão; um único avião não é
    # reprovado só por isso. Documentação de produção, BOM, riscos, custo, instalações e fornecedores ficam humanos.
    "PRR": (
        _c("PRR", 1, "entrada", "The design documentation needed to support production is available.", None, _HUMAN),
        _c("PRR", 2, "entrada", "The bill of materials is available and critical parts identified.", None, _HUMAN),
        _c("PRR", 3, "entrada", "Risks have been identified, credibly assessed, and characterized, and mitigation "
           "efforts have been defined.", None, _HUMAN + " (um estudo de incerteza não é um registo de riscos)"),
        _c("PRR", 4, "sucesso", "High confidence exists that the system requirements will be met in the final "
           "production configuration.", "requisitos_cumpridos",
           "nenhum requisito em falha (salvo dispensa); nao_avaliado/desconhecido → insuficiente"),
        _c("PRR", 5, "sucesso", "The product is deemed manufacturable.", None, _HUMAN),
        _c("PRR", 6, "sucesso", "TBD and TBR items are clearly identified, with acceptable plans and schedule for "
           "their disposition.", None, _HUMAN + " (os TBD/não avaliados estão listados nos itens em aberto)"),
    ),
}


def gate_key(gate: str) -> str:
    g = str(gate).strip().upper()
    if g not in GATES:
        raise ValueError(f"revisão '{gate}' desconhecida; uma de {sorted(GATES)}")
    return g


def criteria_for(gate: str) -> tuple[Criterion, ...]:
    return CRITERIA[gate_key(gate)]
