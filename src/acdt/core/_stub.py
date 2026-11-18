"""Helper for not-yet-implemented methods: each stub names its reference method."""


def not_implemented(method: str, reference: str, phase: str):
    raise NotImplementedError(f"{method} — planned for {phase}. Reference method: {reference}")
