"""
Modelo de dados do registro coletado.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class Resultado:
    """Um resultado individual da busca do G1."""
    titulo: str
    url: str
    resumo: str | None = None
    veiculo: str | None = None
    data_publicacao_raw: str | None = None
    data_publicacao_iso: str | None = None
    publicitario: bool = False
    pagina: int = 1
    termo_busca: str = ""
    coletado_em: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return asdict(self)