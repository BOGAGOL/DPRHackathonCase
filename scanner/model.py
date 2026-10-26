from dataclasses import dataclass, field
from typing import Any


@dataclass
class Table:
    name: str
    columns: list[str]
    data_types: list[str]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    total: int = 0


INVENTORY_FIELDS = (
    "table,column,data_type,detected_type,pdp_class,risk_level,priority,priority_score,"
    "f_sensitivity,f_volume,f_exposure,f_exploitability,f_impact,f_recovery,"
    "content_score,name_score,confidence,triage,derived_from,sample_masked,reason,"
    "recommendation,allowed_roles,search_need,consistent_protection_with"
).split(",")
