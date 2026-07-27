import json
from pathlib import Path
from datetime import datetime


def save_json(articles, output_dir, prefix='result'):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fp = output_dir / f'{prefix}_{ts}.json'
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return fp


def save_csv(articles, output_dir, prefix='result'):
    import csv
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fp = output_dir / f'{prefix}_{ts}.csv'
    fields = ['title', 'url', 'publish_date', 'source', 'score', 'matched_keywords', 'summary', 'content']
    with open(fp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for a in articles:
            row = {k: a.get(k, '') for k in fields}
            if isinstance(row.get('matched_keywords'), list):
                row['matched_keywords'] = ';'.join(row['matched_keywords'])
            w.writerow(row)
    return fp


def save_results(articles, output_dir, prefix='result'):
    jp = save_json(articles, output_dir, prefix)
    cp = save_csv(articles, output_dir, prefix)
    return jp, cp
