"""Documento — categorização e extração.

Recebe o anexo em base64, extrai o texto (PDF ou OCR na foto), classifica numa
das 7 categorias e extrai os campos que a análise precisa.

Três situações parecem iguais e não são: documento fiscal com campo faltando,
documento fiscal de despesa não coberta e arquivo que não é documento fiscal.
A base de conhecimento diz o tratamento de cada uma.
"""
