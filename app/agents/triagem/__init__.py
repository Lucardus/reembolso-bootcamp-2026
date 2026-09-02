"""Triagem — intenção, carteirinha e elegibilidade."""
import re
from datetime import date
from pydantic import BaseModel
from app.agents import AgentState
from app.tools import consultar_beneficiario, calcular_valor_reembolsado_ano
from app.llm import criar_llm
from app.rag import MotorRAG

llm = criar_llm()
motor_rag = MotorRAG()

ANO_REFERENCIA = date(2026, 8, 20).year

class AnaliseIntencao(BaseModel):
    """Classifica se a mensagem é uma pergunta ou fornecimento de informação."""
    eh_pergunta: bool
    topico_pergunta: str = ""
    informacao_fornecida: str = ""

def _analisar_intencao(msg: str) -> AnaliseIntencao:
    """Detecta se a mensagem contém pergunta ou fornecimento de dados."""
    prompt = f"""Classifique a mensagem abaixo:

Mensagem: "{msg}"

Eh uma pergunta (sobre sessões, limite, reembolso, valor, histórico, processo, etc.)?
Ou eh fornecimento de informação (carteirinha, documento, valor, data, etc.)?

Responda em JSON com eh_pergunta (true/false), topico_pergunta e informacao_fornecida."""
    
    resultado = llm.with_structured_output(AnaliseIntencao).invoke(prompt)
    return resultado

