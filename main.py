import machine
from machine import Pin, ADC, PWM, SoftI2C
import time
import dht
import network
from umqtt.simple import MQTTClient
import json
import urequests
import ssd1306

# --- TELA OLED ---
i2c = SoftI2C(scl=Pin(32), sda=Pin(33))
tela = ssd1306.SSD1306_I2C(128, 64, i2c)

def mensagem_tela_cheia(linha1, linha2="", linha3=""):
    tela.fill(0)
    tela.text(linha1, 0, 10)
    tela.text(linha2, 0, 30)
    tela.text(linha3, 0, 50)
    tela.show()

mensagem_tela_cheia("Iniciando...", "Aguarde.")

# --- PINOS DOS SENTIDOS DA CASA ---
sensor_clima = dht.DHT22(Pin(18))
sensor_gas = ADC(Pin(34))
sensor_gas.atten(ADC.ATTN_11DB)
sensor_presenca = Pin(27, Pin.IN)
sensor_luz = ADC(Pin(35))
sensor_luz.atten(ADC.ATTN_11DB)

# --- PINOS DOS MÚSCULOS DA CASA ---
buzzer = PWM(Pin(5))
rele_luz = Pin(23, Pin.OUT)
rele_cortina = Pin(22, Pin.OUT)
rele_ar = Pin(21, Pin.OUT)
rele_janela = Pin(17, Pin.OUT)

# CONFIGURAÇÕES EXTERNAS E EMAIL
URL_PLANILHA = 'https://script.google.com/macros/s/AKfycbw9BJEqROgelaUtEUb5Mb1WVoPXY3Mt1mfrVjHDl172RtE6JUQZ61zIT-IFt4_sLmxh/exec'

# --- CONFIGURAÇÕES DA CASA ---
alarme_ligado = False
modo_ar_auto = True        
ar_desligado_manual = False  
temperatura_alvo = 22      
estado_janela_manual = 0
modo_atual = "PADRAO"

SERVIDOR_MENSAGENS = "broker.hivemq.com"
NOME_DA_PLACA = "casa_inteligente_gabriel"
CANAL_ENVIAR_DADOS = "gabriel/casa/sensores"
CANAL_RECEBER_COMANDOS = "gabriel/casa/comandos"

ultimo_aviso_enviado = 0
INTERVALO_AVISOS = 3000

tempo_ultimo_sheets = 0
soma_temperatura_dia = 0.0
soma_umidade_dia = 0.0
leituras_dia = 0
alerta_ativo = False  # A nossa nova trava de segurança contra atrasos

def conecta_wifi():
    print("Ligando antena Wi-Fi...")
    mensagem_tela_cheia("Conectando", "Wi-Fi...")
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if wifi.isconnected(): return
    wifi.connect("Wokwi-GUEST", "")
    while not wifi.isconnected():
        print(".", end="")
        time.sleep(0.5)
    print("\nWi-fi Conectado!")
    mensagem_tela_cheia("Wi-Fi", "Conectado!")
    time.sleep(1)

# --- OUVINDO OS BOTÕES DO NODE-RED ---
def ouve_node_red(topico, message):
    global alarme_ligado, modo_ar_auto, temperatura_alvo, estado_janela_manual, ar_desligado_manual, modo_atual
    
    comando = message.decode('utf-8')
    if len(comando) > 15 and "_" not in comando:
        return

    if comando == "alarme_on":
        alarme_ligado = True
        print("\n[ SEGURANÇA ] -> Alarme ATIVADO!")
    elif comando == "alarme_off":
        alarme_ligado = False
        desliga_barulho()
        print("\n[ SEGURANÇA ] -> Alarme DESATIVADO.")
    elif comando == "cinema":
        if rele_cortina.value() == 0:
            rele_cortina.value(1)
            rele_luz.value(0)
            modo_atual = "CINEMA"
            print("\n[ MODO CINEMA ] -> ATIVADO!")
        else:
            rele_cortina.value(0)
            rele_luz.value(1)
            modo_atual = "PADRAO"
            print("\n[ MODO CINEMA ] -> DESATIVADO!")
    elif comando == "luz_toggle":
        rele_luz.value(not rele_luz.value())
    elif comando == "cortina_toggle":
        rele_cortina.value(not rele_cortina.value())
    elif comando == "janela_toggle":
        estado_janela_manual = 1 if estado_janela_manual == 0 else 0
    elif comando == "ar_auto":
        modo_ar_auto = True
        ar_desligado_manual = False
    elif comando == "ar_off":
        modo_ar_auto = False
        ar_desligado_manual = True
    elif comando == "ar_mais":
        modo_ar_auto = False
        ar_desligado_manual = False
        temperatura_alvo += 1
    elif comando == "ar_menos":
        modo_ar_auto = False
        ar_desligado_manual = False
        temperatura_alvo -= 1

