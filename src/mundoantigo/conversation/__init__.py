"""Conversa entre a sessao do Claude Code e o revisor, pela pagina da producao.

O Claude pergunta pela CLI (`mundoantigo perguntar`); a pergunta aparece no
topo da pagina com aviso do Windows; o revisor responde ali. A sessao fica
de vigia (`mundoantigo aguardar`) e age assim que chega uma resposta, um
pedido de refacao com motivo ou um comentario do corte final.
"""
