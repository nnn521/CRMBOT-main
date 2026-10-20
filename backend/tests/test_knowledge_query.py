"""Rule planner tests; requested scopes are synthetic, not vehicle facts."""

from dataclasses import FrozenInstanceError

import pytest

from app.services.knowledge.query import plan_query


@pytest.mark.parametrize(("spelling", "canonical"), [
    ("凯美瑞", "CAMRY"), ("camry", "CAMRY"), ("汉兰达", "HIGHLANDER"),
    ("highlander", "HIGHLANDER"), ("RAV4荣放", "RAV4"), ("rav4", "RAV4"), ("荣放", "RAV4"),
])
def test_canonical_entities_and_unspecified_year_for_introductions(spelling, canonical):
    plan = plan_query(f"介绍一下{spelling}")
    assert plan.clarification is None
    assert len(plan.entities) == 1
    entity = plan.entities[0]
    assert entity.model == canonical
    assert entity.year is None
    assert canonical in entity.aliases
    assert "年款未指定" in plan.query
    assert plan.reason == "explicit_scope_year_unspecified"


def test_explicit_year_and_powertrain_are_preserved_without_catalog_claim():
    plan = plan_query("2099款凯美瑞2.5双擎的配置？")
    assert plan.clarification is None
    assert plan.entities[0].year == 2099
    assert plan.entities[0].powertrain == "2.5 双擎"
    assert "2099款" in plan.query
    # A parsed request is a filter, not an assertion that this model year exists.
    assert "有售" not in plan.query
    with pytest.raises(FrozenInstanceError):
        plan.entities[0].year = 2024


@pytest.mark.parametrize("query", ["凯美瑞价格", "汉兰达几座", "荣放油耗", "凯美瑞配置", "CAMRY尺寸"])
def test_specific_questions_require_year(query):
    plan = plan_query(query)
    assert plan.clarification
    assert plan.reason == "missing_year"
    assert plan.entities[0].year is None
    assert plan.query == query


def test_current_model_overrides_old_model_year_and_powertrain():
    plan = plan_query("介绍汉兰达", ["2024款凯美瑞2.0配置如何"])
    assert plan.clarification is None
    assert [(entity.model, entity.year, entity.powertrain) for entity in plan.entities] == [("HIGHLANDER", None, None)]
    assert "CAMRY" not in plan.query and "2024" not in plan.query and "2.0" not in plan.query
    specific = plan_query("汉兰达的价格呢", ["2024款凯美瑞的价格"])
    assert specific.reason == "missing_year"
    assert specific.entities[0].year is None


def test_pronoun_inherits_only_most_recent_explicit_user_model():
    plan = plan_query("它的价格呢", ["介绍2023款凯美瑞", "2024款汉兰达2.5双擎介绍一下"])
    assert plan.clarification is None
    assert [(e.model, e.year, e.powertrain) for e in plan.entities] == [("HIGHLANDER", 2024, "2.5 双擎")]
    assert "凯美瑞" not in plan.query and "2023" not in plan.query


def test_short_question_and_explicit_year_followup_use_checkpoint():
    plan = plan_query("价格呢", ["介绍2024款荣放"])
    assert plan.clarification is None
    assert plan.entities[0].model == "RAV4"
    assert plan.entities[0].year == 2024
    changed = plan_query("那2025款呢", ["2024款凯美瑞介绍一下"])
    assert changed.clarification is None
    assert changed.entities[0].year == 2025


def test_recent_short_followups_update_context_in_order():
    plan = plan_query("它的油耗呢", ["介绍2023款凯美瑞2.0", "2024款呢", "2.5呢"])
    assert plan.clarification is None
    assert [(e.year, e.powertrain) for e in plan.entities] == [(2024, "2.5")]


def test_context_is_bounded_to_four_user_messages():
    assert plan_query("它的价格呢", ["2024款凯美瑞", "你好", "好的", "谢谢", "再见"]).reason == "missing_model"
    within = plan_query("它的价格呢", ["不要使用这条旧消息", "2024款凯美瑞", "价格呢", "油耗呢", "配置呢"])
    assert within.clarification is None
    assert within.entities[0].model == "CAMRY"


def test_unrelated_intervening_topic_blocks_stale_context():
    plan = plan_query("它的价格呢", ["2024款凯美瑞", "我要咨询另一件不相关的事情"])
    assert plan.reason == "missing_model"


