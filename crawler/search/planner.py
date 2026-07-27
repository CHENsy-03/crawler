import logging
from core.query_expander import QueryExpander

log = logging.getLogger('crawler.planner')


class QueryPlanner:
    """Multi-level search strategy planner. Generates keyword expansion plan,
    executes search level by level, stops when target results reached."""

    def __init__(self, expander=None):
        self.expander = expander or QueryExpander()
        self.stats = {}

    def plan(self, keyword):
        """Generate expansion plan: [(level, keyword), ...]."""
        queries = self.expander.expand(keyword)
        plan = [(i + 1, q) for i, q in enumerate(queries)]
        min_r = self.expander.min_results(keyword)
        self.stats = {'keyword': keyword, 'min_results': min_r, 'levels': len(plan), 'per_level': {}}
        log.info('Planner: keyword=%s min_results=%d levels=%d queries=%s', keyword, min_r, len(plan), queries)
        return plan

    def record_level(self, level, found, keyword):
        self.stats['per_level'][level] = {'keyword': keyword, 'found': found}

    def is_enough(self, total):
        return total >= self.stats.get('min_results', 5)

    def summary(self):
        lines = ['QueryPlanner summary:']
        for lv, info in sorted(self.stats.get('per_level', {}).items()):
            lines.append('  L%d: %s -> %d results' % (lv, info['keyword'], info['found']))
        return '\n'.join(lines)
