import main
from extractor.scorer import filter_by_score
from parser.html_parser import extract_content


def test_main_uses_html_parser_extract_content():
    assert main.extract_content is extract_content


def test_main_uses_scorer_filter_by_score():
    assert main.filter_by_score is filter_by_score
