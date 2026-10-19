"""文档文件名消毒：路径穿越防护。"""

from app.agents.nodes.document_nodes import _sanitize_filename_component


def test_sanitize_blocks_traversal_sequences():
    assert ".." not in _sanitize_filename_component("../../etc/passwd")
    assert "/" not in _sanitize_filename_component("a/b")
    assert "\\" not in _sanitize_filename_component("a\\b")


def test_sanitize_keeps_normal_chinese_and_alnum():
    assert _sanitize_filename_component("张三科技") == "张三科技"
    assert _sanitize_filename_component("Acme-2024_v2") == "Acme-2024_v2"


def test_sanitize_falls_back_to_default():
    assert _sanitize_filename_component("", "文档") == "文档"
    assert _sanitize_filename_component("///", "文档") == "文档"
    assert _sanitize_filename_component(None, "文档") == "文档"


def test_sanitize_truncates_long_values():
    assert len(_sanitize_filename_component("长" * 200, "文档")) <= 30
