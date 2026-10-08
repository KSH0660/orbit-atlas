"""Profile storage with inheritance (extends), cloning and override diffs.

A stored profile only keeps *overrides* relative to its parent::

    {"id": "jedec-ddr6", "name": "...", "extends": "jedec",
     "overrides": {"markdown": {"split_level": 2}}}

Resolution = model defaults <- root ancestor overrides <- ... <- own overrides.
Lists of objects carrying an ``id`` (image type rules) merge by id, so a child
profile can change one prompt without copying the whole list. An item with
``"_delete": true`` removes the inherited entry.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from importlib import resources
from pathlib import Path
from typing import Any

from ..schema import utcnow
from ..util import atomic_write_json
from .model import META_FIELDS, SETTINGS_SECTIONS, Profile

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,62}$")


class ProfileError(ValueError):
    pass


def _is_id_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(i, dict) and "id" in i for i in v)


def deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    if isinstance(base, list) and isinstance(over, list) and (_is_id_list(base) or _is_id_list(over)):
        out = [copy.deepcopy(i) for i in base]
        index = {i.get("id"): n for n, i in enumerate(out) if isinstance(i, dict)}
        for item in over:
            if not isinstance(item, dict) or "id" not in item:
                continue
            if item.get("_delete"):
                if item["id"] in index:
                    out[index[item["id"]]] = None
                continue
            if item["id"] in index and out[index[item["id"]]] is not None:
                out[index[item["id"]]] = deep_merge(out[index[item["id"]]], item)
            else:
                index[item["id"]] = len(out)
                out.append(copy.deepcopy(item))
        return [i for i in out if i is not None]
    return copy.deepcopy(over)


def diff_overrides(new: Any, parent: Any) -> Any:
    """Return the minimal override so that deep_merge(parent, result) == new.

    Returns ``_NO_DIFF`` when equal.
    """
    if isinstance(new, dict) and isinstance(parent, dict):
        out = {}
        for k, v in new.items():
            if k not in parent:
                out[k] = copy.deepcopy(v)
                continue
            d = diff_overrides(v, parent[k])
            if d is not _NO_DIFF:
                out[k] = d
        return out if out else _NO_DIFF
    if isinstance(new, list) and isinstance(parent, list) and (_is_id_list(new) or _is_id_list(parent)):
        if new == parent:
            return _NO_DIFF
        p_index = {i["id"]: i for i in parent if isinstance(i, dict) and "id" in i}
        n_ids = {i["id"] for i in new if isinstance(i, dict) and "id" in i}
        out_list: list[dict] = []
        for item in new:
            if item["id"] in p_index:
                d = diff_overrides(item, p_index[item["id"]])
                if d is not _NO_DIFF:
                    d = dict(d)
                    d["id"] = item["id"]
                    out_list.append(d)
            else:
                out_list.append(copy.deepcopy(item))
        for pid in p_index:
            if pid not in n_ids:
                out_list.append({"id": pid, "_delete": True})
        return out_list if out_list else _NO_DIFF
    return _NO_DIFF if new == parent else copy.deepcopy(new)


class _NoDiff:
    def __repr__(self) -> str:  # pragma: no cover
        return "<no diff>"


_NO_DIFF = _NoDiff()


def profile_hash(profile: Profile) -> str:
    data = profile.model_dump(include=set(SETTINGS_SECTIONS))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


REQUIRED_GROUPS = {
    ("parsing", "headings", "numbered_pattern"): ("num", "title"),
    ("parsing", "headings", "annex_pattern"): ("num", "title"),
    ("parsing", "tables", "caption_pattern"): ("num", "title"),
    ("parsing", "figures", "caption_pattern"): ("num", "title"),
}


def validate_patterns(profile: Profile) -> None:
    """Compile every regular expression of a profile; raise ProfileError listing the broken ones."""
    errors: list[str] = []

    def check(label: str, pattern: str, groups: tuple[str, ...] = ()) -> None:
        if not pattern:
            return
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            errors.append(f"{label}: {exc}")
            return
        missing = [g for g in groups if g not in rx.groupindex]
        if missing:
            errors.append(f"{label}: 이름 있는 그룹 (?P<{'>, (?P<'.join(missing)}>)이 필요합니다")

    d = profile.model_dump(include=set(SETTINGS_SECTIONS))
    for path, groups in REQUIRED_GROUPS.items():
        cur: Any = d
        for k in path:
            cur = cur[k]
        check(".".join(path), cur, groups)
    p = d["parsing"]
    for i, pat in enumerate(p["header_footer"]["extra_patterns"]):
        check(f"parsing.header_footer.extra_patterns[{i}]", pat)
    for k in ("title_pattern", "leader_pattern"):
        check(f"parsing.toc.{k}", p["toc"][k])
    for k in ("enum_pattern", "note_pattern"):
        check(f"parsing.paragraphs.{k}", p["paragraphs"][k])
    check("parsing.tables.continued_pattern", p["tables"]["continued_pattern"])
    for k in ("doc_number_pattern", "revision_pattern"):
        check(f"parsing.metadata.{k}", p["metadata"][k])
    for r in d["vision"]["image_types"]:
        check(f"vision.image_types[{r['id']}].caption_regex", r["caption_regex"])
        check(f"vision.image_types[{r['id']}].text_regex", r["text_regex"])
    for key in ("signal_patterns", "extra_token_patterns"):
        for i, pat in enumerate(d["validation"][key]):
            check(f"validation.{key}[{i}]", pat)
    if errors:
        raise ProfileError("정규식 오류: " + " / ".join(errors))


def _defaults() -> dict:
    return Profile(id="_defaults", name="defaults").model_dump(include=set(SETTINGS_SECTIONS))


def _load_builtins() -> dict[str, dict]:
    out: dict[str, dict] = {}
    pkg = resources.files("spec2kb.profiles") / "builtin"
    for entry in pkg.iterdir():
        if entry.name.endswith(".json"):
            raw = json.loads(entry.read_text(encoding="utf-8"))
            raw["builtin"] = True
            out[raw["id"]] = raw
    return out


class ProfileStore:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._builtins = _load_builtins()

    # -- raw access -------------------------------------------------------------
    def _path(self, pid: str) -> Path:
        return self.dir / f"{pid}.json"

    def get_raw(self, pid: str) -> dict:
        if pid in self._builtins:
            return copy.deepcopy(self._builtins[pid])
        p = self._path(pid)
        if not ID_RE.match(pid) or not p.exists():
            raise ProfileError(f"프로필을 찾을 수 없습니다: {pid}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["builtin"] = False
        raw.setdefault("overrides", {})
        return raw

    def exists(self, pid: str) -> bool:
        return pid in self._builtins or (bool(ID_RE.match(pid)) and self._path(pid).exists())

    def list(self) -> list[dict]:
        ids = list(self._builtins)
        ids += sorted(p.stem for p in self.dir.glob("*.json") if p.stem not in self._builtins)
        out = []
        for pid in ids:
            try:
                raw = self.get_raw(pid)
                chain = self.chain(pid)
            except (ProfileError, json.JSONDecodeError) as exc:
                out.append({"id": pid, "name": pid, "error": str(exc), "builtin": False})
                continue
            out.append({
                "id": pid, "name": raw.get("name", pid), "description": raw.get("description", ""),
                "extends": raw.get("extends"), "builtin": raw.get("builtin", False),
                "chain": chain, "updated_at": raw.get("updated_at", ""),
                "override_count": _count_leaves(raw.get("overrides", {})),
            })
        return out

    def chain(self, pid: str) -> list[str]:
        """Inheritance chain from the profile itself up to the root."""
        seen: list[str] = []
        cur: str | None = pid
        while cur:
            if cur in seen:
                raise ProfileError(f"상속 순환이 있습니다: {' -> '.join(seen + [cur])}")
            seen.append(cur)
            cur = self.get_raw(cur).get("extends")
        return seen

    # -- resolution -----------------------------------------------------------
    def resolved_dict(self, pid: str) -> dict:
        data = _defaults()
        for anc in reversed(self.chain(pid)):
            data = deep_merge(data, self.get_raw(anc).get("overrides", {}))
        return data

    def resolve(self, pid: str, extra_overrides: dict | None = None) -> Profile:
        data = self.resolved_dict(pid)
        if extra_overrides:
            data = deep_merge(data, extra_overrides)
        raw = self.get_raw(pid)
        meta = {k: raw.get(k) for k in META_FIELDS if k in raw}
        meta.setdefault("name", pid)
        try:
            prof = Profile(**meta, **data)
        except Exception as exc:  # pydantic validation error -> user-facing message
            raise ProfileError(f"프로필 '{pid}' 설정이 올바르지 않습니다: {exc}") from exc
        validate_patterns(prof)
        return prof

    def parent_resolved_dict(self, pid: str) -> dict:
        parent = self.get_raw(pid).get("extends")
        return self.resolved_dict(parent) if parent else _defaults()

    # -- mutation ---------------------------------------------------------------
    def _write(self, raw: dict) -> None:
        raw = {k: v for k, v in raw.items() if k != "builtin"}
        atomic_write_json(self._path(raw["id"]), raw)

    def create(self, new_id: str, name: str, base_id: str | None = None, mode: str = "inherit",
               description: str = "") -> dict:
        with self._lock:
            if not ID_RE.match(new_id):
                raise ProfileError("프로필 ID는 영문 소문자/숫자/-/_ 2~63자여야 합니다.")
            if self.exists(new_id):
                raise ProfileError(f"이미 존재하는 프로필 ID입니다: {new_id}")
            now = utcnow()
            if base_id and mode == "clone":
                base = self.get_raw(base_id)
                raw = {"id": new_id, "name": name, "description": description or base.get("description", ""),
                       "extends": base.get("extends"), "overrides": copy.deepcopy(base.get("overrides", {}))}
            elif base_id and mode == "flatten":
                raw = {"id": new_id, "name": name, "description": description, "extends": None,
                       "overrides": self.resolved_dict(base_id)}
            else:
                if base_id and not self.exists(base_id):
                    raise ProfileError(f"부모 프로필이 없습니다: {base_id}")
                raw = {"id": new_id, "name": name, "description": description, "extends": base_id,
                       "overrides": {}}
            raw["created_at"] = raw["updated_at"] = now
            self._write(raw)
            self.resolve(new_id)  # validate
            return self.get_raw(new_id)

    def update(self, pid: str, *, name: str | None = None, description: str | None = None,
               extends: str | None | object = ..., overrides: dict | None = None,
               resolved: dict | None = None) -> dict:
        """Update meta and settings. ``resolved`` (full settings) is converted to a minimal diff."""
        with self._lock:
            if pid in self._builtins:
                raise ProfileError("기본 제공 프로필은 수정할 수 없습니다. 복제 또는 상속하여 사용하세요.")
            raw = self.get_raw(pid)
            backup = copy.deepcopy(raw)
            if name is not None:
                raw["name"] = name
            if description is not None:
                raw["description"] = description
            if extends is not ...:
                if extends and (extends == pid or not self.exists(str(extends))):
                    raise ProfileError(f"부모 프로필이 올바르지 않습니다: {extends}")
                raw["extends"] = extends or None
            if resolved is not None:
                parent = self.resolved_dict(raw["extends"]) if raw.get("extends") else _defaults()
                # validate the full settings first so the diff is computed on normalized data
                normalized = Profile(id=pid, name=raw["name"], **{k: resolved.get(k, parent[k]) for k in SETTINGS_SECTIONS})
                full = normalized.model_dump(include=set(SETTINGS_SECTIONS))
                d = diff_overrides(full, parent)
                raw["overrides"] = {} if d is _NO_DIFF else d
            elif overrides is not None:
                raw["overrides"] = overrides
            raw["updated_at"] = utcnow()
            self._write(raw)
            try:
                self.chain(pid)
                self.resolve(pid)
            except ProfileError:
                self._write(backup)
                raise
            return self.get_raw(pid)

    def delete(self, pid: str) -> None:
        with self._lock:
            if pid in self._builtins:
                raise ProfileError("기본 제공 프로필은 삭제할 수 없습니다.")
            children = [p["id"] for p in self.list() if p.get("extends") == pid]
            if children:
                raise ProfileError(f"이 프로필을 상속하는 프로필이 있어 삭제할 수 없습니다: {', '.join(children)}")
            path = self._path(pid)
            if not path.exists():
                raise ProfileError(f"프로필을 찾을 수 없습니다: {pid}")
            path.unlink()

    def import_raw(self, raw: dict, overwrite: bool = False) -> dict:
        pid = str(raw.get("id", ""))
        if not ID_RE.match(pid):
            raise ProfileError("가져올 프로필에 올바른 id가 없습니다.")
        if pid in self._builtins:
            raise ProfileError("기본 제공 프로필 ID로는 가져올 수 없습니다.")
        if self.exists(pid) and not overwrite:
            raise ProfileError(f"이미 존재하는 프로필입니다: {pid}")
        extends = raw.get("extends")
        if extends and not self.exists(extends):
            raise ProfileError(f"부모 프로필이 없습니다: {extends}")
        clean = {"id": pid, "name": raw.get("name") or pid, "description": raw.get("description", ""),
                 "extends": extends, "overrides": raw.get("overrides", {}),
                 "created_at": raw.get("created_at") or utcnow(), "updated_at": utcnow()}
        self._write(clean)
        try:
            self.resolve(pid)
        except ProfileError:
            self._path(pid).unlink(missing_ok=True)
            raise
        return self.get_raw(pid)


def _count_leaves(d: Any) -> int:
    if isinstance(d, dict):
        return sum(_count_leaves(v) for v in d.values())
    if isinstance(d, list) and _is_id_list(d):
        return sum(max(1, _count_leaves({k: v for k, v in i.items() if k != "id"})) for i in d)
    return 1