def test_no_history_and_no_explicit_model_requests_clarification():
    assert plan_query("它的价格呢").reason == "missing_model"
    assert plan_query("请介绍汽车选购知识", ["2024款凯美瑞"]).reason == "missing_model"
    assert plan_query("   ").reason == "empty_query"
    assert plan_query("camryX配置").reason == "missing_model"
    assert plan_query("rav40介绍").reason == "missing_model"


def test_two_car_comparison_keeps_two_entities_and_individual_years():
    plan = plan_query("2024款凯美瑞和2025款汉兰达配置对比", ["2020款荣放"])
    assert plan.clarification is None
    assert [(e.model, e.year) for e in plan.entities] == [("CAMRY", 2024), ("HIGHLANDER", 2025)]
    assert "RAV4" not in plan.query and "2020" not in plan.query
    after = plan_query("凯美瑞2024款和汉兰达2025款配置对比")
    assert [(e.model, e.year) for e in after.entities] == [("CAMRY", 2024), ("HIGHLANDER", 2025)]


def test_named_model_plus_comparative_pronoun_does_not_drop_second_car():
    plan = plan_query("2025款汉兰达和它比价格", ["2024款凯美瑞介绍一下"])
    assert plan.reason == "ambiguous_reference"


def test_disjunctive_model_scope_requires_clarification():
    assert plan_query("2024款凯美瑞还是汉兰达的价格").reason == "ambiguous_reference"


def test_comparison_never_copies_one_year_to_other_car():
    plan = plan_query("2024款凯美瑞和汉兰达价格对比")
    assert plan.reason == "missing_year"
    assert [(e.model, e.year) for e in plan.entities] == [("CAMRY", 2024), ("HIGHLANDER", None)]
    generic = plan_query("凯美瑞与汉兰达区别")
    assert generic.clarification is None
    assert len(generic.entities) == 2
    assert all(e.year is None for e in generic.entities)


def test_comparison_powertrains_do_not_cross_model_boundaries():
    plan = plan_query("2024款凯美瑞2.0和2025款汉兰达2.5双擎配置比较")
    assert plan.clarification is None
    assert [e.powertrain for e in plan.entities] == ["2.0", "2.5 双擎"]


def test_singular_pronoun_after_multi_car_context_is_ambiguous():
    context = ["2024款凯美瑞和2025款汉兰达对比"]
    plan = plan_query("它的价格呢", context)
    assert plan.reason == "ambiguous_reference"
    assert len(plan.entities) == 2
    plural = plan_query("它们的价格呢", context)
    assert plural.clarification is None
    assert len(plural.entities) == 2
    assert plan_query("那2026款呢", context).reason == "ambiguous_reference"


def test_multiple_years_require_explicit_comparison_or_clarification():
    ambiguous = plan_query("2024款或2025款凯美瑞价格")
    assert ambiguous.reason == "ambiguous_year"
    compared = plan_query("2024款和2025款凯美瑞配置对比")
    assert compared.clarification is None
    assert [(e.model, e.year) for e in compared.entities] == [("CAMRY", 2024), ("CAMRY", 2025)]
    assert plan_query("它的价格呢", ["2024款和2025款凯美瑞对比"]).reason == "ambiguous_reference"


def test_relative_year_never_fabricates_or_inherits_catalog_year():
    assert plan_query("最新款凯美瑞价格").reason == "missing_year"
    plan = plan_query("最新款的配置呢", ["2024款凯美瑞"])
    assert plan.reason == "missing_year"
    assert plan.entities[0].year is None
    assert plan_query("24款凯美瑞价格").reason == "missing_year"


def test_powertrain_ambiguity_and_decimal_prices_not_displacement():
    assert plan_query("2024款凯美瑞2.0还是2.5配置").reason == "ambiguous_powertrain"
    plan = plan_query("2024款凯美瑞优惠2.5万元吗")
    assert plan.clarification is None
    assert plan.entities[0].powertrain is None


def test_history_requires_user_text_sequence_not_messages_or_single_string():
    with pytest.raises(TypeError):
        plan_query("它呢", "2024款凯美瑞")
    with pytest.raises(TypeError):
        plan_query("它呢", [{"role": "assistant", "content": "2024款凯美瑞"}])
    with pytest.raises(TypeError):
        plan_query(None)
