"""Conservative, free, rule-only query planning over checkpoint USER text.

The caller must extract only user messages from its server-side checkpoint.
Client history and assistant messages are not inputs to this API. Only the last
four user strings are considered. Parsed years describe requested source scope;
they do not assert that an official model/year/powertrain combination exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import re


@dataclass(frozen=True, slots=True)
class QueryEntity:
    """Canonical scope for runtime pre-filtering; None explicitly means unspecified."""

    model: str
    aliases: tuple[str, ...]
    year: int | None = None
    powertrain: str | None = None


@dataclass(frozen=True, slots=True)
class QueryPlan:
    query: str
    clarification: str | None
    reason: str
    entities: tuple[QueryEntity, ...]


_ALIASES = {
    "CAMRY": ("凯美瑞", "CAMRY"),
    "HIGHLANDER": ("汉兰达", "HIGHLANDER"),
    "RAV4": ("RAV4荣放", "RAV4", "荣放"),
}
_MODEL = re.compile(r"凯美瑞|汉兰达|RAV4\s*荣放|荣放|(?<![a-z0-9_])(?:CAMRY|HIGHLANDER|RAV4)(?![a-z0-9_])", re.I)
_YEAR = re.compile(r"(?<![0-9])(?P<year>20[0-9]{2})\s*(?:年款|款|年)(?![0-9])")
_POWER = re.compile(
    r"(?<![0-9.])(?:2\.0|2\.5)(?![0-9.]|\s*(?:万?元|万元|米|公里|升/))\s*(?:[lL](?![a-zA-Z]))?"
    r"|双擎|混动|(?<![a-zA-Z])HEV(?![a-zA-Z])|燃油|汽油|插混|(?<![a-zA-Z])PHEV(?![a-zA-Z])",
    re.I,
)
_REFERENCE = re.compile(r"它们|它|这两款|那两款|这几款|这款|那款|该车|这辆|那辆|这台|那台|这个车|那个车|刚才(?:说的|那款|的车)?|上面(?:那款|的车)?")
_PLURAL = re.compile(r"它们|这两款|那两款|这几款|这些车|两车")
_COMPARE = re.compile(r"对比|比较|区别|差异|相比|各自|分别|哪个|哪款|哪辆|和.*比|与.*比|跟.*比")
_SPECIFIC = re.compile(r"价格|价钱|多少钱|报价|售价|指导价|落地|配置|参数|马力|扭矩|排量|油耗|续航|尺寸|轴距|几座|座位|功率|电池|变速箱|发动机|优惠|首付|月供|库存")
_SHORT_QUESTION = re.compile(
    r"(?:那|那么|这|的|呢|吗|啊|呀|请问|请|一下|再|说说|介绍|怎么样|如何|多少钱|几座|"
    r"有无|有没有|是否|有什么|哪些|多少|价格|价钱|报价|售价|指导价|落地价|配置|参数|"
    r"马力|扭矩|油耗|续航|尺寸|轴距|座位|功率|电池|变速箱|发动机|优惠|首付|月供|库存|区别|对比|比较)+"
)
_UNSPECIFIED_YEAR = re.compile(r"最新款|新款|现款|今年款|今年的|去年款|去年那款")


def _mentions(text: str) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    for match in _MODEL.finditer(text):
        spelling = re.sub(r"\s", "", match.group()).upper()
        model = next(model for model, aliases in _ALIASES.items() if spelling in aliases)
        result.append((model, match.start(), match.end()))
    return result


def _years(text: str) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(match.group("year")) for match in _YEAR.finditer(text)))


def _powertrain(text: str) -> tuple[str | None, bool]:
    displacements: set[str] = set()
    fuels: set[str] = set()
    for match in _POWER.finditer(text):
        token = match.group().strip().upper()
        if token.startswith(("2.0", "2.5")):
            displacements.add(token[:3])
        else:
            fuels.add({"双擎": "双擎", "混动": "双擎", "HEV": "双擎",
                       "燃油": "燃油", "汽油": "燃油", "插混": "插混", "PHEV": "插混"}[token])
    if len(displacements) > 1 or len(fuels) > 1:
        return None, True
    parts = sorted(displacements) + sorted(fuels)
    return " ".join(parts) if parts else None, False


def _followup(text: str) -> bool:
    if _REFERENCE.search(text):
        return True
    if len(text) > 32:
        return False
    residual = _YEAR.sub("", text)
    residual = _UNSPECIFIED_YEAR.sub("", residual)
    residual = _POWER.sub("", residual)
    residual = re.sub(r"[\s，,。.!！?？:：;；]", "", residual)
    return bool(text.strip()) and (not residual or _SHORT_QUESTION.fullmatch(residual) is not None)


def _explicit_entities(text: str) -> tuple[tuple[QueryEntity, ...], str | None]:
    mentions = _mentions(text)
    models = tuple(dict.fromkeys(model for model, _, _ in mentions))
    years = _years(text)
    if len(models) > 1 and re.search(r"还是|或者|或", text) and not _COMPARE.search(text):
        return tuple(QueryEntity(model, _ALIASES[model]) for model in models), "ambiguous_reference"
    if len(years) > 1 and len(models) == 1:
        if not _COMPARE.search(text):
            return (QueryEntity(models[0], _ALIASES[models[0]]),), "ambiguous_year"
        power, ambiguous = _powertrain(text)
        if ambiguous:
            return (QueryEntity(models[0], _ALIASES[models[0]]),), "ambiguous_powertrain"
        return tuple(QueryEntity(models[0], _ALIASES[models[0]], year, power) for year in years), None
    entities: list[QueryEntity] = []
    for model in models:
        if len(models) == 1:
            selected_years = years
            power_text = text
        else:
            # Bind only adjacent explicit attributes to a model. Never copy one
            # car's year/powertrain onto another car in a comparison.
            selected: list[int] = []
            pieces: list[str] = []
            for index, (mentioned_model, start, end) in enumerate(mentions):
                if mentioned_model != model:
                    continue
                prefix = text[mentions[index - 1][2] if index else 0:start]
                suffix = text[end:mentions[index + 1][1] if index + 1 < len(mentions) else len(text)]
                for year_match in _YEAR.finditer(prefix):
                    if re.fullmatch(r"\s*(?:的)?\s*", prefix[year_match.end():]):
                        selected.append(int(year_match.group("year")))
                for year_match in _YEAR.finditer(suffix):
                    if re.fullmatch(r"\s*(?:的)?\s*", suffix[:year_match.start()]):
                        selected.append(int(year_match.group("year")))
                # Trailing modifiers belong only to the immediately preceding
                # model; leading powertrain modifiers in multi-car queries are
                # left unspecified to avoid crossing a conjunction.
                pieces.append(re.split(r"和|与|跟|、|相比|对比|比较|及|以及", suffix, maxsplit=1)[0])
            selected_years = tuple(dict.fromkeys(selected))
            power_text = " ".join(pieces)
        if len(selected_years) > 1:
            return tuple(entities + [QueryEntity(model, _ALIASES[model])]), "ambiguous_year"
        power, ambiguous = _powertrain(power_text)
        if ambiguous:
            return tuple(entities + [QueryEntity(model, _ALIASES[model])]), "ambiguous_powertrain"
        entities.append(QueryEntity(model, _ALIASES[model], selected_years[0] if selected_years else None, power))
    return tuple(entities), None


def _clarify(query: str, reason: str, entities: tuple[QueryEntity, ...] = ()) -> QueryPlan:
    prompts = {
        "empty_query": "请说明您想了解的问题。",
        "missing_model": "请明确车型：凯美瑞、汉兰达或 RAV4 荣放。",
        "ambiguous_reference": "刚才涉及多个车型或年款，请明确您指的是哪一款。",
        "ambiguous_year": "问题涉及多个年款，请明确所问年款，或说明需要比较哪些年款。",
        "missing_year": "请明确所问车型的四位年款（例如 20xx 款）；比较时请分别说明各车年款。",
        "ambiguous_powertrain": "请明确动力版本，或将不同动力版本分开提问。",
    }
    return QueryPlan(query, prompts[reason], reason, entities)


def _update_followup(entities: tuple[QueryEntity, ...], text: str) -> tuple[tuple[QueryEntity, ...], str | None]:
    years = _years(text)
    if len(years) > 1:
        return entities, "ambiguous_year"
    power, ambiguous = _powertrain(text)
    if ambiguous:
        return entities, "ambiguous_powertrain"
    if len(entities) > 1 and not _PLURAL.search(text) and not _COMPARE.search(text):
        return entities, "ambiguous_reference"
    if len(entities) > 1 and (years or power):
        # Do not assign a new singular attribute to several earlier variants.
        return entities, "ambiguous_reference"
    updated = tuple(replace(entity, year=years[0] if years else entity.year,
                            powertrain=power if power is not None else entity.powertrain) for entity in entities)
    return updated, None


def _checkpoint_context(messages: Sequence[str]) -> tuple[tuple[QueryEntity, ...], str | None]:
    recent = messages[-4:]
    for index in range(len(recent) - 1, -1, -1):
        if not _mentions(recent[index]):
            continue
        entities, error = _explicit_entities(recent[index])
        if error:
            return entities, error
        for subsequent in recent[index + 1:]:
            if not _followup(subsequent):
                return (), None
            entities, error = _update_followup(entities, subsequent)
            if error:
                return entities, error
        return entities, None
    return (), None


def plan_query(query: str, previous_user_messages: Sequence[str] = ()) -> QueryPlan:
    """Plan a query without guessing scope or generating facts.

    ``query`` is original/current user text. ``previous_user_messages`` must be
    user-only text extracted from a trusted server checkpoint, oldest first.
    Current explicit models override history; history is used only for explicit
    references or bounded short follow-ups. A clarification blocks retrieval.
    Successful ``query`` appends canonical model/year/powertrain scope for lexical
    recall; use ``entities`` to pre-filter candidates, never the text alone.
    Missing years stay None for broad introductions; configuration/price questions
    require explicit years. No catalog or official availability is inferred.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(previous_user_messages, (str, bytes)) or not isinstance(previous_user_messages, Sequence):
        raise TypeError("previous_user_messages must be a sequence of checkpoint user strings")
    recent = previous_user_messages[-4:]
    if any(not isinstance(message, str) for message in recent):
        raise TypeError("pass checkpoint user text only, not assistant/role message objects")
    text = query.strip()
    if not text:
        return _clarify(text, "empty_query")
    explicit = bool(_mentions(text))
    if explicit:
        entities, error = _explicit_entities(text)
        if not error and _REFERENCE.search(text) and _COMPARE.search(text):
            # A named car plus "it" may mean two cars; do not silently drop the
            # referenced car or resolve it from a potentially ambiguous context.
            return _clarify(text, "ambiguous_reference", entities)
    elif _followup(text):
        entities, error = _checkpoint_context(recent)
        if entities and not error:
            entities, error = _update_followup(entities, text)
    else:
        entities, error = (), None
    if error:
        return _clarify(text, error, entities)
    if not entities:
        return _clarify(text, "missing_model")
    # Relative wording must never silently inherit an old year as "latest".
    if _UNSPECIFIED_YEAR.search(text) and not _years(text):
        entities = tuple(replace(entity, year=None) for entity in entities)
        return _clarify(text, "missing_year", entities)
    if _SPECIFIC.search(text) and any(entity.year is None for entity in entities):
        return _clarify(text, "missing_year", entities)
    scope = "；".join(
        " ".join(part for part in (entity.aliases[0], entity.model,
                                   f"{entity.year}款" if entity.year is not None else "年款未指定",
                                   entity.powertrain) if part)
        for entity in entities
    )
    reason = "explicit_scope" if explicit else "checkpoint_followup"
    if any(entity.year is None for entity in entities):
        reason += "_year_unspecified"
    return QueryPlan(f"{text}\n检索范围：{scope}", None, reason, entities)