def ag_triagem(state: AgentState) -> AgentState:
    msg = state.get("mensagem_atual", "")
    historico = state.get("historico", [])
    
    # Se há anexo NÃO processado, deixa que ag_documento/ag_normas respondam
    # Apenas preserva anexo mas não gera resposta aqui
    if state.get("anexo_atual") and not state.get("anexo_processado"):
        state["anexo_salvo"] = state["anexo_atual"]
        # NÃO retorna aqui - deixa que continue para possível processamento de outro dados
        # mas vai ser roteado para ag_documento pelas regras do supervisor
    elif state.get("anexo_atual"):
        # Anexo já processado, preserva
        state["anexo_salvo"] = state["anexo_atual"]
    
    # NUNCA extrai carteirinha do anexo - APENAS da mensagem de texto
    if not state.get("carteirinha") and msg:
        match = re.search(r'\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{2,4}\b', msg)
        if match:
            carteirinha_limpa = re.sub(r'\D', '', match.group(0))
            if len(carteirinha_limpa) >= 10:
                state["carteirinha"] = carteirinha_limpa
    
    # Valida múltiplas carteirinhas - APENAS rejeita se há UMA estabelecida e vem OUTRA diferente
    if state.get("carteirinha") and msg:
        outras_carteirinhas = re.findall(r'\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{2,4}\b', msg)
        for c in outras_carteirinhas:
            c_limpa = re.sub(r'\D', '', c)
            if c_limpa != state["carteirinha"] and len(c_limpa) >= 10:
                # Marca flag de terceiro para que ag_normas nao repita
                state["_rejeitou_terceiro"] = True
                state["_contador_respostas_apos_terceiro"] = 0  # Reset contador
                # Recusa EXPLICITA (art. 8o): nao processamos pedido/consulta de
                # outra pessoa neste atendimento, orientamos abrir atendimento
                # proprio com a carteirinha dela, e deixamos claro que seguimos
                # com o titular - sem encerrar o atendimento em curso.
                state["resposta_texto"] = (
                    "Nao consigo analisar ou informar dados do pedido de outra pessoa "
                    "neste atendimento - inclusive de conjuge ou dependente. Ela "
                    "precisaria abrir um atendimento proprio com a carteirinha dela. "
                    "Aqui eu continuo te ajudando com o seu proprio pedido, tudo bem?"
                )
                state["_turno_finalizado"] = True
                return state
    
    # Consulta beneficiario se tiver carteirinha nova
    if state.get("carteirinha") and not state.get("dados_beneficiario"):
        dados = consultar_beneficiario(state["carteirinha"])
        if isinstance(dados, dict) and not dados.get("erro") and not dados.get("isError"):
            state["dados_beneficiario"] = dados
            state["valor_reembolsado_ano"] = calcular_valor_reembolsado_ano(
                state["carteirinha"], ANO_REFERENCIA
            )
            # O anexo pode ter chegado ANTES da carteirinha (fora de ordem).
            # Ele foi preservado em anexo_salvo mas nunca roteado para
            # ag_documento, porque o supervisor so despacha depois de ter
            # carteirinha. Agora que ela chegou, restaura anexo_atual a
            # partir do anexo_salvo para que ag_documento o processe neste
            # turno (ou no proximo, se ja passou o roteamento deste).
            if (
                not state.get("anexo_processado")
                and not state.get("anexo_atual")
                and state.get("anexo_salvo")
            ):
                state["anexo_atual"] = state["anexo_salvo"]
        else:
            state["pendencias"] = state.get("pendencias", []) + ["Beneficiário não localizado no sistema."]
            state["resposta_texto"] = "Desculpe, não consegui localizar sua carteirinha no sistema. Pode confirmar o número?"
            state["_turno_finalizado"] = True
            return state

    # Ha anexo pendente de processar neste turno? Calculado AQUI (depois da
    # eventual restauracao de anexo_salvo acima) e usado abaixo para NAO
    # finalizar o turno prematuramente quando o anexo ainda precisa passar
    # por ag_documento/ag_normas.
    anexo_pendente = bool(state.get("anexo_atual")) and not state.get("anexo_processado")
    
    # =============================================================
    # TURNO 1: Anexo sem mensagem, SEM carteirinha
    # =============================================================
    if not state.get("carteirinha") and not historico and not msg and state.get("anexo_atual"):
        state["resposta_texto"] = (
            "Oi! Recebi o anexo. Para poder analisá-lo e ajudá-lo com o reembolso, "
            "você poderia informar o número da sua carteirinha do plano?"
        )
        state["_turno_finalizado"] = True
        return state
    
    # =============================================================
    # PRIMEIRO TURNO: Sem carteirinha, sem histórico, com mensagem
    # =============================================================
    if not state.get("carteirinha") and not historico and msg:
        regras_processo = motor_rag.buscar_regras(
            "Como funciona o processo de reembolso? Qual é o fluxo básico? Qual é a documentação necessária?"
        )
        prompt = f"""O beneficiário enviou: "{msg}".

Explique de forma amigável como funciona o reembolso na SaúdeMais:
- Qual é o fluxo geral
- O que a gente precisa: carteirinha, documento, etc
- Qual é o próximo passo
- Peça o número da carteirinha

Baseie-se nas regras do sistema:
{regras_processo}

Gere uma resposta natural, NÃO use frases padrão. Seja breve e acessível."""
        resposta_llm = llm.invoke(prompt)
        state["resposta_texto"] = resposta_llm.content if hasattr(resposta_llm, "content") else str(resposta_llm)
        state["_turno_finalizado"] = True
        return state
    
    # =============================================================
    # TEM CARTEIRINHA + DADOS, MAS SEM DOCUMENTO PROCESSADO
    # =============================================================
    if state.get("carteirinha") and state.get("dados_beneficiario"):
        # Se documento foi rejeitado como INVALIDO e não há novo anexo chegando,
        # NÃO retorna silenciosamente — cai para o bloco abaixo que pede o
        # documento correto (com mensagem variada por contador).
        documento_invalido_sem_novo_anexo = (
            state.get("categoria_documento") == "INVALIDO"
            and not state.get("anexo_atual")
        )
        # Se já processou anexo (categoria VÁLIDA) ou há anexo novo chegando,
        # deixa ir para próximo agente (ag_documento ou ag_normas)
        if (state.get("anexo_processado") or state.get("categoria_documento")) and not documento_invalido_sem_novo_anexo:
            # Não preenche resposta: deixa para agentes seguintes
            return state
        
        # Turno onde recebeu carteirinha - confirma APENAS uma vez
        # (mas se HOUVER anexo pendente de processar neste mesmo turno -
        # ex.: o anexo chegou fora de ordem e foi restaurado acima - NAO
        # finaliza o turno aqui: o supervisor precisa rotear para
        # ag_documento/ag_normas para o anexo ser processado.)
        if not state.get("_confirmado_carteirinha") and msg and re.search(r'\d{4}', msg):
            dados_benef = state.get("dados_beneficiario", {})
            state["resposta_texto"] = (
                f"Perfeito! Confirmei seus dados:\n"
                f"- Nome: {dados_benef.get('nome')}\n"
                f"- Plano: {dados_benef.get('plano')}\n"
                f"- Status: {dados_benef.get('status')}\n\n"
                f"Agora, você poderia compartilhar o recibo ou documento do atendimento que quer reembolsar?"
            )
            state["_confirmado_carteirinha"] = True
            if anexo_pendente:
                # Ha anexo para processar - nao finaliza; ag_documento vai
                # gerar a resposta definitiva deste turno (confirmando o
                # recebimento do anexo em vez desta mensagem generica).
                state["resposta_texto"] = ""
            else:
                state["_turno_finalizado"] = True
                return state
        
        # Detecta e responde perguntas (mas somente se nao houver anexo
        # pendente de processar - senao a resposta definitiva do turno
        # deve vir de ag_documento/ag_normas, que tem o anexo em maos)
        if msg and not anexo_pendente:
            intencao = _analisar_intencao(msg)
            
            if intencao.eh_pergunta:
                topico = intencao.topico_pergunta.lower()
                dados_benef = state.get("dados_beneficiario", {})
                
                if "sessao" in topico or "terapia" in topico:
                    sessoes = dados_benef.get("sessoes_terapia_ano", 0)
                    state["resposta_texto"] = (
                        f"Você tem direito a {sessoes} sessões de terapia neste ano conforme seu plano {dados_benef.get('plano')}. "
                        f"Para analisarmos seu reembolso, você poderia compartilhar o recibo ou relatório do atendimento?"
                    )
                    state["_turno_finalizado"] = True
                    return state
                elif "limite" in topico or "teto" in topico or "máximo" in topico:
                    regras_limite = motor_rag.buscar_regras(
                        f"Qual é o limite máximo de reembolso anual ou por sessão para {dados_benef.get('plano', 'plano standard')}?"
                    )
                    prompt_limite = f"""O beneficiário perguntou sobre limite de reembolso.
Plano: {dados_benef.get('plano')}
Status: {dados_benef.get('status')}
Adesão desde: {dados_benef.get('data_adesao')}

Regras sobre limites:
{regras_limite}

Responda especificamente sobre o limite anual para esse plano. Seja breve."""
                    resposta_limite = llm.invoke(prompt_limite)
                    state["resposta_texto"] = resposta_limite.content if hasattr(resposta_limite, "content") else str(resposta_limite)
                    state["_turno_finalizado"] = True
                    return state
        
        # NÃO responda por anexo aqui - deixa ag_documento processar
        # ag_documento vai marcar anexo_processado, depois ag_normas responde
        # Isso evita ECO porque ag_triagem não retorna precocemente
        
        # Padrão genérico para turnos em sequência após rejeitar terceiro
        # (novamente, só finaliza se não houver anexo pendente de processar)
        if state.get("_rejeitou_terceiro") and not state.get("anexo_processado") and not anexo_pendente:
            # Incrementa contador cada vez que passa por aqui
            counter = state.get("_contador_respostas_apos_terceiro", 0) + 1
            state["_contador_respostas_apos_terceiro"] = counter
            
            respostas = [
                "Como você foi dizendo, vamos focar no seu pedido. Tem o documento do atendimento?",
                "E quanto ao seu atendimento? Já conseguiu o recibo ou relatório?",
                "Enquanto isso, você conseguiu localizar o documento do seu atendimento?",
                "Para prosseguirmos com a análise do seu reembolso, qual é a próxima informação que você tem?",
                "Pode compartilhar o documento do atendimento conosco?",
            ]
            
            # Usa contador para variar resposta
            idx = (counter - 1) % len(respostas)
            state["resposta_texto"] = respostas[idx]
            state["_turno_finalizado"] = True
            return state
        
        # Se documento foi rejeitado como INVALIDO, pede novo
        if state.get("categoria_documento") == "INVALIDO":
            contador = state.get("_contador_documentos_rejeitados", 0)
            respostas_rejeicao = [
                "O arquivo enviado não é um documento fiscal de despesa assistencial. Pode enviar o documento correto?",
                "Esse documento não é o que estamos procurando. Por favor, envie o comprovante do atendimento.",
                "Ainda não conseguimos processar esse arquivo. Pode tentar com outro documento?",
            ]
            idx = (contador - 1) % len(respostas_rejeicao)
            state["resposta_texto"] = respostas_rejeicao[idx]
            state["_turno_finalizado"] = True
            return state
        
        # Fallback para qualquer turno subsequente SEM anexo
        if not state.get("anexo_atual"):
            state["resposta_texto"] = (
                "Para continuarmos, você poderia nos enviar o documento do atendimento? "
                "Pode ser o recibo ou um relatório médico."
            )
            state["_turno_finalizado"] = True
        return state
    
    # Fallback final - só se não tiver anexo a processar
    if not state.get("resposta_texto") and not (state.get("anexo_atual") and not state.get("anexo_processado")):
        state["resposta_texto"] = "Entendi. Como posso ajudá-lo com seu pedido de reembolso?"
        state["_turno_finalizado"] = True
    
    return state
