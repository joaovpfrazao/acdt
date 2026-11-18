# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ingestão de dados de ensaio e calibração de modelos (docs/CALIBRACAO.md).

* :mod:`.ingest` — ``acdt.testdata/1``: CSV, Parquet, PX4 ULog, com unidades, metadados e SHA-256;
* :mod:`.fitting` — mínimos quadrados ponderados com incerteza dos parâmetros; Kennedy & O'Hagan leve;
* :mod:`.record` — ``acdt.calib/1``: resíduos, validade, critérios de aceitação, decisão e exportações.
"""
from __future__ import annotations

from .fitting import CalibrationError, ModelSpec, Parameter, fit
from .ingest import Channel, Dataset, IngestError, from_arrays, load
from .record import applicable_at, build_record, decide, factors_file, overlay, run_study, to_design_db, uq_inputs

__all__ = ["CalibrationError", "ModelSpec", "Parameter", "fit", "Channel", "Dataset", "IngestError", "from_arrays",
           "load", "applicable_at", "build_record", "decide", "factors_file", "overlay", "run_study",
           "to_design_db", "uq_inputs"]
