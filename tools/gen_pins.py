"""依据 wheels/ 目录中已下载的最高版本，把 requirements.txt 重写为精确锁定版。

消除 pip 回溯解析（离线环境下多版本候选导致 ResolutionImpossible）。
用法：python tools/gen_pins.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_deps import _VERSION_PINS, top_level_packages  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "wheels"
REQ = ROOT / "backend" / "requirements.txt"


def norm_of(package: str) -> str:
    return package.lower().replace("_", "-")


def max_version_for(package: str) -> str | None:
    norm = norm_of(package)
    pin = _VERSION_PINS.get(norm)
    if pin:
        return pin
    candidates: dict[str, object] = {}
    for whl in WHEELS.glob("*.whl"):
        stem = whl.name
        m = re.match(r"^(.+?)-(\d[\w.+]*(?:\.(?:post|dev)\d+)?)", stem)
        if not m:
            continue
        name = m.group(1).lower().replace("_", "-")
        if name != norm:
            continue
        try:
            from packaging.version import Version
            candidates[m.group(2)] = Version(m.group(2))
        except Exception:
            candidates[m.group(2)] = m.group(2)
    if not candidates:
        return None
    # 稳定版优先：存在稳定版时排除预发布版
    stable = {v: p for v, p in candidates.items() if not getattr(p, "is_prerelease", False)}
    pool = stable or candidates
    try:
        from packaging.version import Version
        best = max(pool.values())
    except Exception:
        best = max(pool.values())
    return str(best)


def main() -> int:
    lines = REQ.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    changed = 0
    for line in lines:
        stripped = line.split("#")[0].strip()
        if not stripped:
            out.append(line)
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)(\[[a-zA-Z0-9_,-]+\])?\s*(>=|==|~=|>|<=)?", stripped)
        if not m:
            out.append(line)
            continue
        package = m.group(1)
        extras = m.group(2) or ""
        # 恢复已被早期运行剥离的 extras（bcrypt/cryptography 依赖来自 extras）
        if not extras and norm_of(package) in ("python-jose",):
            extras = "[cryptography]"
        comment = line.split("#", 1)[1] if "#" in line else ""
        norm = package.lower().replace("_", "-")
        if norm in _VERSION_PINS:
            version = _VERSION_PINS[norm]
        else:
            version = max_version_for(norm)
        if version:
            new = f"{package}{extras}=={version}"
            if comment:
                new += f"  # {comment}"
            out.append(new)
            changed += 1
        else:
            out.append(line)  # 无 wheel 可用，保留原约束交给 bootstrap 解析
    REQ.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"pinned {changed} top-level packages in requirements.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
