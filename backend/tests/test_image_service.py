"""Regression tests for model-image discovery without HTTP or LLM calls."""

from app.services.image_service import find_car_images, requested_image_count


def test_finds_multiple_models_in_one_message():
    images = find_car_images("请介绍凯美瑞、汉兰达和RAV4荣放，也把图片发给我")

    assert any("%E5%87%AF%E7%BE%8E%E7%91%9E" in url for url in images)
    assert any("%E6%B1%89%E5%85%B0%E8%BE%BE" in url for url in images)
    assert any("RAV4" in url for url in images)


def test_brand_prefixed_and_alias_queries_match_a_model():
    assert find_car_images("我想看广汽丰田凯美瑞的图片")
    assert any("RAV4" in url for url in find_car_images("RAV4 图片"))


def test_gallery_request_is_limited_and_has_popular_fallback():
    assert requested_image_count("介绍十款车，图片一起发") == 10

    images = find_car_images("介绍十款热门车，图片一起发", fallback_to_popular=True)
    assert 1 <= len(images) <= 10
