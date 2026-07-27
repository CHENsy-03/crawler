import json
from pathlib import Path


class QueryExpander:

    def __init__(self):
        path = Path("config/keywords.json")
        if path.exists():
            self.rules = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        else:
            self.rules = {}

    def expand(self, keyword):
        rule = self.rules.get(keyword)
        if not rule:
            return [keyword]
        return rule.get(
            "expand",
            [keyword]
        )

    def min_results(self, keyword):
        rule = self.rules.get(keyword)
        if not rule:
            return 5
        return rule.get(
            "min_results",
            5
        )