def prepara_mensageiro():
    carteiro = MQTTClient(NOME_DA_PLACA, SERVIDOR_MENSAGENS)
    carteiro.set_callback(ouve_node_red)
    carteiro.connect()
    carteiro.subscribe(CANAL_RECEBER_COMANDOS)
    return carteiro

def toca_sirene():
    buzzer.freq(1000)
    buzzer.duty(512)

def desliga_barulho():
    buzzer.duty(0)

def enviar_email_relatorio(media_t, media_u, qtd_leituras):
    print("\n[ E-MAIL ] -> INICIANDO ENVIO DE E-MAIL COM MÉDIAS...")
    mensagem_tela_cheia("Enviando...", "Relatorio", "por E-mail")
    try:
        dados_email = {
            "tipo": "email",
            "media_t": f"{media_t:.1f}",
            "media_u": f"{media_u:.1f}",
            "qtd_leituras": qtd_leituras
        }
        res_email = urequests.post(URL_PLANILHA, json=dados_email)
        res_email.close()
        print("[ E-MAIL ] -> >>> ENTREGUE COM SUCESSO! <<<")
        mensagem_tela_cheia("E-mail", "Enviado", "com Sucesso!")
        time.sleep(2)
    except Exception as e:
        print("[ E-MAIL ] -> Falha ao enviar:", e)
        mensagem_tela_cheia("Erro no", "E-mail!")
        time.sleep(2)

def atualiza_display_principal(status, motivo):
    tela.fill(0)
    tela.text("Status: " + status, 0, 0)
    tela.text(motivo, 0, 20)
    tela.text("Modo: " + modo_atual, 0, 45)
    tela.show()

desliga_barulho()
rele_luz.value(0); rele_cortina.value(0)
rele_ar.value(0); rele_janela.value(0)

conecta_wifi()
mensageiro = prepara_mensageiro()

print("=======================================")
print("       CASA INTELIGENTE RODANDO        ")
print("=======================================")

