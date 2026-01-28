"""
Spell database - loads and indexes spell data from spells_us.txt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.data import SpellInfo


class SpellDatabase:
    """
    Loads and indexes spell data for timer tracking.
    
    Provides lookups by:
    - Spell name
    - "Cast on you" message
    - "Cast on other" message  
    - "Spell fades" message
    """

    P99_EXPANSIONS = {"Classic", "Kunark", "Velious", "Hole", ""}

    def __init__(self, spells_file: Path, whitelist_file: Optional[Path] = None):
        self._by_name: dict[str, SpellInfo] = {}
        self._by_cast_on_you: dict[str, list[SpellInfo]] = {}
        self._by_cast_on_other: dict[str, list[SpellInfo]] = {}
        self._by_fades: dict[str, list[SpellInfo]] = {}
        self._cast_times: dict[str, int] = {}
        self._by_id: dict[int, SpellInfo] = {}
        self._whitelist: Optional[set[str]] = None

        # Load whitelist
        if whitelist_file and whitelist_file.exists():
            self._whitelist = set()
            with open(whitelist_file, "r", encoding="utf-8") as f:
                for line in f:
                    spell_name = line.strip()
                    if spell_name:
                        self._whitelist.add(spell_name)
            print(f"Loaded {len(self._whitelist)} spells from whitelist")

        self._load(spells_file)

    def _parse_expansion_info(self, line: str) -> tuple[str, int]:
        """Parse expansion and replacement spell ID from end of line."""
        fields = line.split("^")
        if len(fields) < 2:
            return ("", 0)

        try:
            replacement_id = int(fields[-1])
        except ValueError:
            replacement_id = 0

        expansion_field = fields[-2] if len(fields) >= 2 else ""
        if expansion_field.startswith("!Expansion:"):
            expansion = expansion_field[11:]
        else:
            expansion = ""

        return (expansion, replacement_id)

    def _is_valid_for_p99(self, spell: SpellInfo) -> bool:
        """Check if spell is valid for P99."""
        if self._whitelist is not None and spell.name not in self._whitelist:
            return False
        if spell.replaced_by == 0:
            return True
        if spell.replacement_expansion in self.P99_EXPANSIONS:
            return False
        return True

    def _load(self, path: Path) -> None:
        """Load spell database from file."""
        if not path.exists():
            print(f"ERROR: Spell file not found: {path}")
            return

        all_spells: list[SpellInfo] = []

        with open(path, "r", encoding="latin-1") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                fields = line.split("^")
                if len(fields) >= 14:
                    try:
                        name = fields[1]
                        if "GM" in name:
                            continue

                        cast_time = int(fields[13])
                        if name not in self._cast_times or cast_time > self._cast_times[name]:
                            self._cast_times[name] = cast_time
                    except (ValueError, IndexError):
                        pass

                if len(fields) < 85:
                    continue

                try:
                    spell_id = int(fields[0])
                    name = fields[1]

                    if "GM" in name:
                        continue

                    cast_on_you = fields[6]
                    cast_on_other = fields[7]
                    spell_fades = fields[8]
                    duration_formula = int(fields[16])
                    duration_base = int(fields[17])
                    cast_time_ms = int(fields[13])
                    target_type = int(fields[40])
                    beneficial = int(fields[83]) == 1

                    expansion, replaced_by = self._parse_expansion_info(line)

                    spell = SpellInfo(
                        id=spell_id,
                        name=name,
                        cast_on_you=cast_on_you,
                        cast_on_other=cast_on_other,
                        spell_fades=spell_fades,
                        duration_formula=duration_formula,
                        duration_base=duration_base,
                        cast_time_ms=cast_time_ms,
                        target_type=target_type,
                        beneficial=beneficial,
                        replaced_by=replaced_by,
                        replacement_expansion=expansion,
                    )

                    all_spells.append(spell)
                    self._by_id[spell_id] = spell

                except (ValueError, IndexError):
                    continue

        # Index valid spells
        for spell in all_spells:
            if not self._is_valid_for_p99(spell):
                continue

            self._by_name[spell.name] = spell

            if spell.cast_on_you:
                key = spell.cast_on_you
                if key not in self._by_cast_on_you:
                    self._by_cast_on_you[key] = []
                self._by_cast_on_you[key].append(spell)

            if spell.cast_on_other:
                suffix = spell.cast_on_other
                if suffix not in self._by_cast_on_other:
                    self._by_cast_on_other[suffix] = []
                self._by_cast_on_other[suffix].append(spell)

            if spell.spell_fades:
                key = spell.spell_fades
                if key not in self._by_fades:
                    self._by_fades[key] = []
                self._by_fades[key].append(spell)

        print(f"Loaded {len(self._by_name)} spells ({len(self._cast_times)} with cast times)")

    def get_by_name(self, name: str) -> Optional[SpellInfo]:
        """Get spell by exact name."""
        return self._by_name.get(name)

    def get_cast_time(self, spell_name: str) -> int:
        """Get cast time in ms for a spell."""
        return self._cast_times.get(spell_name, 0)

    def find_by_cast_on_you(self, message: str) -> list[SpellInfo]:
        """Find spells matching a 'cast on you' message."""
        return self._by_cast_on_you.get(message, [])

    def find_by_cast_on_other(self, message: str) -> list[SpellInfo]:
        """Find spells matching a 'cast on other' message (ends with suffix)."""
        results = []
        for suffix, spells in self._by_cast_on_other.items():
            if message.endswith(suffix):
                results.extend(spells)
        return results

    def find_by_fades(self, message: str) -> list[SpellInfo]:
        """Find spells matching a 'spell fades' message."""
        return self._by_fades.get(message, [])

    def best_match(self, spells: list[SpellInfo], prefer_name: Optional[str] = None) -> Optional[SpellInfo]:
        """Choose best spell from candidates, preferring given name if provided."""
        if not spells:
            return None
        if prefer_name:
            for s in spells:
                if s.name == prefer_name:
                    return s
        # Prefer spells with duration
        with_duration = [s for s in spells if s.has_duration]
        if with_duration:
            return with_duration[0]
        return spells[0]
