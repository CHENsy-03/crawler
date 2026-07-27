from parser.multi_strategy import clean_text


def clean_article(article):
    """清洗单篇文章各字段"""
    for field in ['title', 'summary', 'content', 'source']:
        if field in article:
            article[field] = clean_text(article[field])
    return article
