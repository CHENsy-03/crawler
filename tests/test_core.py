import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestImports(unittest.TestCase):
    def test_httpx_imports(self):
        from httpx import fetch, post_json, get_json, rate_limiter_manager, breaker_manager
        self.assertTrue(True)

    def test_parser_imports(self):
        from parser.multi_strategy import clean_text, normalize_date
        from parser.html_parser import extract_title, extract_content
        self.assertEqual(clean_text('<em>low</em> economy'), 'low economy')
        self.assertEqual(normalize_date('日期：2025年6月7日'), '2025-06-07')

    def test_scorer(self):
        from extractor.scorer import score_article
        r = score_article({'title': '低空经济政策', 'content': '发展低空经济', 'url': 'http://test.com/art_1'}, ('低空经济',))
        self.assertTrue(r['passed'])
        self.assertGreater(r['score'], 0)

    def test_plugins_registry(self):
        from plugins import get
        self.assertIsNotNone(get('trs_json'))
        self.assertIsNotNone(get('jpaas_jsearch'))

    def test_metrics_collector(self):
        from monitor.metrics import get_collector
        c = get_collector()
        c.inc('test_counter', 3)
        snap = c.snapshot()
        self.assertIn('test_counter', snap['counters'])

    def test_config_loading(self):
        from main import load_config
        cfg = load_config('czj_beijing')
        self.assertEqual(cfg['name'], '北京市财政局')
        self.assertIn('search', cfg)
        self.assertIn('score', cfg)


if __name__ == '__main__':
    unittest.main()
