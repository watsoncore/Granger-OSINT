import pytest
from grangerpet.browser_policy import validate_search_post


SEARCH='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
PAGE='https://eutils.ncbi.nlm.nih.gov/'
FORM='application/x-www-form-urlencoded'


def test_public_literature_query_preserves_entered_term_and_fixed_database():
    assert validate_search_post(PAGE,SEARCH,FORM,'db=pubmed&term=open+data&retmax=1','open data')==SEARCH


@pytest.mark.parametrize('page,url,ctype,body',[
    ('https://example.org/',SEARCH,FORM,'term=open+data'),
    (PAGE,SEARCH+'?api_key=hidden',FORM,'term=open+data'),
    (PAGE,SEARCH.replace('esearch','epost'),FORM,'term=open+data'),
    (PAGE,SEARCH,'multipart/form-data','term=open+data'),
    (PAGE,SEARCH,FORM,'term=somebody+else'),
    (PAGE,SEARCH,FORM,'term=open+data&term=open+data'),
    (PAGE,SEARCH,FORM,'term=open+data&cookie=hidden'),
    (PAGE,SEARCH,FORM,'term=open+data&retmax=9999'),
])
def test_page_cannot_authorize_other_data_or_consequential_post(page,url,ctype,body):
    with pytest.raises(ValueError):validate_search_post(page,url,ctype,body,'open data')