while True:
    try:
        agora = time.ticks_ms()
        mensageiro.check_msg()

        sensor_clima.measure()
        temperatura = sensor_clima.temperature()
        umidade = sensor_clima.humidity()
        nivel_gas = sensor_gas.read()
        movimento = sensor_presenca.value()

        # --- DETECTAR MOTIVOS DE SEGURANÇA ---
        aviso_seguranca = "Nenhum Alerta"
        motivo_tela = "Tudo OK"
        status_casa = "SEGURA"

        if nivel_gas > 2000:
            aviso_seguranca = "Alto Nivel de Gas Detectado!"
            motivo_tela = "Vazamento Gas!"
            status_casa = "PERIGO"
        elif temperatura > 45:
            aviso_seguranca = "Temperatura Critica / Incendio!"
            motivo_tela = "Fogo/Calor!"
            status_casa = "PERIGO"
        elif alarme_ligado and movimento == 1:
            aviso_seguranca = "Invasor Detectado no Ambiente!"
            motivo_tela = "INVASOR!"
            status_casa = "PERIGO"

        atualiza_display_principal(status_casa, motivo_tela)

        # --- VERIFICADOR IMEDIATO DE PERIGO (FURA FILA) ---
        if status_casa == "PERIGO":
            if not alerta_ativo:
                alerta_ativo = True
                print(f"\n[ ALERTA URGENTE ] -> {aviso_seguranca} -> Disparando e-mail imediatamente!")
                if URL_PLANILHA != '':
                    try:
                        dados_urgentes = {
                            "tipo": "leitura", 
                            "temperatura": temperatura, 
                            "umidade": umidade,
                            "gas": nivel_gas,
                            "aviso_seguranca": aviso_seguranca
                        }
                        res_urgente = urequests.post(URL_PLANILHA, json=dados_urgentes)
                        res_urgente.close()
                        print("[ ALERTA URGENTE ] -> Enviado com sucesso para a nuvem!")
                    except Exception as erro_envio:
                        print("[ ALERTA URGENTE ] -> Erro ao tentar enviar:", erro_envio)
        else:
            alerta_ativo = False # Se a casa desarmar o perigo, destranca a linha para o próximo evento

        # --- PROTEÇÃO MÁXIMA REAL ---
        if temperatura > 45 or nivel_gas > 2000:
            toca_sirene()
            rele_janela.value(1)
            rele_ar.value(0)    
        else:
            if not (alarme_ligado and movimento == 1):
                desliga_barulho()
            rele_janela.value(estado_janela_manual)
            
            if modo_ar_auto:
                if temperatura > 28:
                    rele_ar.value(1)
                elif temperatura < 17:
                    rele_ar.value(1)
                elif 20 <= temperatura <= 24:
                    rele_ar.value(0)
            elif ar_desligado_manual:
                rele_ar.value(0)
            else:
                if temperatura >= (temperatura_alvo + 1) or temperatura <= (temperatura_alvo - 1):
                    rele_ar.value(1)
                else:
                    rele_ar.value(0)

            if alarme_ligado and movimento == 1:
                toca_sirene()

        # --- ENVIO DE ROTINA PARA A PLANILHA DO GOOGLE (A CADA 20 SEGUNDOS) ---
        if time.ticks_diff(agora, tempo_ultimo_sheets) > 20000:
            tempo_ultimo_sheets = agora
            
            print(f"\n[ PLANILHA ] -> Enviando leitura para o Google Sheets... (Lote {leituras_dia + 1}/6)")
            if URL_PLANILHA != '':
                try:
                    dados_enviar = {
                        "tipo": "leitura", 
                        "temperatura": temperatura, 
                        "umidade": umidade,
                        "gas": nivel_gas,
                        "aviso_seguranca": aviso_seguranca
                    }
                    res_sheets = urequests.post(URL_PLANILHA, json=dados_enviar)
                    res_sheets.close()
                    print("[ PLANILHA ] -> Sincronização OK!")
                except Exception as e:
                    print("[ PLANILHA ] -> Erro na sincronização:", e)
            
            soma_temperatura_dia += temperatura
            soma_umidade_dia += umidade
            leituras_dia += 1
            
            if leituras_dia >= 6:
                media_temp_calculada = soma_temperatura_dia / leituras_dia
                media_umid_calculada = soma_umidade_dia / leituras_dia
                enviar_email_relatorio(media_temp_calculada, media_umid_calculada, leituras_dia)
                
                soma_temperatura_dia = 0.0
                soma_umidade_dia = 0.0
                leituras_dia = 0

        # --- RESUMO NO TERMINAL E ENVIO PARA O NODE-RED ---
        if time.ticks_diff(agora, ultimo_aviso_enviado) >= INTERVALO_AVISOS:
            if modo_ar_auto:
                modo_ar = "AUTO"
            elif ar_desligado_manual:
                modo_ar = "DESLIGADO MANUAL"
            else:
                modo_ar = "MANUAL ({}°C)".format(temperatura_alvo)
                
            estado_ar = "LIGADO" if rele_ar.value() == 1 else "DESLIGADO"
            estado_luz = "LIGADA" if rele_luz.value() == 1 else "DESLIGADA"
            estado_cortina = "FECHADA" if rele_cortina.value() == 1 else "ABERTA"
            estado_alarme_texto = "ATIVADO" if alarme_ligado else "DESATIVADO"

            print("\n--- RESUMO DA CASA ---")
            print(f"Clima: {temperatura}°C | Umidade: {umidade}% | Gás: {nivel_gas}")
            print(f"Ar Condicionado: {estado_ar} [{modo_ar}]")
            print(f"Luz: {estado_luz} | Cortina: {estado_cortina} | Modo: {modo_atual}")
            print(f"Segurança: {estado_alarme_texto} | Alerta: {aviso_seguranca}")
            print("----------------------")

            pacote_de_dados = {
                "temperatura_atual": temperatura,
                "nivel_gas": nivel_gas,
                "movimento": movimento,
                "alarme_armado": alarme_ligado,
                "ar_ligado": rele_ar.value(),
                "janela_aberta": rele_janela.value(),
                "modo_ar_auto": modo_ar_auto,
                "ar_desligado_manual": ar_desligado_manual,
                "temperatura_alvo": temperatura_alvo,
                "aviso_seguranca": aviso_seguranca,
                "modo_atual": modo_atual
            }
            mensagem_texto = json.dumps(pacote_de_dados)
            # umqtt.simple.MQTTClient.publish(topic, msg) expects the message
            # as a positional argument, not a keyword. Send the JSON string.
            mensageiro.publish(CANAL_ENVIAR_DADOS, mensagem_texto)
            ultimo_aviso_enviado = agora

    except Exception as erro:
        print("Tropeço geral no sistema:", erro)
    
    time.sleep(0.2)