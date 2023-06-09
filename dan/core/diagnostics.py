from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin, config, LetterCase
from enum import Enum
import typing as t

enabled = False

class Severity(str, Enum):
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'information'
    HINT = 'hint'


@dataclass
class Position:
    line: int = 0
    character: int = 0

@dataclass
class Range:
    start: Position = field(default_factory=Position)
    end: Position = field(default_factory=Position)


@dataclass
class Location:
    uri: str
    range: Range


@dataclass
class RelatedInformation:
    localtion: Location
    message: str


@dataclass
class Diagnostic(DataClassJsonMixin):
    dataclass_json_config = config(letter_case=LetterCase.CAMEL)
    message: str
    range: Range = field(default_factory=Range)
    severity: Severity = Severity.ERROR
    code: t.Optional[str|int] = None
    source: t.Optional[str] = None
    related_information: t.Optional[list[RelatedInformation]] = None


class DiagnosticCollection(dict[str, Diagnostic], DataClassJsonMixin):
    pass
