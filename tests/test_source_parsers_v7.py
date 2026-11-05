import threading
import pytest
from grangerpet.web_scraping import parse_csv,parse_pdf,parser_contract,parse_xml


def test_csv_utf8_fields_and_formula_are_inert_and_rows_are_bounded():
    result=parse_csv('Название;Значение\n"Компания; А";"=1+2"\nКазахстан;БИН\n','https://example.org/data.csv')
    assert result['tables'][0]['headers']==['Название','Значение']
    assert result['tables'][0]['rows'][0]==['Компания; А','=1+2']
    assert parser_contract('text/csv; charset=UTF-8')['version']=='granger-csv/1'
    bounded=parse_csv('name,value\n'+''.join(f'{i},text\n' for i in range(300)),'https://example.org')
    assert len(bounded['structured_data']['records'])==100 and bounded['structured_data']['truncated']


def test_rss_and_xml_do_not_resolve_external_entities():
    with pytest.raises(ValueError,match='entities'):
        parse_xml('<!DOCTYPE x [<!ENTITY a SYSTEM "file:///C:/private">]><x>&a;</x>','https://example.org',lambda x:x)
    result=parse_xml('<rss><channel><title>Публикации</title><item><title>Новость</title><link>https://example.org/a</link></item></channel></rss>','https://example.org',lambda x:x)
    assert result['structured_data']['records'][0]['title']=='Новость'
    assert parser_contract('application/rss+xml')['version']=='granger-rss-atom/2'


def pdf_bytes():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QBuffer,QIODevice
    from PySide6.QtGui import QPdfWriter,QPainter
    app=QApplication.instance() or QApplication([])
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer=QPdfWriter(buffer);writer.setResolution(72);writer.setTitle('Проверка PDF')
    painter=QPainter(writer);painter.drawText(30,60,'Public document / Публичный документ');painter.end();del writer
    result=bytes(buffer.data());buffer.close()
    return result,app


def test_real_qt_pdf_text_extraction_and_no_ocr_claim():
    raw,app=pdf_bytes();result=parse_pdf(raw,'https://example.org/document.pdf')
    assert 'Public document' in result['text'] and 'Публичный документ' in result['text']
    assert result['structured_data']['page_count']==1 and result['structured_data']['pages_extracted']==1
    assert result['title']=='Проверка PDF' and result['links']==[]
    assert 'OCR' in result['render_warnings'][0]


def test_pdf_invalid_and_cancelled_are_not_successful_empty_parses():
    with pytest.raises(ValueError):parse_pdf(b'not a pdf','https://example.org')
    raw,app=pdf_bytes();cancel=threading.Event();cancel.set()
    with pytest.raises(ValueError,match='cancelled'):parse_pdf(raw,'https://example.org',cancel_event=cancel)
