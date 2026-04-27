import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NormaEntry:
    id_canonico: str
    tipo: str
    numero: str
    año: int | None = None
    variantes: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    titulo_oficial: str = ""


class Catalogo:
    def __init__(self, entries: list[NormaEntry]):
        self._entries: dict[str, NormaEntry] = {e.id_canonico: e for e in entries}
        self._lookup: dict[str, str] = {}
        for e in entries:
            for v in e.variantes:
                self._lookup[self._normalize(v)] = e.id_canonico
            for a in e.aliases:
                self._lookup[self._normalize(a)] = e.id_canonico

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^(la|el|los|las)\s+", "", text)
        return text

    def resolve(self, text: str) -> str | None:
        return self._lookup.get(self._normalize(text))

    def get(self, id_canonico: str) -> NormaEntry | None:
        return self._entries.get(id_canonico)

    def all_entries(self) -> list[NormaEntry]:
        return list(self._entries.values())

    @classmethod
    def from_db_and_aliases(cls, db_normas: list[dict], aliases_path: Path | str) -> "Catalogo":
        """Build catalogo from DB rows and config/alias_normas.json."""
        with open(aliases_path) as f:
            alias_data = json.load(f)
        # alias_data structure: {"DFL_4": ["LGSE", ...], "DECRETO_62": [...]}
        entries = []
        for n in db_normas:
            id_can = f"{n['tipo']}_{n['numero']}"
            variantes = cls._gen_variantes(n["tipo"], n["numero"])
            entries.append(NormaEntry(
                id_canonico=id_can,
                tipo=n["tipo"],
                numero=n["numero"],
                año=n.get("año"),
                variantes=variantes,
                aliases=alias_data.get(id_can, []),
                titulo_oficial=n.get("titulo", ""),
            ))
        return cls(entries)

    @staticmethod
    def _gen_variantes(tipo: str, numero: str) -> list[str]:
        """Generate orthographic variants for a tipo+numero."""
        if tipo == "DECRETO":
            return [f"D.S. N° {numero}", f"D.S. {numero}", f"Decreto Supremo {numero}",
                    f"Decreto Supremo N° {numero}", f"decreto {numero}", f"D.S. N°{numero}"]
        if tipo == "LEY":
            return [f"Ley N° {numero}", f"Ley {numero}", f"ley {numero}",
                    f"Ley N°{numero}"]
        if tipo == "DFL":
            return [f"DFL N° {numero}", f"DFL {numero}", f"D.F.L. {numero}",
                    f"DFL N°{numero}", f"D.F.L. N° {numero}"]
        if tipo == "RESOLUCION":
            return [f"Resolución Exenta N° {numero}", f"Res. Ex. {numero}",
                    f"Resolución {numero}", f"Res. Ex. N° {numero}"]
        return [f"{tipo} {numero}"]
