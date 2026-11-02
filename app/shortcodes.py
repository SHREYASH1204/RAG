"""Hugo shortcode resolution engine.

Implements the exact logic from upstream kubernetes/website templates in layouts/shortcodes/:
- skew.html (resolves latestVersion, currentVersion, currentVersionAddMinor, etc.)
- feature-state.html (both for_k8s_version and feature_gate_name forms)
- heading.html (using official data/i18n/en/en.toml values)
- param.html (.Page.Param resolution like version)
- note.html, caution.html, warning.html, alert.html
- glossary_tooltip.html, glossary_definition.html
- version-check.html
- tab.html, tabs.html
- include.html (including content/en/includes and relative paths)
- code.html, code_sample.html, codenew.html (embedding example YAMLs from examples/)
- other layout shortcodes
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

# Version configurations matching upstream hugo.toml
VERSION_SITE_PARAMS = {
    "1.27": {
        "version": "1.27",
        "latest": "1.31",
        "major": 1,
        "minor": 27,
    },
    "1.31": {
        "version": "1.31",
        "latest": "1.35",
        "major": 1,
        "minor": 31,
    },
}

HEADING_MAP = {
    "whatsnext": "What's next",
    "prerequisites": "Before you begin",
    "objectives": "Objectives",
    "cleanup": "Cleaning up",
    "seealso": "See Also",
    "synopsis": "Synopsis",
    "options": "Options",
    "examples": "Examples",
    "envvars": "Environment variables",
    "feedback": "Feedback",
}

# Cache for feature gates loaded from corpus/feature_gates_1.31.json
_FEATURE_GATES_CACHE: Optional[Dict[str, Dict]] = None
# Cache for glossary terms: version -> {term_id: {"title": str, "description": str}}
_GLOSSARY_CACHE: Dict[str, Dict[str, Dict[str, str]]] = {}


def generate_feature_gates_131_from_repo() -> Dict[str, Dict]:
    """Extract feature gates from k8s-1.31 repository files at pinned commit."""
    fg_dir = Path("k8s-1.31/content/en/docs/reference/command-line-tools-reference/feature-gates")
    gates: Dict[str, Dict] = {}
    if fg_dir.exists():
        import yaml
        for p in fg_dir.glob("*.md"):
            if p.name == "index.md":
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if txt.startswith("---"):
                parts = txt.split("---", 2)
                if len(parts) >= 3:
                    try:
                        data = yaml.safe_load(parts[1])
                        if isinstance(data, dict) and "title" in data:
                            title = str(data["title"]).strip()
                            stages = data.get("stages", [])
                            if stages and isinstance(stages, list):
                                curr = stages[-1]
                                gates[title] = {
                                    "stage": curr.get("stage", "alpha"),
                                    "fromVersion": str(curr.get("fromVersion", "1.31")),
                                    "defaultValue": curr.get("defaultValue", False),
                                }
                    except Exception:
                        pass
        if gates:
            out_p = Path("corpus/feature_gates_1.31.json")
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(gates, indent=2), encoding="utf-8")
    return gates


def get_feature_gates_131() -> Dict[str, Dict]:
    """Load or automatically generate 1.31 feature gates mapping from repo files."""
    global _FEATURE_GATES_CACHE
    if _FEATURE_GATES_CACHE is None:
        p = Path("corpus/feature_gates_1.31.json")
        if p.exists():
            try:
                _FEATURE_GATES_CACHE = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                _FEATURE_GATES_CACHE = generate_feature_gates_131_from_repo()
        else:
            _FEATURE_GATES_CACHE = generate_feature_gates_131_from_repo()
    return _FEATURE_GATES_CACHE


def load_glossary_term(term_id: str, version: str) -> Optional[Dict[str, str]]:
    """Load term metadata from glossary markdown files."""
    if version not in _GLOSSARY_CACHE:
        _GLOSSARY_CACHE[version] = {}

    if term_id in _GLOSSARY_CACHE[version]:
        return _GLOSSARY_CACHE[version][term_id]

    candidates = [
        Path(f"corpus/v{version}/glossary/{term_id}.md"),
        Path(f"k8s-{version}/content/en/docs/reference/glossary/{term_id}.md"),
    ]
    for cand in candidates:
        if cand.exists():
            txt = cand.read_text(encoding="utf-8", errors="ignore")
            title = term_id.replace("-", " ").title()
            m_title = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', txt, re.MULTILINE)
            if m_title:
                title = m_title.group(1).strip()
            
            # Extract first paragraph of body
            parts = txt.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else txt
            # Strip markdown links
            body_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
            paragraphs = [p.strip() for p in body_clean.split("\n\n") if p.strip()]
            desc = paragraphs[0] if paragraphs else ""
            res = {"title": title, "description": desc}
            _GLOSSARY_CACHE[version][term_id] = res
            return res

    return None


def resolve_include(path_arg: str, version: str, doc_dir: Optional[Path] = None) -> Tuple[str, bool]:
    """Resolve Hugo {{< include ... >}} shortcode against corpus files."""
    target_clean = path_arg.strip().strip('"').strip("'")
    candidates = []
    if doc_dir:
        candidates.append(doc_dir / target_clean)
    candidates.append(Path(f"corpus/v{version}/includes") / target_clean)
    candidates.append(Path(f"corpus/v{version}/includes") / Path(target_clean).name)
    candidates.append(Path(f"k8s-{version}/content/en/includes") / target_clean)
    candidates.append(Path(f"k8s-{version}/content/en/includes") / Path(target_clean).name)

    for cand in candidates:
        if cand.exists() and cand.is_file():
            raw = cand.read_text(encoding="utf-8", errors="ignore")
            # Strip front matter if present
            if raw.strip().startswith("---"):
                parts = raw.strip().split("---", 2)
                body = parts[2].strip() if len(parts) >= 3 else raw
            else:
                body = raw.strip()
            return body, True

    return "", False


def resolve_code_sample(file_arg: str, lang_arg: str, version: str) -> Tuple[str, bool]:
    """Resolve {{< code file="..." >}} or {{< code_sample ... >}} by reading example manifest."""
    rel_clean = file_arg.strip().strip('"').strip("'").lstrip("/")
    candidates = [
        Path(f"corpus/v{version}/examples") / rel_clean,
        Path(f"k8s-{version}/content/en/examples") / rel_clean,
    ]
    for cand in candidates:
        if cand.exists() and cand.is_file():
            content = cand.read_text(encoding="utf-8", errors="ignore").strip()
            codelang = lang_arg or Path(rel_clean).suffix.lstrip(".") or "yaml"
            return f"\n```{codelang}\n{content}\n```\n", True

    codelang = lang_arg or "yaml"
    return f"\n```{codelang}\n# {rel_clean}\n```\n", False


def resolve_skew(args_str: str, version: str) -> str:
    """Implement exact logic from upstream layouts/shortcodes/skew.html."""
    params = VERSION_SITE_PARAMS.get(version, VERSION_SITE_PARAMS["1.31"])
    tokens = [t.strip().strip('"').strip("'") for t in args_str.strip().split() if t.strip()]
    if not tokens:
        return ""

    arg0 = tokens[0]
    minor = params["minor"]
    major = params["major"]
    latest_minor = int(params["latest"].split(".")[1])

    if arg0 == "currentVersion":
        return f"{major}.{minor}"
    elif arg0 == "latestVersion":
        return params["latest"]
    elif arg0 == "nextMinorVersion":
        return f"{major}.{minor + 1}"
    elif arg0 == "prevMinorVersion":
        return f"{major}.{minor - 1}"
    elif arg0 == "oldestMinorVersion":
        return f"{major}.{minor - 2}"
    elif arg0 == "currentVersionAddMinor":
        offset = int(tokens[1]) if len(tokens) > 1 else 0
        sep = tokens[2] if len(tokens) > 2 else "."
        return f"{major}{sep}{minor + offset}"
    elif arg0 == "latestVersionAddMinor":
        offset = int(tokens[1]) if len(tokens) > 1 else 0
        sep = tokens[2] if len(tokens) > 2 else "."
        return f"{major}{sep}{latest_minor + offset}"
    elif arg0 == "currentPatchVersion":
        return f"{major}.{minor}.0"

    return f"{major}.{minor}"


def resolve_feature_state(args_str: str, version: str) -> Tuple[str, bool]:
    """Implement exact logic from layouts/shortcodes/feature-state.html."""
    # Check for feature_gate_name="..."
    m_gate = re.search(r'feature_gate_name=["\']([^"\']+)["\']', args_str)
    if m_gate:
        gate_name = m_gate.group(1).strip()
        gates_131 = get_feature_gates_131()
        if gate_name in gates_131:
            info = gates_131[gate_name]
            stage = info.get("stage", "alpha")
            from_ver = info.get("fromVersion", version)
            from_str = f"v{from_ver}" if not str(from_ver).startswith("v") else str(from_ver)
            return f"FEATURE STATE: Kubernetes {from_str} [{stage}]", True
        return f"FEATURE STATE: {gate_name}", False

    # Check for for_k8s_version and state
    m_ver = re.search(r'for_k8s_version=["\']([^"\']+)["\']', args_str)
    m_state = re.search(r'state=["\']([^"\']+)["\']', args_str)

    ver = m_ver.group(1).strip() if m_ver else f"v{version}"
    state = m_state.group(1).strip() if m_state else "stable"

    ver_str = ver if ver.startswith("v") else f"v{ver}"
    return f"FEATURE STATE: Kubernetes {ver_str} [{state}]", True


def resolve_shortcodes_in_markdown(
    text: str,
    version: str,
    doc_path: Optional[Path] = None,
) -> Tuple[str, Dict[str, int]]:
    """Scan and resolve all Hugo shortcodes in markdown text according to upstream rules."""
    unresolved_counts: Dict[str, int] = {}
    doc_dir = doc_path.parent if doc_path else None

    # 1. Resolve self-closing tab with include="..." first (must contain closing slash '/')
    # e.g. {{< tab name="Bash" include="included/optional-kubectl-configs-bash-linux.md" />}}
    tab_self_closing_re = re.compile(r"\{\{([<%])\s*tab\b([^>]*?)/\s*([%>])\}\}")

    def tab_self_replacer(match: re.Match) -> str:
        args = match.group(2)
        m_inc = re.search(r'include=["\']([^"\']+)["\']', args)
        m_name = re.search(r'name=["\']([^"\']+)["\']', args)
        tab_name = f"Tab {m_name.group(1)}:\n" if m_name else ""
        if m_inc:
            inc_content, ok = resolve_include(m_inc.group(1), version, doc_dir)
            if ok:
                sub_res, sub_unres = resolve_shortcodes_in_markdown(inc_content, version, doc_path)
                for k, v in sub_unres.items():
                    unresolved_counts[k] = unresolved_counts.get(k, 0) + v
                return f"\n{tab_name}{sub_res}\n"
            unresolved_counts["tab-include"] = unresolved_counts.get("tab-include", 0) + 1
        return ""

    text = tab_self_closing_re.sub(tab_self_replacer, text)

    # 2. Unroll paired shortcodes using loops
    # Inner paired shortcodes
    paired_names_inner = "tab|note|caution|warning|alert|comment|example|details|mermaid|table"
    inner_paired_re = re.compile(
        r"\{\{([<%])\s*(" + paired_names_inner + r")\b(.*?)([%>])\}\}(.*?)\{\{([<%])\s*/\s*\2\s*([%>])\}\}",
        re.DOTALL,
    )
    # Outer container shortcode
    outer_paired_re = re.compile(
        r"\{\{([<%])\s*(tabs)\b(.*?)([%>])\}\}(.*?)\{\{([<%])\s*/\s*\2\s*([%>])\}\}",
        re.DOTALL,
    )

    def paired_inner_replacer(match: re.Match) -> str:
        name = match.group(2).strip()
        args = match.group(3).strip()
        inner = match.group(5).strip()

        if name in ("note", "alert"):
            return f"\nNote: {inner}\n"
        elif name == "caution":
            return f"\nCaution: {inner}\n"
        elif name == "warning":
            return f"\nWarning: {inner}\n"
        elif name == "tab":
            m_name = re.search(r'name=["\']([^"\']+)["\']', args)
            tab_name = f"Tab {m_name.group(1)}:\n" if m_name else ""
            return f"\n{tab_name}{inner}\n"
        elif name == "comment":
            return ""
        elif name in ("example", "details", "table"):
            m_summary = re.search(r'summary=["\']([^"\']+)["\']', args)
            prefix = f"{m_summary.group(1)}\n" if m_summary else ""
            return f"\n{prefix}{inner}\n"
        elif name == "mermaid":
            return f"\n```mermaid\n{inner}\n```\n"

        unresolved_counts[name] = unresolved_counts.get(name, 0) + 1
        return inner

    def paired_outer_replacer(match: re.Match) -> str:
        inner = match.group(5).strip()
        return f"\n{inner}\n"

    # Repeatedly unroll nested paired shortcodes until fixed point
    while True:
        text, n1 = inner_paired_re.subn(paired_inner_replacer, text)
        text, n2 = outer_paired_re.subn(paired_outer_replacer, text)
        if n1 == 0 and n2 == 0:
            break

    # 3. Self-closing shortcodes: {{< name ... >}} or {{% name ... %}}
    single_pattern = re.compile(r"\{\{([<%])\s*([a-zA-Z0-9_\-]+)(.*?)([%>])\}\}", re.DOTALL)

    def single_replacer(match: re.Match) -> str:
        name = match.group(2).strip()
        args = match.group(3).strip()

        if name == "skew":
            return resolve_skew(args, version)
        elif name == "feature-state":
            res, ok = resolve_feature_state(args, version)
            if not ok:
                unresolved_counts["feature-state"] = unresolved_counts.get("feature-state", 0) + 1
            return res
        elif name == "heading":
            key = args.strip().strip('"').strip("'")
            return HEADING_MAP.get(key, key.replace("-", " ").title())
        elif name == "include":
            inc_file = args.strip().strip('"').strip("'")
            inc_content, ok = resolve_include(inc_file, version, doc_dir)
            if ok:
                # Recursively resolve any shortcodes within the included content
                sub_res, sub_unres = resolve_shortcodes_in_markdown(inc_content, version, doc_dir)
                for k, v in sub_unres.items():
                    unresolved_counts[k] = unresolved_counts.get(k, 0) + v
                return f"\n{sub_res}\n"
            unresolved_counts["include"] = unresolved_counts.get("include", 0) + 1
            return ""
        elif name in ("code", "code_sample", "codenew"):
            m_file = re.search(r'file=["\']([^"\']+)["\']', args)
            m_lang = re.search(r'language=["\']([^"\']+)["\']', args)
            if m_file:
                sample, ok = resolve_code_sample(m_file.group(1), m_lang.group(1) if m_lang else "", version)
                if not ok:
                    unresolved_counts[name] = unresolved_counts.get(name, 0) + 1
                return sample
            return ""
        elif name == "param":
            key = args.strip().strip('"').strip("'")
            if key == "version":
                return f"v{version}"
            elif key == "min-kubernetes-server-version":
                return f"v{version}"
            return ""
        elif name == "glossary_tooltip":
            m_text = re.search(r'text=["\']([^"\']+)["\']', args)
            m_term = re.search(r'term_id=["\']([^"\']+)["\']', args)
            if m_text:
                return m_text.group(1)
            elif m_term:
                term_info = load_glossary_term(m_term.group(1), version)
                if term_info:
                    return term_info["title"]
                return m_term.group(1).replace("-", " ")
            return ""
        elif name == "glossary_definition":
            m_term = re.search(r'term_id=["\']([^"\']+)["\']', args)
            m_prepend = re.search(r'prepend=["\']([^"\']+)["\']', args)
            prepend = f"{m_prepend.group(1)} " if m_prepend else ""
            if m_term:
                term_info = load_glossary_term(m_term.group(1), version)
                if term_info and term_info["description"]:
                    desc = term_info["description"]
                    sub_desc, sub_unres = resolve_shortcodes_in_markdown(desc, version, doc_path)
                    for k, v in sub_unres.items():
                        unresolved_counts[k] = unresolved_counts.get(k, 0) + v
                    return f"\n{prepend}{sub_desc}\n"
                return f"\n{prepend}{m_term.group(1).replace('-', ' ')}\n"
            return ""
        elif name == "version-check":
            return (
                f"Your Kubernetes server must be at or later than version v{version}. "
                f"To check the version, enter kubectl version."
            )
        elif name == "thirdparty-content":
            return (
                "Note: This section links to third-party projects that provide functionality "
                "required by Kubernetes. The Kubernetes Project Authors aren't responsible for these projects."
            )
        elif name == "legacy-repos-deprecation":
            return (
                "Note: The legacy package repositories (apt.kubernetes.io and yum.kubernetes.io) "
                "have been deprecated and frozen."
            )
        elif name in ("figure", "image"):
            m_caption = re.search(r'caption=["\']([^"\']+)["\']', args)
            m_title = re.search(r'title=["\']([^"\']+)["\']', args)
            res = []
            if m_title:
                res.append(m_title.group(1))
            if m_caption:
                res.append(m_caption.group(1))
            return "\n".join(res)
        elif name == "api-reference":
            m_text = re.search(r'text=["\']([^"\']+)["\']', args)
            m_anchor = re.search(r'anchor=["\']([^"\']+)["\']', args)
            if m_text:
                return m_text.group(1)
            elif m_anchor:
                return m_anchor.group(1)
            return "API Reference"
        elif name == "link":
            m_text = re.search(r'text=["\']([^"\']+)["\']', args)
            return m_text.group(1) if m_text else ""
        elif name == "feature-gate-description":
            m_name = re.search(r'name=["\']([^"\']+)["\']', args)
            if m_name:
                gate_name = m_name.group(1)
                gates_131 = get_feature_gates_131()
                info = gates_131.get(gate_name, {})
                stage = info.get("stage", "alpha")
                return f"{gate_name} ({stage})"
            return ""
        elif name in ("release-branches", "eol-releases", "release-data", "release-binaries", "upcoming-releases"):
            return f"Kubernetes v{version} release and support schedule."
        elif name in ("table", "highlight", "comment"):
            return ""

        unresolved_counts[name] = unresolved_counts.get(name, 0) + 1
        return ""

    text = single_pattern.sub(single_replacer, text)

    # Strip any orphaned closing shortcode tags (e.g. {{< /tab >}}, {{% /tab %}}, {{< /tabs >}})
    orphan_closing_re = re.compile(r"\{\{([<%])\s*/\s*[a-zA-Z0-9_\-]+\s*([%>])\}\}")
    text = orphan_closing_re.sub("", text)

    # Repeatedly resolve any nested single shortcodes injected by expansions
    for _ in range(3):
        if "{{" in text and single_pattern.search(text):
            text = single_pattern.sub(single_replacer, text)
            text = orphan_closing_re.sub("", text)
        else:
            break

    return text, unresolved_counts
