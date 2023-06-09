from dataclasses import dataclass, field
from pathlib import Path
from dataclasses_json import DataClassJsonMixin, config, LetterCase
from enum import Enum
import typing as t


def hidden_field(*args, **kwargs):
    """Return an object to identify dataclass fields, but is will not be serialized.
    
    See: dataclasses.field"""
    metadata = config(kwargs.pop('metadata', None), exclude=lambda _:True)
    return field(*args, metadata=metadata, **kwargs)


enabled = False

class Severity(Enum):
    ERROR = 0
    WARNING = 1
    INFO = 2
    HINT = 3

@dataclass(init=False)
class Uri:
    """Javascript-friendly URI"""
    scheme: str = 'file'
    path: str
    fragment: str = ''

    def __init__(self, path: str|Path) -> None:
        self.path = str(path)

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
    uri: Uri
    range: Range


@dataclass
class RelatedInformation:
    location: Location
    message: str


@dataclass
class Diagnostic(DataClassJsonMixin):
    dataclass_json_config = config(letter_case=LetterCase.CAMEL)['dataclasses_json']
    message: str
    range: Range = field(default_factory=Range)
    severity: Severity = Severity.ERROR
    code: t.Optional[str|int] = None
    source: t.Optional[str] = None
    related_information: t.Optional[list[RelatedInformation]] = None
    filename: t.Optional[str] = hidden_field(default=None)


class DiagnosticCollection(dict[str, list[Diagnostic]], DataClassJsonMixin):
    
    def __setitem__(self, key: str, value: list[Diagnostic]) -> None:
        match value:
            case list():
                return super().__setitem__(key, value)
            case Diagnostic():
                if not key in self:
                    super().__setitem__(key, list())
                return self[key].append(value)
            case _:
                raise ValueError(f'Unallowed assignment: {type(value)}')

    def insert(self, diagnostics: list[Diagnostic],  default_key: str):
        for diagnostic in diagnostics:
            self[default_key if diagnostic.filename is None else diagnostic.filename] = diagnostic
